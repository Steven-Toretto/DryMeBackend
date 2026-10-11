"""
Run with:  python manage.py test dryMe.test_wallet_api -v 2

Fixtures (from test_wallet.WalletTestCase): 4 kg x KES 100 = KES 400 order,
10% commission (KES 360 earned), M-Pesa payout fee KES 10, bank fee KES 50.
"""
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.db import transaction
from rest_framework.test import APIClient

from .models import Payout, User, Wallet
from .services.wallet import (
    _apply,
    get_locked_wallet,
    mark_payout_paid,
    request_payout,
    settle_order,
)
from .test_wallet import WalletTestCase
from .throttles import PayoutRequestThrottle

WALLET = "/api/owner/wallet/"
TRANSACTIONS = "/api/owner/wallet/transactions/"
PAYOUTS = "/api/owner/payouts/"
QUOTE = "/api/owner/payouts/quote/"


class WalletApiTestCase(WalletTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()  # throttle counters live in the cache and user ids get reused between tests
        self.other_owner = User.objects.create_user(
            username="owner2", email="owner2@test.com", password="pass12345",
            role="owner", phone="0733345678", location="Nairobi",
        )

    def api(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def earn(self):
        """One fully settled order: +KES 360 for the shop owner."""
        order = self.make_order()
        self.mark_paid(order)
        self.mark_completed(order)
        settle_order(order.pk)
        return order

    def fund_other(self, amount):
        with transaction.atomic():
            wallet = get_locked_wallet(self.other_owner)
            _apply(wallet, "adjustment", Decimal(amount))


# =====================================================================
# who may call what
# =====================================================================
class PermissionTests(WalletApiTestCase):

    def test_anonymous_gets_401_everywhere(self):
        client = self.api()
        for url in (WALLET, TRANSACTIONS, PAYOUTS, QUOTE):
            self.assertEqual(client.get(url).status_code, 401, url)
        self.assertEqual(client.post(PAYOUTS, {}, format="json").status_code, 401)

    def test_customers_get_403_everywhere(self):
        client = self.api(self.customer)
        for url in (WALLET, TRANSACTIONS, PAYOUTS, QUOTE):
            self.assertEqual(client.get(url).status_code, 403, url)
        resp = client.post(PAYOUTS, {"amount": "100", "method": "mpesa", "destination": "0712345678"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Payout.objects.count(), 0)


# =====================================================================
# GET owner/wallet/
# =====================================================================
class WalletSummaryTests(WalletApiTestCase):

    def test_new_owner_sees_zeroes_and_the_fee_table(self):
        data = self.api(self.owner).get(WALLET).json()
        for key in ("balance", "pending_earnings", "lifetime_earned", "total_withdrawn", "total_fees_paid"):
            self.assertEqual(Decimal(data[key]), Decimal("0"), key)
        self.assertIsNone(data["open_payout"])
        self.assertEqual(Decimal(data["commission_rate"]), Decimal("0.10"))
        self.assertEqual(Decimal(data["payout_fees"]["mpesa"]), Decimal("10"))
        self.assertEqual(Decimal(data["payout_fees"]["bank"]), Decimal("50"))
        self.assertFalse(Wallet.objects.exists())  # a GET never creates anything

    def test_balance_and_lifetime_after_earning(self):
        self.earn()
        data = self.api(self.owner).get(WALLET).json()
        self.assertEqual(Decimal(data["balance"]), Decimal("360.00"))
        self.assertEqual(Decimal(data["lifetime_earned"]), Decimal("360.00"))

    def test_pending_earnings_are_net_of_commission_and_only_for_unsettled_paid_orders(self):
        in_progress = self.make_order()
        self.mark_paid(in_progress)                      # paid, still pending -> counts (360)
        unpaid = self.make_order()                       # unpaid -> doesn't count
        declined = self.make_order()
        self.mark_paid(declined)
        declined.status = "declined"
        declined.save(update_fields=["status"])          # dead end -> doesn't count
        self.earn()                                      # already settled -> in balance, not pending

        data = self.api(self.owner).get(WALLET).json()

        self.assertEqual(Decimal(data["pending_earnings"]), Decimal("360.00"))
        self.assertEqual(Decimal(data["balance"]), Decimal("360.00"))

    def test_withdrawn_totals_and_open_payout(self):
        self.fund("1000")
        first = request_payout(self.owner, "500", "mpesa", "0712345678")
        mark_payout_paid(first.pk, self.owner, "RKT12345")

        data = self.api(self.owner).get(WALLET).json()
        self.assertEqual(Decimal(data["total_withdrawn"]), Decimal("500.00"))
        self.assertEqual(Decimal(data["total_fees_paid"]), Decimal("10.00"))
        self.assertIsNone(data["open_payout"])

        second = request_payout(self.owner, "100", "mpesa", "0712345678")
        data = self.api(self.owner).get(WALLET).json()
        self.assertEqual(data["open_payout"]["id"], second.pk)
        self.assertEqual(data["open_payout"]["status"], "requested")

    def test_each_owner_only_sees_their_own_money(self):
        self.earn()
        data = self.api(self.other_owner).get(WALLET).json()
        self.assertEqual(Decimal(data["balance"]), Decimal("0"))
        self.assertEqual(Decimal(data["lifetime_earned"]), Decimal("0"))


# =====================================================================
# GET owner/wallet/transactions/
# =====================================================================
class TransactionsTests(WalletApiTestCase):

    def test_lists_only_my_ledger_newest_first_with_labels(self):
        self.earn()
        self.fund("1000")  # a second ledger row (adjustment)
        self.fund_other("777")

        body = self.api(self.owner).get(TRANSACTIONS).json()

        self.assertEqual(body["count"], 2)
        rows = body["results"]
        self.assertEqual([r["type"] for r in rows], ["adjustment", "sale_credit"])
        self.assertEqual(rows[1]["type_label"], "Sale credit")
        self.assertEqual(Decimal(rows[1]["amount"]), Decimal("360.00"))
        self.assertEqual(Decimal(rows[0]["balance_after"]), Decimal("1360.00"))
        self.assertTrue(all(Decimal(r["amount"]) != Decimal("777") for r in rows))

    def test_withdrawals_show_as_negative_rows(self):
        self.fund("1000")
        request_payout(self.owner, "500", "mpesa", "0712345678")
        rows = self.api(self.owner).get(TRANSACTIONS).json()["results"]
        self.assertEqual(rows[0]["type"], "payout_hold")
        self.assertEqual(Decimal(rows[0]["amount"]), Decimal("-500.00"))
        self.assertIsNotNone(rows[0]["payout"])


# =====================================================================
# POST / GET owner/payouts/
# =====================================================================
class PayoutRequestApiTests(WalletApiTestCase):

    def post(self, user=None, **body):
        payload = {"amount": "500", "method": "mpesa", "destination": "0712 345 678"}
        payload.update(body)
        return self.api(user or self.owner).post(PAYOUTS, payload, format="json")

    def test_success_returns_the_payout_and_the_new_balance(self):
        self.fund("1000")
        resp = self.post()

        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(Decimal(body["balance"]), Decimal("500.00"))
        payout = body["payout"]
        self.assertEqual(Decimal(payout["amount"]), Decimal("500.00"))
        self.assertEqual(Decimal(payout["fee"]), Decimal("10.00"))
        self.assertEqual(Decimal(payout["net_amount"]), Decimal("490.00"))
        self.assertEqual(payout["destination"], "254712345678")
        self.assertEqual(payout["status"], "requested")
        self.assertEqual(payout["status_label"], "Requested")

    def test_client_cannot_choose_the_fee_net_amount_or_status(self):
        self.fund("1000")
        resp = self.post(fee="0", net_amount="500", status="paid", reference="HACK", owner=self.other_owner.pk)
        self.assertEqual(resp.status_code, 201)
        payout = Payout.objects.get()
        self.assertEqual(payout.fee, Decimal("10.00"))
        self.assertEqual(payout.net_amount, Decimal("490.00"))
        self.assertEqual(payout.status, "requested")
        self.assertEqual(payout.reference, "")
        self.assertEqual(payout.owner_id, self.owner.pk)

    def test_numeric_json_amount_is_accepted(self):
        self.fund("1000")
        self.assertEqual(self.post(amount=500).status_code, 201)

    def test_no_minimum_a_tiny_withdrawal_works(self):
        self.fund("100")
        resp = self.post(amount="50")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Decimal(resp.json()["payout"]["net_amount"]), Decimal("40.00"))

    def test_bank_payout(self):
        self.fund("1000")
        resp = self.post(method="bank", destination="KCB 1234567890 Jane Doe")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Decimal(resp.json()["payout"]["fee"]), Decimal("50.00"))

    def test_errors_are_400_with_a_single_error_string(self):
        self.fund("100")
        cases = [
            (dict(amount="10"), "transfer fee"),                       # not above the fee
            (dict(amount="101"), "Insufficient balance"),
            (dict(amount="12.5"), "whole number"),
            (dict(amount="0"), "greater than zero"),
            (dict(amount="abc"), "valid amount"),
            (dict(destination="12345"), "valid Safaricom number"),
            (dict(method="paypal"), "M-Pesa or bank"),
            (dict(destination=""), "where to send"),
            (dict(amount=""), "Enter an amount"),
        ]
        for body, expected in cases:
            resp = self.post(**body)
            self.assertEqual(resp.status_code, 400, body)
            self.assertIn(expected, resp.json()["error"], body)
        self.assertEqual(Payout.objects.count(), 0)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("100.00"))

    def test_missing_fields_are_400(self):
        resp = self.api(self.owner).post(PAYOUTS, {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_only_one_open_payout(self):
        self.fund("1000")
        self.assertEqual(self.post(amount="100").status_code, 201)
        resp = self.post(amount="100")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already have a withdrawal in progress", resp.json()["error"])
        self.assertEqual(Payout.objects.count(), 1)

    def test_history_lists_only_my_payouts_newest_first(self):
        self.fund("1000")
        self.fund_other("1000")
        first = request_payout(self.owner, "100", "mpesa", "0712345678")
        mark_payout_paid(first.pk, self.owner, "RKT1")
        second = request_payout(self.owner, "200", "mpesa", "0712345678")
        request_payout(self.other_owner, "300", "mpesa", "0733345678")

        body = self.api(self.owner).get(PAYOUTS).json()

        self.assertEqual(body["count"], 2)
        self.assertEqual([p["id"] for p in body["results"]], [second.pk, first.pk])
        self.assertEqual(body["results"][1]["reference"], "RKT1")
        self.assertEqual(body["results"][1]["status"], "paid")

    def test_rejected_payout_shows_the_reason_to_the_owner(self):
        from .services.wallet import reject_payout
        self.fund("1000")
        payout = request_payout(self.owner, "100", "mpesa", "0712345678")
        reject_payout(payout.pk, self.owner, "Number didn't match your M-Pesa name")
        row = self.api(self.owner).get(PAYOUTS).json()["results"][0]
        self.assertEqual(row["status"], "rejected")
        self.assertIn("didn't match", row["reject_reason"])

    def test_payouts_endpoint_does_not_accept_put_patch_delete(self):
        client = self.api(self.owner)
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(client, method)(PAYOUTS).status_code, 405, method)


class ThrottleTests(WalletApiTestCase):

    def test_withdrawal_requests_are_rate_limited_per_user(self):
        owner_client = self.api(self.owner)
        junk = {"amount": "abc", "method": "mpesa", "destination": "0712345678"}

        with mock.patch.object(PayoutRequestThrottle, "rate", "2/hour"):
            self.assertEqual(owner_client.post(PAYOUTS, junk, format="json").status_code, 400)
            self.assertEqual(owner_client.post(PAYOUTS, junk, format="json").status_code, 400)
            self.assertEqual(owner_client.post(PAYOUTS, junk, format="json").status_code, 429)

            # reading history isn't limited, and another owner has their own allowance
            self.assertEqual(owner_client.get(PAYOUTS).status_code, 200)
            self.assertEqual(self.api(self.other_owner).post(PAYOUTS, junk, format="json").status_code, 400)


# =====================================================================
# GET owner/payouts/quote/
# =====================================================================
class QuoteTests(WalletApiTestCase):

    def test_quote_uses_the_server_side_fee(self):
        client = self.api(self.owner)

        mpesa = client.get(QUOTE, {"amount": "500", "method": "mpesa"}).json()
        self.assertEqual(Decimal(mpesa["fee"]), Decimal("10"))
        self.assertEqual(Decimal(mpesa["net_amount"]), Decimal("490"))
        self.assertEqual(Decimal(mpesa["amount"]), Decimal("500"))

        bank = client.get(QUOTE, {"amount": "500", "method": "bank"}).json()
        self.assertEqual(Decimal(bank["net_amount"]), Decimal("450"))

    def test_method_defaults_to_mpesa(self):
        data = self.api(self.owner).get(QUOTE, {"amount": "100"}).json()
        self.assertEqual(data["method"], "mpesa")
        self.assertEqual(Decimal(data["net_amount"]), Decimal("90"))

    def test_quote_matches_what_a_real_request_then_does(self):
        self.fund("1000")
        quote = self.api(self.owner).get(QUOTE, {"amount": "333", "method": "mpesa"}).json()
        real = request_payout(self.owner, "333", "mpesa", "0712345678")
        self.assertEqual(Decimal(quote["fee"]), real.fee)
        self.assertEqual(Decimal(quote["net_amount"]), real.net_amount)

    def test_invalid_quotes_are_400(self):
        client = self.api(self.owner)
        for params in ({}, {"amount": "abc"}, {"amount": "10"}, {"amount": "12.5"}, {"amount": "500", "method": "paypal"}):
            resp = client.get(QUOTE, params)
            self.assertEqual(resp.status_code, 400, params)
            self.assertIn("error", resp.json())

    def test_quote_never_touches_money(self):
        self.fund("1000")
        self.api(self.owner).get(QUOTE, {"amount": "500", "method": "mpesa"})
        self.assertEqual(Payout.objects.count(), 0)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("1000.00"))
"""
Run with:  python manage.py test dryMe.test_wallet -v 2

Fixtures: 4 kg x KES 100 = KES 400 order, 10% commission (KES 360 to owner),
M-Pesa payout fee KES 10, bank fee KES 50.
"""
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from .models import Order, PaymentAttempt, Payout, Service, Shop, User, Wallet, WalletTransaction
from .services import payments
from .services.wallet import (
    _apply,
    approve_payout,
    fail_payout,
    get_locked_wallet,
    ledger_total,
    mark_payout_paid,
    normalize_msisdn,
    quote_payout,
    reject_payout,
    request_payout,
    settle_order,
)

TEST_SETTINGS = dict(
    COMMISSION_RATE=Decimal("0.10"),
    PAYOUT_FEES={"mpesa": Decimal("10"), "bank": Decimal("50")},
    PAYOUT_MIN_NET=Decimal("1"),
    MPESA_CALLBACK_SECRET="test-secret",
    MPESA_CALLBACK_ALLOWED_IPS=[],
)


def stk_payload(checkout_id, *, amount=None, receipt="QWE123ABC", code=0):
    cb = {
        "MerchantRequestID": "m-1",
        "CheckoutRequestID": checkout_id,
        "ResultCode": code,
        "ResultDesc": "processed",
    }
    if code == 0:
        cb["CallbackMetadata"] = {
            "Item": [
                {"Name": "Amount", "Value": amount},
                {"Name": "MpesaReceiptNumber", "Value": receipt},
                {"Name": "TransactionDate", "Value": 20260101120000},
                {"Name": "PhoneNumber", "Value": 254712345678},
            ]
        }
    return {"Body": {"stkCallback": cb}}


@override_settings(**TEST_SETTINGS)
class WalletTestCase(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="pass12345",
            role="owner", phone="0712345678", location="Nairobi",
        )
        self.customer = User.objects.create_user(
            username="cust", email="cust@test.com", password="pass12345",
            role="customer", phone="0722345678", location="Nairobi",
        )
        self.shop = Shop.objects.create(owner=self.owner, name="Suds", location="Kilimani", description="x")
        self.service = Service.objects.create(
            shop=self.shop, name="Wash", pricing_type="per_kg", price=Decimal("100.00"),
        )

    # ---- helpers ----
    def make_order(self, kg="4"):
        return Order.objects.create(
            user=self.customer, shop=self.shop, service=self.service, weight=Decimal(kg),
        )

    def mark_paid(self, order):
        order.payment_status = "paid"
        order.amount_paid = Decimal(order.payable_amount())
        order.save(update_fields=["payment_status", "amount_paid"])

    def mark_completed(self, order):
        order.status = "completed"
        order.save(update_fields=["status"])

    def pending_order(self, checkout="ws_CO_1", kg="4"):
        order = self.make_order(kg)
        order.payment_status = "pending_payment"
        order.save(update_fields=["payment_status"])
        PaymentAttempt.objects.create(
            order=order, checkout_request_id=checkout, amount=Decimal(order.payable_amount()),
        )
        return order

    def fund(self, amount):
        with transaction.atomic():
            wallet = get_locked_wallet(self.owner)
            _apply(wallet, "adjustment", Decimal(amount), note="test funding")
        return Wallet.objects.get(owner=self.owner)

    def assertLedgerBalanced(self):
        wallet = Wallet.objects.get(owner=self.owner)
        self.assertEqual(ledger_total(wallet), wallet.balance)


# =====================================================================
# settle_order
# =====================================================================
class SettleOrderTests(WalletTestCase):

    def test_credits_net_of_commission_once_paid_and_completed(self):
        order = self.make_order()
        self.mark_paid(order)
        self.assertIsNone(settle_order(order.pk))  # paid but not completed
        self.assertFalse(Wallet.objects.filter(owner=self.owner).exists())

        self.mark_completed(order)
        tx = settle_order(order.pk)

        self.assertEqual(tx.type, "sale_credit")
        self.assertEqual(tx.amount, Decimal("360.00"))
        order.refresh_from_db()
        self.assertEqual(order.commission_amount, Decimal("40.00"))
        self.assertEqual(order.owner_earnings, Decimal("360.00"))
        self.assertIsNotNone(order.settled_at)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("360.00"))
        self.assertLedgerBalanced()

    def test_completed_but_unpaid_does_not_credit(self):
        order = self.make_order()
        self.mark_completed(order)
        self.assertIsNone(settle_order(order.pk))
        self.assertFalse(WalletTransaction.objects.exists())

    def test_settling_twice_credits_once(self):
        order = self.make_order()
        self.mark_paid(order)
        self.mark_completed(order)
        settle_order(order.pk)
        self.assertIsNone(settle_order(order.pk))
        self.assertEqual(WalletTransaction.objects.filter(type="sale_credit").count(), 1)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("360.00"))

    def test_declined_paid_order_never_credits(self):
        order = self.make_order()
        self.mark_paid(order)
        order.status = "declined"
        order.save(update_fields=["status"])
        self.assertIsNone(settle_order(order.pk))
        self.assertFalse(WalletTransaction.objects.exists())

    def test_commission_is_taken_on_amount_actually_paid(self):
        order = self.make_order(kg="4.5")  # 450.00
        self.assertEqual(order.payable_amount(), 450)
        order.payment_status = "paid"
        order.amount_paid = Decimal("450")
        order.save(update_fields=["payment_status", "amount_paid"])
        self.mark_completed(order)
        self.assertEqual(settle_order(order.pk).amount, Decimal("405.00"))

    def test_payable_amount_rounds_to_whole_shillings(self):
        self.service.price = Decimal("123.50")
        self.service.save()
        order = self.make_order(kg="1")  # 123.50
        self.assertEqual(order.payable_amount(), 124)

    def test_db_blocks_second_sale_credit_for_same_order(self):
        order = self.make_order()
        self.mark_paid(order)
        self.mark_completed(order)
        settle_order(order.pk)
        wallet = Wallet.objects.get(owner=self.owner)
        with self.assertRaises(IntegrityError), transaction.atomic():
            WalletTransaction.objects.create(
                wallet=wallet, type="sale_credit", amount=Decimal("1"),
                balance_after=Decimal("1"), order=order,
            )

    def test_db_rejects_negative_balance(self):
        wallet = Wallet.objects.create(owner=self.owner)
        wallet.balance = Decimal("-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            wallet.save()


# =====================================================================
# request_payout + transitions
# =====================================================================
class RequestPayoutTests(WalletTestCase):

    def test_holds_full_amount_and_snapshots_fee(self):
        self.fund("1000")
        payout = request_payout(self.owner, "500", "mpesa", "0712 345 678")

        self.assertEqual(payout.amount, Decimal("500.00"))
        self.assertEqual(payout.fee, Decimal("10.00"))
        self.assertEqual(payout.net_amount, Decimal("490.00"))
        self.assertEqual(payout.destination, "254712345678")
        self.assertEqual(payout.status, "requested")
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("500.00"))
        hold = WalletTransaction.objects.get(payout=payout, type="payout_hold")
        self.assertEqual(hold.amount, Decimal("-500.00"))
        self.assertLedgerBalanced()

    def test_no_minimum_small_withdrawal_allowed(self):
        self.fund("100")
        payout = request_payout(self.owner, "50", "mpesa", "0712345678")
        self.assertEqual(payout.net_amount, Decimal("40.00"))

    def test_amount_not_above_fee_is_rejected(self):
        self.fund("100")
        with self.assertRaisesMessage(ValidationError, "more than the KES 10 transfer fee"):
            request_payout(self.owner, "10", "mpesa", "0712345678")
        self.assertEqual(Payout.objects.count(), 0)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("100.00"))

    def test_insufficient_balance(self):
        self.fund("100")
        with self.assertRaisesMessage(ValidationError, "Insufficient balance"):
            request_payout(self.owner, "101", "mpesa", "0712345678")
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("100.00"))

    def test_withdraw_exact_balance_to_zero(self):
        self.fund("200")
        request_payout(self.owner, "200", "mpesa", "0712345678")
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("0.00"))

    def test_only_one_open_payout_at_a_time(self):
        self.fund("1000")
        first = request_payout(self.owner, "100", "mpesa", "0712345678")
        with self.assertRaisesMessage(ValidationError, "already have a withdrawal in progress"):
            request_payout(self.owner, "100", "mpesa", "0712345678")

        approve_payout(first.pk, self.owner)  # approved is still "open"
        with self.assertRaises(ValidationError):
            request_payout(self.owner, "100", "mpesa", "0712345678")

        mark_payout_paid(first.pk, self.owner, "RKT12345")
        second = request_payout(self.owner, "100", "mpesa", "0712345678")  # allowed again
        self.assertEqual(second.status, "requested")

    def test_db_enforces_one_open_payout(self):
        kwargs = dict(owner=self.owner, amount=Decimal("100"), fee=Decimal("10"),
                      net_amount=Decimal("90"), method="mpesa", destination="254712345678")
        Payout.objects.create(**kwargs)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payout.objects.create(**kwargs)

    def test_input_validation(self):
        self.fund("1000")
        bad_amounts = ["0", "-5", "abc", "", None, "12.5", "NaN", "1e99"]
        for bad in bad_amounts:
            with self.assertRaises(ValidationError, msg=repr(bad)):
                request_payout(self.owner, bad, "mpesa", "0712345678")
        with self.assertRaises(ValidationError):
            request_payout(self.owner, "100", "paypal", "0712345678")
        with self.assertRaises(ValidationError):
            request_payout(self.owner, "100", "mpesa", "12345")
        with self.assertRaises(ValidationError):
            request_payout(self.owner, "100", "bank", "KCB")
        self.assertEqual(Payout.objects.count(), 0)

    def test_bank_payout_uses_bank_fee(self):
        self.fund("1000")
        payout = request_payout(self.owner, "500", "bank", "KCB 1234567890 John Doe")
        self.assertEqual(payout.fee, Decimal("50.00"))
        self.assertEqual(payout.net_amount, Decimal("450.00"))

    def test_customers_cannot_withdraw(self):
        with self.assertRaises(ValidationError):
            request_payout(self.customer, "100", "mpesa", "0712345678")

    def test_fee_is_snapshotted_not_recomputed(self):
        self.fund("1000")
        payout = request_payout(self.owner, "500", "mpesa", "0712345678")
        with override_settings(PAYOUT_FEES={"mpesa": Decimal("99"), "bank": Decimal("99")}):
            mark_payout_paid(payout.pk, self.owner, "RKT12345")
        payout.refresh_from_db()
        self.assertEqual(payout.fee, Decimal("10.00"))
        self.assertEqual(payout.net_amount, Decimal("490.00"))

    def test_quote_matches_request(self):
        self.assertEqual(
            quote_payout("500", "mpesa"),
            (Decimal("500.00"), Decimal("10.00"), Decimal("490.00")),
        )

    def test_msisdn_normalisation(self):
        for raw in ("0712345678", "+254 712 345 678", "254712345678", "712345678", "0112345678"):
            self.assertTrue(normalize_msisdn(raw), raw)
        self.assertEqual(normalize_msisdn("0112345678"), "254112345678")
        for raw in ("", "0612345678", "07123", "abc"):
            self.assertIsNone(normalize_msisdn(raw), raw)

    # ---- transitions ----
    def test_reject_restores_full_gross_including_fee(self):
        self.fund("1000")
        payout = request_payout(self.owner, "500", "mpesa", "0712345678")
        reject_payout(payout.pk, self.owner, "Wrong number")
        payout.refresh_from_db()
        self.assertEqual(payout.status, "rejected")
        self.assertEqual(payout.reject_reason, "Wrong number")
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("1000.00"))
        self.assertLedgerBalanced()

    def test_fail_after_approval_restores_balance(self):
        self.fund("1000")
        payout = request_payout(self.owner, "500", "mpesa", "0712345678")
        approve_payout(payout.pk, self.owner)
        fail_payout(payout.pk, self.owner, "B2C declined")
        self.assertEqual(Payout.objects.get(pk=payout.pk).status, "failed")
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("1000.00"))

    def test_cannot_reverse_twice_or_after_paid(self):
        self.fund("1000")
        payout = request_payout(self.owner, "500", "mpesa", "0712345678")
        reject_payout(payout.pk, self.owner, "x")
        with self.assertRaises(ValidationError):
            reject_payout(payout.pk, self.owner, "x")
        self.assertEqual(WalletTransaction.objects.filter(type="payout_reversal").count(), 1)

        other = request_payout(self.owner, "100", "mpesa", "0712345678")
        mark_payout_paid(other.pk, self.owner, "RKT99999")
        with self.assertRaises(ValidationError):
            reject_payout(other.pk, self.owner, "x")
        self.assertLedgerBalanced()

    def test_paid_requires_reference_and_reason_required_to_reject(self):
        self.fund("1000")
        payout = request_payout(self.owner, "500", "mpesa", "0712345678")
        with self.assertRaises(ValidationError):
            mark_payout_paid(payout.pk, self.owner, "  ")
        with self.assertRaises(ValidationError):
            reject_payout(payout.pk, self.owner, "")
        self.assertEqual(Payout.objects.get(pk=payout.pk).status, "requested")

    def test_mark_paid_records_reference_and_does_not_touch_balance(self):
        self.fund("1000")
        payout = request_payout(self.owner, "500", "mpesa", "0712345678")
        mark_payout_paid(payout.pk, self.owner, "RKT12345")
        payout.refresh_from_db()
        self.assertEqual(payout.status, "paid")
        self.assertEqual(payout.reference, "RKT12345")
        self.assertIsNotNone(payout.paid_at)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("500.00"))
        self.assertLedgerBalanced()


# =====================================================================
# callback processing + view hardening
# =====================================================================
class CallbackTests(WalletTestCase):
    url = "/api/mpesa/callback/test-secret/"

    def post(self, payload, url=None, **extra):
        return APIClient().post(url or self.url, payload, format="json", **extra)

    def test_wrong_secret_is_404_and_changes_nothing(self):
        order = self.pending_order()
        resp = self.post(stk_payload("ws_CO_1", amount=400), url="/api/mpesa/callback/nope/")
        self.assertEqual(resp.status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")

    @override_settings(MPESA_CALLBACK_SECRET="")
    def test_unconfigured_secret_fails_closed(self):
        order = self.pending_order()
        resp = self.post(stk_payload("ws_CO_1", amount=400), url="/api/mpesa/callback/anything/")
        self.assertEqual(resp.status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")

    def test_success_marks_paid_and_records_receipt_and_amount(self):
        order = self.pending_order()
        resp = self.post(stk_payload("ws_CO_1", amount=400, receipt="RKT777"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["ResultCode"], 0)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.mpesa_transaction_code, "RKT777")
        self.assertEqual(order.amount_paid, Decimal("400.00"))
        self.assertFalse(WalletTransaction.objects.exists())  # not completed yet

    def test_amount_mismatch_is_not_marked_paid(self):
        order = self.pending_order()
        self.post(stk_payload("ws_CO_1", amount=1))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")
        self.assertIsNone(order.amount_paid)

    def test_failed_callback_marks_failed(self):
        order = self.pending_order()
        self.post(stk_payload("ws_CO_1", code=1032))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "failed")

    def test_unknown_checkout_and_malformed_payloads_are_harmless(self):
        self.assertEqual(self.post(stk_payload("does-not-exist", amount=400)).status_code, 200)
        for junk in ({}, {"Body": {}}, {"Body": "x"}, {"Body": {"stkCallback": 5}}, [1, 2]):
            self.assertEqual(self.post(junk).status_code, 200, junk)

    def test_replayed_callback_credits_only_once(self):
        order = self.pending_order()
        self.mark_completed(order)  # completed first, paid via callback second
        self.post(stk_payload("ws_CO_1", amount=400))
        self.post(stk_payload("ws_CO_1", amount=400))
        self.post(stk_payload("ws_CO_1", amount=400))
        self.assertEqual(WalletTransaction.objects.filter(type="sale_credit").count(), 1)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("360.00"))
        self.assertLedgerBalanced()

    def test_payment_after_cancel_flags_refund(self):
        order = self.pending_order()
        order.status = "cancelled"
        order.save(update_fields=["status"])
        self.post(stk_payload("ws_CO_1", amount=400))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")
        self.assertTrue(order.refund_needed)
        self.assertFalse(WalletTransaction.objects.exists())  # never credited

    def test_outcomes_from_service(self):
        self.pending_order()
        self.assertEqual(payments.process_stk_callback({}), "malformed")
        self.assertEqual(payments.process_stk_callback(stk_payload("nope", amount=1)), "unknown_attempt")
        self.assertEqual(payments.process_stk_callback(stk_payload("ws_CO_1", amount=5)), "amount_mismatch")
        self.assertEqual(payments.process_stk_callback(stk_payload("ws_CO_1", amount=400)), "paid")
        self.assertEqual(payments.process_stk_callback(stk_payload("ws_CO_1", amount=400)), "duplicate")

    @override_settings(MPESA_CALLBACK_ALLOWED_IPS=["196.201.214.200"])
    def test_ip_allowlist_when_enabled(self):
        order = self.pending_order()
        blocked = self.post(stk_payload("ws_CO_1", amount=400), REMOTE_ADDR="10.0.0.9")
        self.assertEqual(blocked.status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")

        allowed = self.post(stk_payload("ws_CO_1", amount=400), REMOTE_ADDR="196.201.214.200")
        self.assertEqual(allowed.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")


class StatusViewSettlementTests(WalletTestCase):
    # notify() is patched so these tests don't depend on the Notification
    # model/migration drift noted in CHANGES.md.

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    @mock.patch("dryMe.views.notify")
    def test_completing_a_paid_order_credits_wallet(self, _notify):
        order = self.make_order()
        self.mark_paid(order)
        resp = self.client_for(self.owner).put(
            f"/api/orders/{order.pk}/status/", {"status": "completed"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("360.00"))

    @mock.patch("dryMe.views.notify")
    def test_pay_after_complete_also_credits(self, _notify):
        order = self.pending_order()
        resp = self.client_for(self.owner).put(
            f"/api/orders/{order.pk}/status/", {"status": "completed"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(WalletTransaction.objects.exists())
        payments.process_stk_callback(stk_payload("ws_CO_1", amount=400))
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("360.00"))

    @mock.patch("dryMe.views.notify")
    def test_completed_orders_are_final(self, _notify):
        order = self.make_order()
        self.mark_paid(order)
        client = self.client_for(self.owner)
        client.put(f"/api/orders/{order.pk}/status/", {"status": "completed"}, format="json")
        resp = client.put(f"/api/orders/{order.pk}/status/", {"status": "pending"}, format="json")
        self.assertEqual(resp.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, "completed")
        self.assertEqual(WalletTransaction.objects.filter(type="sale_credit").count(), 1)

    @mock.patch("dryMe.views.notify")
    def test_other_owners_cannot_update(self, _notify):
        other = User.objects.create_user(
            username="o2", email="o2@test.com", password="pass12345",
            role="owner", phone="0733345678", location="Nairobi",
        )
        order = self.make_order()
        resp = self.client_for(other).put(
            f"/api/orders/{order.pk}/status/", {"status": "completed"}, format="json",
        )
        self.assertEqual(resp.status_code, 403)
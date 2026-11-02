"""
Run with:  python manage.py test dryMe.test_weigh_in -v 2

Weigh-in for per-kg orders. Fixtures (from test_wallet.WalletTestCase): a shop charging
KES 100 per kg, 10% commission. A 4 kg booking is a KES 400 estimate, so with the default 15%
margin anything up to KES 460 is payable straight away and anything above needs the
customer's approval.
"""
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from .models import Notification, Order, PaymentAttempt, Service, Shop, User, Wallet
from .services import payments
from .services.weigh_in import parse_weight, tolerance, within_tolerance
from .test_wallet import WalletTestCase, stk_payload

ORDERS = "/api/orders/"


def ok_response(checkout_id):
    return {"ResponseCode": "0", "CheckoutRequestID": checkout_id, "ResponseDescription": "Success"}


class WeighInTestCase(WalletTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.cust = self.api(self.customer)
        self.shopkeeper = self.api(self.owner)

    # ---- helpers ----
    def api(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def booking(self, service=None, **extra):
        body = {
            "shop_id": self.shop.pk,
            "service_id": (service or self.service).pk,
            "customer_phone": "0722345678",
            "customer_location": "Kilimani",
        }
        body.update(extra)
        return self.cust.post(ORDERS, body, format="json")

    def book(self, kg=4, **extra):
        """A per-kg booking through the real API: starts as an estimate."""
        resp = self.booking(weight=kg, **extra)
        self.assertEqual(resp.status_code, 201, resp.content)
        return Order.objects.get(pk=resp.json()["id"])

    def book_per_item(self, quantity=2, price="150.00"):
        service = Service.objects.create(shop=self.shop, name="Suit", pricing_type="per_item", price=Decimal(price))
        resp = self.booking(service=service, quantity=quantity)
        self.assertEqual(resp.status_code, 201, resp.content)
        return Order.objects.get(pk=resp.json()["id"])

    def set_status(self, order, status, client=None):
        return (client or self.shopkeeper).put(f"{ORDERS}{order.pk}/status/", {"status": status}, format="json")

    def confirmed(self, kg=4):
        order = self.book(kg)
        self.assertEqual(self.set_status(order, "confirmed").status_code, 200)
        order.refresh_from_db()
        return order

    def weigh(self, order, weight, client=None):
        return (client or self.shopkeeper).post(f"{ORDERS}{order.pk}/weigh/", {"weight": weight}, format="json")

    def accept(self, order, client=None):
        return (client or self.cust).post(f"{ORDERS}{order.pk}/accept-price/")

    def pay(self, order, checkout="ws_CO_W"):
        with mock.patch("dryMe.mpesa.stk_push") as push:
            push.return_value = ok_response(checkout)
            resp = self.cust.post(f"{ORDERS}{order.pk}/pay/")
        return resp, push

    def weighed(self, kg, booked=4):
        """Confirmed and weighed. Returns the refreshed order."""
        order = self.confirmed(booked)
        resp = self.weigh(order, kg)
        self.assertEqual(resp.status_code, 200, resp.content)
        order.refresh_from_db()
        return order


# =====================================================================
# booking
# =====================================================================
class BookingTests(WeighInTestCase):

    def test_a_per_kg_booking_starts_as_an_estimate_and_cannot_be_paid(self):
        order = self.book(4)

        self.assertEqual(order.price_status, "estimate")
        self.assertEqual(order.estimated_weight, Decimal("4.00"))
        self.assertEqual(order.estimated_total_price, Decimal("400.00"))
        self.assertEqual(order.total_price, Decimal("400.00"))
        self.assertEqual(order.unit_price, Decimal("100.00"))
        self.assertIsNone(order.weighed_at)

        resp, push = self.pay(order)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("hasn't weighed", resp.json()["error"])
        push.assert_not_called()
        self.assertEqual(PaymentAttempt.objects.count(), 0)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "unpaid")

    def test_a_per_item_booking_is_final_and_payable_straight_away(self):
        order = self.book_per_item(quantity=2, price="150.00")

        self.assertEqual(order.price_status, "final")
        self.assertIsNone(order.estimated_weight)
        self.assertEqual(order.total_price, Decimal("300.00"))

        resp, push = self.pay(order)

        self.assertEqual(resp.status_code, 200)
        push.assert_called_once_with(phone="0722345678", amount=300, order_id=order.pk)

    def test_the_client_cannot_set_the_weigh_in_fields(self):
        order = self.book(
            4, price_status="final", estimated_weight="1", estimated_total_price="1",
            unit_price="1", total_price="1", weighed_at="2026-01-01T00:00:00Z",
        )
        self.assertEqual(order.price_status, "estimate")
        self.assertEqual(order.estimated_weight, Decimal("4.00"))
        self.assertEqual(order.estimated_total_price, Decimal("400.00"))
        self.assertEqual(order.unit_price, Decimal("100.00"))
        self.assertEqual(order.total_price, Decimal("400.00"))
        self.assertIsNone(order.weighed_at)

    def test_a_service_from_another_shop_is_rejected(self):
        other_owner = User.objects.create_user(
            username="owner2", email="owner2@test.com", password="pass12345",
            role="owner", phone="0733345678", location="Nairobi",
        )
        other_shop = Shop.objects.create(owner=other_owner, name="Other", location="CBD", description="x")
        other_service = Service.objects.create(shop=other_shop, name="Wash", pricing_type="per_kg", price=Decimal("1.00"))

        resp = self.booking(service=other_service, weight=4)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("does not belong to this shop", resp.content.decode())
        self.assertEqual(Order.objects.count(), 0)

    def test_orders_expose_the_weigh_in_fields(self):
        self.book(4)
        row = self.cust.get(ORDERS).json()["results"][0]
        self.assertEqual(row["price_status"], "estimate")
        self.assertEqual(Decimal(row["estimated_weight"]), Decimal("4"))
        self.assertEqual(Decimal(row["estimated_total_price"]), Decimal("400"))
        self.assertEqual(row["weigh_in_tolerance"], "0.15")
        self.assertIsNone(row["weighed_at"])


# =====================================================================
# the shop weighs the laundry
# =====================================================================
class WeighTests(WeighInTestCase):

    def test_the_shop_must_accept_the_order_first(self):
        order = self.book(4)
        resp = self.weigh(order, 4.5)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Accept the order", resp.json()["error"])
        order.refresh_from_db()
        self.assertEqual(order.price_status, "estimate")

    def test_within_the_margin_the_order_becomes_payable_at_the_weighed_price(self):
        order = self.confirmed(4)

        resp = self.weigh(order, 4.5)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["within_margin"])
        self.assertEqual(body["order"]["price_status"], "final")
        order.refresh_from_db()
        self.assertEqual(order.weight, Decimal("4.50"))
        self.assertEqual(order.total_price, Decimal("450.00"))
        self.assertEqual(order.estimated_total_price, Decimal("400.00"))   # the estimate is kept
        self.assertEqual(order.price_status, "final")
        self.assertIsNotNone(order.weighed_at)
        self.assertIsNone(order.price_accepted_at)

        pay, push = self.pay(order)
        self.assertEqual(pay.status_code, 200)
        push.assert_called_once_with(phone="0722345678", amount=450, order_id=order.pk)

    def test_exactly_at_the_margin_is_still_payable_and_a_shilling_over_is_not(self):
        at_limit = self.confirmed(4)
        self.weigh(at_limit, "4.6")                       # KES 460.00 = estimate + 15%
        at_limit.refresh_from_db()
        self.assertEqual(at_limit.total_price, Decimal("460.00"))
        self.assertEqual(at_limit.price_status, "final")

        over = self.confirmed(4)
        self.weigh(over, "4.61")                          # KES 461.00
        over.refresh_from_db()
        self.assertEqual(over.price_status, "needs_approval")

    def test_a_lighter_load_than_estimated_is_simply_cheaper(self):
        order = self.weighed(3)
        self.assertEqual(order.total_price, Decimal("300.00"))
        self.assertEqual(order.price_status, "final")

    def test_above_the_margin_the_customer_must_approve_before_paying(self):
        order = self.weighed(6)

        self.assertEqual(order.total_price, Decimal("600.00"))
        self.assertEqual(order.price_status, "needs_approval")

        resp, push = self.pay(order)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("Accept it first", resp.json()["error"])
        push.assert_not_called()

    def test_customer_is_notified_either_way(self):
        order = self.confirmed(4)
        with self.captureOnCommitCallbacks(execute=True):
            self.weigh(order, 4.5)
        note = Notification.objects.get(user=self.customer, notif_type="order_weighed")
        self.assertEqual(note.order_id, order.pk)
        self.assertIn("4.5 kg", note.message)
        self.assertNotIn("4.50", note.message)
        self.assertIn("KES 450", note.message)
        self.assertIn("pay now", note.message)

        order2 = self.confirmed(4)
        with self.captureOnCommitCallbacks(execute=True):
            self.weigh(order2, 6.5)
        note = Notification.objects.get(user=self.customer, notif_type="price_approval")
        self.assertEqual(note.order_id, order2.pk)
        self.assertIn("KES 650", note.message)
        self.assertIn("KES 400", note.message)
        self.assertIn("Accept it", note.message)

    def test_nothing_is_sent_when_the_weigh_in_is_refused(self):
        order = self.book(4)                              # not accepted yet
        with self.captureOnCommitCallbacks(execute=True):
            self.weigh(order, 4.5)
        self.assertFalse(Notification.objects.filter(notif_type__in=("order_weighed", "price_approval")).exists())

    def test_nonsense_weights_are_rejected_and_change_nothing(self):
        order = self.confirmed(4)
        for bad in ("", "abc", "0", "-1", "0.05", "1000", "NaN", "1e99", None):
            resp = self.weigh(order, bad)
            self.assertEqual(resp.status_code, 400, repr(bad))
            self.assertIn("error", resp.json(), repr(bad))
        order.refresh_from_db()
        self.assertEqual(order.price_status, "estimate")
        self.assertEqual(order.weight, Decimal("4.00"))
        self.assertIsNone(order.weighed_at)

    def test_only_the_shop_that_owns_the_order_can_weigh_it(self):
        order = self.confirmed(4)
        stranger = User.objects.create_user(
            username="owner2", email="owner2@test.com", password="pass12345",
            role="owner", phone="0733345678", location="Nairobi",
        )
        self.assertEqual(self.weigh(order, 4.5, client=self.cust).status_code, 403)
        self.assertEqual(self.weigh(order, 4.5, client=self.api(stranger)).status_code, 403)
        self.assertEqual(self.weigh(order, 4.5, client=self.api()).status_code, 401)
        self.assertEqual(self.weigh(Order(pk=999999), 4.5).status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.price_status, "estimate")

    def test_per_item_orders_have_nothing_to_weigh(self):
        order = self.book_per_item()
        self.set_status(order, "confirmed")
        resp = self.weigh(order, 3)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("nothing to weigh", resp.json()["error"])

    def test_orders_booked_before_weigh_ins_have_nothing_to_weigh(self):
        order = self.make_order()                         # created directly, like every existing order
        self.set_status(order, "confirmed")
        self.assertEqual(self.weigh(order, 3).status_code, 400)

    def test_declined_cancelled_and_finished_orders_cannot_be_weighed(self):
        declined = self.confirmed(4)
        self.shopkeeper.post(f"{ORDERS}{declined.pk}/decline/", {"reason": "Full"}, format="json")
        self.assertEqual(self.weigh(declined, 4.5).status_code, 400)

        cancelled = self.confirmed(4)
        self.cust.post(f"{ORDERS}{cancelled.pk}/cancel/")
        self.assertEqual(self.weigh(cancelled, 4.5).status_code, 400)

    # ---- re-weighing before payment ----
    def test_a_typo_can_be_corrected_before_payment_and_the_approval_resets(self):
        order = self.weighed(6)
        self.assertEqual(self.accept(order).status_code, 200)
        order.refresh_from_db()
        self.assertIsNotNone(order.price_accepted_at)

        self.assertEqual(self.weigh(order, 4.2).status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.total_price, Decimal("420.00"))
        self.assertEqual(order.price_status, "final")
        self.assertIsNone(order.price_accepted_at)

    def test_every_weigh_in_is_compared_with_the_estimate_so_the_price_cannot_creep(self):
        order = self.weighed(4.5)                         # KES 450: payable
        self.assertEqual(order.price_status, "final")

        self.weigh(order, 4.7)                            # KES 470: 17.5% over the ESTIMATE

        order.refresh_from_db()
        self.assertEqual(order.price_status, "needs_approval")

    def test_a_higher_price_the_customer_accepted_is_lost_if_the_shop_changes_it_again(self):
        order = self.weighed(6)
        self.accept(order)
        self.weigh(order, 7)
        order.refresh_from_db()
        self.assertEqual(order.price_status, "needs_approval")
        self.assertEqual(self.pay(order)[0].status_code, 400)

    # ---- rates ----
    def test_the_rate_agreed_at_booking_is_used_even_if_the_shop_changes_its_prices(self):
        order = self.confirmed(4)
        Service.objects.filter(pk=self.service.pk).update(price=Decimal("200.00"))
        self.weigh(order, 5)
        order.refresh_from_db()
        self.assertEqual(order.total_price, Decimal("500.00"))      # 5 kg x KES 100, not KES 200

    def test_saving_an_order_never_reprices_it(self):
        order = self.make_order()                         # 4 kg x KES 100
        Service.objects.filter(pk=self.service.pk).update(price=Decimal("999.00"))
        order = Order.objects.get(pk=order.pk)
        order.customer_notes = "ring the bell"
        order.save()
        self.assertEqual(Order.objects.get(pk=order.pk).total_price, Decimal("400.00"))

    @override_settings(WEIGH_IN_TOLERANCE=Decimal("0.05"))
    def test_the_margin_is_configurable(self):
        within = self.confirmed(4)
        self.weigh(within, "4.2")                         # KES 420 = estimate + 5%
        within.refresh_from_db()
        self.assertEqual(within.price_status, "final")

        over = self.confirmed(4)
        self.weigh(over, "4.21")
        over.refresh_from_db()
        self.assertEqual(over.price_status, "needs_approval")


# =====================================================================
# the weight locks once the customer pays
# =====================================================================
class WeightLockTests(WeighInTestCase):

    def test_locked_once_paid(self):
        order = self.weighed(4.5)
        self.mark_paid(order)

        resp = self.weigh(order, 5)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("already paid", resp.json()["error"])
        order.refresh_from_db()
        self.assertEqual(order.weight, Decimal("4.50"))
        self.assertEqual(order.total_price, Decimal("450.00"))

    def test_locked_while_a_payment_prompt_is_in_flight(self):
        order = self.weighed(4.5)
        pay, _ = self.pay(order)
        self.assertEqual(pay.status_code, 200)

        resp = self.weigh(order, 5)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("in progress", resp.json()["error"])
        order.refresh_from_db()
        self.assertEqual(order.total_price, Decimal("450.00"))

    def test_unlocked_again_after_a_failed_payment(self):
        order = self.weighed(4.5)
        self.pay(order)
        payments.process_stk_callback(stk_payload("ws_CO_W", code=1032))      # customer cancelled the prompt
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "failed")

        self.assertEqual(self.weigh(order, 4.4).status_code, 200)

    def test_a_late_price_change_cannot_alter_what_was_paid(self):
        order = self.weighed(4.5)
        self.pay(order)
        payments.process_stk_callback(stk_payload("ws_CO_W", amount=450, receipt="RCPT_W"))

        self.assertEqual(self.weigh(order, 4.6).status_code, 400)

        order.refresh_from_db()
        self.assertEqual(order.amount_paid, Decimal("450.00"))
        self.assertEqual(order.total_price, Decimal("450.00"))


# =====================================================================
# the customer accepts a higher price
# =====================================================================
class AcceptPriceTests(WeighInTestCase):

    def test_accepting_unlocks_payment_at_the_weighed_price(self):
        order = self.weighed(6)

        resp = self.accept(order)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["order"]["price_status"], "final")
        order.refresh_from_db()
        self.assertEqual(order.price_status, "final")
        self.assertIsNotNone(order.price_accepted_at)

        pay, push = self.pay(order)
        self.assertEqual(pay.status_code, 200)
        push.assert_called_once_with(phone="0722345678", amount=600, order_id=order.pk)

    def test_the_shop_is_told_the_customer_accepted(self):
        order = self.weighed(6)
        with self.captureOnCommitCallbacks(execute=True):
            self.accept(order)
        note = Notification.objects.get(user=self.owner, notif_type="price_accepted")
        self.assertEqual(note.order_id, order.pk)
        self.assertIn("KES 600", note.message)
        self.assertIn("cust", note.message)

    def test_accepting_twice_is_harmless(self):
        order = self.weighed(6)
        with self.captureOnCommitCallbacks(execute=True):
            first = self.accept(order)
            second = self.accept(order)
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(Notification.objects.filter(notif_type="price_accepted").count(), 1)

    def test_accepting_an_already_payable_price_is_a_quiet_no_op(self):
        order = self.weighed(4.5)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.accept(order)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Notification.objects.filter(notif_type="price_accepted").exists())
        order.refresh_from_db()
        self.assertIsNone(order.price_accepted_at)

    def test_nothing_to_accept_before_the_weigh_in(self):
        order = self.confirmed(4)
        resp = self.accept(order)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("hasn't weighed", resp.json()["error"])

    def test_per_item_orders_have_no_price_to_accept(self):
        order = self.book_per_item()
        self.assertEqual(self.accept(order).status_code, 400)

    def test_only_the_customer_who_placed_the_order_can_accept(self):
        order = self.weighed(6)
        stranger = User.objects.create_user(
            username="cust2", email="cust2@test.com", password="pass12345",
            role="customer", phone="0744345678", location="Nairobi",
        )
        self.assertEqual(self.accept(order, client=self.shopkeeper).status_code, 403)   # the shop can't accept for them
        self.assertEqual(self.accept(order, client=self.api(stranger)).status_code, 403)
        self.assertEqual(self.accept(order, client=self.api()).status_code, 401)
        self.assertEqual(self.accept(Order(pk=999999)).status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.price_status, "needs_approval")

    def test_the_customer_can_cancel_instead_of_accepting(self):
        order = self.weighed(6)

        resp = self.cust.post(f"{ORDERS}{order.pk}/cancel/")

        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(self.accept(order).status_code, 400)       # and can't accept it afterwards


# =====================================================================
# washing starts after payment
# =====================================================================
class WashingGateTests(WeighInTestCase):

    def test_no_washing_before_the_laundry_is_weighed(self):
        order = self.confirmed(4)
        resp = self.set_status(order, "washing")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Weigh the laundry first", resp.json()["error"])

    def test_no_washing_while_the_customer_has_yet_to_accept_the_new_price(self):
        order = self.weighed(6)
        resp = self.set_status(order, "washing")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("accept the new price", resp.json()["error"])

    def test_no_washing_or_completing_before_payment(self):
        order = self.weighed(4.5)
        for status in ("washing", "completed"):
            resp = self.set_status(order, status)
            self.assertEqual(resp.status_code, 400, status)
            self.assertIn("payment", resp.json()["error"])
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")

    def test_washing_starts_once_paid(self):
        order = self.weighed(4.5)
        self.mark_paid(order)
        self.assertEqual(self.set_status(order, "washing").status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "washing")
        self.assertIsNotNone(order.washing_at)

    def test_orders_booked_before_weigh_ins_keep_working_as_they_did(self):
        order = self.make_order()                         # unpaid, created directly
        self.assertEqual(self.set_status(order, "washing").status_code, 200)

    def test_per_item_orders_can_be_washed_without_a_weigh_in(self):
        order = self.book_per_item()
        self.assertEqual(self.set_status(order, "washing").status_code, 200)


# =====================================================================
# the whole journey, money included
# =====================================================================
class EndToEndTests(WeighInTestCase):

    def test_book_weigh_pay_wash_complete_credits_the_owner_the_weighed_amount(self):
        order = self.book(4)                                                   # estimate KES 400
        self.assertEqual(self.set_status(order, "confirmed").status_code, 200)
        self.assertEqual(self.weigh(order, 4.5).status_code, 200)              # weighed KES 450

        pay, push = self.pay(order)
        self.assertEqual(pay.status_code, 200)
        push.assert_called_once_with(phone="0722345678", amount=450, order_id=order.pk)

        self.assertEqual(
            payments.process_stk_callback(stk_payload("ws_CO_W", amount=450, receipt="RCPT_W")), "paid",
        )

        self.assertEqual(self.set_status(order, "washing").status_code, 200)
        self.assertEqual(self.set_status(order, "completed").status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.amount_paid, Decimal("450.00"))
        self.assertEqual(order.commission_amount, Decimal("45.00"))
        self.assertEqual(order.owner_earnings, Decimal("405.00"))
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("405.00"))
        self.assertLedgerBalanced()

    def test_the_higher_price_route_ends_with_the_higher_amount_paid(self):
        order = self.book(4)
        self.set_status(order, "confirmed")
        self.weigh(order, 6)
        self.assertEqual(self.accept(order).status_code, 200)

        pay, push = self.pay(order)
        push.assert_called_once_with(phone="0722345678", amount=600, order_id=order.pk)
        payments.process_stk_callback(stk_payload("ws_CO_W", amount=600, receipt="RCPT_W"))

        self.set_status(order, "washing")
        self.set_status(order, "completed")
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("540.00"))   # KES 600 less 10%
        self.assertLedgerBalanced()


# =====================================================================
# the pure rules
# =====================================================================
class RuleTests(SimpleTestCase):

    def test_parse_weight_rounds_to_two_decimals(self):
        self.assertEqual(parse_weight("4.5"), Decimal("4.50"))
        self.assertEqual(parse_weight(" 3 "), Decimal("3.00"))
        self.assertEqual(parse_weight(4.555), Decimal("4.56"))
        self.assertEqual(parse_weight("0.10"), Decimal("0.10"))
        self.assertEqual(parse_weight("999.99"), Decimal("999.99"))

    def test_parse_weight_rejects_nonsense(self):
        for bad in ("", "abc", "0", "-2", "0.04", "1000", "NaN", "Infinity", "1e99", None):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                parse_weight(bad)

    def test_within_tolerance_is_exact_not_floating_point(self):
        self.assertTrue(within_tolerance(Decimal("400"), Decimal("460.00")))
        self.assertFalse(within_tolerance(Decimal("400"), Decimal("460.01")))
        self.assertTrue(within_tolerance(Decimal("400"), Decimal("100")))
        self.assertTrue(within_tolerance(Decimal("123.50"), Decimal("142.02")))     # limit: 123.50 x 1.15 = 142.025
        self.assertFalse(within_tolerance(Decimal("123.50"), Decimal("142.03")))

    def test_tolerance_defaults_to_15_percent_and_ignores_bad_settings(self):
        self.assertEqual(tolerance(), Decimal("0.15"))
        with override_settings(WEIGH_IN_TOLERANCE="oops"):
            self.assertEqual(tolerance(), Decimal("0.15"))
        with override_settings(WEIGH_IN_TOLERANCE=Decimal("-1")):
            self.assertEqual(tolerance(), Decimal("0.15"))
        with override_settings(WEIGH_IN_TOLERANCE=Decimal("0.10")):
            self.assertEqual(tolerance(), Decimal("0.10"))
            
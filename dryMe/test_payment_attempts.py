"""
Run with:  python manage.py test dryMe.test_payment_attempts -v 2

Covers the "double tap" problem: several STK prompts for one order, each
resolved by its own CheckoutRequestID, and the STK push view that creates them.
"""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Order, PaymentAttempt, Wallet, WalletTransaction
from .services import payments
from .test_wallet import WalletTestCase, stk_payload

Status = PaymentAttempt.Status


def ok_response(checkout_id):
    return {"ResponseCode": "0", "CheckoutRequestID": checkout_id, "ResponseDescription": "Success"}


# =====================================================================
# Callback side: many attempts per order
# =====================================================================
class DoubleTapCallbackTests(WalletTestCase):

    def order_with_attempts(self, *checkout_ids):
        order = self.make_order()  # 400
        order.payment_status = "pending_payment"
        order.save(update_fields=["payment_status"])
        for cid in checkout_ids:
            PaymentAttempt.objects.create(order=order, checkout_request_id=cid, amount=Decimal("400"))
        return order

    def status_of(self, checkout_id):
        return PaymentAttempt.objects.get(checkout_request_id=checkout_id).status

    def test_older_attempt_paying_after_a_newer_tap_is_still_credited(self):
        # The original bug: tap #2 overwrote tap #1's checkout id, so paying #1 was lost.
        order = self.order_with_attempts("A", "B")
        self.mark_completed(order)

        self.assertEqual(payments.process_stk_callback(stk_payload("A", amount=400, receipt="RCPT_A")), "paid")

        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.mpesa_transaction_code, "RCPT_A")
        self.assertEqual(self.status_of("A"), Status.SUCCESSFUL)
        self.assertEqual(self.status_of("B"), Status.PENDING)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("360.00"))

    def test_second_success_is_flagged_for_refund_and_never_double_credited(self):
        order = self.order_with_attempts("A", "B")
        self.mark_completed(order)

        payments.process_stk_callback(stk_payload("A", amount=400, receipt="RCPT_A"))
        outcome = payments.process_stk_callback(stk_payload("B", amount=400, receipt="RCPT_B"))

        self.assertEqual(outcome, "duplicate_payment")
        second = PaymentAttempt.objects.get(checkout_request_id="B")
        self.assertEqual(second.status, Status.SUCCESSFUL)
        self.assertEqual(second.transaction_code, "RCPT_B")
        self.assertTrue(second.refund_needed)

        first = PaymentAttempt.objects.get(checkout_request_id="A")
        self.assertFalse(first.refund_needed)

        order.refresh_from_db()
        self.assertEqual(order.mpesa_transaction_code, "RCPT_A")  # order keeps the settling receipt
        self.assertEqual(order.amount_paid, Decimal("400.00"))
        self.assertEqual(WalletTransaction.objects.filter(type="sale_credit").count(), 1)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("360.00"))
        self.assertLedgerBalanced()

    def test_a_failed_prompt_does_not_fail_the_order_while_another_is_pending(self):
        order = self.order_with_attempts("A", "B")

        self.assertEqual(payments.process_stk_callback(stk_payload("A", code=1032)), "failed")
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")
        self.assertEqual(self.status_of("A"), Status.FAILED)

        self.assertEqual(payments.process_stk_callback(stk_payload("B", amount=400)), "paid")
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")

    def test_order_fails_once_every_attempt_has_failed(self):
        order = self.order_with_attempts("A", "B")
        payments.process_stk_callback(stk_payload("A", code=1032))
        payments.process_stk_callback(stk_payload("B", code=1037))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "failed")

    def test_replaying_the_same_attempt_is_a_plain_duplicate_not_a_refund(self):
        self.order_with_attempts("A")
        payments.process_stk_callback(stk_payload("A", amount=400))
        self.assertEqual(payments.process_stk_callback(stk_payload("A", amount=400)), "duplicate")
        self.assertFalse(PaymentAttempt.objects.get(checkout_request_id="A").refund_needed)

    def test_failed_attempt_cannot_be_flipped_to_paid_by_a_later_success_callback(self):
        order = self.order_with_attempts("A")
        payments.process_stk_callback(stk_payload("A", code=1032))
        self.assertEqual(payments.process_stk_callback(stk_payload("A", amount=400)), "duplicate")
        order.refresh_from_db()
        self.assertNotEqual(order.payment_status, "paid")

    def test_amount_must_match_the_attempt_that_was_requested(self):
        order = self.order_with_attempts("A")
        self.assertEqual(payments.process_stk_callback(stk_payload("A", amount=399)), "amount_mismatch")
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")
        self.assertEqual(self.status_of("A"), Status.PENDING)
        self.assertIsNone(order.amount_paid)

    def test_unknown_checkout_id(self):
        self.order_with_attempts("A")
        self.assertEqual(payments.process_stk_callback(stk_payload("nope", amount=400)), "unknown_attempt")

    def test_payment_for_a_deleted_order_is_flagged(self):
        order = self.order_with_attempts("A")
        order.delete()  # attempt survives with order=NULL (SET_NULL)
        outcome = payments.process_stk_callback(stk_payload("A", amount=400, receipt="RCPT_X"))
        self.assertEqual(outcome, "orphaned_payment")
        attempt = PaymentAttempt.objects.get(checkout_request_id="A")
        self.assertIsNone(attempt.order)
        self.assertEqual(attempt.status, Status.SUCCESSFUL)
        self.assertTrue(attempt.refund_needed)

    def test_success_on_a_cancelled_order_flags_the_order_for_refund(self):
        order = self.order_with_attempts("A")
        order.status = "cancelled"
        order.save(update_fields=["status"])
        payments.process_stk_callback(stk_payload("A", amount=400))
        order.refresh_from_db()
        self.assertTrue(order.refund_needed)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_checkout_request_id_is_unique_in_the_database(self):
        order = self.order_with_attempts("A")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentAttempt.objects.create(order=order, checkout_request_id="A", amount=Decimal("400"))


# =====================================================================
# STK push side: every tap creates an attempt
# =====================================================================
class StkPushViewTests(WalletTestCase):

    def pay_client(self, user=None):
        client = APIClient()
        client.force_authenticate(user or self.customer)
        return client

    def pay(self, order, user=None):
        return self.pay_client(user).post(f"/api/orders/{order.pk}/pay/")

    @mock.patch("dryMe.mpesa.stk_push")
    def test_tap_creates_a_pending_attempt_instead_of_overwriting_the_order(self, push):
        push.return_value = ok_response("ws_CO_A")
        order = self.make_order()

        resp = self.pay(order)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["checkout_request_id"], "ws_CO_A")
        push.assert_called_once_with(phone="0722345678", amount=400, order_id=order.pk)

        attempt = PaymentAttempt.objects.get()
        self.assertEqual(attempt.order_id, order.pk)
        self.assertEqual(attempt.checkout_request_id, "ws_CO_A")
        self.assertEqual(attempt.amount, Decimal("400.00"))
        self.assertEqual(attempt.status, Status.PENDING)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")

    @mock.patch("dryMe.mpesa.stk_push")
    def test_second_tap_inside_the_cooldown_is_blocked(self, push):
        push.return_value = ok_response("ws_CO_A")
        order = self.make_order()
        self.pay(order)

        resp = self.pay(order)

        self.assertEqual(resp.status_code, 429)
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        self.assertEqual(push.call_count, 1)

    @override_settings(MPESA_STK_COOLDOWN_SECONDS=0)
    @mock.patch("dryMe.mpesa.stk_push")
    def test_without_a_cooldown_every_tap_gets_its_own_attempt(self, push):
        push.side_effect = [ok_response("ws_CO_A"), ok_response("ws_CO_B")]
        order = self.make_order()
        self.pay(order)
        self.pay(order)
        self.assertEqual(
            sorted(PaymentAttempt.objects.values_list("checkout_request_id", flat=True)),
            ["ws_CO_A", "ws_CO_B"],
        )
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")

    @mock.patch("dryMe.mpesa.stk_push")
    def test_retry_is_allowed_after_the_cooldown_has_passed(self, push):
        push.side_effect = [ok_response("ws_CO_A"), ok_response("ws_CO_B")]
        order = self.make_order()
        self.pay(order)
        PaymentAttempt.objects.update(created_at=timezone.now() - timedelta(seconds=300))

        self.assertEqual(self.pay(order).status_code, 200)
        self.assertEqual(PaymentAttempt.objects.count(), 2)

    @mock.patch("dryMe.mpesa.stk_push")
    def test_inactive_or_paid_orders_cannot_be_paid(self, push):
        for status_value in ("declined", "cancelled"):
            order = self.make_order()
            order.status = status_value
            order.save(update_fields=["status"])
            self.assertEqual(self.pay(order).status_code, 400)

        paid = self.make_order()
        self.mark_paid(paid)
        self.assertEqual(self.pay(paid).status_code, 400)

        push.assert_not_called()
        self.assertEqual(PaymentAttempt.objects.count(), 0)

    @mock.patch("dryMe.mpesa.stk_push")
    def test_only_the_customer_who_owns_the_order_can_pay(self, push):
        order = self.make_order()
        self.assertEqual(self.pay(order, user=self.owner).status_code, 404)
        push.assert_not_called()

    @mock.patch("dryMe.mpesa.stk_push")
    def test_rejected_initiation_creates_no_attempt_and_marks_unpaid_order_failed(self, push):
        push.return_value = {"ResponseCode": "1", "ResponseDescription": "Rejected"}
        order = self.make_order()

        resp = self.pay(order)

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(PaymentAttempt.objects.count(), 0)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "failed")

    @override_settings(MPESA_STK_COOLDOWN_SECONDS=0)
    @mock.patch("dryMe.mpesa.stk_push")
    def test_rejected_initiation_does_not_clobber_an_order_with_a_live_prompt(self, push):
        order = self.pending_order("ws_CO_LIVE")
        push.return_value = {"ResponseCode": "1", "ResponseDescription": "Rejected"}

        self.assertEqual(self.pay(order).status_code, 400)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    @mock.patch("dryMe.mpesa.stk_push")
    def test_safaricom_outage_creates_nothing(self, push):
        push.side_effect = Exception("boom")
        order = self.make_order()

        self.assertEqual(self.pay(order).status_code, 502)

        self.assertEqual(PaymentAttempt.objects.count(), 0)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "unpaid")

    @mock.patch("dryMe.mpesa.stk_push")
    def test_success_response_without_a_checkout_id_is_an_error(self, push):
        push.return_value = {"ResponseCode": "0"}
        order = self.make_order()
        self.assertEqual(self.pay(order).status_code, 502)
        self.assertEqual(PaymentAttempt.objects.count(), 0)

    @mock.patch("dryMe.mpesa.stk_push")
    def test_a_callback_landing_during_the_push_is_not_downgraded(self, push):
        order = self.make_order()

        def push_while_callback_lands(**kwargs):
            Order.objects.filter(pk=order.pk).update(payment_status="paid")
            return ok_response("ws_CO_A")

        push.side_effect = push_while_callback_lands

        self.assertEqual(self.pay(order).status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")  # NOT reset to pending_payment
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    @mock.patch("dryMe.mpesa.stk_push")
    def test_end_to_end_tap_then_webhook_credits_the_owner(self, push):
        push.return_value = ok_response("ws_CO_A")
        order = self.make_order()
        self.pay(order)
        self.mark_completed(order)

        resp = APIClient().post(
            "/api/mpesa/callback/test-secret/",
            stk_payload("ws_CO_A", amount=400, receipt="RCPT_A"),
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("360.00"))
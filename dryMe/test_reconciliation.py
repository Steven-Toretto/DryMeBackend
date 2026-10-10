"""
Run with:  python manage.py test dryMe.test_reconciliation -v 2

Uses an injected query function, so nothing here talks to Safaricom.
"""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase
from django.utils import timezone

from .models import PaymentAttempt, Wallet, WalletTransaction
from .services import payments
from .services.reconciliation import (
    FAILED, PROCESSING, SUCCESS, UNKNOWN,
    interpret_query_response, reconcile_pending_attempts,
)
from .test_wallet import WalletTestCase, stk_payload

Status = PaymentAttempt.Status

PROCESSING_RESPONSE = {
    "requestId": "r-1",
    "errorCode": "500.001.1001",
    "errorMessage": "The transaction is being processed",
}


def q_paid(checkout_id):
    return {
        "ResponseCode": "0", "ResponseDescription": "The service request has been accepted successfully",
        "MerchantRequestID": "m-1", "CheckoutRequestID": checkout_id,
        "ResultCode": "0", "ResultDesc": "The service request is processed successfully.",
    }


def q_not_paid(checkout_id, code="1032"):
    return {
        "ResponseCode": "0", "ResponseDescription": "The service request has been accepted successfully",
        "MerchantRequestID": "m-1", "CheckoutRequestID": checkout_id,
        "ResultCode": code, "ResultDesc": "Request cancelled by user",
    }


# =====================================================================
# interpreting Daraja's answer
# =====================================================================
class InterpretResponseTests(SimpleTestCase):

    def test_known_shapes(self):
        self.assertEqual(interpret_query_response(q_paid("A"), "A"), (SUCCESS, 0))
        self.assertEqual(interpret_query_response(q_not_paid("A", "1032"), "A"), (FAILED, 1032))
        self.assertEqual(interpret_query_response(q_not_paid("A", "1037"), "A"), (FAILED, 1037))
        self.assertEqual(interpret_query_response(PROCESSING_RESPONSE, "A"), (PROCESSING, None))

    def test_ints_and_strings_both_work(self):
        self.assertEqual(interpret_query_response({"ResultCode": 0, "CheckoutRequestID": "A"}, "A"), (SUCCESS, 0))

    def test_anything_else_is_unknown_never_a_guess(self):
        for junk in (None, [], "oops", {}, {"errorCode": "404.001.03"}, {"ResultCode": "abc"},
                     {"errorCode": "non_json_response"}):
            self.assertEqual(interpret_query_response(junk, "A"), (UNKNOWN, None), repr(junk))

    def test_answer_about_a_different_prompt_is_ignored(self):
        self.assertEqual(interpret_query_response(q_paid("SOMEONE_ELSE"), "A"), (UNKNOWN, None))


# =====================================================================
# the reconciliation job
# =====================================================================
class ReconcileJobTests(WalletTestCase):

    def attempt(self, order, checkout_id, *, age_minutes=10, amount="400"):
        attempt = PaymentAttempt.objects.create(
            order=order, checkout_request_id=checkout_id, amount=Decimal(amount),
        )
        PaymentAttempt.objects.filter(pk=attempt.pk).update(
            created_at=timezone.now() - timedelta(minutes=age_minutes),
        )
        return attempt

    def pending_order_with(self, *checkout_ids, age_minutes=10):
        order = self.make_order()
        order.payment_status = "pending_payment"
        order.save(update_fields=["payment_status"])
        for cid in checkout_ids:
            self.attempt(order, cid, age_minutes=age_minutes)
        return order

    def run_job(self, responses, **kwargs):
        """responses: {checkout_id: response-dict | Exception}"""
        def fake(checkout_id):
            value = responses[checkout_id]
            if isinstance(value, Exception):
                raise value
            return value
        query = mock.Mock(side_effect=fake)
        kwargs.setdefault("sleep", 0)
        summary = reconcile_pending_attempts(query_fn=query, **kwargs)
        return summary, query

    def status_of(self, checkout_id):
        return PaymentAttempt.objects.get(checkout_request_id=checkout_id).status

    # ---- the happy paths ----
    def test_lost_webhook_for_a_paid_prompt_is_recovered_and_credits_the_owner(self):
        order = self.pending_order_with("A")
        self.mark_completed(order)

        summary, _ = self.run_job({"A": q_paid("A")})

        self.assertEqual(summary.paid, 1)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.amount_paid, Decimal("400.00"))   # from the attempt: the query has no amount
        self.assertIsNone(order.mpesa_transaction_code)           # the query has no receipt either
        attempt = PaymentAttempt.objects.get(checkout_request_id="A")
        self.assertEqual(attempt.status, Status.SUCCESSFUL)
        self.assertIsNone(attempt.transaction_code)
        self.assertFalse(attempt.refund_needed)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("360.00"))
        self.assertLedgerBalanced()

    def test_prompt_that_was_not_paid_is_marked_failed_and_so_is_the_order(self):
        order = self.pending_order_with("A")

        summary, _ = self.run_job({"A": q_not_paid("A", "1037")})

        self.assertEqual(summary.failed, 1)
        self.assertEqual(self.status_of("A"), Status.FAILED)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "failed")

    def test_still_processing_is_left_alone(self):
        order = self.pending_order_with("A")
        summary, _ = self.run_job({"A": PROCESSING_RESPONSE})
        self.assertEqual(summary.still_pending, 1)
        self.assertEqual(self.status_of("A"), Status.PENDING)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")

    # ---- which attempts get queried ----
    def test_young_attempts_are_not_queried(self):
        order = self.make_order()
        self.attempt(order, "FRESH", age_minutes=1)
        summary, query = self.run_job({})
        query.assert_not_called()
        self.assertEqual(summary.checked, 0)

    def test_attempts_older_than_the_window_are_reported_as_stale_not_touched(self):
        order = self.make_order()
        self.attempt(order, "ANCIENT", age_minutes=60 * 24 * 5)
        summary, query = self.run_job({})
        query.assert_not_called()
        self.assertEqual(summary.stale, 1)
        self.assertEqual(self.status_of("ANCIENT"), Status.PENDING)

    def test_only_pending_attempts_are_queried(self):
        order = self.pending_order_with("OLD_FAIL", "GOOD")
        PaymentAttempt.objects.filter(checkout_request_id="OLD_FAIL").update(status=Status.FAILED)
        summary, query = self.run_job({"GOOD": PROCESSING_RESPONSE})
        query.assert_called_once_with("GOOD")

    def test_limit_applies_and_oldest_go_first(self):
        order = self.make_order()
        self.attempt(order, "NEWER", age_minutes=10)
        self.attempt(order, "OLDEST", age_minutes=30)
        self.attempt(order, "MIDDLE", age_minutes=20)
        summary, query = self.run_job(
            {cid: PROCESSING_RESPONSE for cid in ("NEWER", "OLDEST", "MIDDLE")}, limit=2,
        )
        self.assertEqual([c.args[0] for c in query.call_args_list], ["OLDEST", "MIDDLE"])
        self.assertEqual(summary.checked, 2)

    # ---- things going wrong ----
    def test_query_errors_and_garbage_leave_everything_pending(self):
        order = self.pending_order_with("BOOM", "GARBAGE", "WRONG_PROMPT")
        summary, _ = self.run_job({
            "BOOM": Exception("network down"),
            "GARBAGE": {"hello": "world"},
            "WRONG_PROMPT": q_paid("A_DIFFERENT_PROMPT"),
        })
        self.assertEqual(summary.errors, 1)
        self.assertEqual(summary.unrecognised, 2)
        for cid in ("BOOM", "GARBAGE", "WRONG_PROMPT"):
            self.assertEqual(self.status_of(cid), Status.PENDING)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")
        self.assertFalse(WalletTransaction.objects.exists())

    def test_dry_run_reports_but_changes_nothing(self):
        order = self.pending_order_with("PAID", "NOPE")
        self.mark_completed(order)

        summary, _ = self.run_job({"PAID": q_paid("PAID"), "NOPE": q_not_paid("NOPE")}, dry_run=True)

        self.assertEqual((summary.would_pay, summary.would_fail), (1, 1))
        self.assertEqual((summary.paid, summary.failed), (0, 0))
        self.assertEqual(self.status_of("PAID"), Status.PENDING)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")
        self.assertFalse(WalletTransaction.objects.exists())

    # ---- the double-tap safety net ----
    def test_second_prompt_that_was_also_paid_is_flagged_and_not_double_credited(self):
        order = self.pending_order_with("A", "B")
        self.mark_completed(order)
        payments.process_stk_callback(stk_payload("A", amount=400, receipt="RCPT_A"))  # webhook for A arrived

        summary, query = self.run_job({"B": q_paid("B")})   # B's webhook never did

        query.assert_called_once_with("B")                   # A was already resolved, so not queried
        self.assertEqual(summary.duplicate_payments, 1)
        b = PaymentAttempt.objects.get(checkout_request_id="B")
        self.assertEqual(b.status, Status.SUCCESSFUL)
        self.assertTrue(b.refund_needed)
        self.assertEqual(WalletTransaction.objects.filter(type="sale_credit").count(), 1)
        self.assertEqual(Wallet.objects.get(owner=self.owner).balance, Decimal("360.00"))
        order.refresh_from_db()
        self.assertEqual(order.mpesa_transaction_code, "RCPT_A")

    def test_ignored_second_prompt_timing_out_does_not_touch_a_paid_order(self):
        order = self.pending_order_with("A", "B")
        payments.process_stk_callback(stk_payload("A", amount=400, receipt="RCPT_A"))

        summary, _ = self.run_job({"B": q_not_paid("B", "1037")})

        self.assertEqual(summary.failed, 1)
        self.assertEqual(self.status_of("B"), Status.FAILED)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")

    # ---- racing a webhook ----
    def test_webhook_landing_during_the_query_wins_and_nothing_is_credited_twice(self):
        order = self.pending_order_with("A")
        self.mark_completed(order)

        def query_while_webhook_lands(checkout_id):
            payments.process_stk_callback(stk_payload("A", amount=400, receipt="RCPT_A"))
            return q_paid("A")

        summary = reconcile_pending_attempts(query_fn=query_while_webhook_lands, sleep=0)

        self.assertEqual(summary.already_resolved, 1)
        self.assertEqual(summary.paid, 0)
        self.assertEqual(WalletTransaction.objects.filter(type="sale_credit").count(), 1)
        order.refresh_from_db()
        self.assertEqual(order.mpesa_transaction_code, "RCPT_A")

    def test_late_webhook_fills_in_the_receipt_the_query_could_not(self):
        order = self.pending_order_with("A")
        self.mark_completed(order)
        self.run_job({"A": q_paid("A")})
        self.assertIsNone(PaymentAttempt.objects.get(checkout_request_id="A").transaction_code)

        outcome = payments.process_stk_callback(stk_payload("A", amount=400, receipt="RCPT_LATE"))

        self.assertEqual(outcome, "receipt_backfilled")
        self.assertEqual(PaymentAttempt.objects.get(checkout_request_id="A").transaction_code, "RCPT_LATE")
        order.refresh_from_db()
        self.assertEqual(order.mpesa_transaction_code, "RCPT_LATE")
        self.assertEqual(WalletTransaction.objects.filter(type="sale_credit").count(), 1)  # still credited once

    def test_late_webhook_never_overwrites_a_receipt_or_relabels_a_duplicate(self):
        order = self.pending_order_with("A", "B")
        payments.process_stk_callback(stk_payload("A", amount=400, receipt="RCPT_A"))
        self.run_job({"B": q_paid("B")})   # B flagged as a duplicate payment, no receipt

        outcome = payments.process_stk_callback(stk_payload("B", amount=400, receipt="RCPT_B"))

        self.assertEqual(outcome, "duplicate")
        order.refresh_from_db()
        self.assertEqual(order.mpesa_transaction_code, "RCPT_A")   # B's receipt must not replace A's
        self.assertIsNone(PaymentAttempt.objects.get(checkout_request_id="B").transaction_code)

    def test_running_the_job_twice_is_harmless(self):
        order = self.pending_order_with("A")
        self.mark_completed(order)
        self.run_job({"A": q_paid("A")})
        summary, query = self.run_job({"A": q_paid("A")})
        query.assert_not_called()
        self.assertEqual(WalletTransaction.objects.filter(type="sale_credit").count(), 1)

    def test_payment_for_a_deleted_order_is_flagged(self):
        order = self.pending_order_with("A")
        order.delete()
        summary, _ = self.run_job({"A": q_paid("A")})
        self.assertEqual(summary.orphaned_payments, 1)
        attempt = PaymentAttempt.objects.get(checkout_request_id="A")
        self.assertTrue(attempt.refund_needed)
        self.assertEqual(attempt.status, Status.SUCCESSFUL)


# =====================================================================
# mpesa.stk_query + management command
# =====================================================================
class StkQueryHelperTests(SimpleTestCase):

    @mock.patch("dryMe.mpesa.generate_password", return_value=("pw", "20260101120000"))
    @mock.patch("dryMe.mpesa.get_access_token", return_value="tok")
    @mock.patch("dryMe.mpesa.requests.post")
    def test_builds_the_request_and_returns_the_body(self, post, _token, _pw):
        from dryMe import mpesa
        post.return_value.json.return_value = {"ResultCode": "0"}

        with self.settings(MPESA_SHORTCODE="174379", MPESA_BASE_URL="https://example.test/"):
            result = mpesa.stk_query("ws_CO_1")

        self.assertEqual(result, {"ResultCode": "0"})
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://example.test/mpesa/stkpushquery/v1/query")
        self.assertEqual(kwargs["json"], {
            "BusinessShortCode": "174379", "Password": "pw",
            "Timestamp": "20260101120000", "CheckoutRequestID": "ws_CO_1",
        })
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer tok")

    @mock.patch("dryMe.mpesa.generate_password", return_value=("pw", "ts"))
    @mock.patch("dryMe.mpesa.get_access_token", return_value="tok")
    @mock.patch("dryMe.mpesa.requests.post")
    def test_non_json_body_does_not_raise(self, post, _token, _pw):
        from dryMe import mpesa
        post.return_value.json.side_effect = ValueError("not json")
        post.return_value.text = "<html>Bad gateway</html>"
        post.return_value.status_code = 502

        result = mpesa.stk_query("ws_CO_1")

        self.assertEqual(result["errorCode"], "non_json_response")
        self.assertEqual(interpret_query_response(result, "ws_CO_1"), (UNKNOWN, None))


class ReconcileCommandTests(WalletTestCase):

    def old_pending(self, checkout_id):
        order = self.make_order()
        order.payment_status = "pending_payment"
        order.save(update_fields=["payment_status"])
        attempt = PaymentAttempt.objects.create(order=order, checkout_request_id=checkout_id, amount=Decimal("400"))
        PaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        return order

    @mock.patch("dryMe.mpesa.stk_query")
    def test_command_runs_and_prints_a_summary(self, query):
        order = self.old_pending("A")
        query.return_value = q_paid("A")
        out = StringIO()

        call_command("reconcile_payments", "--sleep=0", stdout=out)

        text = out.getvalue()
        self.assertIn("Checked 1 pending attempt(s)", text)
        self.assertRegex(text, r"paid:\s+1\b")
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")

    @mock.patch("dryMe.mpesa.stk_query")
    def test_dry_run_flag(self, query):
        order = self.old_pending("A")
        query.return_value = q_paid("A")
        out = StringIO()

        call_command("reconcile_payments", "--sleep=0", "--dry-run", stdout=out)

        self.assertIn("DRY RUN", out.getvalue())
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending_payment")

    @mock.patch("dryMe.mpesa.stk_query")
    def test_exits_non_zero_when_every_query_fails(self, query):
        self.old_pending("A")
        query.side_effect = Exception("auth failed")
        with self.assertRaises(CommandError):
            call_command("reconcile_payments", "--sleep=0", stdout=StringIO())

    @mock.patch("dryMe.mpesa.stk_query")
    def test_warns_when_refunds_are_needed(self, query):
        order = self.old_pending("A")
        order.delete()
        query.return_value = q_paid("A")
        out = StringIO()
        call_command("reconcile_payments", "--sleep=0", stdout=out)
        self.assertIn("need a refund", out.getvalue())

    @mock.patch("dryMe.mpesa.stk_query")
    def test_nothing_to_do_is_a_clean_run(self, query):
        out = StringIO()
        call_command("reconcile_payments", "--sleep=0", stdout=out)
        query.assert_not_called()
        self.assertIn("Done.", out.getvalue())
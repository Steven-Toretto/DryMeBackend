"""
Run with:  python manage.py test dryMe.test_notifications -v 2

Notifications are queued with transaction.on_commit, and Django's TestCase never commits,
so every test that expects one wraps the action in captureOnCommitCallbacks(execute=True).
"""
from decimal import Decimal
from unittest import mock

from rest_framework.test import APIClient

from .models import Notification
from .services.wallet import (
    approve_payout,
    fail_payout,
    mark_payout_paid,
    reject_payout,
    request_payout,
    settle_order,
)
from .test_wallet import WalletTestCase


class PayoutNotificationTests(WalletTestCase):

    def setUp(self):
        super().setUp()
        self.fund("1000")
        self.payout = request_payout(self.owner, "500", "mpesa", "0712345678")  # fee 10 -> send 490

    def latest(self):
        return Notification.objects.filter(user=self.owner).order_by("-id").first()

    def test_approve_tells_the_owner(self):
        with self.captureOnCommitCallbacks(execute=True):
            approve_payout(self.payout.pk, self.owner)
        note = self.latest()
        self.assertEqual(note.notif_type, "payout_approved")
        self.assertIn("KES 500", note.message)
        self.assertIn("KES 490", note.message)
        self.assertIn("0712 345 678", note.message)

    def test_paid_includes_the_reference_and_the_net_amount(self):
        with self.captureOnCommitCallbacks(execute=True):
            mark_payout_paid(self.payout.pk, self.owner, "RKT12345")
        note = self.latest()
        self.assertEqual(note.notif_type, "payout_paid")
        self.assertIn("KES 490", note.message)
        self.assertIn("RKT12345", note.message)

    def test_reject_gives_the_reason_and_says_the_money_is_back(self):
        with self.captureOnCommitCallbacks(execute=True):
            reject_payout(self.payout.pk, self.owner, "Name didn't match")
        note = self.latest()
        self.assertEqual(note.notif_type, "payout_rejected")
        self.assertIn("Name didn't match", note.message)
        self.assertIn("back in your wallet", note.message)

    def test_failed_transfer(self):
        approve_payout(self.payout.pk, self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            fail_payout(self.payout.pk, self.owner, "B2C declined")
        self.assertEqual(self.latest().notif_type, "payout_failed")

    def test_a_very_long_reason_still_fits_and_keeps_the_ending(self):
        with self.captureOnCommitCallbacks(execute=True):
            reject_payout(self.payout.pk, self.owner, "x" * 1000)
        note = self.latest()
        self.assertLessEqual(len(note.message), 255)
        self.assertTrue(note.message.endswith("back in your wallet."))

    def test_a_refused_transition_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            reject_payout(self.payout.pk, self.owner, "x")
        before = Notification.objects.count()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(Exception):
                reject_payout(self.payout.pk, self.owner, "x")     # already finalised
        self.assertEqual(Notification.objects.count(), before)

    def test_nothing_is_sent_until_the_transaction_commits(self):
        approve_payout(self.payout.pk, self.owner)                    # no callback execution
        self.assertFalse(Notification.objects.filter(notif_type="payout_approved").exists())

    def test_a_notification_failure_can_never_break_the_payout(self):
        with mock.patch("dryMe.services.notifications.notify", side_effect=Exception("db down")):
            with self.captureOnCommitCallbacks(execute=True):
                approve_payout(self.payout.pk, self.owner)
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, "approved")
        self.assertFalse(Notification.objects.exists())


class EarningsNotificationTests(WalletTestCase):

    def test_completing_a_paid_order_tells_the_owner_they_were_credited(self):
        order = self.make_order()
        self.mark_paid(order)
        self.mark_completed(order)
        with self.captureOnCommitCallbacks(execute=True):
            settle_order(order.pk)
        note = Notification.objects.get(user=self.owner)
        self.assertEqual(note.notif_type, "wallet_credited")
        self.assertEqual(note.order_id, order.pk)
        self.assertIn("KES 360", note.message)
        self.assertIn(f"#{order.pk:05d}", note.message)

    def test_settling_twice_notifies_once(self):
        order = self.make_order()
        self.mark_paid(order)
        self.mark_completed(order)
        with self.captureOnCommitCallbacks(execute=True):
            settle_order(order.pk)
            settle_order(order.pk)
        self.assertEqual(Notification.objects.filter(notif_type="wallet_credited").count(), 1)


class NotificationApiShowsThemTests(WalletTestCase):

    def test_owner_sees_a_payout_notification_through_the_existing_endpoints(self):
        self.fund("1000")
        payout = request_payout(self.owner, "500", "mpesa", "0712345678")
        with self.captureOnCommitCallbacks(execute=True):
            mark_payout_paid(payout.pk, self.owner, "RKT12345")

        client = APIClient()
        client.force_authenticate(self.owner)

        body = client.get("/api/notifications/").json()
        self.assertEqual(body["unread_count"], 1)
        self.assertEqual(body["results"][0]["notif_type"], "payout_paid")
        self.assertFalse(body["results"][0]["is_read"])

        self.assertEqual(client.get("/api/notifications/unread-count/").json()["count"], 1)
        self.assertEqual(client.put("/api/notifications/mark-read/").status_code, 200)
        self.assertEqual(client.get("/api/notifications/unread-count/").json()["count"], 0)

    def test_other_users_never_see_them(self):
        self.fund("1000")
        payout = request_payout(self.owner, "500", "mpesa", "0712345678")
        with self.captureOnCommitCallbacks(execute=True):
            approve_payout(payout.pk, self.owner)
        client = APIClient()
        client.force_authenticate(self.customer)
        self.assertEqual(client.get("/api/notifications/").json()["count"], 0)
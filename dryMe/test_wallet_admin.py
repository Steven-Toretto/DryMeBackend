"""
Run with:  python manage.py test dryMe.test_wallet_admin -v 2

Drives the real admin changelist (POSTing the action form), so it covers the
action wiring, the extra reference/reason inputs and the permission rules.
"""
from decimal import Decimal

from django.db import transaction
from django.urls import reverse

from .models import Payout, User, Wallet, WalletTransaction
from .services.wallet import _apply, get_locked_wallet, request_payout
from .test_wallet import WalletTestCase


class PayoutAdminTests(WalletTestCase):

    def setUp(self):
        super().setUp()
        self.boss = User.objects.create_superuser(
            username="boss", email="boss@test.com", password="pass12345",
            role="customer", phone="0700000000", location="Nairobi",
        )
        self.client.force_login(self.boss)
        self.fund("1000")
        self.payout = request_payout(self.owner, "500", "mpesa", "0712345678")  # fee 10 -> send 490
        # ✅ Fixed case-sensitivity routing layout matching django_apps registration
        self.changelist = reverse("admin:dryMe_payout_changelist")

    # ---- helpers ----
    def run_action(self, action, payouts, **extra):
        data = {
            "action": action,
            "index": "0",
            "_selected_action": [str(p.pk) for p in payouts],
            "reference": "",
            "reason": "",
        }
        data.update(extra)
        return self.client.post(self.changelist, data, follow=True)

    def messages(self, response):
        return [str(m) for m in response.context["messages"]]

    def second_owner_payout(self):
        owner2 = User.objects.create_user(
            username="owner2", email="owner2@test.com", password="pass12345",
            role="owner", phone="0733345678", location="Nairobi",
        )
        with transaction.atomic():
            _apply(get_locked_wallet(owner2), "adjustment", Decimal("1000"))
        return request_payout(owner2, "300", "mpesa", "0733345678")

    def balance(self):
        return Wallet.objects.get(owner=self.owner).balance

    # ---- the list ----
    def test_changelist_shows_what_to_send_and_where(self):
        resp = self.client.get(self.changelist)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "254712345678")   # destination
        self.assertContains(resp, "TO SEND (KES)")
        self.assertContains(resp, "490.00")         # net, not gross
        self.assertContains(resp, 'name="reference"')  # the extra action inputs are present
        self.assertContains(resp, 'name="reason"')

    # ---- approve ----
    def test_approve(self):
        resp = self.run_action("approve_selected", [self.payout])
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, "approved")
        self.assertEqual(self.payout.reviewed_by, self.boss)
        self.assertTrue(any("Approved 1 payout" in m for m in self.messages(resp)))

    # ---- mark paid ----
    def test_mark_paid_stores_reference_and_leaves_the_balance_alone(self):
        resp = self.run_action("mark_paid", [self.payout], reference="RKT12345")
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, "paid")
        self.assertEqual(self.payout.reference, "RKT12345")
        self.assertEqual(self.payout.reviewed_by, self.boss)
        self.assertIsNotNone(self.payout.paid_at)
        self.assertEqual(self.balance(), Decimal("500.00"))  # already held at request time
        self.assertTrue(any("Marked paid 1 payout" in m for m in self.messages(resp)))

    def test_mark_paid_needs_a_reference(self):
        resp = self.run_action("mark_paid", [self.payout], reference="   ")
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, "requested")
        self.assertTrue(any("payment reference" in m for m in self.messages(resp)))

    def test_mark_paid_refuses_more_than_one_payout(self):
        other = self.second_owner_payout()
        resp = self.run_action("mark_paid", [self.payout, other], reference="RKT12345")
        self.assertEqual(Payout.objects.filter(status="paid").count(), 0)
        self.assertTrue(any("exactly one" in m for m in self.messages(resp)))

    # ---- reject / fail ----
    def test_reject_restores_the_full_amount_and_records_the_reason(self):
        resp = self.run_action("reject_selected", [self.payout], reason="Name didn't match")
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, "rejected")
        self.assertEqual(self.payout.reject_reason, "Name didn't match")
        self.assertEqual(self.balance(), Decimal("1000.00"))  # 500 back, fee included
        self.assertTrue(any("Rejected 1 payout" in m for m in self.messages(resp)))

    def test_reject_needs_a_reason(self):
        resp = self.run_action("reject_selected", [self.payout], reason="")
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, "requested")
        self.assertEqual(self.balance(), Decimal("500.00"))
        self.assertTrue(any("reason is required" in m for m in self.messages(resp)))

    def test_mark_failed_after_approval_restores_the_balance(self):
        self.run_action("approve_selected", [self.payout])
        self.run_action("mark_failed", [self.payout], reason="B2C declined")
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, "failed")
        self.assertEqual(self.balance(), Decimal("1000.00"))

    def test_reject_can_handle_several_at_once(self):
        other = self.second_owner_payout()
        resp = self.run_action("reject_selected", [self.payout, other], reason="Maintenance window")
        self.assertEqual(Payout.objects.filter(status="rejected").count(), 2)
        self.assertTrue(any("Rejected 2 payouts" in m for m in self.messages(resp)))

    # ---- safety ----
    def test_running_an_action_twice_cannot_double_refund(self):
        self.run_action("reject_selected", [self.payout], reason="x")
        resp = self.run_action("reject_selected", [self.payout], reason="x")
        self.assertEqual(self.balance(), Decimal("1000.00"))
        self.assertEqual(WalletTransaction.objects.filter(type="payout_reversal").count(), 1)
        self.assertTrue(any("already finalised" in m for m in self.messages(resp)))

    def test_a_paid_payout_cannot_be_rejected_afterwards(self):
        self.run_action("mark_paid", [self.payout], reference="RKT12345")
        self.run_action("reject_selected", [self.payout], reason="changed my mind")
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, "paid")
        self.assertEqual(self.balance(), Decimal("500.00"))

    def test_payouts_cannot_be_added_edited_or_deleted_through_the_admin(self):
        add = self.client.get(reverse("admin:dryMe_payout_add"))
        self.assertEqual(add.status_code, 403)

        delete = self.client.get(reverse("admin:dryMe_payout_delete", args=[self.payout.pk]))
        self.assertEqual(delete.status_code, 403)

        # the change page opens, but every money field is read-only (no inputs for them)
        change = self.client.get(reverse("admin:dryMe_payout_change", args=[self.payout.pk]))
        self.assertEqual(change.status_code, 200)
        for field in ("amount", "fee", "net_amount", "status", "destination"):
            self.assertNotContains(change, f'name="{field}"')

    def test_staff_without_permissions_cannot_see_payouts(self):
        staff = User.objects.create_user(
            username="clerk", email="clerk@test.com", password="pass12345",
            role="customer", phone="0700000001", location="Nairobi", is_staff=True,
        )
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.changelist).status_code, 403)
        resp = self.client.post(self.changelist, {
            "action": "mark_paid", "index": "0", "_selected_action": [str(self.payout.pk)],
            "reference": "RKT12345", "reason": "",
        })
        self.assertEqual(resp.status_code, 403)
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, "requested")


class WalletAdminTests(WalletTestCase):

    def setUp(self):
        super().setUp()
        self.boss = User.objects.create_superuser(
            username="boss", email="boss@test.com", password="pass12345",
            role="customer", phone="0700000000", location="Nairobi",
        )
        self.client.force_login(self.boss)
        self.fund("1000")
        # ✅ Fixed case-sensitivity routing layout matching django_apps registration
        self.changelist = reverse("admin:dryMe_wallet_changelist")

    def test_wallet_list_and_detail_show_a_passing_integrity_check(self):
        wallet = Wallet.objects.get(owner=self.owner)

        lst = self.client.get(self.changelist)
        self.assertEqual(lst.status_code, 200)
        self.assertContains(lst, "1000.00")
        self.assertContains(lst, "icon-yes")        # ledger_matches renders the green tick

        detail = self.client.get(reverse("admin:dryMe_wallet_change", args=[wallet.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "test funding")  # the ledger inline

    def test_integrity_check_flags_a_wallet_that_no_longer_matches_its_ledger(self):
        Wallet.objects.filter(owner=self.owner).update(balance=Decimal("999999.00"))  # simulated corruption
        lst = self.client.get(self.changelist)
        self.assertContains(lst, "icon-no")

    def test_wallets_and_ledger_are_view_only(self):
        wallet = Wallet.objects.get(owner=self.owner)
        # ✅ Fixed case-sensitivity routing layout matching django_apps registration
        tx_changelist = reverse("admin:dryMe_wallettransaction_changelist")
        tx = WalletTransaction.objects.first()

        self.assertEqual(self.client.get(reverse("admin:dryMe_wallet_add")).status_code, 403)
        self.assertEqual(
self.client.get(reverse("admin:dryMe_wallet_change", args=[wallet.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:dryMe_wallet_delete", args=[wallet.pk])).status_code, 403)

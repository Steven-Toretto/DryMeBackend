"""
Run with:  python manage.py test dryMe.test_profile_stats -v 2

The owner Profile page's "Gross sales": money actually received on orders that were completed.
It must line up with the wallet: earnings = gross sales - commission.
"""
from decimal import Decimal

from rest_framework.test import APIClient

from .services.wallet import settle_order
from .test_wallet import WalletTestCase


class OwnerGrossSalesTests(WalletTestCase):

    def gross_sales(self, user=None):
        client = APIClient()
        client.force_authenticate(user or self.owner)
        return client.get("/api/profile/").json()["stats"]["revenue"]

    def sale(self, **flags):
        """A 4 kg x KES 100 = KES 400 order, paid and completed unless told otherwise."""
        order = self.make_order()
        if flags.get("paid", True):
            self.mark_paid(order)
        if flags.get("completed", True):
            self.mark_completed(order)
        if flags.get("status"):
            order.status = flags["status"]
            order.save(update_fields=["status"])
        if flags.get("archived"):
            order.owner_archived = True
            order.save(update_fields=["owner_archived"])
        return order

    def test_no_sales_is_zero(self):
        self.assertEqual(Decimal(self.gross_sales()), Decimal("0"))

    def test_is_a_string_not_a_float(self):
        # DRF turns a raw Decimal into a float; money goes over the wire as "400.00" instead.
        self.sale()
        value = self.gross_sales()
        self.assertIsInstance(value, str)
        self.assertEqual(value, "400.00")

    def test_only_paid_and_completed_orders_count(self):
        self.sale()                                        # counts: 400
        self.sale(paid=False)                              # completed but never paid
        self.sale(completed=False)                         # paid, still in progress
        self.sale(status="declined")                       # paid then declined -> refunded, not a sale
        self.sale(status="cancelled")
        self.assertEqual(Decimal(self.gross_sales()), Decimal("400.00"))

    def test_archived_sales_still_count(self):
        self.sale(archived=True)
        self.sale()
        self.assertEqual(Decimal(self.gross_sales()), Decimal("800.00"))

    def test_not_limited_to_one_page_of_orders(self):
        for _ in range(12):
            self.sale()
        self.assertEqual(Decimal(self.gross_sales()), Decimal("4800.00"))

    def test_uses_what_was_actually_received(self):
        order = self.sale()
        order.amount_paid = Decimal("399.00")
        order.save(update_fields=["amount_paid"])
        self.assertEqual(Decimal(self.gross_sales()), Decimal("399.00"))

    def test_gross_sales_minus_commission_is_what_the_wallet_earned(self):
        for _ in range(3):
            order = self.sale()
            settle_order(order.pk)

        client = APIClient()
        client.force_authenticate(self.owner)
        earned = Decimal(client.get("/api/owner/wallet/").json()["lifetime_earned"])

        self.assertEqual(Decimal(self.gross_sales()), Decimal("1200.00"))
        self.assertEqual(Decimal(self.gross_sales()) - earned, Decimal("120.00"))   # the 10% commission

    def test_other_owners_sales_are_not_included(self):
        from .models import User
        other = User.objects.create_user(
            username="owner2", email="owner2@test.com", password="pass12345",
            role="owner", phone="0733345678", location="Nairobi",
        )
        self.sale()
        self.assertEqual(Decimal(self.gross_sales(other)), Decimal("0"))
"""
Run with:  python manage.py test dryMe.test_owner_stats -v 2
"""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient

from .models import Order, Shop, User
from .services.owner_stats import owner_stats
from .test_wallet import WalletTestCase

STATS = "/api/owner/stats/"
ALL_STATUSES = {"pending", "confirmed", "washing", "completed", "declined", "cancelled"}


class OwnerStatsTests(WalletTestCase):

    def setUp(self):
        super().setUp()
        self.customer2 = User.objects.create_user(
            username="cust2", email="cust2@test.com", password="pass12345",
            role="customer", phone="0744345678", location="Nairobi",
        )
        self.other_owner = User.objects.create_user(
            username="owner2", email="owner2@test.com", password="pass12345",
            role="owner", phone="0733345678", location="Nairobi",
        )

    # ---- helpers ----
    def order(self, status="pending", customer=None, shop=None, service=None, **update):
        order = Order.objects.create(
            user=customer or self.customer,
            shop=shop or self.shop,
            service=service or self.service,
            weight=Decimal("2"),
        )
        Order.objects.filter(pk=order.pk).update(status=status, **update)
        return order

    def api(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    # ---- who may call it ----
    def test_anonymous_gets_401_and_customers_get_403(self):
        self.assertEqual(self.api().get(STATS).status_code, 401)
        self.assertEqual(self.api(self.customer).get(STATS).status_code, 403)

    # ---- the numbers ----
    def test_new_owner_gets_zeroes_for_every_status(self):
        data = self.api(self.owner).get(STATS).json()
        self.assertEqual(data["total_orders"], 0)
        self.assertEqual(data["orders_this_week"], 0)
        self.assertEqual(data["unique_customers"], 0)
        self.assertEqual(data["shops_count"], 1)
        self.assertEqual(data["status_counts"], {status: 0 for status in ALL_STATUSES})

    def test_status_keys_follow_the_model(self):
        self.assertEqual({v for v, _ in Order.STATUS_CHOICES}, ALL_STATUSES)
        self.assertEqual(set(owner_stats(self.owner)["status_counts"]), ALL_STATUSES)

    def test_counts_every_status(self):
        for status in ("pending", "pending", "confirmed", "washing", "completed", "completed", "completed",
                       "declined", "cancelled"):
            self.order(status)

        data = self.api(self.owner).get(STATS).json()

        self.assertEqual(data["total_orders"], 9)
        self.assertEqual(data["status_counts"], {
            "pending": 2, "confirmed": 1, "washing": 1, "completed": 3, "declined": 1, "cancelled": 1,
        })

    def test_not_limited_to_the_first_page_of_orders(self):
        # The dashboard bug this endpoint exists to fix: the orders API returns 10 per page.
        for _ in range(23):
            self.order("completed")
        self.assertEqual(self.api(self.owner).get(STATS).json()["total_orders"], 23)
        self.assertEqual(self.api(self.owner).get(STATS).json()["status_counts"]["completed"], 23)

    def test_archived_orders_still_count(self):
        self.order("completed", owner_archived=True)
        self.order("completed")
        data = self.api(self.owner).get(STATS).json()
        self.assertEqual(data["total_orders"], 2)
        self.assertEqual(data["status_counts"]["completed"], 2)

    def test_unique_customers_counts_people_not_orders(self):
        self.order()
        self.order()
        self.order(customer=self.customer2)
        self.assertEqual(self.api(self.owner).get(STATS).json()["unique_customers"], 2)

    def test_this_week_is_a_rolling_seven_days(self):
        now = timezone.now()
        self.order()                                                          # today
        self.order(created_at=now - timedelta(days=6, hours=23))              # still inside the window
        self.order(created_at=now - timedelta(days=8))                        # outside
        data = self.api(self.owner).get(STATS).json()
        self.assertEqual(data["orders_this_week"], 2)
        self.assertEqual(data["total_orders"], 3)

    def test_only_this_owners_shops_count(self):
        other_shop = Shop.objects.create(owner=self.other_owner, name="Other", location="CBD", description="x")
        other_service = other_shop.services.create(name="Wash", pricing_type="per_kg", price=Decimal("50"))
        self.order()
        self.order(shop=other_shop, service=other_service, customer=self.customer2)

        mine = self.api(self.owner).get(STATS).json()
        theirs = self.api(self.other_owner).get(STATS).json()

        self.assertEqual((mine["total_orders"], mine["unique_customers"]), (1, 1))
        self.assertEqual((theirs["total_orders"], theirs["unique_customers"]), (1, 1))

    def test_shops_count_includes_every_shop_the_owner_has(self):
        Shop.objects.create(owner=self.owner, name="Second", location="Westlands", description="x")
        self.assertEqual(self.api(self.owner).get(STATS).json()["shops_count"], 2)

    def test_it_is_two_queries_however_many_orders_there_are(self):
        for status in ("pending", "completed", "declined"):
            self.order(status)
        with self.assertNumQueries(2):
            owner_stats(self.owner)
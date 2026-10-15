"""
Run with:  python manage.py test dryMe.test_owner_orders -v 2

GET owner/orders/?status=…&page=…  — the Orders tab loads one status at a time, 10 per page.
"""
from decimal import Decimal

from rest_framework.test import APIClient

from .models import Order, User
from .test_wallet import WalletTestCase

ORDERS = "/api/owner/orders/"
ARCHIVED = "/api/owner/orders/archived/"


class OwnerOrdersFilterTests(WalletTestCase):

    def setUp(self):
        super().setUp()
        self.other_owner = User.objects.create_user(
            username="owner2", email="owner2@test.com", password="pass12345",
            role="owner", phone="0733345678", location="Nairobi",
        )

    def order(self, status="pending", **update):
        order = Order.objects.create(
            user=self.customer, shop=self.shop, service=self.service, weight=Decimal("2"),
        )
        Order.objects.filter(pk=order.pk).update(status=status, **update)
        return order

    def get(self, url=ORDERS, user=None, **params):
        client = APIClient()
        client.force_authenticate(user or self.owner)
        return client.get(url, params)

    def test_no_filter_still_returns_every_non_archived_order(self):
        self.order("pending")
        self.order("completed")
        self.order("completed", owner_archived=True)
        body = self.get().json()
        self.assertEqual(body["count"], 2)

    def test_status_filter_returns_only_that_status(self):
        for status in ("pending", "pending", "confirmed", "completed"):
            self.order(status)
        body = self.get(status="pending").json()
        self.assertEqual(body["count"], 2)
        self.assertTrue(all(row["status"] == "pending" for row in body["results"]))

    def test_filter_applies_before_pagination_so_old_orders_are_reachable(self):
        # The bug: 25 newer completed orders used to push the one old pending order off page 1 forever.
        old_pending = self.order("pending")
        for _ in range(25):
            self.order("completed")

        body = self.get(status="pending").json()

        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], old_pending.pk)

    def test_pages_walk_the_whole_list_newest_first(self):
        ids = [self.order("completed").pk for _ in range(23)]
        seen = []
        page = 1
        while True:
            body = self.get(status="completed", page=page).json()
            seen += [row["id"] for row in body["results"]]
            if not body["next"]:
                break
            page += 1
        self.assertEqual(len(seen), 23)
        self.assertEqual(sorted(seen), sorted(ids))
        self.assertEqual(seen, sorted(seen, reverse=True))     # newest first

    def test_unknown_status_is_a_400_not_an_empty_list(self):
        resp = self.get(status="shipped")
        self.assertEqual(resp.status_code, 400)

    def test_archived_orders_stay_out_of_the_active_list_even_when_filtered(self):
        self.order("completed", owner_archived=True)
        self.assertEqual(self.get(status="completed").json()["count"], 0)

    def test_archived_endpoint_pages_too(self):
        for _ in range(12):
            self.order("completed", owner_archived=True)
        body = self.get(ARCHIVED).json()
        self.assertEqual(body["count"], 12)
        self.assertEqual(len(body["results"]), 10)
        self.assertIsNotNone(body["next"])

    def test_only_this_owners_orders(self):
        self.order("pending")
        self.assertEqual(self.get(status="pending", user=self.other_owner).json()["count"], 0)

    def test_customers_cannot_use_the_owner_list(self):
        self.assertEqual(self.get(user=self.customer).status_code, 403)
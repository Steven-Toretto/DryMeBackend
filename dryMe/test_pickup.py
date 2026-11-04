"""
Run with:  python manage.py test dryMe.test_pickup -v 2

Pickup windows: two-hour slots between 8am and 8pm Nairobi time (always UTC+3), a one-hour lead
time, and a week's reach. The server decides what can be booked.
"""
from datetime import date, datetime, timedelta
from unittest import mock

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from .models import Order
from .services import pickup
from .test_wallet import WalletTestCase

ORDERS = "/api/orders/"
SLOTS = "/api/pickup-slots/"


def at(hour, minute=0, day=2):
    """A moment in Nairobi on 2 Nov 2026 (a Monday)."""
    return datetime(2026, 11, day, hour, minute, tzinfo=pickup.EAT)


def now_is(moment):
    return mock.patch("dryMe.services.pickup.now_eat", return_value=moment)


# =====================================================================
# the pure rules
# =====================================================================
class SlotRuleTests(SimpleTestCase):

    def test_labels_read_like_a_clock(self):
        self.assertEqual(pickup.slot_label("08-10"), "8:00 – 10:00am")
        self.assertEqual(pickup.slot_label("10-12"), "10:00am – 12:00pm")   # crosses noon, so both are named
        self.assertEqual(pickup.slot_label("12-14"), "12:00 – 2:00pm")
        self.assertEqual(pickup.slot_label("16-18"), "4:00 – 6:00pm")
        self.assertEqual(pickup.slot_label("18-20"), "6:00 – 8:00pm")

    def test_day_labels(self):
        today = date(2026, 11, 2)
        self.assertEqual(pickup.day_label(today, today), "Today")
        self.assertEqual(pickup.day_label(date(2026, 11, 3), today), "Tomorrow")
        self.assertEqual(pickup.day_label(date(2026, 11, 4), today), "Wed 4 Nov")

    def test_the_rest_of_today_shrinks_as_the_day_goes(self):
        with now_is(at(9, 0)):
            today = pickup.available_days()[0]
        self.assertEqual(today["label"], "Today")
        self.assertEqual([s["key"] for s in today["slots"]], ["10-12", "12-14", "14-16", "16-18", "18-20"])

    def test_a_window_needs_an_hours_notice(self):
        with now_is(at(15, 0)):
            keys = [s["key"] for s in pickup.available_days()[0]["slots"]]
        self.assertEqual(keys, ["16-18", "18-20"])                         # 4pm is exactly an hour away: still bookable
        with now_is(at(15, 1)):
            keys = [s["key"] for s in pickup.available_days()[0]["slots"]]
        self.assertEqual(keys, ["18-20"])

    def test_a_day_with_nothing_left_is_left_out(self):
        with now_is(at(18, 30)):
            days = pickup.available_days()
        self.assertEqual(days[0]["label"], "Tomorrow")

    def test_a_week_is_offered(self):
        with now_is(at(7, 0)):
            days = pickup.available_days()
        self.assertEqual(len(days), 7)
        self.assertEqual(days[-1]["date"], "2026-11-08")

    @override_settings(PICKUP_DAYS_AHEAD=1, PICKUP_LEAD_MINUTES=0)
    def test_reach_and_lead_time_are_settings(self):
        with now_is(at(15, 1)):
            days = pickup.available_days()
        self.assertEqual(len(days), 2)
        self.assertEqual([s["key"] for s in days[0]["slots"]], ["16-18", "18-20"])   # no notice needed

    def test_check_slot_accepts_what_can_be_booked(self):
        with now_is(at(9, 0)):
            pickup.check_slot(date(2026, 11, 2), "10-12")                  # starts in exactly an hour: enough notice
            pickup.check_slot(date(2026, 11, 3), "08-10")
            pickup.check_slot(date(2026, 11, 8), "18-20")                  # the last day offered (today + 6)

    def test_check_slot_refuses_what_cannot_be_booked(self):
        refused = [
            (date(2026, 11, 1), "12-14"),      # yesterday
            (date(2026, 11, 2), "08-10"),      # started an hour ago
            (date(2026, 11, 9), "08-10"),      # one day past the reach
            (date(2026, 11, 3), "07-09"),      # not one of the windows
        ]
        with now_is(at(9, 0)):
            for day, key in refused:
                with self.assertRaises(pickup.PickupError, msg=f"{day} {key}"):
                    pickup.check_slot(day, key)
        with now_is(at(9, 1)):
            with self.assertRaises(pickup.PickupError):
                pickup.check_slot(date(2026, 11, 2), "10-12")              # one minute short of an hour's notice

    def test_today_is_nairobis_today_not_utcs(self):
        # 22:30 UTC on 2 Nov is 01:30 on 3 Nov in Nairobi.
        late_utc = datetime(2026, 11, 2, 22, 30, tzinfo=pickup.dt_timezone.utc)
        with mock.patch("django.utils.timezone.now", return_value=late_utc):
            first = pickup.available_days()[0]
        self.assertEqual((first["date"], first["label"]), ("2026-11-03", "Today"))


# =====================================================================
# the public slots endpoint
# =====================================================================
class SlotsEndpointTests(WalletTestCase):

    def test_anyone_can_read_the_slots_and_they_come_as_json(self):
        with now_is(at(9, 0)):
            resp = APIClient().get(SLOTS)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Type"].startswith("application/json"))
        body = resp.json()
        self.assertEqual(body["timezone"], "Africa/Nairobi")
        self.assertEqual(body["days"][0]["label"], "Today")
        self.assertEqual(body["days"][0]["slots"][0], {"key": "10-12", "label": "10:00am – 12:00pm"})
        self.assertEqual(body["days"][1]["label"], "Tomorrow")
        self.assertEqual(len(body["days"][1]["slots"]), 6)


# =====================================================================
# booking with a pickup window
# =====================================================================
class BookingWindowTests(WalletTestCase):

    def setUp(self):
        super().setUp()
        self.cust = APIClient()
        self.cust.force_authenticate(self.customer)

    def book(self, **extra):
        body = {
            "shop_id": self.shop.pk, "service_id": self.service.pk, "weight": 4,
            "customer_phone": "0722345678", "customer_location": "Kilimani",
        }
        body.update(extra)
        return self.cust.post(ORDERS, body, format="json")

    def test_a_valid_window_is_saved_and_labelled(self):
        with now_is(at(9, 0)):
            resp = self.book(pickup_date="2026-11-03", pickup_slot="08-10")
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["pickup_date"], "2026-11-03")
        self.assertEqual(body["pickup_slot"], "08-10")
        self.assertEqual(body["pickup_slot_label"], "8:00 – 10:00am")
        order = Order.objects.get(pk=body["id"])
        self.assertEqual(order.pickup_date, date(2026, 11, 3))
        self.assertEqual(order.pickup_slot, "08-10")

    def test_booking_without_a_window_still_works(self):
        resp = self.book()                                                  # an older app, or an API client
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.json()["pickup_date"])
        self.assertEqual(resp.json()["pickup_slot_label"], "")

    def test_a_window_needs_both_a_day_and_a_time(self):
        with now_is(at(9, 0)):
            self.assertEqual(self.book(pickup_date="2026-11-03").status_code, 400)
            self.assertEqual(self.book(pickup_slot="08-10").status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_windows_that_cannot_be_booked_are_refused_with_a_sentence(self):
        cases = [
            ("2026-11-01", "12-14"),     # yesterday
            ("2026-11-02", "08-10"),     # started an hour ago
            ("2026-11-10", "08-10"),     # more than a week away
        ]
        for day, key in cases:
            with now_is(at(9, 0)):
                resp = self.book(pickup_date=day, pickup_slot=key)
            self.assertEqual(resp.status_code, 400, (day, key))
            self.assertIn("pickup_slot", resp.json(), (day, key))
        with now_is(at(9, 0)):
            self.assertEqual(self.book(pickup_date="2026-11-03", pickup_slot="07-09").status_code, 400)
            self.assertEqual(self.book(pickup_date="not-a-date", pickup_slot="08-10").status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_the_servers_clock_decides_not_the_customers(self):
        # A phone that thinks it's still morning can't book a window the server knows has started.
        with now_is(at(11, 30)):
            resp = self.book(pickup_date="2026-11-02", pickup_slot="12-14")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("too soon", str(resp.json()["pickup_slot"]))

    def test_orders_list_shows_the_window(self):
        with now_is(at(9, 0)):
            self.book(pickup_date="2026-11-04", pickup_slot="16-18")
        row = self.cust.get(ORDERS).json()["results"][0]
        self.assertEqual((row["pickup_date"], row["pickup_slot_label"]), ("2026-11-04", "4:00 – 6:00pm"))
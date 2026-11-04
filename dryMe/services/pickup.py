"""
Pickup windows: when the shop will collect the laundry.

Two-hour windows between 8am and 8pm, in Nairobi time. Kenya has no daylight saving, so Nairobi
time is always UTC+3; a fixed offset means no timezone database is needed (Windows doesn't ship one).

The server is the single source of truth for which windows can be booked: it hides windows that
have started or begin too soon, and it re-checks the choice when the order is created.

Settings (both optional):
    PICKUP_DAYS_AHEAD    how many days after today can be booked (default 6, so a week in all)
    PICKUP_LEAD_MINUTES  the shop needs at least this long before a window opens (default 60)
"""
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone

EAT = dt_timezone(timedelta(hours=3), "EAT")

# key -> (start hour, end hour), 24h clock
_SLOT_HOURS = {
    "08-10": (8, 10),
    "10-12": (10, 12),
    "12-14": (12, 14),
    "14-16": (14, 16),
    "16-18": (16, 18),
    "18-20": (18, 20),
}
SLOT_KEYS = list(_SLOT_HOURS)


class PickupError(ValueError):
    """A pickup choice that can't be booked. The message is written for the customer."""


def _clock(hour):
    return f"{hour % 12 or 12}:00", "am" if hour < 12 else "pm"


def slot_label(key):
    """'08-10' -> '8:00 – 10:00am';  '10-12' -> '10:00am – 12:00pm';  '16-18' -> '4:00 – 6:00pm'."""
    start, end = _SLOT_HOURS[key]
    start_text, start_half = _clock(start)
    end_text, end_half = _clock(end)
    if start_half == end_half:
        return f"{start_text} – {end_text}{end_half}"
    return f"{start_text}{start_half} – {end_text}{end_half}"


SLOT_CHOICES = [(key, slot_label(key)) for key in SLOT_KEYS]


def days_ahead():
    return int(getattr(settings, "PICKUP_DAYS_AHEAD", 6))


def lead_time():
    return timedelta(minutes=int(getattr(settings, "PICKUP_LEAD_MINUTES", 60)))


def now_eat():
    return timezone.now().astimezone(EAT)


def slot_start(day, key):
    return datetime.combine(day, time(_SLOT_HOURS[key][0]), tzinfo=EAT)


def day_label(day, today):
    gap = (day - today).days
    if gap == 0:
        return "Today"
    if gap == 1:
        return "Tomorrow"
    return f"{day:%a} {day.day} {day:%b}"


def check_slot(day, key, now=None):
    """Raise PickupError unless this day + window can still be booked."""
    now = now or now_eat()
    today = now.date()

    if key not in _SLOT_HOURS:
        raise PickupError("Choose one of the pickup time windows.")
    if day < today:
        raise PickupError("That day has already passed. Choose today or a later day.")
    if day > today + timedelta(days=days_ahead()):
        raise PickupError(f"Pickups can be booked up to {days_ahead() + 1} days ahead.")
    if slot_start(day, key) < now + lead_time():
        raise PickupError("That time window is too soon or has already started. Pick a later one.")


def available_days(now=None):
    """
    The bookable days, each with its bookable windows. A day with no windows left (say, after 6pm
    for today) is left out.
    """
    now = now or now_eat()
    today = now.date()
    earliest = now + lead_time()

    days = []
    for offset in range(days_ahead() + 1):
        day = today + timedelta(days=offset)
        slots = [
            {"key": key, "label": slot_label(key)}
            for key in SLOT_KEYS
            if slot_start(day, key) >= earliest
        ]
        if slots:
            days.append({"date": day.isoformat(), "label": day_label(day, today), "slots": slots})
    return days
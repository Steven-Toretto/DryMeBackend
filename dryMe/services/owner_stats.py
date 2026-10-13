"""
Numbers for the owner dashboard overview, computed in the database.

The dashboard used to count the orders it had loaded in the browser, but the
orders API is paginated (10 per page), so every count silently stopped at the
first page. These are real totals over ALL of the owner's orders, archived ones
included: archiving tidies the list, it doesn't un-happen a sale.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from ..models import Order, Shop

WEEK = timedelta(days=7)


def owner_stats(owner, now=None):
    """Two queries total: one conditional aggregate over orders, one shop count."""
    now = now or timezone.now()

    # Derived from the model so a new order status shows up here automatically.
    statuses = [value for value, _label in Order.STATUS_CHOICES]

    aggregates = {
        "total": Count("id"),
        "this_week": Count("id", filter=Q(created_at__gte=now - WEEK)),
        "customers": Count("user", distinct=True),
    }
    for value in statuses:
        aggregates[f"status_{value}"] = Count("id", filter=Q(status=value))

    row = Order.objects.filter(shop__owner=owner).aggregate(**aggregates)

    return {
        "total_orders": row["total"],
        "orders_this_week": row["this_week"],
        "unique_customers": row["customers"],
        "status_counts": {value: row[f"status_{value}"] for value in statuses},
        "shops_count": Shop.objects.filter(owner=owner).count(),
    }
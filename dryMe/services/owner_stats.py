"""
Numbers for the owner dashboard, computed in the database.

The dashboard used to count the orders it had loaded in the browser, but the
orders API is paginated (10 per page), so every count silently stopped at the
first page. These are real totals.

Two views of the same orders:
  * lifetime counts (total / this week / customers / status_counts) include
    archived orders: archiving tidies the list, it doesn't un-happen a sale;
  * "listed" counts are exactly what the Orders tab can show (not archived),
    so its filter chips always agree with the list underneath them.
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
        "archived": Count("id", filter=Q(owner_archived=True)),
    }
    for value in statuses:
        aggregates[f"status_{value}"] = Count("id", filter=Q(status=value))
        aggregates[f"listed_{value}"] = Count("id", filter=Q(status=value, owner_archived=False))

    row = Order.objects.filter(shop__owner=owner).aggregate(**aggregates)

    listed_counts = {value: row[f"listed_{value}"] for value in statuses}

    return {
        "total_orders": row["total"],
        "orders_this_week": row["this_week"],
        "unique_customers": row["customers"],
        "status_counts": {value: row[f"status_{value}"] for value in statuses},
        "listed_counts": listed_counts,
        "listed_total": sum(listed_counts.values()),
        "archived_count": row["archived"],
        "shops_count": Shop.objects.filter(owner=owner).count(),
    }
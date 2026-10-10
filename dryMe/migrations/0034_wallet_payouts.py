from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0033_alter_notification_id_alter_review_id"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── Order: what we actually received + settlement snapshot ──
        migrations.AddField(
            model_name="order",
            name="amount_paid",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="commission_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="owner_earnings",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="settled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ── Wallet ──
        migrations.CreateModel(
            name="Wallet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="wallet", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("balance__gte", 0)), name="wallet_balance_non_negative"),
                ],
            },
        ),

        # ── Payout ──
        migrations.CreateModel(
            name="Payout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("fee", models.DecimalField(decimal_places=2, max_digits=10)),
                ("net_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("method", models.CharField(choices=[("mpesa", "M-Pesa"), ("bank", "Bank")], max_length=10)),
                ("destination", models.CharField(max_length=255)),
                ("status", models.CharField(
                    choices=[
                        ("requested", "Requested"),
                        ("approved", "Approved"),
                        ("paid", "Paid"),
                        ("rejected", "Rejected"),
                        ("failed", "Failed"),
                    ],
                    default="requested",
                    max_length=10,
                )),
                ("reference", models.CharField(blank=True, default="", max_length=100)),
                ("reject_reason", models.TextField(blank=True, default="")),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payouts", to=settings.AUTH_USER_MODEL)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_payouts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-requested_at"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status__in", ["requested", "approved"])),
                        fields=("owner",),
                        name="one_open_payout_per_owner",
                    ),
                    models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="payout_amount_positive"),
                    models.CheckConstraint(condition=models.Q(("net_amount__gt", 0)), name="payout_net_positive"),
                    models.CheckConstraint(
                        condition=models.Q(("net_amount", models.F("amount") - models.F("fee"))),
                        name="payout_net_equals_amount_minus_fee",
                    ),
                ],
            },
        ),

        # ── Ledger ──
        migrations.CreateModel(
            name="WalletTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(
                    choices=[
                        ("sale_credit", "Sale credit"),
                        ("payout_hold", "Payout hold"),
                        ("payout_reversal", "Payout reversal"),
                        ("adjustment", "Adjustment"),
                    ],
                    max_length=20,
                )),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("balance_after", models.DecimalField(decimal_places=2, max_digits=12)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="wallet_transactions", to="dryMe.order")),
                ("payout", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="wallet_transactions", to="dryMe.payout")),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="dryMe.wallet")),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("type", "sale_credit")),
                        fields=("order",),
                        name="uniq_sale_credit_per_order",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("payout__isnull", False)),
                        fields=("payout", "type"),
                        name="uniq_ledger_entry_per_payout_type",
                    ),
                ],
            },
        ),
    ]
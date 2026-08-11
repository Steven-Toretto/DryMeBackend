from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0028_order_pickup_gps"),
    ]

    operations = [

        # Service: price_per_kg -> price (same column, new meaning
        # depends on pricing_type below), plus the new pricing_type field.
        migrations.RenameField(
            model_name="service",
            old_name="price_per_kg",
            new_name="price",
        ),

        migrations.AddField(
            model_name="service",
            name="pricing_type",
            field=models.CharField(
                max_length=10,
                choices=[
                    ("per_kg", "Per Kg"),
                    ("per_item", "Per Item"),
                ],
                default="per_kg",
            ),
        ),

        # Order: weight becomes optional (per-item orders don't use it),
        # quantity added for per-item orders.
        migrations.AlterField(
            model_name="order",
            name="weight",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                blank=True,
                null=True,
            ),
        ),

        migrations.AddField(
            model_name="order",
            name="quantity",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
            ),
        ),
    ]
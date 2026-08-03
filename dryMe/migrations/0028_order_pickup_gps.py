from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0027_order_cancelled_status"),
    ]

    operations = [

        migrations.AddField(
            model_name="order",
            name="pickup_lat",
            field=models.DecimalField(
                max_digits=9,
                decimal_places=6,
                blank=True,
                null=True,
            ),
        ),

        migrations.AddField(
            model_name="order",
            name="pickup_lng",
            field=models.DecimalField(
                max_digits=9,
                decimal_places=6,
                blank=True,
                null=True,
            ),
        ),
    ]
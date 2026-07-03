from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0025_order_customer_notes"),
    ]

    operations = [

        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("washing", "Washing"),
                    ("completed", "Completed"),
                    ("declined", "Declined"),
                ],
                default="pending",
                max_length=20,
            ),
        ),

        migrations.AddField(
            model_name="order",
            name="decline_reason",
            field=models.TextField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name="order",
            name="refund_needed",
            field=models.BooleanField(default=False),
        ),

        migrations.AddField(
            model_name="order",
            name="confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name="order",
            name="declined_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0026_order_confirm_decline_workflow"),
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
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),

        migrations.AddField(
            model_name="order",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0022_email_unique_username_non_unique"),
    ]

    operations = [

        migrations.AddField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("unpaid", "Unpaid"),
                    ("pending_payment", "Pending Payment"),
                    ("paid", "Paid"),
                    ("failed", "Failed"),
                ],
                default="unpaid",
            ),
        ),

        migrations.AddField(
            model_name="order",
            name="mpesa_checkout_request_id",
            field=models.CharField(
                max_length=100,
                blank=True,
                null=True,
            ),
        ),

        migrations.AddField(
            model_name="order",
            name="mpesa_transaction_code",
            field=models.CharField(
                max_length=50,
                blank=True,
                null=True,
            ),
        ),
    ]
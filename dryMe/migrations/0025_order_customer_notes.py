from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0024_order_timeline_timestamps"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="customer_notes",
            field=models.TextField(blank=True, null=True),
        ),
    ]
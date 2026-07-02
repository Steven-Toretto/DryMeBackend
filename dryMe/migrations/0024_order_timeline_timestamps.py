from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0023 order mpesa payment fields"),
    ]

    operations = [

        migrations.AddField(
            model_name="order",
            name="washing_at",
            field=models.DateTimeField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name="order",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
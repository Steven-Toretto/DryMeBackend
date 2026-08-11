from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0030_review"),
    ]

    operations = [

        migrations.AddField(
            model_name="shop",
            name="lat",
            field=models.FloatField(blank=True, null=True),
        ),

        migrations.AddField(
            model_name="shop",
            name="lng",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
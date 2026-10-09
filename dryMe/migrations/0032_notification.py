from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0031_shop_gps"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notif_type", models.CharField(
                    max_length=30,
                    choices=[
                        ("new_order",       "New Order"),
                        ("order_confirmed", "Order Confirmed"),
                        ("order_declined",  "Order Declined"),
                        ("order_cancelled", "Order Cancelled"),
                        ("order_washing",   "Washing Started"),
                        ("order_completed", "Order Completed"),
                    ],
                )),
                ("message", models.TextField()),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("recipient", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="notifications",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("order", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="notifications",
                    to="dryMe.order",
                )),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]


# from django.db import migrations, models
# import django.db.models.deletion


# class Migration(migrations.Migration):

#     dependencies = [
#         ("dryMe", "0031_shop_gps"),
#     ]

#     operations = [

#         migrations.CreateModel(
#             name="Notification",
#             fields=[
#                 ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
#                 ("notif_type", models.CharField(max_length=20, choices=[
#                     ("order_confirmed", "Order Confirmed"),
#                     ("order_washing", "Order Washing"),
#                     ("order_completed", "Order Completed"),
#                     ("order_declined", "Order Declined"),
#                     ("order_cancelled", "Order Cancelled"),
#                     ("new_review", "New Review"),
#                 ])),
#                 ("message", models.CharField(max_length=255)),
#                 ("is_read", models.BooleanField(default=False)),
#                 ("created_at", models.DateTimeField(auto_now_add=True)),
#                 ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="dryMe.order")),
#                 ("review", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="dryMe.review")),
#                 ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="dryMe.user")),
#             ],
#             options={
#                 "ordering": ["-created_at"],
#             },
#         ),
#     ]
from django.db import migrations, models
import uuid


def fill_empty_emails(apps, schema_editor):
    """
    Before adding the unique constraint on email,
    fill any empty email fields with a placeholder
    so the migration doesn't fail on existing data.
    """
    User = apps.get_model("dryMe", "User")
    for user in User.objects.filter(email=""):
        user.email = f"placeholder-{uuid.uuid4().hex[:8]}@dryme.invalid"
        user.save()


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0021_remove_order_payment_status"),
    ]

    operations = [

        # Step 1: Fill empty emails before adding unique constraint
        migrations.RunPython(
            fill_empty_emails,
            reverse_code=migrations.RunPython.noop,
        ),

        # Step 2: Make username non-unique
        migrations.AlterField(
            model_name="user",
            name="username",
            field=models.CharField(max_length=150),
        ),

        # Step 3: Make email unique
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(max_length=254, unique=True),
        ),
    ]
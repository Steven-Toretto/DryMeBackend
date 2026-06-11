from django.db import migrations
import uuid


def fill_empty_emails(apps, schema_editor):
    """
    Fill any empty email fields with a unique placeholder
    so the unique constraint on email doesn't fail.
    """
    User = apps.get_model("dryMe", "User")
    for user in User.objects.filter(email=""):
        user.email = f"placeholder-{uuid.uuid4().hex[:8]}@dryme.invalid"
        user.save()


class Migration(migrations.Migration):

    dependencies = [
        ("dryMe", "0022_alter_user_email_alter_user_username"),
    ]

    operations = [
        migrations.RunPython(
            fill_empty_emails,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
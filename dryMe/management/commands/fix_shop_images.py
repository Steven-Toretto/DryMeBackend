import os
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.conf import settings
from dryMe.models import Shop

class Command(BaseCommand):
    help = "Sanitize existing shop image filenames"

    def handle(self, *args, **kwargs):
        for shop in Shop.objects.exclude(image=""):
            old_path = shop.image.path
            if not os.path.exists(old_path):
                self.stdout.write(self.style.WARNING(f"File not found: {old_path}"))
                continue

            name, ext = os.path.splitext(os.path.basename(old_path))
            safe_name = slugify(name) + ext
            new_rel_path = f"shops/{safe_name}"
            new_abs_path = os.path.join(settings.MEDIA_ROOT, new_rel_path)

            # Move file
            os.makedirs(os.path.dirname(new_abs_path), exist_ok=True)
            os.rename(old_path, new_abs_path)

            # Update model
            shop.image.name = new_rel_path
            shop.save()

            self.stdout.write(self.style.SUCCESS(f"Renamed {old_path} → {new_rel_path}"))

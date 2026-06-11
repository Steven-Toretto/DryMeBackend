from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()

class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        try:
            # Admin passes email via 'username' field
            lookup_email = email or username
            user = User.objects.get(email__iexact=lookup_email)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            return None
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class EmailBackend(ModelBackend):

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        email=None,
        **kwargs
    ):
        User = get_user_model()

        try:
            # Django admin sends the typed value as 'username'
            # Our API sends it as 'email'
            lookup = email or username

            if not lookup:
                return None

            user = User.objects.get(
                email__iexact=lookup
            )

        except User.DoesNotExist:
            return None

        if not user.check_password(password):
            return None

        # ✅ This is the critical check Django admin requires
        if not self.user_can_authenticate(user):
            return None

        return user

    def get_user(self, user_id):
        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
            return user if self.user_can_authenticate(user) else None
        except User.DoesNotExist:
            return None
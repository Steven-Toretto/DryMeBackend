# ========================================================
# 🚨 TEMPORARY SUPERUSER RECOVERY BACKDOOR (DELETE AFTER USE)
# ========================================================
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def create_emergency_admin(request):
    User = get_user_model()
    username = "admin_recovery"
    email = "admin@dryme.com"
    password = "DryMeMasterPassword2026!" # 💡 Change this to whatever password you want!
    
    # Check if this recovery admin already exists to prevent duplication crashes
    if User.objects.filter(username=username).exists():
        return Response({"message": "Recovery user already exists!"}, status=200)
        
    # Create the master profile record database entries cleanly
    admin_user = User(
        username=username,
        email=email,
        password=make_password(password),
        is_superuser=True,
        is_staff=True,
        role="owner", # Gives it shop owner visibility rules too
        phone="0700000000",
        location="Nairobi"
    )
    admin_user.save()
    return Response({"message": "Superuser 'admin_recovery' created successfully!"}, status=201)

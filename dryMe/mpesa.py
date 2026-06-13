import requests
import base64
from datetime import datetime
from requests.auth import HTTPBasicAuth
from django.conf import settings


# ===============================
# 🔑 GET ACCESS TOKEN
# ===============================
def get_access_token():
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

    response = requests.get(
        url,
        auth=HTTPBasicAuth(
            settings.MPESA_CONSUMER_KEY,
            settings.MPESA_CONSUMER_SECRET
        ),
        timeout=30
    )

    data = response.json()
    token = data.get("access_token")

    if not token:
        raise Exception(f"Failed to get access token: {data}")

    return token


# ===============================
# 🔐 GENERATE PASSWORD
# ===============================
def generate_password():
    shortcode = settings.MPESA_SHORTCODE
    passkey = settings.MPESA_PASSKEY
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

    password = base64.b64encode(
        (shortcode + passkey + timestamp).encode()
    ).decode()

    return password, timestamp


# ===============================
# 📲 STK PUSH
# ===============================
def stk_push(phone, amount, order_id):
    access_token = get_access_token()
    password, timestamp = generate_password()

    # Format phone — must be 2547XXXXXXXX
    phone = str(phone).strip()
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("+"):
        phone = phone[1:]

    url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": settings.MPESA_CALLBACK_URL,
        "AccountReference": f"DryMe-{order_id}",
        "TransactionDesc": f"DryMe Laundry Order {order_id}"
    }

    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=30
    )

    return response.json()
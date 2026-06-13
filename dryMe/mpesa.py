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

    print("[MPESA] Fetching access token...")
    print(f"[MPESA] Consumer Key (first 10): {settings.MPESA_CONSUMER_KEY[:10]}")

    response = requests.get(
        url,
        auth=HTTPBasicAuth(
            settings.MPESA_CONSUMER_KEY,
            settings.MPESA_CONSUMER_SECRET
        ),
        timeout=30
    )

    print(f"[MPESA] Token status: {response.status_code}")
    print(f"[MPESA] Token body: {response.text}")

    data = response.json()
    token = data.get("access_token")

    if not token:
        raise Exception(f"No access token: {data}")

    return token


# ===============================
# 🔐 GENERATE PASSWORD
# ===============================
def generate_password():
    shortcode = settings.MPESA_SHORTCODE
    passkey = settings.MPESA_PASSKEY
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

    print(f"[MPESA] Shortcode: {shortcode}")
    print(f"[MPESA] Passkey (first 10): {passkey[:10]}")
    print(f"[MPESA] Timestamp: {timestamp}")

    password = base64.b64encode(
        (shortcode + passkey + timestamp).encode()
    ).decode()

    print(f"[MPESA] Password (first 20): {password[:20]}")

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

    print(f"[MPESA] Phone: {phone}, Amount: {amount}, Order: {order_id}")

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

    print(f"[MPESA] Payload: {payload}")

    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=30
    )

    print(f"[MPESA] STK status: {response.status_code}")
    print(f"[MPESA] STK body: {response.text}")

    return response.json()
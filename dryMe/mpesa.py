import base64
import time
from datetime import datetime

import requests
from django.conf import settings
from requests.auth import HTTPBasicAuth

# Sandbox by default so nothing changes until you opt in. For production set
#   MPESA_BASE_URL=https://api.safaricom.co.ke
# (and use your production consumer key/secret, shortcode and passkey).
DEFAULT_BASE_URL = "https://sandbox.safaricom.co.ke"

# Daraja access tokens live ~3599s. Cache for less so we never send an expired one.
_TOKEN_TTL_SECONDS = 3000
_token_cache = {"value": None, "expires_at": 0.0}


def _url(path):
    base = getattr(settings, "MPESA_BASE_URL", DEFAULT_BASE_URL)
    return f"{base.rstrip('/')}{path}"


# ===============================
# 🔑 GET ACCESS TOKEN
# ===============================
def get_access_token():
    if _token_cache["value"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["value"]

    response = requests.get(
        _url("/oauth/v1/generate?grant_type=client_credentials"),
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

    _token_cache["value"] = token
    _token_cache["expires_at"] = time.time() + _TOKEN_TTL_SECONDS
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
        _url("/mpesa/stkpush/v1/processrequest"),
        json=payload,
        headers=headers,
        timeout=30
    )

    return response.json()


# ===============================
# 🔎 STK QUERY (ask Safaricom what happened to a prompt)
# ===============================
def stk_query(checkout_request_id):
    """
    Returns Safaricom's JSON as-is. Shapes the reconciliation job understands:
      - {"ResultCode": "0", "CheckoutRequestID": ..., ...}   prompt resolved (0 = paid, anything else = not paid)
      - {"errorCode": "500.001.1001", ...}                  still being processed
    Daraja signals "still processing" with an HTTP 500, so we never raise on the
    status code — the caller decides from the body.
    """
    access_token = get_access_token()
    password, timestamp = generate_password()

    response = requests.post(
        _url("/mpesa/stkpushquery/v1/query"),
        json={
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        },
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    try:
        return response.json()
    except ValueError:
        return {
            "errorCode": "non_json_response",
            "errorMessage": response.text[:200],
            "httpStatus": response.status_code,
        }
from rest_framework.throttling import UserRateThrottle


class PayoutRequestThrottle(UserRateThrottle):
    """Withdrawal requests (POST). Counts every attempt, valid or not, per user."""
    scope = "payout_request"
    rate = "10/hour"


class PayoutQuoteThrottle(UserRateThrottle):
    """Live fee preview as the owner types an amount."""
    scope = "payout_quote"
    rate = "60/min"
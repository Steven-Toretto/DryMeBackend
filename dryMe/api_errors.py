def flatten_error_detail(detail):
    """DRF ValidationError.detail (str / list / dict, nested) -> one readable string."""
    if isinstance(detail, (list, tuple)):
        return " ".join(flatten_error_detail(d) for d in detail)
    if isinstance(detail, dict):
        return " ".join(flatten_error_detail(v) for v in detail.values())
    return str(detail)
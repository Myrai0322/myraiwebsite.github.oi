"""
Myrai Labs - Utility Functions
"""
from django.core.cache import cache

from django.conf import settings


def client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() or request.META.get("REMOTE_ADDR", ""))[:45]


def too_many_requests(request, bucket, max_per_hour=None):
    """Returns True when this IP exceeded the hourly cap for the given bucket."""
    limit = max_per_hour
    if limit is None:
        limit = getattr(settings, "QUOTE_MAX_PER_HOUR", 5) if bucket == "quote" else getattr(settings, "CONTACT_MAX_PER_HOUR", 10)
    key = f"rl:{bucket}:{client_ip(request)}"
    count = cache.get(key, 0) + 1
    cache.set(key, count, 3600)
    return count > limit
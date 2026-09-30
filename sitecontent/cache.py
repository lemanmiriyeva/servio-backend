from django.core.cache import cache

CACHE_KEY = "public-site-content"


def invalidate_site_content_cache(sender=None, **kwargs):
    cache.delete(CACHE_KEY)

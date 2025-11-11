"""
Caching utilities for Google API responses.

Two-tier caching strategy:
1. Geocoding cache (LRU, indefinite) - addresses don't change location
2. Places cache (TTL, 1 hour default) - places may change over time
"""

import hashlib
import os
from cachetools import LRUCache, TTLCache
from typing import Any

# Cache configuration
GEOCODING_CACHE_SIZE = int(os.getenv("GEOCODING_CACHE_SIZE", "1000"))
PLACES_CACHE_SIZE = int(os.getenv("PLACES_CACHE_SIZE", "500"))
PLACES_CACHE_TTL = int(os.getenv("PLACES_CACHE_TTL", "3600"))  # 1 hour default

# Initialize caches
geocoding_cache: LRUCache = LRUCache(maxsize=GEOCODING_CACHE_SIZE)
places_cache: TTLCache = TTLCache(maxsize=PLACES_CACHE_SIZE, ttl=PLACES_CACHE_TTL)

# Statistics tracking
cache_stats = {"geocoding_hits": 0, "geocoding_misses": 0, "places_hits": 0, "places_misses": 0}


def make_cache_key(*parts: Any) -> str:
    """
    Create a consistent cache key from arbitrary parts.

    Args:
        *parts: Variable parts to include in the key

    Returns:
        SHA256 hash of the serialized parts
    """
    # Convert all parts to strings and join
    key_string = "|".join(str(part) for part in parts)
    # Hash for consistent length and avoid special characters
    return hashlib.sha256(key_string.encode()).hexdigest()


def get_geocoding_cache(address: str) -> dict | None:
    """
    Get geocoding result from cache.

    Args:
        address: The address to look up

    Returns:
        Cached coordinates dict {lat, lng} or None if not cached
    """
    key = make_cache_key("geocode", address.lower().strip())
    result = geocoding_cache.get(key)
    if result:
        cache_stats["geocoding_hits"] += 1
    else:
        cache_stats["geocoding_misses"] += 1
    return result


def set_geocoding_cache(address: str, coordinates: dict) -> None:
    """
    Store geocoding result in cache.

    Args:
        address: The address that was geocoded
        coordinates: Dict with {lat, lng}
    """
    key = make_cache_key("geocode", address.lower().strip())
    geocoding_cache[key] = coordinates


def get_places_cache(lat: float, lng: float, feature_type: str, radius: int) -> list | None:
    """
    Get nearby places result from cache.

    Args:
        lat: Latitude
        lng: Longitude
        feature_type: Place type (e.g., "park")
        radius: Search radius in meters

    Returns:
        Cached places list or None if not cached
    """
    # Round coordinates to reduce cache misses from tiny differences
    lat_rounded = round(lat, 4)  # ~11 meters precision
    lng_rounded = round(lng, 4)
    key = make_cache_key("places", lat_rounded, lng_rounded, feature_type, radius)

    result = places_cache.get(key)
    if result:
        cache_stats["places_hits"] += 1
    else:
        cache_stats["places_misses"] += 1
    return result


def set_places_cache(lat: float, lng: float, feature_type: str, radius: int, places: list) -> None:
    """
    Store nearby places result in cache.

    Args:
        lat: Latitude
        lng: Longitude
        feature_type: Place type (e.g., "park")
        radius: Search radius in meters
        places: List of place results to cache
    """
    lat_rounded = round(lat, 4)
    lng_rounded = round(lng, 4)
    key = make_cache_key("places", lat_rounded, lng_rounded, feature_type, radius)
    places_cache[key] = places


def get_reverse_geocoding_cache(lat: float, lng: float) -> dict | None:
    """
    Get reverse geocoding result from cache.

    Args:
        lat: Latitude
        lng: Longitude

    Returns:
        Cached address dict or None if not cached
    """
    # Round coordinates to reduce cache misses from tiny differences
    lat_rounded = round(lat, 4)  # ~11 meters precision
    lng_rounded = round(lng, 4)
    key = make_cache_key("reverse_geocode", lat_rounded, lng_rounded)

    result = geocoding_cache.get(key)
    if result:
        cache_stats["geocoding_hits"] += 1
    else:
        cache_stats["geocoding_misses"] += 1
    return result


def set_reverse_geocoding_cache(lat: float, lng: float, address_data: dict) -> None:
    """
    Store reverse geocoding result in cache.

    Args:
        lat: Latitude
        lng: Longitude
        address_data: Dict with address information
    """
    lat_rounded = round(lat, 4)
    lng_rounded = round(lng, 4)
    key = make_cache_key("reverse_geocode", lat_rounded, lng_rounded)
    geocoding_cache[key] = address_data


def get_cache_stats() -> dict:
    """
    Get cache statistics.

    Returns:
        Dict with hit/miss counts and hit rates
    """
    total_geocoding = cache_stats["geocoding_hits"] + cache_stats["geocoding_misses"]
    total_places = cache_stats["places_hits"] + cache_stats["places_misses"]

    return {
        "geocoding": {
            "hits": cache_stats["geocoding_hits"],
            "misses": cache_stats["geocoding_misses"],
            "hit_rate": (
                cache_stats["geocoding_hits"] / total_geocoding if total_geocoding > 0 else 0
            ),
            "cache_size": len(geocoding_cache),
        },
        "places": {
            "hits": cache_stats["places_hits"],
            "misses": cache_stats["places_misses"],
            "hit_rate": cache_stats["places_hits"] / total_places if total_places > 0 else 0,
            "cache_size": len(places_cache),
        },
    }


def clear_caches() -> None:
    """Clear all caches (useful for testing)"""
    geocoding_cache.clear()
    places_cache.clear()
    cache_stats["geocoding_hits"] = 0
    cache_stats["geocoding_misses"] = 0
    cache_stats["places_hits"] = 0
    cache_stats["places_misses"] = 0

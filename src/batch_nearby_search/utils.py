"""
Utility functions for the batch nearby search MCP server.
"""

import math
from typing import Any


def filter_place_fields(place: dict, include_fields: list[str] | None) -> dict:
    """
    Extract only requested fields from Google Places API response.

    Args:
        place: Raw place dict from Google API
        include_fields: List of field names to include, or None for minimal fields only

    Returns:
        Filtered dict with requested fields
    """
    # Always include minimal fields
    result = {
        "name": place.get("name", "Unknown"),
        "place_id": place.get("place_id", ""),
        "distance_meters": place.get("distance_meters"),
    }

    if not include_fields:
        return result

    # Mapping from user-friendly field names to Google API field names
    field_map = {
        "rating": "rating",
        "user_ratings_total": "user_ratings_total",
        "address": "vicinity",  # Use vicinity for nearby search, formatted_address for details
        "phone_number": "formatted_phone_number",
        "website": "website",
        "price_level": "price_level",
        "opening_hours": "opening_hours",
        "types": "types",
    }

    # Add requested optional fields
    for user_field in include_fields:
        api_field = field_map.get(user_field)
        if api_field and api_field in place:
            result[user_field] = place[api_field]

    return result


def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate distance between two coordinates using Haversine formula.

    Args:
        lat1: Latitude of point 1
        lng1: Longitude of point 1
        lat2: Latitude of point 2
        lng2: Longitude of point 2

    Returns:
        Distance in meters
    """
    # Earth's radius in meters
    R = 6371000

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    # Haversine formula
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(
        delta_lng / 2
    ) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return R * c


def format_distance(meters: float) -> str:
    """
    Format distance in human-readable format.

    Args:
        meters: Distance in meters

    Returns:
        Formatted string (e.g., "1.2 km" or "350 m")
    """
    if meters >= 1000:
        return f"{meters / 1000:.1f} km"
    return f"{int(meters)} m"


def format_duration(seconds: int) -> str:
    """
    Format duration in human-readable format.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string (e.g., "1h 23m" or "45m")
    """
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    elif seconds >= 60:
        minutes = seconds // 60
        return f"{minutes}m"
    return f"{seconds}s"


def validate_coordinates(lat: float, lng: float) -> bool:
    """
    Validate that coordinates are in valid ranges.

    Args:
        lat: Latitude
        lng: Longitude

    Returns:
        True if valid, False otherwise
    """
    return -90 <= lat <= 90 and -180 <= lng <= 180


def normalize_place_type(place_type: str) -> str:
    """
    Normalize place type to lowercase and replace spaces with underscores.

    Args:
        place_type: Raw place type string

    Returns:
        Normalized place type
    """
    return place_type.lower().strip().replace(" ", "_")

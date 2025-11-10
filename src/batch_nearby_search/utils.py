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


def format_batch_search_results(results: list[dict], summary: dict) -> str:
    """
    Format batch search results in human-readable text.

    Args:
        results: List of location results
        summary: Summary statistics

    Returns:
        Human-readable summary string
    """
    lines = []

    # Header with summary
    total = summary.get("total_locations", 0)
    successful = summary.get("successful", 0)
    partial = summary.get("partial", 0)
    failed = summary.get("failed", 0)
    total_places = summary.get("total_places_found", 0)

    if failed == 0:
        lines.append(f"Found {total_places} places across {total} location(s)")
    else:
        lines.append(
            f"Found {total_places} places across {successful + partial}/{total} location(s) "
            f"({failed} failed)"
        )
    lines.append("")

    # Per-location breakdown
    for result in results:
        loc_idx = result.get("location_index", "?")
        location = result.get("location", {})
        coords = result.get("coordinates", {})
        features = result.get("features", {})
        status = result.get("status", "unknown")

        # Location header
        if location.get("address"):
            loc_str = f"Location {loc_idx + 1}: {location['address']}"
        else:
            loc_str = f"Location {loc_idx + 1}: ({coords.get('lat', '?')}, {coords.get('lng', '?')})"

        # Count places by feature type
        feature_counts = []
        for feature_type, places in features.items():
            count = len(places) if isinstance(places, list) else 0
            if count > 0:
                feature_counts.append(f"{count} {feature_type.replace('_', ' ')}")

        if feature_counts:
            lines.append(f"  {loc_str}: {', '.join(feature_counts)}")
        else:
            lines.append(f"  {loc_str}: No places found")

        # Add errors if any
        if "errors" in result and result["errors"]:
            for error in result["errors"]:
                lines.append(f"    ⚠ {error}")

    return "\n".join(lines)


def format_nearby_search_results(
    location: dict, features: dict, summary: dict
) -> str:
    """
    Format nearby search results in human-readable text.

    Args:
        location: Location coordinates
        features: Dictionary of feature types and places
        summary: Summary statistics

    Returns:
        Human-readable summary string
    """
    lines = []

    total_types = summary.get("total_feature_types", 0)
    total_places = summary.get("total_places_found", 0)
    radius = summary.get("radius_meters", 0)

    # Header
    lines.append(
        f"Found {total_places} places of {total_types} type(s) "
        f"within {format_distance(radius)}"
    )
    lines.append("")

    # Per-feature breakdown
    for feature_type, data in features.items():
        if isinstance(data, dict) and "places" in data:
            places = data["places"]
            if places:
                lines.append(f"{feature_type.replace('_', ' ').title()} ({len(places)}):")
                for place in places[:3]:  # Show up to 3 places
                    name = place.get("name", "Unknown")
                    dist = place.get("distance_meters")
                    rating = place.get("rating")

                    place_str = f"  • {name}"
                    if dist:
                        place_str += f" - {format_distance(dist)}"
                    if rating:
                        place_str += f" ⭐ {rating}"

                    lines.append(place_str)

                if len(places) > 3:
                    lines.append(f"  ... and {len(places) - 3} more")
        elif isinstance(data, dict) and "error" in data:
            lines.append(f"{feature_type.replace('_', ' ').title()}: ⚠ {data['error']}")

    return "\n".join(lines)


def format_distance_matrix_results(results: list[dict], summary: dict) -> str:
    """
    Format distance matrix results in human-readable text.

    Args:
        results: List of origin-destination pairs
        summary: Summary statistics

    Returns:
        Human-readable summary string
    """
    lines = []

    mode = summary.get("mode", "driving")
    lines.append(f"Distance Matrix Results (mode: {mode})")
    lines.append("")

    for result in results:
        origin = result.get("origin", "Unknown")
        destination = result.get("destination", "Unknown")
        distance = result.get("distance_meters")
        duration = result.get("duration_seconds")
        status = result.get("status", "UNKNOWN")

        if status == "OK" and distance and duration:
            lines.append(
                f"• {origin} → {destination}: "
                f"{format_distance(distance)} ({format_duration(duration)})"
            )
        else:
            lines.append(f"• {origin} → {destination}: ⚠ {status}")

    return "\n".join(lines)

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
    Format batch search results in log-style output.

    Each line shows: location, coordinates, place name, distance, and optional fields.

    Args:
        results: List of location results
        summary: Summary statistics

    Returns:
        Log-style output with each place on a separate line
    """
    lines = []

    # Iterate through each location
    for result in results:
        location = result.get("location", {})
        coords = result.get("coordinates", {})
        features = result.get("features", {})

        # Format location identifier
        if location.get("address"):
            loc_str = location["address"]
        else:
            loc_str = f"{location.get('lat', coords.get('lat', '?'))}, {location.get('lng', coords.get('lng', '?'))}"

        # Format coordinates
        lat = coords.get("lat", location.get("lat", "?"))
        lng = coords.get("lng", location.get("lng", "?"))
        coord_str = f"({lat}, {lng})"

        # Iterate through each feature type and place
        for feature_type, places in features.items():
            if isinstance(places, list):
                for place in places:
                    name = place.get("name", "Unknown")
                    distance = place.get("distance_meters")

                    # Build the log line: - <location> <coords> "<name>" <distance> meters
                    line_parts = ["-", loc_str, coord_str, f'"{name}"']

                    if distance is not None:
                        line_parts.append(f"{int(distance)} meters")

                    # Add optional fields if present
                    if "rating" in place and place["rating"]:
                        line_parts.append(f"[rating: {place['rating']:.1f}]")
                    if "address" in place and place["address"]:
                        line_parts.append(f"[addr: {place['address']}]")
                    if "phone_number" in place and place["phone_number"]:
                        line_parts.append(f"[tel: {place['phone_number']}]")

                    lines.append(" ".join(line_parts))

        # Add errors if any
        if "errors" in result and result["errors"]:
            for error in result["errors"]:
                lines.append(f"- {loc_str} {coord_str} ERROR: {error}")

    return "\n".join(lines) if lines else "No places found"


def format_nearby_search_results(
    location: dict, features: dict, summary: dict
) -> str:
    """
    Format nearby search results in log-style output.

    Each line shows: coordinates, place name, distance, and optional fields.

    Args:
        location: Location coordinates
        features: Dictionary of feature types and places
        summary: Summary statistics

    Returns:
        Log-style output with each place on a separate line
    """
    lines = []

    # Format coordinates
    lat = location.get("lat", "?")
    lng = location.get("lng", "?")
    coord_str = f"({lat}, {lng})"

    # Iterate through each feature type and place
    for feature_type, data in features.items():
        if isinstance(data, dict) and "places" in data:
            places = data["places"]
            for place in places:
                name = place.get("name", "Unknown")
                distance = place.get("distance_meters")

                # Build the log line: - <coords> "<name>" <distance> meters
                line_parts = ["-", coord_str, f'"{name}"']

                if distance is not None:
                    line_parts.append(f"{int(distance)} meters")

                # Add optional fields if present
                if "rating" in place and place["rating"]:
                    line_parts.append(f"[rating: {place['rating']:.1f}]")
                if "address" in place and place["address"]:
                    line_parts.append(f"[addr: {place['address']}]")
                if "phone_number" in place and place["phone_number"]:
                    line_parts.append(f"[tel: {place['phone_number']}]")

                lines.append(" ".join(line_parts))
        elif isinstance(data, dict) and "error" in data:
            lines.append(f"- {coord_str} ERROR: {data['error']}")

    return "\n".join(lines) if lines else "No places found"


def format_distance_matrix_results(results: list[dict], summary: dict) -> str:
    """
    Format distance matrix results in log-style output.

    Each line shows: origin -> destination, distance, duration.

    Args:
        results: List of origin-destination pairs
        summary: Summary statistics

    Returns:
        Log-style output with each route on a separate line
    """
    lines = []

    for result in results:
        origin = result.get("origin", "Unknown")
        destination = result.get("destination", "Unknown")
        distance = result.get("distance_meters")
        duration = result.get("duration_seconds")
        status = result.get("status", "UNKNOWN")

        if status == "OK" and distance and duration:
            lines.append(
                f"- {origin} -> {destination} "
                f"{format_distance(distance)} "
                f"{format_duration(duration)}"
            )
        else:
            lines.append(f"- {origin} -> {destination} ERROR: {status}")

    return "\n".join(lines) if lines else "No routes found"


def format_geocode_results(results: list[dict], summary: dict) -> str:
    """
    Format geocoding results in log-style output.

    Each line shows: address -> (lat, lng)

    Args:
        results: List of geocoding results
        summary: Summary statistics

    Returns:
        Log-style output with each geocoded address on a separate line
    """
    lines = []

    for result in results:
        address = result.get("address", "Unknown")
        status = result.get("status", "success")

        if status == "success":
            formatted_address = result.get("formatted_address", "")
            lat = result.get("lat")
            lng = result.get("lng")

            # Format: - "Original Address" -> "Formatted Address" (lat, lng)
            if formatted_address and lat is not None and lng is not None:
                lines.append(f'- "{address}" -> "{formatted_address}" ({lat:.4f}, {lng:.4f})')
            else:
                lines.append(f'- "{address}" ERROR: Missing coordinates')
        else:
            error = result.get("error", "Unknown error")
            lines.append(f'- "{address}" ERROR: {error}')

    return "\n".join(lines) if lines else "No addresses geocoded"


def format_reverse_geocode_results(results: list[dict], summary: dict) -> str:
    """
    Format reverse geocoding results in log-style output.

    Each line shows: (lat, lng) -> address

    Args:
        results: List of reverse geocoding results
        summary: Summary statistics

    Returns:
        Log-style output with each reverse geocoded location on a separate line
    """
    lines = []

    for result in results:
        lat = result.get("lat")
        lng = result.get("lng")
        status = result.get("status", "success")

        coord_str = f"({lat:.4f}, {lng:.4f})" if lat is not None and lng is not None else "(?, ?)"

        if status == "success":
            formatted_address = result.get("formatted_address", "Unknown")
            lines.append(f'- {coord_str} -> "{formatted_address}"')
        else:
            error = result.get("error", "Unknown error")
            lines.append(f"- {coord_str} ERROR: {error}")

    return "\n".join(lines) if lines else "No locations reverse geocoded"

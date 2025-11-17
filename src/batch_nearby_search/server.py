"""
Batch Nearby Search MCP Server

FastMCP server providing optimized batch nearby searches using Google Places API.

Tools:
- distance_matrix: Calculate distances between multiple origin-destination pairs
- nearby_search: Find nearby places from a single location
- batch_nearby_search: Find nearby places from multiple locations in parallel (optimized)
- list_place_types: Discover valid Google Place types by category
- geocode: Convert addresses to coordinates (forward geocoding)
- reverse_geocode: Convert coordinates to addresses (reverse geocoding)
- optimize_route: Find optimized route between multiple locations
"""

import asyncio
import json
import os
from typing import Literal
from dotenv import load_dotenv
from fastmcp import FastMCP

from .models import (
    Location,
    PlaceResult,
    DistanceMatrixResult,
    LocationSearchResult,
    BatchSearchSummary,
    AVAILABLE_FIELDS,
)
from .google_client import GooglePlacesClient
from .cache import get_cache_stats
from .utils import (
    parse_string_or_array,
    filter_place_fields,
    format_batch_search_results,
    format_nearby_search_results,
    format_distance_matrix_results,
    format_geocode_results,
    format_reverse_geocode_results,
)
from .place_types import (
    PLACE_TYPES_BY_CATEGORY,
    ALL_PLACE_TYPES,
    validate_place_types,
    get_category_for_type,
)

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("batch-nearby-search")

# Initialize Google API client (will be created on first use)
_google_client: GooglePlacesClient | None = None


def get_google_client() -> GooglePlacesClient:
    """Get or create the Google API client singleton"""
    global _google_client
    if _google_client is None:
        max_concurrent = int(os.getenv("MAX_CONCURRENT_REQUESTS", "10"))
        _google_client = GooglePlacesClient(max_concurrent=max_concurrent)
    return _google_client


@mcp.tool
async def distance_matrix(
    origins: list[str],
    destinations: list[str],
    mode: Literal["driving", "walking", "bicycling", "transit"] = "driving",
    format: Literal["text", "json"] | None = None,
) -> str | dict:
    """
    Calculate distances and travel times between multiple origin-destination pairs.

    Uses Google Distance Matrix API for fixed locations. Useful for comparing
    commute times or distances to known destinations.

    Args:
        origins: List of origin addresses (e.g., ["123 Main St, City, State"])
        destinations: List of destination addresses
        mode: Travel mode - driving, walking, bicycling, or transit
        format: Output format - "text" for human-readable (default), "json" for structured data

    Returns:
        Human-readable log format (default) or JSON structured data

    Example:
        distance_matrix(
            origins=["1600 Amphitheatre Parkway, Mountain View, CA"],
            destinations=["1 Apple Park Way, Cupertino, CA"],
            mode="driving"
        )
    """
    client = get_google_client()

    try:
        # Call Distance Matrix API
        result = await client.distance_matrix(origins, destinations, mode)

        # Parse and structure the results
        parsed_results = []

        for i, row in enumerate(result["rows"]):
            origin = origins[i] if i < len(origins) else "Unknown"

            for j, element in enumerate(row["elements"]):
                destination = destinations[j] if j < len(destinations) else "Unknown"

                distance_meters = None
                duration_seconds = None

                if element["status"] == "OK":
                    distance_meters = element["distance"]["value"]
                    duration_seconds = element["duration"]["value"]

                parsed_results.append(
                    {
                        "origin": origin,
                        "destination": destination,
                        "distance_meters": distance_meters,
                        "duration_seconds": duration_seconds,
                        "status": element["status"],
                    }
                )

        structured_data = {
            "results": parsed_results,
            "summary": {
                "total_pairs": len(parsed_results),
                "mode": mode,
                "api_calls": 1,
            },
        }

        # Return based on format
        if format == "json":
            return structured_data
        else:
            # Text mode (default): return human-readable log format
            return format_distance_matrix_results(
                parsed_results, structured_data["summary"]
            )

    except Exception as e:
        error_data = {"error": str(e), "results": []}

        if format == "json":
            return error_data
        else:
            return f"Error: {str(e)}"


@mcp.tool
async def nearby_search(
    location: Location,
    feature_types: list[str] | str,
    radius_meters: int = 5000,
    max_results_per_type: int = 3,
    include_fields: list[str] | None = None,
    format: Literal["text", "json"] | None = None,
) -> str | dict:
    """
    Find nearby places of multiple types from a single location.

    Searches for multiple feature types (e.g., park, gym, grocery store) from one location
    in parallel. Results are cached to reduce API costs for repeated queries.

    Args:
        location: Search origin - provide either address OR coordinates
        feature_types: Place type(s) to search for. Can be a single string or list of strings.
                      Also accepts category names (e.g., "food_drink", "sports") to search all types in that category.
        radius_meters: Search radius in meters (100-50000, default 5000)
        max_results_per_type: Maximum results per feature type (1-10, default 3)
        include_fields: Optional fields to include (rating, address, phone_number, etc.)
        format: Output format - "text" for human-readable (default), "json" for structured data

    Returns:
        Human-readable log format (default) or JSON structured data

    Example:
        nearby_search(
            location={"address": "123 Main St, City, State"},
            feature_types=["park", "cafe", "gym"],
            include_fields=["rating", "address"]
        )

    Available include_fields:
        rating, user_ratings_total, address, phone_number, website, price_level,
        opening_hours, types

    Note:
        Use list_place_types() to discover valid place types before searching.
        Invalid types will return helpful suggestions for corrections.
    """
    client = get_google_client()

    try:
        # Handle single string input or JSON-stringified array
        feature_types = parse_string_or_array(feature_types)
        if not feature_types:
            feature_types = []

        # Parse include_fields if it's a stringified array
        include_fields = parse_string_or_array(include_fields)

        # Validate place types and collect warnings
        validation = validate_place_types(feature_types)
        warnings = []

        if not validation["all_valid"]:
            # Build helpful warning messages for each invalid type
            invalid_msgs = []
            for invalid_type in validation["invalid"]:
                suggestions = validation["suggestions"].get(invalid_type, [])
                if suggestions:
                    suggestion_str = ", ".join(suggestions[:3])
                    invalid_msgs.append(
                        f"  - '{invalid_type}' is not valid. Did you mean: {suggestion_str}?"
                    )
                else:
                    invalid_msgs.append(
                        f"  - '{invalid_type}' is not valid. Use list_place_types() to see all options."
                    )

            # Create a comprehensive validation summary
            valid_types = validation["valid"]
            if valid_types:
                warnings.append(
                    f"Validation: {len(valid_types)} of {len(feature_types)} place types are valid. "
                    f"Proceeding with: {', '.join(valid_types)}\n"
                    f"Invalid types:\n" + "\n".join(invalid_msgs)
                )
            else:
                warnings.append(
                    f"Validation: None of the {len(feature_types)} place types are valid.\n"
                    f"Invalid types:\n" + "\n".join(invalid_msgs)
                )
        else:
            valid_types = validation["valid"]

        if not valid_types:
            error_msg = "Error: No valid place types provided"
            if warnings:
                error_msg += "\n\n" + "\n".join(warnings)

            if format == "json":
                return {
                    "error": "No valid place types provided",
                    "warnings": warnings,
                    "features": {},
                }
            else:
                return error_msg

        # Geocode if address provided
        if location.address:
            coords = await client.geocode_location(location.address)
            lat, lng = coords["lat"], coords["lng"]
        else:
            lat, lng = location.lat, location.lng

        # Search for each feature type in parallel
        tasks = []
        for feature_type in valid_types:
            task = client.nearby_search(lat, lng, feature_type, radius_meters, max_results_per_type)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Organize results by feature type
        features_dict = {}
        total_places = 0

        for feature_type, result in zip(valid_types, results):
            if isinstance(result, Exception):
                features_dict[feature_type] = {"error": str(result), "places": []}
            else:
                # Filter fields based on include_fields parameter
                filtered_places = [filter_place_fields(place, include_fields) for place in result]
                features_dict[feature_type] = {"places": filtered_places}
                total_places += len(filtered_places)

        structured_data = {
            "location": {"lat": lat, "lng": lng},
            "features": features_dict,
            "summary": {
                "total_feature_types": len(valid_types),
                "total_places_found": total_places,
                "radius_meters": radius_meters,
            },
        }

        # Add warnings if there were invalid types
        if warnings:
            structured_data["warnings"] = warnings

        # Return based on format
        if format == "json":
            return structured_data
        else:
            # Text mode (default): return human-readable log format
            text_output = format_nearby_search_results(
                structured_data["location"], features_dict, structured_data["summary"]
            )

            # Add warnings to text if present
            if warnings:
                text_output = "\n".join(warnings) + "\n\n" + text_output

            return text_output

    except Exception as e:
        if format == "json":
            return {"error": str(e), "features": {}}
        else:
            return f"Error: {str(e)}"


@mcp.tool
async def batch_nearby_search(
    locations: list[Location],
    feature_types: list[str] | str,
    radius_meters: int = 5000,
    max_results_per_type: int = 3,
    include_fields: list[str] | None = None,
    format: Literal["text", "json"] | None = None,
) -> str | dict:
    """
    Find nearby places for MULTIPLE locations in parallel - OPTIMIZED for batch operations.

    Searches for multiple feature types across multiple locations concurrently, making
    all API calls in parallel. Results are organized by location, then by feature type.

    Args:
        locations: List of search origins (max 20) - provide address OR coordinates
                  Mix of addresses and coordinates is supported
        feature_types: Place type(s) to search for. Can be a single string or list of strings.
                      Also accepts category names (e.g., "food_drink", "sports") to search all types in that category.
        radius_meters: Search radius in meters (100-50000, default 5000)
        max_results_per_type: Maximum results per feature type (1-10, default 3)
        include_fields: Optional fields to include (rating, address, phone_number, etc.)
        format: Output format - "text" for human-readable (default), "json" for structured data

    Returns:
        Results organized by location, then feature type. Each location has:
        - location_index: Index in the original locations list
        - coordinates: Resolved {lat, lng}
        - features: Dict mapping feature_type -> list of places
        - status: "success", "partial", or "error"

        Summary includes total locations, successful/partial/failed counts, and total places found.

    Example:
        batch_nearby_search(
            locations=[
                {"address": "1600 Amphitheatre Parkway, Mountain View, CA"},
                {"address": "1 Apple Park Way, Cupertino, CA"},
                {"lat": 37.4849, "lng": -122.1477}
            ],
            feature_types=["park", "grocery_store"],
            radius_meters=2000,
            include_fields=["rating", "address"],
            format="json"
        )

        Returns structure:
        {
          "results": [
            {
              "location_index": 0,
              "coordinates": {"lat": 37.4220, "lng": -122.0841},
              "features": {
                "park": [
                  {"name": "Charleston Park", "distance_meters": 450, "rating": 4.5, ...}
                ],
                "grocery_store": [
                  {"name": "Whole Foods", "distance_meters": 1200, "rating": 4.2, ...}
                ]
              },
              "status": "success"
            },
            ... (more locations)
          ],
          "summary": {
            "total_locations": 3,
            "successful": 3,
            "partial": 0,
            "failed": 0,
            "total_places_found": 15
          }
        }

    Available include_fields:
        rating, user_ratings_total, address, phone_number, website, price_level,
        opening_hours, types

    Important limits:
        - Max 20 locations per request (enforced by validation)
        - Max 10 feature types per request (enforced by validation)
        - Total API calls = num_locations × num_feature_types
        - Example: 10 locations × 5 types = 50 parallel API calls

    Note:
        Use list_place_types() to discover valid place types before searching.
        Invalid types will return helpful suggestions for corrections.
        Partial failures are supported - if one feature type fails at a location,
        other feature types will still return results.
    """
    client = get_google_client()

    # Handle single string input or JSON-stringified array
    feature_types = parse_string_or_array(feature_types)
    if not feature_types:
        feature_types = []

    # Parse include_fields if it's a stringified array
    include_fields = parse_string_or_array(include_fields)

    # Parse locations if it's a stringified array (for Location objects)
    locations = parse_string_or_array(locations)
    if not locations:
        locations = []

    # Convert dict locations to Location objects
    locations = [
        Location(**loc) if isinstance(loc, dict) else loc
        for loc in locations
    ]

    # Validate place types and collect warnings
    validation = validate_place_types(feature_types)
    warnings = []

    if not validation["all_valid"]:
        # Build helpful warning messages for each invalid type
        invalid_msgs = []
        for invalid_type in validation["invalid"]:
            suggestions = validation["suggestions"].get(invalid_type, [])
            if suggestions:
                suggestion_str = ", ".join(suggestions[:3])
                invalid_msgs.append(
                    f"  - '{invalid_type}' is not valid. Did you mean: {suggestion_str}?"
                )
            else:
                invalid_msgs.append(
                    f"  - '{invalid_type}' is not valid. Use list_place_types() to see all options."
                )

        # Create a comprehensive validation summary
        valid_types = validation["valid"]
        if valid_types:
            warnings.append(
                f"Validation: {len(valid_types)} of {len(feature_types)} place types are valid. "
                f"Proceeding with: {', '.join(valid_types)}\n"
                f"Invalid types:\n" + "\n".join(invalid_msgs)
            )
        else:
            warnings.append(
                f"Validation: None of the {len(feature_types)} place types are valid.\n"
                f"Invalid types:\n" + "\n".join(invalid_msgs)
            )
    else:
        valid_types = validation["valid"]

    if not valid_types:
        error_msg = "Error: No valid place types provided"
        if warnings:
            error_msg += "\n\n" + "\n".join(warnings)

        if format == "json":
            return {
                "error": "No valid place types provided",
                "warnings": warnings,
                "results": [],
                "summary": {
                    "total_locations": len(locations),
                    "successful": 0,
                    "partial": 0,
                    "failed": len(locations),
                    "total_places_found": 0,
                },
            }
        else:
            return error_msg

    location_results = []
    total_places_found = 0
    successful = 0
    failed = 0
    partial = 0

    try:
        # Step 1: Geocode all addresses in parallel
        geocode_tasks = []
        for location in locations:
            if location.address:
                geocode_tasks.append(client.geocode_location(location.address))
            else:
                # Already have coordinates
                geocode_tasks.append(
                    asyncio.sleep(0, result={"lat": location.lat, "lng": location.lng})
                )

        geocoded = await asyncio.gather(*geocode_tasks, return_exceptions=True)

        # Step 2: Build coordinate list
        coords_list = []
        for i, result in enumerate(geocoded):
            if isinstance(result, Exception):
                coords_list.append({"error": str(result)})
            else:
                coords_list.append(result)

        # Step 3: Batch nearby search for all locations × feature types
        batch_results = await client.batch_nearby_search(
            [c for c in coords_list if "error" not in c],
            valid_types,
            radius_meters,
            max_results_per_type,
        )

        # Step 4: Organize results by location
        location_map = {}
        for batch_result in batch_results:
            loc_idx = batch_result["location_index"]
            if loc_idx not in location_map:
                location_map[loc_idx] = {
                    "location_index": loc_idx,
                    "location": locations[loc_idx].model_dump(),
                    "coordinates": batch_result["location"],
                    "features": {},
                    "errors": [],
                }

            feature_type = batch_result["feature_type"]
            if batch_result["error"]:
                location_map[loc_idx]["errors"].append(
                    f"{feature_type}: {batch_result['error']}"
                )
            else:
                # Filter fields based on include_fields parameter
                filtered_places = [
                    filter_place_fields(place, include_fields) for place in batch_result["places"]
                ]
                location_map[loc_idx]["features"][feature_type] = filtered_places
                total_places_found += len(filtered_places)

        # Step 5: Determine status for each location
        for loc_idx, loc_data in location_map.items():
            has_results = len(loc_data["features"]) > 0
            has_errors = len(loc_data["errors"]) > 0

            if has_results and not has_errors:
                loc_data["status"] = "success"
                successful += 1
            elif has_results and has_errors:
                loc_data["status"] = "partial"
                partial += 1
            else:
                loc_data["status"] = "error"
                failed += 1

            # Clean up errors field if empty
            if not has_errors:
                loc_data.pop("errors")

            location_results.append(loc_data)

        # Build structured response
        structured_data = {
            "results": location_results,
            "summary": {
                "total_locations": len(locations),
                "successful": successful,
                "partial": partial,
                "failed": failed,
                "total_places_found": total_places_found,
            },
        }

        # Add warnings if there were invalid types
        if warnings:
            structured_data["warnings"] = warnings

        # Return based on format
        if format == "json":
            return structured_data
        else:
            # Text mode (default): return human-readable log format
            text_output = format_batch_search_results(
                location_results, structured_data["summary"]
            )

            # Add warnings to text if present
            if warnings:
                text_output = "\n".join(warnings) + "\n\n" + text_output

            return text_output

    except Exception as e:
        error_data = {
            "error": str(e),
            "results": location_results,
            "summary": {
                "total_locations": len(locations),
                "successful": successful,
                "partial": partial,
                "failed": failed,
                "total_places_found": total_places_found,
            },
        }

        # Add warnings even in error case
        if warnings:
            error_data["warnings"] = warnings

        # Return based on format
        if format == "json":
            return error_data
        else:
            error_text = f"Error: {str(e)}"
            if warnings:
                error_text = "\n".join(warnings) + "\n\n" + error_text
            return error_text


@mcp.tool
async def list_place_types(categories: list[str] | str | None = None) -> dict:
    """
    Get all valid Google Place types, optionally filtered by category.

    Use this tool to discover valid place types before making search requests.
    This helps avoid typos and ensures you're using the correct type names.

    Args:
        categories: Optional category or list of categories to filter by. Can be a single string or list of strings.
                   Available categories:
            - automotive (car dealers, gas stations, parking, etc.)
            - business (corporate offices, farms, ranches)
            - culture (museums, galleries, monuments, etc.)
            - education (schools, libraries, universities)
            - entertainment_recreation (parks, theaters, zoos, etc.)
            - facilities (public baths, stables, etc.)
            - finance (banks, ATMs, accounting)
            - food_drink (restaurants, cafes, bars, etc.)
            - government (city hall, police, post office, etc.)
            - health_wellness (hospitals, pharmacies, doctors, etc.)
            - lodging (hotels, hostels, campgrounds, etc.)
            - places_of_worship (churches, temples, mosques, etc.)
            - services (salons, lawyers, florists, etc.)
            - shopping (stores, malls, supermarkets, etc.)
            - sports (gyms, stadiums, golf courses, etc.)
            - transportation (airports, train stations, bus stops, etc.)

    Returns:
        Dictionary of place types by category, or all types if no category specified

    Example:
        list_place_types(categories="food_drink")
        # Returns: {"food_drink": ["restaurant", "cafe", "bar", ...]}

        list_place_types(categories=["food_drink", "sports"])
        # Returns: {"food_drink": [...], "sports": [...]}

        list_place_types()
        # Returns: {"automotive": [...], "business": [...], ...}
    """
    if categories:
        # Handle single string input or JSON-stringified array
        categories = parse_string_or_array(categories)

        # Normalize category names
        categories = [cat.lower().strip() for cat in categories]

        result = {}
        errors = []

        for category in categories:
            if category in PLACE_TYPES_BY_CATEGORY:
                result[category] = PLACE_TYPES_BY_CATEGORY[category]
            else:
                errors.append(category)

        if errors:
            # Provide helpful error with available categories
            available = list(PLACE_TYPES_BY_CATEGORY.keys())
            return {
                "error": f"Unknown categories: {', '.join(errors)}",
                "available_categories": available,
                "valid_results": result if result else None,
            }
        else:
            return {
                "categories": result,
                "total_types": sum(len(types) for types in result.values()),
            }
    else:
        # Return all types organized by category
        return {
            "categories": PLACE_TYPES_BY_CATEGORY,
            "total_categories": len(PLACE_TYPES_BY_CATEGORY),
            "total_types": len(ALL_PLACE_TYPES),
        }


@mcp.tool
async def geocode(
    addresses: list[str] | str,
    include_components: bool = False,
    format: Literal["text", "json"] | None = None,
) -> str | dict:
    """
    Convert addresses to coordinates (forward geocoding).

    Useful for looking up coordinates for addresses you want to use in nearby searches
    or distance calculations. Supports batch geocoding of multiple addresses in parallel.
    Results are cached to reduce API costs for repeated queries.

    Args:
        addresses: Single address string or list of addresses to geocode
        include_components: Include detailed address components (street, city, state, etc.)
        format: Output format - "text" for human-readable (default), "json" for structured data

    Returns:
        Human-readable log format (default) or JSON structured data

    Example:
        geocode(addresses="1600 Amphitheatre Parkway, Mountain View, CA")
        # Returns: - "1600 Amphitheatre..." -> "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA" (37.4220, -122.0841)

        geocode(addresses=["Times Square, NYC", "Golden Gate Bridge, SF"])
        # Batch geocodes both addresses in parallel
    """
    client = get_google_client()

    # Handle single string input or JSON-stringified array
    addresses = parse_string_or_array(addresses)
    if not addresses:
        addresses = []

    results = []
    total_success = 0
    total_failed = 0

    try:
        # Geocode all addresses in parallel
        geocode_tasks = []
        for address in addresses:
            geocode_tasks.append(client.geocode_location(address))

        geocoded = await asyncio.gather(*geocode_tasks, return_exceptions=True)

        # Process results
        for i, result in enumerate(geocoded):
            original_address = addresses[i]

            if isinstance(result, Exception):
                results.append({
                    "address": original_address,
                    "status": "error",
                    "error": str(result),
                })
                total_failed += 1
            else:
                result_dict = {
                    "address": original_address,
                    "formatted_address": result["formatted_address"],
                    "lat": result["lat"],
                    "lng": result["lng"],
                    "status": "success",
                }

                if include_components:
                    # Fetch full details if components requested (not in cached response)
                    result_dict["place_id"] = result.get("place_id")

                results.append(result_dict)
                total_success += 1

        # Build structured response
        structured_data = {
            "results": results,
            "summary": {
                "total_addresses": len(addresses),
                "successful": total_success,
                "failed": total_failed,
            },
        }

        # Return based on format
        if format == "json":
            return structured_data
        else:
            # Text mode (default): return human-readable log format
            return format_geocode_results(results, structured_data["summary"])

    except Exception as e:
        error_data = {
            "error": str(e),
            "results": results,
            "summary": {
                "total_addresses": len(addresses),
                "successful": total_success,
                "failed": total_failed,
            },
        }

        if format == "json":
            return error_data
        else:
            return f"Error: {str(e)}"


@mcp.tool
async def reverse_geocode(
    coordinates: list[dict] | dict,
    include_components: bool = False,
    format: Literal["text", "json"] | None = None,
) -> str | dict:
    """
    Convert coordinates to addresses (reverse geocoding).

    Useful for finding addresses for coordinates from GPS, maps, or other sources.
    Supports batch reverse geocoding. Results are cached to reduce API costs.

    Args:
        coordinates: Single coordinate dict or list of dicts with {lat, lng}
        include_components: Include detailed address components (street, city, state, etc.)
        format: Output format - "text" for human-readable (default), "json" for structured data

    Returns:
        Human-readable log format (default) or JSON structured data

    Example:
        reverse_geocode(coordinates={"lat": 37.4220, "lng": -122.0841})
        # Returns: - (37.4220, -122.0841) -> "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA"

        reverse_geocode(coordinates=[
            {"lat": 37.4220, "lng": -122.0841},
            {"lat": 40.7580, "lng": -73.9855}
        ])
        # Batch reverse geocodes both locations in parallel
    """
    client = get_google_client()

    # Handle single dict input or JSON-stringified array
    coordinates = parse_string_or_array(coordinates)
    if not coordinates:
        coordinates = []

    results = []
    total_success = 0
    total_failed = 0

    try:
        # Validate and reverse geocode all coordinates in parallel
        reverse_geocode_tasks = []
        valid_coords = []

        for coord in coordinates:
            lat = coord.get("lat")
            lng = coord.get("lng")

            if lat is None or lng is None:
                results.append({
                    "lat": lat,
                    "lng": lng,
                    "status": "error",
                    "error": "Missing lat or lng",
                })
                total_failed += 1
            elif not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                results.append({
                    "lat": lat,
                    "lng": lng,
                    "status": "error",
                    "error": "Invalid coordinates (lat must be -90 to 90, lng must be -180 to 180)",
                })
                total_failed += 1
            else:
                reverse_geocode_tasks.append(client.reverse_geocode_location(lat, lng))
                valid_coords.append(coord)

        # Execute all valid reverse geocoding tasks
        if reverse_geocode_tasks:
            geocoded = await asyncio.gather(*reverse_geocode_tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(geocoded):
                original_coord = valid_coords[i]
                lat = original_coord["lat"]
                lng = original_coord["lng"]

                if isinstance(result, Exception):
                    results.append({
                        "lat": lat,
                        "lng": lng,
                        "status": "error",
                        "error": str(result),
                    })
                    total_failed += 1
                else:
                    result_dict = {
                        "lat": lat,
                        "lng": lng,
                        "formatted_address": result["formatted_address"],
                        "status": "success",
                    }

                    if include_components:
                        result_dict["place_id"] = result.get("place_id")
                        result_dict["address_components"] = result.get("address_components")

                    results.append(result_dict)
                    total_success += 1

        # Build structured response
        structured_data = {
            "results": results,
            "summary": {
                "total_coordinates": len(coordinates),
                "successful": total_success,
                "failed": total_failed,
            },
        }

        # Return based on format
        if format == "json":
            return structured_data
        else:
            # Text mode (default): return human-readable log format
            return format_reverse_geocode_results(results, structured_data["summary"])

    except Exception as e:
        error_data = {
            "error": str(e),
            "results": results,
            "summary": {
                "total_coordinates": len(coordinates),
                "successful": total_success,
                "failed": total_failed,
            },
        }

        if format == "json":
            return error_data
        else:
            return f"Error: {str(e)}"


@mcp.tool
async def optimize_route(
    origin: Location,
    destination: Location,
    waypoints: list[Location],
    travel_mode: Literal["DRIVE", "BICYCLE", "WALK", "TWO_WHEELER"] = "DRIVE",
    optimize_order: bool = True,
    format: Literal["text", "json"] | None = None,
) -> str | dict:
    """
    Find an optimized route between multiple locations.

    Calculates the best route from origin to destination through multiple waypoints,
    optionally optimizing the order of waypoints for minimum travel time and distance.
    Uses Google Routes API with advanced route optimization.

    Args:
        origin: Starting location (address or coordinates)
        destination: Ending location (address or coordinates)
        waypoints: List of intermediate stops (1-25 waypoints)
        travel_mode: Travel mode - DRIVE (default), BICYCLE, WALK, or TWO_WHEELER
        optimize_order: Optimize waypoint order for efficiency (default True)
        format: Output format - "text" for human-readable (default), "json" for structured data

    Returns:
        Optimized route with waypoint order, total distance, duration, and encoded polyline

    Example:
        optimize_route(
            origin={"address": "San Francisco, CA"},
            destination={"address": "Los Angeles, CA"},
            waypoints=[
                {"address": "Palo Alto, CA"},
                {"address": "San Jose, CA"},
                {"address": "Santa Barbara, CA"}
            ],
            travel_mode="DRIVE",
            optimize_order=True
        )

        Returns:
        {
          "origin": {"lat": 37.7749, "lng": -122.4194},
          "destination": {"lat": 34.0522, "lng": -118.2437},
          "waypoints": [
            {"original_index": 0, "optimized_index": 0, "lat": 37.4419, "lng": -122.1430, "address": "Palo Alto, CA"},
            {"original_index": 1, "optimized_index": 1, "lat": 37.3382, "lng": -121.8863, "address": "San Jose, CA"},
            {"original_index": 2, "optimized_index": 2, "lat": 34.4208, "lng": -119.6982, "address": "Santa Barbara, CA"}
          ],
          "optimized_waypoint_order": [0, 1, 2],
          "total_distance_meters": 550000,
          "total_duration_seconds": 19800,
          "travel_mode": "DRIVE",
          "optimized": true
        }

    Important limits:
        - Minimum 1 waypoint, maximum 25 waypoints
        - Waypoint optimization uses Routes API Compute Routes Pro SKU (higher cost)
        - Returns encoded polyline for route visualization

    Notes:
        - Waypoint optimization considers travel time, distance, and number of turns
        - Cannot use TRAFFIC_AWARE_OPTIMAL routing preference with optimization
        - All waypoints must be stopovers (not pass-through via points)
        - The optimized_waypoint_order shows the reordered indices of original waypoints
    """
    client = get_google_client()

    # Parse waypoints if it's a stringified array
    waypoints = parse_string_or_array(waypoints)
    if not waypoints:
        error_msg = "Error: At least 1 waypoint required"
        if format == "json":
            return {"error": error_msg}
        else:
            return error_msg

    # Convert dict waypoints to Location objects
    waypoints = [
        Location(**wp) if isinstance(wp, dict) else wp
        for wp in waypoints
    ]

    try:
        # Geocode origin
        if origin.address:
            origin_coords = await client.geocode_location(origin.address)
            origin_lat, origin_lng = origin_coords["lat"], origin_coords["lng"]
            origin_formatted = origin_coords["formatted_address"]
        else:
            origin_lat, origin_lng = origin.lat, origin.lng
            origin_formatted = f"({origin_lat}, {origin_lng})"

        # Geocode destination
        if destination.address:
            dest_coords = await client.geocode_location(destination.address)
            dest_lat, dest_lng = dest_coords["lat"], dest_coords["lng"]
            dest_formatted = dest_coords["formatted_address"]
        else:
            dest_lat, dest_lng = destination.lat, destination.lng
            dest_formatted = f"({dest_lat}, {dest_lng})"

        # Geocode all waypoints in parallel
        waypoint_tasks = []
        for waypoint in waypoints:
            if waypoint.address:
                waypoint_tasks.append(client.geocode_location(waypoint.address))
            else:
                waypoint_tasks.append(
                    asyncio.sleep(0, result={"lat": waypoint.lat, "lng": waypoint.lng, "formatted_address": f"({waypoint.lat}, {waypoint.lng})"})
                )

        waypoint_results = await asyncio.gather(*waypoint_tasks, return_exceptions=True)

        # Build waypoint coordinate list
        waypoint_coords = []
        waypoint_details = []
        for i, result in enumerate(waypoint_results):
            if isinstance(result, Exception):
                error_msg = f"Error geocoding waypoint {i}: {str(result)}"
                if format == "json":
                    return {"error": error_msg}
                else:
                    return error_msg

            waypoint_coords.append({"lat": result["lat"], "lng": result["lng"]})
            waypoint_details.append({
                "original_index": i,
                "lat": result["lat"],
                "lng": result["lng"],
                "address": result.get("formatted_address", f"({result['lat']}, {result['lng']})")
            })

        # Call route optimization API
        route_result = await client.optimize_route(
            origin={"lat": origin_lat, "lng": origin_lng},
            destination={"lat": dest_lat, "lng": dest_lng},
            waypoints=waypoint_coords,
            travel_mode=travel_mode,
            optimize_order=optimize_order
        )

        # Update waypoint details with optimized indices
        if route_result["optimized_waypoint_order"]:
            optimized_order = route_result["optimized_waypoint_order"]
            for i, original_idx in enumerate(optimized_order):
                waypoint_details[original_idx]["optimized_index"] = i
        else:
            # No optimization, indices remain the same
            for i, detail in enumerate(waypoint_details):
                detail["optimized_index"] = i

        # Build structured response
        structured_data = {
            "origin": {
                "lat": origin_lat,
                "lng": origin_lng,
                "address": origin_formatted
            },
            "destination": {
                "lat": dest_lat,
                "lng": dest_lng,
                "address": dest_formatted
            },
            "waypoints": waypoint_details,
            "optimized_waypoint_order": route_result["optimized_waypoint_order"],
            "total_distance_meters": route_result["total_distance_meters"],
            "total_duration_seconds": route_result["total_duration_seconds"],
            "polyline": route_result["polyline"],
            "travel_mode": route_result["travel_mode"],
            "optimized": route_result["optimized"]
        }

        # Return based on format
        if format == "json":
            return structured_data
        else:
            # Text mode (default): return human-readable format
            output_lines = []
            output_lines.append("=== OPTIMIZED ROUTE ===\n")
            output_lines.append(f"Origin: {origin_formatted}")
            output_lines.append(f"Destination: {dest_formatted}")
            output_lines.append(f"Travel Mode: {travel_mode}")
            output_lines.append(f"Optimization: {'Enabled' if optimize_order else 'Disabled'}\n")

            # Display waypoints in optimized order
            if route_result["optimized_waypoint_order"]:
                output_lines.append("Waypoints (optimized order):")
                for optimized_idx in range(len(waypoint_details)):
                    # Find waypoint with this optimized_index
                    for detail in waypoint_details:
                        if detail["optimized_index"] == optimized_idx:
                            output_lines.append(
                                f"  {optimized_idx + 1}. {detail['address']} "
                                f"(originally #{detail['original_index'] + 1})"
                            )
                            break
            else:
                output_lines.append("Waypoints (original order):")
                for i, detail in enumerate(waypoint_details):
                    output_lines.append(f"  {i + 1}. {detail['address']}")

            # Display summary
            distance_km = route_result["total_distance_meters"] / 1000
            duration_hours = route_result["total_duration_seconds"] / 3600
            duration_minutes = (route_result["total_duration_seconds"] % 3600) / 60

            output_lines.append(f"\nTotal Distance: {distance_km:.2f} km ({route_result['total_distance_meters']} meters)")
            output_lines.append(f"Total Duration: {int(duration_hours)}h {int(duration_minutes)}m ({route_result['total_duration_seconds']} seconds)")

            if route_result["polyline"]:
                output_lines.append(f"\nEncoded Polyline: {route_result['polyline'][:50]}...")

            return "\n".join(output_lines)

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        if format == "json":
            return {"error": str(e)}
        else:
            return error_msg


def main():
    """Entry point for the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()

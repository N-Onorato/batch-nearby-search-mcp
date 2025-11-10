"""
Batch Nearby Search MCP Server

FastMCP server providing optimized batch nearby searches using Google Places API.

Tools:
- distance_matrix: Calculate distances between multiple origin-destination pairs
- nearby_search: Find nearby places from a single location
- batch_nearby_search: Find nearby places from multiple locations in parallel (optimized)
- list_place_types: Discover valid Google Place types by category
"""

import asyncio
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
    filter_place_fields,
    format_batch_search_results,
    format_nearby_search_results,
    format_distance_matrix_results,
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
    response_format: Literal["concise", "detailed"] = "concise",
) -> dict:
    """
    Calculate distances and travel times between multiple origin-destination pairs.

    Uses Google Distance Matrix API for fixed locations. Useful for comparing
    commute times or distances to known destinations.

    Args:
        origins: List of origin addresses (e.g., ["123 Main St, City, State"])
        destinations: List of destination addresses
        mode: Travel mode - driving, walking, bicycling, or transit
        response_format: "concise" for human-readable summary (default), "detailed" for full structured data

    Returns:
        Human-readable summary (concise mode) or full structured data (detailed mode)

    Example:
        distance_matrix(
            origins=["1600 Amphitheatre Parkway, Mountain View, CA"],
            destinations=["1 Apple Park Way, Cupertino, CA"],
            mode="driving",
            response_format="concise"
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

        # Return based on response_format
        if response_format == "detailed":
            return structured_data
        else:
            # Concise mode: return human-readable text + structured data
            text_summary = format_distance_matrix_results(
                parsed_results, structured_data["summary"]
            )

            return {
                "text": text_summary,
                "data": structured_data,
            }

    except Exception as e:
        error_data = {"error": str(e), "results": []}

        if response_format == "detailed":
            return error_data
        else:
            error_text = f"Error: {str(e)}"
            return {"text": error_text, "data": error_data}


@mcp.tool
async def nearby_search(
    location: Location,
    feature_types: list[str],
    radius_meters: int = 5000,
    max_results_per_type: int = 3,
    include_fields: list[str] | None = None,
    response_format: Literal["concise", "detailed"] = "concise",
) -> dict:
    """
    Find nearby places of multiple types from a single location.

    Searches for multiple feature types (e.g., park, gym, grocery store) from one location
    in parallel. Results are cached to reduce API costs for repeated queries.

    Args:
        location: Search origin - provide either address OR coordinates
        feature_types: List of place types (e.g., ["park", "gym", "grocery_store"])
        radius_meters: Search radius in meters (100-50000, default 5000)
        max_results_per_type: Maximum results per feature type (1-10, default 3)
        include_fields: Optional fields to include (rating, address, phone_number, etc.)
        response_format: "concise" for human-readable summary (default), "detailed" for full structured data

    Returns:
        Human-readable summary (concise mode) or full structured data (detailed mode)

    Example:
        nearby_search(
            location={"address": "123 Main St, City, State"},
            feature_types=["park", "cafe", "gym"],
            include_fields=["rating", "address"],
            response_format="concise"
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
        # Validate place types and collect warnings
        validation = validate_place_types(feature_types)
        warnings = []

        if not validation["all_valid"]:
            # Build helpful warning messages
            for invalid_type in validation["invalid"]:
                suggestions = validation["suggestions"].get(invalid_type, [])
                if suggestions:
                    suggestion_str = ", ".join(suggestions[:3])
                    warnings.append(
                        f"'{invalid_type}' is not a valid place type. Did you mean: {suggestion_str}?"
                    )
                else:
                    warnings.append(
                        f"'{invalid_type}' is not a valid place type. Use list_place_types() to see valid options."
                    )

        # Use only valid types for the search
        valid_types = validation["valid"]

        if not valid_types:
            error_data = {
                "error": "No valid place types provided",
                "warnings": warnings,
                "features": {},
            }

            if response_format == "detailed":
                return error_data
            else:
                error_text = "Error: No valid place types provided\n\n" + "\n".join(warnings)
                return {"text": error_text, "data": error_data}

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

        # Return based on response_format
        if response_format == "detailed":
            return structured_data
        else:
            # Concise mode: return human-readable text + structured data
            text_summary = format_nearby_search_results(
                structured_data["location"], features_dict, structured_data["summary"]
            )

            # Add warnings to text if present
            if warnings:
                text_summary = "\n".join(warnings) + "\n\n" + text_summary

            return {
                "text": text_summary,
                "data": structured_data,
            }

    except Exception as e:
        error_data = {"error": str(e), "features": {}}

        if response_format == "detailed":
            return error_data
        else:
            error_text = f"Error: {str(e)}"
            return {"text": error_text, "data": error_data}


@mcp.tool
async def batch_nearby_search(
    locations: list[Location],
    feature_types: list[str],
    radius_meters: int = 5000,
    max_results_per_type: int = 3,
    include_fields: list[str] | None = None,
    response_format: Literal["concise", "detailed"] = "concise",
) -> dict:
    """
    Find nearby places for MULTIPLE locations in parallel - OPTIMIZED for batch operations.

    It searches for multiple feature types across multiple locations concurrently.

    Args:
        locations: List of search origins (max 20) - provide address OR coordinates
        feature_types: List of place types (max 10, e.g., ["park", "gym", "grocery_store"])
        radius_meters: Search radius in meters (100-50000, default 5000)
        max_results_per_type: Maximum results per feature type (1-10, default 3)
        include_fields: Optional fields to include (rating, address, phone_number, etc.)
        response_format: "concise" for human-readable summary (default), "detailed" for full structured data

    Returns:
        Human-readable summary (concise mode) or full structured data (detailed mode)

    Example:
        batch_nearby_search(
            locations=[
                {"address": "123 Main St, City, State"},
                {"address": "456 Oak Ave, City, State"},
                {"lat": 37.4220, "lng": -122.0841}
            ],
            feature_types=["park", "grocery_store", "gym"],
            include_fields=["rating", "address", "distance_meters"],
            response_format="concise"
        )

    Available include_fields:
        rating, user_ratings_total, address, phone_number, website, price_level,
        opening_hours, types

    Note:
        Use list_place_types() to discover valid place types before searching.
        Invalid types will return helpful suggestions for corrections.
    """
    client = get_google_client()

    # Validate place types and collect warnings
    validation = validate_place_types(feature_types)
    warnings = []

    if not validation["all_valid"]:
        # Build helpful warning messages
        for invalid_type in validation["invalid"]:
            suggestions = validation["suggestions"].get(invalid_type, [])
            if suggestions:
                suggestion_str = ", ".join(suggestions[:3])
                warnings.append(
                    f"'{invalid_type}' is not a valid place type. Did you mean: {suggestion_str}?"
                )
            else:
                warnings.append(
                    f"'{invalid_type}' is not a valid place type. Use list_place_types() to see valid options."
                )

    # Use only valid types for the search
    valid_types = validation["valid"]

    if not valid_types:
        error_data = {
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

        if response_format == "detailed":
            return error_data
        else:
            error_text = "Error: No valid place types provided\n\n" + "\n".join(warnings)
            return {"text": error_text, "data": error_data}

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

        # Return based on response_format
        if response_format == "detailed":
            return structured_data
        else:
            # Concise mode: return human-readable text + structured data
            text_summary = format_batch_search_results(
                location_results, structured_data["summary"]
            )

            # Add warnings to text if present
            if warnings:
                text_summary = "\n".join(warnings) + "\n\n" + text_summary

            return {
                "text": text_summary,
                "data": structured_data,
            }

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

        # Return based on response_format
        if response_format == "detailed":
            return error_data
        else:
            error_text = f"Error: {str(e)}"
            if warnings:
                error_text = "\n".join(warnings) + "\n\n" + error_text
            return {"text": error_text, "data": error_data}


@mcp.tool
async def list_place_types(category: str | None = None) -> dict:
    """
    Get all valid Google Place types, optionally filtered by category.

    Use this tool to discover valid place types before making search requests.
    This helps avoid typos and ensures you're using the correct type names.

    Args:
        category: Optional category to filter by. Available categories:
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
        list_place_types(category="food_drink")
        # Returns: {"food_drink": ["restaurant", "cafe", "bar", ...]}

        list_place_types()
        # Returns: {"automotive": [...], "business": [...], ...}
    """
    if category:
        # Normalize category name
        category = category.lower().strip()

        if category in PLACE_TYPES_BY_CATEGORY:
            return {
                "category": category,
                "types": PLACE_TYPES_BY_CATEGORY[category],
                "count": len(PLACE_TYPES_BY_CATEGORY[category]),
            }
        else:
            # Provide helpful error with available categories
            available = list(PLACE_TYPES_BY_CATEGORY.keys())
            return {
                "error": f"Unknown category '{category}'",
                "available_categories": available,
            }
    else:
        # Return all types organized by category
        return {
            "categories": PLACE_TYPES_BY_CATEGORY,
            "total_categories": len(PLACE_TYPES_BY_CATEGORY),
            "total_types": len(ALL_PLACE_TYPES),
        }


def main():
    """Entry point for the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()

"""
Batch Nearby Search MCP Server

FastMCP server providing optimized batch nearby searches using Google Places API.

Tools (use get_tool_docs(tool_name) for detailed documentation):
- batch_nearby_search: Find nearby places from multiple locations in parallel (optimized)
- nearby_search: Find nearby places from a single location
- distance_matrix: Calculate distances between origin-destination pairs
- list_place_types: Discover valid Google Place types by category
- geocode: Convert addresses to coordinates (forward geocoding)
- reverse_geocode: Convert coordinates to addresses (reverse geocoding)
- get_tool_docs: Get detailed on-demand documentation for any tool
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
from .tool_docs import get_tool_documentation, list_available_tools

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
    """Calculate distances and travel times between origin-destination pairs. Takes origins (addresses), destinations (addresses), mode (driving/walking/bicycling/transit). Use get_tool_docs('distance_matrix') for details."""
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
    """Find nearby places from a SINGLE location. Takes location (address or coords), feature_types, radius_meters (100-50k). Simpler than batch version. Use get_tool_docs('nearby_search') for details."""
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
    """Find nearby places for MULTIPLE locations in parallel (optimized batch operation). Takes locations (max 20, addresses or coords), feature_types, radius_meters (100-50k). Results organized by location then type. Use get_tool_docs('batch_nearby_search') for details."""
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
    """Get valid Google Place types by category. Use before searching to discover valid types and avoid typos. Categories: automotive, food_drink, sports, etc. Use get_tool_docs('list_place_types') for all categories."""
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
    """Convert addresses to coordinates (forward geocoding). Takes addresses (single or list), returns lat/lng. Supports batch processing. Results cached. Use get_tool_docs('geocode') for details."""
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
    """Convert coordinates to addresses (reverse geocoding). Takes coordinates {lat, lng} (single or list), returns addresses. Supports batch processing. Results cached. Use get_tool_docs('reverse_geocode') for details."""
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
async def get_tool_docs(
    tool_name: str,
    detail_level: Literal["usage", "examples", "full"] = "usage",
) -> str:
    """
    Get detailed documentation for a specific tool on-demand.

    Reduces context bloat by loading full docs only when needed. Use this to get
    comprehensive parameter descriptions, examples, and usage patterns for any tool.

    Args:
        tool_name: Name of the tool (e.g., "batch_nearby_search", "geocode")
        detail_level: Level of detail - "usage" (parameters & return), "examples" (code samples), or "full" (everything)

    Returns:
        Formatted documentation at the requested detail level
    """
    return get_tool_documentation(tool_name, detail_level)


def main():
    """Entry point for the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()

"""
Tool Documentation - Full documentation for MCP tools.

This module stores comprehensive documentation for all tools to reduce context bloat.
Tool definitions in server.py use minimal descriptions; detailed docs are fetched on-demand.
"""

TOOL_DOCS = {
    "batch_nearby_search": {
        "name": "batch_nearby_search",
        "summary": "Find nearby places for MULTIPLE locations in parallel - optimized for batch operations",
        "usage": """
Usage: batch_nearby_search(locations, feature_types, radius_meters=5000, max_results_per_type=3, include_fields=None, format=None)

Parameters:
  locations: list[Location]
    - List of search origins (max 20)
    - Provide either address OR coordinates
    - Mix of addresses and coordinates is supported
    - Example: [{"address": "123 Main St"}, {"lat": 37.42, "lng": -122.08}]

  feature_types: list[str] | str
    - Place type(s) to search for
    - Can be single string or list of strings
    - Also accepts category names (e.g., "food_drink", "sports")
    - Example: ["park", "grocery_store"] or "park"

  radius_meters: int (default: 5000)
    - Search radius in meters
    - Range: 100-50000

  max_results_per_type: int (default: 3)
    - Maximum results per feature type
    - Range: 1-10

  include_fields: list[str] | None (default: None)
    - Optional fields to include in results
    - Available: rating, user_ratings_total, address, phone_number, website,
                 price_level, opening_hours, types
    - Default includes only: name, distance_meters, place_id

  format: "text" | "json" | None (default: None)
    - Output format
    - "text": Human-readable log format
    - "json": Structured data
    - None: Defaults to "text"

Returns:
  Results organized by location, then feature type.

  Structure (JSON format):
  {
    "results": [
      {
        "location_index": 0,
        "coordinates": {"lat": 37.4220, "lng": -122.0841},
        "features": {
          "park": [{"name": "...", "distance_meters": 450, ...}],
          "grocery_store": [...]
        },
        "status": "success" | "partial" | "error"
      }
    ],
    "summary": {
      "total_locations": 3,
      "successful": 3,
      "partial": 0,
      "failed": 0,
      "total_places_found": 15
    }
  }

Important Limits:
  - Max 20 locations per request
  - Max 10 feature types per request
  - Total API calls = num_locations × num_feature_types
  - Example: 10 locations × 5 types = 50 parallel API calls
""",
        "examples": """
Example 1: Basic batch search
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

Example 2: Using category instead of individual types
  batch_nearby_search(
      locations=[{"address": "Times Square, NYC"}],
      feature_types="food_drink",  # Expands to all food/drink types
      radius_meters=1000
  )

Example 3: Multiple locations, minimal results
  batch_nearby_search(
      locations=[
          {"lat": 37.7749, "lng": -122.4194},
          {"lat": 40.7580, "lng": -73.9855}
      ],
      feature_types=["cafe", "gym"],
      max_results_per_type=1,
      format="text"
  )

Access Pattern for Results:
  result["results"][location_idx]["features"][feature_type][place_idx]

Common Mistakes:
  ❌ WRONG: result["results"]["park"][0]  # Not grouped by type first
  ✅ CORRECT: result["results"][0]["features"]["park"][0]  # Location first!

  ❌ WRONG: Assuming all types have results
  ✅ CORRECT: Check if type exists: features.get("park", [])
""",
        "full": """
BATCH NEARBY SEARCH - Complete Documentation

PURPOSE:
  Find nearby places of multiple types across multiple locations in parallel.
  Optimized for batch operations with concurrent API calls and intelligent caching.
  Achieves 50-80% cost reduction vs sequential searches.

PARAMETERS:
  locations: list[Location] (required)
    - Maximum: 20 locations
    - Each location needs either:
      * address: str (e.g., "123 Main St, City, State")
      * OR lat + lng: float, float (e.g., lat=37.42, lng=-122.08)
    - Geocoding happens in parallel for all addresses
    - Mix addresses and coordinates freely

  feature_types: list[str] | str (required)
    - Place types to search for at each location
    - Maximum: 10 types
    - Can be individual types: ["park", "cafe", "gym"]
    - Can be category names: "food_drink" (expands to all types in category)
    - Mix categories and types: ["food_drink", "park"]
    - Use list_place_types() to discover valid types
    - Invalid types are filtered out with helpful suggestions

  radius_meters: int (default: 5000)
    - Search radius around each location
    - Minimum: 100 meters
    - Maximum: 50000 meters (50km)
    - Applied uniformly to all locations

  max_results_per_type: int (default: 3)
    - Limit results per feature type per location
    - Minimum: 1
    - Maximum: 10
    - Results are sorted by distance (nearest first)

  include_fields: list[str] | None (default: None)
    - Additional fields to include in results
    - Default fields (always included): name, place_id, distance_meters
    - Available optional fields:
      * rating: float (1.0-5.0)
      * user_ratings_total: int
      * address: str (vicinity address)
      * phone_number: str
      * website: str (URL)
      * price_level: int (0-4, where 0=free, 4=very expensive)
      * opening_hours: dict (current status + weekly hours)
      * types: list[str] (all types this place matches)
    - More fields = more API quota used

  format: "text" | "json" | None (default: None)
    - Controls output format
    - "text": Human-readable log-style output, great for conversation
    - "json": Structured data, easy to parse programmatically
    - None: Defaults to "text"

RETURN VALUE:
  Text format:
    Log-style output with location headers and place listings
    Example:
      Location 0: 1600 Amphitheatre Parkway... (37.4220, -122.0841)

      park (2 results):
        - Charleston Park: 450m [rating: 4.5]
        - Shoreline Park: 890m [rating: 4.2]

      grocery_store (1 result):
        - Whole Foods Market: 1200m [rating: 4.3]

  JSON format:
    {
      "results": [
        {
          "location_index": 0,
          "location": {"address": "..."} | {"lat": ..., "lng": ...},
          "coordinates": {"lat": 37.4220, "lng": -122.0841},
          "features": {
            "park": [
              {
                "name": "Charleston Park",
                "place_id": "ChIJ...",
                "distance_meters": 450,
                "rating": 4.5,  // if include_fields contains "rating"
                "address": "..."  // if include_fields contains "address"
              }
            ],
            "grocery_store": [...]
          },
          "status": "success" | "partial" | "error",
          "errors": ["..."]  // Only present if status is "partial" or "error"
        }
      ],
      "summary": {
        "total_locations": 3,
        "successful": 3,  // All feature types succeeded
        "partial": 0,     // Some feature types failed
        "failed": 0,      // All feature types failed
        "total_places_found": 15
      },
      "warnings": ["..."]  // Only present if invalid types were provided
    }

STATUS MEANINGS:
  - "success": All feature types returned results or empty arrays (no errors)
  - "partial": Some feature types succeeded, others failed (check "errors" field)
  - "error": All feature types failed or geocoding failed

PERFORMANCE & COSTS:
  API Call Calculation:
    total_calls = num_locations × num_valid_feature_types

  Examples:
    - 5 locations × 3 types = 15 API calls (~$0.48 at $0.032/call)
    - 10 locations × 5 types = 50 API calls (~$1.60)
    - 20 locations × 10 types = 200 API calls (~$6.40)

  Recommendation: Keep total calls under 50 for responsive performance

  Caching: Results cached for 1 hour, geocoding cached indefinitely

  Parallelization: All API calls execute concurrently (max 10 at a time)

VALIDATION & ERROR HANDLING:
  - Invalid place types are filtered out automatically
  - Warnings show which types were invalid + suggestions
  - Search proceeds with valid types only
  - Each location can succeed/fail independently
  - Partial failures are tracked per location

EXAMPLES:
  See "examples" section for detailed code examples.

TIPS:
  - Use list_place_types() first to discover valid types
  - Start with small batches (5 locations × 3 types) to test
  - Use format="json" for programmatic processing
  - Check status field to handle partial failures
  - Results within each type are sorted by distance (nearest first)
  - Access pattern: results[loc_idx]["features"][type][place_idx]

SEE ALSO:
  - nearby_search: For single location searches
  - list_place_types: To discover valid place types
  - geocode: To get coordinates for addresses beforehand
"""
    },

    "nearby_search": {
        "name": "nearby_search",
        "summary": "Find nearby places of multiple types from a single location",
        "usage": """
Usage: nearby_search(location, feature_types, radius_meters=5000, max_results_per_type=3, include_fields=None, format=None)

Parameters:
  location: Location
    - Single search origin
    - Provide either address OR coordinates
    - Example: {"address": "123 Main St"} or {"lat": 37.42, "lng": -122.08}

  feature_types: list[str] | str
    - Place type(s) to search for
    - Can be single string or list
    - Example: ["park", "cafe"] or "park"

  radius_meters: int (default: 5000)
    - Search radius in meters (100-50000)

  max_results_per_type: int (default: 3)
    - Maximum results per type (1-10)

  include_fields: list[str] | None
    - Optional fields: rating, address, phone_number, etc.

  format: "text" | "json" | None
    - Output format (default: "text")

Returns:
  Places organized by feature type with location coordinates.
""",
        "examples": """
Example 1: Basic search
  nearby_search(
      location={"address": "123 Main St, City, State"},
      feature_types=["park", "cafe", "gym"],
      include_fields=["rating", "address"]
  )

Example 2: Coordinate-based search
  nearby_search(
      location={"lat": 37.4220, "lng": -122.0841},
      feature_types="restaurant",
      radius_meters=1000,
      max_results_per_type=5
  )
""",
        "full": """
NEARBY SEARCH - Complete Documentation

PURPOSE:
  Find nearby places of multiple types from a single location.
  Simpler than batch_nearby_search for single-location queries.

For complete parameter descriptions, see batch_nearby_search documentation.
This tool has the same parameters except it takes a single location instead of a list.

DIFFERENCES FROM BATCH_NEARBY_SEARCH:
  - Takes single location instead of list
  - No location_index in results
  - Simpler result structure (no array of locations)
  - Use this when you only have one location to search from

RETURN VALUE (JSON format):
  {
    "location": {"lat": 37.4220, "lng": -122.0841},
    "features": {
      "park": [{"name": "...", "distance_meters": 450, ...}],
      "cafe": [...]
    },
    "summary": {
      "total_feature_types": 3,
      "total_places_found": 8,
      "radius_meters": 5000
    },
    "warnings": ["..."]  // Only if invalid types provided
  }

See batch_nearby_search for full parameter documentation.
"""
    },

    "distance_matrix": {
        "name": "distance_matrix",
        "summary": "Calculate distances and travel times between multiple origin-destination pairs",
        "usage": """
Usage: distance_matrix(origins, destinations, mode="driving", format=None)

Parameters:
  origins: list[str]
    - List of origin addresses
    - Example: ["123 Main St, City, State"]

  destinations: list[str]
    - List of destination addresses
    - Example: ["456 Oak Ave, City, State"]

  mode: "driving" | "walking" | "bicycling" | "transit" (default: "driving")
    - Travel mode for distance calculation

  format: "text" | "json" | None
    - Output format (default: "text")

Returns:
  Distance and duration for each origin-destination pair.
  Total pairs = len(origins) × len(destinations)
""",
        "examples": """
Example 1: Commute time from home to multiple offices
  distance_matrix(
      origins=["123 Home St, City, State"],
      destinations=[
          "456 Office Ave, City, State",
          "789 Branch Rd, Other City, State"
      ],
      mode="driving"
  )

Example 2: Walking distance between landmarks
  distance_matrix(
      origins=["Times Square, NYC"],
      destinations=["Central Park, NYC", "Brooklyn Bridge, NYC"],
      mode="walking",
      format="json"
  )
""",
        "full": """
DISTANCE MATRIX - Complete Documentation

PURPOSE:
  Calculate actual travel distances and times between multiple origins and destinations.
  Uses Google Distance Matrix API for real routing (not straight-line distance).

PARAMETERS:
  origins: list[str] (required)
    - List of starting point addresses
    - Can be full addresses or landmarks
    - Example: ["1600 Amphitheatre Parkway, Mountain View, CA"]

  destinations: list[str] (required)
    - List of ending point addresses
    - Same format as origins
    - Can be different from origins

  mode: str (default: "driving")
    - "driving": Car travel via roads
    - "walking": Pedestrian routes
    - "bicycling": Bike routes
    - "transit": Public transportation
    - Each mode uses different routing algorithms

  format: "text" | "json" | None (default: None)
    - Output format preference

RETURN VALUE (JSON format):
  {
    "results": [
      {
        "origin": "123 Main St...",
        "destination": "456 Oak Ave...",
        "distance_meters": 5420,
        "duration_seconds": 780,
        "status": "OK" | "NOT_FOUND" | "ZERO_RESULTS"
      }
    ],
    "summary": {
      "total_pairs": 4,
      "mode": "driving",
      "api_calls": 1
    }
  }

API CALL CALCULATION:
  The Distance Matrix API is efficient - one call can handle multiple pairs.
  Generally: 1 API call for up to 25 origin-destination pairs.

USE CASES:
  - Compare commute times from home to multiple job locations
  - Find closest office to a customer address
  - Calculate delivery route distances
  - Compare different travel modes (driving vs transit)

NOTES:
  - Returns actual routed distance, not straight-line
  - Duration includes typical traffic patterns
  - Results depend on availability of routing data
  - Some remote areas may return ZERO_RESULTS
"""
    },

    "list_place_types": {
        "name": "list_place_types",
        "summary": "Get all valid Google Place types, optionally filtered by category",
        "usage": """
Usage: list_place_types(categories=None)

Parameters:
  categories: list[str] | str | None (default: None)
    - Optional category filter
    - Examples: "food_drink", ["food_drink", "sports"]
    - If None, returns all categories

Returns:
  Dictionary of place types organized by category.

Available categories:
  automotive, business, culture, education, entertainment_recreation,
  facilities, finance, food_drink, government, health_wellness,
  lodging, places_of_worship, services, shopping, sports, transportation
""",
        "examples": """
Example 1: Get all food-related types
  list_place_types(categories="food_drink")
  # Returns: {"food_drink": ["restaurant", "cafe", "bar", "bakery", ...]}

Example 2: Get multiple categories
  list_place_types(categories=["food_drink", "sports"])

Example 3: Get all types
  list_place_types()
  # Returns all categories with all types
""",
        "full": """
LIST PLACE TYPES - Complete Documentation

PURPOSE:
  Discover valid Google Place types before making search requests.
  Helps avoid typos and shows all available options by category.

PARAMETERS:
  categories: list[str] | str | None (default: None)
    - Filter to specific categories
    - Single string: "food_drink"
    - List: ["food_drink", "sports"]
    - None: Return all categories

AVAILABLE CATEGORIES:
  - automotive: car_dealer, gas_station, parking, car_rental, car_repair, etc.
  - business: corporate_office, farm, ranch
  - culture: museum, art_gallery, monument, historical_landmark, etc.
  - education: school, university, library, driving_school
  - entertainment_recreation: park, amusement_park, zoo, aquarium, theater, etc.
  - facilities: public_bath, stable
  - finance: bank, atm, accounting
  - food_drink: restaurant, cafe, bar, bakery, meal_delivery, etc.
  - government: city_hall, courthouse, embassy, fire_station, police, etc.
  - health_wellness: hospital, pharmacy, doctor, dentist, physiotherapist, etc.
  - lodging: hotel, motel, hostel, campground, rv_park
  - places_of_worship: church, hindu_temple, mosque, synagogue
  - services: barber_shop, beauty_salon, florist, funeral_home, lawyer, etc.
  - shopping: shopping_mall, department_store, supermarket, bookstore, etc.
  - sports: gym, stadium, golf_course, sports_club, ski_resort
  - transportation: airport, train_station, bus_station, subway_station, etc.

RETURN VALUE:
  {
    "categories": {
      "food_drink": ["restaurant", "cafe", "bar", ...],
      "sports": ["gym", "stadium", ...]
    },
    "total_categories": 16,
    "total_types": 200+
  }

ERROR HANDLING:
  If invalid category provided:
  {
    "error": "Unknown categories: xyz",
    "available_categories": [...],
    "valid_results": {...}  // Any valid categories
  }

USAGE PATTERN:
  1. Call list_place_types() to see all options
  2. Note which types you want
  3. Use those types in nearby_search or batch_nearby_search
  4. Tool will validate and suggest corrections for typos

TIP:
  In nearby_search/batch_nearby_search, you can use category names directly.
  Example: feature_types="food_drink" expands to all food/drink types.
"""
    },

    "geocode": {
        "name": "geocode",
        "summary": "Convert addresses to coordinates (forward geocoding)",
        "usage": """
Usage: geocode(addresses, include_components=False, format=None)

Parameters:
  addresses: list[str] | str
    - Single address or list of addresses
    - Example: "1600 Amphitheatre Parkway, Mountain View, CA"
    - Example: ["Times Square, NYC", "Golden Gate Bridge, SF"]

  include_components: bool (default: False)
    - Include detailed address components (street, city, state, etc.)

  format: "text" | "json" | None
    - Output format (default: "text")

Returns:
  Coordinates and formatted addresses for each input address.
  Results are cached to reduce API costs.
""",
        "examples": """
Example 1: Single address
  geocode(addresses="1600 Amphitheatre Parkway, Mountain View, CA")

Example 2: Batch geocoding
  geocode(addresses=[
      "Times Square, NYC",
      "Golden Gate Bridge, SF",
      "Space Needle, Seattle"
  ])

Example 3: With components
  geocode(
      addresses="123 Main St, City, State",
      include_components=True,
      format="json"
  )
""",
        "full": """
GEOCODE - Complete Documentation

PURPOSE:
  Convert addresses to geographic coordinates (latitude/longitude).
  Useful for preparing location data before nearby searches or distance calculations.
  Supports batch processing with parallel API calls.

PARAMETERS:
  addresses: list[str] | str (required)
    - Address(es) to geocode
    - Can be full addresses: "123 Main St, City, State, ZIP"
    - Can be landmarks: "Eiffel Tower", "Times Square"
    - Can be partial: "Mountain View, CA"
    - Batch mode: List of addresses processed in parallel

  include_components: bool (default: False)
    - If True, includes detailed address breakdown
    - Components: street_number, route, locality, administrative_area, etc.
    - Useful for parsing addresses into structured data

  format: "text" | "json" | None (default: None)
    - Output format preference

RETURN VALUE (JSON format):
  {
    "results": [
      {
        "address": "1600 Amphitheatre Pkwy...",  // Original input
        "formatted_address": "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA",
        "lat": 37.4220,
        "lng": -122.0841,
        "place_id": "ChIJ...",  // Google's unique place identifier
        "status": "success"
      }
    ],
    "summary": {
      "total_addresses": 3,
      "successful": 3,
      "failed": 0
    }
  }

CACHING:
  - Results cached indefinitely (addresses don't change)
  - Subsequent requests for same address use cache
  - No API calls for cached addresses
  - Saves costs on repeated queries

ERROR HANDLING:
  - Invalid addresses return status: "error"
  - Partial results returned if some addresses fail
  - Each address processed independently

BATCH PROCESSING:
  - Multiple addresses geocoded in parallel
  - Max 10 concurrent requests
  - Efficient for processing location lists

USE CASES:
  - Convert user-entered addresses to coordinates
  - Prepare location data for batch_nearby_search
  - Standardize address formats
  - Extract detailed address components
  - Validate addresses before use

NOTES:
  - More specific addresses = better results
  - Include city/state for ambiguous street names
  - Landmark names work well (e.g., "Statue of Liberty")
  - Non-existent addresses may geocode to approximate locations
"""
    },

    "reverse_geocode": {
        "name": "reverse_geocode",
        "summary": "Convert coordinates to addresses (reverse geocoding)",
        "usage": """
Usage: reverse_geocode(coordinates, include_components=False, format=None)

Parameters:
  coordinates: list[dict] | dict
    - Single coordinate dict or list of dicts with {lat, lng}
    - Example: {"lat": 37.4220, "lng": -122.0841}
    - Example: [{"lat": 37.42, "lng": -122.08}, {"lat": 40.75, "lng": -73.98}]

  include_components: bool (default: False)
    - Include detailed address components

  format: "text" | "json" | None
    - Output format (default: "text")

Returns:
  Formatted addresses for each coordinate pair.
  Results are cached to reduce API costs.
""",
        "examples": """
Example 1: Single coordinate
  reverse_geocode(coordinates={"lat": 37.4220, "lng": -122.0841})

Example 2: Batch reverse geocoding
  reverse_geocode(coordinates=[
      {"lat": 37.4220, "lng": -122.0841},
      {"lat": 40.7580, "lng": -73.9855}
  ])

Example 3: GPS coordinates to address
  reverse_geocode(
      coordinates={"lat": 37.422, "lng": -122.084},
      format="json"
  )
""",
        "full": """
REVERSE GEOCODE - Complete Documentation

PURPOSE:
  Convert geographic coordinates to human-readable addresses.
  Useful for interpreting GPS data, map clicks, or stored coordinates.
  Supports batch processing with parallel API calls.

PARAMETERS:
  coordinates: list[dict] | dict (required)
    - Coordinate(s) to reverse geocode
    - Format: {"lat": latitude, "lng": longitude}
    - Latitude range: -90 to 90
    - Longitude range: -180 to 180
    - Batch mode: List of coordinate dicts processed in parallel

  include_components: bool (default: False)
    - If True, includes detailed address breakdown
    - Components: street_number, route, locality, etc.

  format: "text" | "json" | None (default: None)
    - Output format preference

RETURN VALUE (JSON format):
  {
    "results": [
      {
        "lat": 37.4220,
        "lng": -122.0841,
        "formatted_address": "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA",
        "place_id": "ChIJ...",
        "status": "success"
      }
    ],
    "summary": {
      "total_coordinates": 2,
      "successful": 2,
      "failed": 0
    }
  }

CACHING:
  - Results cached for 1 hour
  - Reduces API costs for repeated queries
  - Coordinate matching uses reasonable precision

VALIDATION:
  - Latitude must be -90 to 90
  - Longitude must be -180 to 180
  - Invalid coordinates return error status
  - Each coordinate validated independently

BATCH PROCESSING:
  - Multiple coordinates processed in parallel
  - Max 10 concurrent requests
  - Efficient for processing coordinate lists

USE CASES:
  - Convert GPS coordinates to addresses
  - Display human-readable locations from map clicks
  - Interpret sensor/tracking data
  - Generate address labels for coordinate data

PRECISION:
  - Google returns most specific address for coordinates
  - May return street address, intersection, or general area
  - Remote locations may return regional names
  - Ocean coordinates return nearest landmass

NOTES:
  - Results depend on Google Maps coverage
  - Same coordinates always return same address
  - Address may be interpolated between known addresses
  - More precise coordinates = more specific addresses
"""
    }
}


def get_tool_documentation(tool_name: str, detail_level: str = "usage") -> str:
    """
    Get documentation for a specific tool at the requested detail level.

    Args:
        tool_name: Name of the tool
        detail_level: "usage", "examples", or "full"

    Returns:
        Formatted documentation string
    """
    if tool_name not in TOOL_DOCS:
        available = ", ".join(TOOL_DOCS.keys())
        return f"Error: Unknown tool '{tool_name}'. Available tools: {available}"

    tool_doc = TOOL_DOCS[tool_name]

    if detail_level == "usage":
        return f"{tool_doc['name']}: {tool_doc['summary']}\n\n{tool_doc['usage']}"
    elif detail_level == "examples":
        return f"{tool_doc['name']}: {tool_doc['summary']}\n\n{tool_doc['examples']}"
    elif detail_level == "full":
        return f"{tool_doc['name']}: {tool_doc['summary']}\n\n{tool_doc['full']}"
    else:
        return f"Error: Unknown detail level '{detail_level}'. Use 'usage', 'examples', or 'full'."


def list_available_tools() -> dict:
    """
    Get a list of all available tools with their summaries.

    Returns:
        Dictionary mapping tool names to summaries
    """
    return {name: doc["summary"] for name, doc in TOOL_DOCS.items()}

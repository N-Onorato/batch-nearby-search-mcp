# CLAUDE.md - Developer Reference

**Quick reference for AI assistants and developers working on this codebase.**
**Limited to 300 lines - essential patterns and commands only.**

---

## Project Overview

**Purpose**: Optimized MCP server for batch nearby searches using Google Places
API **Language**: Python 3.10+ **Framework**: FastMCP **Key optimization**:
Parallel API calls + caching (50-80% cost reduction)

---

## Context Bloat Optimization (IMPORTANT!)

**This server implements progressive disclosure to reduce context usage by ~80-85%.**

Traditional MCP servers load full documentation for all tools upfront, consuming thousands
of tokens before any conversation starts. This server uses a different approach:

**Minimal Tool Descriptions**:
- Each tool has a ~30-50 token summary (vs. traditional 500-800 tokens)
- Just enough info for the LLM to know WHEN to use the tool
- Example: "Find nearby places for MULTIPLE locations in parallel..."

**On-Demand Documentation**:
- Use `get_tool_docs(tool_name, detail_level)` to fetch full docs when needed
- Detail levels:
  - `"usage"`: Parameter descriptions and return values (~200 tokens)
  - `"examples"`: Code examples and common patterns (~300 tokens)
  - `"full"`: Everything including tips, edge cases, API costs (~500 tokens)

**Expected Savings**:
- Before: ~5-6k tokens for all tool descriptions
- After: ~600-800 tokens (summaries) + on-demand fetches
- Reduction: 80-85% baseline context usage

**Usage Pattern**:
1. See tool summaries in initial context
2. If you need details, call `get_tool_docs("batch_nearby_search", "usage")`
3. If you need examples, call `get_tool_docs("batch_nearby_search", "examples")`
4. If you need everything, call `get_tool_docs("batch_nearby_search", "full")`

---

## Essential Files

```
src/batch_nearby_search/
├── server.py          # Main MCP server, @mcp.tool decorators, entry point
├── tool_docs.py       # Full tool documentation (loaded on-demand)
├── models.py          # Pydantic models (Location, PlaceResult, etc.)
├── google_client.py   # Google API wrapper (async + caching)
├── cache.py           # Caching utilities (LRU + TTL)
└── utils.py           # Helper functions

Configuration:
├── pyproject.toml     # Dependencies and scripts
├── .env               # API keys (gitignored)
└── .env.example       # Template

Documentation:
├── README.md          # User-facing setup/usage
├── IMPL_PLAN.md       # Implementation details
└── CLAUDE.md          # This file
```

---

## Code Patterns

### 1. Pydantic Models (models.py)

**Location input** - Accept either address OR coordinates:

```python
class Location(BaseModel):
    address: str | None = None
    lat: float | None = None
    lng: float | None = None

    @model_validator(mode='after')
    def check_location(self):
        if not self.address and not (self.lat and self.lng):
            raise ValueError("Provide either address or lat/lng")
        return self
```

**Field filtering** - Optional fields based on user request:

```python
class PlaceResult(BaseModel):
    # Always included (minimal)
    name: str
    distance_meters: float | None
    place_id: str

    # Optional fields (included if in include_fields param)
    rating: float | None = None
    address: str | None = None
    phone_number: str | None = None
    # ... more optional fields
```

**Input validation** - Use Field for constraints:

```python
class BatchRequest(BaseModel):
    locations: list[Location] = Field(..., max_length=20)  # Max 20 locations
    feature_types: list[str] = Field(..., min_length=1, max_length=10)
    radius_meters: int = Field(5000, ge=100, le=50000)  # 100m-50km
    include_fields: list[str] | None = None
```

### 2. FastMCP Tools (server.py)

**Tool decorator pattern**:

```python
from fastmcp import FastMCP

mcp = FastMCP("batch-nearby-search")

@mcp.tool
async def batch_nearby_search(
    locations: list[Location],
    feature_types: list[str] | str,  # Can be single string or list
    radius_meters: int = 5000,
    include_fields: list[str] | None = None,
    format: Literal["text", "json"] | None = None  # Output format
) -> str | dict:
    """
    Docstring becomes tool description in MCP.

    Args:
        locations: List of addresses or coordinates
        feature_types: Place types like ["park", "gym"] or categories like "food_drink"
        radius_meters: Search radius (100-50000)
        include_fields: Optional fields to include in results
        format: "text" for log format (default), "json" for structured data

    Returns:
        Log-style text output (default) or structured JSON
    """
    # Implementation
```

**Error handling & format support** - Return partial results, don't fail completely:

```python
# Handle single string input
if isinstance(feature_types, str):
    feature_types = [feature_types]

results = {}
for i, location in enumerate(locations):
    try:
        results[f"location_{i}"] = await process_location(location)
    except Exception as e:
        results[f"location_{i}"] = {"status": "error", "error": str(e)}

# Return based on format
if format == "json":
    return {"results": results, "summary": {...}}
else:
    # Text mode (default): log-style output
    # Example: - 123 Main St (37.7, -122.4) "Starbucks" 250 meters [rating: 4.5]
    return format_as_log(results)
```

### 3. Async Google API Client (google_client.py)

**Rate limiting with semaphore**:

```python
class GooglePlacesClient:
    def __init__(self, api_key: str, max_concurrent: int = 10):
        self.client = googlemaps.Client(key=api_key)
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def _rate_limited_call(self, func, *args, **kwargs):
        async with self.semaphore:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, func, *args, **kwargs)
```

**Parallel execution pattern**:

```python
async def batch_search(self, locations, feature_types):
    tasks = []
    for location in locations:
        for feature_type in feature_types:
            tasks.append(self.nearby_search(location, feature_type))

    # Execute all in parallel (rate-limited by semaphore)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

### 4. Caching (cache.py)

**Two-tier caching strategy**:

```python
from cachetools import LRUCache, TTLCache
from functools import wraps

# Geocoding cache - indefinite (addresses don't change)
geocoding_cache = LRUCache(maxsize=1000)

# Places cache - 1 hour TTL (places may change)
places_cache = TTLCache(maxsize=500, ttl=3600)

def cache_geocoding(func):
    @wraps(func)
    async def wrapper(address: str):
        if address in geocoding_cache:
            return geocoding_cache[address]
        result = await func(address)
        geocoding_cache[address] = result
        return result
    return wrapper
```

**Cache key generation**:

```python
def make_cache_key(location: Location, feature_type: str, radius: int) -> str:
    """Create consistent cache key"""
    if location.address:
        return f"{location.address}|{feature_type}|{radius}"
    else:
        return f"{location.lat},{location.lng}|{feature_type}|{radius}"
```

### 5. Field Filtering (utils.py)

**Extract only requested fields**:

```python
def filter_place_fields(place: dict, include_fields: list[str] | None) -> dict:
    """Extract only requested fields from Google API response"""
    # Always include minimal fields
    result = {
        "name": place.get("name"),
        "place_id": place.get("place_id"),
        "distance_meters": place.get("distance_meters")
    }

    if not include_fields:
        return result

    # Field mapping: user-friendly name -> API field
    field_map = {
        "rating": "rating",
        "user_ratings_total": "user_ratings_total",
        "address": "vicinity",
        "phone_number": "formatted_phone_number",
        "website": "website",
        "price_level": "price_level",
        "opening_hours": "opening_hours"
    }

    for field in include_fields:
        if field in field_map:
            result[field] = place.get(field_map[field])

    return result
```

---

## Common Usage Patterns & Best Practices

### Using batch_nearby_search Effectively

**Example call structure**:

```python
# Mix of addresses and coordinates
locations = [
    {"address": "1600 Amphitheatre Parkway, Mountain View, CA"},
    {"address": "1 Apple Park Way, Cupertino, CA"},
    {"lat": 37.4849, "lng": -122.1477}
]

# Can be string or list
feature_types = ["park", "grocery_store"]  # or just "park"

# Call the tool
result = await batch_nearby_search(
    locations=locations,
    feature_types=feature_types,
    radius_meters=2000,
    include_fields=["rating", "address"],
    format="json"  # or "text"
)
```

**Result structure** - Always organized by location first, then feature type:

```python
{
  "results": [
    {
      "location_index": 0,
      "coordinates": {"lat": 37.4220, "lng": -122.0841},
      "features": {
        "park": [{"name": "...", "distance_meters": 450, ...}],
        "grocery_store": [...]
      },
      "status": "success"  # or "partial" or "error"
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
```

**Access pattern**: `result["results"][location_idx]["features"][feature_type][place_idx]`

### Common Mistakes & Solutions

**❌ WRONG**: Expecting results grouped by feature type first
```python
# This structure does NOT exist:
result["results"]["park"][0]  # Wrong!
```

**✅ CORRECT**: Results are grouped by location first
```python
# Access like this:
result["results"][0]["features"]["park"][0]  # Correct!
```

**❌ WRONG**: Assuming all feature types will always have results
```python
# This might not exist if no parks found:
parks = result["results"][0]["features"]["park"]  # Might be []
```

**✅ CORRECT**: Check if feature type exists and has results
```python
features = result["results"][0]["features"]
parks = features.get("park", [])
if parks:
    nearest_park = parks[0]  # Places are sorted by distance
```

### Validation & Error Handling

**Invalid place types** - Tool now shows helpful validation messages:

```
Validation: 2 of 3 place types are valid. Proceeding with: park, grocery_store
Invalid types:
  - 'grocrey_store' is not valid. Did you mean: grocery_store, convenience_store, supermarket?
```

**Key points**:
- Search PROCEEDS with valid types (doesn't fail completely)
- Invalid types are skipped automatically
- You get suggestions for corrections
- Check warnings field in response for details

**Partial failures** - Individual locations or feature types can fail:

```python
# Check status per location
for location_result in result["results"]:
    if location_result["status"] == "success":
        # All feature types succeeded
        pass
    elif location_result["status"] == "partial":
        # Some feature types succeeded, check "errors" field
        errors = location_result.get("errors", [])
    elif location_result["status"] == "error":
        # All feature types failed
        pass
```

### Limits & API Call Calculations

**Hard limits** (enforced by Pydantic validation):
- Max 20 locations per request
- Max 10 feature types per request
- Radius: 100m - 50km

**API call calculation**:
```
Total API calls = num_locations × num_feature_types

Examples:
- 5 locations × 3 types = 15 API calls (~$0.48)
- 10 locations × 5 types = 50 API calls (~$1.60)
- 20 locations × 10 types = 200 API calls (~$6.40)
```

**Recommendation**: Keep batches under 50 total API calls for responsive performance.

---

## Important Commands

### Setup

```bash
# Install dependencies (using uv - recommended)
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"

# Set up environment
cp .env.example .env
# Edit .env and add your GOOGLE_MAPS_API_KEY
```

### Running the Server

**For Claude Desktop**:

```bash
# Start server (stdio transport)
uv run batch-nearby-search

# Or with python -m
python -m batch_nearby_search.server
```

**Testing locally**:

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=batch_nearby_search --cov-report=html

# Format code
black src/ tests/

# Lint
ruff check src/ tests/
```

### Claude Desktop Configuration

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
    "mcpServers": {
        "batch-nearby-search": {
            "command": "uv",
            "args": [
                "--directory",
                "/absolute/path/to/batch-nearby-search-mcp",
                "run",
                "batch-nearby-search"
            ],
            "env": {
                "GOOGLE_MAPS_API_KEY": "your-key-here"
            }
        }
    }
}
```

After updating config:

1. Save the file
2. Restart Claude Desktop completely
3. Check for the MCP icon to verify connection

---

## Google API Reference

### Required APIs

Enable these in Google Cloud Console:

1. **Places API (New)** - For nearby searches
2. **Distance Matrix API** - For distance calculations
3. **Geocoding API** - For address → coordinates

### Place Types (feature_types)

Common types to use:

```python
amenities = ["park", "gym", "library", "hospital"]
food = ["restaurant", "cafe", "grocery_store", "supermarket"]
transit = ["bus_station", "subway_station", "train_station"]
services = ["atm", "bank", "pharmacy", "gas_station"]
```

Full list:
https://developers.google.com/maps/documentation/places/web-service/supported_types

## Testing Locations (For Development)

```python
test_locations = [
    {"address": "1600 Amphitheatre Parkway, Mountain View, CA"},  # Googleplex
    {"address": "1 Apple Park Way, Cupertino, CA"},              # Apple Park
    {"lat": 37.7749, "lng": -122.4194},                          # San Francisco
]

test_features = ["park", "cafe", "gym"]
```

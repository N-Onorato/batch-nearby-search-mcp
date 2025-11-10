# CLAUDE.md - Developer Reference

**Quick reference for AI assistants and developers working on this codebase.**
**Limited to 300 lines - essential patterns and commands only.**

---

## Project Overview

**Purpose**: Optimized MCP server for batch nearby searches using Google Places
API **Language**: Python 3.10+ **Framework**: FastMCP **Key optimization**:
Parallel API calls + caching (50-80% cost reduction)

---

## Essential Files

```
src/batch_nearby_search/
├── server.py          # Main MCP server, @mcp.tool decorators, entry point
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
    feature_types: list[str],
    radius_meters: int = 5000,
    include_fields: list[str] | None = None
) -> dict:
    """
    Docstring becomes tool description in MCP.

    Args:
        locations: List of addresses or coordinates
        feature_types: Place types like ["park", "gym", "grocery_store"]
        radius_meters: Search radius (100-50000)
        include_fields: Optional fields to include in results

    Returns:
        Structured results with per-location status and summary
    """
    # Implementation
```

**Error handling** - Return partial results, don't fail completely:

```python
results = {}
for i, location in enumerate(locations):
    try:
        results[f"location_{i}"] = await process_location(location)
    except Exception as e:
        results[f"location_{i}"] = {"status": "error", "error": str(e)}

return {"results": results, "summary": {...}}
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

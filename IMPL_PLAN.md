# Batch Nearby Search MCP - Implementation Plan

## Project Overview

An optimized MCP server for finding distances to various places using Google's APIs. The server reduces API calls from O(N×M) to parallelized O(N×M) with intelligent caching.

## Problem Statement

Current approach requires at least N tool calls for nearby searches with dynamic features. This results in:
- High API costs (each call charges separately)
- Increased latency (sequential calls)
- Poor user experience (Claude makes many individual requests)

## Solution Architecture

### Three-Tool Design

1. **distance_matrix** - For fixed locations using Google Distance Matrix API
2. **nearby_search** - Single location, multiple feature types
3. **batch_nearby_search** - Multiple locations × multiple features (PRIMARY OPTIMIZATION)

### Key Optimization: Concurrent API Calls

Instead of sequential calls:
```
Location 1 + Park -> API call (wait)
Location 1 + Gym -> API call (wait)
Location 2 + Park -> API call (wait)
...
```

Use async parallelization:
```
asyncio.gather(
    all_location_feature_combinations
) -> Results in parallel
```

### Optional Field Selection

Allow Claude to request specific fields per task:
```python
nearby_search(
    location="123 Main St",
    feature_types=["park", "gym"],
    include_fields=["name", "rating", "distance", "address"]  # Optional
)
```

Default fields (minimal):
- name
- distance
- place_id

Common optional fields:
- rating
- user_ratings_total
- address
- phone_number
- opening_hours
- price_level
- website
- photos (photo_reference URLs)

## Implementation Phases

### Phase 1: Project Setup (30 min)

**Files to create:**
- `pyproject.toml` - Dependencies: fastmcp, googlemaps, pydantic, python-dotenv
- `.env.example` - Template for API key
- Directory structure:
  ```
  src/batch_nearby_search/
  ├── __init__.py
  ├── server.py
  ├── models.py
  ├── google_client.py
  ├── cache.py
  └── utils.py
  ```

**Dependencies:**
```toml
[project]
dependencies = [
    "fastmcp>=0.3.0",
    "googlemaps>=4.10.0",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
]
```

### Phase 2: Data Models (1 hour)

**models.py - Pydantic models:**

```python
from pydantic import BaseModel, Field
from typing import Literal

class Location(BaseModel):
    """Flexible location input - address OR coordinates"""
    address: str | None = None
    lat: float | None = None
    lng: float | None = None

class PlaceResult(BaseModel):
    """Standardized place result"""
    name: str
    distance_meters: float | None
    place_id: str
    # Optional fields (included based on include_fields param)
    rating: float | None = None
    user_ratings_total: int | None = None
    address: str | None = None
    phone_number: str | None = None
    website: str | None = None
    price_level: int | None = None
    opening_hours: dict | None = None

class BatchNearbySearchRequest(BaseModel):
    """Request for batch nearby search"""
    locations: list[Location] = Field(..., max_length=20)
    feature_types: list[str] = Field(..., min_length=1, max_length=10)
    radius_meters: int = Field(1500, ge=100, le=50000)
    max_results_per_type: int = Field(3, ge=1, le=10)
    include_fields: list[str] | None = None
```

### Phase 3: Google API Client (1.5 hours)

**google_client.py - Async wrapper with caching:**

Key features:
- Async/await for all API calls
- Geocoding cache (address → coordinates) with LRU
- Places cache with TTL (1 hour default)
- Error handling for individual location failures
- Field filtering based on include_fields parameter

**Caching strategy:**
```python
@lru_cache(maxsize=1000)
def geocode_address(address: str) -> tuple[float, float]:
    """Cache geocoding results indefinitely"""

@ttl_cache(maxsize=500, ttl=3600)
def nearby_search_cached(lat, lng, types, radius) -> list[dict]:
    """Cache nearby results for 1 hour"""
```

### Phase 4: MCP Tools Implementation (2 hours)

#### Tool 1: distance_matrix
```python
@mcp.tool
async def distance_matrix(
    origins: list[str],
    destinations: list[str],
    mode: Literal["driving", "walking", "bicycling", "transit"] = "driving"
) -> dict:
    """
    Calculate distances between multiple origin-destination pairs.
    Uses Google Distance Matrix API for fixed locations.
    """
```

#### Tool 2: nearby_search
```python
@mcp.tool
async def nearby_search(
    location: Location,
    feature_types: list[str],
    radius_meters: int = 1500,
    max_results_per_type: int = 3,
    include_fields: list[str] | None = None
) -> dict:
    """
    Find nearby places of multiple types from a single location.

    Args:
        location: Address or coordinates
        feature_types: Place types (e.g., ["park", "gym", "grocery_store"])
        radius_meters: Search radius (100-50000)
        max_results_per_type: Max results per type (1-10)
        include_fields: Optional fields to include (rating, address, etc.)
    """
```

#### Tool 3: batch_nearby_search (MAIN OPTIMIZATION)
```python
@mcp.tool
async def batch_nearby_search(
    locations: list[Location],
    feature_types: list[str],
    radius_meters: int = 1500,
    max_results_per_type: int = 3,
    include_fields: list[str] | None = None
) -> dict:
    """
    Find nearby places for MULTIPLE locations in parallel.

    Optimized for:
    - Concurrent API calls (asyncio.gather)
    - Partial failure handling (returns success per location)
    - Caching (reduces redundant API calls)

    Returns structure:
    {
        "results": {
            "location_0": {
                "address": "123 Main St",
                "features": {
                    "park": [...results...],
                    "gym": [...results...]
                },
                "status": "success"
            },
            ...
        },
        "summary": {
            "total_locations": 5,
            "successful": 4,
            "failed": 1,
            "total_places_found": 47
        }
    }
    """
```

### Phase 5: Rate Limiting (30 min)

**Implementation:**
```python
class RateLimiter:
    def __init__(self, max_concurrent=10):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(self, coro):
        async with self.semaphore:
            return await coro
```

**Google API Quotas:**
- Distance Matrix: 100 elements/sec
- Places Nearby Search: 10 QPS (standard), 100 QPS (premium)
- Default to conservative 10 concurrent requests

### Phase 6: Claude Desktop Integration

**Configuration file location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

**Example configuration:**
```json
{
  "mcpServers": {
    "batch-nearby-search": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/batch-nearby-search-mcp",
        "run",
        "batch-nearby-search"
      ],
      "env": {
        "GOOGLE_MAPS_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## Expected Performance Improvements

### API Call Reduction
- **Before**: 5 locations × 3 features = 15 sequential calls (~30-45 seconds)
- **After**: 15 parallel calls (~3-5 seconds)
- **With caching**: Repeated queries = 0 additional calls

### Cost Savings
- Geocoding cache: Eliminates repeated address lookups
- Places cache: 1-hour TTL reduces repeated searches by 70-90%
- Estimated savings: 50-80% for typical usage patterns

## Testing Strategy

### Unit Tests
- Geocoding cache hit/miss
- Field filtering logic
- Error handling (invalid addresses, API failures)

### Integration Tests
- Real Google API calls with test locations
- Batch operations with 10+ locations
- Partial failure scenarios

### Usage Examples for Claude

**Example 1: Compare amenities across neighborhoods**
```
Find the nearest park, grocery store, and coffee shop for these addresses:
- 1600 Amphitheatre Parkway, Mountain View, CA
- 1 Apple Park Way, Cupertino, CA
- 1 Hacker Way, Menlo Park, CA

Include ratings and addresses in the results.
```

**Example 2: Distance analysis**
```
I'm looking at houses in these 5 locations. For each, find:
- Nearest hospital (with phone number)
- Nearest elementary school (with rating)
- Nearest public transit station

Show me distances and ratings.
```

## File Structure (Final)

```
batch-nearby-search-mcp/
├── IMPL_PLAN.md              # This file
├── CLAUDE.md                  # Code guidelines and patterns
├── README.md                  # User-facing documentation
├── pyproject.toml             # Project config and dependencies
├── .env.example               # Environment template
├── .gitignore
├── src/
│   └── batch_nearby_search/
│       ├── __init__.py
│       ├── server.py          # Main MCP server with @mcp.tool decorators
│       ├── models.py          # Pydantic models
│       ├── google_client.py   # Google API wrapper (async + caching)
│       ├── cache.py           # Caching utilities (LRU + TTL)
│       └── utils.py           # Helper functions
└── tests/
    ├── __init__.py
    └── test_tools.py          # Test suite
```

## Timeline Estimate

- Phase 1 (Setup): 30 minutes
- Phase 2 (Models): 1 hour
- Phase 3 (Google Client): 1.5 hours
- Phase 4 (Tools): 2 hours
- Phase 5 (Rate Limiting): 30 minutes
- Phase 6 (Integration): 30 minutes
- Documentation & Testing: 1 hour

**Total: 6-7 hours for complete implementation**

## Success Criteria

- ✅ All three tools functional in Claude Desktop
- ✅ Batch operations run concurrently (verified via timing)
- ✅ Caching reduces redundant API calls (verified via logs)
- ✅ Optional field selection works correctly
- ✅ Partial failures handled gracefully
- ✅ Cost reduced by 50%+ for typical usage
- ✅ Documentation complete with examples

## Next Steps After Implementation

1. **Monitoring**: Add logging for API usage tracking
2. **Cost alerts**: Track API spend per session
3. **Extended caching**: Consider Redis for persistent cache
4. **Additional tools**:
   - Route optimization (best order to visit places)
   - Place details enrichment
   - Travel time matrix with traffic

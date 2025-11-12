# Batch Nearby Search MCP Server

An optimized Model Context Protocol (MCP) server for finding distances to various places using Google's APIs. Built with FastMCP, this server provides intelligent batch processing with concurrent API calls and caching to reduce costs by 50-80%.

## Features

- **Batch Processing**: Search multiple locations and feature types in parallel
- **Intelligent Caching**: Two-tier caching (geocoding + places) reduces redundant API calls
- **Optional Field Selection**: Claude can request only the fields needed for each task
- **Partial Failure Handling**: Returns successful results even if some locations fail
- **Cost Optimization**: Parallel execution + caching = 50-80% cost savings
- **Easy Integration**: Works seamlessly with Claude Desktop

## Tools Provided

### 1. `distance_matrix`
Calculate distances and travel times between multiple origin-destination pairs using Google Distance Matrix API.

**Best for**: Comparing commute times to known destinations

### 2. `nearby_search`
Find nearby places of multiple types from a single location.

**Best for**: Exploring amenities around one address

### 3. `batch_nearby_search` (⚡ OPTIMIZED)
Find nearby places for multiple locations in parallel - the primary optimization tool.

**Best for**: Comparing amenities across multiple neighborhoods or properties

## Installation

### Prerequisites

- Python 3.10 or higher
- Google Maps API key with the following APIs enabled:
  - Places API (New)
  - Distance Matrix API
  - Geocoding API
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd batch-nearby-search-mcp
   ```

2. **Install dependencies**

   With uv (recommended):
   ```bash
   uv pip install -e .
   ```

   With pip:
   ```bash
   pip install -e .
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your Google Maps API key:
   ```
   GOOGLE_MAPS_API_KEY=your-api-key-here
   ```

4. **Get a Google Maps API key**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable required APIs: Places API (New), Distance Matrix API, Geocoding API
   - Create credentials (API key)
   - Enable billing (required for API usage)

## Claude Desktop Configuration

Add this to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

**Linux**: `~/.config/Claude/claude_desktop_config.json`

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
        "GOOGLE_MAPS_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

**Important**: Replace `/absolute/path/to/batch-nearby-search-mcp` with the actual path on your system.

After updating the configuration:
1. Save the file
2. Restart Claude Desktop completely
3. Look for the MCP icon to verify the connection

## Usage Examples

### Example 1: Compare Neighborhoods

Ask Claude:
```
I'm looking at houses in these locations:
- 1600 Amphitheatre Parkway, Mountain View, CA
- 1 Apple Park Way, Cupertino, CA
- 1 Hacker Way, Menlo Park, CA

For each location, find the nearest:
- Park (with rating)
- Grocery store (with address and rating)
- Coffee shop (with rating)

Show me a comparison.
```

Claude will use `batch_nearby_search` to efficiently search all locations in parallel.

### Example 2: Distance Analysis

Ask Claude:
```
Calculate driving distances from my address (123 Main St, City, State) to:
- San Francisco Airport
- Stanford University
- Downtown San Jose

Show me distances and travel times.
```

Claude will use `distance_matrix` for this request.

### Example 3: Single Location Exploration

Ask Claude:
```
I'm staying at 456 Market St, San Francisco, CA.
Find nearby restaurants, cafes, and gyms within walking distance (500 meters).
Include ratings and addresses.
```

Claude will use `nearby_search` for this request.

### Example 4: Batch Nearby Search (Detailed)

This example shows the **exact structure** for calling `batch_nearby_search` directly, including how results are organized.

**What you're searching:**
- 3 locations (mix of addresses and coordinates)
- 2 feature types per location (park, grocery_store)
- Include optional fields (rating, address)

**Tool call structure:**
```json
{
  "locations": [
    {"address": "1600 Amphitheatre Parkway, Mountain View, CA"},
    {"address": "1 Apple Park Way, Cupertino, CA"},
    {"lat": 37.4849, "lng": -122.1477}
  ],
  "feature_types": ["park", "grocery_store"],
  "radius_meters": 2000,
  "include_fields": ["rating", "address"],
  "format": "json"
}
```

**How results are organized:**

Results are grouped **by location first, then by feature type**:

```
results[0]  (first location: "1600 Amphitheatre...")
  ├── location_index: 0
  ├── coordinates: {lat: 37.4220, lng: -122.0841}
  ├── features:
  │   ├── "park": [
  │   │     {name: "Charleston Park", distance_meters: 450, rating: 4.5, ...},
  │   │     {name: "Shoreline Park", distance_meters: 890, rating: 4.7, ...}
  │   │   ]
  │   └── "grocery_store": [
  │         {name: "Whole Foods", distance_meters: 1200, rating: 4.2, ...}
  │       ]
  └── status: "success"

results[1]  (second location: "1 Apple Park...")
  ├── location_index: 1
  ├── features:
  │   ├── "park": [...]
  │   └── "grocery_store": [...]
  └── status: "success"

results[2]  (third location: coordinates)
  └── ... (same structure)
```

**Summary information:**
```json
{
  "summary": {
    "total_locations": 3,
    "successful": 3,
    "partial": 0,
    "failed": 0,
    "total_places_found": 15
  }
}
```

**Key points:**
- Each location gets its own entry in `results[]`
- Within each location, results are grouped by `feature_type`
- Partial failures are supported - if one feature type fails, others still return
- Total API calls = 3 locations × 2 feature types = 6 parallel requests

**Text format output:**
```
=== Location 0: 1600 Amphitheatre Parkway, Mountain View, CA ===
Coordinates: (37.4220, -122.0841)
Status: success

  Feature: park
  - "Charleston Park" 450m [rating: 4.5, address: "123 Charleston Rd"]
  - "Shoreline Park" 890m [rating: 4.7, address: "3070 N Shoreline Blvd"]

  Feature: grocery_store
  - "Whole Foods Market" 1200m [rating: 4.2, address: "2580 California St"]

=== Location 1: 1 Apple Park Way, Cupertino, CA ===
...
```

**Limits and gotchas:**
- **Max 20 locations** per request (validation enforces this)
- **Max 10 feature types** per request
- API calls = locations × feature_types (e.g., 10 locations × 5 types = 50 calls)
- Results can vary in size - some locations may have no results for certain types
- Partial failures are handled gracefully - check `status` field per location

## Performance & Cost

### API Costs (as of 2024)

- **Places API Nearby Search**: $32 per 1,000 requests
- **Distance Matrix API**: $5 per 1,000 elements
- **Geocoding API**: $5 per 1,000 requests

### Cost Optimization Examples

**Without caching**:
- 5 locations × 3 features = 15 API calls
- Cost: ~$0.48
- Time: ~30-45 seconds (sequential)

**With this server (parallel + caching)**:
- First query: 15 API calls, ~$0.48, ~3-5 seconds
- Repeated query: 0 API calls (cached), $0.00, <1 second
- **Savings: 50-80% over time**

### Batch Size Recommendations

- **Optimal**: 5-15 locations × 2-5 feature types (25-75 API calls)
- **Maximum**: 20 locations × 10 feature types (200 API calls, ~$6.40)

## Configuration Options

Environment variables (set in `.env`):

```bash
# Required
GOOGLE_MAPS_API_KEY=your-api-key-here

# Optional - adjust caching
GEOCODING_CACHE_SIZE=1000        # Default: 1000
PLACES_CACHE_SIZE=500            # Default: 500
PLACES_CACHE_TTL=3600            # Default: 3600 (1 hour)

# Optional - rate limiting
MAX_CONCURRENT_REQUESTS=10       # Default: 10 (recommended)
```

## Common Place Types

Use these in `feature_types` parameters. You can specify individual place types or entire categories:

**Individual Place Types**:
- **Amenities**: `park`, `gym`, `library`, `hospital`, `pharmacy`
- **Food & Drink**: `restaurant`, `cafe`, `bar`, `grocery_store`, `supermarket`
- **Transit**: `bus_station`, `subway_station`, `train_station`, `airport`
- **Services**: `atm`, `bank`, `gas_station`, `post_office`
- **Education**: `school`, `university`

**Category Names** (searches all types in category):
- `food_drink` - All restaurants, cafes, bars, etc.
- `sports` - All gyms, fitness centers, stadiums, etc.
- `health_wellness` - All hospitals, pharmacies, doctors, etc.
- `shopping` - All stores, malls, supermarkets, etc.
- `entertainment_recreation` - All parks, theaters, museums, etc.
- And more! Use `list_place_types()` to see all categories.

Full list: [Google Place Types](https://developers.google.com/maps/documentation/places/web-service/supported_types)

## Optional Fields & Output Format

### Output Format

All tools support a `format` parameter:
- **`format="text"`** (default): Returns human-readable log format showing each place on its own line
- **`format="json"`**: Returns structured JSON data for programmatic use

Example log format output:
```
- 123 Main St (37.7749, -122.4194) "Starbucks" 250 meters [rating: 4.5]
- 123 Main St (37.7749, -122.4194) "Blue Bottle Coffee" 450 meters [rating: 4.2]
```

### Optional Fields

When using `nearby_search` or `batch_nearby_search`, you can specify which optional fields to include:

**Available fields**:
- `rating` - Average rating (0-5)
- `user_ratings_total` - Number of ratings
- `address` - Formatted address
- `phone_number` - Phone number
- `website` - Website URL
- `price_level` - Price level (0-4)
- `opening_hours` - Opening hours information
- `types` - List of place types

**Default** (if not specified): Only `name`, `place_id`, and `distance_meters` are returned.

## Understanding Tool Responses

This section explains how each tool organizes its results so you know exactly what to expect.

### `batch_nearby_search` Response Structure

Results are organized **by location first, then by feature type within each location**:

```json
{
  "results": [
    {
      "location_index": 0,
      "location": {"address": "1600 Amphitheatre Parkway, Mountain View, CA"},
      "coordinates": {"lat": 37.4220, "lng": -122.0841},
      "features": {
        "park": [
          {"name": "Charleston Park", "distance_meters": 450, "place_id": "ChIJ...", ...},
          {"name": "Shoreline Park", "distance_meters": 890, "place_id": "ChIJ...", ...}
        ],
        "grocery_store": [
          {"name": "Whole Foods", "distance_meters": 1200, "place_id": "ChIJ...", ...}
        ]
      },
      "status": "success"
    },
    {
      "location_index": 1,
      "location": {"lat": 37.4849, "lng": -122.1477},
      "coordinates": {"lat": 37.4849, "lng": -122.1477},
      "features": {
        "park": [...],
        "grocery_store": [...]
      },
      "status": "success"
    }
  ],
  "summary": {
    "total_locations": 2,
    "successful": 2,
    "partial": 0,
    "failed": 0,
    "total_places_found": 8
  }
}
```

**Key points:**
- **Hierarchy**: `results[location_index].features[feature_type][place_index]`
- **Status values**:
  - `"success"`: All feature types returned results
  - `"partial"`: Some feature types succeeded, some failed (see `errors` field)
  - `"error"`: All feature types failed or geocoding failed
- **Partial failures**: If searching for 3 feature types and 1 fails, you still get results for the other 2
- **Empty results**: A feature type can have an empty array `[]` if no places were found

### `nearby_search` Response Structure

Similar to batch, but for a single location:

```json
{
  "location": {"lat": 37.4220, "lng": -122.0841},
  "features": {
    "park": [
      {"name": "Charleston Park", "distance_meters": 450, ...}
    ],
    "cafe": [
      {"name": "Blue Bottle Coffee", "distance_meters": 320, ...}
    ]
  },
  "summary": {
    "total_feature_types": 2,
    "total_places_found": 5,
    "radius_meters": 5000
  }
}
```

**Key points:**
- **Hierarchy**: `features[feature_type][place_index]`
- Results are grouped by feature type
- Each feature type is an array of places, sorted by distance

### `distance_matrix` Response Structure

```json
{
  "results": [
    {
      "origin": "1600 Amphitheatre Parkway, Mountain View, CA",
      "destination": "1 Apple Park Way, Cupertino, CA",
      "distance_meters": 15420,
      "duration_seconds": 1260,
      "status": "OK"
    }
  ],
  "summary": {
    "total_pairs": 1,
    "mode": "driving",
    "api_calls": 1
  }
}
```

**Key points:**
- Each origin-destination pair gets its own result
- 3 origins × 2 destinations = 6 results
- `status` can be `"OK"`, `"NOT_FOUND"`, `"ZERO_RESULTS"`, etc.

### `geocode` and `reverse_geocode` Response Structure

```json
{
  "results": [
    {
      "address": "Times Square, NYC",
      "formatted_address": "Manhattan, NY 10036, USA",
      "lat": 40.7580,
      "lng": -73.9855,
      "status": "success"
    }
  ],
  "summary": {
    "total_addresses": 1,
    "successful": 1,
    "failed": 0
  }
}
```

**Key points:**
- Supports batch geocoding (multiple addresses at once)
- Each result has a `status` field: `"success"` or `"error"`
- Failed geocoding still returns partial results for successful addresses

### Validation Warnings

When you provide invalid place types, you'll see a warning like this:

```
Validation: 2 of 3 place types are valid. Proceeding with: park, grocery_store
Invalid types:
  - 'grocrey_store' is not valid. Did you mean: grocery_store, convenience_store, supermarket?
```

**What this means:**
- The search will **proceed** with the valid types (park, grocery_store)
- Invalid types are skipped, but you get suggestions for corrections
- No need to retry - you'll still get results for the valid types

## Troubleshooting

### "API key not valid"
1. Check that your `.env` file contains the correct API key
2. Verify APIs are enabled in Google Cloud Console
3. Ensure billing is enabled for your project

### "Too many requests" or rate limiting errors
- Reduce `MAX_CONCURRENT_REQUESTS` in `.env` (try 5 instead of 10)
- Check your Google Cloud quota limits

### Claude Desktop not showing tools
1. Verify the config file path is correct
2. Check JSON syntax (no trailing commas)
3. Ensure the path to the project is absolute, not relative
4. Check logs: `tail -f ~/Library/Logs/Claude/mcp*.log` (macOS)
5. Restart Claude Desktop completely

### No results found
1. Check that `radius_meters` isn't too small (try 2000-5000)
2. Verify `feature_type` is a valid Google place type
3. Try broader types (e.g., "restaurant" instead of "sushi_restaurant")

## Development

### Running Tests

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=batch_nearby_search --cov-report=html
```

### Code Formatting

```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/
```

## Architecture

### Project Structure

```
batch-nearby-search-mcp/
├── src/batch_nearby_search/
│   ├── server.py          # FastMCP server with @mcp.tool decorators
│   ├── models.py          # Pydantic models for validation
│   ├── google_client.py   # Google API wrapper (async + caching)
│   ├── cache.py           # Two-tier caching (LRU + TTL)
│   └── utils.py           # Helper functions
├── tests/                 # Test suite
├── IMPL_PLAN.md          # Detailed implementation plan
├── CLAUDE.md             # Quick reference for AI assistants
└── README.md             # This file
```

### Key Design Patterns

1. **Concurrent API Calls**: Uses `asyncio.gather()` to parallelize requests
2. **Rate Limiting**: Semaphore-based to respect Google API quotas
3. **Two-Tier Caching**:
   - Geocoding cache (LRU, indefinite) - addresses don't change
   - Places cache (TTL, 1 hour) - places may change over time
4. **Partial Failure Handling**: Returns successful results even if some locations fail
5. **Optional Field Selection**: Reduces response size and API costs

## License

MIT

## Contributing

Contributions welcome! Please open an issue or pull request.

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review logs in `~/Library/Logs/Claude/mcp*.log` (macOS)
3. Open an issue on GitHub

## Acknowledgments

Built with:
- [FastMCP](https://github.com/jlowin/fastmcp) - High-level MCP framework
- [Google Maps Python Client](https://github.com/googlemaps/google-maps-services-python)
- [Pydantic](https://docs.pydantic.dev/) - Data validation

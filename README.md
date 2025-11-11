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

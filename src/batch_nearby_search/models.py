"""
Pydantic models for batch nearby search MCP server.

These models define the structure of inputs and outputs for all MCP tools,
with automatic validation and schema generation.
"""

from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class Location(BaseModel):
    """
    Flexible location input - can be either an address string OR coordinates.

    Examples:
        - Address: Location(address="1600 Amphitheatre Parkway, Mountain View, CA")
        - Coordinates: Location(lat=37.4220, lng=-122.0841)
    """

    address: str | None = Field(None, description="Street address or place name")
    lat: float | None = Field(None, ge=-90, le=90, description="Latitude (-90 to 90)")
    lng: float | None = Field(None, ge=-180, le=180, description="Longitude (-180 to 180)")

    @model_validator(mode="after")
    def check_location_provided(self):
        """Ensure either address or coordinates are provided"""
        if not self.address and not (self.lat is not None and self.lng is not None):
            raise ValueError("Must provide either 'address' or both 'lat' and 'lng'")
        if self.address and (self.lat is not None or self.lng is not None):
            raise ValueError("Provide either 'address' OR coordinates, not both")
        return self


class PlaceResult(BaseModel):
    """
    Standardized place result from Google Places API.

    Always includes: name, distance, place_id
    Optional fields based on include_fields parameter.
    """

    # Always included (minimal fields)
    name: str = Field(..., description="Name of the place")
    distance_meters: float | None = Field(None, description="Distance from origin in meters")
    place_id: str = Field(..., description="Google Place ID for detailed lookups")

    # Optional fields (included based on include_fields parameter)
    rating: float | None = Field(None, ge=0, le=5, description="Average rating (0-5)")
    user_ratings_total: int | None = Field(None, ge=0, description="Total number of ratings")
    address: str | None = Field(None, description="Formatted address or vicinity")
    phone_number: str | None = Field(None, description="Formatted phone number")
    website: str | None = Field(None, description="Website URL")
    price_level: int | None = Field(None, ge=0, le=4, description="Price level (0-4, 4=expensive)")
    opening_hours: dict | None = Field(None, description="Opening hours information")
    types: list[str] | None = Field(None, description="List of place types")

    class Config:
        extra = "allow"  # Allow additional fields from Google API if needed


class DistanceMatrixResult(BaseModel):
    """Result for a single origin-destination pair in distance matrix"""

    origin: str = Field(..., description="Origin address or coordinates")
    destination: str = Field(..., description="Destination address or coordinates")
    distance_meters: int | None = Field(None, description="Distance in meters")
    duration_seconds: int | None = Field(None, description="Travel duration in seconds")
    status: str = Field(..., description="Status: OK, NOT_FOUND, ZERO_RESULTS, etc.")


class NearbySearchRequest(BaseModel):
    """Request model for single-location nearby search"""

    location: Location = Field(..., description="Search origin (address or coordinates)")
    feature_types: list[str] = Field(
        ..., min_length=1, max_length=10, description="Place types to search for"
    )
    radius_meters: int = Field(
        5000, ge=100, le=50000, description="Search radius in meters (100m - 50km)"
    )
    max_results_per_type: int = Field(
        3, ge=1, le=10, description="Maximum results per feature type"
    )
    include_fields: list[str] | None = Field(
        None,
        description="Optional fields to include: rating, address, phone_number, website, etc.",
    )

    @field_validator("feature_types")
    @classmethod
    def validate_feature_types(cls, v):
        """Ensure feature types are lowercase and non-empty"""
        return [ft.lower().strip() for ft in v if ft.strip()]


class BatchNearbySearchRequest(BaseModel):
    """Request model for batch nearby search across multiple locations"""

    locations: list[Location] = Field(
        ..., min_length=1, max_length=20, description="List of search origins (max 20)"
    )
    feature_types: list[str] = Field(
        ..., min_length=1, max_length=10, description="Place types to search for"
    )
    radius_meters: int = Field(
        5000, ge=100, le=50000, description="Search radius in meters (100m - 50km)"
    )
    max_results_per_type: int = Field(
        3, ge=1, le=10, description="Maximum results per feature type"
    )
    include_fields: list[str] | None = Field(
        None,
        description="Optional fields to include: rating, address, phone_number, website, etc.",
    )

    @field_validator("feature_types")
    @classmethod
    def validate_feature_types(cls, v):
        """Ensure feature types are lowercase and non-empty"""
        return [ft.lower().strip() for ft in v if ft.strip()]


class LocationSearchResult(BaseModel):
    """Results for a single location in batch search"""

    location_index: int = Field(..., description="Index in the original locations list")
    location: Location = Field(..., description="Original location query")
    coordinates: dict | None = Field(
        None, description="Resolved coordinates {lat, lng} if geocoded"
    )
    features: dict[str, list[PlaceResult]] = Field(
        ..., description="Results grouped by feature type"
    )
    status: Literal["success", "error", "partial"] = Field(..., description="Search status")
    error: str | None = Field(None, description="Error message if status is error")


class BatchSearchSummary(BaseModel):
    """Summary statistics for batch search operation"""

    total_locations: int = Field(..., description="Total locations searched")
    successful: int = Field(..., description="Locations with successful results")
    failed: int = Field(..., description="Locations that failed completely")
    partial: int = Field(..., description="Locations with partial results")
    total_places_found: int = Field(..., description="Total places found across all locations")
    total_api_calls: int = Field(..., description="Total Google API calls made")
    cache_hits: int = Field(0, description="Number of cache hits (saved API calls)")


class BatchNearbySearchResponse(BaseModel):
    """Complete response for batch nearby search"""

    results: list[LocationSearchResult] = Field(..., description="Results per location")
    summary: BatchSearchSummary = Field(..., description="Summary statistics")


# Available field names for include_fields parameter
AVAILABLE_FIELDS = [
    "rating",
    "user_ratings_total",
    "address",
    "phone_number",
    "website",
    "price_level",
    "opening_hours",
    "types",
]

# Common Google place types for reference
COMMON_PLACE_TYPES = [
    # Amenities
    "park",
    "gym",
    "library",
    "hospital",
    "pharmacy",
    "dentist",
    # Food & Drink
    "restaurant",
    "cafe",
    "bar",
    "grocery_store",
    "supermarket",
    "bakery",
    # Transit
    "bus_station",
    "subway_station",
    "train_station",
    "airport",
    # Services
    "atm",
    "bank",
    "gas_station",
    "car_wash",
    "post_office",
    # Education
    "school",
    "university",
    # Entertainment
    "movie_theater",
    "museum",
    "shopping_mall",
    "stadium",
]

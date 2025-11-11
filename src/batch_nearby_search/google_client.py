"""
Google Maps API client wrapper with async support, caching, and rate limiting.

Now uses the NEW Google Places API (places.googleapis.com/v1) for nearby searches,
which supports modern place types like "fast_food_restaurant", "grocery_store", etc.
"""

import asyncio
import os
from typing import Any
import googlemaps
import httpx
from googlemaps.exceptions import ApiError, Timeout, TransportError

from .cache import (
    get_geocoding_cache,
    set_geocoding_cache,
    get_places_cache,
    set_places_cache,
)
from .utils import calculate_distance, normalize_place_type


class GooglePlacesClient:
    """
    Async wrapper around Google Maps API client with built-in:
    - Rate limiting (semaphore-based)
    - Caching (geocoding and places)
    - Error handling and retries

    Uses NEW Places API for nearby searches and legacy API for geocoding.
    """

    def __init__(self, api_key: str | None = None, max_concurrent: int = 10):
        """
        Initialize the Google Places client.

        Args:
            api_key: Google Maps API key (or read from GOOGLE_MAPS_API_KEY env var)
            max_concurrent: Maximum concurrent API requests (default 10)
        """
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
        if not self.api_key:
            raise ValueError("Google Maps API key required (set GOOGLE_MAPS_API_KEY env var)")

        # Legacy client for geocoding and distance matrix
        self.client = googlemaps.Client(key=self.api_key)

        # HTTP client for new Places API
        self.http_client = httpx.AsyncClient()

        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.api_call_count = 0

        # New Places API endpoint
        self.places_api_url = "https://places.googleapis.com/v1/places:searchNearby"

    async def _rate_limited_call(self, func, *args, **kwargs):
        """
        Execute a function with rate limiting.

        Args:
            func: Function to call
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Result of the function call
        """
        async with self.semaphore:
            loop = asyncio.get_event_loop()
            self.api_call_count += 1
            return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def geocode_location(self, address: str) -> dict:
        """
        Geocode an address to coordinates with caching.

        Args:
            address: Address string to geocode

        Returns:
            Dict with {lat, lng, formatted_address}

        Raises:
            ValueError: If geocoding fails or address not found
        """
        # Check cache first
        cached = get_geocoding_cache(address)
        if cached:
            return cached

        # Call Google Geocoding API
        try:
            result = await self._rate_limited_call(self.client.geocode, address)
            if not result:
                raise ValueError(f"Address not found: {address}")

            location = result[0]["geometry"]["location"]
            formatted_address = result[0]["formatted_address"]

            coords = {"lat": location["lat"], "lng": location["lng"], "formatted_address": formatted_address}

            # Cache the result
            set_geocoding_cache(address, coords)

            return coords

        except (ApiError, Timeout, TransportError) as e:
            raise ValueError(f"Geocoding API error: {str(e)}")

    async def reverse_geocode_location(self, lat: float, lng: float) -> dict:
        """
        Reverse geocode coordinates to address with caching.

        Args:
            lat: Latitude
            lng: Longitude

        Returns:
            Dict with {formatted_address, lat, lng, place_id, address_components}

        Raises:
            ValueError: If reverse geocoding fails or coordinates invalid
        """
        from .cache import get_reverse_geocoding_cache, set_reverse_geocoding_cache

        # Check cache first
        cached = get_reverse_geocoding_cache(lat, lng)
        if cached:
            return cached

        # Call Google Geocoding API with latlng parameter
        try:
            latlng = f"{lat},{lng}"
            result = await self._rate_limited_call(self.client.reverse_geocode, (lat, lng))

            if not result:
                raise ValueError(f"No address found for coordinates: ({lat}, {lng})")

            # Get the first (most specific) result
            first_result = result[0]
            formatted_address = first_result["formatted_address"]
            place_id = first_result.get("place_id")
            address_components = first_result.get("address_components", [])

            response = {
                "lat": lat,
                "lng": lng,
                "formatted_address": formatted_address,
                "place_id": place_id,
                "address_components": address_components,
            }

            # Cache the result
            set_reverse_geocoding_cache(lat, lng, response)

            return response

        except (ApiError, Timeout, TransportError) as e:
            raise ValueError(f"Reverse geocoding API error: {str(e)}")

    async def nearby_search(
        self,
        lat: float,
        lng: float,
        feature_type: str,
        radius: int = 5000,
        max_results: int = 3,
    ) -> list[dict]:
        """
        Search for nearby places of a specific type with caching.

        Uses the NEW Google Places API (places.googleapis.com/v1) which supports
        modern place types like "fast_food_restaurant", "grocery_store", etc.

        Args:
            lat: Latitude
            lng: Longitude
            feature_type: Place type (e.g., "park", "fast_food_restaurant", "grocery_store")
            radius: Search radius in meters
            max_results: Maximum number of results to return (1-20)

        Returns:
            List of place dicts with distance_meters added
        """
        # Normalize feature type
        feature_type = normalize_place_type(feature_type)

        # Check cache first
        cached = get_places_cache(lat, lng, feature_type, radius)
        if cached:
            return cached[:max_results]

        # Call NEW Google Places API (Nearby Search)
        try:
            async with self.semaphore:
                # Build request body for new API
                request_body = {
                    "includedTypes": [feature_type],
                    "maxResultCount": min(max_results, 20),  # API limit is 20
                    "locationRestriction": {
                        "circle": {
                            "center": {
                                "latitude": lat,
                                "longitude": lng
                            },
                            "radius": float(radius)
                        }
                    },
                    "rankPreference": "DISTANCE"  # Sort by distance
                }

                # Set headers
                headers = {
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.nationalPhoneNumber,places.websiteUri,places.priceLevel,places.currentOpeningHours,places.types,places.id"
                }

                # Make POST request
                response = await self.http_client.post(
                    self.places_api_url,
                    json=request_body,
                    headers=headers,
                    timeout=30.0
                )

                self.api_call_count += 1

                # Check for errors
                if response.status_code != 200:
                    error_detail = response.text
                    raise ValueError(f"Places API error ({response.status_code}): {error_detail}")

                result = response.json()
                places_raw = result.get("places", [])

                # Transform new API response to legacy format for compatibility
                places = []
                for place_data in places_raw:
                    # Extract location
                    location = place_data.get("location", {})
                    place_lat = location.get("latitude")
                    place_lng = location.get("longitude")

                    if place_lat is None or place_lng is None:
                        continue

                    # Calculate distance
                    distance = calculate_distance(lat, lng, place_lat, place_lng)

                    # Transform to legacy-compatible format
                    transformed_place = {
                        "name": place_data.get("displayName", {}).get("text", "Unknown"),
                        "place_id": place_data.get("id", "").replace("places/", ""),  # Strip prefix
                        "geometry": {
                            "location": {
                                "lat": place_lat,
                                "lng": place_lng
                            }
                        },
                        "distance_meters": distance,
                        "vicinity": place_data.get("formattedAddress", ""),
                        "rating": place_data.get("rating"),
                        "user_ratings_total": place_data.get("userRatingCount"),
                        "formatted_phone_number": place_data.get("nationalPhoneNumber"),
                        "website": place_data.get("websiteUri"),
                        "price_level": place_data.get("priceLevel"),
                        "opening_hours": place_data.get("currentOpeningHours"),
                        "types": place_data.get("types", [])
                    }

                    places.append(transformed_place)

                # Already sorted by distance due to rankPreference
                # Cache the full results
                set_places_cache(lat, lng, feature_type, radius, places)

                return places[:max_results]

        except httpx.HTTPError as e:
            raise ValueError(f"Places API HTTP error for {feature_type}: {str(e)}")
        except Exception as e:
            raise ValueError(f"Places API error for {feature_type}: {str(e)}")

    async def batch_nearby_search(
        self,
        locations: list[dict],
        feature_types: list[str],
        radius: int = 5000,
        max_results_per_type: int = 3,
    ) -> list[dict]:
        """
        Search for nearby places across multiple locations and feature types in parallel.

        Args:
            locations: List of dicts with {lat, lng}
            feature_types: List of place types to search for
            radius: Search radius in meters
            max_results_per_type: Max results per feature type

        Returns:
            List of dicts with {location, feature_type, places, error}
        """
        # Create all tasks
        tasks = []
        task_metadata = []

        for i, location in enumerate(locations):
            for feature_type in feature_types:
                task = self.nearby_search(
                    location["lat"],
                    location["lng"],
                    feature_type,
                    radius,
                    max_results_per_type,
                )
                tasks.append(task)
                task_metadata.append(
                    {
                        "location_index": i,
                        "location": location,
                        "feature_type": feature_type,
                    }
                )

        # Execute all tasks in parallel (with rate limiting via semaphore)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine results with metadata
        combined = []
        for metadata, result in zip(task_metadata, results):
            if isinstance(result, Exception):
                combined.append({**metadata, "places": [], "error": str(result)})
            else:
                combined.append({**metadata, "places": result, "error": None})

        return combined

    async def distance_matrix(
        self,
        origins: list[str],
        destinations: list[str],
        mode: str = "driving",
    ) -> dict:
        """
        Calculate distance matrix between origins and destinations.

        Args:
            origins: List of origin addresses
            destinations: List of destination addresses
            mode: Travel mode (driving, walking, bicycling, transit)

        Returns:
            Dict with rows of distance/duration information
        """
        try:
            result = await self._rate_limited_call(
                self.client.distance_matrix,
                origins=origins,
                destinations=destinations,
                mode=mode,
            )
            return result

        except (ApiError, Timeout, TransportError) as e:
            raise ValueError(f"Distance Matrix API error: {str(e)}")

    def get_api_call_count(self) -> int:
        """Get the number of API calls made in this session"""
        return self.api_call_count

    def reset_api_call_count(self) -> None:
        """Reset the API call counter"""
        self.api_call_count = 0

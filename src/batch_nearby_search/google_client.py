"""
Google Maps API client wrapper with async support, caching, and rate limiting.
"""

import asyncio
import os
from typing import Any
import googlemaps
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

        self.client = googlemaps.Client(key=self.api_key)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.api_call_count = 0

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

    async def nearby_search(
        self,
        lat: float,
        lng: float,
        feature_type: str,
        radius: int = 1500,
        max_results: int = 3,
    ) -> list[dict]:
        """
        Search for nearby places of a specific type with caching.

        Args:
            lat: Latitude
            lng: Longitude
            feature_type: Place type (e.g., "park", "restaurant")
            radius: Search radius in meters
            max_results: Maximum number of results to return

        Returns:
            List of place dicts with distance_meters added
        """
        # Normalize feature type
        feature_type = normalize_place_type(feature_type)

        # Check cache first
        cached = get_places_cache(lat, lng, feature_type, radius)
        if cached:
            return cached[:max_results]

        # Call Google Places API (Nearby Search)
        try:
            result = await self._rate_limited_call(
                self.client.places_nearby,
                location=(lat, lng),
                radius=radius,
                type=feature_type,
            )

            places = result.get("results", [])

            # Calculate and add distance to each place
            for place in places:
                place_lat = place["geometry"]["location"]["lat"]
                place_lng = place["geometry"]["location"]["lng"]
                place["distance_meters"] = calculate_distance(lat, lng, place_lat, place_lng)

            # Sort by distance
            places.sort(key=lambda p: p.get("distance_meters", float("inf")))

            # Cache the full results
            set_places_cache(lat, lng, feature_type, radius, places)

            return places[:max_results]

        except (ApiError, Timeout, TransportError) as e:
            raise ValueError(f"Places API error for {feature_type}: {str(e)}")

    async def batch_nearby_search(
        self,
        locations: list[dict],
        feature_types: list[str],
        radius: int = 1500,
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

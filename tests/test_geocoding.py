"""
Tests for geocoding functionality
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.batch_nearby_search.google_client import GooglePlacesClient
from src.batch_nearby_search.cache import (
    get_geocoding_cache,
    set_geocoding_cache,
    get_reverse_geocoding_cache,
    set_reverse_geocoding_cache,
    clear_caches,
)


@pytest.fixture
def mock_google_client():
    """Create a mock Google client for testing"""
    with patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY': 'test_key'}):
        client = GooglePlacesClient(api_key='test_key', max_concurrent=5)
        yield client


@pytest.fixture(autouse=True)
def clear_cache_before_test():
    """Clear caches before each test"""
    clear_caches()
    yield
    clear_caches()


def test_geocoding_cache():
    """Test geocoding cache functionality"""
    address = "1600 Amphitheatre Parkway, Mountain View, CA"
    coords = {"lat": 37.4220, "lng": -122.0841, "formatted_address": "Test Address"}

    # Should be None initially
    assert get_geocoding_cache(address) is None

    # Set cache
    set_geocoding_cache(address, coords)

    # Should retrieve from cache
    cached = get_geocoding_cache(address)
    assert cached is not None
    assert cached["lat"] == 37.4220
    assert cached["lng"] == -122.0841


def test_reverse_geocoding_cache():
    """Test reverse geocoding cache functionality"""
    lat = 37.4220
    lng = -122.0841
    address_data = {
        "lat": lat,
        "lng": lng,
        "formatted_address": "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA",
        "place_id": "test_place_id",
    }

    # Should be None initially
    assert get_reverse_geocoding_cache(lat, lng) is None

    # Set cache
    set_reverse_geocoding_cache(lat, lng, address_data)

    # Should retrieve from cache
    cached = get_reverse_geocoding_cache(lat, lng)
    assert cached is not None
    assert cached["formatted_address"] == address_data["formatted_address"]
    assert cached["lat"] == lat
    assert cached["lng"] == lng


def test_reverse_geocoding_cache_rounding():
    """Test that reverse geocoding cache rounds coordinates properly"""
    # These coordinates should round to the same cache key
    lat1, lng1 = 37.42201, -122.08411
    lat2, lng2 = 37.42204, -122.08414

    address_data = {
        "lat": lat1,
        "lng": lng1,
        "formatted_address": "Test Address",
    }

    # Set cache with first coordinates
    set_reverse_geocoding_cache(lat1, lng1, address_data)

    # Should retrieve with slightly different coordinates (within rounding)
    cached = get_reverse_geocoding_cache(lat2, lng2)
    assert cached is not None
    assert cached["formatted_address"] == "Test Address"


@pytest.mark.asyncio
async def test_reverse_geocode_location_with_mock():
    """Test reverse_geocode_location method with mocked Google API"""
    with patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY': 'test_key'}):
        client = GooglePlacesClient(api_key='test_key', max_concurrent=5)

        # Mock the reverse_geocode API call
        mock_result = [{
            "formatted_address": "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA",
            "place_id": "ChIJ2eUgeAK6j4ARbn5u_wAGqWA",
            "address_components": [
                {"long_name": "1600", "short_name": "1600", "types": ["street_number"]},
                {"long_name": "Amphitheatre Parkway", "short_name": "Amphitheatre Pkwy", "types": ["route"]},
            ],
        }]

        with patch.object(client.client, 'reverse_geocode', return_value=mock_result):
            result = await client.reverse_geocode_location(37.4220, -122.0841)

            assert result is not None
            assert result["lat"] == 37.4220
            assert result["lng"] == -122.0841
            assert result["formatted_address"] == "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA"
            assert result["place_id"] == "ChIJ2eUgeAK6j4ARbn5u_wAGqWA"
            assert len(result["address_components"]) == 2


@pytest.mark.asyncio
async def test_reverse_geocode_location_caching():
    """Test that reverse geocoding results are cached"""
    with patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY': 'test_key'}):
        client = GooglePlacesClient(api_key='test_key', max_concurrent=5)

        mock_result = [{
            "formatted_address": "Test Address",
            "place_id": "test_place_id",
            "address_components": [],
        }]

        with patch.object(client.client, 'reverse_geocode', return_value=mock_result) as mock_reverse_geocode:
            # First call should hit the API
            result1 = await client.reverse_geocode_location(37.4220, -122.0841)
            assert mock_reverse_geocode.call_count == 1

            # Second call should use cache
            result2 = await client.reverse_geocode_location(37.4220, -122.0841)
            assert mock_reverse_geocode.call_count == 1  # Still 1, not 2

            # Results should be the same
            assert result1["formatted_address"] == result2["formatted_address"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

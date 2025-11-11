"""
Google Places API place types organized by category.

Based on: https://developers.google.com/maps/documentation/places/web-service/place-types

This module provides:
- Comprehensive list of all valid Google Place types
- Organization by category for easier discovery
- Fuzzy matching for suggesting corrections to invalid types
"""

from difflib import get_close_matches

# Google Place Types organized by category (Table A - Primary & Filterable Types)
PLACE_TYPES_BY_CATEGORY = {
    "automotive": [
        "car_dealer",
        "car_rental",
        "car_repair",
        "car_wash",
        "electric_vehicle_charging_station",
        "gas_station",
        "parking",
        "rest_stop",
    ],
    "business": [
        "corporate_office",
        "farm",
        "ranch",
    ],
    "culture": [
        "art_gallery",
        "art_studio",
        "auditorium",
        "cultural_landmark",
        "historical_place",
        "monument",
        "museum",
        "performing_arts_theater",
        "sculpture",
    ],
    "education": [
        "library",
        "preschool",
        "primary_school",
        "school",
        "secondary_school",
        "university",
    ],
    "entertainment_recreation": [
        "amusement_center",
        "amusement_park",
        "aquarium",
        "banquet_hall",
        "bowling_alley",
        "casino",
        "community_center",
        "convention_center",
        "cultural_center",
        "dog_park",
        "event_venue",
        "hiking_area",
        "historical_landmark",
        "marina",
        "movie_rental",
        "movie_theater",
        "national_park",
        "night_club",
        "park",
        "tourist_attraction",
        "visitor_center",
        "wedding_venue",
        "zoo",
    ],
    "facilities": [
        "public_bath",
        "public_bathroom",
        "stable",
    ],
    "finance": [
        "accounting",
        "atm",
        "bank",
    ],
    "food_drink": [
        "american_restaurant",
        "bakery",
        "bar",
        "barbecue_restaurant",
        "brazilian_restaurant",
        "breakfast_restaurant",
        "brunch_restaurant",
        "cafe",
        "chinese_restaurant",
        "coffee_shop",
        "fast_food_restaurant",
        "french_restaurant",
        "greek_restaurant",
        "hamburger_restaurant",
        "ice_cream_shop",
        "indian_restaurant",
        "indonesian_restaurant",
        "italian_restaurant",
        "japanese_restaurant",
        "korean_restaurant",
        "lebanese_restaurant",
        "meal_delivery",
        "meal_takeaway",
        "mediterranean_restaurant",
        "mexican_restaurant",
        "middle_eastern_restaurant",
        "pizza_restaurant",
        "ramen_restaurant",
        "restaurant",
        "sandwich_shop",
        "seafood_restaurant",
        "spanish_restaurant",
        "steak_house",
        "sushi_restaurant",
        "thai_restaurant",
        "turkish_restaurant",
        "vegan_restaurant",
        "vegetarian_restaurant",
        "vietnamese_restaurant",
    ],
    "government": [
        "city_hall",
        "courthouse",
        "embassy",
        "fire_station",
        "local_government_office",
        "police",
        "post_office",
    ],
    "health_wellness": [
        "dental_clinic",
        "dentist",
        "doctor",
        "drugstore",
        "hospital",
        "medical_lab",
        "pharmacy",
        "physiotherapist",
        "spa",
    ],
    "lodging": [
        "bed_and_breakfast",
        "campground",
        "camping_cabin",
        "cottage",
        "extended_stay_hotel",
        "farmstay",
        "guest_house",
        "hostel",
        "hotel",
        "lodging",
        "motel",
        "private_guest_room",
        "resort_hotel",
        "rv_park",
    ],
    "places_of_worship": [
        "church",
        "hindu_temple",
        "mosque",
        "synagogue",
    ],
    "services": [
        "barber_shop",
        "beauty_salon",
        "cemetery",
        "child_care_agency",
        "consultant",
        "courier_service",
        "electrician",
        "florist",
        "funeral_home",
        "hair_care",
        "hair_salon",
        "insurance_agency",
        "laundry",
        "lawyer",
        "locksmith",
        "moving_company",
        "painter",
        "plumber",
        "real_estate_agency",
        "roofing_contractor",
        "storage",
        "tailor",
        "telecommunications_service_provider",
        "travel_agency",
        "veterinary_care",
    ],
    "shopping": [
        "auto_parts_store",
        "bicycle_store",
        "book_store",
        "cell_phone_store",
        "clothing_store",
        "convenience_store",
        "department_store",
        "discount_store",
        "electronics_store",
        "furniture_store",
        "gift_shop",
        "grocery_store",
        "hardware_store",
        "home_goods_store",
        "home_improvement_store",
        "jewelry_store",
        "liquor_store",
        "market",
        "pet_store",
        "shoe_store",
        "shopping_mall",
        "sporting_goods_store",
        "store",
        "supermarket",
        "wholesaler",
    ],
    "sports": [
        "athletic_field",
        "fitness_center",
        "golf_course",
        "gym",
        "playground",
        "ski_resort",
        "sports_club",
        "sports_complex",
        "stadium",
        "swimming_pool",
    ],
    "transportation": [
        "airport",
        "bus_station",
        "bus_stop",
        "ferry_terminal",
        "heliport",
        "light_rail_station",
        "park_and_ride",
        "subway_station",
        "taxi_stand",
        "train_station",
        "transit_depot",
        "transit_station",
        "truck_stop",
    ],
}

# Flatten all types for validation and fuzzy matching
ALL_PLACE_TYPES = set()
for types in PLACE_TYPES_BY_CATEGORY.values():
    ALL_PLACE_TYPES.update(types)

# Convert to sorted list for consistent ordering
ALL_PLACE_TYPES = sorted(ALL_PLACE_TYPES)


def suggest_place_types(invalid_type: str, max_suggestions: int = 5) -> list[str]:
    """
    Find similar valid place types using fuzzy matching.

    Args:
        invalid_type: The invalid place type to match against
        max_suggestions: Maximum number of suggestions to return (default 5)

    Returns:
        List of similar valid place types, ordered by similarity

    Example:
        >>> suggest_place_types("restraunt")
        ['restaurant', 'fast_food_restaurant', 'american_restaurant']

        >>> suggest_place_types("coffee")
        ['coffee_shop', 'cafe']
    """
    # Normalize input
    invalid_type = invalid_type.lower().strip()

    # Try exact match first
    if invalid_type in ALL_PLACE_TYPES:
        return [invalid_type]

    # Fuzzy match with 60% similarity threshold
    suggestions = get_close_matches(
        invalid_type,
        ALL_PLACE_TYPES,
        n=max_suggestions,
        cutoff=0.6
    )

    return suggestions


def validate_place_types(place_types: list[str]) -> dict:
    """
    Validate a list of place types and return validation results.

    Also supports category names - if a category name is provided (e.g., "food_drink"),
    it will be expanded to all place types in that category.

    Args:
        place_types: List of place types or category names to validate

    Returns:
        Dictionary with:
        - valid: List of valid place types (with categories expanded)
        - invalid: List of invalid place types
        - suggestions: Dict mapping invalid types to suggested corrections
        - all_valid: Boolean indicating if all types are valid

    Example:
        >>> validate_place_types(["park", "restraunt", "gym"])
        {
            "valid": ["park", "gym"],
            "invalid": ["restraunt"],
            "suggestions": {"restraunt": ["restaurant", "fast_food_restaurant"]},
            "all_valid": False
        }

        >>> validate_place_types(["food_drink"])
        {
            "valid": ["restaurant", "cafe", "bar", ...],  # All food_drink types
            "invalid": [],
            "suggestions": {},
            "all_valid": True
        }
    """
    valid = []
    invalid = []
    suggestions = {}

    for place_type in place_types:
        normalized = place_type.lower().strip()

        # Check if it's a valid place type
        if normalized in ALL_PLACE_TYPES:
            valid.append(normalized)
        # Check if it's a category name
        elif normalized in PLACE_TYPES_BY_CATEGORY:
            # Expand category to all its types
            valid.extend(PLACE_TYPES_BY_CATEGORY[normalized])
        else:
            invalid.append(place_type)
            type_suggestions = suggest_place_types(normalized)
            if type_suggestions:
                suggestions[place_type] = type_suggestions

    return {
        "valid": valid,
        "invalid": invalid,
        "suggestions": suggestions,
        "all_valid": len(invalid) == 0,
    }


def get_category_for_type(place_type: str) -> str | None:
    """
    Get the category for a given place type.

    Args:
        place_type: The place type to lookup

    Returns:
        Category name or None if not found

    Example:
        >>> get_category_for_type("restaurant")
        'food_drink'

        >>> get_category_for_type("park")
        'entertainment_recreation'
    """
    place_type = place_type.lower().strip()

    for category, types in PLACE_TYPES_BY_CATEGORY.items():
        if place_type in types:
            return category

    return None

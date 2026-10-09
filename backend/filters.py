"""Shared filtering logic for hackathons and subscriber preferences."""

import re

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
    "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
}


def is_us_location(location: str) -> bool:
    if not location:
        return False
    return any(part in US_STATES for part in re.split(r"[\s,]+", location))


def _hackathon_field(hackathon, key: str, default=None):
    if isinstance(hackathon, dict):
        return hackathon.get(key, default)
    return getattr(hackathon, key, default)


def matches_subscriber(hackathon, subscriber) -> bool:
    region = _hackathon_field(subscriber, "region", "all")
    in_person_only = _hackathon_field(subscriber, "in_person_only", False)
    location = _hackathon_field(hackathon, "location", "")
    format_type = _hackathon_field(hackathon, "format_type", "in_person")

    if region == "us" and not is_us_location(location):
        return False
    if region == "intl" and is_us_location(location):
        return False
    if in_person_only and format_type != "in_person":
        return False
    return True


def preference_summary(region: str, in_person_only: bool) -> str:
    region_labels = {"all": "all regions", "us": "US", "intl": "international"}
    parts = [region_labels.get(region, "all regions")]
    if in_person_only:
        parts.append("in-person only")
    return " and ".join(parts)

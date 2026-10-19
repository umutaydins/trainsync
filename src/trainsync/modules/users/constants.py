"""Emergency numbers by country for the distress reply (ADR 0032, 0036). Anything not listed
uses `EMERGENCY_NUMBER`. Sources: national emergency services; 112 also works across the EU."""

from collections.abc import Mapping

EMERGENCY_NUMBERS: Mapping[str, str] = {
    "AU": "000",
    "BR": "190",
    "CA": "911",
    "CN": "110",
    "GB": "999",
    "IE": "112",
    "IN": "112",
    "JP": "110",
    "MX": "911",
    "NZ": "111",
    "TR": "112",
    "US": "911",
    "ZA": "10111",
}

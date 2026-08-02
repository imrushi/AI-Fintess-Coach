"""Utilities for fetching and parsing Garmin HR time-in-zone data."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ingestion.garmin_client import GarminClient

logger = logging.getLogger(__name__)


def parse_zone_response(raw) -> tuple[dict, dict] | None:
    """Parse a Garmin hrTimeInZones response.

    Handles two formats:
    - List: [{"zoneNumber": 1, "secsInZone": 120.0, "zoneLowBoundary": 101}, ...]
    - Dict: {"heartRateZones": [{"zone": 1, "secsInZone": 120.0, ...}, ...]}

    Returns (secs_map, thresholds_map) with string keys "1"–"5", or None if
    the response is absent or malformed.

    secs_map:       {"1": 120.0, "2": 450.0, ...}
    thresholds_map: {"1": {"low": 101, "high": 120}, ...}
    """
    if not raw:
        return None

    # Normalise to a list of zone entries
    if isinstance(raw, list):
        zones = raw
    elif isinstance(raw, dict):
        zones = raw.get("heartRateZones")
        if not zones or not isinstance(zones, list):
            return None
    else:
        return None

    secs_map: dict[str, float] = {}
    low_by_key: dict[str, int] = {}

    for entry in zones:
        if not isinstance(entry, dict):
            continue
        # Support both "zoneNumber" (list format) and "zone" (dict format)
        zone_num = entry.get("zoneNumber") or entry.get("zone")
        secs = entry.get("secsInZone")
        if zone_num is None or secs is None:
            continue
        key = str(int(zone_num))
        secs_map[key] = float(secs)
        low = entry.get("zoneLowBoundary")
        if low is not None:
            low_by_key[key] = int(low)

    if not secs_map:
        return None

    # Build thresholds: high of zone N = low of zone N+1 − 1; Z5 high = 999
    thresholds_map: dict[str, dict] = {}
    sorted_keys = sorted(low_by_key.keys(), key=int)
    for i, key in enumerate(sorted_keys):
        low = low_by_key[key]
        if i + 1 < len(sorted_keys):
            high = low_by_key[sorted_keys[i + 1]] - 1
        else:
            high = 999
        thresholds_map[key] = {"low": low, "high": high}

    # Also handle explicit zoneHighBoundary if present (dict format)
    for entry in zones:
        if not isinstance(entry, dict):
            continue
        zone_num = entry.get("zoneNumber") or entry.get("zone")
        high = entry.get("zoneHighBoundary")
        if zone_num is not None and high is not None:
            key = str(int(zone_num))
            if key in thresholds_map:
                thresholds_map[key]["high"] = int(high)

    return secs_map, thresholds_map


def fetch_zones_for_activities(
    client: "GarminClient",
    activities_json: str | None,
) -> dict[str, dict]:
    """Fetch HR zone data from Garmin for each activity in the JSON list.

    Returns {garmin_activity_id: {"secs": {...}, "thresholds": {...}}}.
    Silently skips activities where the API call fails.
    """
    if not activities_json:
        return {}
    try:
        activities = json.loads(activities_json)
    except (json.JSONDecodeError, TypeError):
        return {}

    result: dict[str, dict] = {}
    for activity in activities:
        garmin_id = str(activity.get("activityId", "")).strip()
        if not garmin_id:
            continue
        try:
            raw = client.get_activity_hr_in_timezones(garmin_id)
            parsed = parse_zone_response(raw)
            if parsed:
                secs, thresholds = parsed
                result[garmin_id] = {"secs": secs, "thresholds": thresholds}
                logger.debug("HR zones fetched for activity %s", garmin_id)
        except Exception as exc:
            logger.warning("Failed to fetch HR zones for activity %s: %s", garmin_id, exc)

    return result

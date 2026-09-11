"""Overpass JSON element -> RawCandidate mapping. Pure transformation, no
network calls, no normalization (phone/email/website/domain normalization
and dedup are out of scope for MLE-003).
"""

import logging
from typing import Any

from app.models.source import SourceType
from sources.osm.tag_mapping import OsmPreset
from sources.schemas import RawCandidate

logger = logging.getLogger("mpua.sources.osm.parser")


def _external_id(element: dict[str, Any]) -> str:
    return f"osm:{element['type']}:{element['id']}"


def _source_url(element: dict[str, Any]) -> str:
    return f"https://www.openstreetmap.org/{element['type']}/{element['id']}"


def _pick_first(tags: dict[str, str], keys: list[str]) -> str | None:
    for key in keys:
        value = tags.get(key)
        if value:
            return value
    return None


def _build_raw_address(tags: dict[str, str]) -> str | None:
    parts = [
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:city"),
        tags.get("addr:postcode"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


def _coordinates(element: dict[str, Any]) -> tuple[float | None, float | None]:
    if element["type"] == "node":
        return element.get("lat"), element.get("lon")

    center = element.get("center") or {}
    return center.get("lat"), center.get("lon")


def element_to_candidate(
    element: dict[str, Any],
    preset: OsmPreset,
    country: str | None,
    region: str | None,
    city: str | None,
) -> RawCandidate | None:
    """Return a validated RawCandidate, or None if the element must be
    dropped (e.g. no name tag).
    """

    tags = element.get("tags") or {}
    name = tags.get("name")

    if not name or not name.strip():
        logger.info(
            "osm parser: dropping element without name tag",
            extra={"external_id": _external_id(element)},
        )
        return None

    lat, lon = _coordinates(element)

    payload = {
        "element": element,
        "matched_preset": preset.key,
    }

    try:
        return RawCandidate(
            external_id=_external_id(element),
            name=name,
            category=preset.label,
            description=tags.get("description"),
            country=country,
            region=region,
            city=city or tags.get("addr:city"),
            raw_address=_build_raw_address(tags),
            phone=_pick_first(tags, ["contact:phone", "phone"]),
            website=_pick_first(tags, ["contact:website", "website"]),
            email=_pick_first(tags, ["contact:email", "email"]),
            rating=None,
            reviews_count=None,
            source_type=SourceType.openstreetmap,
            source_url=_source_url(element),
            raw_payload=payload,
            lat=lat,
            lon=lon,
        )
    except Exception:
        logger.warning(
            "osm parser: candidate failed validation",
            extra={"external_id": _external_id(element)},
            exc_info=True,
        )
        return None


def parse_elements(
    elements: list[dict[str, Any]],
    preset: OsmPreset,
    country: str | None,
    region: str | None,
    city: str | None,
    limit: int,
) -> list[RawCandidate]:
    candidates: list[RawCandidate] = []

    for element in elements:
        if len(candidates) >= limit:
            break

        candidate = element_to_candidate(
            element, preset=preset, country=country, region=region, city=city
        )
        if candidate is not None:
            candidates.append(candidate)

    return candidates

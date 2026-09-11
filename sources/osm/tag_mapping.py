"""Controlled preset -> OSM tag registry.

Only tags that are actually documented/established on the OSM wiki are
mapped here. A preset with no reliable canonical tag is marked
unsupported rather than guessed, per MLE-003 scope.

Sources checked against the OSM tagging wiki (Map Features / Key:shop /
Key:amenity):
  - amenity=dentist   -> standard tag for dental clinics.
  - shop=car_repair   -> standard tag for car repair / garages (a
                          `craft=car_repair` value also exists for
                          craftsperson-style listings, but `shop=car_repair`
                          is the canonical, far more widely used tag, so
                          v0.1 queries that one).
  - shop=car_parts    -> standard tag for auto parts stores.

`hvac` and `construction` have no single canonical, reliably-populated OSM
tag (candidates like `craft=hvac` or `office=construction_company` exist
but are sparsely used / ambiguous), so they are intentionally left
unsupported for v0.1 instead of guessing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OsmPreset:
    key: str
    label: str
    tags: tuple[tuple[str, str], ...]  # (osm_key, osm_value) pairs, OR-ed together
    supported: bool = True
    note: str | None = None


OSM_PRESETS: dict[str, OsmPreset] = {
    "dentist": OsmPreset(
        key="dentist",
        label="Dental clinic",
        tags=(("amenity", "dentist"),),
    ),
    "car_repair": OsmPreset(
        key="car_repair",
        label="Car repair / STO",
        tags=(("shop", "car_repair"),),
    ),
    "car_parts": OsmPreset(
        key="car_parts",
        label="Auto parts store",
        tags=(("shop", "car_parts"),),
    ),
    "hvac": OsmPreset(
        key="hvac",
        label="HVAC",
        tags=(),
        supported=False,
        note="No reliable canonical OSM tag for HVAC contractors in v0.1; not implemented.",
    ),
    "construction": OsmPreset(
        key="construction",
        label="Construction",
        tags=(),
        supported=False,
        note="No single reliable canonical OSM tag for construction companies in v0.1; not implemented.",
    ),
}


def get_preset(key: str) -> OsmPreset:
    try:
        preset = OSM_PRESETS[key]
    except KeyError as exc:
        raise ValueError(f"Unknown OSM preset: {key!r}") from exc

    if not preset.supported:
        raise ValueError(f"OSM preset {key!r} is not supported: {preset.note}")

    return preset

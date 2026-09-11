"""Builds Overpass QL queries for a preset + city/country.

Prefers a bounding-box filter for the known MLE-003 benchmark cities
(sources/osm/cities.py) since it proved far more reliable against the
public Overpass instance than `area["name"=...]` resolution. Falls back
to a nested area-name query for any other city (best-effort; Overpass
returns zero elements rather than erroring if the area can't be found).
"""

from sources.osm.cities import get_benchmark_bbox
from sources.osm.tag_mapping import OsmPreset


def build_area_query(city: str, country: str | None) -> str:
    """Overpass QL fragment resolving `.searchArea` for a city, optionally
    scoped to a country's ISO 3166-1 code.
    """

    safe_city = city.replace('"', '\\"')

    if country:
        safe_country = country.replace('"', '\\"')
        return (
            f'area["ISO3166-1"="{safe_country}"]["admin_level"="2"]->.country;\n'
            f'area["name"="{safe_city}"]["admin_level"~"^(4|6|7|8)$"](area.country)->.searchArea;\n'
        )

    return f'area["name"="{safe_city}"]["admin_level"~"^(4|6|7|8)$"]->.searchArea;\n'


def build_preset_query(
    preset: OsmPreset,
    city: str,
    country: str | None,
    timeout: int = 60,
    output_limit: int | None = None,
) -> str:
    """Build a full Overpass QL query for the given preset within a city,
    covering node/way/relation and returning tags + a center point for
    ways/relations.
    """

    bbox = get_benchmark_bbox(city)

    clauses = []
    for osm_key, osm_value in preset.tags:
        for element in ("node", "way", "relation"):
            if bbox is not None:
                south, west, north, east = bbox
                clauses.append(
                    f'  {element}["{osm_key}"="{osm_value}"]({south},{west},{north},{east});'
                )
            else:
                clauses.append(f'  {element}["{osm_key}"="{osm_value}"](area.searchArea);')

    body = "\n".join(clauses)

    out_clause = "out center tags;"
    if output_limit:
        out_clause = f"out center tags {int(output_limit)};"

    area_fragment = "" if bbox is not None else build_area_query(city=city, country=country)

    return (
        f"[out:json][timeout:{int(timeout)}];\n"
        f"{area_fragment}"
        "(\n"
        f"{body}\n"
        ");\n"
        f"{out_clause}\n"
    )

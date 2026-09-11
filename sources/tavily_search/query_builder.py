"""Controlled preset -> search-query-variant registry, mirroring the OSM
preset registry's philosophy: a small, curated set rather than arbitrary
free text.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TavilyPreset:
    key: str
    query_templates: tuple[str, ...]  # "{region}" is substituted


TAVILY_PRESETS: dict[str, TavilyPreset] = {
    "dentist": TavilyPreset(
        key="dentist",
        query_templates=(
            "стоматологія {region}",
            "стоматологічна клініка {region}",
        ),
    ),
    "car_repair": TavilyPreset(
        key="car_repair",
        query_templates=(
            "СТО {region}",
            "автосервіс {region}",
        ),
    ),
    "car_parts": TavilyPreset(
        key="car_parts",
        query_templates=(
            "магазин автозапчастин {region}",
            "автозапчастини {region}",
        ),
    ),
    "hvac": TavilyPreset(
        key="hvac",
        query_templates=(
            "монтаж кондиціонерів {region}",
            "вентиляція та кондиціонування {region}",
        ),
    ),
}


def get_preset(key: str) -> TavilyPreset:
    try:
        return TAVILY_PRESETS[key]
    except KeyError as exc:
        raise ValueError(f"Unknown Tavily Search preset: {key!r}") from exc


def build_query_variants(preset_key: str, region: str | None) -> list[str]:
    preset = get_preset(preset_key)
    region_part = region or ""
    return [template.format(region=region_part).strip() for template in preset.query_templates]

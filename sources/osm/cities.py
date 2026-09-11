"""Static bounding-box fixture for the MLE-003 benchmark cities.

Overpass `area["name"=...]` resolution proved unreliable against the
public instance during development (empty/degraded results even for
well-known cities such as Kyiv), so for these five benchmark cities we
query by bounding box instead, which Overpass handles efficiently and
reliably. Any other city falls back to name-based area resolution in
query_builder.py (best-effort; may return 0 results if resolution fails,
which is not treated as an error per MLE-003 scope).

Boxes are approximate city-extent rectangles (south, west, north, east)
for coverage/dev-testing purposes only — not authoritative administrative
boundaries. This is a data fixture, not business logic: adapters/parsers
never hardcode coordinates directly.
"""

BenchmarkBBox = tuple[float, float, float, float]

BENCHMARK_CITY_BBOXES: dict[str, BenchmarkBBox] = {
    "dnipro": (48.35, 34.90, 48.55, 35.25),
    "kyiv": (50.20, 30.24, 50.65, 30.83),
    "lviv": (49.75, 23.85, 49.90, 24.15),
    "odesa": (46.35, 30.55, 46.55, 30.85),
    "vinnytsia": (49.15, 28.35, 49.28, 28.60),
}


def get_benchmark_bbox(city: str) -> BenchmarkBBox | None:
    return BENCHMARK_CITY_BBOXES.get(city.strip().lower())

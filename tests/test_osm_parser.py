import json
from pathlib import Path

from app.models.source import SourceType
from sources.osm.parser import element_to_candidate, parse_elements
from sources.osm.tag_mapping import get_preset

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "osm_overpass_response.json"


def load_elements():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data["elements"]


def test_parser_handles_node():
    elements = load_elements()
    node = elements[0]
    preset = get_preset("dentist")

    candidate = element_to_candidate(node, preset=preset, country="UA", region="Dnipro", city="Dnipro")

    assert candidate is not None
    assert candidate.external_id == "osm:node:111111"
    assert candidate.name == "Dental Studio Dnipro"
    assert candidate.source_type == SourceType.openstreetmap
    assert candidate.source_url == "https://www.openstreetmap.org/node/111111"


def test_parser_handles_way_with_center():
    elements = load_elements()
    way = elements[1]
    preset = get_preset("dentist")

    candidate = element_to_candidate(way, preset=preset, country="UA", region="Dnipro", city="Dnipro")

    assert candidate is not None
    assert candidate.external_id == "osm:way:222222"
    assert candidate.name == "Smile Clinic"


def test_parser_handles_relation():
    elements = load_elements()
    relation = elements[2]
    preset = get_preset("dentist")

    candidate = element_to_candidate(relation, preset=preset, country="UA", region="Dnipro", city="Dnipro")

    assert candidate is not None
    assert candidate.external_id == "osm:relation:333333"
    assert candidate.name == "OrthoDent Group"


def test_contact_phone_has_priority_over_phone():
    elements = load_elements()
    node = elements[0]
    preset = get_preset("dentist")

    candidate = element_to_candidate(node, preset=preset, country="UA", region="Dnipro", city="Dnipro")

    assert candidate.phone == "+380 56 111 22 33"


def test_contact_website_has_priority_over_website():
    elements = load_elements()
    node = elements[0]
    preset = get_preset("dentist")

    candidate = element_to_candidate(node, preset=preset, country="UA", region="Dnipro", city="Dnipro")

    assert candidate.website == "https://dental-studio.example.com"


def test_contact_email_has_priority_over_email():
    elements = load_elements()
    relation = elements[2]
    preset = get_preset("dentist")

    candidate = element_to_candidate(relation, preset=preset, country="UA", region="Dnipro", city="Dnipro")

    assert candidate.email == "info@orthodent.example.com"


def test_raw_address_is_assembled_from_addr_tags():
    elements = load_elements()
    node = elements[0]
    preset = get_preset("dentist")

    candidate = element_to_candidate(node, preset=preset, country="UA", region="Dnipro", city="Dnipro")

    assert candidate.raw_address == "Yavornytskoho Ave, 12, Dnipro, 49000"


def test_element_without_name_is_dropped():
    elements = load_elements()
    unnamed = elements[3]
    preset = get_preset("dentist")

    candidate = element_to_candidate(unnamed, preset=preset, country="UA", region="Dnipro", city="Dnipro")

    assert candidate is None


def test_raw_payload_is_preserved():
    elements = load_elements()
    node = elements[0]
    preset = get_preset("dentist")

    candidate = element_to_candidate(node, preset=preset, country="UA", region="Dnipro", city="Dnipro")

    assert candidate.raw_payload["element"]["id"] == 111111
    assert candidate.raw_payload["element"]["tags"]["name"] == "Dental Studio Dnipro"
    assert candidate.raw_payload["matched_preset"] == "dentist"


def test_parse_elements_respects_limit():
    elements = load_elements()
    preset = get_preset("dentist")

    candidates = parse_elements(
        elements, preset=preset, country="UA", region="Dnipro", city="Dnipro", limit=2
    )

    assert len(candidates) == 2


def test_parse_elements_drops_unnamed_and_keeps_valid_ones():
    elements = load_elements()
    preset = get_preset("dentist")

    candidates = parse_elements(
        elements, preset=preset, country="UA", region="Dnipro", city="Dnipro", limit=10
    )

    # 4 elements total, 1 has no name -> 3 valid candidates
    assert len(candidates) == 3

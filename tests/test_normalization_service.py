import json
from pathlib import Path

from app.models.source import SourceType
from processing.normalization.service import normalize_candidate, normalize_candidates
from sources.osm.parser import parse_elements
from sources.osm.tag_mapping import get_preset
from sources.schemas import RawCandidate

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "osm_overpass_response.json"


def _sample_candidate(**overrides) -> RawCandidate:
    defaults = dict(
        external_id="ext-1",
        name='ТОВ "Клімат-Сервіс"',
        category="HVAC",
        country="UA",
        region="Kyiv",
        city="Київ",
        raw_address="  вул. Хрещатик,   1  ",
        phone="050 123 45 67",
        website="https://www.example.com/contact",
        email="INFO@EXAMPLE.COM",
        rating=4.2,
        reviews_count=10,
        source_type=SourceType.manual,
        source_url="https://mock.local/1",
        raw_payload={"foo": "bar"},
    )
    defaults.update(overrides)
    return RawCandidate(**defaults)


def test_normalize_candidate_does_not_mutate_original():
    candidate = _sample_candidate()
    original_name = candidate.name

    normalize_candidate(candidate)

    assert candidate.name == original_name


def test_normalize_candidate_populates_all_fields():
    candidate = _sample_candidate()
    normalized = normalize_candidate(candidate)

    assert normalized.canonical_name == 'ТОВ "Клімат-Сервіс"'
    assert normalized.normalized_name == "клімат сервіс"
    assert normalized.phone_normalized == "+380501234567"
    assert normalized.email_normalized == "info@example.com"
    assert normalized.website_domain == "example.com"
    assert normalized.normalized_address == "вул. хрещатик 1"
    assert normalized.normalized_city == "київ"
    assert normalized.raw_payload == {"foo": "bar"}


def test_normalize_candidate_is_deterministic():
    candidate = _sample_candidate()

    first = normalize_candidate(candidate)
    second = normalize_candidate(candidate)

    assert first.model_dump() == second.model_dump()


def test_normalize_candidate_never_makes_network_calls(monkeypatch):
    import socket

    def fail(*args, **kwargs):
        raise AssertionError("normalization must not touch the network")

    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(socket, "create_connection", fail)

    normalize_candidate(_sample_candidate())


def test_normalize_candidates_batch_stats():
    candidates = [_sample_candidate(external_id=f"ext-{i}") for i in range(5)]
    candidates.append(_sample_candidate(external_id="ext-bad", phone="not a phone", email="bad", website=None))

    results, stats = normalize_candidates(candidates)

    assert stats.received == 6
    assert stats.normalized == 6
    assert stats.failed == 0
    assert len(results) == 6

    # 5 good + 1 bad phone -> 6 present, 5 valid, 1 invalid
    assert stats.phones_present == 6
    assert stats.phones_valid == 5
    assert stats.phones_invalid == 1

    assert stats.emails_present == 6
    assert stats.emails_valid == 5
    assert stats.emails_invalid == 1

    assert stats.websites_present == 5
    assert stats.domains_valid == 5


def test_one_bad_candidate_does_not_fail_the_batch(monkeypatch):
    import processing.normalization.service as service_module

    good = _sample_candidate(external_id="ok")
    bad = _sample_candidate(external_id="boom")

    original = service_module.normalize_candidate

    def flaky(candidate):
        if candidate.external_id == "boom":
            raise RuntimeError("simulated failure")
        return original(candidate)

    monkeypatch.setattr(service_module, "normalize_candidate", flaky)

    results, stats = service_module.normalize_candidates([good, bad])

    assert stats.received == 2
    assert stats.normalized == 1
    assert stats.failed == 1
    assert len(results) == 1


def test_osm_fixture_regression():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    preset = get_preset("dentist")

    raw_candidates = parse_elements(
        data["elements"], preset=preset, country="UA", region="Dnipro", city="Dnipro", limit=10
    )
    assert len(raw_candidates) == 3  # 4 elements, 1 dropped for missing name

    normalized, stats = normalize_candidates(raw_candidates)

    assert stats.received == 3
    assert stats.normalized == 3
    assert stats.failed == 0

    by_name = {c.canonical_name: c for c in normalized}

    dental_studio = by_name["Dental Studio Dnipro"]
    assert dental_studio.phone_normalized == "+380561112233"
    assert dental_studio.website_domain == "dental-studio.example.com"
    assert dental_studio.normalized_address == "yavornytskoho ave 12 dnipro 49000"

    smile_clinic = by_name["Smile Clinic"]
    assert smile_clinic.phone_normalized == "+380561234567"

    ortho_dent = by_name["OrthoDent Group"]
    assert ortho_dent.email_normalized == "info@orthodent.example.com"

import pytest
from pydantic import ValidationError

from app.models.source import SourceType
from sources.schemas import RawCandidate


def test_valid_candidate_is_accepted():
    candidate = RawCandidate(
        external_id="ext-1",
        name="Company 001",
        category="HVAC",
        city="Kyiv",
        phone="+380441112233",
        website="https://example.com",
        rating=4.5,
        reviews_count=10,
        source_type=SourceType.manual,
        source_url="https://mock.local/1",
        raw_payload={"foo": "bar"},
    )

    assert candidate.name == "Company 001"
    assert candidate.source_type == SourceType.manual


def test_empty_name_is_rejected():
    with pytest.raises(ValidationError):
        RawCandidate(name="", source_type=SourceType.manual)


def test_blank_name_is_rejected():
    with pytest.raises(ValidationError):
        RawCandidate(name="   ", source_type=SourceType.manual)


def test_source_type_is_required():
    with pytest.raises(ValidationError):
        RawCandidate(name="Company 001")


def test_optional_fields_default_to_none():
    candidate = RawCandidate(name="Company 001", source_type=SourceType.manual)

    assert candidate.source_url is None
    assert candidate.rating is None
    assert candidate.reviews_count is None
    assert candidate.phone is None
    assert candidate.website is None
    assert candidate.raw_payload is None

from processing.identity.models import Decision
from processing.identity.resolver import resolve_decision
from processing.identity.signals import (
    MatchCandidate,
    evaluate_signals,
    is_free_email_domain,
    is_shared_domain,
)


def _match(**overrides) -> MatchCandidate:
    defaults = dict(
        company_id="company-1",
        normalized_name="клімат сервіс",
        normalized_city="дніпро",
        phones=frozenset(),
        emails=frozenset(),
        domains=frozenset(),
        normalized_addresses=frozenset(),
        external_ids=frozenset(),
    )
    defaults.update(overrides)
    return MatchCandidate(**defaults)


def test_same_phone_is_immediate_match():
    match = _match(phones=frozenset({"+380501111111"}))
    score, signals = evaluate_signals(
        normalized_name="something else",
        normalized_city=None,
        normalized_address=None,
        phone_normalized="+380501111111",
        email_normalized=None,
        website_domain=None,
        source_type=None,
        external_id=None,
        match=match,
    )
    assert score == 100
    assert signals == ["same_phone"]
    assert resolve_decision([(match, score, signals)]).decision == Decision.MATCH


def test_same_business_domain_is_immediate_match():
    match = _match(domains=frozenset({"example.com"}))
    score, signals = evaluate_signals(
        normalized_name="x",
        normalized_city=None,
        normalized_address=None,
        phone_normalized=None,
        email_normalized=None,
        website_domain="example.com",
        source_type=None,
        external_id=None,
        match=match,
    )
    assert score == 100
    assert "same_domain" in signals


def test_shared_domain_never_matches():
    match = _match(domains=frozenset({"facebook.com"}))
    score, signals = evaluate_signals(
        normalized_name="x",
        normalized_city=None,
        normalized_address=None,
        phone_normalized=None,
        email_normalized=None,
        website_domain="facebook.com",
        source_type=None,
        external_id=None,
        match=match,
    )
    assert score == 0
    assert "same_domain" not in signals
    assert is_shared_domain("facebook.com")
    assert is_shared_domain("prom.ua")
    assert is_shared_domain("olx.ua")
    assert is_shared_domain("instagram.com")


def test_same_source_external_id_is_immediate_match():
    match = _match(external_ids=frozenset({("openstreetmap", "osm:node:123")}))
    score, signals = evaluate_signals(
        normalized_name="x",
        normalized_city=None,
        normalized_address=None,
        phone_normalized=None,
        email_normalized=None,
        website_domain=None,
        source_type="openstreetmap",
        external_id="osm:node:123",
        match=match,
    )
    assert score == 100
    assert signals == ["same_source_external_id"]


def test_exact_email_is_strong_signal():
    match = _match(emails=frozenset({"sales@example.com"}))
    score, signals = evaluate_signals(
        normalized_name="x",
        normalized_city=None,
        normalized_address=None,
        phone_normalized=None,
        email_normalized="sales@example.com",
        website_domain=None,
        source_type=None,
        external_id=None,
        match=match,
    )
    assert score == 90
    assert resolve_decision([(match, score, signals)]).decision == Decision.MATCH


def test_free_email_domain_alone_never_matches_two_different_addresses():
    # a@gmail.com vs b@gmail.com: different exact addresses -> no signal at all.
    match = _match(emails=frozenset({"a@gmail.com"}))
    score, signals = evaluate_signals(
        normalized_name="x",
        normalized_city=None,
        normalized_address=None,
        phone_normalized=None,
        email_normalized="b@gmail.com",
        website_domain=None,
        source_type=None,
        external_id=None,
        match=match,
    )
    assert score == 0
    assert signals == []
    assert is_free_email_domain("gmail.com")


def test_name_and_city_only_is_review_not_match():
    match = _match(normalized_name="стоматологія", normalized_city="дніпро")
    score, signals = evaluate_signals(
        normalized_name="стоматологія",
        normalized_city="дніпро",
        normalized_address=None,
        phone_normalized=None,
        email_normalized=None,
        website_domain=None,
        source_type=None,
        external_id=None,
        match=match,
    )
    assert score == 70
    assert signals == ["same_name_city"]
    assert resolve_decision([(match, score, signals)]).decision == Decision.REVIEW


def test_same_name_different_city_does_not_match():
    match = _match(normalized_name="авто плюс", normalized_city="львів")
    score, signals = evaluate_signals(
        normalized_name="авто плюс",
        normalized_city="київ",
        normalized_address=None,
        phone_normalized=None,
        email_normalized=None,
        website_domain=None,
        source_type=None,
        external_id=None,
        match=match,
    )
    assert score == 0
    assert signals == []


def test_name_and_address_is_strong_match():
    match = _match(
        normalized_name="клімат сервіс", normalized_addresses=frozenset({"вул. шевченка 10"})
    )
    score, signals = evaluate_signals(
        normalized_name="клімат сервіс",
        normalized_city=None,
        normalized_address="вул. шевченка 10",
        phone_normalized=None,
        email_normalized=None,
        website_domain=None,
        source_type=None,
        external_id=None,
        match=match,
    )
    assert score == 90
    assert signals == ["same_name_address"]
    assert resolve_decision([(match, score, signals)]).decision == Decision.MATCH


def test_conflicting_phones_with_only_name_city_is_review():
    match = _match(
        normalized_name="стоматологія", normalized_city="дніпро", phones=frozenset({"+380501111111"})
    )
    score, signals = evaluate_signals(
        normalized_name="стоматологія",
        normalized_city="дніпро",
        normalized_address=None,
        phone_normalized="+380509999999",  # different phone: no phone signal
        email_normalized=None,
        website_domain=None,
        source_type=None,
        external_id=None,
        match=match,
    )
    assert score == 70
    assert signals == ["same_name_city"]
    assert resolve_decision([(match, score, signals)]).decision == Decision.REVIEW


def test_no_signals_is_new():
    decision = resolve_decision([])
    assert decision.decision == Decision.NEW
    assert decision.company_id is None
    assert decision.score == 0

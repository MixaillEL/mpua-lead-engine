import json
from pathlib import Path

from app.models.source import SourceType
from sources.tavily_search.parser import dedupe_by_domain, filter_relevant, parse_response, result_to_candidate

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tavily_search_response.json"


def _load():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_response_extracts_results_with_title_and_url():
    data = _load()
    results = parse_response(data, query="стоматологія Київ")
    # 7 raw entries, 1 has an empty title -> dropped at parse level
    assert len(results) == 6
    assert all(r.title and r.url for r in results)


def test_parse_response_empty_results_key():
    assert parse_response({}, query="x") == []
    assert parse_response({"results": []}, query="x") == []


def test_dedupe_by_domain_collapses_same_domain():
    data = _load()
    results = parse_response(data, query="стоматологія Київ")
    deduped = dedupe_by_domain(results)
    smile_urls = [r.url for r in deduped if "smile-dental.example.com" in r.url]
    assert len(smile_urls) == 1
    assert smile_urls[0] == "https://smile-dental.example.com/"  # first/highest-ranked kept


def test_filter_relevant_drops_social_pdf_listicle():
    data = _load()
    results = parse_response(data, query="стоматологія Київ")
    deduped = dedupe_by_domain(results)
    relevant = filter_relevant(deduped)

    urls = {r.url for r in relevant}
    assert "https://facebook.com/smiledentalkyiv" not in urls
    assert not any("top-10-dentists" in u for u in urls)
    assert "https://smile-dental.example.com/" in urls
    assert "https://dentalplus.example.com/" in urls


def test_result_to_candidate_preserves_raw_payload_with_content_and_score():
    data = _load()
    results = parse_response(data, query="стоматологія Київ")
    result = next(r for r in results if "dentalplus" in r.url)

    candidate = result_to_candidate(result, country="UA", region="Kyiv")

    assert candidate.name == "Dental Plus Clinic"
    assert candidate.website == "https://dentalplus.example.com/"
    assert candidate.source_url == "https://dentalplus.example.com/"
    assert candidate.source_type == SourceType.web_search
    assert candidate.raw_payload["content"] == "Family dental clinic in Kyiv."
    assert candidate.raw_payload["score"] == 0.88
    assert candidate.raw_payload["query"] == "стоматологія Київ"


def test_content_snippet_never_written_into_candidate_description():
    data = _load()
    results = parse_response(data, query="стоматологія Київ")
    result = next(r for r in results if "dentalplus" in r.url)

    candidate = result_to_candidate(result, country="UA", region="Kyiv")
    assert candidate.description is None  # only in raw_payload, per policy


def test_external_id_is_stable_hash_of_domain():
    data = _load()
    results = parse_response(data, query="стоматологія Київ")
    result = next(r for r in results if "dentalplus" in r.url)

    c1 = result_to_candidate(result, country="UA", region="Kyiv")
    c2 = result_to_candidate(result, country="UA", region="Kyiv")
    assert c1.external_id == c2.external_id
    assert c1.external_id.startswith("tavily:")


def test_title_cleaned():
    data = _load()
    results = parse_response(data, query="стоматологія Київ")
    result = next(r for r in results if r.url == "https://smile-dental.example.com/")

    candidate = result_to_candidate(result, country="UA", region="Kyiv")
    assert candidate.name == "Стоматологія Смайл"

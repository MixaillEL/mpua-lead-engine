import pytest

from processing.normalization.website import normalize_website


@pytest.mark.parametrize(
    "raw",
    [
        "example.com",
        "www.example.com",
        "http://example.com/",
        "https://www.example.com/",
        "https://example.com/contact",
    ],
)
def test_domain_is_always_example_com(raw):
    _, domain = normalize_website(raw)
    assert domain == "example.com"


def test_scheme_is_added_when_missing():
    url, _ = normalize_website("example.com")
    assert url.startswith("https://")


def test_fragment_is_removed():
    url, domain = normalize_website("https://example.com/page#section")
    assert "#" not in url
    assert domain == "example.com"


def test_idn_domain_does_not_crash():
    url, domain = normalize_website("http://приклад.укр")
    assert url is not None
    assert domain is not None


def test_none_returns_none_none():
    assert normalize_website(None) == (None, None)


def test_empty_string_returns_none_none():
    assert normalize_website("   ") == (None, None)

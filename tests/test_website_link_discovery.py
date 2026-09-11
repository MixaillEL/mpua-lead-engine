from pathlib import Path

from enrichment.website.extractor import extract_links
from enrichment.website.link_discovery import (
    discover_contact_links,
    is_same_domain,
    normalize_url,
    should_skip_path,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_same_domain_true():
    assert is_same_domain("https://www.example.com/contacts", "example.com")
    assert is_same_domain("https://example.com/about", "example.com")


def test_same_domain_false():
    assert not is_same_domain("https://facebook.com/example", "example.com")
    assert not is_same_domain("https://partner-site.com/", "example.com")


def test_discover_contact_links_prioritizes_contact_over_about():
    html = _load("website_a_complete.html")
    links = extract_links(html)
    urls = discover_contact_links(links, base_url="https://example.com/", root_domain="example.com")
    assert urls[0].endswith("/contacts")
    assert any(u.endswith("/about") for u in urls)


def test_external_links_are_excluded():
    html = _load("website_d_external_links.html")
    links = extract_links(html)
    urls = discover_contact_links(links, base_url="https://example.com/", root_domain="example.com")
    assert all("partner-site.com" not in u for u in urls)
    assert all("facebook.com" not in u for u in urls)
    assert any(u.endswith("/contacts") for u in urls)


def test_skip_admin_login_cart_paths():
    assert should_skip_path("https://example.com/wp-admin/edit")
    assert should_skip_path("https://example.com/login")
    assert should_skip_path("https://example.com/cart")
    assert not should_skip_path("https://example.com/contacts")


def test_normalize_url_strips_fragment_and_tracking_params():
    url = "https://example.com/contacts?utm_source=fb&id=1#section"
    normalized = normalize_url(url)
    assert "#" not in normalized
    assert "utm_source" not in normalized
    assert "id=1" in normalized


def test_normalize_url_collapses_trailing_slash():
    assert normalize_url("https://example.com/contacts/") == normalize_url("https://example.com/contacts")


def test_cyrillic_links_discovered_same_domain():
    html = _load("website_e_cyrillic.html")
    links = extract_links(html)
    urls = discover_contact_links(
        links, base_url="https://klimat-servis.example/", root_domain="klimat-servis.example"
    )
    assert any("контакти" in u for u in urls)

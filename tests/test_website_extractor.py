from pathlib import Path

from enrichment.website.extractor import extract_contacts, extract_links

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_fixture_a_tel_mailto_socials_and_jsonld():
    html = _load("website_a_complete.html")
    phones, emails, socials = extract_contacts(html, "https://example.com/")

    phone_raws = {p.raw for p in phones}
    assert "+380501234567" in phone_raws

    email_raws = {e.raw for e in emails}
    assert "info@example.com" in email_raws

    platforms = {s.platform for s in socials}
    assert "facebook" in platforms
    assert "instagram" in platforms


def test_fixture_a_contact_link_discovered():
    html = _load("website_a_complete.html")
    links = extract_links(html)
    hrefs = {href for href, _ in links}
    assert "/contacts" in hrefs
    assert "/about" in hrefs


def test_tel_link_has_highest_confidence():
    html = _load("website_a_complete.html")
    phones, _, _ = extract_contacts(html, "https://example.com/")
    tel_phone = next(p for p in phones if p.raw == "+380501234567" and p.confidence == 1.0)
    assert tel_phone is not None


def test_mailto_link_extracted():
    html = '<a href="mailto:sales@example.com">Email us</a>'
    _, emails, _ = extract_contacts(html, "https://example.com/")
    assert any(e.raw == "sales@example.com" for e in emails)


def test_visible_phone_extracted():
    html = "<p>Дзвоніть нам: 050 123 45 67</p>"
    phones, _, _ = extract_contacts(html, "https://example.com/")
    assert any("050" in p.raw for p in phones)


def test_visible_email_extracted():
    html = "<p>Пишіть: hello@example.com</p>"
    _, emails, _ = extract_contacts(html, "https://example.com/")
    assert any(e.raw == "hello@example.com" for e in emails)


def test_json_ld_phone_and_email():
    html = _load("website_a_complete.html")
    phones, emails, socials = extract_contacts(html, "https://example.com/")
    jsonld_phones = [p for p in phones if p.confidence == 0.95]
    jsonld_emails = [e for e in emails if e.confidence == 0.95]
    assert len(jsonld_phones) >= 1
    assert len(jsonld_emails) >= 1
    jsonld_socials = [s for s in socials if s.page_url == "https://example.com/"]
    assert any(s.platform == "facebook" for s in jsonld_socials)


def test_duplicate_phone_and_email_collapse_to_one_unique_raw_value():
    html = _load("website_b_duplicates.html")
    phones, emails, _ = extract_contacts(html, "https://example.com/")

    unique_phone_raws = {p.raw.replace(" ", "") for p in phones}
    unique_email_raws = {e.raw for e in emails}

    # multiple *mentions* across footer/main/json-ld collapse to 1 distinct value
    assert unique_phone_raws == {"+380501234567"}
    assert unique_email_raws == {"info@example.com"}


def test_garbage_emails_are_filtered_out():
    html = _load("website_c_garbage.html")
    _, emails, _ = extract_contacts(html, "https://example.com/")
    email_raws = {e.raw.lower() for e in emails}
    assert "noreply@example.com" not in email_raws
    assert "test@test.com" not in email_raws
    assert "example@example.com" not in email_raws


def test_javascript_link_is_not_a_contact_link():
    html = _load("website_c_garbage.html")
    links = extract_links(html)
    hrefs = [href for href, _ in links]
    assert any(href.startswith("javascript:") for href in hrefs)  # present in HTML
    # but extract_contacts must not treat it as tel/mailto
    phones, emails, _ = extract_contacts(html, "https://example.com/")
    assert all(not p.raw.startswith("javascript") for p in phones)


def test_obfuscated_email_at_dot():
    html = "<p>Contact: info [at] example [dot] com</p>"
    _, emails, _ = extract_contacts(html, "https://example.com/")
    assert any(e.raw == "info@example.com" for e in emails)


def test_obfuscated_email_parens():
    html = "<p>Contact: info(at)example.com</p>"
    _, emails, _ = extract_contacts(html, "https://example.com/")
    assert any(e.raw == "info@example.com" for e in emails)


def test_cyrillic_contact_links_and_phone():
    html = _load("website_e_cyrillic.html")
    links = extract_links(html)
    hrefs = {href for href, _ in links}
    assert "/контакти" in hrefs
    assert "/про-нас" in hrefs

    phones, _, _ = extract_contacts(html, "https://klimat-servis.example/")
    assert any("380671112233" in p.raw.replace(" ", "").replace("+", "") for p in phones)

from sources.tavily_search.filters import (
    clean_title,
    get_domain,
    is_denylisted_domain,
    is_directory_result,
    is_file_result,
    is_listicle_title,
    is_relevant_result,
    is_valid_http_url,
)


def test_denylisted_social_domain():
    assert is_denylisted_domain("facebook.com")
    assert is_denylisted_domain("instagram.com")
    assert is_denylisted_domain("wikipedia.org")
    assert not is_denylisted_domain("example.com")


def test_directory_result_detected():
    assert is_directory_result("https://hotline.ua/x", "hotline.ua")
    assert is_directory_result("https://example.com/company/foo", "example.com")
    assert not is_directory_result("https://example.com/about", "example.com")


def test_file_result_detected():
    assert is_file_result("https://example.com/price.pdf")
    assert not is_file_result("https://example.com/contacts")


def test_listicle_title_detected():
    assert is_listicle_title("ТОП-10 стоматологій Києва 2026")
    assert is_listicle_title("Рейтинг кращих СТО")
    assert not is_listicle_title("Dental Plus Clinic")


def test_clean_title_strips_suffix():
    assert clean_title("Стоматологія Смайл — Офіційний сайт") == "Стоматологія Смайл"
    assert clean_title("Example Co - Official site") == "Example Co"
    assert clean_title("Plain Name") == "Plain Name"


def test_valid_http_url():
    assert is_valid_http_url("https://example.com/")
    assert not is_valid_http_url("ftp://example.com/")
    assert not is_valid_http_url("not a url")


def test_get_domain_strips_www():
    assert get_domain("https://www.example.com/x") == "example.com"
    assert get_domain("https://example.com/x") == "example.com"


def test_is_relevant_result_accepts_real_business():
    assert is_relevant_result("Dental Plus Clinic", "https://dentalplus.example.com/")


def test_is_relevant_result_rejects_social():
    assert not is_relevant_result("Smile Dental (Facebook)", "https://facebook.com/smiledentalkyiv")


def test_is_relevant_result_rejects_empty_title():
    assert not is_relevant_result("", "https://example.com/")


def test_is_relevant_result_rejects_pdf():
    assert not is_relevant_result("Price list", "https://example.com/price.pdf")


def test_is_relevant_result_rejects_listicle():
    assert not is_relevant_result("ТОП-10 стоматологій Києва", "https://blog.example.com/top-10")

from processing.normalization.address import normalize_address, normalize_city


def test_extra_spaces_and_punctuation_are_collapsed():
    assert normalize_address("  вул. Шевченка,   10  ") == "вул. шевченка 10"


def test_unicode_and_cyrillic_are_lowercased():
    assert normalize_address("ВУЛИЦЯ ХРЕЩАТИК") == "вулиця хрещатик"


def test_none_returns_none():
    assert normalize_address(None) is None


def test_empty_string_returns_none():
    assert normalize_address("   ") is None


def test_city_normalization_converges():
    # "Київ"/"київ" converge; "KYIV" is a different (Latin) string, kept
    # canonical for its own script, but still deterministic/lowercase/trimmed.
    assert normalize_city("Київ") == normalize_city("київ") == "київ"
    assert normalize_city("KYIV") == "kyiv"

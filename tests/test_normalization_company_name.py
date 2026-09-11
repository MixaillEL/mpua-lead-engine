from processing.normalization.company_name import canonicalize_name, normalize_name


def test_legal_prefix_tov_is_stripped():
    name = 'ТОВ "Клімат-Сервіс"'
    assert canonicalize_name(name) == 'ТОВ "Клімат-Сервіс"'
    assert normalize_name(name) == "клімат сервіс"


def test_variants_converge_to_same_normalized_name():
    variants = [
        'ТОВ "Клімат-Сервіс"',
        "ТОВ Клімат Сервіс",
        '"КЛІМАТ-СЕРВІС"',
    ]
    normalized = {normalize_name(v) for v in variants}
    assert normalized == {"клімат сервіс"}


def test_prefix_word_inside_real_name_is_kept():
    # "Сервіс Плюс" must survive untouched; only the standalone "ТОВ" token drops.
    assert normalize_name("ТОВ Сервіс Плюс") == "сервіс плюс"


def test_normalization_is_deterministic():
    name = 'ФОП Іванов І. І.'
    assert normalize_name(name) == normalize_name(name)


def test_canonical_name_is_trim_only():
    assert canonicalize_name("  Клімат-Сервіс  ") == "Клімат-Сервіс"

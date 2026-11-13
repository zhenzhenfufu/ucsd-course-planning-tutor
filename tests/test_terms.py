import pytest

from terms import Term, next_term, parse_term, term_from_code, terms_from


@pytest.mark.parametrize("label,expected", [
    ("Fall 2026", Term("FA", 2026)),
    ("fall 2026", Term("FA", 2026)),
    ("FA26", Term("FA", 2026)),
    ("Winter 2027", Term("WI", 2027)),
    ("WI27", Term("WI", 2027)),
    ("SP27", Term("SP", 2027)),
    ("Spring 2027", Term("SP", 2027)),
    ("Summer 2027", Term("SU", 2027)),
    ("SU27", Term("SU", 2027)),
    ("  Fall 2026 ", Term("FA", 2026)),
])
def test_parse_accepts(label, expected):
    assert parse_term(label) == expected


@pytest.mark.parametrize("label", [
    "Term 1", "F", "W", "Fall", "Summer", "", "FA", "FA2026x", "Autumn 2026", None, 5,
])
def test_parse_rejects(label):
    assert parse_term(label) is None


def test_code_name_year():
    t = Term("WI", 2027)
    assert t.code == "WI27"
    assert t.name == "Winter 2027"
    assert Term("FA", 2026).academic_year == "2026-27"
    assert t.academic_year == "2026-27"
    assert Term("SP", 2027).academic_year == "2026-27"
    assert Term("SU", 2027).academic_year == "2026-27"
    assert Term("FA", 2099).academic_year == "2099-00"


def test_next_and_terms_from():
    assert next_term(Term("FA", 2026)) == Term("WI", 2027)
    assert next_term(Term("WI", 2027)) == Term("SP", 2027)
    assert next_term(Term("SP", 2027)) == Term("FA", 2027)
    assert next_term(Term("SU", 2027)) == Term("FA", 2027)
    assert [t.name for t in terms_from(Term("WI", 2027), 3)] == [
        "Winter 2027", "Spring 2027", "Fall 2027"]
    assert terms_from(Term("WI", 2027), 0) == []


def test_term_from_code():
    assert term_from_code("FA26") == Term("FA", 2026)
    with pytest.raises(ValueError):
        term_from_code("Term 1")

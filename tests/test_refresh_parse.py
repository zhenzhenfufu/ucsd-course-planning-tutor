"""Course IDs, units and prerequisite clause parsing (pure functions)."""

from refresh.ids import expand_ids, normalize_id, parse_units
from refresh.prereq_parse import ParsedPrereq, parse_prereq_clause


def test_normalize_id_spellings():
    assert normalize_id("DSC 10/R") == "DSC 10"
    assert normalize_id("DSC-040A") == "DSC 40A"
    assert normalize_id("040A", "DSC") == "DSC 40A"
    assert normalize_id("MATH 31 AH") == "MATH 31AH"
    assert normalize_id("ECE 005") == "ECE 5"
    assert normalize_id("CSE 158R") == "CSE 158R"
    assert normalize_id("no id here") is None
    assert normalize_id("") is None


def test_expand_ids_carries_subject_and_dedupes():
    assert expand_ids("DSC 20/R and 40A/R") == ["DSC 20", "DSC 40A"]
    assert expand_ids("MATH 20C or 31BH") == ["MATH 20C", "MATH 31BH"]
    assert expand_ids("DSC 10, DSC 10 or DSC 20") == ["DSC 10", "DSC 20"]
    assert expand_ids("40A", "DSC") == ["DSC 40A"]


def test_expand_ids_hyphen_sequences():
    assert expand_ids("MATH 181A-B-C") == ["MATH 181A", "MATH 181B", "MATH 181C"]
    assert expand_ids("DSC 40A/R-B/R") == ["DSC 40A", "DSC 40B"]


def test_parse_units():
    assert parse_units("Seminar (2 or 4)") == (2.0, 4.0)
    assert parse_units("Title (4)") == (4.0, 4.0)
    assert parse_units("T (1–4)") == (1.0, 4.0)
    assert parse_units("T (4-4-4)") == (4.0, 4.0)
    assert parse_units("T (1 to 12)") == (1.0, 12.0)
    assert parse_units("T (2, 4)") == (2.0, 4.0)
    assert parse_units("Intro (Formerly CSE 5) (4)") == (4.0, 4.0)


def test_clause_groups_and_condition():
    p = parse_prereq_clause(
        "DSC 10/R, (MATH 20C or MATH 31BH) and (MATH 18 or MATH 20F or MATH 31AH). "
        "Restricted to students within the data science major.", "DSC")
    assert isinstance(p, ParsedPrereq)
    assert p.groups == [["DSC 10"], ["MATH 20C", "MATH 31BH"],
                        ["MATH 18", "MATH 20F", "MATH 31AH"]]
    assert p.conditions == ["major restriction"]
    assert p.ambiguities == []


def test_clause_bare_numbers_and_comma_and():
    p = parse_prereq_clause("DSC 20/R and 40A/R.", "DSC")
    assert p.groups == [["DSC 20"], ["DSC 40A"]]
    p = parse_prereq_clause("DSC 102 and (MATH 189 or DSC 152), and "
                            "(DSC 140B or CSE 151A or COGS 188).", "DSC")
    assert p.groups == [["DSC 102"], ["MATH 189", "DSC 152"],
                        ["DSC 140B", "CSE 151A", "COGS 188"]]
    p = parse_prereq_clause("(MATH 20C or MATH 31BH) and (MATH 18 or MATH 31 AH).", "DSC")
    assert ["MATH 18", "MATH 31AH"] in p.groups


def test_clause_conditions():
    p = parse_prereq_clause(
        "restricted to students with upper-division standing. Consent of the "
        "instructor and approval of the department are required.", "DSC")
    assert p.groups == []
    assert p.conditions == ["upper-division standing", "instructor consent",
                            "department approval"]
    assert p.ambiguities == []


def test_clause_abstract_and_concurrent():
    p = parse_prereq_clause("a probability course; may be taken concurrently.", "DSC")
    assert p.groups == [["<probability>"]] and p.concurrent_ok
    p = parse_prereq_clause("DSC 40A may be taken concurrently.", "DSC")
    assert p.groups == [["DSC 40A"]] and p.concurrent_ok


def test_clause_none_and_unresolved():
    assert parse_prereq_clause("None", "DSC").groups == []
    assert parse_prereq_clause("No prerequisites.", "DSC").groups == []
    p = parse_prereq_clause("satisfactory completion of an unusual requirement "
                            "that nobody can parse at all here", "DSC")
    assert p.groups == []
    assert p.ambiguities[0]["kind"] == "unresolved"
    assert len(p.ambiguities[0]["fragment"].split()) <= 10


def test_clause_keeps_out_of_scope_courses():
    p = parse_prereq_clause("PHYS 2A or PHYS 4A.", "DSC")
    assert p.groups == [["PHYS 2A", "PHYS 4A"]]

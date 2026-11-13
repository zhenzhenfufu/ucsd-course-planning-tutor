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


def test_bare_numbers_are_not_fake_ids():
    p = parse_prereq_clause("DSC 20 with a grade of 2.0 or better", "DSC")
    assert p.groups == [["DSC 20"]]
    assert expand_ids("ECE 005 and 2 units") == ["ECE 5"]
    assert expand_ids("DSC 20 in 2026") == ["DSC 20"]
    assert expand_ids("DSC 10 and 4 units of GPA 3.0") == ["DSC 10"]


def test_bare_number_continuation_still_works():
    assert expand_ids("DSC 140A, 140B, 148, and 155") == [
        "DSC 140A", "DSC 140B", "DSC 148", "DSC 155"]
    assert expand_ids("DSC 20/R and 40A/R") == ["DSC 20", "DSC 40A"]
    assert expand_ids("MATH 20C or 31BH") == ["MATH 20C", "MATH 31BH"]


def test_condition_sentence_keeps_its_courses():
    p = parse_prereq_clause("Prerequisites: DSC 40A and DSC 80, or consent of instructor.", "DSC")
    assert p.groups == [["DSC 40A"], ["DSC 80"]]
    assert p.conditions == ["instructor consent"]
    p = parse_prereq_clause("Restricted to students within the data science major.", "DSC")
    assert p.groups == [] and p.ambiguities == []


def test_concurrent_removes_only_its_phrase():
    p = parse_prereq_clause("DSC 40A may be taken concurrently, and DSC 20", "DSC")
    assert p.groups == [["DSC 40A"], ["DSC 20"]]
    assert p.concurrent_ok


def test_credit_exclusion_sentences_yield_no_groups():
    p = parse_prereq_clause(
        "(MATH 20C or MATH 31BH) and (MATH 18 or MATH 31 AH). Students may not receive "
        "credit for both DSC 123A and MATH 173A. Students who have not completed listed "
        "prerequisites may enroll with consent of instructor.", "DSC")
    assert p.groups == [["MATH 20C", "MATH 31BH"], ["MATH 18", "MATH 31AH"]]
    assert p.conditions == ["credit exclusion", "instructor consent"]
    for s in ("Credit not allowed for both DSC 10 and DSC 20.",
              "Not open to students who have completed DSC 20.",
              "Students may not enroll in this course if they have completed DSC 30."):
        q = parse_prereq_clause("DSC 10. " + s, "DSC")
        assert q.groups == [["DSC 10"]] and q.conditions == ["credit exclusion"], s


def test_standing_approval_and_chemistry_become_conditions_not_groups():
    p = parse_prereq_clause("DSC 80 or department and instructor approval required.", "DSC")
    assert p.groups == [["DSC 80"]] and "instructor consent" in p.conditions
    p = parse_prereq_clause("Instructor approval required.", "DSC")
    assert p.groups == [] and p.conditions == ["instructor consent"]
    p = parse_prereq_clause("High school chemistry.", "CHEM")
    assert p.groups == [] and p.conditions == ["external requirement"]
    p = parse_prereq_clause("A probability course and DSC 10.", "DSC")
    assert ["<probability>"] in p.groups


def test_advisory_sentence_is_not_a_prerequisite():
    p = parse_prereq_clause(
        "DSC 10. Completion of MATH 102 is encouraged but not required.", "DSC")
    assert p.groups == [["DSC 10"]]
    assert p.ambiguities == [{"kind": "advisory",
                              "fragment": "Completion of MATH 102 is encouraged but not required"}]


def test_coscheduled_and_receive_credit_sentences_yield_no_groups():
    p = parse_prereq_clause(
        "DSC 10. May be coscheduled with CSE 258. Students may not receive credit for "
        "DSC 77 and DSC 78 or DSC 79.", "DSC")
    assert p.groups == [["DSC 10"]]
    assert p.conditions == ["credit exclusion"]
    assert p.ambiguities == []


def test_known_subject_codes_match_case_insensitively():
    p = parse_prereq_clause("Math 20C or MATH 31BH, or consent of instructor.", "DSC")
    assert p.groups == [["MATH 20C", "MATH 31BH"]]
    assert parse_prereq_clause("Zorp 20C.", "DSC").groups == []


def test_restriction_sentences_never_yield_options():
    p = parse_prereq_clause(
        "DSC 10; restricted to students within the XY25, XY26, and ZZ25 majors. "
        "Restricted to junior and senior level students. All other students will be "
        "allowed as space permits.", "DSC")
    assert p.groups == [["DSC 10"]]
    assert p.conditions == ["major restriction", "enrollment restriction"]
    assert p.ambiguities == []
    q = parse_prereq_clause("DSC 10 and 20; restricted to XY25 majors.", "DSC")
    assert q.groups == [["DSC 10"], ["DSC 20"]]


def test_exam_alternatives_become_a_token_inside_the_or_group():
    p = parse_prereq_clause(
        "Placement Exam qualifying score, or AP Widgets score of 4 or 5, or DSC 10 "
        "with a grade of C- or better, or DSC 20.", "DSC")
    assert p.groups == [["<exam or placement>", "DSC 10", "DSC 20"]]
    assert p.ambiguities == []
    q = parse_prereq_clause("DSC 10 or equivalent.", "DSC")
    assert q.groups == [["DSC 10", "<exam or placement>"]]
    from refresh.prereq_parse import ABSTRACT_SATISFIERS
    assert ABSTRACT_SATISFIERS["<exam or placement>"] == []


def test_one_of_list_is_a_single_or_group():
    p = parse_prereq_clause(
        "DSC 10 or DSC 20, and DSC 30 and one of DSC 40, DSC 50, DSC 60, or DSC 70. "
        "Students may enroll with consent of instructor.", "DSC")
    assert p.groups == [["DSC 10", "DSC 20"], ["DSC 30"],
                        ["DSC 40", "DSC 50", "DSC 60", "DSC 70"]]


def test_comma_or_is_an_or_not_an_and():
    p = parse_prereq_clause("DSC 10, or DSC 20, or DSC 30.", "DSC")
    assert p.groups == [["DSC 10", "DSC 20", "DSC 30"]]


def test_hyphen_sequences_are_and_and_duplicate_groups_collapse():
    p = parse_prereq_clause("DSC 10A-B, and DSC 30 or DSC 40. DSC 30 or DSC 40.", "DSC")
    assert p.groups == [["DSC 10A"], ["DSC 10B"], ["DSC 30", "DSC 40"]]
    p = parse_prereq_clause("DSC 10A-B or DSC 20A-B-C.", "DSC")
    assert len(p.groups) == 6 and ["DSC 10B", "DSC 20C"] in p.groups

# Data Refresh and Quarter Offerings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-written course data with a generated catalog snapshot and quarter-offerings layer, refreshed weekly by GitHub Actions, and add a `NOT_OFFERED` validator rule.

**Architecture:** A `refresh/` package fetches UCSD's public pages through one polite HTTP client, parses them into derived facts, and writes `data/catalog.json` and `data/offerings.json`. The app-side modules (`prereq_graph`, `validator`, `planner`, `retrieval`, `app`) only read those files plus hand files (`data/scope.json`, `data/sources.json`, `data/offerings_manual.json`, `prereq_overrides.json`). A weekly workflow runs the refresh and the offline tests and opens one PR with a readable report.

**Tech Stack:** Python 3.11, requests, beautifulsoup4, protego (new), networkx, Streamlit, pytest, GitHub Actions with `gh`.

**Spec:** `docs/superpowers/specs/2026-11-12-data-refresh-design.md`. Source details (selectors, column headers, robots and terms quotes) are in `docs/research/data-sources-2026-11-12.json`; read the matching section before writing an adapter.

## Global Constraints

- User-Agent `ucsd-course-planning-tutor (student project)`; at most 1 request per second per host; honor robots with `protego`; never follow a redirect to `a5.ucsd.edu`.
- No credentials anywhere: no cookies, no personal tokens, nothing from `.env` in CI.
- Stored data = derived facts: IDs, titles, units, prerequisite groups, condition tokens, quarter booleans, `source_url`, `fetched_at`, `content_hash`. No descriptions, no instructor names, no raw responses.
- Ambiguity fragments: at most about ten words, never a full sentence.
- Class Planner: only `/api/v1/public/*`. Never `/api/v1/planner/*`, `/api/v1/catalog/*`, `/api/v1/user-state`, TSS, api.ucsd.edu, CAPE results, SET, DARS.
- Test fixtures are small hand-written snippets that copy each source's structure with invented text. Never save real UCSD pages into the repo.
- `pytest tests/ -q` and `python eval/run_eval.py --offline` never touch the network.
- Last good snapshot wins: a source that fails its shape check keeps its previous data.
- Python 3.11. One new dependency: `protego`.
- Commits authored as `zhenzhenfufu <zhw124@ucsd.edu>` with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push to `main`; never commit `.env` or `GEMINI_API_KEY`.
- README claims stay true. The 40% → 100% result predates the October 2026 rebuild; keep it labelled as that past measurement.

## Review Focus

1. **Term labels the validator cannot place** (`Term 1`, `F`, `Summer`, `Summer 2027`, lower-case `fall 2026`): no `NOT_OFFERED` finding and no exception. Test in Task 7 and Task 12.
2. **A department URL that answers 200 with an HTML page instead of CSV** (unpublished or re-keyed Google Sheet): the adapter raises `ShapeError`, that source keeps its previous data, and the report lists it as failed. Test in Task 10 and Task 11.
3. **ID spellings seen live but easy to miss**: `MATH 31 AH` (space inside, on DSC 123A today), `DSC-040A`, `040A` with subject given separately, `CSE 158R`, `ECE 005`. All normalize. Test in Task 2.
4. **A Class Planner term that lists zero courses for a subject** (partial refresh, or `configured: false`): that subject is treated as not covered for that term, so it never produces `NOT_OFFERED` errors. Test in Task 8.
5. **`data/offerings.json` missing or unreadable** (first deploy, bad merge): validator gives no `NOT_OFFERED` findings, planner and app still run, the app says offerings are unavailable. Test in Task 8 and Task 13.

## File Structure

| Path | Responsibility |
|---|---|
| `refresh/__init__.py` | package marker |
| `refresh/http.py` | `PoliteSession`: the only network access in refresh code |
| `refresh/ids.py` | course-ID normalization and expansion |
| `refresh/prereq_parse.py` | prerequisite clause → groups, conditions, ambiguities (moved out of `prereq_graph.py`) |
| `refresh/catalog.py` | catalog page parser and `catalog.json` builder |
| `refresh/classplanner.py` | Class Planner public API client |
| `refresh/offerings/{dsc,cse,math,cogs,phys,ece}.py` | one tentative-plan adapter each |
| `refresh/offerings/__init__.py` | `ShapeError`, adapter registry |
| `refresh/report.py` | catalog and offerings diffs, PR body |
| `refresh/run.py` | CLI entry point: runs sources, applies last-good, writes files and report |
| `terms.py` | term-label parsing and term arithmetic (used by app side) |
| `offerings.py` | load `offerings.json` + manual file, `lookup()` |
| `prereq_graph.py` | builds `CourseGraph` from `data/catalog.json` + scope + overrides |
| `validator.py`, `planner.py`, `retrieval.py`, `ai_advisor.py`, `app.py` | adjusted readers |
| `data/scope.json`, `data/sources.json`, `data/offerings_manual.json` | hand files |
| `data/catalog.json`, `data/offerings.json` | generated files |
| `.github/workflows/refresh.yml` | weekly refresh + PR |
| `tests/test_refresh_*.py`, `tests/test_offerings.py`, `tests/fixtures/` | new offline tests |
| deleted: `scraper.py`, `dsc_courses.json` | |

## Delivery

- **PR 1 (Tasks 1–6):** from the current branch `claude/mystifying-cray-bbd7c1` (it already carries the docs commit). Title: "Generate the catalog snapshot and replace descriptions with keywords".
- **PR 2 (Tasks 7–13):** branch `data-refresh-offerings` from PR 1's tip (or from `main` once PR 1 is merged).
- **PR 3 (Tasks 14–15):** branch `data-refresh-workflow` from PR 2's tip.

Each PR body lists what was verified and what was not. Run `pytest tests/ -q` and `python eval/run_eval.py --offline` before every commit.

---

## PR 1 — catalog snapshot and keywords

### Task 1: Polite HTTP client

**Files:**
- Create: `refresh/__init__.py`, `refresh/http.py`
- Modify: `requirements.txt` (add `protego`)
- Test: `tests/test_refresh_http.py`

**Interfaces:**
- Produces:
  - `UA = "ucsd-course-planning-tutor (student project)"`
  - `class FetchError(Exception)`, `class SSORedirect(FetchError)`, `class RobotsDisallowed(FetchError)`, `class PathNotAllowed(FetchError)`
  - `@dataclass FetchResult: url: str; status: int; text: str; not_modified: bool; headers: dict[str, str]`
  - `class PoliteSession(transport=None, min_interval: float = 1.0, clock=time.monotonic, sleep=time.sleep, cache_dir: Path | None = None, allowed_prefixes: dict[str, tuple[str, ...]] | None = None)`
    - `.get(url: str) -> FetchResult`
    - `.post_json(url: str, payload: dict) -> dict`

Behaviour: `transport` is a `requests.Session` (default) or a test double with the same `request(method, url, headers=..., json=..., allow_redirects=False, timeout=...)`. Redirects are followed by hand, at most 5; any `Location` whose host is `a5.ucsd.edu` raises `SSORedirect`. Robots: fetch `https://{host}/robots.txt` once per host without following redirects; 200 → parse with `protego`; anything else → no rules. Requests to the same host are spaced by `min_interval` using `clock`/`sleep`. `cache_dir` stores ETag / Last-Modified per URL and sends `If-None-Match` / `If-Modified-Since`; a 304 returns the cached text with `not_modified=True`. `allowed_prefixes` maps host → allowed path prefixes; anything else raises `PathNotAllowed`. Timeout 30 s; retry twice with 2 s and 4 s backoff on connection errors and 5xx.

- [ ] **Step 1: Write the failing tests** with a fake transport (a class recording calls and returning scripted responses):

```python
def test_sends_user_agent(fake): ...            # headers["User-Agent"] == UA
def test_spaces_requests_per_host(fake):        # two GETs to one host -> sleep called with ~1.0
def test_stops_on_sso_redirect(fake):           # 302 Location https://a5.ucsd.edu/... -> raises SSORedirect
def test_robots_wildcard_disallow(fake):        # robots "User-agent: *\nDisallow: *.pdf" -> get(".../x.pdf") raises RobotsDisallowed
def test_robots_redirect_means_no_rules(fake):  # robots 307 -> get(".../page") succeeds
def test_conditional_get_uses_cache(fake, tmp_path):  # 2nd get sends If-None-Match; 304 -> same text, not_modified True
def test_path_allowlist(fake):                  # allowed_prefixes={"classplanner.apps.ucsd.edu": ("/api/v1/public/",)}; "/api/v1/planner/x" raises PathNotAllowed
```

- [ ] **Step 2: Run** `pytest tests/test_refresh_http.py -v` — expect FAIL (module missing).
- [ ] **Step 3: Implement `refresh/http.py`** as specified above; add `protego` to `requirements.txt`; `pip install protego`.
- [ ] **Step 4: Run** `pytest tests/ -q` — expect all pass.
- [ ] **Step 5: Commit** `feat: add polite HTTP client for refresh jobs`.

### Task 2: Course IDs, units and prerequisite clauses

**Files:**
- Create: `refresh/ids.py`, `refresh/prereq_parse.py`
- Test: `tests/test_refresh_parse.py`

**Interfaces:**
- Produces:
  - `normalize_id(raw: str, subject: str | None = None) -> str | None` — `"DSC 10/R"→"DSC 10"`, `"DSC-040A"→"DSC 40A"`, `("040A","DSC")→"DSC 40A"`, `"MATH 31 AH"→"MATH 31AH"`, `"ECE 005"→"ECE 5"`, `"CSE 158R"→"CSE 158R"`; returns `None` when no ID is present.
  - `expand_ids(text: str, subject: str | None = None) -> list[str]` — ordered, de-duplicated; carries the last subject to bare numbers (`"DSC 20/R and 40A/R"→["DSC 20","DSC 40A"]`); expands hyphen sequences (`"MATH 181A-B-C"→["MATH 181A","MATH 181B","MATH 181C"]`, `"DSC 40A/R-B/R"→["DSC 40A","DSC 40B"]`).
  - `parse_units(text: str) -> tuple[float, float]` — `"(4)"→(4,4)`, `"(2 or 4)"→(2,4)`, `"(1–4)"→(1,4)`, `"(4-4-4)"→(4,4)`, `"(1 to 12)"→(1,12)`, `"(2, 4)"→(2,4)`; reads the last parenthesised group.
  - `@dataclass ParsedPrereq: groups: list[list[str]]; concurrent_ok: bool; conditions: list[str]; ambiguities: list[dict]` (each ambiguity: `{"kind": str, "fragment": str}`, fragment ≤ 10 words)
  - `parse_prereq_clause(text: str, subject: str) -> ParsedPrereq`
  - `CONDITION_PATTERNS: list[tuple[re.Pattern, str]]` producing tokens `"upper-division standing"`, `"major restriction"`, `"instructor consent"`, `"department approval"`, `"gpa"`, `"units completed"`.
  - `ABSTRACT_PATTERNS` and `ABSTRACT_SATISFIERS` move here from `prereq_graph.py` unchanged; `prereq_graph.py` re-exports `ABSTRACT_SATISFIERS` so `validator.py` keeps its import.

Approach for `parse_prereq_clause`: split into sentences; sentences matching a condition pattern add tokens; `concurrent` sets `concurrent_ok`; the remaining requirement text is split on `,` and ` and ` **at parenthesis depth 0**, each part has its outer parentheses stripped and is split on ` or ` into one OR-group; each option resolves through `expand_ids` (carrying the subject), else an abstract pattern, else an ambiguity of kind `"unresolved"` (truncated to 10 words). Options are kept even when the course is outside scope. `none` / `no prerequisites` → empty groups.

- [ ] **Step 1: Write the failing tests**, including:

```python
assert normalize_id("MATH 31 AH") == "MATH 31AH"
assert normalize_id("040A", "DSC") == "DSC 40A"
assert expand_ids("DSC 40A/R-B/R") == ["DSC 40A", "DSC 40B"]
assert parse_units("Seminar (2 or 4)") == (2.0, 4.0)
p = parse_prereq_clause("DSC 10/R, (MATH 20C or MATH 31BH) and (MATH 18 or MATH 20F or MATH 31AH). "
                        "Restricted to students within the data science major.", "DSC")
assert p.groups == [["DSC 10"], ["MATH 20C", "MATH 31BH"], ["MATH 18", "MATH 20F", "MATH 31AH"]]
assert p.conditions == ["major restriction"]
p = parse_prereq_clause("DSC 102 and (MATH 189 or DSC 152), and (DSC 140B or CSE 151A).", "DSC")
assert ["MATH 189", "DSC 152"] in p.groups
p = parse_prereq_clause("(MATH 20C or MATH 31BH) and (MATH 18 or MATH 31 AH).", "DSC")
assert ["MATH 18", "MATH 31AH"] in p.groups
p = parse_prereq_clause("a probability course; may be taken concurrently.", "DSC")
assert p.groups == [["<probability>"]] and p.concurrent_ok
p = parse_prereq_clause("satisfactory completion of an unusual requirement that nobody can parse at all here", "DSC")
assert len(p.ambiguities[0]["fragment"].split()) <= 10
```

- [ ] **Step 2: Run** `pytest tests/test_refresh_parse.py -v` — expect FAIL.
- [ ] **Step 3: Implement** both modules with the signatures above.
- [ ] **Step 4: Run** `pytest tests/ -q` — expect all pass.
- [ ] **Step 5: Commit** `feat: parse course IDs, units and prerequisite clauses`.

### Task 3: Catalog page parser and snapshot builder

**Files:**
- Create: `refresh/catalog.py`, `tests/fixtures/catalog_dsc.html`, `tests/fixtures/catalog_cse.html`
- Test: `tests/test_refresh_catalog.py`

**Interfaces:**
- Consumes: Task 1 `PoliteSession`, Task 2 functions.
- Produces:
  - `CATALOG_BASE = "https://catalog.ucsd.edu/courses/"`
  - `@dataclass CatalogCourse: id, department, title, units, units_max, units_text, prereq_groups, concurrent_ok, conditions, ambiguities, catalog_url, content_hash`
  - `parse_course_page(html: str, department: str, page_url: str) -> list[CatalogCourse]`
  - `parse_edition(html: str) -> str | None` (short edition label from `p.course-disclaimer`)
  - `build_catalog_snapshot(pages: dict[str, list[CatalogCourse]], scope_ids: list[str], previous: dict | None, fetched_at: str, edition: str | None) -> dict` — the `catalog.json` document:

```json
{"source": "https://catalog.ucsd.edu/courses/", "fetched_at": "...", "catalog_edition": "...",
 "courses": {"DSC 80": {"id": "DSC 80", "department": "DSC", "title": "...", "units": 4, "units_max": 4,
   "units_text": "4", "prereq_groups": [["DSC 30"], ["DSC 40A"]], "concurrent_ok": false,
   "conditions": ["major restriction"], "ambiguities": [], "catalog_url": "...#dsc80r",
   "content_hash": "sha256:...", "stale": false}},
 "referenced": {"DSC 152": {"defined": false}, "ECON 120A": {"defined": true}}}
```

Parser rules (spec "Refresh code"): iterate `p.course-name`; the course text is every following sibling up to the next `p.course-name` or heading, skipping `p.anchor-parent`; take the element's class-less `<p>` too. Strip a trailing `Tag:` element from the title. The anchor comes from the `a[id]` in the preceding `p.anchor-parent`; use `page_url#anchor` only if that anchor is unique on the page, else `page_url`. `content_hash` is SHA-256 of the whitespace-collapsed course text (the hash is stored, the text is not). Only courses whose number is < 200 are kept. A scope course absent from the fetched page keeps its `previous` record with `"stale": true`. `referenced` lists every prerequisite option not in scope, with `defined` true when any parsed page has it.

- [ ] **Step 1: Write fixtures** with invented text that copies the structure: a `p.anchor-parent` + `p.course-name` + `p.course-descriptions` triple; one course whose description `<p>` has **no class** (the bug scraper.py hit); two courses sharing anchor `dsc40r`; a CSE title ending in `<strong>Tag:</strong>…`; a graduate course `DSC 200`.
- [ ] **Step 2: Write the failing tests:**

```python
def test_description_without_class_is_not_shifted(): ...  # course after the class-less <p> gets its own prereqs
def test_r_suffix_is_normalized(): ...                     # "DSC 40B/R." -> id "DSC 40B"
def test_duplicate_anchor_links_to_page_only(): ...        # catalog_url == page_url for both dsc40r courses
def test_tag_is_stripped_from_title(): ...
def test_graduate_courses_are_skipped(): ...
def test_snapshot_keeps_stale_course_and_lists_referenced(): ...  # previous record kept with stale True; "DSC 152" defined False
def test_no_description_text_is_stored(): ...              # json.dumps(snapshot) contains no sentence from the fixture prose
```

- [ ] **Step 3: Run** `pytest tests/test_refresh_catalog.py -v` — expect FAIL.
- [ ] **Step 4: Implement** `refresh/catalog.py`.
- [ ] **Step 5: Run** `pytest tests/ -q` — expect all pass.
- [ ] **Step 6: Commit** `feat: parse catalog course pages into structured records`.

### Task 4: Hand files: scope with keywords, overrides carried over

**Files:**
- Create: `data/scope.json`
- Modify: `prereq_overrides.json`
- Test: `tests/test_scope.py`

**Interfaces:**
- Produces `data/scope.json`:

```json
{"_comment": "Hand-maintained. keywords are written by the owner; never copy catalog or department text.",
 "by_arrangement": ["DSC 197", "DSC 198", "DSC 199"],
 "courses": {"DSC 100": {"department": "DSC", "keywords": ["SQL", "relational databases", "normalization", "transactions", "NoSQL"],
                         "links": {"Course Site": "https://..."}}}}
```

- Produces new `prereq_overrides.json` keys, each entry with a `why`:
  - `"substitutes": [{"course": "CSE 151A", "replaces": "DSC 140A", "why": "..."}]`
  - `"advisory_edges": [{"from": "MATH 180A", "to": "DSC 140A", "why": "..."}]`
  - existing `add_edges` gains any hard forward edge the old build produced that the catalog line does not state.

- [ ] **Step 1: Capture the old facts before anything changes.** With the current code, dump `cg.substitutes`, `cg.advisory.edges`, and the forward edges into a scratch file (`python -c "from prereq_graph import build; ..."`; keep it out of the repo).
- [ ] **Step 2: Write `data/scope.json`** from `dsc_courses.json`: all 69 IDs with their `department`, the `🌐 Course Site` link (as `"Course Site"`), and 3–6 keywords per course drafted from the existing hand-written summary. Keywords are topic words, not sentences. Leave the catalog and CAPE links out (they are generated).
- [ ] **Step 3: Add the captured substitutes and advisories** to `prereq_overrides.json` with `why`: `"Carried over from the hand-written dataset (before 2026-11); the catalog prerequisite line does not state it. Owner to confirm."`
- [ ] **Step 4: Write the failing test** `tests/test_scope.py`:

```python
def test_scope_has_every_current_course(): ...   # 69 ids, each with department and non-empty keywords
def test_keywords_are_short(): ...               # every keyword <= 4 words, no '.' inside
def test_overrides_have_reasons(): ...           # every substitutes/advisory_edges/add_edges entry has a non-empty "why"
```

- [ ] **Step 5: Run** `pytest tests/test_scope.py -v` — expect PASS (the data was written first; the test pins it).
- [ ] **Step 6: Commit** `data: add course scope with keywords and carry reviewed edges into overrides`.

### Task 5: Graph reads the snapshot; first live catalog fetch

**Files:**
- Create: `refresh/run.py` (catalog part only), `data/catalog.json` (generated)
- Modify: `prereq_graph.py`, `tests/test_core.py`
- Test: `tests/test_core.py`, `tests/test_refresh_run.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `python -m refresh.run [--only catalog|offerings|classplanner ...] [--data-dir data] [--report refresh_report.md]`; `main(argv: list[str] | None = None, session: PoliteSession | None = None) -> int`
  - `prereq_graph.build(catalog_path=DATA/"catalog.json", scope_path=DATA/"scope.json", overrides_path=OVERRIDES_PATH) -> CourseGraph`
  - `CourseGraph` keeps every existing method and field and adds `by_arrangement: set[str]`, `referenced: dict[str, dict]`, `catalog_meta: dict` (`fetched_at`, `catalog_edition`).
  - `CourseGraph.courses[cid]` keys: `id`, `department`, `name` (= catalog title), `units`, `units_max`, `keywords`, `links` (hand links + `"Catalog": catalog_url`), `catalog_url`, `conditions`, `stale`.
  - `CourseGraph.satisfied` also accepts out-of-scope options: an option in `taken` satisfies its group even when it is not a node.
  - Graph edges are added only between in-scope courses; overrides `substitutes` fill `cg.substitutes`, `advisory_edges` fill `cg.advisory`.

- [ ] **Step 1: Rewrite the prose-dependent tests** in `tests/test_core.py`:
  - `test_forward_statement_points_the_right_way` → assert `MATH 20B → MATH 20C` exists and comes from `add_edges`.
  - `test_substitution_is_not_a_prerequisite` and `test_advisory_is_not_a_prerequisite` → same assertions, now fed by the override keys.
  - `test_out_of_catalog_references_are_reported_not_dropped` → `"MATH 31AH" in cg.referenced` and `"MATH 31AH"` is an option in one of DSC 40A's groups.
  - Add `test_dsc_180a_accepts_dsc_152` (`["MATH 189", "DSC 152"]` sorted is a group of DSC 180A) and `test_completed_out_of_scope_option_satisfies` (`cg.satisfied(["ECON 120A", "MATH 180A"], {"ECON 120A"})`).
- [ ] **Step 2: Write** `tests/test_refresh_run.py::test_catalog_run_writes_snapshot` using a fake session serving the Task 3 fixtures; assert `data/catalog.json` is written to `tmp_path` and the exit code is 0; and `test_catalog_shape_failure_keeps_previous` (fixture with no `p.course-name` → previous file unchanged, exit code 1 when it is the only source).
- [ ] **Step 3: Run** `pytest tests/ -q` — expect FAIL.
- [ ] **Step 4: Implement** the catalog part of `refresh/run.py` and the new `prereq_graph.build`. Subjects to fetch = unique `department` values in scope. The parsing code removed from `prereq_graph.py` now lives in `refresh/prereq_parse.py`.
- [ ] **Step 5: Live fetch once:** `python -m refresh.run --only catalog`. This makes 8–9 polite requests to `catalog.ucsd.edu`. Check the result: 69 courses, DSC 180A has `["MATH 189", "DSC 152"]`, DSC 123A has `["MATH 18", "MATH 31AH"]`, no description text in the file (`grep -c "Restricted to" data/catalog.json` is 0).
- [ ] **Step 6: Run** `pytest tests/ -q` and `python eval/run_eval.py --offline` — expect all pass and 9/9 fixtures. If a validator fixture now fails because the catalog changed a prerequisite, note it in the PR body rather than editing the fixture to pass.
- [ ] **Step 7: Commit** `feat: build the prerequisite graph from the generated catalog snapshot`.

### Task 6: Readers without descriptions; remove the old scraper

**Files:**
- Modify: `retrieval.py`, `app.py`, `ai_advisor.py`, `README.md`
- Delete: `scraper.py`, `dsc_courses.json`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: Task 5 `CourseGraph.courses[cid]` keys.
- Produces: `retrieval.build_documents(cg: CourseGraph, offerings=None) -> dict[str, str]` (the `offerings` argument is used from Task 13; now ignored).

- [ ] **Step 1: Write failing tests:** `test_documents_have_keywords_not_descriptions` (DSC 100 doc contains `"SQL"`; no doc contains `"Prerequisites:"` twice); keep `test_tfidf_finds_an_obvious_match`; add `test_tfidf_finds_sql` (`"SQL"` → DSC 100 in the top 3).
- [ ] **Step 2: Run** `pytest tests/ -q` — expect FAIL.
- [ ] **Step 3: Implement:**
  - `retrieval.build_documents`: replace the description with `"Topics: " + ", ".join(keywords)`.
  - `app.py`: build `df` from `COURSE_GRAPH.courses`; search over `id`, `name`, keywords; course view shows keywords as tags and a "Catalog entry" link to `catalog_url`; no description. Units display as `"2–4"` when `units_max > units`. CAPE links (`app.py:56`, `app.py:181`) become `https://set.ucsd.edu/` with the note "CAPE results end at Spring 2023"; HDSI links at `app.py:63` → `https://datascience.ucsd.edu/current-students/major-requirements/` and `app.py:67` → `https://datascience.ucsd.edu/current-students/academic-advising/`. `app.py:64` and `app.py:229` link text no longer mentions descriptions.
  - `ai_advisor.py`: remove the sentences about stats (Hours/Week, Assignment Load, Content Difficulty, GPA trends, exam difficulty); that data does not exist.
  - Delete `scraper.py` and `dsc_courses.json`.
  - `README.md`: replace the `dsc_courses.json` and scraper descriptions with the `data/` files and `refresh/`; course counts read 69; test counts match `pytest` output.
- [ ] **Step 4: Run** `pytest tests/ -q`, `python eval/run_eval.py --offline`, and `streamlit run app.py` — open the app, search "SQL", open DSC 100, confirm keywords and the catalog link show and nothing errors.
- [ ] **Step 5: Commit** `feat: replace course descriptions with keywords and catalog links`.
- [ ] **Step 6: Push the branch and open PR 1** (`gh pr create --base main`), body: summary, the DSC 180A / DSC 123A drift, the carried-over overrides that need the owner's confirmation, test results, and that the app was checked locally.

---

## PR 2 — offerings and `NOT_OFFERED`

### Task 7: Term labels

**Files:**
- Create: `terms.py`
- Test: `tests/test_terms.py`

**Interfaces:**
- Produces:
  - `Quarter = Literal["FA", "WI", "SP", "SU"]`
  - `@dataclass(frozen=True) Term: quarter: Quarter; year: int` with `.code -> str` (`"WI27"`), `.name -> str` (`"Winter 2027"`), `.academic_year -> str` (`"2026-27"` for FA26, WI27, SP27)
  - `parse_term(label: str) -> Term | None` — accepts `"Fall 2026"`, `"fall 2026"`, `"FA26"`, `"Winter 2027"`, `"WI27"`, `"SP27"`, `"Summer 2027"`/`"SU27"` (returns a SU term); returns `None` for `"Term 1"`, `"F"`, `"Fall"`.
  - `next_term(t: Term) -> Term` (FA→WI→SP→FA, summer skipped) and `terms_from(start: Term, n: int) -> list[Term]`
  - `term_from_code(code: str) -> Term`

- [ ] **Step 1: Write failing tests** for every accepted and rejected label above, `terms_from(Term("WI", 2027), 3)` → `["Winter 2027", "Spring 2027", "Fall 2027"]`, and `Term("FA", 2026).academic_year == "2026-27"`.
- [ ] **Step 2: Run** `pytest tests/test_terms.py -v` — expect FAIL.
- [ ] **Step 3: Implement** `terms.py`.
- [ ] **Step 4: Run** `pytest tests/ -q` — expect PASS.
- [ ] **Step 5: Commit** `feat: parse and step through quarter labels`.

### Task 8: Offerings snapshot and lookup

**Files:**
- Create: `offerings.py`, `data/offerings_manual.json`, `data/sources.json`
- Test: `tests/test_offerings.py`, `tests/fixtures/offerings_small.json`

**Interfaces:**
- Consumes: Task 7.
- Produces `data/offerings.json` shape (written by Task 11):

```json
{"generated_at": "...",
 "sources": {"classplanner": {"ok": true, "fetched_at": "...", "source_url": "...", "error": null}, "dsc": {...}},
 "scheduled": {"WI27": {"last_full_refresh_at": "...", "fetched_at": "...", "subjects": {"DSC": 31, "MATH": 0},
                        "courses": ["DSC 10", "DSC 20"]}},
 "tentative": {"2026-27": {"DSC": {"source_url": "...", "fetched_at": "...", "content_hash": "...",
                                   "status": "tentative", "courses": {"DSC 10": ["FA", "WI", "SP"]}}}}}
```

- `data/offerings_manual.json`: `{"2026-27": {"CHEM": {"entered_by": "...", "entered_at": "...", "source_url": "...", "courses": {"CHEM 6A": ["FA","WI","SP"]}}, "BIOL": {...}}}`. Fill in CHEM 6A/6B/6C/11 and the 5 BIOL-department courses from the public pages by reading them as a person (no automated fetch of `/ext/` on chem-web).
- `data/sources.json`: `{"2026-27": {"DSC": {"url": "...", "kind": "html"}, "CSE": {"url": "...", "kind": "csv"}, "MATH": {...}, "COGS": {...}, "PHYS": {...}, "ECE": {...}}}`, URLs from the research JSON.
- `offerings.py`:
  - `@dataclass OfferingStatus: kind: Literal["exempt","scheduled_offered","scheduled_absent","tentative_offered","tentative_other_quarters","tentative_unlisted","unknown"]; quarters: list[str]; academic_year: str | None; source_url: str | None; as_of: str | None`
  - `class Offerings: generated_at: str | None; available: bool; scheduled: dict[str, dict]; tentative: dict[str, dict]` (the two blocks of the file, manual entries merged into `tentative`)
    - `.lookup(course_id: str, department: str, term: Term, by_arrangement: set[str] = frozenset()) -> OfferingStatus`
    - `.summary(course_id: str, department: str) -> str` (e.g. `"2026-27 tentative: FA, SP · WI27 scheduled: yes"`, used by retrieval and the app)
  - `load_offerings(path: Path = DATA/"offerings.json", manual_path: Path = DATA/"offerings_manual.json") -> Offerings` — missing or invalid JSON → `Offerings` with `available=False` whose `lookup` always returns `unknown`.

Lookup order (spec "Validator: NOT_OFFERED"): exempt → scheduled (only when the course's subject prefix has a count > 0 in `scheduled[term.code]["subjects"]`) → tentative (official adapter data, else manual) → unknown. Summer → unknown.

- [ ] **Step 1: Write fixture** `tests/fixtures/offerings_small.json` covering WI27 scheduled for DSC (with DSC 10, not DSC 30) and MATH with count 0, and 2026-27 tentative for DSC (DSC 30 FA only), no SP27 scheduled block, and MATH (MATH 18 all three).
- [ ] **Step 2: Write failing tests:**

```python
def test_scheduled_absent(off): assert off.lookup("DSC 30", "DSC", Term("WI", 2027)).kind == "scheduled_absent"
def test_zero_course_subject_is_not_covered(off):   # MATH count 0 -> falls through to tentative
    assert off.lookup("MATH 18", "MATH", Term("WI", 2027)).kind == "tentative_offered"
def test_tentative_other_quarters(off): assert off.lookup("DSC 30", "DSC", Term("SP", 2027)).kind == "tentative_other_quarters"
def test_out_of_year_is_unknown(off): assert off.lookup("DSC 30", "DSC", Term("WI", 2028)).kind == "unknown"
def test_unlisted(off): assert off.lookup("DSC 999", "DSC", Term("SP", 2027)).kind == "tentative_unlisted"
def test_exempt(off): assert off.lookup("DSC 199", "DSC", Term("SP", 2027), {"DSC 199"}).kind == "exempt"
def test_manual_file_fills_chem(off): ...
def test_missing_file_is_unknown(tmp_path): assert not load_offerings(tmp_path/"none.json").available
def test_corrupt_file_is_unknown(tmp_path): ...
```

- [ ] **Step 3: Run** `pytest tests/test_offerings.py -v` — expect FAIL.
- [ ] **Step 4: Implement** `offerings.py`; write `data/sources.json` and `data/offerings_manual.json`.
- [ ] **Step 5: Run** `pytest tests/ -q` — expect PASS.
- [ ] **Step 6: Commit** `feat: offerings snapshot model and lookup`.

### Task 9: Class Planner client

**Files:**
- Create: `refresh/classplanner.py`, `tests/fixtures/cp_terms.json`, `tests/fixtures/cp_search_dsc.json`
- Test: `tests/test_refresh_classplanner.py`

**Interfaces:**
- Consumes: Task 1, Task 2 `normalize_id`.
- Produces:
  - `BASE = "https://classplanner.apps.ucsd.edu"`; `ALLOWED = {"classplanner.apps.ucsd.edu": ("/api/v1/public/",)}` (pass to `PoliteSession`)
  - `class SchemaError(Exception)`
  - `fetch_terms(session) -> list[dict]` — `GET /api/v1/public/catalog/terms`; each item must have `term_code`, `last_full_refresh_at`, `configured`.
  - `fetch_term_courses(session, term_code: str, subject: str) -> set[str]` — `POST /api/v1/public/catalog/courses/search` with `{"term_code": term_code, "subject_code": [subject], "limit": 48, "offset": n}`, paging until `offset + len(courses) >= total`; normalizes every course code with `normalize_id`; keeps only course IDs (no sections, no seats, no instructors).

- [ ] **Step 1: Check the live response shape once** by hand: one `GET .../terms` and one search `POST` for DSC WI27 through `PoliteSession`. Write the two fixtures by hand with the same keys and invented values. Do not save the live response.
- [ ] **Step 2: Write failing tests:** terms parsed; paging across two pages; `"DSC-080"` / `"080"` normalize to `"DSC 80"`; a missing `total` key raises `SchemaError`; a term with `configured: false` is skipped by the caller (assert in Task 11).
- [ ] **Step 3: Run** `pytest tests/test_refresh_classplanner.py -v` — expect FAIL.
- [ ] **Step 4: Implement** `refresh/classplanner.py`.
- [ ] **Step 5: Run** `pytest tests/ -q` — expect PASS.
- [ ] **Step 6: Commit** `feat: read term offerings from the Class Planner public API`.

### Task 10: Department tentative-plan adapters

**Files:**
- Create: `refresh/offerings/__init__.py`, `refresh/offerings/{dsc,cse,math,cogs,phys,ece}.py`, `tests/fixtures/offer_{dsc,math,phys,ece}.html`, `tests/fixtures/offer_{cse,cogs}.csv`
- Test: `tests/test_refresh_offerings.py`

**Interfaces:**
- Consumes: Task 2 `normalize_id` / `expand_ids`.
- Produces:
  - `class ShapeError(Exception)`
  - each module: `DEPARTMENT: str` and `parse(text: str, academic_year: str) -> dict[str, list[str]]` (course ID → sorted subset of `["FA","WI","SP"]`, summer columns ignored); raises `ShapeError` when the expected table or header is missing.
  - `ADAPTERS: dict[str, ModuleType]` keyed by department.

Per-adapter rules (details in the research JSON `dept_projected_offerings` section):
- DSC: table `#tablepress-4`, columns Course # / Title / Quarter; `DSC-040A`→`DSC 40A`; strip suffixes like `(1 IWC)`; split `DSC-190/291`; drop numbers ≥ 200.
- CSE: CSV header must match `Course #,Title,(Fall|Winter|Spring) \d{4}`; a non-empty cell in a quarter column means offered.
- MATH: HTML table with rowspans; reproduce the logical grid before reading cells.
- COGS: CSV `gid=866922720` only; collapse `A00`/`B00` section rows to one course.
- PHYS: headers from `<thead>` only (not `<tfoot>`).
- ECE: key on the catalog `href` fragment (`#ece108`); strip zero padding; ignore `<style>` blocks.

- [ ] **Step 1: Write fixtures** with invented rows copying each structure, plus `tests/fixtures/offer_html_instead_of_csv.txt` (an HTML page body).
- [ ] **Step 2: Write failing tests:** one happy-path test per adapter asserting two or three exact mappings; `test_csv_adapter_rejects_html` (`ShapeError` for both CSE and COGS); `test_math_rowspan`; `test_ece_uses_href_fragment` (broken text `ECE 10 8` with href `#ece108` → `ECE 108`); `test_dsc_drops_graduate_rows`.
- [ ] **Step 3: Run** `pytest tests/test_refresh_offerings.py -v` — expect FAIL.
- [ ] **Step 4: Implement** the six adapters.
- [ ] **Step 5: Run** `pytest tests/ -q` — expect PASS.
- [ ] **Step 6: Commit** `feat: parse department tentative course plans`.

### Task 11: Offerings refresh run; first live fetch

**Files:**
- Modify: `refresh/run.py`
- Create: `data/offerings.json` (generated)
- Test: `tests/test_refresh_run.py`

**Interfaces:**
- Consumes: Tasks 8–10.
- Produces: `main()` handles `--only offerings` (department adapters from `data/sources.json`, every academic year listed there) and `--only classplanner` (every term with `configured: true`, every subject prefix in scope). Each source records `ok`, `fetched_at`, `source_url`, `error`; a failed source keeps its previous block. Exit code 1 only when every selected source failed.

- [ ] **Step 1: Write failing tests** with a fake session: `test_failed_adapter_keeps_previous_block` (CSE returns HTML → previous CSE block unchanged, `sources.cse.ok` false, exit code 0 because others succeeded); `test_unconfigured_term_skipped`; `test_all_sources_failed_exits_1`.
- [ ] **Step 2: Run** — expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Live fetch once:** `python -m refresh.run --only offerings classplanner`. Check: WI27 and FA26 present; DSC 2026-27 block present; no instructor names (`grep -ci "staff\|instructor" data/offerings.json` is 0).
- [ ] **Step 5: Run** `pytest tests/ -q` — expect PASS.
- [ ] **Step 6: Commit** `feat: refresh offerings from departments and the Class Planner`.

### Task 12: Validator rule `NOT_OFFERED`

**Files:**
- Modify: `validator.py`, `eval/run_eval.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: Task 7 `parse_term`, Task 8 `Offerings`, `load_offerings`.
- Produces: `validate(plan, cg=None, completed=(), offerings: Offerings | None = None) -> list[Violation]` and the same new argument on `is_legal`. `offerings=None` loads the default snapshot once (module-level cache).

Messages (code `NOT_OFFERED` for all three):
- error: `f"{course} is not on the published {term.name} Schedule of Classes (Class Planner, refreshed {as_of})."`
- warning, other quarters: `f"{course} is listed for {', '.join(quarter names)} only in the {department} {academic_year} tentative plan, not {quarter name}."`
- warning, unlisted: `f"{course} is not on the {department} {academic_year} tentative course list; check the Schedule of Classes."`

- [ ] **Step 1: Write failing tests** using `tests/fixtures/offerings_small.json`: error for DSC 30 in `"Winter 2027"`; warning (other quarters) for DSC 30 in `"Spring 2027"` (no SP27 scheduled block; DSC 30 listed FA only → "listed for Fall only" wording); warning (unlisted); no finding for `"Term 1"`, `"Summer 2027"`, `"Fall 2030"`, DSC 199; no finding when `offerings.available` is false; warnings do not change `is_legal`.
- [ ] **Step 2: Add `VALIDATOR_FIXTURES`** entries `("not-offered-scheduled", False, ...)` and `("not-offered-tentative-is-legal", True, ...)`; make `run_validator_fixtures` pass the fixture offerings file so results do not change with live data.
- [ ] **Step 3: Run** `pytest tests/ -q` — expect FAIL.
- [ ] **Step 4: Implement** the rule in the per-course loop of `validate()`, using `cg.courses[course]["department"]` and `cg.by_arrangement`.
- [ ] **Step 5: Run** `pytest tests/ -q` and `python eval/run_eval.py --offline` — expect PASS, 11/11 fixtures.
- [ ] **Step 6: Commit** `feat: flag courses planned in quarters they are not offered`.

### Task 13: Planner, retrieval and app use real quarters

**Files:**
- Modify: `planner.py`, `retrieval.py`, `app.py`, `ai_advisor.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: Tasks 7, 8, 12.
- Produces:
  - `planner.default_start_term(offerings: Offerings, today: date) -> Term` — the latest term in `offerings.scheduled`, else the next Fall after `today`.
  - `planner.eligible_now(cg, taken, term: Term | None = None, offerings: Offerings | None = None) -> list[str]` — drops `scheduled_absent` courses for `term`.
  - `plan_iterative(..., start_term: str | None = None, offerings: Offerings | None = None)` labels terms with `Term.name` from `terms_from(start, n_terms)`; each course row in the prompt includes `offerings.summary(...)`.
  - `retrieval.build_documents(cg, offerings)` appends `"Offered: " + summary`.

- [ ] **Step 1: Write failing tests:** `test_eligible_drops_scheduled_absent` (DSC 30 not eligible for WI27 with the fixture, eligible with `term=None`); `test_default_start_term_uses_latest_scheduled` (`WI27`); `test_default_start_term_without_data` (`today=date(2026,11,12)` → `Fall 2027`); `test_documents_include_offerings`.
- [ ] **Step 2: Run** — expect FAIL.
- [ ] **Step 3: Implement** planner and retrieval changes. Then `app.py`:
  - sidebar caption `f"Catalog as of {catalog date} · Offerings as of {offerings date}"`, or `"Offerings unavailable"` when `not offerings.available`;
  - banner `st.info("Quarter offerings are tentative department plans unless marked scheduled. Check the Schedule of Classes before you enroll.")`;
  - course view: the offerings summary and a link to `https://classplanner.apps.ucsd.edu/search`;
  - My Plan: an academic-year selectbox (current and next academic year, default from `default_start_term`); plan term labels become `f"{q} {year}"` (Fall uses the start year, Winter/Spring/Summer the next) before calling `validate`;
  - auto planner: a start-term selectbox passed as `start_term`.
  - `ai_advisor.py`: the prompt's course rows already come from retrieval, so they carry offerings; add one sentence: offerings marked tentative may change.
- [ ] **Step 4: Run** `pytest tests/ -q`, `python eval/run_eval.py --offline`, then `streamlit run app.py`: put DSC 30 in Winter 2026-27 in My Plan and see the `NOT_OFFERED` result; rename `data/offerings.json` temporarily and confirm the app shows "Offerings unavailable" and still validates; restore it.
- [ ] **Step 5: Commit** `feat: plan with real quarter names and show offerings in the app`.
- [ ] **Step 6: Push and open PR 2**, body: summary, test results, what the app check covered, the manual CHEM/BIOL entries and their sources.

---

## PR 3 — weekly refresh

### Task 14: Refresh report

**Files:**
- Create: `refresh/report.py`
- Modify: `refresh/run.py`, `.gitignore` (add `refresh_report.md`, `.refresh_cache/`)
- Test: `tests/test_refresh_report.py`

**Interfaces:**
- Produces:
  - `diff_catalog(old: dict, new: dict) -> list[str]` — per course: added/removed course, title change, units change, prerequisite options added or removed per group, condition changes, new ambiguities (fragment + catalog link), `stale` changes.
  - `diff_offerings(old: dict, new: dict) -> list[str]` — per course and per academic year or term: quarters gained or lost; new or vanished terms.
  - `render_report(catalog_lines, offering_lines, sources: dict, tests_summary: str | None) -> str` — Markdown: a "Sources" table first (failed sources at the top, each with its error), then "Catalog changes", "Offering changes", "Tests". From March to June it adds "No plan found for next academic year: …" for each department missing from `data/sources.json` for the next year.
  - `run.main` writes the report to `--report` and uses `.refresh_cache/` as the `PoliteSession` cache dir.

- [ ] **Step 1: Write failing tests:** `test_prereq_option_added_is_reported` (DSC 180A gains `DSC 152` → a line naming DSC 180A and DSC 152); `test_failed_source_listed_first`; `test_no_changes_says_so`; `test_next_year_reminder_in_march` (inject `today`).
- [ ] **Step 2: Run** — expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/ -q` — expect PASS.
- [ ] **Step 5: Commit** `feat: write a readable refresh report`.

### Task 15: Weekly workflow and docs

**Files:**
- Create: `.github/workflows/refresh.yml`
- Modify: `.github/workflows/tests.yml` (comment only: drop the hard-coded "27"), `README.md`, `docs/DATA_SOURCES.md` (link the spec and mark plan steps done)

**Workflow requirements:**
- `on: schedule: - cron: "0 15 * * 1"` (Mondays 15:00 UTC) and `workflow_dispatch`.
- `permissions: contents: write, pull-requests: write`; `concurrency: data-refresh`.
- Steps: checkout; setup-python 3.11 with pip cache; `pip install -r requirements.txt pytest`; `python -m refresh.run --report refresh_report.md` (a non-zero exit fails the job after the report is uploaded as an artifact); `pytest tests/ -q` and `python eval/run_eval.py --offline` with `continue-on-error: true`, their summary lines appended to the report; if `git status --porcelain data/` is non-empty: commit as `github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>` on branch `data-refresh` (`git switch -C data-refresh`, `git push --force`), then `gh pr edit data-refresh --body-file refresh_report.md` if a PR exists, else `gh pr create --base main --head data-refresh --title "Data refresh $(date -u +%F)" --body-file refresh_report.md`. `GH_TOKEN: ${{ github.token }}`.
- No secrets other than `github.token`.

- [ ] **Step 1: Write the workflow.**
- [ ] **Step 2: Lint it:** `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/refresh.yml'))"` and, if available, `actionlint`.
- [ ] **Step 3: Update `README.md`:** data sources and refresh cadence, the freshness banner, the derived-facts policy (no catalog or department prose; owner-written keywords), the one-time repository setting, and test counts as `pytest` reports them. Leave the 40% → 100% table labelled as the pre-rebuild measurement.
- [ ] **Step 4: Run** `pytest tests/ -q` and `python eval/run_eval.py --offline` — expect PASS.
- [ ] **Step 5: Commit** `ci: refresh course data weekly and open a PR`.
- [ ] **Step 6: Push and open PR 3.** In the body, ask the owner to enable Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests", then run the workflow once with `workflow_dispatch` after merge. The first real run is verified only after that.

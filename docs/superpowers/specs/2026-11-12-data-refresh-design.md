# Data refresh pipeline and quarter offerings (project A)

Date: 2026-11-12. Owner: Zhen Wang (zhenzhenfufu).
Background research: `docs/DATA_SOURCES.md` (summary) and
`docs/research/data-sources-2026-11-12.json` (raw findings, selectors, quotes).

This is the first of three projects the owner asked for, in this order:

- **A. Data pipeline (this document):** keep the tutor's course data current
  from UCSD's public pages and add quarter offerings.
- **B. Wider coverage:** electives and courses from other majors that DS
  students take. A is designed so that B mostly means adding config.
- **C. 3D relationship graph:** a 3D network view of courses, prerequisites
  and offerings, built on the data model A and B settle.

## Intent

The owner wants the tutor to stop going stale. Today every course fact in the
app was written by hand once (`dsc_courses.json`, 69 courses in 8 departments),
and nothing tells the planner which quarters a course actually runs. A plan can
pass every prerequisite check and still schedule a course in a quarter it is
not taught.

The owner asked for "APIs that keep the tutor up to date in real time". UCSD
has no official public course API, and the closest thing to live data, the
Class Planner's public JSON, is itself refreshed every few days. So the target
is: **a scheduled job pulls UCSD's public pages and the Class Planner's public
endpoints, turns them into structured facts, and proposes the update as a PR;
CI checks it; the owner merges; Streamlit Cloud redeploys from `main`.**

## Decisions already made by the owner

| Decision | Choice |
|---|---|
| Order of projects | A, then B, then C |
| Refresh cadence | Weekly cron plus a manual `workflow_dispatch` button |
| `NOT_OFFERED` severity | Tiered: tentative list says not this quarter, or does not list the course = **warning**; the published term schedule confirms it is absent = **error**; outside the covered years = no finding; by-arrangement courses exempt |
| Catalog text | Store structured facts and links only; do not store or show catalog or department prose. No permission emails. |
| Topic search | Keep a short owner-written keyword list per course in place of descriptions |

## Goals

1. **Catalog snapshot generated, not hand-written.** For every in-scope course:
   ID, title, units, parsed prerequisite groups, non-course conditions, and a
   link to the catalog. Fixes the `scraper.py` index-zip bug and the `/R` IDs.
2. **Offerings layer.** For every in-scope course and quarter: offered or not,
   with status `scheduled` (Class Planner, current and next term) or
   `tentative` (department annual plan), plus source URL and fetch time.
3. **Validator rule `NOT_OFFERED`** with the tiered severity above.
4. **Planner uses real quarters.** Plans are labelled `Fall 2026`,
   `Winter 2027`, … from a chosen start term, so `NOT_OFFERED` can apply, and
   the term-by-term planner does not offer courses that are confirmed absent.
5. **Weekly refresh workflow** that opens one PR with a readable per-course
   diff, after running the offline tests itself.
6. **App shows freshness and sources:** "data as of …", a "tentative — check
   the Schedule of Classes" banner, offered quarters per course, links out.
7. **Polite, safe fetching** everywhere (rules below).

## Non-goals (for A)

- Degree-requirement checking (major core, electives, catalog year). The
  validator checks prerequisites, order, units and now offerings, nothing more.
  Catalog-year versioning matters for degree requirements, not for
  prerequisites, which are enforced as currently published.
- Major or standing restrictions as validator rules. They are parsed and
  stored as conditions, but not enforced.
- Expanding the course list beyond the current 69 courses (that is B).
- Historical "usually offered in" from the SheepTester TOMLs or the legacy
  act.ucsd.edu Schedule of Classes. Useful for years with no published plan;
  left for later.
- Seat counts, instructors, times, sections. Never stored.
- Anything behind SSO: TSS, api.ucsd.edu, CAPE results, SET, DARS,
  `classplanner…/api/v1/planner/*`, `/api/v1/catalog/*`, `/api/v1/user-state`.
- Daily freshness checks. Possible later (one request to the Class Planner
  `terms` endpoint per day); the owner chose weekly for now.

## Anti-goals (would make this a failure even if it runs)

- Committing or displaying verbatim catalog or department prose.
- Turning "not listed on a tentative plan" into a hard error.
- A refresh that silently overwrites good data with a broken parse (a
  department re-keys a Google Sheet and we commit an HTML error page as data).
- Hammering UCSD hosts, ignoring robots, or touching SSO.
- Saving real UCSD pages as test fixtures in the public repo.
- Bot PRs nobody can read: a diff of a 3,000-line JSON with no summary.
- README claims that stop being true (including the 40% → 100% result, which
  predates the October rebuild and must not be restated as current).

## Constraints

- **Fetching manners.** User-Agent `ucsd-course-planning-tutor (student project)`.
  At most 1 request per second per host. Honor robots with a wildcard-aware
  parser (`protego`; `urllib.robotparser` ignores Blink's `Disallow: *.pdf`).
  Conditional GET where supported (catalog sends ETag and Last-Modified).
  Never follow a redirect to `a5.ucsd.edu`: treat it as a hard stop for that
  source. Timeouts and a small retry with backoff.
- **No credentials.** No cookies, no personal tokens, nothing from `.env` in
  CI. `GEMINI_API_KEY` is never needed by the refresh.
- **Stored data = derived facts.** IDs, titles, units, prerequisite groups,
  condition tokens, quarter booleans, `source_url`, `fetched_at`,
  `content_hash`. No descriptions, no instructor names, no raw responses.
- **Last good snapshot wins.** A source that fails its header or schema check
  keeps its previous data; the PR says so.
- **Python 3.11**, same as CI and the devcontainer. New dependency: `protego`.
- **Offline tests stay offline.** `pytest tests/ -q` and
  `python eval/run_eval.py --offline` must not touch the network.

## Sources used in A

All verified on 2026-11-12; details and selectors are in the research JSON.

| What | Source | Status it gives |
|---|---|---|
| IDs, titles, units, prerequisites | `catalog.ucsd.edu/courses/{DSC,MATH,CSE,PHYS,BIOL,CHEM,COGS,ECE}.html` | catalog facts |
| This term and next term | Class Planner `GET /api/v1/public/catalog/terms`, `POST /api/v1/public/catalog/courses/search` | `scheduled` |
| DSC annual plan | `datascience.ucsd.edu/current-students/course-offerings/` (`#tablepress-4`) | `tentative` |
| CSE annual plan | published Google Sheet CSV (assert header) | `tentative` |
| MATH annual plan | `math.ucsd.edu/students/planned-course-offerings?year=…` | `tentative` |
| COGS annual plan | Google Sheet CSV, `gid=866922720` only | `tentative` |
| PHYS annual plan | `physics.ucsd.edu/students/courseofferings` | `tentative` |
| ECE annual plan | `ece.ucsd.edu/ece-tentative-course-list` | `tentative` |
| CHEM, BIOL | hand-entered file, updated yearly (CHEM robots-disallowed; BIOL APIs undocumented) | `tentative` |

The Class Planner check on 2026-11-12: `/api/v1/public/catalog/terms` answered
200 without login and listed FA26 (refreshed 2026-11-11) and WI27 (refreshed
2026-11-06). Its `robots.txt` redirects to a login page, so the host publishes
no robots policy; only `/api/v1/public/*` is used.

## Design

### Data files

Generated files are written only by the refresh job; hand files only by people.

| File | Kind | Contents |
|---|---|---|
| `data/scope.json` | hand | The in-scope course IDs (today's 69), by-arrangement exemptions, per-course hand links (e.g. course website), and per-course `keywords`: a short list of topic words written by the owner, never copied from the catalog or a department page (e.g. DSC 100: `SQL, relational databases, normalization, transactions, NoSQL`). B grows this list. |
| `data/catalog.json` | generated | One record per in-scope course: `id`, `department`, `title`, `units` and `units_max` (equal for fixed-unit courses; for `2 or 4`, `1–4` or `1 to 12` the minimum and maximum, and the validator uses `units`, the minimum — my call), `units_text`, `prereq_groups` (AND of OR, may name out-of-scope or undefined courses), `concurrent_ok`, `conditions` (standing, major restriction, consent, GPA, as tokens), `ambiguities` (each: a category, the unparsed fragment capped at about ten words, never a full sentence, and the catalog anchor — my call: a short prerequisite fragment is a fact, and the weekly PR must be reviewable), `catalog_url` (page + anchor), `content_hash`. Plus `referenced` — courses named in prerequisites that are not in scope, with whether the catalog defines them. Top-level `source`, `fetched_at`, `catalog_edition`. |
| `data/offerings.json` | generated | Keyed by academic year, holding every year a source currently publishes (in spring that is both the current and the next year), plus Class Planner terms by term code. Per source: `source_url`, `fetched_at`, `content_hash`, `status`, `academic_year` or `term_code`, `ok`. Per course: quarters offered, keyed by source. |
| `data/sources.json` | hand | Per department, the offering-plan URL for each academic year (Google Sheet IDs and gids, the ECE page, the MATH `?year=` value, the DSC table ID). Year-tied sources need a hand edit when a department posts next year's plan; the refresh report flags "no plan found for next year" from March on so the owner knows when. My call: no automatic URL discovery. |
| `data/offerings_manual.json` | hand | CHEM and BIOL quarters for the year, with who entered them and when. |
| `prereq_overrides.json` | hand | Unchanged role: reviewed corrections the catalog text cannot carry. |

`dsc_courses.json` is retired once nothing reads it.

### Refresh code (`refresh/` package)

- `refresh/http.py` — the only way any refresh code touches the network:
  UA, per-host 1 s spacing, `protego` robots check (cached per host), ETag /
  Last-Modified cache, SSO-redirect stop, timeouts, retries.
- `refresh/catalog.py` — parses course pages by walking siblings after each
  `p.course-name`; strips `Tag:`; reads units from the last parenthesised
  group; finds the prerequisite clause with `/Prerequisites?\s*:/` over
  `get_text()`; normalizes IDs (`/R` suffix, implied subjects, hyphen
  sequences like `181A-B-C`); splits course groups from non-course conditions.
  The prerequisite parsing logic that lives in `prereq_graph.py` today moves
  here, so it runs at refresh time on the fetched page and only its output is
  committed.
- `refresh/classplanner.py` — terms list, then course search per subject,
  zero-padded codes normalized (`040A` → `DSC 40A`), response schema checked.
- `refresh/offerings/{dsc,cse,math,cogs,phys,ece}.py` — one adapter each,
  returning `{course_id: set(quarters)}` for one academic year, or raising a
  clear error if the page shape is not what it expects (header assertion).
- `refresh/run.py` — runs everything, applies "last good snapshot wins",
  writes the generated files, and writes `refresh_report.md` (the PR body).

`scraper.py` is deleted (it is the bug the research found, and it writes fake
stats).

### Prerequisite graph

`prereq_graph.build()` reads `data/catalog.json` groups plus
`prereq_overrides.json` instead of parsing description prose. The graph's
public API (`CourseGraph`, `satisfied`, `missing_groups`, `concurrent_ok`,
`units`, `known`, `topo_layers`, `unlocks`) stays the same so validator,
planner, retrieval and app keep working.

Two behaviours change:

- OR-groups keep every option the catalog names, including out-of-scope
  courses (e.g. `ECON 120A`). A completed out-of-scope course satisfies its
  group; planning one is still `UNKNOWN_COURSE`.
- Prerequisites the current hand-written descriptions phrase as "prerequisite
  for X" (forward statements) and "accepted as alternative to" (substitutions)
  are not catalog text, so they disappear with the descriptions. Any of those
  that are real get re-entered in `prereq_overrides.json` with a reason.

### Validator: `NOT_OFFERED`

For each course in each term:

1. Parse the term label to (quarter, year). Accept `Fall 2026`, `FA26`,
   `Winter 2027`, `WI27` and similar. Unparseable labels (`Term 1`, `F`) or
   summer terms produce no finding.
2. Exempt courses listed as by-arrangement in `data/scope.json`
   (DSC 197/198/199 at least).
3. If the Class Planner has that term: course absent → **error**
   `NOT_OFFERED` ("not on the published Winter 2027 Schedule of Classes").
4. Otherwise, if a tentative plan covers that academic year for the course's
   department: listed but not in that quarter, or not listed at all →
   **warning** `NOT_OFFERED`, worded differently for the two cases ("listed
   for Fall and Spring only" vs "not on the 2026-27 tentative list").
5. Otherwise: no finding.

`validate()` gains an optional `offerings` argument (defaulting to the loaded
snapshot) so tests and fixtures can pass a fixed one. Offerings never change
`is_legal()` except through step 3.

### Planner

- `plan_iterative` takes a start term (default: the next term the Class
  Planner lists, else the next Fall) and labels terms with real names.
- The per-term eligible set drops courses that would get the step-3 error and
  shows tentative ones with their quarters in the course details, so the
  model can avoid warnings without being forbidden.

### Retrieval

Each course document becomes: ID, title, units, department, prerequisite
expression, what it unlocks, substitutes, quarters offered, and the owner's
`keywords`. No description. The keywords keep topic questions ("which course
teaches SQL") working.

The first keyword lists are drafted from the current hand-written summaries
in `dsc_courses.json` (paraphrases already in the repo, not catalog text) and land in PR 1 for the owner to review. The embedding cache key
already includes a content hash, so it rebuilds itself.

### App

- Course detail: title, units, prerequisites, offered quarters with status
  and date, link to the catalog anchor and to the Class Planner search. No
  description text.
- Search: over ID, title and keywords. Keywords are shown as tags.
- Header or sidebar: "Catalog data as of …, offerings as of …" and the
  tentative banner.
- My Plan: add an academic-year selector so the four quarter tabs map to real
  terms (`Fall 2026` …) for `NOT_OFFERED`.
- Link fixes from the research: CAPE links point to `set.ucsd.edu` with a
  note that CAPE data ends Spring 2023 (`app.py:56`, `app.py:181`); dead HDSI
  links at `app.py:63` and `app.py:67` replaced.

### Refresh workflow (`.github/workflows/refresh.yml`)

- Triggers: weekly cron and `workflow_dispatch`.
- Steps: install deps, `python -m refresh.run`, `pytest tests/ -q`,
  `python eval/run_eval.py --offline`, then if any generated file changed,
  create or update one PR from branch `data-refresh` with
  `refresh_report.md` as the body.
- Report contents: per course, added or removed prerequisite options, unit
  or title changes, offering changes per quarter, new or vanished courses,
  new ambiguities; per source, ok / failed / unchanged with dates; test
  results.
- A source failure keeps old data and is listed at the top of the report; if
  every source fails, the job fails so GitHub emails the owner.
- Permissions: `contents: write`, `pull-requests: write`. A PR opened with
  the default `GITHUB_TOKEN` does not trigger `tests.yml`, which is why the
  refresh job runs the tests itself and puts the result in the PR body.
  Checked 2026-11-12: `main` has no branch protection or rulesets, so a bot
  PR without the `tests` check is not blocked. No personal access token is
  used.
- **Owner setup step:** enable "Allow GitHub Actions to create and approve
  pull requests" in the repository settings (Settings → Actions → General).
  On 2026-11-12 it is off (`can_approve_pull_request_reviews: false`,
  default workflow permissions `read`).

### Tests

- Parser tests use small hand-written HTML / CSV / JSON snippets that copy
  the structure of each source (class names, table shapes, header rows), not
  saved UCSD pages.
- Required cases: the sibling walk (a description `<p>` with no class), `/R`
  normalization, unit forms (`2 or 4`, `1–4`, `4-4-4`, `1 to 12`), implied
  subjects and hyphen sequences, `Tag:` stripping, header-assertion failure
  keeps the last snapshot, SSO redirect stops a source, robots wildcard deny.
- Validator: `NOT_OFFERED` error, both warning wordings, exemption,
  unparseable term, out-of-year term — with a fixed offerings fixture. Add
  matching entries to `VALIDATOR_FIXTURES`.
- The existing 27 tests are kept in spirit; those that test prose parsing
  (forward, substitution, advisory statements) are rewritten against the new
  parser and overrides.

### README

Describe the refresh, the sources, the freshness banner and the derived-facts
policy. Do not restate the 40% → 100% result as current.

## Delivery

Work on a branch; several small PRs, never a push to `main`:

1. Polite fetcher + catalog parser + `data/catalog.json` + graph reads it +
   descriptions replaced by keywords (app and retrieval adjusted).
2. Offerings adapters + Class Planner + `NOT_OFFERED` + planner real terms +
   app freshness.
3. Refresh workflow + report.

## Known data drift found during design

Comparing the stored prerequisites with the live DSC catalog page on
2026-11-12: DSC 180A now accepts `MATH 189 or DSC 152` (DSC 152 has no catalog
entry yet), and DSC 123A now accepts `MATH 18 or MATH 31AH`. The first
generated snapshot should show both in its PR.

## Resolved after review

- **Course summaries (owner, 2026-11-12):** the `description` field in
  `dsc_courses.json` turned out to be a hand-written paraphrase, not catalog
  text. Descriptions are removed; each course keeps a short owner-written
  `keywords` list instead.
- **Several academic years at once, year-tied URLs, ambiguity fragments,
  branch protection:** settled in the sections above (`data/sources.json`,
  `data/offerings.json`, `data/catalog.json`, refresh workflow).

## Left to the builder

Module and function names inside `refresh/`; exact report formatting; the
cron day and hour; how term labels are parsed beyond the forms listed;
fixture contents.

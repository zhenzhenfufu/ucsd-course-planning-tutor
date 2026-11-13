# Keeping the planner's data current: UCSD sources

Research date: 2026-11-12. Five researchers each fetched real pages for one
source family. An independent agent then re-fetched every claim. The full
findings and verdicts, with selectors, column headers and quoted robots and
terms lines, are in `docs/research/data-sources-2026-11-12.json`. This file
is the summary and the plan.

## Bottom line

- **UCSD has no official public API for courses, the catalog, terms or the
  Schedule of Classes.**
  - `api.ucsd.edu` (WSO2) needs SSO to list APIs.
  - TSS (`tss.ucsd.edu`, the new SIS) is SSO-only. It is the official
    Schedule of Classes from Fall 2026.
  - CAPE, SET and the degree audit (DARS) are all SSO.
- **"Real time" is not available.** The realistic target is a scheduled
  refresh: a GitHub Actions cron fetches public pages, builds a structured
  snapshot, and opens a PR with a diff. CI (`tests.yml`) runs on that PR, and
  a person merges it.
- **The biggest gap today is offerings, not prerequisites.** The validator does
  not know which quarters a course is offered in, so a plan can be legal on
  prerequisites and still schedule a course that does not run that term.

## Sources, by what they give the planner

### 1. Prerequisites, units, course IDs: the General Catalog (public, automatable)

- **Course pages:** `https://catalog.ucsd.edu/courses/{DSC,MATH,CSE,PHYS,BIOL,CHEM,COGS,ECE}.html`
  - Static HTML, with no robots.txt (404).
  - Conditional GET works (ETag returns 304).
  - The whole site was batch-republished on 2026-11-04. Detect changes by
    hashing each course's normalized text, not by `Last-Modified`.
- **Major requirements:** `https://catalog.ucsd.edu/curric/DSC-ug.html`
  - The lower-division and core lists parse cleanly into AND-of-OR groups.
  - The subject-domain and elective rules are prose. Keep those hand-curated,
    and alert when the hash of that section changes.
- **Catalog-year snapshots:** `https://catalog.ucsd.edu/archive/{YYYY-YY}/...`,
  available back to 2021-22.
  - Requirements bind by catalog year. The live "Interim Update" is "for
    information and advising purposes only", so keep it as an advisory layer.
  - Concrete case: the DS core changed from `MATH 189` to `MATH 189 or DSC 152`,
    and `DSC 152` has no catalog entry yet. The validator needs a rule for
    courses that are referenced but undefined.
- **Parser pitfalls the current `scraper.py` hits:**
  - It zips `p.course-name` with `p.course-descriptions` by index, but some
    description `<p>` tags have no class. On today's DSC page every description
    from DSC 40B/R onward lands on the wrong course. Walk siblings instead.
  - Units come in forms like `2 or 4`, `1–4`, `4-4-4` and `1 to 12`.
  - CSE titles carry a trailing `Tag:` element.
  - Prerequisite labels use many tag variants. Split on `/Prerequisites?\s*:/`
    over `get_text()`.
  - IDs now carry `/R` suffixes (`DSC 10/R`), and subjects are implied in text
    (`DSC 20/R and 40A/R`, `181A-B-C`).
  - The anchor `dsc40r` is used for both 40A/R and 40B/R.

### 2. Which quarters a course runs this year: department tentative offerings (the annual plan)

These pages are the only official look-ahead for the year. Treat every entry
as **tentative**.

| Dept | Source | Format | Automate? |
|---|---|---|---|
| DSC | `datascience.ucsd.edu/current-students/course-offerings/` | WordPress TablePress `#tablepress-4` (Course # / Title / Quarter); `/wp-json/wp/v2/pages?include=19449` gives `modified` | yes |
| CSE | `cse.ucsd.edu/undergraduate/tentative-course-offerings` | published Google Sheet; CSV via 307 redirect | yes, assert header |
| MATH | `math.ucsd.edu/students/planned-course-offerings?year=2026-2027` | HTML table with rowspans | yes |
| COGS | `cogsci.ucsd.edu/undergraduates/courses/` | Google Sheet CSV, `gid=866922720` only (never the staffing tabs) | yes |
| PHYS | `physics.ucsd.edu/students/courseofferings` + `/typical-course-frequencies-terms` | HTML | yes |
| ECE | `ece.ucsd.edu/ece-tentative-course-list` | HTML, key on the catalog href fragment | yes |
| ECON (optional) | `economics.ucsd.edu/undergraduate-program/resources/courses/` | HTML table | yes, if electives need it |
| CHEM | `chem-web.ucsd.edu/ext/ugcourses.html` | robots `Disallow: /ext/` | **no**: enter by hand each year (4 courses) |
| BIOL | Angular app over undocumented APIs | unverified | **no**: ask the department first; enter the 5 courses by hand |

What the data means:
- If a course is missing from a list, mark it "not listed", never "not offered".
- DSC 197/198/199 are by arrangement and must be exempt.
- Some courses alternate years (MATH 182 ran in 2025-26 and is absent in
  2026-27). Label any fallback to a previous year as a guess.
- Prefer the tables over the DSC FAQ prose; the two disagree for DSC 102, 106
  and 148.
- Physics posts upcoming prerequisite changes ("Pilot Prereqs"). Add them to
  the prerequisite review queue.

### 3. The term's actual schedule

- **Official UCSD Class Planner:** `classplanner.apps.ucsd.edu`
  - The Blink enrollment calendar now links its "Schedule of Classes" row here.
  - One verifier found unauthenticated JSON under `/api/v1/public/catalog/terms`
    and `/api/v1/public/catalog/courses/search`. These return terms with
    `last_full_refresh_at`, per-course sections and prerequisite strings.
  - Another researcher found `/api/v1/planner/*` returning 401. **Re-verify
    which endpoints are public before building on them.**
  - The API is undocumented and refreshes periodically, not in real time.
  - Use only `/api/v1/public/*`, validate the schema, and keep the last good
    snapshot if it fails.
- **Legacy act.ucsd.edu Schedule of Classes:** public, but frozen at SU26 and
  expected to retire around mid-December 2026.
  - Useful once, for history before it goes. Do this by hand or with a single
    `workflow_dispatch` run, not a recurring scraper.
- **History for "usually offered in":** the MIT-licensed
  `SheepTester-forks/ucsd-historical-schedule-of-classes` (TOML per term,
  WI95–SU26).
  - Import it once and compute quarter frequency per course.
  - Use the result as a soft hint, never a hard rule.
- **Optional unofficial signal:** `alchin2/tssplusplus` `data/offered/<term>.csv`.
  - Pin it to a commit SHA.
  - Show it as "reported offered" only.

### 4. When to refresh

- **Academic calendar:** `blink.ucsd.edu/instructors/resources/academic/calendars/2026.html`
- **Enrollment calendar:** `blink.ucsd.edu/instructors/courses/enrollment/calendars/2026.html`
  - It has a "Schedule of Classes available" date, which can trigger a refresh.
  - Drop struck-through `<span>` dates first.

### 5. Eval fixtures: plans.ucsd.edu

- `controller.php?action=LoadPlans&college=..&year=2025&major=DS25` returns
  public JSON of the sample four-year plans for each college.
- No 2026-27 DS plan exists yet. The site says to use the 2025-26 plan when
  nothing changed.

### Off limits

- **SSO or login-gated:** TSS, CAPE `Results.aspx`, SET, DARS, `api.ucsd.edu`.
  Any 302 to `a5.ucsd.edu` means stop.
- **Credentials:** never put a personal session cookie into CI or Streamlit.
- **SET:** its data is stated as "not intended for project or research use".

## Terms of use

This is a reading of the terms, not legal advice.

- **What the terms say:** the ucsd.edu Terms of Use allow one personal,
  non-commercial copy. They prohibit republishing, including use "on any other
  website or networked computer environment", without explicit permission.
- **Where the public app conflicts:** it stores and shows full catalog
  descriptions (`dsc_courses.json`).
- **Safer default:**
  - Store derived facts only: IDs, units, parsed prerequisite edges, terms
    offered, `source_url`, `fetched_at`.
  - Link out to the catalog anchor for the prose.
  - Show a "tentative — check the Schedule of Classes" banner and the date of
    the last refresh.
- **Ask for permission:**
  - HDSI, which maintains the DSC pages.
  - ITS, through the contact named in the Terms.
  - The Registrar or the Class Planner team (tss@ucsd.edu). Also ask whether a
    sanctioned feed exists.
- **Fetching manners:**
  - Use the User-Agent `ucsd-course-planning-tutor (student project)`.
  - Make at most 1 request per second, and cache.
  - Use a wildcard-aware robots parser (`protego`). `urllib.robotparser`
    ignores Blink's `Disallow: *.pdf`.

## Proposed plan

1. **Fix the catalog scraper.**
   - Replace `scraper.py`: walk siblings, normalize IDs, handle the unit forms.
   - Write a structured snapshot.
   - The prerequisite graph keeps reading through `prereq_graph.py` and
     `prereq_overrides.json`.
2. **Offerings layer.**
   - One adapter per department writes `data/offerings.json`, with records
     `{course, academic_year, quarters, status: tentative|scheduled, source_url, fetched_at, content_hash}`.
3. **Validator rule `NOT_OFFERED`.**
   - Warning when the course is tentatively not listed in that quarter.
   - Error only when the published term schedule confirms it is absent.
   - "Unknown" outside the covered year.
   - Exempt by-arrangement courses.
   - Add fixtures to `VALIDATOR_FIXTURES` and tests.
4. **Refresh workflow.**
   - Weekly cron, plus a daily cheap check of the terms list.
   - Validate headers and schemas, and keep the last good snapshot on failure.
   - Open a PR with a per-course diff, prerequisite edges included.
   - CI runs the tests.
5. **App.**
   - Show "data as of …", the tentative banner, and source links.
   - Move CAPE links to set.ucsd.edu (CAPE data stops at Spring 2023).
   - Fix the dead HDSI links at `app.py:63` and `app.py:67`.
6. **Descriptions.** Decide on the full descriptions once permission is
   answered: keep them, or move to derived facts plus links.

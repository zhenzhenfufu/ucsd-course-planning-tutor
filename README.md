# UCSD Course Planning Tutor

An academic planner for the UCSD Data Science major that will not hand you a
schedule you are not allowed to take.

**[Live demo](https://ucsd-course-planning-tutor.streamlit.app/)** ·
[![tests](https://github.com/zhenzhenfufu/ucsd-course-planning-tutor/actions/workflows/tests.yml/badge.svg)](https://github.com/zhenzhenfufu/ucsd-course-planning-tutor/actions/workflows/tests.yml)

---

## The problem with asking a model to plan courses

A language model is good at reading "I want to specialise in machine learning"
and picking sensible courses. It is unreliable at the other half of the job:
holding a 69-node prerequisite graph in its head and making sure every course
sits strictly after everything it depends on.

In an earlier measurement (before the October 2026 data rebuild below), on 20 planning tasks, asked to produce a whole multi-quarter plan in
one shot, the model produced a **legal** plan 40% of the time. The failures are
not exotic — it schedules DSC 100 before DSC 80, or fills a quarter to 8 units.

So the model does not decide whether a plan is valid. Code does.

```
model  ->  which courses, for this goal, in roughly what order
code   ->  is that ordering actually legal
```

---

## October 2026: the prerequisite data was wrong, and it was the data

The course data used to live in a hand-written `dsc_courses.json`, and its
`Prerequisites:` sentences did not match the university's catalog. The
parser was reading them faithfully; the source was wrong. Six examples of what
that cost:

| Course | Dataset said | Catalog says |
|---|---|---|
| DSC 80 | DSC 10 | DSC 30 **and** DSC 40A |
| DSC 40B | DSC 30, DSC 40A | DSC 20, DSC 40A |
| MATH 183 | MATH 20B | MATH 20C |
| MATH 180A | nothing | MATH 20C |
| DSC 161 | DSC 80 | ECON 5 or one of six POLI courses |
| DSC 180A | DSC 102, MATH 189 | also DSC 106 and a machine-learning elective |

Every sentence is now regenerated from `catalog.ucsd.edu`, for every department
the graph touches, which took the graph from **74 edges to 143**. Three habits
of the catalog had to be handled before the rest fell out:

- the department is carried over rather than repeated — `DSC 20/R and 40A/R`
- the subject code is not consistently capitalised — `Math 20C or MATH 31BH`
- a dash means a whole sequence — `MATH 20A-B-C`

Two modelling rules go with it. A requirement a placement exam or AP score can
satisfy is **not** a hard prerequisite, so it does not become an edge; where the
ordering still binds for anyone who does take the course (`MATH 20A → 20B →
20C`), that is recorded in `prereq_overrides.json` with the reason. And a
sequence offered as one alternative of a disjunction — `PHYS 4A-B or
PHYS 2A-B-C` — is distributed into conjunctive normal form rather than
flattened into a false conjunction.

**The evaluation numbers below predate this rebuild.** They were measured on the
74-edge graph and describe the method, not this graph; re-running `eval/run_eval.py`
against the corrected data needs a `GEMINI_API_KEY` and has not been done yet.

## Repository layout

The app lives at the repository root. `ucsd-course-planning-tutor/app.py` is a
shim kept only so an existing deployment pointed at the old path keeps working.

## Architecture

```
data/catalog.json         catalog snapshot: 69 courses, prerequisites as prose
data/scope.json           which courses are in scope, topic keywords, course sites
data/offerings.json       quarters each course runs (tentative plans + Class Planner)
        |                 (refresh/ regenerates both snapshots every week)
        v
prereq_graph.py           parse prose -> prerequisite DAG (AND of OR-groups)
        |                 + substitution rules, abstract requirements
        |                 + prereq_overrides.json (reviewed corrections)
        v
retrieval.py              per-course documents -> embeddings (or TF-IDF)
        |                 + graph expansion: retrieve a course, get its prereqs
        v
planner.py                generate a quarter -> validate -> regenerate
        |
        v
validator.py              deterministic: ordering, units, duplicates, OR-groups
```

### 1. Parsing prerequisites out of prose

The catalog states prerequisites in sentences, in **two opposite directions**:

| Sentence | Meaning |
|---|---|
| `MATH 180A — Prerequisite: MATH 20C.` | MATH 20C comes **before** MATH 180A |
| `MATH 20B — Prerequisite for MATH 20C.` | MATH 20B comes **before** MATH 20C |

Reading the second form as if it were the first reverses the edge. Direction is
therefore decided per sentence, before any course code is extracted.

Two more forms look forward but are not prerequisites at all, and treating them
as such was a real bug caught during development:

| Sentence | Correct reading |
|---|---|
| `CSE 151A — Accepted as alternative to DSC 148/140A/140B` | CSE 151A **replaces** those courses |
| `MATH 180A — Required or recommended for DSC 140A, 140B…` | advisory, **not** a gate |

Parsing "accepted as alternative to DSC 140A" as a prerequisite would have made
CSE 151A mandatory before DSC 140A — the exact inverse of what it means.

Requirements are stored as an AND of OR-groups, so alternatives survive:

```
CSE 158 -> [[DSC 40B, CSE 12], [DSC 80, CSE 15L], [<probability>]]
```

`<probability>` is an *abstract requirement*: the prose says "a probability
course" and names the acceptable ones elsewhere in the catalog
(MATH 180A, MATH 183, CSE 103, ECE 109).

What the parser produces:

| | |
|---|---|
| courses | 69 |
| prerequisite edges | 143 |
| substitution rules found in prose | 7 |
| OR-groups (two or more alternatives) | 74 |
| abstract requirement atoms | 5 |
| cycles | **0** (verified DAG) |
| depth | 9 topological layers |
| sentences it flagged as ambiguous | 20, listed rather than dropped |

Those 20 are reported, not silently discarded — advisory wording, nested
AND/OR clauses and references the parser cannot place on a course in scope.

### 2. One source of truth

The Streamlit app used to carry its own hand-written `EDGES` list. Compared
against the parsed graph, the two had drifted **25 edges apart**: 9 the hand
list asserted that the catalog never says, 16 the hand list had missed.

The hand list is gone. Facts the prose genuinely omits now live in
`prereq_overrides.json` — including the edges from the old list that were
**rejected**, each with the reason, so they do not quietly come back.

### 3. Retrieval

The first version pasted the whole catalog — about 31 KB of JSON — into every
request. Now each course becomes a document (name, units, prerequisite
expression, what it unlocks, substitutions, topic keywords) and only the relevant
rows are retrieved: typically **8–13% of the catalog** per question.

Similarity alone is not sufficient here. Asked *"what do I need before
DSC 100?"*, embedding search returns DSC 100 and courses that read like it,
but **DSC 40B — an actual prerequisite — does not rank**, because it is not
textually similar to the question. So retrieval hits are expanded one hop along
the DAG: whenever a course is in context, the courses it depends on are too.

```
similarity  : DSC 100, DSC 10, DSC 102, DSC 106, DSC 180A, DSC 80
+graph hops : DSC 40B, MATH 189          <- recovered, would have been missed
```

Backends: Gemini embeddings when an API key is present (vectors cached on disk,
keyed by content hash), pure-Python TF-IDF otherwise, so tests and the harness
run offline.

### 4. Validation

`validator.py` takes a plan and returns typed violations. No API calls, so the
same plan always gets the same verdict:

`PREREQ_MISSING` · `NOT_OFFERED` · `UNITS_BELOW_FULL_TIME` · `UNITS_OVER_CAP` ·
`DUPLICATE_COURSE` · `DUPLICATE_IN_TERM` · `UNKNOWN_COURSE` ·
`UNITS_HEAVY` (warning) · `EMPTY_TERM` (warning)

Prerequisites must be satisfied in a **strictly earlier** term, unless the
catalog marks them concurrent-eligible (`PHYS 2A — Prerequisite: MATH 20B
(concurrent OK)`). Substitutions and abstract requirements are honoured, so
CSE 15L satisfies a DSC 80 requirement and ECE 109 satisfies `<probability>`.

### 5. Planning term by term

Two strategies were built and measured against each other.

**A — plan every quarter at once, hand back violations, regenerate.** This
restates the constraint but does not remove it: the model still has to satisfy
ordering across the whole plan by itself.

**B — plan one quarter at a time.** Before each quarter, the eligible set is
recomputed from the DAG and handed to the model, which may only choose from it.
The quarter is validated before the next one is drafted. The model is never
asked to make a decision it cannot legally make.

---

## Results

Earlier measurement, taken before the October 2026 rebuild (74-edge graph; not re-run on the current data): 20 planning tasks (`eval/cases.json`), Gemini embeddings, `eval/run_eval.py`:

| | first plan legal | legal after repair | model calls / task |
|---|---|---|---|
| No structure (whole plan at once) | **40%** (8/20) | 70% (14/20) | 1.90 |
| Per-term against a recomputed eligible set | **100%** (20/20) | 100% (20/20) | 2.65 |

Violations the checker caught in arm A: 12 × `PREREQ_MISSING`,
3 × `UNITS_BELOW_FULL_TIME`, 1 × `DUPLICATE_COURSE`.

The checker is itself checked: 11 hand-built plans with known verdicts
(`VALIDATOR_FIXTURES`), 11/11 correct. 201 unit tests cover the graph, the
validator, retrieval, offerings and the refresh code, and run without network access. Both the tests and
the validator self-test run in CI on every push and pull request
(`.github/workflows/tests.yml`).

```bash
python eval/run_eval.py            # full run
python eval/run_eval.py --offline  # validator self-test only, no API key
pytest tests/ -q                   # 201 tests
```

### What this does not do

Legality is not the same as goal attainment. A plan can pass every check and
still not reach what the student asked for — "three quarters ending with the
capstone" is simply not reachable from some starting points, and the planner
currently returns a legal plan rather than saying so. Detecting *unreachable*
goals from the DAG and reporting them is the obvious next step.

---

## Keeping the data current

There is no public UCSD API for courses, so a GitHub Actions job
(`.github/workflows/refresh.yml`) refreshes the data **every Monday at 15:00 UTC**
and can also be started by hand (Actions tab, "data-refresh", Run workflow).
It opens or updates one pull request, `data-refresh`, whose body is a readable
report of what changed; a person reviews and merges it. A data file is rewritten
only when something other than fetch times and source status changed, so a quiet
week opens no pull request, and the "as of" dates in the app are those of the
last run that changed the data.

| Source | What it gives | Written to |
|---|---|---|
| General Catalog (`catalog.ucsd.edu`) | course IDs, titles, units, prerequisite sentences | `data/catalog.json` |
| Department tentative plans (DSC, CSE, MATH, COGS, PHYS, ECE) | which quarters a course is planned for the year | `data/offerings.json` |
| UCSD Class Planner public API (`/api/v1/public/*` only) | which courses are on the published schedule for a term | `data/offerings.json` |

The fetcher identifies itself as `ucsd-course-planning-tutor (student project)`,
makes at most one request per second to a host, honors `robots.txt`, uses
conditional requests, sends no cookies and refuses to follow a redirect into
UCSD single sign-on. A source that fails its shape check keeps its previous
data. The job runs the offline tests itself and puts their summary in the pull
request, because a pull request opened with the default token does not trigger
`tests.yml`. To run it locally:

```bash
python -m refresh.run --report refresh_report.md
```

(With no `--only`, every source is refreshed; `--only catalog` limits the run to the named sources.)

**What is stored.** Derived facts only: course IDs, titles, units, prerequisite
groups, condition tokens, which quarters a course runs, `source_url`,
`fetched_at` and a content hash. No catalog or department prose is copied, and
the topic keywords in `data/scope.json` are written by the owner.

**What the app shows.** The sidebar caption reads "Catalog as of DATE ·
Offerings as of DATE", or "Offerings unavailable" if `data/offerings.json`
cannot be read (the planner and validator still run). A banner states that
quarter offerings are tentative department plans unless marked scheduled.

**`NOT_OFFERED` severity.** The validator checks each course against the quarter
it is planned in:

| Evidence | Finding |
|---|---|
| Class Planner lists the term for that subject and the course is absent | error |
| Department plan lists the course only in other quarters | warning |
| Department plan does not list the course | warning |
| Department plan lists the course with no quarter | warning |
| By-arrangement courses, Summer, terms with no data | no finding |

**CHEM and BIOL are entered by hand.** The chemistry page disallows robots in
its path and the biology page has no documented feed, so neither is fetched.
`data/offerings_manual.json` has empty `CHEM` and `BIOL` blocks for 2026-27; until
the owner fills their `courses` (course ID to quarters such as `["FA", "WI"]`,
plus `entered_by` and `entered_at`), those departments count as no coverage and
produce no `NOT_OFFERED` findings. Fetched department data wins over manual data.
Write quarters as a list of `FA`, `WI`, `SP`: the tests fail on anything else so
a bad edit is caught in CI, and the app itself reads `Fall`/`Winter`/`Spring` in
any case and ignores any other value instead of crashing.

**One-time repository setting (owner only).** Settings, Actions, General,
"Allow GitHub Actions to create and approve pull requests" must be enabled, or
the workflow cannot open its pull request. It is off by default.

## Running it

```bash
pip install -r requirements.txt
echo "GEMINI_API_KEY=your_key" > .env
streamlit run app.py
```

Without a key the catalog, the graph and the validator all still work; the
retrieval layer falls back to TF-IDF and the generative tabs are disabled.

## Layout

| Path | |
|---|---|
| `data/` | `catalog.json`, `offerings.json` (derived facts), `scope.json` (course scope, keywords), `sources.json` (department plan URLs), `offerings_manual.json` (hand-entered) |
| `refresh/` | fetches and parses the catalog, department plans and Class Planner terms |
| `prereq_graph.py` | prose → prerequisite DAG |
| `prereq_overrides.json` | reviewed corrections, and rejections with reasons |
| `retrieval.py` | documents, embeddings/TF-IDF, graph expansion |
| `validator.py` | deterministic plan checking |
| `planner.py` | generate → validate → repair, both strategies |
| `app.py` | Streamlit UI |
| `eval/` | 20 planning tasks, harness, results |
| `tests/` | 201 offline tests |
| `.github/workflows/refresh.yml` | weekly data refresh that opens a pull request |
| `.github/workflows/tests.yml` | offline tests on every push and pull request |
| `.github/workflows/keepalive.yml` | keeps the hosted demo from sleeping |

# UCSD Course Planning Tutor

An academic planner for the UCSD Data Science major that will not hand you a
schedule you are not allowed to take.

**[Live demo](https://ucsd-course-planning-tutor.streamlit.app/)**

---

## The problem with asking a model to plan courses

A language model is good at reading "I want to specialise in machine learning"
and picking sensible courses. It is unreliable at the other half of the job:
holding a 68-node prerequisite graph in its head and making sure every course
sits strictly after everything it depends on.

Measured on 20 planning tasks, asked to produce a whole multi-quarter plan in
one shot, the model produced a **legal** plan 40% of the time. The failures are
not exotic — it schedules DSC 100 before DSC 80, or fills a quarter to 8 units.

So the model does not decide whether a plan is valid. Code does.

```
model  ->  which courses, for this goal, in roughly what order
code   ->  is that ordering actually legal
```

---

## Architecture

```
dsc_courses.json          catalog: 68 courses, prerequisites written in prose
        |
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
| courses | 68 |
| prerequisite edges | 74 |
| substitution rules found in prose | 7 |
| OR-groups | 3 |
| abstract requirement atoms | 18 |
| cycles | **0** (verified DAG) |
| depth | 9 topological layers |
| references it could not resolve | 8, listed rather than dropped |

Those 8 are reported, not silently discarded — they are things like `CHEM 4`
and `6BH`, which the prose names but the catalog does not contain.

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
expression, what it unlocks, substitutions, description) and only the relevant
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

`PREREQ_MISSING` · `UNITS_BELOW_FULL_TIME` · `UNITS_OVER_CAP` ·
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

20 planning tasks (`eval/cases.json`), Gemini embeddings, `eval/run_eval.py`:

| | first plan legal | legal after repair | model calls / task |
|---|---|---|---|
| No structure (whole plan at once) | **40%** (8/20) | 70% (14/20) | 1.90 |
| Per-term against a recomputed eligible set | **100%** (20/20) | 100% (20/20) | 2.65 |

Violations the checker caught in arm A: 12 × `PREREQ_MISSING`,
3 × `UNITS_BELOW_FULL_TIME`, 1 × `DUPLICATE_COURSE`.

The checker is itself checked: 9 hand-built plans with known verdicts
(`VALIDATOR_FIXTURES`), 9/9 correct. 27 unit tests cover the graph, the
validator and retrieval, and run without network access.

```bash
python eval/run_eval.py            # full run
python eval/run_eval.py --offline  # validator self-test only, no API key
pytest tests/ -q                   # 27 tests
```

### What this does not do

Legality is not the same as goal attainment. A plan can pass every check and
still not reach what the student asked for — "three quarters ending with the
capstone" is simply not reachable from some starting points, and the planner
currently returns a legal plan rather than saying so. Detecting *unreachable*
goals from the DAG and reporting them is the obvious next step.

---

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
| `prereq_graph.py` | prose → prerequisite DAG |
| `prereq_overrides.json` | reviewed corrections, and rejections with reasons |
| `retrieval.py` | documents, embeddings/TF-IDF, graph expansion |
| `validator.py` | deterministic plan checking |
| `planner.py` | generate → validate → repair, both strategies |
| `app.py` | Streamlit UI |
| `eval/` | 20 planning tasks, harness, results |
| `tests/` | 27 offline tests |
| `.github/workflows/keepalive.yml` | keeps the hosted demo from sleeping |

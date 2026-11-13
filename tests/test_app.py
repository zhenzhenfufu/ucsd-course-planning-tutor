"""Streamlit AppTest checks for My Plan's academic-year selector (offline)."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from planner import PlanResult  # noqa: E402
from terms import parse_term  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def _no_model_key(monkeypatch):
    # An empty key stops load_dotenv from filling one in; nothing here calls the model.
    monkeypatch.setenv("GEMINI_API_KEY", "")


def _app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def _year_select(at):
    return next(s for s in at.selectbox if s.label == "Academic year")


def _start_year(label: str) -> int:
    t = parse_term(label)
    return t.year if t.quarter == "FA" else t.year - 1


def _load(at, first_term):
    at.session_state["auto_result"] = PlanResult(
        plan=[{"term": first_term, "courses": ["DSC 10"]}], violations=[], rounds=1,
        first_pass_legal=True, legal=True)
    at.run()
    assert not at.exception
    next(b for b in at.button if b.label == "Load into My Plan").click().run()
    assert not at.exception


def _assert_selected(at, year):
    assert at.session_state["plan_year"] == year
    sel = _year_select(at)
    assert sel.value == year
    assert f"{year}-{(year + 1) % 100:02d}" in sel.options


def test_load_plan_starting_in_last_start_quarter():
    at = _app()
    last = next(s for s in at.selectbox if s.label == "Start quarter").options[-1]
    _load(at, last)
    _assert_selected(at, _start_year(last))


def test_load_plan_outside_every_offered_year_is_still_selectable():
    at = _app()
    _load(at, "Fall 2040")
    _assert_selected(at, 2040)

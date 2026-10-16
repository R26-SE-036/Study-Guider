"""The Java foundations course: the units are valid, true, and never touch progress.

Three properties, each one a way the course could quietly go wrong:

  1. Every unit file matches the schema the page renders, so a unit cannot
     ship with a block the browser does not know how to draw.
  2. Every runnable example does what the unit says it does - prints exactly
     the stated output, or fails with the stated exception. A unit that teaches
     the wrong output is worse than no unit.
  3. Reading the course writes nothing. Mastery comes from quizzes on a
     student's own mistakes; a general unit read in passing is not that
     evidence, and the course routes must work with the graph unreachable.
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.auth import CurrentUser, get_current_user  # noqa: E402
from app.core.concepts import ERROR_TYPE_TO_CONCEPT, PREREQUISITE_EDGES  # noqa: E402
from app.db.neo4j_connection import neo4j_db  # noqa: E402
from app.dev_tools.course_java import check_unit, jdk_available  # noqa: E402
from app.main import app  # noqa: E402
from app.services import course_service  # noqa: E402
from app.services import progress_service  # noqa: E402

STUDENT = CurrentUser({"user_id": "student_1", "full_name": "Ana", "email": "ana@example.com"}, "token")
PILOT = ["OFF_BY_ONE_LOOP_BOUNDARY", "STRING_EQUALITY_WITH_OPERATOR", "MISSING_BREAK_IN_SWITCH"]

UNIT_FILES = sorted(f for f in os.listdir(course_service.COURSE_DIR) if f.endswith(".json"))


# ── The files ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("filename", UNIT_FILES)
def test_every_unit_file_matches_the_schema_and_its_name(filename):
    with open(os.path.join(course_service.COURSE_DIR, filename), encoding="utf-8") as handle:
        unit = course_service.Unit.model_validate(json.load(handle))
    assert filename == f"{unit.id}.json"


@pytest.mark.skipif(not jdk_available(), reason="no JDK on PATH")
@pytest.mark.parametrize("unit_id", [f[:-5] for f in UNIT_FILES])
def test_runnable_examples_do_what_the_unit_says(unit_id):
    problems = check_unit(course_service._load(unit_id))
    assert problems == [], "\n".join(f"{p.where}: {p.detail}" for p in problems)


def test_the_pilot_units_are_published():
    for unit_id in PILOT:
        assert course_service.is_published(unit_id)


def test_the_course_order_never_teaches_a_concept_before_its_prerequisite():
    position = {concept: i for i, concept in enumerate(course_service.COURSE_ORDER)}
    for prerequisite, dependent in PREREQUISITE_EDGES:
        assert position[prerequisite] < position[dependent], f"{prerequisite} must come before {dependent}"


def test_the_catalogue_lists_every_error_type_once():
    catalogue = course_service.catalogue()
    ids = [u["id"] for m in catalogue["modules"] for u in m["units"]]
    assert sorted(ids) == sorted(ERROR_TYPE_TO_CONCEPT)
    assert len(catalogue["modules"]) == 14
    assert catalogue["units_available"] == sum(course_service.is_published(u) for u in ids)


def test_a_draft_is_never_served(monkeypatch, tmp_path):
    draft = json.load(open(course_service.unit_path(PILOT[0]), encoding="utf-8"))
    draft["status"] = "draft"
    (tmp_path / f"{PILOT[0]}.json").write_text(json.dumps(draft), encoding="utf-8")
    monkeypatch.setattr(course_service, "COURSE_DIR", str(tmp_path))
    course_service._load.cache_clear()
    try:
        assert not course_service.is_published(PILOT[0])
    finally:
        course_service._load.cache_clear()


# ── The API ────────────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch):
    """Signed in, with every route into the graph and into progress booby-trapped."""
    def no_graph(*_args, **_kwargs):
        raise AssertionError("the course must not touch the graph")

    monkeypatch.setattr(neo4j_db, "execute_query", no_graph)
    monkeypatch.setattr(progress_service, "update_student_progress", no_graph)
    app.dependency_overrides[get_current_user] = lambda: STUDENT
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_the_catalogue_answers_without_the_graph(client):
    response = client.get("/api/course")
    assert response.status_code == 200, response.text
    assert response.json()["units_total"] == 19


def test_a_unit_answers_without_the_graph_and_links_its_neighbours(client):
    response = client.get("/api/course/units/missing_break_in_switch")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["unit"]["id"] == "MISSING_BREAK_IN_SWITCH"
    assert data["module"]["title"] == "Switch statements"
    assert data["next"] is not None or data["previous"] is not None


@pytest.mark.parametrize("unit_id", ["NOT_AN_ERROR_TYPE", "DIVISION_BY_ZERO_LITERAL"])
def test_unknown_and_unwritten_units_are_404(client, unit_id):
    if unit_id == "DIVISION_BY_ZERO_LITERAL" and course_service.is_published(unit_id):
        pytest.skip("this unit has been written since")
    assert client.get(f"/api/course/units/{unit_id}").status_code == 404


def test_the_course_needs_a_signed_in_student():
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/course").status_code == 401


def test_units_are_indexed_as_plain_text_for_retrieval():
    text = course_service.unit_text(course_service.published_unit(PILOT[0]))
    assert "length − 1" in text and "scores.length" in text

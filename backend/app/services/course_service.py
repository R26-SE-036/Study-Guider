"""The Java foundations course: one written unit per Code Coach error type.

============================ WHY THIS EXISTS ============================
Every other lesson in Study Guider starts with a remediation trigger from Code
Coach: no repeated mistake, no lesson. That makes Study Guider's teaching
depend on a component it does not own - if Code Coach is down, or a student
simply has not made the mistake yet, there is nothing to study.

The course removes that dependency for the content itself. Its units are
written ahead of time, reviewed, and served from files in data/course/, so
reading one needs no trigger, no language model and no graph query. Sign-in
still goes through Code Coach (Study Guider has no accounts of its own; see
app/core/auth.py), so this narrows the dependency to identity rather than
removing it.

============================ WHAT IT MUST NOT DO ============================
Touch knowledge tracing. Mastery is estimated from quiz answers to lessons
written for a student's own mistake; a student reading a general unit and
clicking through its practice questions is a different kind of evidence, and
mixing the two would make the progress page claim knowledge it never saw
tested. Nothing here writes to the graph, and the practice questions are
checked in the browser. tests/test_course.py holds that line.

============================ HOW UNITS ARE MADE ============================
app/dev_tools/write_course_unit.py drafts a unit with the language model from
the course notes for its concept and its prerequisites, checks it against the
schema below and compiles every runnable example. A draft is saved with
status "draft" and is never served; a person reads it, fixes it and sets
"published". Only published units reach students.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.concepts import CONCEPT_TAGS, ERROR_TYPE_TO_CONCEPT
from app.core.config import settings

COURSE_DIR = os.path.join(settings.DATA_DIR, "course")

# The order the modules are taught in. A pedagogical claim, like
# PREREQUISITE_EDGES, and checked against it: no module comes before one it
# depends on (tests/test_course.py).
COURSE_ORDER = [
    "assignment_logic",
    "arithmetic_operations",
    "boolean_logic",
    "conditional_logic",
    "statement_structure",
    "control_flow",
    "switch_statements",
    "string_comparison",
    "immutable_strings",
    "loop_initialization",
    "loop_control",
    "loop_termination",
    "loop_boundaries",
    "array_indexing",
]

MODULES = {
    "assignment_logic": ("Variables and assignment", "What `=` really does, and the assignments that change nothing."),
    "arithmetic_operations": ("Arithmetic", "Integer division, decimals and dividing by zero."),
    "boolean_logic": ("Boolean logic", "How `&&` and `||` combine conditions, and conditions that can never change."),
    "conditional_logic": ("If and else", "Choosing the right comparison and keeping branches distinct."),
    "statement_structure": ("Statement structure", "Where a semicolon ends more than you meant it to."),
    "control_flow": ("Control flow", "Code that can never run, and why the compiler sometimes says so."),
    "switch_statements": ("Switch statements", "How a switch jumps, falls through and stops."),
    "string_comparison": ("Comparing Strings", "Same text versus same object."),
    "immutable_strings": ("Strings that never change", "Why String methods return a new String."),
    "loop_initialization": ("Starting a loop", "Loops that never begin because their condition starts false."),
    "loop_control": ("Loop direction", "Counting the right way towards the stop condition."),
    "loop_termination": ("Ending a loop", "While loops whose variable never moves."),
    "loop_boundaries": ("Loop boundaries", "Off-by-one: one step too many or too few."),
    "array_indexing": ("Array indexing", "Positions from 0 to length − 1."),
}

# Shown for a unit that is not written yet. Plain words, not the error code.
UNIT_TITLES = {
    "OFF_BY_ONE_LOOP_BOUNDARY": "Off-by-one loop boundaries",
    "INCORRECT_CONDITIONAL_OPERATOR": "The wrong comparison operator",
    "ARRAY_LENGTH_INDEX_MISUSE": "Using length as an index",
    "STRING_EQUALITY_WITH_OPERATOR": "Comparing Strings with ==",
    "LOOP_UPDATE_WRONG_DIRECTION": "Counting the wrong way",
    "UNREACHABLE_CODE_AFTER_RETURN": "Code after return",
    "MISSING_BREAK_IN_SWITCH": "Missing break in a switch",
    "EMPTY_CONDITIONAL_BODY": "The semicolon after if",
    "SELF_ASSIGNMENT": "Assigning a variable to itself",
    "ALWAYS_TRUE_OR_CONDITION": "An OR that is always true",
    "IGNORED_STRING_METHOD_RESULT": "Ignoring a String method's result",
    "DIVISION_BY_ZERO_LITERAL": "Dividing by zero",
    "CONSTANT_FALSE_LOOP_CONDITION": "A loop that never starts",
    "DUPLICATE_IF_ELSE_CONDITION": "The same condition twice",
    "WHILE_VARIABLE_NOT_UPDATED": "A while loop that never moves",
    "INTEGER_DIVISION_IN_DECIMAL_CONTEXT": "Integer division into a double",
    "DECIMAL_EQUALITY_COMPARISON": "Comparing decimals with ==",
    "POSTFIX_INCREMENT_ASSIGNED_BACK": "count = count++",
    "ALWAYS_FALSE_AND_CONDITION": "An AND that is never true",
}


# ── The unit schema ─────────────────────────────────────────────────────────
# Every block a unit can contain. Strict on purpose: a unit the language model
# drafted with a field the page does not know would otherwise render as a gap.

class _Block(BaseModel):
    model_config = {"extra": "forbid"}


class Text(_Block):
    type: Literal["text"]
    text: str = Field(min_length=1)


class Callout(_Block):
    type: Literal["callout"]
    tone: Literal["info", "tip", "warn"]
    title: str
    text: str


class Program(_Block):
    """A piece of code. `runnable` means it is a whole program: the check
    compiles and runs it and compares `output` (stdout) and `error` (a phrase
    expected in stderr) with what actually happens."""
    title: str = ""
    code: str = Field(min_length=1)
    runnable: bool = False
    output: Optional[str] = None
    error: Optional[str] = None


class Code(Program):
    type: Literal["code"]


class Compare(_Block):
    type: Literal["compare"]
    bad: Program
    good: Program
    note: str = ""


class Table(_Block):
    type: Literal["table"]
    caption: str
    columns: list[str] = Field(min_length=1)
    rows: list[list[str]] = Field(min_length=1)
    highlight: list[int] = []

    @model_validator(mode="after")
    def rows_fit_columns(self):
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError(f"row {row} does not have {len(self.columns)} cells")
        for index in self.highlight:
            if not 0 <= index < len(self.rows):
                raise ValueError(f"highlight {index} is not a row")
        return self


class Diagram(_Block):
    type: Literal["diagram"]
    caption: str
    mermaid: str = Field(min_length=1)


class ArrayView(_Block):
    """An array drawn as numbered boxes. `outside` is an index one past the
    end (or before the start) to draw as the box that is not there."""
    type: Literal["array"]
    caption: str
    name: str
    values: list[str] = Field(min_length=1)
    highlight: list[int] = []
    outside: Optional[int] = None
    note: str = ""


class MemoryVariable(BaseModel):
    name: str
    target: str


class MemoryObject(BaseModel):
    id: str
    text: str


class Memory(_Block):
    """Variables on the left, the objects they refer to on the right."""
    type: Literal["memory"]
    caption: str
    variables: list[MemoryVariable] = Field(min_length=1)
    objects: list[MemoryObject] = Field(min_length=1)
    note: str = ""

    @model_validator(mode="after")
    def targets_exist(self):
        ids = {o.id for o in self.objects}
        for variable in self.variables:
            if variable.target not in ids:
                raise ValueError(f"{variable.name} points at unknown object {variable.target}")
        return self


class Series(BaseModel):
    name: str
    values: list[float]


class Chart(_Block):
    type: Literal["chart"]
    caption: str
    x_label: str
    y_label: str
    categories: list[str] = Field(min_length=1)
    series: list[Series] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def series_fit_categories(self):
        for s in self.series:
            if len(s.values) != len(self.categories):
                raise ValueError(f"series {s.name} needs {len(self.categories)} values")
        return self


class Steps(_Block):
    type: Literal["steps"]
    title: str = ""
    items: list[str] = Field(min_length=2)


class Check(_Block):
    """A practice question. Checked in the browser and never recorded."""
    type: Literal["check"]
    question: str
    code: str = ""
    options: list[str] = Field(min_length=2, max_length=5)
    answer: int
    explanation: str

    @model_validator(mode="after")
    def answer_is_an_option(self):
        if not 0 <= self.answer < len(self.options):
            raise ValueError("answer must index an option")
        return self


class KeyPoints(_Block):
    type: Literal["keypoints"]
    items: list[str] = Field(min_length=2)


Block = Annotated[
    Union[Text, Callout, Code, Compare, Table, Diagram, ArrayView, Memory, Chart, Steps, Check, KeyPoints],
    Field(discriminator="type"),
]


class Section(BaseModel):
    model_config = {"extra": "forbid"}
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str
    blocks: list[Block] = Field(min_length=1)


class Unit(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    concept: str
    title: str
    summary: str
    minutes: int = Field(ge=3, le=60)
    status: Literal["draft", "published"]
    objectives: list[str] = Field(min_length=2)
    sections: list[Section] = Field(min_length=3)
    # The course-note files the unit was written from.
    sources: list[str] = []

    @field_validator("id")
    @classmethod
    def known_error_type(cls, value: str) -> str:
        if value not in ERROR_TYPE_TO_CONCEPT:
            raise ValueError(f"{value} is not a Code Coach error type")
        return value

    @model_validator(mode="after")
    def concept_matches(self):
        expected = ERROR_TYPE_TO_CONCEPT[self.id]
        if self.concept != expected:
            raise ValueError(f"{self.id} belongs to {expected}, not {self.concept}")
        ids = [s.id for s in self.sections]
        if len(ids) != len(set(ids)):
            raise ValueError("section ids must be unique")
        return self


# ── Reading ──────────────────────────────────────────────────────────────────

class UnitNotFound(LookupError):
    pass


def unit_path(unit_id: str) -> str:
    return os.path.join(COURSE_DIR, f"{unit_id}.json")


@lru_cache(maxsize=None)
def _load(unit_id: str) -> Optional[Unit]:
    """The unit on disk, validated, or None when there is no file.

    Cached for the life of the process: units change only with a deploy. A
    file that does not validate raises rather than being skipped, so a broken
    unit fails loudly in the tests instead of quietly vanishing from the course.
    """
    path = unit_path(unit_id)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return Unit.model_validate(json.load(handle))


def published_unit(unit_id: str) -> Unit:
    """A published unit, or UnitNotFound. Drafts are never served."""
    if unit_id not in ERROR_TYPE_TO_CONCEPT:
        raise UnitNotFound(unit_id)
    unit = _load(unit_id)
    if unit is None or unit.status != "published":
        raise UnitNotFound(unit_id)
    return unit


def is_published(unit_id: str) -> bool:
    try:
        published_unit(unit_id)
        return True
    except UnitNotFound:
        return False


def _units_in(concept: str) -> list[str]:
    return sorted(e for e, c in ERROR_TYPE_TO_CONCEPT.items() if c == concept)


def reading_order() -> list[str]:
    """Every unit id, module by module."""
    return [unit_id for concept in COURSE_ORDER for unit_id in _units_in(concept)]


def catalogue() -> dict:
    """Modules in teaching order, each with its units and whether they can be read."""
    modules = []
    for number, concept in enumerate(COURSE_ORDER, start=1):
        title, blurb = MODULES[concept]
        units = []
        for unit_id in _units_in(concept):
            try:
                unit = published_unit(unit_id)
                units.append({"id": unit_id, "title": unit.title, "summary": unit.summary,
                              "minutes": unit.minutes, "available": True})
            except UnitNotFound:
                units.append({"id": unit_id, "title": UNIT_TITLES[unit_id], "summary": "",
                              "minutes": None, "available": False})
        modules.append({"number": number, "concept": concept, "title": title, "blurb": blurb, "units": units})

    total = sum(len(m["units"]) for m in modules)
    available = sum(u["available"] for m in modules for u in m["units"])
    return {"modules": modules, "units_total": total, "units_available": available}


def unit_view(unit_id: str) -> dict:
    """A published unit for the page, with its module and its neighbours."""
    unit = published_unit(unit_id)
    order = [u for u in reading_order() if is_published(u)]
    position = order.index(unit_id)
    neighbour = lambda i: (  # noqa: E731
        {"id": order[i], "title": published_unit(order[i]).title} if 0 <= i < len(order) else None
    )
    title, _ = MODULES[unit.concept]
    return {
        "unit": unit.model_dump(),
        "module": {"number": COURSE_ORDER.index(unit.concept) + 1, "concept": unit.concept, "title": title},
        "previous": neighbour(position - 1),
        "next": neighbour(position + 1),
    }


def unit_text(unit: Unit) -> str:
    """The unit as plain text, for the syllabus vector index."""
    parts = [unit.title, unit.summary, *unit.objectives]
    for section in unit.sections:
        parts.append(section.title)
        for block in section.blocks:
            if isinstance(block, (Text, Callout)):
                parts.append(getattr(block, "title", "") + " " + block.text)
            elif isinstance(block, Compare):
                parts += [f"Mistake:\n{block.bad.code}", f"Fix:\n{block.good.code}", block.note]
            elif isinstance(block, Code):
                parts.append(block.code)
            elif isinstance(block, (Steps, KeyPoints)):
                parts += block.items
            elif isinstance(block, Check):
                parts.append(f"{block.question} {block.options[block.answer]}. {block.explanation}")
            elif isinstance(block, (ArrayView, Memory, Table, Diagram, Chart)):
                parts.append(block.caption)
    return "\n".join(p.strip() for p in parts if p and p.strip())


def published_units() -> list[Unit]:
    return [published_unit(u) for u in reading_order() if is_published(u)]


assert set(COURSE_ORDER) == set(CONCEPT_TAGS), "every concept needs a module, and only those"
assert set(UNIT_TITLES) == set(ERROR_TYPE_TO_CONCEPT), "every error type needs a unit title"

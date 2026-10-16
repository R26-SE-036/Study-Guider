"""Draft a course unit with the language model, check it, and save it as a draft.

    python -m app.dev_tools.write_course_unit DIVISION_BY_ZERO_LITERAL
    python -m app.dev_tools.write_course_unit --all          # every unit with no file yet

WHAT IT DOES
    1. Collects the course notes for the unit's concept and its direct
       prerequisites (data/<concept>.txt) - the same material the micro-lessons
       are grounded in.
    2. Asks the configured model (settings.LLM_PROVIDER) for a unit in the
       course's JSON format, showing it a published unit as the example of the
       shape and the standard expected.
    3. Validates the answer against the schema in course_service and compiles
       and runs every runnable example with the local JDK. A unit that fails
       either check is not saved; the problems are printed.
    4. Saves data/course/<ERROR_TYPE>.json with status "draft".

WHAT IT DOES NOT DO
    Publish. A draft is never served to students. Read it, fix what is wrong,
    set "status": "published", and run the tests (tests/test_course.py compiles
    every published example again). Then re-run index_knowledge_base so the
    unit joins the syllabus vector index.

COST
    One model call per unit (a few US cents with OpenAI). Nothing is written to
    Neo4j.
"""

from __future__ import annotations

import argparse
import json
import os

from pydantic import ValidationError

from app.core.concepts import ERROR_TYPE_TO_CONCEPT, PREREQUISITE_EDGES
from app.core.config import settings
from app.dev_tools.course_java import check_unit, jdk_available
from app.services import course_service
from app.services.llm import LLMUnavailable, generate, strip_code_fence

# The published unit shown to the model as the example.
EXAMPLE_UNIT = "OFF_BY_ONE_LOOP_BOUNDARY"

RULES = """\
Write one unit of a free Java course for first-year university students who
are new to programming. The unit teaches one common mistake.

Return ONLY a JSON object in exactly the format of the example unit below:
the same top-level fields, the same block types and the same field names.
Allowed block types: text, callout, code, compare, table, diagram, array,
memory, chart, steps, check, keypoints. Do not invent new fields or types.

Standards:
- Plain, friendly English for a beginner. Short sentences. Explain every term.
- 6 to 8 sections: the mistake, why it happens (with a diagram or picture),
  a step-by-step trace table, at least two worked examples, "the same bug in
  disguise" variations, 3 practice checks, and key points.
- Use at least one diagram (Mermaid flowchart, no parentheses or square
  brackets inside node labels), and a chart or an array/memory picture where it
  genuinely helps.
- Every "runnable": true program must be a complete Java 17 program with one
  public class, and its "output" must be exactly what it prints. For a program
  that crashes, put the stdout in "output" and the exception name in "error".
- Teach the reasoning, then the fix. Never just state the rule.
- "status" must be "draft". "sources" lists the note files you used.
- Only use facts from standard Java and the course notes below.
"""


def notes_for(concept: str) -> tuple[str, list[str]]:
    prerequisites = [p for p, d in PREREQUISITE_EDGES if d == concept]
    used, parts = [], []
    for name in [concept, *prerequisites]:
        path = os.path.join(settings.DATA_DIR, f"{name}.txt")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                parts.append(f"--- {name}.txt ---\n{handle.read().strip()}")
            used.append(f"{name}.txt")
    return "\n\n".join(parts), used


def prompt_for(unit_id: str) -> str:
    concept = ERROR_TYPE_TO_CONCEPT[unit_id]
    notes, _ = notes_for(concept)
    with open(course_service.unit_path(EXAMPLE_UNIT), encoding="utf-8") as handle:
        example = handle.read()
    return (
        f"{RULES}\n"
        f"The unit to write: id {unit_id}, concept {concept}, "
        f"title \"{course_service.UNIT_TITLES[unit_id]}\".\n\n"
        f"COURSE NOTES\n{notes}\n\n"
        f"EXAMPLE UNIT (shape and standard only; a different mistake)\n{example}\n"
    )


def draft(unit_id: str, force: bool = False) -> bool:
    path = course_service.unit_path(unit_id)
    if os.path.exists(path) and not force:
        print(f"{unit_id}: a file already exists; use --force to replace it.")
        return False

    try:
        raw = generate(prompt_for(unit_id))
    except LLMUnavailable as error:
        print(f"{unit_id}: the model did not answer ({error}).")
        return False

    try:
        data = json.loads(strip_code_fence(raw))
        data["id"], data["status"] = unit_id, "draft"
        unit = course_service.Unit.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as error:
        print(f"{unit_id}: the answer is not a valid unit:\n{error}")
        return False

    if jdk_available():
        problems = check_unit(unit)
        if problems:
            print(f"{unit_id}: examples that do not do what the unit says:")
            for problem in problems:
                print(f"  {problem.where}: {problem.detail}")
            return False
    else:
        print(f"{unit_id}: no JDK on PATH, so the examples were not compiled. Check them before publishing.")

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(unit.model_dump(exclude_defaults=False), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"{unit_id}: draft saved to {os.path.relpath(path)}. Review it, then set status to published.")
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("unit_ids", nargs="*", help="error types to draft")
    parser.add_argument("--all", action="store_true", help="every unit that has no file yet")
    parser.add_argument("--force", action="store_true", help="replace an existing file")
    arguments = parser.parse_args(argv)

    os.makedirs(course_service.COURSE_DIR, exist_ok=True)
    ids = [u.upper() for u in arguments.unit_ids]
    if arguments.all:
        ids = [u for u in course_service.reading_order() if not os.path.exists(course_service.unit_path(u))]
    unknown = [u for u in ids if u not in ERROR_TYPE_TO_CONCEPT]
    if unknown or not ids:
        raise SystemExit(f"Name one or more error types (unknown: {unknown})" if unknown else "Nothing to draft.")

    written = sum(draft(u, arguments.force) for u in ids)
    print(f"\n{written} of {len(ids)} draft(s) saved.")


if __name__ == "__main__":
    main()

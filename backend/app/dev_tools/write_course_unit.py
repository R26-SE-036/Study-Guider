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
from app.services.concept_examples import example_for
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
- Every complete program (one with a main method) MUST have "runnable": true.
  It will be compiled with javac 17 and run, and the unit is rejected if it
  does not behave as stated. "output" is exactly what it prints. For a program
  that crashes, put the stdout in "output" and the exception message in
  "error". For a program that does not compile, put a phrase from javac's
  message in "compile_error" (for example "unreachable statement").
- Be exact about compile time versus run time. Many mistakes compile without
  any warning and only go wrong when the program runs; say so, and never claim
  the compiler rejects code unless a program with "compile_error" proves it.
- Only add a chart when it compares real quantities (counts, results) that
  help the explanation. No charts of yes/no values.
- Teach the reasoning, then the fix. Never just state the rule.
- In prose fields (text, note, question, explanation, items, objectives) and
  in table cells, wrap code - keywords, operators, expressions, variable names
  - in backticks, exactly as the example does: `==`, `scores[3]`, `break`.
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
        # Without this the model teaches whatever the title suggests to it:
        # "Assigning a variable to itself" came back as a lesson on swapping
        # two variables, which is not what Code Coach flags.
        f"THE MISTAKE, exactly as Code Coach flags it in a student's code. The unit "
        f"must be about this pattern; open with it and keep returning to it.\n"
        f"{example_for(unit_id)}\n\n"
        f"COURSE NOTES\n{notes}\n\n"
        f"EXAMPLE UNIT (shape and standard only; a different mistake)\n{example}\n"
    )


def draft(unit_id: str, force: bool = False) -> bool:
    path = course_service.unit_path(unit_id)
    if os.path.exists(path) and not force:
        print(f"{unit_id}: a file already exists; use --force to replace it.")
        return False

    prompt = prompt_for(unit_id)
    unit, complaint = None, ""
    # One attempt, plus one repair: the model is shown exactly what the schema
    # or the compiler said and asked to fix only that. A unit that still fails
    # is not saved.
    for attempt in range(2):
        try:
            raw = generate(prompt if not complaint else (
                f"{prompt}\n\nYOUR PREVIOUS ANSWER\n{raw}\n\n"
                f"IT WAS REJECTED FOR THESE REASONS. Return the whole corrected unit.\n{complaint}"
            ))
        except LLMUnavailable as error:
            print(f"{unit_id}: the model did not answer ({error}).")
            return False

        try:
            data = json.loads(strip_code_fence(raw))
            data["id"], data["status"] = unit_id, "draft"
            # The model writes "warning" for the "warn" tone often enough to
            # spend a whole repair attempt on it; it means the same thing.
            for section in data.get("sections", []):
                for block in section.get("blocks", []):
                    if block.get("type") == "callout" and block.get("tone") == "warning":
                        block["tone"] = "warn"
            unit = course_service.Unit.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as error:
            complaint, unit = f"Not a valid unit: {error}", None
        else:
            if not jdk_available():
                print(f"{unit_id}: no JDK on PATH, so the examples were not compiled. Check them before publishing.")
                break
            problems = check_unit(unit)
            if not problems:
                break
            complaint = "Examples that do not do what the unit says:\n" + "\n".join(
                f"  {p.where}: {p.detail}" for p in problems
            )
            unit = None
        print(f"{unit_id}: attempt {attempt + 1} rejected.\n{complaint}")

    if unit is None:
        print(f"{unit_id}: not saved.")
        return False

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(unit.model_dump(exclude_defaults=False), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"{unit_id}: draft saved to {os.path.relpath(path)}. Review it, then set status to published.")
    return True


def allow_long_answers() -> None:
    """A unit is several times longer than a lesson, and the shared OpenAI
    client gives up after 40 s to stay inside the web app's proxy limit. This
    runs offline, so it can wait."""
    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        from openai import OpenAI

        from app.services import llm

        llm._openai_client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=600.0, max_retries=1)


def main(argv: list[str] | None = None) -> None:
    allow_long_answers()
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

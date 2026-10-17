"""Compile and run a course unit's example programs.

A unit that teaches "this prints 72, 85, 90 and then crashes" has to be right
about that, and a language model drafting units will sometimes not be. Every
block marked `runnable` is a whole program: it is compiled with javac, run with
java, and its stdout compared with the block's `output` and its stderr checked
for the block's `error`.

Used by write_course_unit.py before a draft is saved and by tests/test_course.py
on every published unit. Needs a JDK on PATH; callers skip when there is none.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from app.services.course_service import Chart, Code, Compare, Program, Unit


@dataclass
class Problem:
    where: str
    detail: str


def jdk_available() -> bool:
    return bool(shutil.which("javac") and shutil.which("java"))


def all_programs(unit: Unit) -> list[tuple[str, Program]]:
    found = []
    for section in unit.sections:
        for index, block in enumerate(section.blocks):
            where = f"{section.id}[{index}]"
            if isinstance(block, Code):
                found.append((where, block))
            elif isinstance(block, Compare):
                found += [(f"{where}.{side}", getattr(block, side)) for side in ("bad", "good")]
    return found


def runnable_programs(unit: Unit) -> list[tuple[str, Program]]:
    return [(where, program) for where, program in all_programs(unit) if program.runnable]


def is_whole_program(program: Program) -> bool:
    return bool(re.search(r"static\s+void\s+main\s*\(", program.code))


def _normalise(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").strip().split("\n"))


def run_program(program: Program, timeout: float = 15.0) -> tuple[str, str, int]:
    match = re.search(r"public\s+class\s+(\w+)", program.code)
    if not match:
        raise ValueError("a runnable program needs a public class")
    name = match.group(1)
    with tempfile.TemporaryDirectory() as folder:
        source = os.path.join(folder, f"{name}.java")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(program.code)
        compiled = subprocess.run(["javac", source], capture_output=True, text=True, timeout=timeout)
        if compiled.returncode != 0:
            return "", "javac: " + compiled.stderr, compiled.returncode
        ran = subprocess.run(["java", "-cp", folder, name], capture_output=True, text=True, timeout=timeout)
        return ran.stdout, ran.stderr, ran.returncode


def chart_problems(unit: Unit) -> list[Problem]:
    """Charts that cannot say anything: only 0s and 1s (a yes/no drawn as
    bars), or values so far apart that the small ones are invisible."""
    problems = []
    for section in unit.sections:
        for index, block in enumerate(section.blocks):
            if not isinstance(block, Chart):
                continue
            values = [v for s in block.series for v in s.values]
            nonzero = [abs(v) for v in values if v]
            if set(values) <= {0, 1}:
                problems.append(Problem(f"{section.id}[{index}]", "a chart of only 0s and 1s says nothing a sentence does not"))
            elif nonzero and max(nonzero) / min(nonzero) > 1000:
                problems.append(Problem(f"{section.id}[{index}]", "values differ by more than 1000x, so the small bars are invisible"))
    return problems


def check_unit(unit: Unit) -> list[Problem]:
    problems = chart_problems(unit)
    for where, program in all_programs(unit):
        # The unit that started this rule claimed `10 / 0` does not compile.
        # It does. The program was marked not runnable, so nothing tested the
        # claim. A whole program is now always tested.
        if is_whole_program(program) and not program.runnable:
            problems.append(Problem(where, "a whole program must be marked runnable so its behaviour is checked"))

    for where, program in runnable_programs(unit):
        try:
            stdout, stderr, code = run_program(program)
        except (ValueError, subprocess.TimeoutExpired) as error:
            problems.append(Problem(where, str(error)))
            continue
        compiled = not stderr.startswith("javac: ")
        if program.compile_error:
            if compiled:
                problems.append(Problem(where, f"compiles, but the unit says it fails with {program.compile_error!r}"))
            elif program.compile_error not in stderr:
                problems.append(Problem(where, f"javac says {stderr.strip()!r}, not {program.compile_error!r}"))
            continue
        if not compiled:
            problems.append(Problem(where, stderr.strip()))
            continue
        if program.output is not None and _normalise(stdout) != _normalise(program.output):
            problems.append(Problem(where, f"prints {stdout!r}, unit says {program.output!r}"))
        if program.error:
            if program.error not in stderr:
                problems.append(Problem(where, f"expected {program.error!r} in stderr, got {stderr.strip()!r}"))
        elif code != 0:
            problems.append(Problem(where, f"exited with {code}: {stderr.strip()}"))
    return problems

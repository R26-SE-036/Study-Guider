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

from app.services.course_service import Code, Compare, Program, Unit


@dataclass
class Problem:
    where: str
    detail: str


def jdk_available() -> bool:
    return bool(shutil.which("javac") and shutil.which("java"))


def runnable_programs(unit: Unit) -> list[tuple[str, Program]]:
    found = []
    for section in unit.sections:
        for index, block in enumerate(section.blocks):
            where = f"{section.id}[{index}]"
            if isinstance(block, Code) and block.runnable:
                found.append((where, block))
            elif isinstance(block, Compare):
                for side in ("bad", "good"):
                    program = getattr(block, side)
                    if program.runnable:
                        found.append((f"{where}.{side}", program))
    return found


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


def check_unit(unit: Unit) -> list[Problem]:
    problems = []
    for where, program in runnable_programs(unit):
        try:
            stdout, stderr, code = run_program(program)
        except (ValueError, subprocess.TimeoutExpired) as error:
            problems.append(Problem(where, str(error)))
            continue
        if stderr.startswith("javac: "):
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

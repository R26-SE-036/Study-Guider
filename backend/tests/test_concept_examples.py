"""Every canonical example must be reachable under the name Code Coach sends.

A lesson generated from a remediation trigger has no student code, so it is
taught from CONCEPT_EXAMPLES[error_type]. Two entries were keyed
MISSING_BREAK and WHILE_NOT_UPDATED, which Code Coach has never sent, so
their lessons fell back to the default off-by-one snippet - a lesson about a
switch statement illustrated with a for loop, and nothing reported it.

These tests fail if an example is keyed by a name that is not a mapped Code
Coach error type.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.concepts import ERROR_TYPE_TO_CONCEPT  # noqa: E402
from app.services.concept_examples import (  # noqa: E402
    CONCEPT_EXAMPLES,
    DEFAULT_EXAMPLE,
    example_for,
)


def test_every_example_is_keyed_by_a_real_error_type():
    unknown = sorted(set(CONCEPT_EXAMPLES) - set(ERROR_TYPE_TO_CONCEPT))
    assert unknown == [], f"examples under names Code Coach never sends: {unknown}"


def test_the_renamed_examples_are_found_under_code_coachs_names():
    for error_type in ("MISSING_BREAK_IN_SWITCH", "WHILE_VARIABLE_NOT_UPDATED"):
        assert example_for(error_type) != DEFAULT_EXAMPLE, error_type


def test_every_error_type_has_an_example_of_its_own():
    missing = sorted(set(ERROR_TYPE_TO_CONCEPT) - set(CONCEPT_EXAMPLES))
    assert missing == [], f"taught from the off-by-one default: {missing}"

    examples = list(CONCEPT_EXAMPLES.values())
    assert DEFAULT_EXAMPLE not in examples
    assert len(set(examples)) == len(examples), "two error types share one example"


def test_an_unknown_error_type_still_gets_an_example():
    assert example_for("NOT_A_REAL_ERROR_TYPE") == DEFAULT_EXAMPLE

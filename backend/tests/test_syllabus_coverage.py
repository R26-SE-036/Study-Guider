"""Every concept must have syllabus material, and the mapping must be honest.

NFR-03 requires generated lessons to be "grounded in the provided vector
database". That cannot hold for a concept with no material: retrieval still
returns its nearest neighbours, so a lesson about switch statements was
grounded in notes about loop boundaries and nothing said so.

These tests fail if a concept is ever added without notes, or if a mapping
entry points at a file that is not there.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.concepts import CONCEPT_TAGS  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.vector_index import SOURCE_FILE_CONCEPTS  # noqa: E402


def test_every_concept_has_syllabus_material():
    covered = set(SOURCE_FILE_CONCEPTS.values())
    missing = sorted(set(CONCEPT_TAGS) - covered)
    assert not missing, (
        f"No syllabus notes for: {', '.join(missing)}. Retrieval will return "
        "another concept's text and the lesson will be ungrounded."
    )


def test_every_mapped_file_exists():
    absent = [
        name
        for name in SOURCE_FILE_CONCEPTS
        if not os.path.isfile(os.path.join(settings.DATA_DIR, name))
    ]
    assert not absent, f"Mapped but missing from data/: {absent}"


def test_no_file_is_mapped_to_an_unknown_concept():
    """A typo here would index text under a tag nothing ever searches for."""
    unknown = sorted(set(SOURCE_FILE_CONCEPTS.values()) - set(CONCEPT_TAGS))
    assert not unknown, f"Mapped to concepts that do not exist: {unknown}"


def test_notes_are_substantial_enough_to_retrieve():
    """A near-empty file embeds to noise and would win retrievals it should lose."""
    thin = []
    for name in SOURCE_FILE_CONCEPTS:
        path = os.path.join(settings.DATA_DIR, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as handle:
            if len(handle.read().split()) < 60:
                thin.append(name)
    assert not thin, f"Too short to be useful context: {thin}"

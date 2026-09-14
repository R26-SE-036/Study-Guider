"""Syllabus notes for a lesson prompt, and whether there were any.

The contract used to be "a string of context, or a sentence saying there is
none" - and the sentence was the same whether the search ran and matched nothing
or never ran because the graph was unreachable. A lesson written without notes
then read exactly like one grounded in the syllabus. RetrievedNotes keeps the
difference, and the lesson reports it.

Backed by Neo4j's native vector index - see app/db/vector_index.py.
"""

from dataclasses import dataclass, field

from app.db.neo4j_connection import GraphUnavailable
from app.db.vector_index import NotesUnavailable, search

FOUND = "found"
NONE_FOUND = "none_found"
UNAVAILABLE = "unavailable"

NO_NOTES_TEXT = "No specific university guidelines available."


@dataclass
class RetrievedNotes:
    status: str
    chunks: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        if not self.chunks:
            return NO_NOTES_TEXT
        return "\n".join(chunk["text"] for chunk in self.chunks)


def retrieve_notes(query: str, k: int = 2) -> RetrievedNotes:
    """The closest syllabus chunks, and whether the search found, missed or could not run."""
    try:
        matches = search(query, k=k)
    except (GraphUnavailable, NotesUnavailable) as error:
        print(f"⚠️ Syllabus notes unavailable: {error}")
        return RetrievedNotes(UNAVAILABLE)

    chunks = [match for match in matches if match.get("text")]
    return RetrievedNotes(FOUND if chunks else NONE_FOUND, chunks)


def retrieve_context(query: str, k=2) -> str:
    """Just the prompt text, for a caller that does not need to know which it was."""
    return retrieve_notes(query, k=k).text

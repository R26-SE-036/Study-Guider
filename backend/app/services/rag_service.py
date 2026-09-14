"""Syllabus notes for a lesson prompt, numbered so the lesson can cite them.

The contract used to be "a string of context, or a sentence saying there is
none" - and the sentence was the same whether the search ran and matched nothing
or never ran because the graph was unreachable. RetrievedNotes keeps the
difference, and the lesson reports it.

Notes come from the lesson's own concept and its prerequisites when the concept
is known (vector_index.search_with_prerequisites), not from whichever chunks are
nearest across the whole syllabus. Each is numbered N1, N2, ... in the prompt so
the lesson can say which it drew on, and those ids are checked against what was
actually offered.
"""

from dataclasses import dataclass, field

from app.db.neo4j_connection import GraphUnavailable
from app.db.vector_index import NotesUnavailable, search, search_with_prerequisites

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
        return "\n\n".join(
            f"[{chunk['id']}] (notes on {chunk.get('concept') or chunk.get('source') or 'this topic'})\n{chunk['text']}"
            for chunk in self.chunks
        )


def retrieve_notes(query: str, concept: str | None = None, k: int = 3) -> RetrievedNotes:
    """The nearest notes, within the concept when it is known, numbered for citation."""
    try:
        matches = search_with_prerequisites(query, concept, k=k) if concept else search(query, k=k)
    except (GraphUnavailable, NotesUnavailable) as error:
        print(f"⚠️ Syllabus notes unavailable: {error}")
        return RetrievedNotes(UNAVAILABLE)

    chunks = [
        {**match, "id": f"N{number}"}
        for number, match in enumerate((m for m in matches if m.get("text")), start=1)
    ]
    return RetrievedNotes(FOUND if chunks else NONE_FOUND, chunks)


def retrieve_context(query: str, k=2) -> str:
    """Just the prompt text, for a caller that does not need to know which it was."""
    return retrieve_notes(query, k=k).text

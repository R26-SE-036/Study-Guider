from app.db.vector_index import search


def retrieve_context(query: str, k=2):
    """Searches the syllabus vector store for notes related to the student's error.

    Backed by Neo4j's native vector index rather than a Chroma directory on
    local disk - see app/db/vector_index.py for why. The contract is unchanged:
    a string of context, or a sentence saying there is none.
    """
    try:
        matches = search(query, k=k)
        if not matches:
            return "No specific university guidelines available."

        return "\n".join(match["text"] for match in matches if match.get("text"))
    except Exception as e:
        print(f"⚠️ Retrieval Error: {e}")
        return "No specific university guidelines available."

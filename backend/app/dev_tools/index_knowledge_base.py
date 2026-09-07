"""Embed the syllabus files in data/ into Neo4j's vector index.

    python -m app.dev_tools.index_knowledge_base

Run this once after deploying, and again whenever data/*.txt changes. It is
idempotent - chunks are keyed on (source, position), so re-running updates them
in place rather than doubling the corpus.

It is a deliberate step rather than something the service does at startup. Each
run costs one Gemini embedding call per chunk, and a service that re-embedded
its corpus on every boot would pay that on every deploy, restart and scale
event. That was the practical problem with the previous Chroma directory: it
could not survive a container, so it was rebuilt constantly.
"""

from app.db.vector_index import index_knowledge_base
from app.db.neo4j_connection import neo4j_db


def main():
    if not neo4j_db.driver:
        raise SystemExit("Neo4j is not connected - check NEO4J_URI in backend/.env")

    result = index_knowledge_base()

    if not result.get("success"):
        raise SystemExit(f"Indexing failed: {result.get('error')}")

    print(f"Indexed {result['chunks_indexed']} chunk(s) into Neo4j.")


if __name__ == "__main__":
    main()

"""The syllabus vector store, held in Neo4j rather than on local disk.

============================ WHY THIS REPLACED CHROMA ============================
chroma_setup.py persisted to a `chroma_db/` directory beside the source. That
is fine on a laptop and unworkable anywhere this service is actually deployed:
a container's filesystem is ephemeral, so the index vanished on every restart,
deploy and scale event, and every rebuild re-embedded the whole corpus through
the Gemini API. The directory was also committed to git - sqlite file, HNSW
index binaries and all - so a clone carried one machine's embeddings around.

Neo4j is already a hard dependency of this service and already holds the
concept graph, so putting the vectors there removes a datastore rather than
replacing one. Chunks attach to the concepts they explain:

    (:Chunk {text, embedding, source}) -[:EXPLAINS]-> (:Concept {name})

which makes retrieval and graph traversal the same query. Asking for "material
about the concept this student is stuck on, and about its unmastered
prerequisites" is now one Cypher statement rather than a Chroma search followed
by a separate graph walk and a join in Python.

It also makes an existing claim true. The platform architecture diagram
(code-coach/docs/diagrams/render_codeguru_platform.py) describes this component
as doing "Graph RAG micro-lessons". With a vector store sitting outside the
graph, the retrieval and the graph had nothing to do with each other.
=================================================================================
"""

import os

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.concepts import normalise_concept
from app.core.config import settings
from app.db.neo4j_connection import neo4j_db

VECTOR_INDEX_NAME = "syllabus_chunk_embeddings"

# ── On db.index.vector.queryNodes ────────────────────────────────────────────
# Neo4j 5.27 emits a deprecation notice for it, naming SEARCH as the
# replacement. SEARCH is NOT usable yet: on this server every documented form
# of it is a CypherSyntaxError ("Invalid input 'SEARCH'"), so the notice is
# announcing something a later version will provide rather than something
# available now.
#
# queryNodes therefore stays. When Aura ships SEARCH this becomes a two-line
# change here and nowhere else, which is the reason both call sites are in this
# module rather than spread through the services.
#
# Worth knowing when testing that swap: neo4j_connection.execute_query returns
# None both for "the query failed" and, on some paths, for "no rows". A broken
# replacement query therefore looks exactly like an empty result set. Verify
# against a raw driver session, not through the wrapper.
# ─────────────────────────────────────────────────────────────────────────────

# models/gemini-embedding-001 returns 3072 dimensions. Measured, not assumed -
# a mismatch here does not error, it silently returns nothing from every
# search, because the index simply never matches.
EMBEDDING_DIMENSIONS = 3072

# Cosine, because the embeddings are not normalised to unit length and cosine
# is what the model is trained for.
SIMILARITY_FUNCTION = "cosine"

# Matches chroma_setup.py, so retrieval quality does not change as a side
# effect of moving stores. Worth revisiting deliberately, not incidentally.
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Which concept each syllabus file explains. The filenames predate the concept
# vocabulary and do not match it - `conditionals.txt` is about
# `conditional_logic` - so the mapping is explicit rather than inferred from
# the filename.
SOURCE_FILE_CONCEPTS = {
    # The two originals. Their names predate the concept vocabulary, which is
    # why the mapping is explicit rather than derived from the filename.
    "conditionals.txt": "conditional_logic",
    "loop_boundaries.txt": "loop_boundaries",
    # The other twelve, added so every concept in CONCEPT_TAGS has material.
    # Before this, retrieval for a concept with no notes returned whichever of
    # the two files above was least unrelated - so a lesson on switch
    # statements was grounded in text about loop boundaries, and NFR-03's
    # "100% grounded in the provided vector database" could not hold.
    # These filenames match their concept tags exactly.
    "arithmetic_operations.txt": "arithmetic_operations",
    "array_indexing.txt": "array_indexing",
    "assignment_logic.txt": "assignment_logic",
    "boolean_logic.txt": "boolean_logic",
    "control_flow.txt": "control_flow",
    "immutable_strings.txt": "immutable_strings",
    "loop_control.txt": "loop_control",
    "loop_initialization.txt": "loop_initialization",
    "loop_termination.txt": "loop_termination",
    "statement_structure.txt": "statement_structure",
    "string_comparison.txt": "string_comparison",
    "switch_statements.txt": "switch_statements",
}


def get_embeddings_model():
    """The embedding model, or None when no API key is configured.

    Imported lazily so that importing this module - which app.main does at
    startup - never depends on a network library initialising correctly.
    """
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        if not settings.GEMINI_API_KEY:
            print("⚠️ GEMINI_API_KEY is not set; vector search is disabled.")
            return None

        return GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=settings.GEMINI_API_KEY,
        )
    except Exception as error:
        print(f"⚠️ Embeddings initialization failed: {error}")
        return None


def ensure_vector_index() -> bool:
    """Create the vector index if it does not exist. Idempotent."""
    if not neo4j_db.driver:
        print("⚠️ Neo4j unavailable; cannot create the vector index.")
        return False

    neo4j_db.execute_query(
        f"""
        CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
        FOR (chunk:Chunk) ON (chunk.embedding)
        OPTIONS {{ indexConfig: {{
            `vector.dimensions`: {EMBEDDING_DIMENSIONS},
            `vector.similarity_function`: '{SIMILARITY_FUNCTION}'
        }} }}
        """
    )
    return True


def index_knowledge_base() -> dict:
    """Embed the syllabus files and store them as :Chunk nodes.

    Safe to re-run: chunks are keyed on (source, position), so a second run
    updates in place instead of duplicating the corpus. That matters because
    the obvious failure mode of a re-indexing script is silently doubling
    every search result's neighbourhood.
    """
    if not neo4j_db.driver:
        return {"success": False, "error": "Neo4j unavailable."}

    embeddings = get_embeddings_model()
    if embeddings is None:
        return {"success": False, "error": "No embeddings model available."}

    if not os.path.isdir(settings.DATA_DIR):
        return {"success": False, "error": f"No data directory at {settings.DATA_DIR}"}

    ensure_vector_index()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )

    indexed = 0
    for filename in sorted(os.listdir(settings.DATA_DIR)):
        if not filename.endswith(".txt"):
            continue

        with open(os.path.join(settings.DATA_DIR, filename), encoding="utf-8") as handle:
            text = handle.read()

        concept = normalise_concept(
            SOURCE_FILE_CONCEPTS.get(filename, os.path.splitext(filename)[0])
        )

        for position, chunk in enumerate(splitter.split_text(text)):
            vector = embeddings.embed_query(chunk)

            # db.create.setNodeVectorProperty rather than SET: it stores the
            # value in the typed form the vector index reads. A plain list
            # assignment is accepted and then simply never matched by a search.
            neo4j_db.execute_query(
                """
                MERGE (chunk:Chunk {source: $source, position: $position})
                SET chunk.text = $text
                WITH chunk
                CALL db.create.setNodeVectorProperty(chunk, 'embedding', $vector)
                WITH chunk
                MERGE (concept:Concept {name: $concept})
                MERGE (chunk)-[:EXPLAINS]->(concept)
                """,
                {
                    "source": filename,
                    "position": position,
                    "text": chunk,
                    "vector": vector,
                    "concept": concept,
                },
            )
            indexed += 1

    return {"success": True, "chunks_indexed": indexed}


def search(query: str, k: int = 2) -> list[dict]:
    """Nearest syllabus chunks to `query`. Empty list rather than raising."""
    if not neo4j_db.driver:
        return []

    embeddings = get_embeddings_model()
    if embeddings is None:
        return []

    try:
        vector = embeddings.embed_query(query)
    except Exception as error:
        print(f"⚠️ Could not embed the query: {error}")
        return []

    rows = neo4j_db.execute_query(
        f"""
        CALL db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', $k, $vector)
        YIELD node, score
        OPTIONAL MATCH (node)-[:EXPLAINS]->(concept:Concept)
        RETURN node.text AS text, node.source AS source,
               concept.name AS concept, score
        ORDER BY score DESC
        """,
        {"k": k, "vector": vector},
    )
    return rows or []


def search_with_prerequisites(query: str, concept: str, k: int = 2) -> list[dict]:
    """Chunks for `concept` and for the concepts it depends on.

    This is the query that only exists because the vectors live in the graph:
    a similarity search whose candidate set is restricted by a variable-depth
    walk up the prerequisite chain. With the vectors in a separate store it
    would be a search, a traversal, and a join in Python.

    Falls back to a plain search when the prerequisite graph has not been
    populated, so it degrades to exactly the previous behaviour rather than
    returning nothing.
    """
    if not neo4j_db.driver:
        return []

    embeddings = get_embeddings_model()
    if embeddings is None:
        return []

    target = normalise_concept(concept)

    try:
        vector = embeddings.embed_query(query)
    except Exception as error:
        print(f"⚠️ Could not embed the query: {error}")
        return []

    rows = neo4j_db.execute_query(
        f"""
        CALL db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', $k, $vector)
        YIELD node, score
        MATCH (node)-[:EXPLAINS]->(chunk_concept:Concept)
        WHERE chunk_concept.name = $target
           OR (chunk_concept)-[:PREREQUISITE_OF*1..4]->(:Concept {{name: $target}})
        RETURN node.text AS text, node.source AS source,
               chunk_concept.name AS concept, score
        ORDER BY score DESC
        """,
        {"k": k * 4, "vector": vector, "target": target},
    )

    return rows or search(query, k)

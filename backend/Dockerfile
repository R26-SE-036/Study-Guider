# Study Guider backend - adaptive remediation (micro-lessons + validation quizzes).
#
# Build from the backend directory:
#   docker build -t study-guider-api .
#   docker run --rm -p 8010:8010 \
#     -e CODE_COACH_URL=... -e NEO4J_URI=... -e NEO4J_USERNAME=... \
#     -e NEO4J_PASSWORD=... -e GEMINI_API_KEY=... study-guider-api
#
# This service holds no accounts. Every request carries a Code Coach access
# token and is verified by calling Code Coach, so CODE_COACH_URL must be set and
# reachable or nothing authenticates.

FROM python:3.12-slim

# Dependencies first so the layer caches across code changes.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app

COPY app ./app
# data/ holds the syllabus text the RAG pipeline indexes and dataset.csv, which
# the cognitive-state model was fitted from. Both are read at runtime.
COPY data ./data

# The vector store is in Neo4j, not on this filesystem.
#
# It used to be a Chroma directory beside the source, which a container's
# ephemeral disk destroyed on every restart - so the corpus was re-embedded
# through the Gemini API on the first request after each deploy. The syllabus
# vectors now live in Neo4j's native vector index alongside the concept graph,
# so this image is genuinely stateless and nothing here needs a volume.
#
# Populate the index once per deploy, and after any change to data/*.txt:
#     python -m app.dev_tools.index_knowledge_base
# It is idempotent, and deliberately a separate step rather than something the
# service does at startup - each run costs one embedding call per chunk.

# Emoji appear in status prints across eight modules here, several at import
# time. Without this the container's stdout can default to ASCII and the import
# raises UnicodeEncodeError before uvicorn binds. app/__init__.py reconfigures
# the streams too; this is the belt to that pair of braces.
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1

# Drop root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

# 8010, not 8000: 8000 belongs to Code Coach, which this service must be able to
# call to verify every token. If Study Guider takes 8000, Code Coach cannot
# start and nothing here authenticates.
ENV PORT=8010
EXPOSE 8010

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

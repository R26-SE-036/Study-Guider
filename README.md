# Study Guider

The learning component of Code Guru. When Code Coach sees a student repeat the
same mistake, it raises a remediation trigger; Study Guider turns that trigger
into a short lesson on the concept behind the mistake and a quiz that checks it
was understood, then tracks the student's mastery over time.

The UI is in `codeguru-web` (`/study`). This repository is the backend, a
FastAPI service on port `8010`.

## What it does

| Area | Routes | |
|---|---|---|
| Remediation | `/api/remediation`, `/api/struggle` | Lessons for the student's open triggers, written from the concept and grounded in the syllabus. |
| Quizzes | `/api/quiz` | A validation quiz per lesson; the score goes back to Code Coach, which closes the trigger at 70%. |
| Course | `/api/course` | The Java foundations course: one written unit for each of Code Coach's 30 error types, so there is something to study before a mistake is ever made. |
| Progress | `/api/progress`, `/api/dashboard` | Mastery per concept by Bayesian Knowledge Tracing over quiz attempts, the student's learning path, and a cognitive-state label from a stated rubric. |
| Game summaries | `/api/games` | Receives a performance summary from the Gamification Engine after each game. |
| Session review | `/api/session-review` | Written for PairPath after a pair session. Server to server only, behind `X-Internal-Key`, because the request carries the model solution. |

Every student route takes the Code Coach access token and verifies it with Code
Coach (`app/core/auth.py`); `me` is always the token's owner.

## Data

**Neo4j AuraDB** holds the concept graph, each student's attempts and
progress, and the syllabus vector index used to ground lessons. Lessons and
quizzes are written by a language model - Gemini, or OpenAI with
`LLM_PROVIDER=openai` - and cached in the graph. The course units and the
per-concept syllabus text are files in `data/`.

## Running it

Create `backend/.env` from `backend/.env.example`. It needs the Neo4j
connection (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`), `CODE_COACH_URL`,
an LLM key (`GEMINI_API_KEY` or `OPENAI_API_KEY`), and `INTERNAL_SERVICE_KEY`
for the session review.

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --port 8010
```

Then sign in through `codeguru-web` and open **Study**. A student only has
lessons once Code Coach has raised a trigger; `app/dev_tools/seed_demo_student.py`
creates one to test with.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest
```

## Tools

`backend/app/dev_tools/` builds the content: indexing the syllabus into the
vector index, migrating the graph, writing and pregenerating course units, and
reporting on content coverage. Most of them write to the Neo4j database or call
the language model; read one before running it.

## Deployment

A push to `main` runs the tests, builds the image, pushes it to ECR and rolls it
out on the AWS server (`.github/workflows/ci-cd.yml`).

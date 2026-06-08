# LaunchGood — Campaign Trust & Safety Review Agent

> An AI-powered moderation system that automatically risk-scores fundraising campaigns and routes borderline cases to human reviewers — so a small T&S team can handle Ramadan-scale volume without burning out or letting fraud slip through.

---

## 🔗 Live Demo

- **Frontend:** [https://launchgood-ts-agent.vercel.app](https://launchgood-ts-agent.vercel.app)
- **API Docs (Swagger):** [https://appealing-embrace-production-4999.up.railway.app/docs](https://appealing-embrace-production-4999.up.railway.app/docs)

---

## Problem Statement

LaunchGood reviews every campaign before it goes live — covering fraud screening, content policy, and OFAC/AML compliance. During Ramadan, submission volume spikes 7× while the Trust & Safety team stays the same size, creating an impossible triage problem where both missed fraud and wrongful rejections carry serious consequences.

---

## Solution Overview

An AI agent (built with LangGraph + Google Gemini) automatically analyzes each campaign across four risk dimensions — content quality, compliance, fraud signals, and creator credibility — and produces a structured risk score with human-readable reasoning. Low-risk campaigns can be auto-approved; medium and high-risk campaigns are surfaced to human reviewers via a dashboard with full AI context, cutting average review time from ~20 minutes to under 5.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js)                       │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────┐   │
│  │  Campaign Queue │  │ Review Dashboard │  │  Analytics &  │   │
│  │  (Inbox View)   │  │  (Detail View)   │  │  Eval Panel   │   │
│  └────────┬────────┘  └────────┬─────────┘  └───────┬───────┘   │
└───────────┼────────────────────┼────────────────────┼───────────┘
            │                    │                     │
            ▼                    ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                       BACKEND API (FastAPI)                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Campaign Router                       │   │
│  │  POST /campaigns/submit                                  │   │
│  │  GET  /campaigns/queue                                   │   │
│  │  POST /campaigns/{id}/review                             │   │
│  │  GET  /campaigns/{id}/analysis                           │   │
│  │  GET  /analytics/eval-metrics                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AI AGENT LAYER (LangGraph)                 │
│                                                                 │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────────┐  │
│  │  Intake     │──►│  Analysis    │──►│  Risk Scoring        │  │
│  │  Node       │   │  Node        │   │  Node                │  │
│  └─────────────┘   └──────────────┘   └──────────┬───────────┘  │
│                                                  │              │
│                         ┌────────────────────────┘              │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Decision Node                           │   │
│  │  APPROVE (score < 30) / ESCALATE (30-70) / REJECT (>70)  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                              │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────────┐  │
│  │  PostgreSQL  │  │  Vector Store  │  │  Redis (Queue)      │  │
│  │  (campaigns, │  │  (pgvector)    │  │  (async job queue)  │  │
│  │   reviews,   │  │                │  │                     │  │
│  │   audit log) │  │                │  │                     │  │
│  └──────────────┘  └────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Human/AI Boundary

| Scenario | AI Role | Human Role | Rationale |
|---|---|---|---|
| Score < 30 (LOW) | Recommend APPROVE | Can auto-approve or spot-check | High volume, low risk |
| Score 30–70 (MEDIUM) | Recommend ESCALATE + reasoning | Review required, final decision | Requires human judgment |
| Score > 70 (HIGH) | Recommend REJECT + reasoning | Review required before final reject | Avoid costly false positives |
| OFAC-listed country | Flag HARD BLOCK | Review required + legal team | Legal risk too high for AI alone |
| System confidence < 50% | Flag LOW CONFIDENCE | Review required | AI uncertainty → human takes over |
| Creator with fraud history | Flag + strong REJECT | Human notified | Protect platform integrity |

**What AI must never do:**
- Send rejection notifications directly to campaign creators
- Access or modify payment/payout data
- Make a final decision on campaigns with OFAC flags
- Override a human reviewer's decision

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind CSS 4, Recharts |
| Backend | FastAPI 0.115, Python 3.11, Uvicorn |
| AI Agent | LangGraph 0.2, Google Gemini Flash + Pro |
| Database | PostgreSQL 16 + pgvector |
| Cache / Queue | Redis 7, Celery |
| ORM / Migrations | SQLAlchemy 2.0 async, Alembic |
| Containerisation | Docker, Docker Compose |
| Deploy: API | Railway |
| Deploy: UI | Vercel |

---

## Local Setup

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for PostgreSQL + Redis)
- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) — `pip install uv`

### 1. Clone the repo

```bash
git clone https://github.com/your-org/launchgood-ts-agent.git
cd launchgood-ts-agent
```

### 2. Copy `.env.example` to `.env` and fill in

```bash
cp .env.example .env
cd backend && cp .env.example .env && cd ..
```

Edit `backend/.env` and set:

| Variable | Description |
|---|---|
| `GOOGLE_API_KEY` | Google AI Studio API key for Gemini |
| `DATABASE_URL` | `postgresql+asyncpg://launchgood:launchgood_secret@localhost:5432/launchgood_ts` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `SECRET_KEY` | Any long random string |

### 3. Start infrastructure (PostgreSQL + Redis)

```bash
docker compose up -d postgres redis
docker compose ps   # verify both are healthy
```

### 4. Install backend dependencies

```bash
cd backend
uv sync
```

### 5. Run database migrations

```bash
cd backend
uv run alembic upgrade head
```

### 6. Seed mock data

```bash
cd backend
uv run python seed.py
# Populates 50 realistic mock campaigns in various risk states
```

### 7. Start the backend

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verify:
- Swagger UI → http://localhost:8000/docs
- Health check → http://localhost:8000/api/health

### 8. Start the frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Frontend → http://localhost:3000

---

## Running Evals

### Deterministic tests (rule-based assertions)

```bash
cd backend
uv run python run_deterministic_evals.py
```

Validates hard rules such as: OFAC-sanctioned countries always produce HIGH risk, verified UK campaigns always produce LOW risk, processing time < 10 seconds.

### LLM-as-judge

```bash
cd backend
uv run pytest tests/ -v -k "llm_judge"
```

Scores AI reasoning summaries on clarity, completeness, actionability, and accuracy using a Gemini judge model.

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check — returns service status |
| `POST` | `/api/campaigns/submit` | Submit a campaign for AI risk analysis |
| `GET` | `/api/campaigns/queue` | Paginated, filterable review queue |
| `GET` | `/api/campaigns/{id}/analysis` | Full campaign data + AI analysis result |
| `POST` | `/api/campaigns/{id}/review` | Submit human reviewer decision (HITL) |
| `GET` | `/api/analytics/eval-metrics` | AI performance KPIs and override stats |

Full interactive docs at `/docs` (Swagger) and `/redoc`.

---

## Known Limitations

- **No authentication** — any user can submit campaigns or act as a reviewer (out of scope for prototype)
- **No rate limiting** — the API accepts unlimited requests (out of scope for prototype)
- **OFAC list is static** — hardcoded list of sanctioned countries, not a real-time API call
- **Single reviewer per campaign** — no multi-reviewer workflow or quorum logic

---

## Assumptions

1. **Volume model:** LaunchGood receives hundreds of campaigns per month normally, spiking ~7× during Ramadan — all require T&S review before going live.
2. **AI assists, humans decide:** The AI agent produces recommendations and reasoning, but a human reviewer makes every final call. The AI never autonomously publishes or rejects a campaign.
3. **Risk scoring is weighted:** Four dimensions (content quality 20%, compliance/OFAC 35%, fraud signals 30%, creator credibility 15%) combine into a single 0–100 score.
4. **OFAC/AML is the highest-stakes dimension:** Compliance carries the highest weight (0.35) because legal exposure outweighs other risk types.
5. **Mock data suffices for demo:** No access to real LaunchGood data; 50 synthetic campaigns spanning all risk tiers are generated by `seed.py`.
6. **Creator identity is mocked:** Account age, history, and verification status are simulated fields — no real identity verification pipeline.
7. **Gemini is the LLM:** Google Gemini Flash for analysis nodes (speed), Gemini Pro for the decision node (reasoning quality).
8. **Celery is optional for demo:** The agent runs synchronously in development; Celery/Redis async queue is wired but not required for the local dev loop.
9. **Overrides are training signals:** Every human override is logged and surfaced in analytics, with the intent to drive future prompt engineering or weight adjustments.
10. **Single-tenant prototype:** No multi-org or role-based access control — this is a single-team internal tool.

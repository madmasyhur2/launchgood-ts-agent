# LaunchGood — Campaign Trust & Safety Review Agent
## Prototype System Design Document

> **Tujuan dokumen ini:** Blueprint lengkap untuk membangun dan men-deploy prototype AI-powered campaign moderation system sebagai submission Applied AI Engineer di LaunchGood.

---

## 1. Problem Statement

### Konteks Bisnis
LaunchGood menerima ribuan campaign submission setiap bulan. Setiap campaign **wajib direview** oleh Trust & Safety team sebelum live — mencakup verifikasi legitimasi, screening fraud, dan compliance terhadap regulasi OFAC/AML (Anti-Money Laundering).

### Pain Point Nyata
| Kondisi | Detail |
|---|---|
| Volume normal | ~ratusan campaign/bulan |
| Volume Ramadan | 7x lipat dari normal |
| Tim yang handle | Small T&S team (~handful of specialists) |
| Konsekuensi error | Fraud lolos → reputasi rusak, legal risk |
| Konsekuensi over-reject | Campaign legitimate ditolak → revenue hilang, creator kecewa |

### Core Problem
> Tim kecil harus mereview volume besar dengan akurasi tinggi, dalam waktu singkat, di bawah tekanan seasonal spike — tanpa tooling AI.

---

## 2. Proposed Solution

**AI-Assisted Campaign Moderation System dengan Human-in-the-Loop (HITL)**

AI Agent menganalisis setiap campaign submission secara otomatis, menghasilkan risk assessment + reasoning, lalu mempresentasikannya ke human reviewer melalui dashboard. Human membuat keputusan final dengan konteks penuh dari AI.

### Prinsip Desain
- **AI menangani volume** — pre-screening, risk scoring, flag detection
- **Human menangani judgment** — keputusan final, edge cases, override
- **Setiap keputusan loggable** — audit trail lengkap untuk compliance
- **Sistem bisa dievaluasi** — track AI accuracy vs human override rate

---

## 3. System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js)                       │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │  Campaign Queue  │  │  Review Dashboard │  │  Analytics &  │  │
│  │  (Inbox View)   │  │  (Detail View)    │  │  Eval Panel   │  │
│  └────────┬────────┘  └────────┬─────────┘  └───────┬───────┘  │
└───────────┼────────────────────┼────────────────────┼──────────┘
            │                    │                     │
            ▼                    ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                       BACKEND API (FastAPI)                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Campaign Router                        │   │
│  │  POST /campaigns/submit                                   │   │
│  │  GET  /campaigns/queue                                    │   │
│  │  POST /campaigns/{id}/review                             │   │
│  │  GET  /campaigns/{id}/analysis                           │   │
│  │  GET  /analytics/eval-metrics                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AI AGENT LAYER (LangGraph)                  │
│                                                                   │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────────┐  │
│  │  Intake     │──►│  Analysis    │──►│  Risk Scoring        │  │
│  │  Node       │   │  Node        │   │  Node                │  │
│  └─────────────┘   └──────────────┘   └──────────┬───────────┘  │
│                                                    │              │
│                         ┌──────────────────────────┘              │
│                         ▼                                          │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                  Decision Node                            │    │
│  │  APPROVE (score < 30) / ESCALATE (30-70) / REJECT (>70)  │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                               │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────────┐  │
│  │  PostgreSQL  │  │  Vector Store  │  │  Redis (Queue)      │  │
│  │  (campaigns, │  │  (ChromaDB /   │  │  (async job queue)  │  │
│  │   reviews,   │  │   pgvector)    │  │                     │  │
│  │   audit log) │  │                │  │                     │  │
│  └──────────────┘  └────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. AI Agent Design (LangGraph)

### Agent Graph Flow

```
[START]
   │
   ▼
[intake_node]
   │  - Parse campaign submission
   │  - Normalize fields
   │  - Extract key entities (country, amount, org name)
   ▼
[content_analysis_node]
   │  - Analyze campaign title, story, category
   │  - Check for prohibited keywords/patterns
   │  - Semantic similarity vs flagged campaigns (RAG)
   │  - Detect language + geo context
   ▼
[compliance_check_node]
   │  - Screen creator country vs OFAC sanctioned list
   │  - Check beneficiary country restrictions
   │  - Validate organization name patterns
   │  - Flag high-risk jurisdictions
   ▼
[fraud_signal_node]
   │  - Analyze goal amount reasonableness
   │  - Check creator account age/history (mocked)
   │  - Detect urgency manipulation patterns
   │  - Cross-reference similar campaign patterns
   ▼
[risk_scoring_node]
   │  - Aggregate signals dari semua node sebelumnya
   │  - Generate weighted risk score (0-100)
   │  - Assign risk category per dimension
   ▼
[decision_node]
   │  - score < 30  → Recommend APPROVE
   │  - score 30-70 → Recommend ESCALATE (human review priority)
   │  - score > 70  → Recommend REJECT
   │  - Generate reasoning summary (human-readable)
   │  - Generate confidence level
   ▼
[END] → Return structured analysis to API
```

### Agent State Schema

```python
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime

class RiskDimension(BaseModel):
    score: int          # 0-100
    signals: list[str]  # list of detected signals
    weight: float       # bobot dalam final score

class AgentState(BaseModel):
    campaign_id: str
    campaign_data: dict

    # Per-node outputs
    normalized_data: Optional[dict] = None
    content_flags: Optional[list[str]] = None
    compliance_flags: Optional[list[str]] = None
    fraud_signals: Optional[list[str]] = None

    # Risk dimensions
    risk_dimensions: Optional[dict[str, RiskDimension]] = None

    # Final output
    risk_score: Optional[int] = None
    risk_level: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None
    recommendation: Optional[Literal["APPROVE", "ESCALATE", "REJECT"]] = None
    confidence: Optional[float] = None  # 0.0 - 1.0
    reasoning_summary: Optional[str] = None
    processing_time_ms: Optional[int] = None
```

### Risk Scoring Formula

```
Final Score = Σ (dimension_score × weight)

Dimensions & Weights:
├── Content Quality        : weight 0.20
├── Compliance/OFAC        : weight 0.35  ← highest, legal risk
├── Fraud Signals          : weight 0.30
└── Creator Credibility    : weight 0.15

Thresholds:
├── 0  - 29  → LOW    → Recommend: APPROVE
├── 30 - 69  → MEDIUM → Recommend: ESCALATE
└── 70 - 100 → HIGH   → Recommend: REJECT
```

---

## 5. API Design

### Endpoints

#### `POST /api/campaigns/submit`
Submit campaign untuk di-review oleh AI agent.

**Request:**
```json
{
  "title": "Build a Water Well in Somalia",
  "story": "Our community in Mogadishu...",
  "category": "humanitarian",
  "goal_amount": 15000,
  "currency": "USD",
  "creator": {
    "name": "Ahmad Hassan",
    "email": "ahmad@example.com",
    "country": "US",
    "account_age_days": 245
  },
  "beneficiary_country": "SO",
  "organization_name": "Al-Noor Foundation",
  "documents": ["doc_url_1", "doc_url_2"]
}
```

**Response:**
```json
{
  "campaign_id": "cmp_abc123",
  "status": "queued",
  "estimated_analysis_seconds": 15
}
```

---

#### `GET /api/campaigns/{id}/analysis`
Ambil hasil analisis AI untuk satu campaign.

**Response:**
```json
{
  "campaign_id": "cmp_abc123",
  "status": "completed",
  "ai_analysis": {
    "risk_score": 42,
    "risk_level": "MEDIUM",
    "recommendation": "ESCALATE",
    "confidence": 0.78,
    "reasoning_summary": "Campaign memiliki tujuan humanitarian yang jelas dan creator dengan history akun positif. Namun beneficiary country (Somalia) masuk dalam kategori high-risk jurisdiction yang memerlukan verifikasi dokumen tambahan sebelum approval.",
    "risk_dimensions": {
      "content_quality": {
        "score": 15,
        "signals": ["clear_goal", "compelling_story", "realistic_amount"],
        "weight": 0.20
      },
      "compliance": {
        "score": 65,
        "signals": ["high_risk_beneficiary_country", "requires_additional_docs"],
        "weight": 0.35
      },
      "fraud_signals": {
        "score": 20,
        "signals": ["established_account", "reasonable_goal_amount"],
        "weight": 0.30
      },
      "creator_credibility": {
        "score": 10,
        "signals": ["verified_email", "positive_history"],
        "weight": 0.15
      }
    },
    "flags": [
      {
        "type": "COMPLIANCE",
        "severity": "MEDIUM",
        "detail": "Beneficiary country Somalia memerlukan dokumentasi organisasi lokal yang terverifikasi"
      }
    ],
    "processing_time_ms": 3241
  },
  "created_at": "2024-01-15T08:30:00Z"
}
```

---

#### `GET /api/campaigns/queue`
Ambil daftar campaign yang menunggu human review.

**Query params:** `?status=pending&risk_level=MEDIUM&page=1&limit=20`

**Response:**
```json
{
  "total": 47,
  "pending": 12,
  "items": [
    {
      "campaign_id": "cmp_abc123",
      "title": "Build a Water Well in Somalia",
      "risk_score": 42,
      "risk_level": "MEDIUM",
      "recommendation": "ESCALATE",
      "submitted_at": "2024-01-15T08:00:00Z",
      "time_in_queue_minutes": 30
    }
  ]
}
```

---

#### `POST /api/campaigns/{id}/review`
Human reviewer submit keputusan final.

**Request:**
```json
{
  "reviewer_id": "rev_xyz",
  "decision": "APPROVE",
  "override_reason": "Dokumentasi organisasi sudah diverifikasi via email langsung",
  "notes": "Minta creator upload sertifikat organisasi sebelum campaign live"
}
```

**Response:**
```json
{
  "campaign_id": "cmp_abc123",
  "decision": "APPROVE",
  "ai_recommendation": "ESCALATE",
  "is_override": true,
  "audit_log_id": "log_789",
  "processed_at": "2024-01-15T09:15:00Z"
}
```

---

#### `GET /api/analytics/eval-metrics`
Dashboard metrics untuk evaluasi performa AI.

**Response:**
```json
{
  "period": "last_30_days",
  "total_campaigns": 342,
  "ai_performance": {
    "accuracy_rate": 0.87,
    "override_rate": 0.13,
    "override_breakdown": {
      "ai_approve_human_reject": 0.04,
      "ai_reject_human_approve": 0.06,
      "ai_escalate_human_approve": 0.03
    },
    "avg_processing_time_ms": 2850,
    "avg_human_review_time_minutes": 4.2
  },
  "throughput": {
    "ai_auto_resolved": 198,
    "required_human_review": 144,
    "human_time_saved_hours": 28.4
  },
  "risk_distribution": {
    "LOW": 0.58,
    "MEDIUM": 0.29,
    "HIGH": 0.13
  }
}
```

---

## 6. Database Schema

```sql
-- Campaign submissions
CREATE TABLE campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    story           TEXT,
    category        VARCHAR(50),
    goal_amount     DECIMAL(12,2),
    currency        VARCHAR(3),
    creator_id      UUID,
    beneficiary_country VARCHAR(2),
    organization_name   TEXT,
    status          VARCHAR(20) DEFAULT 'pending',
    submitted_at    TIMESTAMPTZ DEFAULT NOW(),
    raw_data        JSONB
);

-- AI analysis results
CREATE TABLE ai_analyses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     UUID REFERENCES campaigns(id),
    risk_score      INTEGER CHECK (risk_score BETWEEN 0 AND 100),
    risk_level      VARCHAR(10),
    recommendation  VARCHAR(10),
    confidence      DECIMAL(3,2),
    reasoning_summary TEXT,
    risk_dimensions JSONB,
    flags           JSONB,
    processing_time_ms INTEGER,
    model_version   VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Human review decisions
CREATE TABLE reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     UUID REFERENCES campaigns(id),
    reviewer_id     UUID,
    decision        VARCHAR(10) NOT NULL,
    ai_recommendation VARCHAR(10),
    is_override     BOOLEAN DEFAULT FALSE,
    override_reason TEXT,
    notes           TEXT,
    reviewed_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Full audit trail
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     UUID REFERENCES campaigns(id),
    event_type      VARCHAR(50),
    actor           VARCHAR(20),  -- 'ai' or 'human'
    actor_id        TEXT,
    payload         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_campaigns_status ON campaigns(status);
CREATE INDEX idx_analyses_campaign ON ai_analyses(campaign_id);
CREATE INDEX idx_reviews_campaign ON reviews(campaign_id);
CREATE INDEX idx_audit_campaign ON audit_logs(campaign_id);
```

---

## 7. Frontend — Human Review Dashboard

### Halaman & Komponen Utama

```
/dashboard
├── /queue              ← Campaign inbox (list view)
├── /campaign/:id       ← Detail review view
└── /analytics          ← Eval metrics panel
```

### Queue View (Inbox)
```
┌─────────────────────────────────────────────────────────────────┐
│  Campaign Review Queue                    [47 pending] [Filter▼] │
├──────┬───────────────────────┬────────┬──────────┬─────────────┤
│ Risk │ Campaign              │ Score  │ Rec.     │ Time in Q   │
├──────┼───────────────────────┼────────┼──────────┼─────────────┤
│ 🔴   │ Build Mosque in Syria │ 82     │ REJECT   │ 5 min       │
│ 🟡   │ Water Well - Somalia  │ 42     │ ESCALATE │ 30 min      │
│ 🟢   │ Quran School - UK     │ 18     │ APPROVE  │ 1 hr        │
└──────┴───────────────────────┴────────┴──────────┴─────────────┘
```

### Campaign Detail View
```
┌─────────────────────────────────────────────────────────────────┐
│  Campaign: "Build a Water Well in Somalia"          [← Back]    │
├──────────────────────────┬──────────────────────────────────────┤
│  CAMPAIGN INFO           │  AI ANALYSIS                         │
│  ─────────────────────   │  ─────────────────────               │
│  Title: Build Water Well │  Risk Score: 42 / 100  [MEDIUM]      │
│  Goal: $15,000           │  Confidence: 78%                     │
│  Category: Humanitarian  │                                      │
│  Creator: Ahmad Hassan   │  Recommendation:                     │
│  Country: US             │  ┌──────────────────────────────┐   │
│  Beneficiary: Somalia    │  │  ⚠️  ESCALATE FOR REVIEW      │   │
│  Org: Al-Noor Foundation │  └──────────────────────────────┘   │
│                          │                                      │
│  STORY PREVIEW           │  REASONING                          │
│  ─────────────────────   │  ─────────────────────              │
│  "Our community in       │  "Campaign memiliki tujuan          │
│   Mogadishu needs clean  │   humanitarian yang jelas...        │
│   water access..."       │   Beneficiary country (Somalia)     │
│                          │   memerlukan verifikasi dokumen      │
│  [View Full Story]       │   tambahan..."                      │
│                          │                                      │
│                          │  RISK DIMENSIONS                    │
│                          │  ─────────────────────              │
│                          │  Content Quality  ████░░░░  15/100  │
│                          │  Compliance       ██████░░  65/100  │
│                          │  Fraud Signals    ██░░░░░░  20/100  │
│                          │  Credibility      █░░░░░░░  10/100  │
│                          │                                      │
│                          │  FLAGS                              │
│                          │  ─────────────────────              │
│                          │  ⚠️ High-risk beneficiary country    │
│                          │  ℹ️ Additional docs required         │
├──────────────────────────┴──────────────────────────────────────┤
│  REVIEWER DECISION                                              │
│  ─────────────────────────────────────────────────────────────  │
│  Override reason (required if overriding AI):                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Dokumentasi organisasi sudah diverifikasi via email...    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Notes:                                                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Minta creator upload sertifikat sebelum campaign live     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  [✅ APPROVE]  [⚠️ ESCALATE]  [❌ REJECT]                       │
└─────────────────────────────────────────────────────────────────┘
```

### Analytics / Eval Panel
```
┌─────────────────────────────────────────────────────────────────┐
│  AI Performance Metrics                    [Last 30 days ▼]     │
├──────────────────┬─────────────────────────────────────────────┤
│  Accuracy Rate   │  Override Rate  │  Time Saved  │ Throughput  │
│  87%             │  13%            │  28.4 hrs    │ 342 reviews  │
├──────────────────┴─────────────────────────────────────────────┤
│  Override Breakdown                                             │
│  AI Approved → Human Rejected   ████░░░░░░  4%                 │
│  AI Rejected → Human Approved   ██████░░░░  6%                 │
│  AI Escalated → Human Approved  ███░░░░░░░  3%                 │
├─────────────────────────────────────────────────────────────────┤
│  Risk Distribution                                              │
│  LOW (0-29)    ████████████░░░░░░░░  58%                       │
│  MEDIUM (30-69) ██████░░░░░░░░░░░░░  29%                       │
│  HIGH (70-100)  ███░░░░░░░░░░░░░░░░  13%                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Eval Framework

Ini adalah **differentiator utama** submission — kebanyakan kandidat tidak include ini.

### Eval Dimensions

#### A. Deterministic Evals (Unit Tests)
```python
# Test: OFAC-sanctioned country harus selalu HIGH risk
def test_ofac_country_always_high_risk():
    campaign = mock_campaign(beneficiary_country="SY")  # Syria
    result = run_agent(campaign)
    assert result.risk_level == "HIGH"
    assert result.risk_score >= 70

# Test: Verified creator dengan UK campaign harus LOW risk
def test_verified_uk_campaign_low_risk():
    campaign = mock_campaign(
        beneficiary_country="GB",
        creator_account_age_days=500,
        goal_amount=5000
    )
    result = run_agent(campaign)
    assert result.risk_level == "LOW"
    assert result.risk_score < 30

# Test: Processing time harus < 10 detik
def test_processing_time_sla():
    result = run_agent(mock_campaign())
    assert result.processing_time_ms < 10000
```

#### B. LLM-as-Judge Evals
```python
# Evaluasi kualitas reasoning summary
JUDGE_PROMPT = """
Evaluate this AI reasoning summary for a campaign moderation system.
Score 1-5 on:
1. Clarity: Is it understandable to a non-technical reviewer?
2. Completeness: Does it cover all major risk factors?
3. Actionability: Does it give clear next steps?
4. Accuracy: Is the reasoning consistent with the risk score?

Reasoning: {reasoning_summary}
Risk Score: {risk_score}
Flags: {flags}

Return JSON: {"clarity": N, "completeness": N, "actionability": N, "accuracy": N}
"""

def eval_reasoning_quality(analysis_result):
    judge_response = call_llm(JUDGE_PROMPT.format(**analysis_result))
    scores = parse_json(judge_response)
    return scores
```

#### C. Human Review Tracking (Production Eval)
```python
# Track setiap override untuk continuous improvement
def track_override_signal(campaign_id, ai_rec, human_decision, override_reason):
    """
    Setiap override adalah data training signal.
    Kumpulkan ini untuk:
    1. Identify systematic AI errors
    2. Update risk scoring weights
    3. Retrain/prompt engineer berdasarkan patterns
    """
    db.audit_logs.insert({
        "campaign_id": campaign_id,
        "event_type": "human_override",
        "payload": {
            "ai_recommendation": ai_rec,
            "human_decision": human_decision,
            "override_reason": override_reason
        }
    })
```

### Eval Metrics yang Dilaporkan

| Metric | Target | Cara Ukur |
|---|---|---|
| AI Accuracy Rate | > 85% | Human agrees dengan AI rec |
| Override Rate | < 15% | Human overrides AI decision |
| False Positive Rate | < 5% | AI reject tapi harusnya approve |
| Processing Time P95 | < 10s | 95th percentile latency |
| Reasoning Quality | > 3.5/5 | LLM-as-judge score |
| Human Review Time | < 5 min avg | Waktu reviewer per campaign |

---

## 9. Human/AI Boundary — Decision Matrix

Ini adalah bagian paling penting yang akan dinilai interviewer.

| Skenario | AI Role | Human Role | Rationale |
|---|---|---|---|
| Score < 30 (LOW) | Recommend APPROVE | Bisa auto-approve atau spot-check | Volume besar, low risk |
| Score 30-70 (MEDIUM) | Recommend ESCALATE + reasoning | Review wajib, keputusan final | Butuh judgment manusia |
| Score > 70 (HIGH) | Recommend REJECT + reasoning | Review wajib sebelum reject final | Avoid false positive yang costly |
| OFAC-listed country | Flag HARD BLOCK | Review wajib + legal team | Legal risk terlalu tinggi untuk AI |
| System confidence < 50% | Flag LOW CONFIDENCE | Review wajib | AI tidak yakin = human ambil alih |
| Creator dengan history fraud | Flag + REJECT kuat | Notifikasi ke human | Protect platform integrity |

### Yang TIDAK Boleh Dilakukan AI
- Mengirim notifikasi rejection langsung ke campaign creator
- Mengakses atau memodifikasi payment/payout data
- Membuat keputusan final pada campaign dengan OFAC flags
- Override keputusan human reviewer

---

## 10. Tech Stack & Project Structure

### Stack

| Layer | Technology | Alasan |
|---|---|---|
| Frontend | Next.js 14 + TypeScript | SSR untuk performance, type safety |
| UI Components | shadcn/ui + Tailwind | Rapid development, consistent design |
| Backend | FastAPI (Python) | Async support, auto OpenAPI docs |
| AI Agent | LangGraph | State machine yang explicit, debuggable |
| LLM | Claude claude-sonnet-4-20250514 (via Anthropic API) | Best reasoning untuk structured analysis |
| Database | PostgreSQL | Relational integrity untuk audit trail |
| Vector Store | pgvector | Similarity search untuk flagged campaigns |
| Queue | Redis + Celery | Async processing, tidak block HTTP request |
| Deploy | Railway (backend) + Vercel (frontend) | Fast deploy, free tier cukup untuk demo |

### Project Structure

```
launchgood-ts-agent/
├── frontend/                    # Next.js app
│   ├── app/
│   │   ├── dashboard/
│   │   │   ├── page.tsx         # Queue overview
│   │   │   ├── campaign/
│   │   │   │   └── [id]/
│   │   │   │       └── page.tsx # Campaign detail review
│   │   │   └── analytics/
│   │   │       └── page.tsx     # Eval metrics
│   │   └── layout.tsx
│   ├── components/
│   │   ├── CampaignQueue.tsx
│   │   ├── RiskScoreCard.tsx
│   │   ├── ReviewPanel.tsx
│   │   └── EvalDashboard.tsx
│   └── lib/
│       └── api.ts               # API client
│
├── backend/                     # FastAPI app
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   │   ├── campaigns.py
│   │   │   ├── reviews.py
│   │   │   └── analytics.py
│   │   ├── agent/
│   │   │   ├── graph.py         # LangGraph definition
│   │   │   ├── nodes/
│   │   │   │   ├── intake.py
│   │   │   │   ├── content_analysis.py
│   │   │   │   ├── compliance_check.py
│   │   │   │   ├── fraud_signals.py
│   │   │   │   ├── risk_scoring.py
│   │   │   │   └── decision.py
│   │   │   └── state.py         # AgentState schema
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   └── evals/
│   │       ├── deterministic.py
│   │       ├── llm_judge.py
│   │       └── metrics.py
│   ├── tests/
│   │   ├── test_agent.py
│   │   └── test_evals.py
│   └── requirements.txt
│
├── docker-compose.yml           # Local dev setup
├── .env.example
└── README.md
```

---

## 11. Mock Data Strategy

Karena tidak punya akses ke data LaunchGood yang sesungguhnya, gunakan mock data yang **realistis dan variatif**.

### Kategori Mock Campaigns

```python
MOCK_CAMPAIGNS = [
    # LOW RISK — Harus APPROVE
    {
        "title": "Quran School Renovation - Birmingham, UK",
        "goal": 8000, "creator_country": "GB",
        "beneficiary_country": "GB", "account_age_days": 730
    },
    # MEDIUM RISK — Harus ESCALATE
    {
        "title": "Water Well Project - Somalia",
        "goal": 15000, "creator_country": "US",
        "beneficiary_country": "SO", "account_age_days": 245
    },
    # HIGH RISK — Harus REJECT
    {
        "title": "Humanitarian Aid - Syria",
        "goal": 50000, "creator_country": "TR",
        "beneficiary_country": "SY", "account_age_days": 3
    },
    # EDGE CASE — Suspicious amount
    {
        "title": "Orphan Support Fund",
        "goal": 999999, "creator_country": "AE",
        "beneficiary_country": "PK", "account_age_days": 30
    },
]
```
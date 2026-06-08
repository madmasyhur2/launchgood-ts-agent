# -*- coding: utf-8 -*-
"""
seed.py

Seeds the database with realistic mock campaign data for development and demo purposes.

Mock campaigns (5 total):
  1. "Quran School Renovation - Birmingham, UK"  → LOW  risk (score: 12) — APPROVE
  2. "Orphan Support Fund - Kuala Lumpur"         → LOW  risk (score: 18) — APPROVE
  3. "Water Well Project - Somalia"               → MEDIUM risk (score: 42) — ESCALATE
  4. "Community Aid - Gaza Relief"                → MEDIUM risk (score: 58) — ESCALATE
  5. "Humanitarian Aid - Syria"                   → HIGH risk (score: 84) — REJECT

Each campaign gets:
  - A Campaign record
  - An AIAnalysis record (pre-computed, matches the mock scoring logic)
  - Two AuditLog entries: campaign_submitted + ai_analysis_complete

Run with: uv run python seed.py
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Ensure we can import the app package from the backend directory
sys.path.insert(0, ".")

from sqlalchemy import select, text

from app.config import get_settings
from app.database import AsyncSessionLocal, engine
from app.models.ai_analysis import AIAnalysis
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign

settings = get_settings()


# =============================================================================
# Mock campaign definitions
# =============================================================================

MOCK_CAMPAIGNS = [
    # -------------------------------------------------------------------------
    # 1 — LOW RISK: Well-established UK creator, UK beneficiary
    # -------------------------------------------------------------------------
    {
        "campaign": {
            "title": "Quran School Renovation - Birmingham, UK",
            "story": (
                "Our local Quran school in Birmingham has been serving the Muslim community "
                "for over 20 years. The building urgently needs renovation — the roof is "
                "leaking, classrooms need new furniture, and the heating system must be "
                "replaced before winter. All funds will go directly to contractors and "
                "materials. We have full documentation from the local council and registered "
                "charity number available on request."
            ),
            "category": "education",
            "goal_amount": 8000.00,
            "currency": "GBP",
            "creator_name": "Fatima Al-Rashid",
            "creator_email": "fatima@alnoormasjid.org.uk",
            "creator_country": "GB",
            "creator_account_age_days": 730,
            "beneficiary_country": "GB",
            "organization_name": "Al-Noor Educational Trust",
            "status": "completed",
            "ai_recommendation": "APPROVE",
            "ai_risk_level": "LOW",
            "ai_risk_score": 12,
        },
        "analysis": {
            "risk_score": 12,
            "risk_level": "LOW",
            "recommendation": "APPROVE",
            "confidence": 0.92,
            "reasoning_summary": (
                'Campaign "Quran School Renovation - Birmingham, UK" received a risk score '
                "of 12/100 (LOW). Beneficiary country is not on any restricted jurisdiction list. "
                "Creator has a well-established account with positive history. "
                "AI recommendation: APPROVE. Low risk — no significant concerns detected."
            ),
            "risk_dimensions": {
                "content_quality": {"score": 8, "signals": ["clear_goal", "compelling_story", "realistic_amount"], "weight": 0.20},
                "compliance": {"score": 10, "signals": ["low_risk_jurisdiction", "uk_registered_charity"], "weight": 0.35},
                "fraud_signals": {"score": 10, "signals": ["established_account", "reasonable_goal_amount"], "weight": 0.30},
                "creator_credibility": {"score": 5, "signals": ["verified_email", "positive_history", "long_standing_account"], "weight": 0.15},
            },
            "flags": [],
            "processing_time_ms": 1240,
            "model_version": "mock-rules-v1.0",
        },
    },
    # -------------------------------------------------------------------------
    # 2 — LOW RISK: Malaysian creator, Malaysia beneficiary, orphan support
    # -------------------------------------------------------------------------
    {
        "campaign": {
            "title": "Orphan Support Fund - Kuala Lumpur",
            "story": (
                "We are a registered NGO in Malaysia supporting over 200 orphaned children "
                "in Kuala Lumpur. This campaign funds school fees, medical care, and daily "
                "meals for the upcoming academic year. Our organisation has been operational "
                "since 2015 and is audited annually by Jabatan Kebajikan Masyarakat (JKM). "
                "Detailed financial reports and registration documents are available on our website."
            ),
            "category": "humanitarian",
            "goal_amount": 25000.00,
            "currency": "USD",
            "creator_name": "Ahmad Zulkifli",
            "creator_email": "ahmad@yayasanihsan.my",
            "creator_country": "MY",
            "creator_account_age_days": 412,
            "beneficiary_country": "MY",
            "organization_name": "Yayasan Ihsan Malaysia",
            "status": "completed",
            "ai_recommendation": "APPROVE",
            "ai_risk_level": "LOW",
            "ai_risk_score": 18,
        },
        "analysis": {
            "risk_score": 18,
            "risk_level": "LOW",
            "recommendation": "APPROVE",
            "confidence": 0.89,
            "reasoning_summary": (
                'Campaign "Orphan Support Fund - Kuala Lumpur" received a risk score '
                "of 18/100 (LOW). Beneficiary country (Malaysia) is not on any restricted "
                "jurisdiction list. Creator has a well-established account with positive history. "
                "Organisation is a verified registered NGO with public audit records. "
                "AI recommendation: APPROVE. Low risk — no significant concerns detected."
            ),
            "risk_dimensions": {
                "content_quality": {"score": 10, "signals": ["clear_goal", "compelling_story", "realistic_amount"], "weight": 0.20},
                "compliance": {"score": 10, "signals": ["low_risk_jurisdiction", "registered_ngo"], "weight": 0.35},
                "fraud_signals": {"score": 15, "signals": ["established_account", "reasonable_goal_amount"], "weight": 0.30},
                "creator_credibility": {"score": 5, "signals": ["verified_email", "positive_history", "long_standing_account"], "weight": 0.15},
            },
            "flags": [],
            "processing_time_ms": 980,
            "model_version": "mock-rules-v1.0",
        },
    },
    # -------------------------------------------------------------------------
    # 3 — MEDIUM RISK: US creator, Somalia beneficiary (high-risk jurisdiction)
    # -------------------------------------------------------------------------
    {
        "campaign": {
            "title": "Water Well Project - Somalia",
            "story": (
                "Our community in Mogadishu desperately needs clean water access. "
                "Every day, women and children walk miles to collect water from contaminated sources. "
                "This campaign will fund the construction of 3 deep water wells in partnership "
                "with a local NGO. The wells will serve approximately 2,000 people. "
                "We have partnered with Al-Noor Foundation, a local organisation with 10 years "
                "of experience in water infrastructure."
            ),
            "category": "humanitarian",
            "goal_amount": 15000.00,
            "currency": "USD",
            "creator_name": "Ahmad Hassan",
            "creator_email": "ahmad@example.com",
            "creator_country": "US",
            "creator_account_age_days": 245,
            "beneficiary_country": "SO",
            "organization_name": "Al-Noor Foundation",
            "status": "completed",
            "ai_recommendation": "ESCALATE",
            "ai_risk_level": "MEDIUM",
            "ai_risk_score": 42,
        },
        "analysis": {
            "risk_score": 42,
            "risk_level": "MEDIUM",
            "recommendation": "ESCALATE",
            "confidence": 0.78,
            "reasoning_summary": (
                'Campaign "Water Well Project - Somalia" received a risk score '
                "of 42/100 (MEDIUM). Beneficiary country (Somalia) is classified as "
                "a high-risk jurisdiction. Additional organisational documentation is required "
                "before approval. Creator has a moderately established account with reasonable "
                "history. Campaign story is clear and goal amount is realistic for the stated purpose. "
                "AI recommendation: ESCALATE. Human review required to verify the flagged concerns."
            ),
            "risk_dimensions": {
                "content_quality": {"score": 10, "signals": ["clear_goal", "compelling_story", "realistic_amount"], "weight": 0.20},
                "compliance": {"score": 65, "signals": ["high_risk_beneficiary_country", "requires_additional_docs"], "weight": 0.35},
                "fraud_signals": {"score": 25, "signals": ["moderate_account_age", "reasonable_goal_amount"], "weight": 0.30},
                "creator_credibility": {"score": 20, "signals": ["established_account"], "weight": 0.15},
            },
            "flags": [
                {
                    "type": "COMPLIANCE",
                    "severity": "MEDIUM",
                    "detail": "Beneficiary country Somalia is classified as a high-risk jurisdiction. Verified local organisation documentation required.",
                }
            ],
            "processing_time_ms": 2180,
            "model_version": "mock-rules-v1.0",
        },
    },
    # -------------------------------------------------------------------------
    # 4 — MEDIUM RISK: AE creator, new-ish account, large goal, high-risk region
    # -------------------------------------------------------------------------
    {
        "campaign": {
            "title": "Community Aid - Gaza Relief",
            "story": (
                "We are raising emergency funds for families displaced by the ongoing conflict "
                "in Gaza. Funds will provide food packs, medical supplies, and temporary shelter "
                "materials distributed through our partner network on the ground. "
                "Our organisation is based in Dubai and has been active in humanitarian relief "
                "since 2020. We work with verified partners in the region who have established "
                "supply chains and distribution networks."
            ),
            "category": "emergency",
            "goal_amount": 75000.00,
            "currency": "USD",
            "creator_name": "Ibrahim Al-Mansouri",
            "creator_email": "ibrahim@reliefbridge.ae",
            "creator_country": "AE",
            "creator_account_age_days": 89,
            "beneficiary_country": "PS",
            "organization_name": "Relief Bridge International",
            "status": "completed",
            "ai_recommendation": "ESCALATE",
            "ai_risk_level": "MEDIUM",
            "ai_risk_score": 58,
        },
        "analysis": {
            "risk_score": 58,
            "risk_level": "MEDIUM",
            "recommendation": "ESCALATE",
            "confidence": 0.71,
            "reasoning_summary": (
                'Campaign "Community Aid - Gaza Relief" received a risk score '
                "of 58/100 (MEDIUM). Creator account is relatively new (89 days) which is "
                "a moderate fraud signal for a large fund target of $75,000. "
                "Beneficiary region requires standard AML documentation. "
                "Organisation description is plausible but should be verified. "
                "AI recommendation: ESCALATE. Human review required to verify organisation "
                "credentials and disbursement pathway."
            ),
            "risk_dimensions": {
                "content_quality": {"score": 15, "signals": ["clear_goal", "realistic_amount"], "weight": 0.20},
                "compliance": {"score": 45, "signals": ["moderate_risk_region", "requires_disbursement_verification"], "weight": 0.35},
                "fraud_signals": {"score": 55, "signals": ["moderate_account_age", "elevated_goal_amount"], "weight": 0.30},
                "creator_credibility": {"score": 40, "signals": ["moderate_history"], "weight": 0.15},
            },
            "flags": [
                {
                    "type": "FRAUD",
                    "severity": "MEDIUM",
                    "detail": "Creator account is 89 days old with a $75,000 fundraising target. Identity verification and organisation documents required.",
                },
                {
                    "type": "COMPLIANCE",
                    "severity": "LOW",
                    "detail": "Disbursement pathway to the Palestinian Territories requires AML documentation and local partner verification.",
                },
            ],
            "processing_time_ms": 3140,
            "model_version": "mock-rules-v1.0",
        },
    },
    # -------------------------------------------------------------------------
    # 5 — HIGH RISK: Turkey creator, Syria beneficiary (OFAC-sanctioned)
    # -------------------------------------------------------------------------
    {
        "campaign": {
            "title": "Humanitarian Aid - Syria",
            "story": (
                "We are urgently seeking funds to provide humanitarian aid to displaced families "
                "in northern Syria. The situation is dire — thousands of families are without "
                "food, medicine, or shelter following recent conflict escalations. "
                "Funds will be transferred to our network on the ground who will purchase "
                "and distribute supplies directly to affected families."
            ),
            "category": "emergency",
            "goal_amount": 50000.00,
            "currency": "USD",
            "creator_name": "Mehmet Yilmaz",
            "creator_email": "mehmet@insanyardim.tr",
            "creator_country": "TR",
            "creator_account_age_days": 3,
            "beneficiary_country": "SY",
            "organization_name": "Insan Yardim Dernegi",
            "status": "completed",
            "ai_recommendation": "REJECT",
            "ai_risk_level": "HIGH",
            "ai_risk_score": 84,
        },
        "analysis": {
            "risk_score": 84,
            "risk_level": "HIGH",
            "recommendation": "REJECT",
            "confidence": 0.97,
            "reasoning_summary": (
                'Campaign "Humanitarian Aid - Syria" received a risk score '
                "of 84/100 (HIGH). Beneficiary country (Syria) is on the OFAC sanctions list. "
                "This is a hard compliance block — legal team review is mandatory before any approval. "
                "Additionally, creator account was created only 3 days ago, which is a critical "
                "fraud signal. The combination of OFAC-sanctioned beneficiary country and a "
                "brand-new account represents the highest risk profile. "
                "AI recommendation: REJECT. Do not approve without thorough legal/compliance team review."
            ),
            "risk_dimensions": {
                "content_quality": {"score": 30, "signals": ["thin_story", "vague_disbursement"], "weight": 0.20},
                "compliance": {"score": 100, "signals": ["ofac_sanctioned_country", "hard_block_required"], "weight": 0.35},
                "fraud_signals": {"score": 90, "signals": ["brand_new_account", "high_fraud_risk"], "weight": 0.30},
                "creator_credibility": {"score": 75, "signals": ["new_account", "limited_credibility_signals"], "weight": 0.15},
            },
            "flags": [
                {
                    "type": "COMPLIANCE",
                    "severity": "CRITICAL",
                    "detail": "Beneficiary country Syria (SY) is on the OFAC sanctions list. Approval is legally prohibited without explicit legal team sign-off.",
                },
                {
                    "type": "FRAUD",
                    "severity": "HIGH",
                    "detail": "Creator account is only 3 days old. This is a strong fraud indicator, especially combined with a $50,000 fundraising target.",
                },
            ],
            "processing_time_ms": 1890,
            "model_version": "mock-rules-v1.0",
        },
    },
]


# =============================================================================
# Seeder
# =============================================================================

async def seed() -> None:
    """Insert all mock campaigns into the database."""
    print("=" * 60)
    print("LaunchGood T&S Agent - Database Seeder")
    print("=" * 60)

    async with AsyncSessionLocal() as session:
        # Check if already seeded to avoid duplicates
        result = await session.execute(select(Campaign).limit(1))
        existing = result.scalar_one_or_none()
        if existing:
            print("\n[WARN] Database already contains campaign data.")
            print("   To re-seed, truncate the tables first:")
            print("   TRUNCATE campaigns CASCADE;")
            return

        now = datetime.now(timezone.utc)

        for i, mock in enumerate(MOCK_CAMPAIGNS):
            c_data = mock["campaign"]
            a_data = mock["analysis"]

            # Stagger submission times so the queue looks realistic
            submitted_at = now - timedelta(hours=i * 2 + 1)

            # ------------------------------------------------------------------
            # 1. Create Campaign
            # ------------------------------------------------------------------
            campaign = Campaign(
                title=c_data["title"],
                story=c_data["story"],
                category=c_data["category"],
                goal_amount=c_data["goal_amount"],
                currency=c_data["currency"],
                creator_name=c_data["creator_name"],
                creator_email=c_data["creator_email"],
                creator_country=c_data["creator_country"],
                creator_account_age_days=c_data["creator_account_age_days"],
                beneficiary_country=c_data["beneficiary_country"],
                organization_name=c_data["organization_name"],
                status=c_data["status"],
                ai_recommendation=c_data["ai_recommendation"],
                ai_risk_level=c_data["ai_risk_level"],
                ai_risk_score=c_data["ai_risk_score"],
                raw_data=c_data,
                submitted_at=submitted_at,
                updated_at=submitted_at,
            )
            session.add(campaign)
            await session.flush()  # generates campaign.id

            # ------------------------------------------------------------------
            # 2. Create AIAnalysis
            # ------------------------------------------------------------------
            analysis = AIAnalysis(
                campaign_id=campaign.id,
                risk_score=a_data["risk_score"],
                risk_level=a_data["risk_level"],
                recommendation=a_data["recommendation"],
                confidence=a_data["confidence"],
                reasoning_summary=a_data["reasoning_summary"],
                risk_dimensions=a_data["risk_dimensions"],
                flags=a_data["flags"],
                processing_time_ms=a_data["processing_time_ms"],
                model_version=a_data["model_version"],
                created_at=submitted_at + timedelta(seconds=a_data["processing_time_ms"] / 1000),
            )
            session.add(analysis)

            # ------------------------------------------------------------------
            # 3. Audit log — submission
            # ------------------------------------------------------------------
            submit_audit = AuditLog(
                campaign_id=campaign.id,
                event_type="campaign_submitted",
                actor="system",
                actor_id="seed_script",
                payload={
                    "title": c_data["title"],
                    "goal_amount": c_data["goal_amount"],
                    "beneficiary_country": c_data["beneficiary_country"],
                },
                created_at=submitted_at,
            )
            session.add(submit_audit)

            # ------------------------------------------------------------------
            # 4. Audit log — AI analysis complete
            # ------------------------------------------------------------------
            analysis_audit = AuditLog(
                campaign_id=campaign.id,
                event_type="ai_analysis_complete",
                actor="ai",
                actor_id=a_data["model_version"],
                payload={
                    "risk_score": a_data["risk_score"],
                    "risk_level": a_data["risk_level"],
                    "recommendation": a_data["recommendation"],
                    "processing_time_ms": a_data["processing_time_ms"],
                },
                created_at=submitted_at + timedelta(seconds=a_data["processing_time_ms"] / 1000),
            )
            session.add(analysis_audit)

            risk_label = {"LOW": "[LOW] ", "MEDIUM": "[MED] ", "HIGH": "[HIGH]"}[c_data["ai_risk_level"]]
            print(
                f"\n{risk_label} [{i+1}/5] {c_data['title']}\n"
                f"     Score: {c_data['ai_risk_score']} | Level: {c_data['ai_risk_level']} "
                f"| Rec: {c_data['ai_recommendation']}\n"
                f"     Campaign ID: {campaign.id}"
            )

        await session.commit()

    print("\n" + "=" * 60)
    print("[OK] Seeding complete! 5 campaigns inserted.")
    print("   Run: uv run uvicorn app.main:app --reload")
    print("   Then: curl http://localhost:8000/api/campaigns/queue")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed())

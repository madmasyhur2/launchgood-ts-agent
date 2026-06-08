"""
test_agent.py

Run the full LangGraph agent against 5 mock campaigns and print results.
Tests cover all risk tiers: OFAC block, high-risk jurisdiction, new-account fraud,
medium-risk, and clean low-risk.

Usage (from backend/):
    uv run python test_agent.py
"""

import asyncio
import io
import logging
import os
import sys
import time

# Force UTF-8 output on Windows (avoids cp1252 crash on special chars)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Set up logging before imports so we see all node logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
    stream=sys.stdout,
)

from app.agent.graph import run_analysis

# ---------------------------------------------------------------------------
# 5 Mock campaigns
# ---------------------------------------------------------------------------

MOCK_CAMPAIGNS = [
    # 1. OFAC blocked — Syria beneficiary → always HIGH/REJECT
    {
        "id": "test-001",
        "data": {
            "title": "Humanitarian Aid — Syria Relief Fund",
            "story": (
                "We are raising funds to provide food, medicine, and shelter "
                "to displaced families in Aleppo, Syria. The crisis has left "
                "thousands without basic necessities. Your donation will go "
                "directly to trusted local partners on the ground."
            ),
            "category": "humanitarian",
            "goal_amount": 50_000,
            "currency": "USD",
            "beneficiary_country": "SY",
            "organization_name": "Syria Relief Coalition",
            "creator": {
                "name": "Ahmed Al-Hassan",
                "email": "ahmed@reliefcoalition.org",
                "country": "TR",
                "account_age_days": 180,
            },
        },
        "expected_risk": "HIGH",
        "expected_rec": "REJECT",
        "note": "OFAC sanctioned beneficiary country (Syria)",
    },

    # 2. HIGH risk — brand new account + huge goal amount
    {
        "id": "test-002",
        "data": {
            "title": "Emergency Mosque Construction Fund",
            "story": (
                "URGENT! We need to raise $500,000 immediately for a mosque "
                "construction project. Act now — last chance to contribute! "
                "Wire transfer accepted. This is critical and time-sensitive."
            ),
            "category": "mosque",
            "goal_amount": 500_000,
            "currency": "USD",
            "beneficiary_country": "US",
            "organization_name": "",
            "creator": {
                "name": "Unknown Person",
                "email": "user123@gmail.com",
                "country": "US",
                "account_age_days": 3,
            },
        },
        "expected_risk": "MEDIUM",
        "expected_rec": "ESCALATE",
        "note": "Brand-new account (3 days), urgency manipulation, large goal → ESCALATE for human identity check",
    },

    # 3. MEDIUM risk — high-risk jurisdiction (Somalia), legitimate-looking campaign
    {
        "id": "test-003",
        "data": {
            "title": "Water Well Project — Rural Somalia",
            "story": (
                "Our NGO has been operating in Somalia for 5 years, providing "
                "clean water access to rural communities in the Gedo region. "
                "This campaign will fund 3 new water wells, each serving "
                "approximately 500 people. We have letters of support from "
                "local authorities and UN OCHA."
            ),
            "category": "humanitarian",
            "goal_amount": 15_000,
            "currency": "USD",
            "beneficiary_country": "SO",
            "organization_name": "Horn of Africa Water Initiative",
            "creator": {
                "name": "Fatima Warsame",
                "email": "fatima@hoawi.org",
                "country": "US",
                "account_age_days": 720,
            },
        },
        "expected_risk": "MEDIUM",
        "expected_rec": "ESCALATE",
        "note": "Somalia = high-risk jurisdiction (not OFAC), credible org and creator",
    },

    # 4. MEDIUM risk — Gaza (PS), medium account age, reasonable goal
    {
        "id": "test-004",
        "data": {
            "title": "Community Aid — Gaza Relief Fund",
            "story": (
                "We are collecting donations to provide emergency food packages "
                "and medical supplies to families in Gaza. Our partner "
                "organisation has been operating in Palestine since 2010 "
                "and has a proven track record of transparent fund distribution."
            ),
            "category": "emergency",
            "goal_amount": 75_000,
            "currency": "USD",
            "beneficiary_country": "PS",
            "organization_name": "Palestine Relief Foundation",
            "creator": {
                "name": "Omar Khalil",
                "email": "omar@palestinerelief.org",
                "country": "AE",
                "account_age_days": 365,
            },
        },
        "expected_risk": "MEDIUM",
        "expected_rec": "ESCALATE",
        "note": "Palestine (PS) is not OFAC but flags for enhanced due diligence",
    },

    # 5. LOW risk — UK Quran school, verified org, established account
    {
        "id": "test-005",
        "data": {
            "title": "Quran School Renovation — Birmingham, UK",
            "story": (
                "Al-Noor Islamic Centre has been serving the Birmingham Muslim "
                "community for over 20 years. We need to renovate our Quran "
                "school building, which serves 200 children weekly. The renovation "
                "will include new classrooms, better lighting, and improved "
                "accessibility for disabled students. All funds are managed by "
                "our registered UK charity (Charity No. 1183927)."
            ),
            "category": "education",
            "goal_amount": 8_000,
            "currency": "GBP",
            "beneficiary_country": "GB",
            "organization_name": "Al-Noor Islamic Centre",
            "creator": {
                "name": "Ibrahim Khan",
                "email": "ibrahim@alnoor-centre.org.uk",
                "country": "GB",
                "account_age_days": 1825,
            },
        },
        "expected_risk": "LOW",
        "expected_rec": "APPROVE",
        "note": "Clean UK campaign, registered charity, veteran account, reasonable goal",
    },
]

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

RESET  = ""
BOLD   = ""
RED    = ""
YELLOW = ""
GREEN  = ""
CYAN   = ""
GRAY   = ""

RISK_COLOR = {"HIGH": "[HIGH] ", "MEDIUM": "[MED]  ", "LOW": "[LOW]  "}
REC_COLOR  = {"REJECT": "[REJECT]  ", "ESCALATE": "[ESCALATE]", "APPROVE": "[APPROVE] "}


def _color_risk(level: str | None) -> str:
    return RISK_COLOR.get(level or "", "") + (level or "?")


def _color_rec(rec: str | None) -> str:
    return REC_COLOR.get(rec or "", "") + (rec or "?")


def _check(actual: str | None, expected: str) -> str:
    if actual == expected:
        return "PASS"
    return f"FAIL (expected {expected})"


async def run_all() -> None:
    print()
    print("=" * 70)
    print(f"  LaunchGood T&S Agent - Test Run ({len(MOCK_CAMPAIGNS)} campaigns)")
    print("=" * 70)
    print()

    passed = 0
    failed = 0
    total_ms = 0

    for idx, campaign in enumerate(MOCK_CAMPAIGNS, 1):
        camp_id = campaign["id"]
        note    = campaign["note"]
        exp_risk = campaign["expected_risk"]
        exp_rec  = campaign["expected_rec"]

        print(f"[{idx}/{len(MOCK_CAMPAIGNS)}] {camp_id}  -- {note}")
        print(f"  Title: {campaign['data']['title']}")

        t0 = time.time()
        result = await run_analysis(camp_id, campaign["data"])
        elapsed = int((time.time() - t0) * 1000)
        total_ms += elapsed

        risk_ok = result.risk_level == exp_risk
        rec_ok  = result.recommendation == exp_rec

        if risk_ok and rec_ok:
            passed += 1
        else:
            failed += 1

        ok_str = "PASS" if (risk_ok and rec_ok) else "FAIL"
        print(f"  Status : {ok_str}  ({elapsed}ms)")
        print(f"  Score  : {result.risk_score}/100")
        print(f"  Risk   : {_color_risk(result.risk_level)}  {_check(result.risk_level, exp_risk)}")
        print(f"  Rec    : {_color_rec(result.recommendation)}  {_check(result.recommendation, exp_rec)}")
        print(f"  Conf   : {(result.confidence or 0):.2f}")

        if result.reasoning_summary:
            # Wrap at 70 chars
            summary = result.reasoning_summary
            lines = []
            while len(summary) > 70:
                cut = summary[:70].rfind(" ")
                lines.append(summary[:cut if cut > 0 else 70])
                summary = summary[cut + 1 if cut > 0 else 70:]
            lines.append(summary)
            print(f"  Reason : {lines[0]}")
            for line in lines[1:]:
                print(f"           {line}")

        if result.errors:
            print(f"  Errors : {result.errors}")

        # Dimension breakdown
        if result.risk_dimensions:
            print("  Dims   :")
            for name, dim in result.risk_dimensions.items():
                bar_len = dim.score // 10
                bar = "#" * bar_len + "." * (10 - bar_len)
                print(f"    {name:<22} [{bar}] {dim.score:3d}")

        print()

    # Summary
    sla_ok = total_ms / len(MOCK_CAMPAIGNS) < 10_000
    avg_ms = total_ms // len(MOCK_CAMPAIGNS)

    print("=" * 70)
    sla_str = "OK" if sla_ok else "FAIL"
    print(f"  Results: {passed} passed / {failed} failed  |  Avg: {avg_ms}ms  SLA (<10s): {sla_str}")
    print("=" * 70)
    print()

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    # Prompt for GOOGLE_API_KEY if not set
    if not os.getenv("GOOGLE_API_KEY"):
        key = os.getenv("GOOGLE_API_KEY") or ""
        if not key:
            print(
                f"{YELLOW}Warning: GOOGLE_API_KEY not set — "
                "LLM nodes will use rule-based fallback{RESET}\n"
            )

    asyncio.run(run_all())

"""
run_deterministic_evals.py

Standalone runner for the deterministic eval suite.
Usage: uv run python run_deterministic_evals.py

Exit code 0 = all passed, 1 = one or more failed.
"""
import asyncio
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
logging.basicConfig(
    level=logging.WARNING,  # suppress node-level logs for clean output
    format="%(levelname)-8s %(name)s - %(message)s",
    stream=sys.stdout,
)

from app.evals.deterministic import run_all, summarise


async def main() -> int:
    print()
    print("=" * 65)
    print("  LaunchGood T&S Agent - Deterministic Eval Suite")
    print("=" * 65)
    print()

    results = await run_all()
    summary = summarise(results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}]  {r.name:<40} {r.duration_ms:>5}ms")
        if not r.passed:
            print(f"          => {r.message}")

    print()
    print("=" * 65)
    total = summary["total"]
    passed = summary["passed"]
    failed = summary["failed"]
    rate = summary["pass_rate"]
    print(f"  Results: {passed}/{total} passed ({rate:.0%})  |  {failed} failed")
    print("=" * 65)
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

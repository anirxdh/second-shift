"""Preparedness scan: what if each technician called out today?

Simulates every call-out (full solver + independent checker, nothing written) and
ranks single points of failure. Writes evals/PREPAREDNESS.md.

  uv run python -m evals.preparedness          # demo company (in-memory apps)
  uv run python -m evals.preparedness --live   # your real Sheets + Calendar (read-only)
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

from second_shift.adapters.fakes import build_fake_ports
from second_shift.engine import Engine
from second_shift.ledger import Ledger

OUT = Path(__file__).resolve().parent / "PREPAREDNESS.md"


def main() -> int:
    load_dotenv()
    if "--live" in sys.argv:
        from second_shift.adapters.live import build_live_ports

        ports = build_live_ports()
    else:
        ports, _ = build_fake_ports()
    rows = Engine(ports, Ledger(), None, now=lambda: 405).preparedness_scan()
    lines = [
        "# Preparedness scan",
        "",
        "What if each technician called out today? Every row is a full re-plan (CP-SAT) checked by the",
        "independent rule checker. Nothing is written. Riskiest first.",
        "",
        "| Technician | Skills | Their jobs | Covered | Need rescheduling | Customers emailed | Plan legal |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(f"| {r['name']} | {', '.join(r['skills'])} | {r['jobs']} | {r['covered']} | {r['reschedule']} | "
                     f"{r['customer_notices']} | {'yes' if r['valid'] else 'NO'} |")
    lines += ["", "## Jobs that could not be covered", ""]
    for r in rows:
        for j in r["reschedule_jobs"]:
            lines.append(f"- If **{r['name']}** is out: {j['job_id']} {j['customer']}. {j['why']}")
    OUT.write_text("\n".join(lines) + "\n")
    for r in rows:
        print(f"{r['name']:12} jobs {r['jobs']}  covered {r['covered']}  reschedule {r['reschedule']}  "
              f"emails {r['customer_notices']}  legal {r['valid']}")
    print(f"\nReport: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

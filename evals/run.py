"""Run every reliability scenario and write evals/REPORT.md.

  uv run python -m evals.run
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from .scenarios import run_all

OUT = Path(__file__).resolve().parent / "REPORT.md"


def main() -> int:
    results = run_all()
    passed = sum(r.passed for r in results)
    lines = [
        "# Second Shift reliability report",
        "",
        f"Generated {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} by `uv run python -m evals.run`.",
        "Every scenario runs against fresh in-memory Sheets, Calendar, Slack and Gmail that share the",
        "engine, solver, checker, ledger and sheet-parsing code with the live Google/Slack run.",
        "",
        f"**{passed}/{len(results)} scenarios passed.**",
        "",
        "| Group | Scenario | What it proves | Result | ms |",
        "|---|---|---|---|---:|",
    ]
    for r in results:
        lines.append(f"| {r.group} | `{r.name}` | {r.proves} | {'PASS' if r.passed else '**FAIL**'} | {r.ms} |")
    lines += ["", "## Evidence per scenario", ""]
    for r in results:
        lines.append(f"### {'PASS' if r.passed else 'FAIL'}: `{r.name}`")
        lines += [f"- {fact}" for fact in r.facts]
        lines.append("")
    OUT.write_text("\n".join(lines))
    for r in results:
        print(f"{'PASS' if r.passed else 'FAIL'}  {r.group:10}  {r.name}")
        if not r.passed:
            for fact in r.facts:
                print(f"        {fact}")
    print(f"\n{passed}/{len(results)} passed. Report: {OUT}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

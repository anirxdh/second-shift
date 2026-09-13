"""Load the demo company. Customer emails are plus-aliases of the demo inbox,
so a live demo never emails a real third party."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Company

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "company.json"


def alias_email(base: str | None, tag: str) -> str:
    if not base:
        return f"demo+{tag}@example.com"
    user, domain = base.split("@", 1)
    return f"{user}+{tag}@{domain}"


def load_company(demo_gmail: str | None = None, path: Path = FIXTURE) -> Company:
    raw = json.loads(path.read_text())
    for job in raw["jobs"]:
        job["customer_email"] = alias_email(demo_gmail, "cust-" + job.pop("alias"))
    return Company.model_validate(raw)

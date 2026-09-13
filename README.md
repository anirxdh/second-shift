# Second Shift

When a technician calls out sick, Second Shift re-plans a service crew's day across **Slack, Google Sheets, Google Calendar, and Gmail**, then proves the result.

A constraint solver finds a legal new plan: skills, promised arrival windows, shifts, drive time, and no double-booking. An independent checker verifies it. A dispatcher approves. The agent re-checks that nothing changed, writes to all four apps through an idempotent ledger, and reads everything back.

- System and reliability brief: [docs/BRIEF.md](docs/BRIEF.md)
- Reliability report (26 scenarios): [evals/REPORT.md](evals/REPORT.md)
- Message-understanding report: [evals/LLM_REPORT.md](evals/LLM_REPORT.md)

## Run it in 1 minute (fake apps, no accounts)

```bash
uv sync
uv run uvicorn second_shift.server:app --port 8000
```

Open http://localhost:8000 and click **Plan manually → Marco**, then **Approve**. The in-memory Sheets, Calendar, Slack, and Gmail use the same engine code as the live run. To let Claude read typed Slack messages, put `ANTHROPIC_API_KEY` in `.env` (copy `.env.example`).

## Run it live (real Google + Slack, all free tiers)

1. Follow [SETUP.md](SETUP.md): Google Cloud OAuth client, free Slack workspace and app, Anthropic key.
2. `uv run python scripts/check_setup.py`. Every line should say PASS.
3. `uv run python scripts/seed_live.py` creates the Jobs sheet and one calendar per technician, with today's bookings.
4. `SECOND_SHIFT_MODE=live uv run uvicorn second_shift.server:app --port 8000`
5. In Slack `#dispatch`, post: `Marco just called, he's out sick all day`. The plan appears in the app. Approve it, then watch Calendar, the sheet, Slack, and the Gmail inbox update.

## Tests and evals

```bash
uv run pytest -q                 # 26 reliability scenarios + 74 adapter unit tests
uv run python -m evals.run       # same scenarios, writes evals/REPORT.md
uv run python -m evals.llm_eval  # real Claude calls, writes evals/LLM_REPORT.md
```

## Layout

```
second_shift/
  models.py        jobs, technicians, plans (times = minutes since midnight)
  solver.py        OR-Tools CP-SAT re-planner
  validate.py      independent rule checker (shares no code with the solver)
  engine.py        read -> parse -> guard -> solve -> check -> approve -> re-check -> write -> verify
  ledger.py        SQLite record of plans, every write (pending/done/failed), and the trace
  parse.py         Claude structured-output reader for Slack messages
  messages.py      Slack and email templates (facts come from the plan, never the model)
  sheet_codec.py   Company <-> spreadsheet tabs
  adapters/        real Google/Slack adapters + in-memory fakes with fault injection
  server.py        FastAPI app + JSON API
web/               dispatcher dashboard
evals/             reliability scenarios and the message eval
scripts/           setup check and live seeding/reset
fixtures/          the demo company (6 technicians, 16 jobs)
```

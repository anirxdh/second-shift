# 2-minute demo script

Setup before recording: `uv run python scripts/seed_live.py` (clean day), app running in live mode,
browser tabs ready: the app, Slack #dispatch, Google Calendar (all 6 tech calendars visible, day view),
the Jobs sheet, and the Gmail inbox. Record at 1440x900.

| Time | Screen | Say |
|---|---|---|
| 0:00-0:12 | Slack #dispatch | "It's 6:45 AM at a home-services company. Marco, one of only two gas-certified HVAC techs, just called in sick. Four customers are expecting him, including an 11 o'clock contract job." Post: *Marco just called, he's out sick all day* |
| 0:12-0:22 | Slack | The agent replies within seconds: *covers 3 of 4 affected jobs, 1 needs rescheduling, 5 customers would be emailed. Nothing changes until dispatch approves.* "Claude reads the message. Code decides everything else." |
| 0:22-0:45 | App: schedule board, After view | "It read the jobs from Google Sheets and everyone's day from Google Calendar, then a constraint solver re-planned the whole crew." Point at the chain move: "Wei is the only other gas-certified HVAC tech, but he was booked. So it gives Wei's plumbing job to Ana, which frees Wei for the contract job at exactly 11. Rosa's AC repair goes to Priya, still inside her 8 to 10 window." Point at the red tray: "One job truly has no legal slot. It doesn't fake it; that customer gets a reschedule request." |
| 0:45-0:55 | App: plan panel | "An independent checker re-verifies every rule. Here is exactly what it will write in each app." Click **Approve**. |
| 0:55-1:20 | Calendar, Sheet, Slack, Gmail (quick cuts) | "Right before writing, it re-reads everything to make sure nothing changed. Then Calendar bookings move, the sheet updates, each tech gets their new route in Slack, and customers get an email." |
| 1:20-1:35 | App: verification + trace | "Then it reads everything back: 36 of 36 checks passed. Every step is traced." |
| 1:35-1:52 | App: Reliability lab, or drag a Calendar event before approving | "If someone edits the calendar while the plan waits, it refuses to write and re-plans. If it crashes mid-run, it resumes without double-booking or double-emailing anyone." Show the stale banner or the crash/resume. |
| 1:52-2:00 | evals/REPORT.md | "26 reliability scenarios pass, including crashes, rate limits, and prompt injection. Second Shift." |

Backup if live apps misbehave: switch to fake mode (`SECOND_SHIFT_MODE=fake`), which uses the same engine.

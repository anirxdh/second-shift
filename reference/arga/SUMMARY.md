Source: https://docs.argalabs.com/llms.txt https://www.argalabs.com/pricing
Fetched: 2026-09-13T06:19:43.055423+00:00

# Arga Labs

## Hackathon planning assumption

Per the user, assume hackathon credits or complimentary access will cover the lowest paid tier. The captured marketing page calls that tier Pro. Use paid-tier access as the planning baseline; the conflicting documentation means exact quotas and multi-twin entitlements still need confirmation when access is issued. The free-tier limits below are reference facts, not our assumed project constraint.

Arga provides stateful service twins, reusable seeded scenarios, API/MCP access, and browser test runs. For this hackathon, it can supply controlled app environments and repeatable evaluation cases.

Access: start at https://login.argalabs.com/ from the marketing site's “Get started” / “Spin up a twin” links. The dashboard is https://app.argalabs.com/. No account was created.

Free: the docs specify 10 URL Test Runs/month, one service twin per short-lived run, and a fixed 10-minute TTL. The marketing page instead calls the monthly quota “10 pre-built digital twins,” also with one twin/run and 10-minute sessions. Paid plans also conflict: docs describe Free/Team/Paid, while marketing describes Free/Pro/Team/Enterprise. Treat paid limits and the monthly free quota as unresolved; both raw sources are preserved. A three-app scenario may need access beyond the one-twin-per-run free limit. Hackathon-specific access was not established by this scrape.

Useful starting pages:

1. [Twins quickstart](docs/features/twins-quickstart.md) — provision twins and obtain endpoints.
2. [Twin reference](docs/concepts/twin-reference.md) — service coverage, limits, MCP tools.
3. [Local testing](docs/features/local-testing.md) — replace real API endpoints.
4. [Custom scenarios](docs/features/custom-scenarios.md) — seed repeatable starting state.
5. [Test workflows](docs/features/validate-modes.md) — choose the appropriate run type.
6. [Python SDK](docs/sdks/python.md) — Python client and linked method references.
7. [TypeScript SDK](docs/sdks/typescript.md) — TypeScript client and linked method references.
8. [MCP tools](docs/mcp-tools.md) — coding-agent integration.
9. [Plans](docs/plans.md) — limits; compare with [marketing pricing](marketing/pricing.txt).
10. [ArgaBench](marketing/benchmark.txt) — multi-system tasks and executable evaluation context.

`docs/_llms-full.txt` preserves the combined docs. `skills-or-repos/` contains seven official repositories: both SDKs, CLI, quickstart stub, twin take-home starter, multi-app benchmark, and visual workflow builder. Commit IDs are recorded in `../repos-manifest.txt`.

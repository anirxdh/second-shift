Source: https://docs.uselemma.ai/llms.txt https://www.uselemma.ai/
Fetched: 2026-09-13T06:19:43.055423+00:00

# Lemma AI

## Hackathon planning assumption

Per the user, assume hackathon credits or complimentary access will cover the lowest paid plan. Plan to use paid access for tracing and evaluation. No paid-tier name or quota was established by the captured sources, so do not infer unlimited usage or particular entitlements.

Lemma records agent traces, analyzes completed executions for failures, groups repeated evidence into issues, and supports investigation and alerts through its dashboard, Slack, Linear, MCP, and webhooks. Its docs explicitly describe detection as probabilistic; inspect supporting traces before treating findings as ground truth.

Access: the homepage links to https://platform.uselemma.ai/ for login and offers a demo. The documented setup is to select/create an organization and project, generate a server-side API key, and instrument the agent. Verify a real execution becomes a ready, inspectable trace. No login, signup, or demo booking was performed.

Free: no explicit free-tier allowance or public price was found in the captured homepage and documentation. Do not assume tracing or evaluation is free; hackathon access remains unverified.

Useful starting pages:

1. [Setup](docs/tracing/instrumentation/setup.md) — environment variables and first trace.
2. [Instrument an agent](docs/tracing/instrumentation/instrument-an-agent.md) — trace structure.
3. [Tool calls](docs/tracing/instrumentation/tool-calls.md) — external actions and tool spans.
4. [Generations](docs/tracing/instrumentation/generations.md) — model calls.
5. [Trace contract](docs/reference/trace-contract.md) — exact ingestion requirements.
6. [High-quality traces](docs/guides/building-high-quality-traces.md) — useful evidence.
7. [Multi-turn agents](docs/guides/instrumenting-multi-turn-agents.md) — conversation continuity.
8. [Examples](docs/guides/examples.md) — implementation examples.
9. [OpenAI Agents integration](docs/integrations/openai-agents.md) — framework integration; other integrations are also saved.
10. [Slack](docs/connections/slack.md) — alerting and issue briefs.

`docs/_llms-full.txt` preserves the combined docs. The exact clone of https://github.com/uselemma/skills is in `skills-repo/`; its files are reference material and were not installed or executed.

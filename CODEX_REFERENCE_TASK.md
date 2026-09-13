# Task for Codex: build the `reference/` folder

We are entering the Multi-App AI Agent Hackathon (virtual, Sunday Sept 13, 2026).
Brief: build one useful multi-step AI agent that connects to at least 3 external apps, and prove it works.
Judging: 30% technical execution, 25% reliability & evaluation, 20% usefulness, 15% originality, 10% demo.

The hosts and judges run companies that test and monitor AI agents (Arga Labs, Lemma AI), so we will
probably use their products. Scrape their docs into this repo so the coding agent can read them offline.

## Rules

1. Save content **raw**. Do not summarize or rewrite docs pages. We need exact API shapes, field names, and code samples.
2. At the top of every saved file, add two lines: `Source: <url>` and `Fetched: <date>`.
3. The docs sites serve raw markdown. Any URL ending in `.md` or `.txt` below can be fetched with plain `curl`. No browser needed.
4. The marketing sites (argalabs.com, userlens.io, getclera.com) render with JavaScript. `curl` returns an empty page. Use a headless browser (Playwright) and save `document.body.innerText`.
5. After scraping, write a short `SUMMARY.md` in each vendor folder: what the product does, how you sign up, what's free, and the 5 to 10 most useful pages for building an agent.
6. Write `reference/INDEX.md` with one line per file: path and what it's for.
7. Do not sign up for anything, submit any form, or book any demo.

## Folder layout

```
reference/
  INDEX.md
  00-hackathon/
  arga/
    docs/          one file per docs page
    marketing/
    skills-or-repos/
  lemma/
    docs/
    marketing/
    skills-repo/   git clone of github.com/uselemma/skills
  userlens/
  clera/
  comma/
```

## 1. Hackathon site (small)

- https://multiappagenthackathon.com/
- https://multiappagenthackathon.com/judges/

## 2. Arga Labs (judges: CEO Phillip Li and CTO Akira Tong). HIGHEST PRIORITY

What it is: "twins", which are fake but stateful copies of Slack, Gmail, GitHub, Stripe, Google Calendar,
Notion, Linear, HubSpot and about 30 more. You point your agent at a twin URL instead of the real API,
let it act, then check the results. This is how we'd prove our agent works.

Docs (plain curl):
- https://docs.argalabs.com/llms-full.txt   ALL docs in one file (about 340 KB). Save as `arga/docs/_llms-full.txt`
- https://docs.argalabs.com/llms.txt        Index of every page. Use it to fetch each page below as its own file.
- https://docs.argalabs.com/AGENTS.md       Instructions written for coding agents. Important.
- Fetch every `.md` link listed in llms.txt into `arga/docs/`. The most important ones:
  - https://docs.argalabs.com/concepts/twin-reference.md       which twins exist, their limits, their MCP tools
  - https://docs.argalabs.com/features/twins-quickstart.md
  - https://docs.argalabs.com/features/local-testing.md         twins as drop-in replacements for real APIs
  - https://docs.argalabs.com/features/custom-scenarios.md      seeding twins with starting data
  - https://docs.argalabs.com/features/validate-modes.md
  - https://docs.argalabs.com/features/google-workspace-cli.md
  - https://docs.argalabs.com/mcp-tools.md
  - https://docs.argalabs.com/cli-and-mcp.md
  - https://docs.argalabs.com/plans.md
  - https://docs.argalabs.com/sdks/python.md and all of `sdks/python/*`
  - https://docs.argalabs.com/sdks/typescript.md and all of `sdks/typescript/*`
  - all of `api-reference/*`

Marketing (headless browser):
- https://www.argalabs.com/
- https://www.argalabs.com/twins            full list of available twins
- https://www.argalabs.com/twins/slack
- https://www.argalabs.com/twins/github
- https://www.argalabs.com/twins/gmail
- https://www.argalabs.com/use-cases/rl-training
- https://www.argalabs.com/use-cases/enterprise-agent-sandboxes
- https://www.argalabs.com/use-cases/code-change-validation
- https://www.argalabs.com/blog/making-ai-agents-ready-for-the-real-world
- https://www.argalabs.com/blog   (index, plus every post linked from it)
- https://www.argalabs.com/research   (index, plus every item linked from it)
- https://www.argalabs.com/pricing

Also search GitHub for public repos or SDKs from Arga Labs (org name might be `argalabs` or `arga-labs`). Clone any SDK or example repos into `arga/skills-or-repos/`.

## 3. Lemma AI (host). HIGH PRIORITY

What it is: monitoring for AI agents in production. You send it traces (every model call and tool call),
and it flags failures that look like success, groups them into issues, and alerts in Slack.
This is how we'd show "we know it works" while it runs.

Docs (plain curl):
- https://docs.uselemma.ai/llms-full.txt   ALL docs in one file (about 300 KB). Save as `lemma/docs/_llms-full.txt`
- https://docs.uselemma.ai/llms.txt        Index. Fetch every `.md` page into `lemma/docs/`. The most important ones:
  - https://docs.uselemma.ai/tracing/instrumentation/setup.md                 quickstart
  - https://docs.uselemma.ai/tracing/instrumentation/instrument-an-agent.md
  - https://docs.uselemma.ai/tracing/instrumentation/tool-calls.md
  - https://docs.uselemma.ai/tracing/instrumentation/generations.md
  - https://docs.uselemma.ai/tracing/instrumentation/context.md
  - https://docs.uselemma.ai/reference/trace-contract.md
  - https://docs.uselemma.ai/guides/building-high-quality-traces.md
  - https://docs.uselemma.ai/guides/instrumenting-multi-turn-agents.md
  - https://docs.uselemma.ai/guides/examples.md
  - https://docs.uselemma.ai/integrations/openai-agents.md
  - https://docs.uselemma.ai/integrations/vercel-ai.md
  - https://docs.uselemma.ai/integrations/langchain.md
  - https://docs.uselemma.ai/integrations/langgraph.md
  - https://docs.uselemma.ai/integrations/mastra.md
  - https://docs.uselemma.ai/connections/mcp.md
  - https://docs.uselemma.ai/connections/slack.md
  - https://docs.uselemma.ai/connections/linear.md
  - https://docs.uselemma.ai/connections/webhooks.md
  - all of `platform/*` and `api-reference/*`

Repo:
- `git clone https://github.com/uselemma/skills lemma/skills-repo`   (their homepage says: install this skill to add tracing)

Marketing (headless browser):
- https://www.uselemma.ai/
- https://www.uselemma.ai/blog   (index, plus every post)
- https://www.uselemma.ai/weekly/issue-003
- https://www.uselemma.ai/changelog

## 4. Userlens (judges: CEO Ankur Dahama and co-founder Hai Ta). CONTEXT ONLY

What it is: Lumi, an agent that reads how each customer uses a product and sends them personal guidance.
No public developer docs found. We only need to understand what they value.
- https://userlens.io/llms.txt   (plain curl, good overview)
- https://userlens.io/           (headless)
- https://userlens.io/lumi
- https://userlens.io/news/introducing-lumi
- https://userlens.io/pricing

## 5. Clera (judge: founding engineer Shlok Mundhra). CONTEXT ONLY

What it is: an AI talent agent that matches job seekers to startups and makes intros.
- https://www.getclera.com/   (headless)
- try https://www.getclera.com/llms.txt, save it if it exists

## 6. Comma Capital (co-host, a VC fund). CONTEXT ONLY

- https://comma.vc/   (headless, homepage only)

## Do NOT scrape yet

- **The docs for the 3+ apps our agent will use** (Slack API, Gmail API, etc.). We haven't picked the idea yet, and those docs are huge. We'll scrape only the endpoints we need once the idea is locked.
- **Anthropic / Claude docs.** Claude Code already has these built in.

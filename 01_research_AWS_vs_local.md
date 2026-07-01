# Career Site Agent — Research: AWS vs Local + n8n

Date: 2026-06-07
Owner: Akhilesh

## TL;DR

For a **personal** job-application system at low volume (you, ~20–100 jobs/week), **AWS Bedrock AgentCore is overkill and expensive**. The realistic path is **n8n (self-hosted) + Claude/OpenAI API + Playwright + Google Sheets API**, deployed on a $5–12/month VPS. AWS becomes interesting only if you want to put this on your resume as "deployed agentic system on AWS" — in which case use Bedrock AgentCore for *one* showcase agent and keep the rest local.

Two things you must know up front:

1. **LinkedIn outreach automation is a real ban risk.** ~23% of automation users get restricted within 90 days per industry data ([Growleads, 2026](https://growleads.io/blog/linkedin-automation-ban-risk-2026-safe-use/)). Recommendation below mitigates this but does not eliminate it.
2. **AWS does not have a "job application autofill" service.** No vendor does. That agent has to be built with a browser-automation tool (Playwright / browser-use / Stagehand) driven by an LLM. This is true whether you host on AWS or locally.

---

## 1. Does AWS offer AI agent services?

Yes. Three relevant products:

### a) Amazon Bedrock AgentCore (the main one)

Source: [AWS — Amazon Bedrock AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)

Quote: "AgentCore Runtime charges $0.0895 per vCPU-hour and $0.00945 per GB-hour based on active CPU use and peak memory consumed over time."

Pricing has **five separate billed components**, per [Cloud Burn's breakdown](https://cloudburn.io/blog/amazon-bedrock-agentcore-pricing):

| Component | What it bills |
|---|---|
| Runtime | per-second vCPU + GB-hours (only while CPU is active — idle = free) |
| Gateway | per MCP/tool operation |
| Memory | per raw event + per record processed |
| Identity | per OAuth token / API key |
| Policy | $0.000025 per authorization request |

Plus you separately pay for **model inference** (Claude/Llama/Nova tokens) on top.

**Realistic monthly cost for your use case** (very low volume — ~5 agent runs/day, low token counts): probably **$15–60/month** on AgentCore infra + **$10–40/month** in model tokens. The published "moderate" example is $50–200 infra + $200–800 models — but that's 10,000 conversations/month, not your scale ([Cloud Burn](https://cloudburn.io/blog/amazon-bedrock-agentcore-pricing)).

**The cost trap**, quoted from [Bacancy's 2026 Bedrock guide](https://www.bacancytechnology.com/blog/aws-bedrock-pricing): *"For agentic workloads, multiply the result by 5 to 8 to account for token amplification. … a single user question might trigger 10x the tokens you expected due to this internal looping and reasoning trace."*

### b) Amazon Bedrock (plain) — model API only

Pay-per-token access to Claude, Llama, Nova, Mistral. No "agent" wrapper. You'd write your own orchestration. Same per-token price as calling Anthropic / OpenAI directly. No advantage for you unless you're already deep in AWS.

### c) Amazon Q Developer — NOT for this

Source: [AWS — Q Developer Pricing](https://aws.amazon.com/q/developer/pricing/). Free tier exists; Pro is $19/user/month. This is a coding assistant (IDE plugin). Not for building application agents. Skip.

---

## 2. The 5 agents — what each one actually needs

| # | Agent | Where the work happens | AWS service? |
|---|---|---|---|
| 1 | Job search by profile | LinkedIn/Indeed scraping or RSS + LLM scoring | No native AWS — needs scraping layer (Bright Data, SerpAPI, or LinkedIn RSS) |
| 2 | Resume tailoring per JD | Pure LLM task | Bedrock works; so does Claude API directly |
| 3 | Application autofill in portals | **Browser automation + LLM** | No AWS service. Must use Playwright / browser-use / Stagehand |
| 4 | Recruiter finder + LinkedIn DM draft | Scraping + LLM | No AWS service; LinkedIn ToS risk (see below) |
| 5 | Google Sheet + Gmail tracking | Sheets API + Gmail API + LLM | n8n has native nodes; AWS doesn't add value here |

**Conclusion:** Only agents #2 (resume tailoring) and partially #5 (email parsing) are clean fits for AWS Bedrock. The rest need browser/scraping infrastructure that AWS doesn't provide as a managed service.

---

## 3. LinkedIn risk — read this before building agent #4

Source: [Growleads — LinkedIn Automation Ban Risk 2026](https://growleads.io/blog/linkedin-automation-ban-risk-2026-safe-use/)

Quote: "Around 23% of automation users face a restriction within their first 90 days."

Source: [ConnectSafely.ai — LinkedIn ToS 2026](https://connectsafely.ai/articles/is-linkedin-automation-safe-tos-scraping-guide-2026)

Quote: LinkedIn prohibits automation that "simulates human behavior at scale" and bans bots and scraping — but not all automation.

What this means for agent #4:
- **Don't** auto-send connection requests at scale. The agent should *draft* the note and surface a "click to send" review step.
- Stay under ~3% of total connections per day in invites ([Growleads, 2026](https://growleads.io/blog/linkedin-automation-ban-risk-2026-safe-use/)).
- For finding recruiters, prefer LinkedIn's own search UI (manual click-through) or paid APIs like [Apollo.io](https://www.apollo.io) / Hunter.io rather than scraping LinkedIn profile pages.

---

## 4. Recommended architecture — Local + n8n

This is the cheapest, most controllable path. Working n8n templates already exist for exactly this use case:

- [n8n — Automated job applications & status tracking with LinkedIn, Indeed & Google Sheets](https://n8n.io/workflows/5906-automated-job-applications-and-status-tracking-with-linkedin-indeed-and-google-sheets/)
- [n8n — AI resume tailoring with GPT-4o, LinkedIn & Gmail](https://n8n.io/workflows/11215-automate-job-applications-with-ai-resume-tailoring-using-gpt-4o-linkedin-and-gmail/)
- [n8n — LinkedIn job finder using Bright Data API & Google Sheets](https://n8n.io/workflows/4775-linkedin-job-finder-automation-using-bright-data-api-and-google-sheets/)
- [GitHub — AloysJehwin/job-app (resume tailoring + Sheets via n8n)](https://github.com/AloysJehwin/job-app)

### Stack

| Layer | Tool | Cost |
|---|---|---|
| Orchestrator | n8n (self-hosted, Docker) | Free locally; $5–12/mo on a Hetzner/DigitalOcean VPS once deployed |
| LLM brain | Claude API (Sonnet 4.6 for tailoring, Haiku 4.5 for cheap classification) | ~$10–30/mo at your volume |
| Job sourcing | LinkedIn/Indeed RSS feeds, or Bright Data / SerpAPI for richer search | RSS = free; Bright Data ~$15–50/mo |
| Browser automation (autofill) | Playwright via n8n's Execute Command node, or [browser-use](https://github.com/browser-use/browser-use) | Free |
| Recruiter contact lookup | Apollo.io free tier or Hunter.io | Free tier OK to start |
| Sheets + Gmail | Native n8n Google nodes | Free |
| Local dev box | Your PC (Docker Desktop) | $0 |
| Production hosting | Hetzner CX22 VPS or Railway | $5–12/mo |

**Estimated total: $20–60/month** vs. AWS's $50–200+/month for the same workload.

### Workflow map (one per agent)

1. **Job search** — Cron trigger → fetch LinkedIn/Indeed RSS or Bright Data API → loop jobs → Claude scores fit vs your profile → write filtered jobs to Sheet.
2. **Resume tailoring** — Triggered per job row → Claude rewrites resume sections to match JD → save .docx to Drive → link back to Sheet row.
3. **Autofill** — n8n triggers a Playwright script (or [browser-use](https://github.com/browser-use/browser-use), an LLM-driven browser agent) that opens the application URL, reads form fields, asks Claude what to put in each, fills it, and **pauses for your approval before submit**.
4. **Recruiter + DM draft** — Use Apollo.io / Hunter.io to find recruiters at the company → Claude drafts a 300-char connection note referencing the JD → write to Sheet "Connections" tab → you click send manually in LinkedIn (to dodge the ban risk).
5. **Status tracker** — Cron → Gmail node filters job-related emails → Claude classifies (rejection / interview / offer / no-reply) → updates Status column in Sheet.

### Deployment to internet

- Day 1: Run n8n in Docker on your PC. Get all 5 workflows working.
- Day 2: Move to a $5/mo Hetzner VPS or use [n8n Cloud](https://n8n.io/cloud/) starter tier (~$20/mo) if you don't want to manage Linux.
- Day 3: Point a domain at it, set up Cloudflare Tunnel for free HTTPS.

Resume bullet you can write afterward: *"Designed and deployed a 5-agent job-application automation system using n8n, Claude API, and Playwright on a self-managed VPS — reduced application time per role from 25 min to 4 min."*

---

## 5. Hybrid option (resume booster)

If the resume signal matters more than cost:

- Run agents 1, 3, 4, 5 in n8n (cheap, local).
- Build agent **#2 (resume tailoring)** on **AWS Bedrock AgentCore** with Claude Sonnet 4.6 as the model and a real MCP gateway. Cost: ~$10–25/month extra. Now you can truthfully claim AWS Bedrock AgentCore experience on your resume — which is a genuinely scarce skill in 2026.

---

## 6. What I'm NOT confident about

- Exact Bedrock AgentCore cost for *your* volume. I'm extrapolating from AWS's published "moderate" example downward. You'd want to run the [AWS pricing calculator](https://aws.amazon.com/bedrock/agentcore/pricing/) once your token counts stabilize.
- Whether LinkedIn RSS still returns full job postings in 2026 — needs a live test.
- Whether Workday/Greenhouse/Lever portals you target have anti-bot measures that defeat Playwright. Real-world hit rate is probably 60–80%, not 100%.

---

## Sources

- [AWS — Amazon Bedrock AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- [AWS — Amazon Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
- [AWS — Amazon Q Developer Pricing](https://aws.amazon.com/q/developer/pricing/)
- [Cloud Burn — AgentCore Pricing Breakdown](https://cloudburn.io/blog/amazon-bedrock-agentcore-pricing)
- [Bacancy — AWS Bedrock Pricing 2026](https://www.bacancytechnology.com/blog/aws-bedrock-pricing)
- [Growleads — LinkedIn Automation Ban Risk 2026](https://growleads.io/blog/linkedin-automation-ban-risk-2026-safe-use/)
- [ConnectSafely.ai — LinkedIn ToS 2026](https://connectsafely.ai/articles/is-linkedin-automation-safe-tos-scraping-guide-2026)
- [n8n template — Automated job applications & status tracking](https://n8n.io/workflows/5906-automated-job-applications-and-status-tracking-with-linkedin-indeed-and-google-sheets/)
- [n8n template — AI resume tailoring with GPT-4o](https://n8n.io/workflows/11215-automate-job-applications-with-ai-resume-tailoring-using-gpt-4o-linkedin-and-gmail/)
- [n8n template — LinkedIn job finder (Bright Data)](https://n8n.io/workflows/4775-linkedin-job-finder-automation-using-bright-data-api-and-google-sheets/)
- [GitHub — AloysJehwin/job-app](https://github.com/AloysJehwin/job-app)
- [browser-use — LLM-driven browser automation](https://github.com/browser-use/browser-use)

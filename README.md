# claude-code-router

Routes Claude Code requests across Alkemio's tiered AI inference architecture, as defined in the [Alkemio AI Inference Hosting Policy](https://alkemio.org) (February 2026).

```
Claude Code session
  │  ANTHROPIC_BASE_URL=http://localhost:4000
  ▼
┌──────────────────────────────────────────────────────┐
│            LiteLLM Proxy (Docker, :4000)              │
│                                                       │
│  task_router.py inspects:                             │
│   • MCP tool namespaces (scaleway, ory_kratos, ...)  │
│   • Repo path (alkemio/server vs alkemio/client)     │
│   • Content patterns (test gen, refactoring, docs)   │
│                                                       │
│  Routes to the appropriate tier:                      │
└───┬──────────┬──────────┬──────────────┬──────────────┘
    ▼          ▼          ▼              ▼
 Tier 1     Tier 1     Tier 2        Tier 3
 Primary    Fallback   EU APIs     Commercial
 (vLLM)   (DGX Spark) (Scaleway)  (Claude/Alibaba)
```

## Policy Alignment

| Tier | What | When | Pool Name |
|---|---|---|---|
| **1** | Company-owned hardware (RTX PRO 6000, DGX Spark) | Phase 1+ | `tier1-primary`, `tier1-fallback` |
| **2** | EU-hosted open-weight APIs (Scaleway AI, Mistral) | Phase 2+ | `tier2-eu` |
| **3** | Commercial coding tools — scoped exception | Now | `tier3-claude`, `tier3-alibaba` |

**Key policy constraints reflected in routing:**

- Platform AI and user data processing → Tier 1 only (when deployed). Never Tier 3.
- Batch coding tasks (test gen, refactoring, migrations) → Tier 1 when available, currently Tier 3 cost tier (Alibaba).
- Interactive coding requiring frontier capability → Tier 3 Claude (scoped exception: code only, no user data).
- Tier 2 is overflow/emergency failover only, not routine.
- Fallback chain follows Section 7.3: Tier 1 primary → DGX Spark → Tier 2 EU → Tier 3.

## Setup

```bash
git clone git@github.com:alkemio/claude-code-router.git
cd claude-code-router
cp .env.example .env
# Edit .env — add your API keys
docker compose up -d
```

In your shell profile (`~/.bashrc`, `~/.zshrc`):

```bash
export ANTHROPIC_BASE_URL=http://localhost:4000
```

Restart terminal, run `claude` as normal.

## Current State (Phase 1)

Only Tier 3 pools are active. The router optimises cost within Tier 3 by
sending routine tasks to Alibaba (Qwen) and reserving Claude for the
core server repo and complex reasoning.

When Tier 1 hardware is deployed, uncomment the corresponding sections in
`litellm_config.yaml` and `task_router.py`. Batch coding and internal ops
will automatically route to local hardware.

## Routing Rules

Rules are in `task_router.py`, evaluated by priority (lower = first). First match wins.

### Currently Active

| Priority | Rule | Signal | Pool |
|---|---|---|---|
| 10 | infra-scaleway | MCP: `scaleway` | tier3-alibaba |
| 10 | identity-ory | MCP: `ory_kratos`, `ory_hydra` | tier3-alibaba |
| 10 | project-management | MCP: `github`, `gitlab` | tier3-alibaba |
| 10 | kubernetes | MCP: `kubernetes` | tier3-alibaba |
| 50 | alkemio-server-core | Repo: `alkemio/server` | tier3-claude |
| 50 | alkemio-client | Repo: `alkemio/client` | tier3-alibaba |
| 50 | alkemio-infra | Repo: `alkemio/infra`, `terraform`, etc. | tier3-alibaba |
| 50 | alkemio-tooling | Repo: `alkemio/mcp`, `mcp-ory-kratos` | tier3-alibaba |
| 70 | batch-test-generation | Content: "generate tests" | tier3-alibaba |
| 70 | batch-refactoring | Content: "refactor all" | tier3-alibaba |
| 70 | batch-documentation | Content: "generate jsdoc" | tier3-alibaba |
| — | (default) | No match | tier3-claude |

### Planned (Tier 1 Online)

When Tier 1 hardware is deployed, batch coding and Platform AI rules at priority 5
will route to `tier1-primary` before any Tier 3 rules are evaluated.

## Adding a Provider

1. Add deployment to `litellm_config.yaml` under `model_list` with a `model_name`
2. Reference that name as `pool` in routing rules in `task_router.py`
3. Add fallback chain in `router_settings.fallbacks`
4. `docker compose restart litellm`

## Enabling Tier 1 (Local Hardware)

When the RTX PRO 6000 workstation is running vLLM:

1. Uncomment `tier1-primary` and `tier1-fallback` in `litellm_config.yaml`
2. Uncomment `TIER1_PRIMARY` / `TIER1_FALLBACK` pool constants in `task_router.py`
3. Uncomment Tier 1 routing rules (priority 5) in `task_router.py`
4. Update batch coding rules (priority 70) to use `TIER1_PRIMARY` instead of `TIER3_ALIBABA`
5. Uncomment fallback chains in `router_settings`
6. `docker compose restart litellm`

For Ollama on the host machine, use `host.docker.internal` as api_base.

## Debugging

```bash
docker compose logs -f litellm
```

Every request logs: MCP namespaces detected, repo path extracted, rule matched, pool selected.

## Caveats

- **MCP tools are per-session, not per-request.** Indicates "what kind of session" not "which tool is being called right now."
- **Repo path extraction is regex-based.** May need updating if Claude Code changes its system prompt format.
- **Provider compatibility.** Tool use, extended thinking, and streaming may differ across providers. Test workflows before routing critical work away from Anthropic.
- **Alibaba (DashScope) is not EU-hosted.** It falls under the same Tier 3 scoped exception as Claude Code — code only, no user data, per policy Section 5.3.

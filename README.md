# claude-code-router

A local LiteLLM proxy that routes Claude Code requests to different model pools based on the task, optimising cost by sending routine work to cheaper models and reserving frontier models for complex reasoning.

```
Claude Code session
  │  ANTHROPIC_BASE_URL=http://localhost:4891
  ▼
┌──────────────────────────────────────────────────────┐
│            LiteLLM Proxy (Docker, :4891)              │
│                                                       │
│  task_router.py inspects:                             │
│   • MCP tool namespaces (scaleway, ory_kratos, ...)  │
│   • Repo path (alkemio/server vs alkemio/client)     │
│   • Content patterns (test gen, refactoring, docs)   │
│                                                       │
│  Routes to the appropriate pool:                      │
└───┬────────────────┬─────────────────┬────────────────┘
    ▼                ▼                 ▼
  Claude           Qwen            Local
  (Anthropic)    (DashScope)     (self-hosted)
  frontier       cost-optimised   future
```

## Model Pools

| Pool | Provider | Use Case |
|------|----------|----------|
| `claude` | Anthropic (Claude Sonnet 4) | Complex reasoning, agentic workflows |
| `qwen` | Alibaba DashScope (Qwen3.5 Plus) | Routine tasks, batch operations |
| `local-primary` | vLLM on own hardware | Future — batch coding, full sovereignty |
| `local-fallback` | DGX Spark | Future — fallback for local pool |

## Setup

```bash
git clone git@github.com:alkemio/claude-code-router.git
cd claude-code-router
cp .env.example .env
# Edit .env — add your DashScope API key
docker compose up -d
```

In your shell profile (`~/.bashrc`, `~/.zshrc`):

```bash
export ANTHROPIC_BASE_URL=http://localhost:4891
```

Restart terminal, run `claude` as normal.

## Routing Rules

Rules are in `task_router.py`, evaluated by priority (lower = first). First match wins.

| Priority | Rule | Signal | Pool |
|---|---|---|---|
| 10 | infra-scaleway | MCP: `scaleway` | qwen |
| 10 | identity-ory | MCP: `ory_kratos`, `ory_hydra` | qwen |
| 10 | project-management | MCP: `github`, `gitlab` | qwen |
| 10 | kubernetes | MCP: `kubernetes` | qwen |
| 50 | alkemio-server-core | Repo: `alkemio/server` | claude |
| 50 | alkemio-client | Repo: `alkemio/client`, `alkemio/web` | qwen |
| 50 | alkemio-infra | Repo: `alkemio/infra`, `terraform`, etc. | qwen |
| 50 | alkemio-tooling | Repo: `alkemio/mcp`, `mcp-ory-kratos` | qwen |
| 60 | personal-projects | Repo: `personal/`, `sandbox/` | qwen |
| 70 | batch-test-generation | Content: "generate tests" | qwen |
| 70 | batch-refactoring | Content: "refactor all" | qwen |
| 70 | batch-documentation | Content: "generate jsdoc" | qwen |
| — | (default) | No match | claude |

## Adding a Provider

1. Add deployment to `litellm_config.yaml` under `model_list` with a `model_name`
2. Reference that name as `pool` in routing rules in `task_router.py`
3. Add fallback chain in `router_settings.fallbacks`
4. `docker compose restart litellm`

## Enabling Local Hardware

When the RTX PRO 6000 workstation is running vLLM:

1. Uncomment `local-primary` and `local-fallback` in `litellm_config.yaml`
2. Uncomment `LOCAL_PRIMARY` / `LOCAL_FALLBACK` pool constants in `task_router.py`
3. Uncomment local routing rules (priority 5) in `task_router.py`
4. Update batch coding rules (priority 70) to use `LOCAL_PRIMARY` instead of `QWEN`
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

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Setup

```bash
# Install and start
docker compose up -d

# View routing logs
docker compose logs -f litellm

# Restart after config changes
docker compose restart litellm
```

Set in your shell profile:
```bash
export ANTHROPIC_BASE_URL=http://localhost:4891
```

## How Routing Works

The proxy routes requests to different model pools based on:

1. **MCP namespaces** — tools like `scaleway`, `ory_kratos`, `github`
2. **Repo path** — e.g., `alkemio/server` vs `alkemio/client`
3. **Content patterns** — e.g., "generate tests", "refactor"

Rules are in `task_router.py`, evaluated by priority (lower = first). First match wins.

## Active Routing Rules

| Rule | Signal | Model |
|------|--------|-------|
| infra-scaleway | MCP: `scaleway` | qwen3.5-plus |
| identity-ory | MCP: `ory_kratos`, `ory_hydra` | qwen3.5-plus |
| project-management | MCP: `github`, `gitlab` | qwen3.5-plus |
| kubernetes | MCP: `kubernetes` | qwen3.5-plus |
| alkemio-server-core | Repo: `alkemio/server` | claude-sonnet-4 |
| alkemio-client | Repo: `alkemio/client`, `alkemio/web` | qwen3.5-plus |
| alkemio-infra | Repo: `alkemio/infra`, `terraform`, `k8s` | qwen3.5-plus |
| alkemio-tooling | Repo: `alkemio/mcp`, `mcp-ory-kratos` | qwen3.5-plus |
| batch-test-generation | Content: "generate tests" | qwen3.5-plus |
| batch-refactoring | Content: "refactor", "migrate" | qwen3.5-plus |
| batch-documentation | Content: "generate jsdoc" | qwen3.5-plus |
| (default) | No match | claude-sonnet-4 |

## Configuration Files

- `litellm_config.yaml` — model pools and fallback chains
- `task_router.py` — routing rules and logic
- `.env` — API keys (copy from `.env.example`)

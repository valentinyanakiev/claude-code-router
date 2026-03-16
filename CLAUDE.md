# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Routes Claude Code requests across Alkemio's tiered AI inference architecture using LiteLLM as a proxy. Routes based on MCP tool namespaces, repo paths, and content patterns.

## Commands

```bash
# Start the proxy
docker compose up -d

# View logs (debugging routing decisions)
docker compose logs -f litellm

# Restart after config changes
docker compose restart litellm
```

## Architecture

**Key files:**
- `litellm_config.yaml` — defines model pools (tier3-claude, tier3-alibaba, etc.) and fallback chains
- `task_router.py` — routing rules evaluated by priority (lower = first); first match wins
- `docker-compose.yml` — runs LiteLLM proxy with custom routing strategy

**Routing signals (in priority order):**
1. MCP tool namespaces (e.g., `scaleway`, `ory_kratos`, `github`)
2. Repository path (regex match on system prompt)
3. Content patterns (regex on last user message)

**Current state (Phase 1):** Only Tier 3 pools active. Tier 1 (company hardware) and Tier 2 (EU APIs) are commented out, to be enabled when deployed.

**Adding a provider:**
1. Add to `model_list` in `litellm_config.yaml`
2. Reference pool name in `task_router.py` routing rules
3. Add fallback chain in `router_settings.fallbacks`
4. `docker compose restart litellm`

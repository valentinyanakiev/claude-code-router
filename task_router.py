"""
Task-Aware Router for Alkemio Claude Code → LiteLLM Proxy
============================================================

Aligned with: Alkemio AI Inference Hosting Policy (February 2026)

Routes requests across the three-tier inference architecture:

  Tier 1 — Company-owned hardware (vLLM on RTX PRO 6000 / DGX Spark)
           For: batch coding, internal ops, Platform AI
  Tier 2 — EU-hosted open-weight APIs (Scaleway AI, Mistral)
           For: overflow / emergency failover only
  Tier 3 — Commercial coding tools (Claude Code, Alibaba)
           For: interactive coding (scoped exception: code only, no user data)

Routing signals:
  1. MCP tool namespaces — extracted from the tools array
  2. Repository path — extracted from Claude Code's system prompt
  3. Content patterns — optional regex on the last user message

The policy states (Section 5.3):
  - "Well-defined batch coding tasks (automated refactoring, test generation,
    large-scale migrations) are routed to Tier 1 local hardware"
  - Interactive coding requiring frontier model capability stays on Tier 3
  - No user data is ever processed through Tier 3

Usage:
  Referenced by litellm_config.yaml via:
    custom_routing_strategy: "task_router.TaskAwareRouter"
    custom_routing_strategy_path: "./task_router.py"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from litellm.router import CustomRoutingStrategyBase

logger = logging.getLogger("task_router")
logger.setLevel(logging.INFO)

# =============================================================================
# POOL CONFIGURATION
# =============================================================================
# Pool names must match model_name values in litellm_config.yaml.
# As tiers come online, update these and uncomment the corresponding
# model_list entries in litellm_config.yaml.

# Tier 1 pools (uncomment when hardware is deployed — Phase 1, Q1 2026)
# TIER1_PRIMARY = "tier1-primary"
# TIER1_FALLBACK = "tier1-fallback"

# Tier 2 pool (uncomment when EU provider contracts are live — Phase 2, Q2 2026)
# TIER2_EU = "tier2-eu"

# Tier 3 pools (active now)
TIER3_CLAUDE = "tier3-claude"       # Anthropic — frontier interactive coding
TIER3_ALIBABA = "tier3-alibaba"     # DashScope — cost-optimised routine coding

# Default pool: where requests go when no rule matches.
# Currently Tier 3 Claude (interactive coding is the primary Claude Code use case).
# When Tier 1 is live, batch/internal tasks will route there instead.
DEFAULT_POOL = TIER3_CLAUDE


# =============================================================================
# ROUTING RULES
# =============================================================================

@dataclass
class RoutingRule:
    """A single routing rule evaluated by priority (lower = checked first)."""

    name: str
    pool: str
    priority: int = 100
    # Match if ANY of these MCP namespaces appear in the tools array.
    # Namespace = prefix before first "__" in mcp__<namespace>__<tool>
    mcp_namespaces: list[str] = field(default_factory=list)
    # Match if repo path matches any of these regex patterns (case-insensitive).
    repo_patterns: list[str] = field(default_factory=list)
    # Match if last user message matches any of these regex patterns.
    content_patterns: list[str] = field(default_factory=list)


# fmt: off
ROUTING_RULES: list[RoutingRule] = [
    # =========================================================================
    # TIER 1 RULES — uncomment when hardware is deployed
    # =========================================================================
    # Per policy Section 5.1: batch coding tasks with well-defined scope
    # (refactoring, test generation, documentation, migrations) go to Tier 1.
    #
    # RoutingRule(
    #     name="batch-coding-test-gen",
    #     pool=TIER1_PRIMARY,
    #     priority=5,
    #     content_patterns=[
    #         r"(?:generate|write|create)\s+(?:unit\s+)?tests?\b",
    #         r"(?:refactor|migrate|convert)\s+",
    #         r"(?:generate|write)\s+(?:jsdoc|documentation|docs)\b",
    #     ],
    # ),
    # RoutingRule(
    #     name="platform-ai",
    #     pool=TIER1_PRIMARY,
    #     priority=5,
    #     mcp_namespaces=["alkemio_platform"],
    #     repo_patterns=[r"alkemio[/\\]platform-ai", r"alkemio[/\\]virtual-contributor"],
    # ),

    # =========================================================================
    # MCP-NAMESPACE RULES — route infra/identity/PM tasks to cost tier
    # =========================================================================
    # These are routine operational tasks on Alkemio's open-source codebase.
    # Per policy Section 5.3 scoped exception: code only, no user data.
    RoutingRule(
        name="infra-scaleway",
        pool=TIER3_ALIBABA,
        priority=10,
        mcp_namespaces=["scaleway"],
    ),
    RoutingRule(
        name="identity-ory",
        pool=TIER3_ALIBABA,
        priority=10,
        mcp_namespaces=["ory_kratos", "ory_hydra", "ory"],
    ),
    RoutingRule(
        name="project-management",
        pool=TIER3_ALIBABA,
        priority=10,
        mcp_namespaces=["github", "gitlab", "linear", "jira"],
    ),
    RoutingRule(
        name="kubernetes",
        pool=TIER3_ALIBABA,
        priority=10,
        mcp_namespaces=["kubernetes"],
    ),

    # =========================================================================
    # REPO-PATH RULES
    # =========================================================================
    # Core platform server: complex reasoning needed → Claude (frontier)
    RoutingRule(
        name="alkemio-server-core",
        pool=TIER3_CLAUDE,
        priority=50,
        repo_patterns=[r"alkemio[/\\]server"],
    ),
    # Client / frontend: routine → cost tier
    RoutingRule(
        name="alkemio-client",
        pool=TIER3_ALIBABA,
        priority=50,
        repo_patterns=[r"alkemio[/\\]client", r"alkemio[/\\]web"],
    ),
    # Infrastructure repos: routine → cost tier
    RoutingRule(
        name="alkemio-infra",
        pool=TIER3_ALIBABA,
        priority=50,
        repo_patterns=[
            r"alkemio[/\\]infra",
            r"alkemio[/\\]terraform",
            r"alkemio[/\\]k8s",
            r"alkemio[/\\]helm",
            r"alkemio[/\\](?:docker|deploy)",
        ],
    ),
    # MCP servers, tooling repos: routine → cost tier
    RoutingRule(
        name="alkemio-tooling",
        pool=TIER3_ALIBABA,
        priority=50,
        repo_patterns=[
            r"alkemio[/\\]mcp",
            r"mcp-ory-kratos",
            r"alkemio[/\\]scripts",
        ],
    ),
    # Personal / sandbox projects
    RoutingRule(
        name="personal-projects",
        pool=TIER3_ALIBABA,
        priority=60,
        repo_patterns=[r"personal[/\\]", r"sandbox[/\\]", r"experiments[/\\]"],
    ),

    # =========================================================================
    # CONTENT-BASED RULES (lower priority, checked last)
    # =========================================================================
    # Batch coding tasks per policy Section 5.3 mitigations:
    # "Well-defined batch coding tasks are routed to Tier 1 local hardware
    # to reduce both cost and dependency."
    #
    # Currently routes to Alibaba (cost tier) until Tier 1 hardware is live.
    # When Tier 1 is deployed, change pool to TIER1_PRIMARY.
    RoutingRule(
        name="batch-test-generation",
        pool=TIER3_ALIBABA,
        priority=70,
        content_patterns=[
            r"(?:generate|write|create)\s+(?:unit\s+)?tests?\b",
            r"(?:generate|add)\s+(?:test\s+)?coverage\b",
        ],
    ),
    RoutingRule(
        name="batch-refactoring",
        pool=TIER3_ALIBABA,
        priority=70,
        content_patterns=[
            r"(?:refactor|migrate|convert|rename)\s+(?:all|every|each)\b",
            r"(?:find\s+and\s+replace|mass\s+rename|bulk\s+update)\b",
        ],
    ),
    RoutingRule(
        name="batch-documentation",
        pool=TIER3_ALIBABA,
        priority=70,
        content_patterns=[
            r"(?:generate|write|add)\s+(?:jsdoc|tsdoc|docstring|documentation)\b",
        ],
    ),
]
# fmt: on

# Sort once at module load
ROUTING_RULES.sort(key=lambda r: r.priority)


# =============================================================================
# Extraction helpers
# =============================================================================

def extract_mcp_namespaces(tools: list[dict]) -> set[str]:
    """
    Extract MCP server namespaces from the tools array.

    Claude Code tool names follow the pattern:
      mcp__<namespace>__<toolName>
      e.g. mcp__ory_kratos__listIdentities → namespace = "ory_kratos"
    """
    namespaces: set[str] = set()
    for tool in tools:
        name = ""
        if isinstance(tool, dict):
            func = tool.get("function", {})
            name = func.get("name", "") if isinstance(func, dict) else ""
            if not name:
                name = tool.get("name", "")

        if name.startswith("mcp__"):
            parts = name.split("__", 2)
            if len(parts) >= 2:
                namespaces.add(parts[1])

    return namespaces


def extract_repo_path(messages: list[dict]) -> Optional[str]:
    """
    Extract the working directory / repo path from Claude Code's system prompt.
    """
    for msg in messages:
        if msg.get("role") != "system":
            continue

        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )

        patterns = [
            r"(?:current\s+(?:working\s+)?directory|cwd|working\s+in|repo)[\s:]+([^\n\r]+)",
            r"(?:project|repository)\s+(?:root|path|dir)[\s:]+([^\n\r]+)",
            r"(/(?:home|Users|root)/[^\s\n]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()

    return None


def extract_last_user_message(messages: list[dict]) -> str:
    """Get the text of the last user message for content-based routing."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
    return ""


# =============================================================================
# Router implementation
# =============================================================================

class TaskAwareRouter(CustomRoutingStrategyBase):
    """
    Routes Claude Code requests across Alkemio's tiered inference architecture.

    Evaluates routing rules by priority (lower = first). First match wins.
    If no rule matches, routes to DEFAULT_POOL.
    """

    def _pick_pool(
        self,
        messages: Optional[List[Dict[str, str]]],
        request_kwargs: Optional[Dict] = None,
    ) -> str:
        """Evaluate routing rules and return the target pool name."""
        messages = messages or []
        request_kwargs = request_kwargs or {}

        tools = request_kwargs.get("tools", []) or []
        mcp_ns = extract_mcp_namespaces(tools)
        repo_path = extract_repo_path(messages)
        last_msg = extract_last_user_message(messages)

        logger.info(
            f"[TaskRouter] MCP namespaces: {mcp_ns}, "
            f"repo: {repo_path}, "
            f"last_msg_len: {len(last_msg)}"
        )

        for rule in ROUTING_RULES:
            matched = False

            # Check MCP namespace match
            if rule.mcp_namespaces:
                if mcp_ns & set(rule.mcp_namespaces):
                    matched = True
                    logger.info(
                        f"[TaskRouter] Rule '{rule.name}' matched on MCP namespace "
                        f"(hit: {mcp_ns & set(rule.mcp_namespaces)})"
                    )

            # Check repo path match
            if not matched and rule.repo_patterns and repo_path:
                for pattern in rule.repo_patterns:
                    if re.search(pattern, repo_path, re.IGNORECASE):
                        matched = True
                        logger.info(
                            f"[TaskRouter] Rule '{rule.name}' matched on repo "
                            f"path: {repo_path}"
                        )
                        break

            # Check content match
            if not matched and rule.content_patterns and last_msg:
                for pattern in rule.content_patterns:
                    if re.search(pattern, last_msg, re.IGNORECASE):
                        matched = True
                        logger.info(
                            f"[TaskRouter] Rule '{rule.name}' matched on content"
                        )
                        break

            if matched:
                logger.info(f"[TaskRouter] → pool: {rule.pool}")
                return rule.pool

        logger.info(f"[TaskRouter] → No rule matched, default: {DEFAULT_POOL}")
        return DEFAULT_POOL

    def _find_deployment(self, pool: str, router: Any) -> Optional[Dict]:
        """Find a deployment from the router's model list matching the pool."""
        model_list = getattr(router, "model_list", [])
        candidates = [
            m for m in model_list
            if isinstance(m, dict) and m.get("model_name") == pool
        ]
        if not candidates:
            logger.warning(
                f"[TaskRouter] No deployments for pool '{pool}', "
                f"falling back to '{DEFAULT_POOL}'"
            )
            candidates = [
                m for m in model_list
                if isinstance(m, dict) and m.get("model_name") == DEFAULT_POOL
            ]
        return candidates[0] if candidates else None

    async def async_get_available_deployment(
        self,
        model: str,
        messages: Optional[List[Dict[str, str]]] = None,
        input: Optional[Union[str, List]] = None,
        specific_deployment: Optional[bool] = False,
        request_kwargs: Optional[Dict] = None,
    ):
        pool = self._pick_pool(messages, request_kwargs)
        router = getattr(self, "router", None)
        if router is None:
            logger.error("[TaskRouter] No router reference")
            return None

        deployment = self._find_deployment(pool, router)
        if deployment:
            logger.info(
                f"[TaskRouter] Selected: "
                f"{deployment.get('model_info', {}).get('id', '?')}"
            )
        return deployment

    def get_available_deployment(
        self,
        model: str,
        messages: Optional[List[Dict[str, str]]] = None,
        input: Optional[Union[str, List]] = None,
        specific_deployment: Optional[bool] = False,
        request_kwargs: Optional[Dict] = None,
    ):
        pool = self._pick_pool(messages, request_kwargs)
        router = getattr(self, "router", None)
        if router is None:
            return None
        return self._find_deployment(pool, router)

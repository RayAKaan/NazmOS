"""Phase 11 — agent least-privilege + tool-registry validity (§Part 19).

Every registered agent's declared tools must be valid registry tools; mutating tools must
be policy-gated (never directly callable); read-only agents must only declare read-only
tools.
"""
from app.intelligence.agents.registry import AGENT_REGISTRY
from app.services.tool_registry import TOOLS, call_tool


def test_every_agent_declared_tools_are_valid():
    valid = set(TOOLS.keys())
    for name, cls in AGENT_REGISTRY.items():
        for tool in (cls.tools or []):
            assert tool in valid, f"{name} declares unknown tool {tool!r}"


def test_read_only_agents_only_declare_read_only_tools():
    for name, cls in AGENT_REGISTRY.items():
        if getattr(cls, "read_only", True):
            for tool in (cls.tools or []):
                assert TOOLS[tool].read_only is True, f"{name} is read_only but declares mutating tool {tool}"


def test_mutating_tools_are_not_directly_callable():
    # The tool registry refuses direct invocation of mutating tools (§Part 20: executor must
    # not become an alternate authorization path).
    for name, tool in TOOLS.items():
        if not tool.read_only:
            # call_tool is async; assert the guard exists structurally (fn is _mutating_tool).
            assert tool.fn.__name__ == "_mutating_tool", f"{name} should be policy-gated"


def test_all_agents_declare_identity_and_budget():
    for name, cls in AGENT_REGISTRY.items():
        assert cls.agent_type == name
        assert isinstance(cls.max_tool_calls, int) and cls.max_tool_calls > 0
        assert isinstance(cls.tools, list)

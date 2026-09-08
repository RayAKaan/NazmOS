"""Temporal workflow determinism (structural, DB-free).

The workflows in ``app.orchestration.temporal.workflows`` run on the real
Temporal substrate, where event history must replay identically. This test
audits the workflow source with AST so that non-determinism (clocks, UUIDs,
randomness, wall-time, blocking I/O, network) can never silently enter a
workflow body — the only legal side effects are ``workflow.execute_activity``
calls resolved by ``_act``, executed last-in-history by the server.

Scope is deliberately the workflow module (plus its sandbox-scope helper
``policies``): activity modules are unsandboxed worker code and legitimately
use clocks/uuid/DB — they are the server-side effect carriers, not the
orchestration skeleton.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.orchestration.temporal import policies
from app.orchestration.temporal.workflows import WORKFLOWS

_MODULE_ROOT = Path(__file__).resolve().parents[1]

SCANNED_MODULES = [
    "app/orchestration/temporal/workflows.py",
    "app/orchestration/temporal/policies.py",
]

# Feature names (dotted-parts tokens) that break determinism or hide I/O.
# Matching is by exact dotted parts: a two-part token must be a *suffix* of the
# call's dotted path, so ``time.time`` matches ``client().time.time`` but never
# the benign ``datetime.timedelta``. Single-part tokens match any part.
FORBIDDEN_CALLS = [
    "utcnow",
    "datetime.now",
    "datetime.utcnow",
    "datetime.today",
    "date.today",
    "time.time",
    "time.time_ns",
    "time.monotonic",
    "time.sleep",
    "asyncio.sleep",
    "threading.sleep",
    "uuid4",
    "uuid1",
    "uuid3",
    "uuid5",
    "uuid.uuid4",
    "uuid.uuid1",
    "uuid.uuid3",
    "uuid.uuid5",
    "random",
    "secrets",
    "os.urandom",
    "open",
    "read_text",
    "write_text",
    "os.environ",
    "os.getenv",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "subprocess",
    "os.system",
    "os.popen",
]


def _is_banned(name: str) -> bool:
    parts = name.split(".")
    for token in FORBIDDEN_CALLS:
        token_parts = token.split(".")
        if len(token_parts) == 1:
            if token in parts:
                return True
        elif parts[-len(token_parts):] == token_parts:
            return True
    return False

# Workflow bodies may only produce side effects via this starter (which wraps
# workflow.execute_activity). Any other call at function-body depth is suspect.
ALLOWED_ACTIVITY_STARTERS = {"_act", "workflow.execute_activity"}

# Benign deterministic calls allowed inside a workflow run body: pure-python
# helpers, dict accessors, and the temporal API surface itself.
ALLOWED_CALL_PREFIXES = {"_act", "workflow.", "_meta", "activity_retry_policy"}
ALLOWED_CALL_SUFFIXES = {".get", ".items", ".keys", ".values", ".pop"}
ALLOWED_BUILTINS = {
    "dict", "str", "bool", "int", "list", "tuple", "len", "sorted", "min",
    "max", "getattr", "setattr", "isinstance", "repr", "format", "enumerate",
    "zip", "range", "round", "sum", "any", "all", "set", "frozenset",
}


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


class _DeterminismVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted(node.func)
        if name and _is_banned(name):
            self.hits.append(f"{name}(...)")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.split(".")[0] in ("random", "secrets", "socket", "subprocess"):
                self.hits.append(f"import {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            root = node.module.split(".")[0]
            if root in ("random", "secrets", "socket", "subprocess", "os"):
                self.hits.append(f"from {node.module} import ...")
        self.generic_visit(node)


@pytest.mark.parametrize("relpath", SCANNED_MODULES)
def test_workflow_module_has_no_nondeterministic_calls(relpath: str):
    source = _MODULE_ROOT.joinpath(relpath).read_text(encoding="utf-8")
    tree = ast.parse(source)
    visitor = _DeterminismVisitor()
    visitor.visit(tree)
    assert not visitor.hits, (
        f"{relpath} contains non-deterministic or hidden-I/O constructs:\n"
        + "\n".join(f"  {h}" for h in visitor.hits)
        + "\nWorkflows must be replay-safe: no clocks, UUIDs, randomness, "
        "network, or blocking I/O. Delegate all side effects to activities."
    )


def test_banned_surface_is_actually_capable_of_failing():
    """Sanity: the AST scanner must catch the constructs it bans."""
    visitor = _DeterminismVisitor()
    visitor.visit(ast.parse("import time\ndef f():\n    return time.time()\n"))
    visitor.visit(ast.parse("from datetime import datetime\nnow = datetime.utcnow()\n"))
    assert visitor.hits


def test_every_workflow_worker_function_starts_only_allowed_activity_calls():
    """Workflow run bodies must orchestrate solely through _act/execute_activity."""
    source = _MODULE_ROOT.joinpath(SCANNED_MODULES[0]).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
            "run",
            "_act",
            "_meta",
        ):
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                name = _dotted(call.func)
                if not name:
                    continue
                if name in ALLOWED_BUILTINS or name in ALLOWED_ACTIVITY_STARTERS:
                    continue
                if any(name.startswith(p) for p in ALLOWED_CALL_PREFIXES):
                    continue
                if any(name.endswith(s) for s in ALLOWED_CALL_SUFFIXES):
                    continue
                raise AssertionError(
                    f"workflow.{node.name} uses {name}() at line {call.lineno}; "
                    "side effects must be delegated to activities."
                )


def test_registered_workflows_match_runtime_table():
    assert sorted(WORKFLOWS) == ["agent_approval", "manual_action", "simulated"]
    assert callable(policies.activity_retry_policy)
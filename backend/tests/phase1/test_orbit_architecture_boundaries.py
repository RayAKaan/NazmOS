"""Architecture boundary guards (spec §54, §56, §57, §58).

These tests fail the build if the boundaries are crossed. They inspect **actual
import structure** and module contents rather than environment variables, because a
missing ``GROQ_API_KEY`` says nothing about whether Orbit can call an LLM.

Two boundaries are enforced:

1. **Phase 1 Orbit is LLM-free.** Orbit may be imported by code that talks to
   models; it must never import a model provider itself. The future arrangement is
   Intelligence/Loop -> LLMGateway -> OpenRouterAdapter, and that is where model
   calls belong.

2. **JEV is advisory, never authority.** It may classify, score and review. It may
   not approve, execute, authorize, or write canonical truth. This is enforced both
   by inspecting the JEV boundary modules and by checking that no JEV surface exists
   whose method name implies those powers.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
ORBIT = BACKEND / "app" / "services" / "orbit"

#: Modules that reach a language model. Orbit must not import any of them, directly
#: or transitively.
LLM_MODULES = {
    "ai_gateway",
    "llm_orchestrator",
    "llm_rate_limiter",
    "openrouter_adapter",
    "openrouter",
}

#: Provider names that must never appear as an import in Orbit.
LLM_PROVIDER_ROOTS = {
    "groq", "google", "openai", "anthropic", "openrouter",
    "litellm", "cohere", "mistralai", "ollama",
}


def _module_imports(path: Path) -> set[str]:
    """Top-level module names imported by a file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
                if alias.name.startswith("app."):
                    parts = alias.name.split(".")
                    if "services" in parts:
                        idx = parts.index("services")
                        if len(parts) > idx + 1:
                            names.add(parts[idx + 1])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import
                continue
            if node.module:
                names.add(node.module.split(".")[0])
                parts = node.module.split(".")
                if "services" in parts:
                    idx = parts.index("services")
                    if len(parts) > idx + 1:
                        names.add(parts[idx + 1])
    return names


def _orbit_modules() -> list[Path]:
    return sorted(ORBIT.rglob("*.py"))


class TestOrbitIsLlmFree:
    def test_orbit_exists(self):
        assert ORBIT.exists()
        assert _orbit_modules(), "no Orbit modules found to check"

    def test_orbit_imports_no_llm_module(self):
        """Direct imports of an LLM gateway from Orbit fail the build."""
        offenders: list[str] = []
        for path in _orbit_modules():
            for name in _module_imports(path) & LLM_MODULES:
                offenders.append(f"{path.name} imports {name}")
        assert not offenders, (
            "Phase 1 Orbit must not import an LLM module: " + "; ".join(offenders)
        )

    def test_orbit_imports_no_llm_provider_package(self):
        offenders: list[str] = []
        for path in _orbit_modules():
            for name in _module_imports(path) & LLM_PROVIDER_ROOTS:
                offenders.append(f"{path.name} imports {name}")
        assert not offenders, (
            "Phase 1 Orbit must not import an LLM provider: " + "; ".join(offenders)
        )

    def test_orbit_is_transitively_llm_free(self):
        """No Orbit module may import an Orbit module that reaches a model.

        Followed within the Orbit package only. Crossing the package boundary is
        already covered by the direct-import test above, because anything Orbit
        imports from outside ``app.services.orbit`` is inspected by name.
        """
        reachable: dict[Path, set[str]] = {p: _module_imports(p) for p in _orbit_modules()}
        by_stem: dict[str, list[Path]] = {}
        for path in _orbit_modules():
            by_stem.setdefault(path.stem, []).append(path)

        def reaches_llm(path: Path, seen: frozenset[Path]) -> bool:
            if path in seen:
                return False
            seen = seen | {path}
            imports = reachable.get(path, set())
            if imports & (LLM_MODULES | LLM_PROVIDER_ROOTS):
                return True
            return any(
                reaches_llm(other, seen)
                for name in imports
                for other in by_stem.get(name, [])
                if other != path
            )

        offenders = [p.name for p in _orbit_modules() if reaches_llm(p, frozenset())]
        assert not offenders, (
            "these Orbit modules transitively reach an LLM: " + ", ".join(offenders)
        )

    def test_orbit_does_not_read_llm_credentials(self):
        """Orbit must not read provider keys even if a provider were imported."""
        needles = ("GROQ_API_KEY", "GOOGLE_AI_API_KEY", "OPENAI_API_KEY",
                   "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY")
        offenders: list[str] = []
        for path in _orbit_modules():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in needles:
                if needle in text:
                    offenders.append(f"{path.name} references {needle}")
        assert not offenders, (
            "Orbit must not read LLM credentials: " + "; ".join(offenders)
        )


class TestJevIsAdvisoryOnly:
    """JEV may judge. It may not act."""

    #: Method names that would imply authority JEV must never hold.
    FORBIDDEN_METHOD_NAMES = {
        "approve", "approve_action", "authorize", "authorize_action",
        "execute", "execute_action", "dispatch", "commit_change",
        "write_canonical_state", "mutate_inventory", "apply_balance",
        "grant_approval", "sign_off",
    }

    def _jev_boundary_files(self) -> list[Path]:
        candidates = [
            BACKEND / "app" / "services" / "ai_providers" / "jev.py",
            BACKEND / "app" / "services" / "ai_gateway.py",
            BACKEND / "app" / "services" / "canonical_controller.py",
            BACKEND / "app" / "security" / "capsule.py",
            BACKEND / "app" / "security" / "ai_policy.py",
        ]
        extra = sorted((BACKEND / "app" / "services" / "orbit" / "jev").rglob("*.py")) \
            if (BACKEND / "app" / "services" / "orbit" / "jev").exists() else []
        return [p for p in candidates + extra if p.exists()]

    def test_jev_boundary_files_exist(self):
        assert self._jev_boundary_files(), "no JEV boundary modules found to check"

    def test_jev_exposes_no_authority_methods(self):
        offenders: list[str] = []
        for path in self._jev_boundary_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.lower() in self.FORBIDDEN_METHOD_NAMES:
                        offenders.append(f"{path.name}.{node.name}")
        assert not offenders, (
            "JEV must not expose authority-bearing methods: " + ", ".join(offenders)
        )

    def test_canonical_controller_is_the_decision_boundary(self):
        """The deterministic-first choke point must exist and stay deterministic-first."""
        controller = BACKEND / "app" / "services" / "canonical_controller.py"
        assert controller.exists(), (
            "canonical_controller is the validated JEV boundary and must exist"
        )
        source = controller.read_text(encoding="utf-8")
        assert "def canonical_decision" in source, (
            "canonical_decision() is the required bounded-judgment entry point"
        )

    def test_jev_service_does_not_import_execution(self):
        """A JEV module must not reach the orchestration/execution layer."""
        execution_modules = {"orchestration", "execution", "temporal"}
        jev_dir = BACKEND / "app" / "services" / "orbit" / "jev"
        offenders: list[str] = []
        if jev_dir.exists():
            for path in jev_dir.rglob("*.py"):
                for name in _module_imports(path) & execution_modules:
                    offenders.append(f"{path.name} imports {name}")
        assert not offenders, (
            "JEV must not import the execution layer: " + "; ".join(offenders)
        )


class TestPhaseOneDoesNotImplementLaterPhases:
    """Phase 1 must not smuggle in Intelligence or Loop features."""

    def test_orbit_emits_no_recommendations(self):
        """Phase 1 produces state, not advice.

        ``BusinessContext.open_recommendations`` exists in the contract for the
        Intelligence phase and must stay empty here.
        """
        offenders: list[str] = []
        for path in _orbit_modules():
            source = path.read_text(encoding="utf-8", errors="ignore")
            for needle in ("open_recommendations=[", "open_recommendations=tuple("):
                if needle in source:
                    offenders.append(path.name)
        assert not offenders, (
            "Phase 1 must not populate recommendations: " + ", ".join(offenders)
        )

    def test_no_phase2_or_phase3_modules_in_orbit(self):
        forbidden = {
            "copilot", "root_cause", "forecast_intelligence", "scenario",
            "approval_workflow", "verified_learning", "autonomous_action",
        }
        stems = {p.stem.lower() for p in _orbit_modules()}
        offenders = stems & forbidden
        assert not offenders, (
            f"Phase 2/3 modules must not live in Orbit: {sorted(offenders)}"
        )

class TestSingleTruthPipeline:
    """Canonical Orbit owns ingestion truth; ETLPipeline is compatibility projection only."""

    def test_no_production_module_instantiates_etl_truth_pipeline(self):
        offenders: list[str] = []
        app_root = BACKEND / "app"
        for path in sorted(app_root.rglob("*.py")):
            if path == BACKEND / "app" / "services" / "etl_pipeline.py":
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            if "from app.services.etl_pipeline import ETLPipeline" in source:
                offenders.append(f"{path}: imports ETLPipeline")
            if "ETLPipeline(" in source:
                offenders.append(f"{path}: instantiates ETLPipeline")
        assert not offenders, (
            "ETLPipeline is a compatibility projector, never a production "
            "truth producer: " + "; ".join(offenders)
        )

    def test_business_snapshot_builder_is_only_a_canonical_compatibility_adapter(self):
        builder = BACKEND / "app" / "services" / "business_snapshot_builder.py"
        assert builder.exists()
        source = builder.read_text(encoding="utf-8", errors="ignore")
        assert "CanonicalOrbitIngestionPipeline" in source
        assert "Compatibility wrapper" in source

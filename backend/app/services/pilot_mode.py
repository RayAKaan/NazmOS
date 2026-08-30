"""Phase 5 controlled pilot-mode policy."""
from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class PilotPolicy:
    enabled: bool=True
    require_approval: bool=True
    allow_real_execution: bool=False
    ai_enabled: bool=True
    ai_max_calls_per_audit: int=10

    @classmethod
    def from_env(cls):
        return cls(enabled=os.getenv("NAZMOS_PILOT_MODE","true").lower() in {"1","true","yes"},
                   require_approval=os.getenv("NAZMOS_PILOT_REQUIRE_APPROVAL","true").lower() in {"1","true","yes"},
                   allow_real_execution=os.getenv("NAZMOS_PILOT_ALLOW_REAL_EXECUTION","false").lower() in {"1","true","yes"},
                   ai_enabled=os.getenv("NAZMOS_PILOT_AI_ENABLED","true").lower() in {"1","true","yes"},
                   ai_max_calls_per_audit=int(os.getenv("NAZMOS_PILOT_AI_MAX_CALLS","10")))

    def disposition(self, *, execution_capable: bool) -> str:
        if not execution_capable: return "MANUAL"
        if self.require_approval: return "APPROVAL_REQUIRED"
        return "AUTO" if self.allow_real_execution else "APPROVAL_REQUIRED"

POLICY=PilotPolicy.from_env()

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.security.capsule import ReasoningCapsule
from app.security.privacy_firewall import build_bounded_choice_capsule
from app.services.ai_gateway import systemone_reason


@dataclass(frozen=True)
class JevCallRecord:
    capability: str
    purpose: str
    model: str | None
    request_hash: str
    choice: str
    confidence: float
    latency_ms: float
    status: str
    fallback_used: bool
    capsule_hash: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class JevDecision:
    choice: str
    confidence: float
    origin: str
    selected_id: str | None = None
    alternatives: tuple[str, ...] = ()
    challenge: bool = False
    capsule_hash: str = ''
    latency_ms: float = 0.0


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='nazmos-jev') as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


class JevService:
    def __init__(self, *, client: Any | None = None) -> None:
        self.client = client
        self.calls: list[JevCallRecord] = []

    def decide_choice(
        self,
        *,
        capability: str,
        purpose: str,
        question: str,
        candidates: Sequence[str],
        fallback: str,
        context_bands: Mapping[str, Any] | None = None,
    ) -> JevDecision:
        choices = tuple(dict.fromkeys(str(c).strip().upper() for c in candidates if str(c).strip()))
        fallback = str(fallback).strip().upper()
        if not choices:
            return JevDecision(choice=fallback, confidence=0.0, origin='deterministic')

        capsule: ReasoningCapsule = build_bounded_choice_capsule(
            candidates=list(choices),
            context_bands=context_bands,
            capability=capability,
            purpose=purpose,
        )
        result = _run_async(
            systemone_reason(
                {},
                capability=capability,
                purpose=purpose,
                deterministic_decision=fallback,
                question=question,
                client=self.client,
                shadow=False,
                allowed_suggestions=frozenset(choices),
                allowed_decisions=frozenset((*choices, fallback)),
                capsule=capsule,
            )
        )
        suggested = result.get('alternative_decision')
        suggested = str(suggested).upper() if suggested else None
        accepted = suggested if suggested in choices else None
        choice = accepted or fallback
        source = str(result.get('source') or 'fallback')
        model = result.get('model')
        confidence = float(result.get('confidence') or 0.0)
        latency = float(result.get('latency_ms') or 0.0)

        self.calls.append(
            JevCallRecord(
                capability=capability,
                purpose=purpose,
                model=model,
                request_hash=capsule.capsule_hash,
                choice=choice,
                confidence=confidence,
                latency_ms=latency,
                status='ok' if source == 'jev' else 'fallback',
                fallback_used=source != 'jev',
                capsule_hash=capsule.capsule_hash,
            )
        )
        return JevDecision(
            choice=choice,
            confidence=confidence,
            origin='jev' if accepted is not None else 'deterministic',
            alternatives=tuple(c for c in choices if c != choice),
            challenge=bool(result.get('challenge')),
            capsule_hash=capsule.capsule_hash,
            latency_ms=latency,
        )

    def decide_artifact_type(self, *, candidates: Sequence[str], filename: str = '') -> JevDecision:
        return self.decide_choice(
            capability='orbit.artifact.classify',
            purpose='classify an ambiguous business artifact from bounded evidence',
            question='Choose the best supported artifact type from the bounded candidates.',
            candidates=candidates,
            fallback='UNKNOWN',
            context_bands={'filename_shape': filename[-80:]},
        )

    def decide_column_role(self, *, candidates: Sequence[str], header: str = '') -> JevDecision:
        return self.decide_choice(
            capability='orbit.column.classify',
            purpose='classify an ambiguous business column from bounded evidence',
            question='Choose the best supported semantic role from the bounded candidates.',
            candidates=candidates,
            fallback='UNKNOWN',
            context_bands={'header_shape': header[:80]},
        )

    def decide_row_role(self, *, candidates: Sequence[str], row_shape: str = '') -> JevDecision:
        return self.decide_choice(
            capability='orbit.row.classify',
            purpose='classify an ambiguous spreadsheet row from bounded evidence',
            question='Choose the best supported row role from the bounded candidates.',
            candidates=candidates,
            fallback='UNKNOWN',
            context_bands={'row_shape': row_shape[:80]},
        )

    def decide_entity(
        self,
        *,
        kind: str,
        observed_name: str,
        candidates: Sequence[Mapping[str, Any]],
        identifiers_present: Sequence[str] = (),
    ) -> JevDecision:
        ids = tuple(str(c.get('entity_id')) for c in candidates if c.get('entity_id'))
        choice = self.decide_choice(
            capability='orbit.entity.resolve',
            purpose='resolve an ambiguous business entity from bounded candidates',
            question='Choose a candidate entity, DIFFERENT_ENTITY, or AMBIGUOUS.',
            candidates=(*ids, 'DIFFERENT_ENTITY', 'AMBIGUOUS'),
            fallback='AMBIGUOUS',
            context_bands={
                'entity_kind': kind,
                'observed_name_shape': observed_name[:80],
                'identifier_types': list(identifiers_present)[:8],
                'candidate_count': len(ids),
            },
        )
        if choice.choice in ids:
            return JevDecision('same_entity', choice.confidence, choice.origin,
                               selected_id=choice.choice,
                               alternatives=choice.alternatives,
                               challenge=choice.challenge,
                               capsule_hash=choice.capsule_hash,
                               latency_ms=choice.latency_ms)
        if choice.choice == 'DIFFERENT_ENTITY':
            return JevDecision('different_entity', choice.confidence, choice.origin,
                               alternatives=choice.alternatives,
                               challenge=choice.challenge,
                               capsule_hash=choice.capsule_hash,
                               latency_ms=choice.latency_ms)
        return JevDecision('ambiguous', choice.confidence, choice.origin,
                           alternatives=choice.alternatives,
                           challenge=choice.challenge,
                           capsule_hash=choice.capsule_hash,
                           latency_ms=choice.latency_ms)

    def interpret_date(self, *, candidates: Sequence[str], raw: str = '') -> JevDecision:
        return self.decide_choice(
            capability='orbit.time.interpret',
            purpose='interpret an ambiguous business date from bounded candidates',
            question='Choose the supported date interpretation from the bounded candidates.',
            candidates=candidates,
            fallback='AMBIGUOUS',
            context_bands={'raw_shape': raw[:40]},
        )

    def classify_conflict(self, *, relationship: str, field: str, value_a: str, value_b: str) -> JevDecision:
        return self.decide_choice(
            capability='orbit.conflict.classify',
            purpose='classify an ambiguous source conflict',
            question='Classify the source relationship without altering either source value.',
            candidates=('DUPLICATE', 'SOURCE_LAG', 'DATA_ENTRY_ERROR', 'TEMPORAL_DIFFERENCE',
                         'LEGITIMATE_VARIATION', 'TRUE_CONFLICT', 'AMBIGUOUS'),
            fallback='AMBIGUOUS',
            context_bands={
                'relationship': relationship,
                'field': field,
                'value_a_type': type(value_a).__name__,
                'value_b_type': type(value_b).__name__,
            },
        )

    def triage_quality(self, *, candidates: Sequence[str], issue: str) -> JevDecision:
        return self.decide_choice(
            capability='orbit.quality.triage',
            purpose='triage an ambiguous data-quality issue',
            question='Choose the best supported data-quality category.',
            candidates=candidates,
            fallback='AMBIGUOUS',
            context_bands={'issue_type': issue[:80]},
        )

    def route_analysis(self, *, candidates: Sequence[str], artifact_kind: str) -> JevDecision:
        return self.decide_choice(
            capability='orbit.analysis.route',
            purpose='route an ambiguous artifact to a deterministic analysis',
            question='Choose the deterministic analyzer best matched to this artifact.',
            candidates=candidates,
            fallback='MANUAL_REVIEW',
            context_bands={'artifact_kind': artifact_kind},
        )


__all__ = ['JevCallRecord', 'JevDecision', 'JevService']

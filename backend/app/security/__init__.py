"""Phase A isolation core: the trusted boundary between merchant data and AI.

The AI (LLM provider or OpenCode brain) is a reasoning layer ABOVE the
deterministic financial engine. It never receives merchant identifiers or exact
financial values. It only receives a signed ReasoningCapsule of derived,
banded signals and constrained candidate decisions. Its output is un-trusted
until it passes the output gate and is revalidated by NazmOS.

Trust zones:
    TRUSTED  : app/services, routers, database (sees BusinessContext,
               ItemEvidence, StructuredContext, exact SAR values)
    BOUNDARY : this package (privacy_firewall, capsule, dlp, output_gate)
    UNTRUSTED: what actually leaves the process toward a third-party LLM or
               the OpenCode CLI. Everything is derived signals; nothing exact.

Invariant enforced by typing: ``reason(capsule: ReasoningCapsule, ...)``.
Raw evidence dicts are not accepted as prompt input on the AI path.
"""
"""AI provider adapters (canonical gateway routes).

The canonical gateway (app/services/ai_gateway.py) is the ONLY sanctioned place
to consult AI providers during a NazmOS decision. Providers here are
NON-AUTHORITATIVE: the deterministic decision always wins; a provider may
enrich reasoning or raise a challenge, but can never override the trusted
decision. See app/services/ai_providers/jev.py.
"""
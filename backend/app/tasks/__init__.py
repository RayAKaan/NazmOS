"""Background-operation bodies (single canonical NazmOS run_* functions).

The run_* functions in this package are the business logic invoked by Temporal
activities (``app.orchestration.temporal.activities``). They contain no
Celery/queue wiring.
"""
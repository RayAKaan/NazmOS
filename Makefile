.PHONY: verify backend-test frontend-test contract runtime-smoke local-up local-down phase1-up phase1-down phase1-migrate phase1-seed phase1-test phase1-reset

verify:
	python scripts/verify_workspace.py

backend-test:
	cd backend && PYTHONPATH=. pytest -q && PYTHONPATH=. python -m compileall -q app tests && PYTHONPATH=. python -m alembic heads

frontend-test:
	cd frontend && npm run lint && npm run build && npm audit --audit-level=moderate --omit=dev

contract:
	cd backend && PYTHONPATH=. pytest tests/test_retail_recovery_contract.py -q

runtime-smoke:
	python scripts/runtime_smoke.py

runtime-e2e:
	python scripts/runtime_e2e_upload_money_audit.py

local-up:
	docker compose -f docker-compose.local.yml up --build

local-down:
	docker compose -f docker-compose.local.yml down

runtime-up:
	docker compose --env-file .env.runtime-test -f docker-compose.local.yml up --build -d
	python scripts/wait_runtime.py

runtime-down:
	docker compose --env-file .env.runtime-test -f docker-compose.local.yml down

runtime-logs:
	docker compose --env-file .env.runtime-test -f docker-compose.local.yml logs --tail=200

runtime-readiness:
	python scripts/runtime_smoke.py

reality-test-v5:
	python scripts/runtime_v5_guard.py


# Phase 1 — Universal Business Reality
phase1-up:
	docker compose up -d postgres redis temporal

phase1-down:
	docker compose down

phase1-migrate:
	cd backend && PYTHONPATH=. python -m alembic upgrade head

phase1-seed:
	cd backend && PYTHONPATH=. python -m pytest tests/phase1/test_phase1_pipeline.py -q

phase1-test:
	cd backend && PYTHONPATH=. pytest -q tests/phase1

phase1-reset:
	docker compose down -v

.PHONY: debatemind-backend frontend worker dev infra-up infra-down infra-build infra-logs start

debatemind-backend:
	uv run uvicorn debatemind.main:app --reload --port 8001

frontend:
	cd ../frontend && npm run dev

# --pool=solo avoids macOS fork SIGSEGVs; prod uses prefork on Linux instead.
worker:
	OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES uv run celery -A debatemind.worker.celery_app worker --loglevel=info --pool=solo

dev:
	make -j3 debatemind-backend frontend worker

# Infra: postgres, cognee-db (pgvector), redis, neo4j
infra-build:
	docker compose -f ../docker-compose.yml build

infra-up:
	docker compose -f ../docker-compose.yml up -d --remove-orphans

infra-down:
	docker compose -f ../docker-compose.yml down --remove-orphans

infra-logs:
	docker compose -f ../docker-compose.yml logs -f

# Start everything: infra first, then backend + frontend + celery in parallel
start:
	make infra-up && make dev

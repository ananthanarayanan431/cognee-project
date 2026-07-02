.PHONY: debatemind-backend frontend celery worker dev infra-up infra-down infra-build infra-logs start

debatemind-backend:
	uv run uvicorn debatemind.main:app --reload --port 8001

frontend:
	cd ../frontend && npm run dev

celery worker:
	uv run celery -A debatemind.worker.celery_app worker --loglevel=info --concurrency=2

dev:
	make -j3 debatemind-backend frontend celery

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

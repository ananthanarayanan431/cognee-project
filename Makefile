.PHONY: debatemind-backend frontend celery dev infra-up infra-down infra-build infra-logs start

debatemind-backend:
	cd debatemind-backend && uv run uvicorn debatemind.main:app --reload --port 8001

frontend:
	cd frontend && npm run dev

celery:
	cd debatemind-backend && uv run celery -A debatemind.worker.celery_app worker --loglevel=info --concurrency=2

dev:
	make -j3 debatemind-backend frontend celery

# Infra: postgres, cognee-db (pgvector+kuzu), minio, redis
infra-build:
	docker compose build

infra-up:
	docker compose up -d --remove-orphans

infra-down:
	docker compose down --remove-orphans

infra-logs:
	docker compose logs -f

# Start everything: infra first, then backend + frontend + celery in parallel
start:
	make infra-up && make dev

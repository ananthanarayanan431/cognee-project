.PHONY: debatemind-backend frontend dev infra-up infra-down infra-build infra-logs start

debatemind-backend:
	cd debatemind-backend && uv run uvicorn debatemind.main:app --reload --port 8001

frontend:
	cd frontend && npm run dev

dev:
	make -j2 debatemind-backend frontend

# Infra: postgres, cognee-db (pgvector+kuzu), minio
infra-build:
	docker compose build

infra-up:
	docker compose up -d --remove-orphans

infra-down:
	docker compose down --remove-orphans

infra-logs:
	docker compose logs -f

# Start everything: infra first, then backend + frontend in parallel
start:
	make infra-up && make dev

.PHONY: debatemind-backend frontend dev infra-up infra-down infra-build

debatemind-backend:
	cd debatemind-backend && uv run uvicorn debatemind.main:app --reload --port 8001

frontend:
	cd frontend && npm run dev

dev:
	make -j2 debatemind-backend frontend

infra-build:
	docker compose build

infra-up:
	docker compose up -d --remove-orphans

infra-down:
	docker compose down --remove-orphans

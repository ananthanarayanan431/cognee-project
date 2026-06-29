.PHONY: debatemind-backend frontend dev docker-up docker-down docker-build

debatemind-backend:
	cd debatemind-backend && uv run uvicorn debatemind.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	make -j2 debatemind-backend frontend

docker-build:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down

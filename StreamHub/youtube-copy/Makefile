.PHONY: up down logs test migrate seed
up:
	./deploy.sh

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

test:
	pytest -q

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m app.seed

PYTHON = .venv/bin/python

.PHONY: setup dev backend frontend sync sync-force status db-migrate db-reset test

setup:
	python3.13 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt
	cd frontend && npm install
	@[ -f .env ] || cp .env.example .env
	@make db-migrate
	@echo "Setup complete. Fill in .env keys as you sign up (README → Getting started)."

dev:
	@echo "Backend http://127.0.0.1:8001  ·  Frontend http://localhost:5174"
	@make backend & make frontend & wait

backend:
	cd backend && ../$(PYTHON) -m uvicorn main:app --reload --host 127.0.0.1 --port 8001

frontend:
	cd frontend && npm run dev

sync:
	@curl -s -X POST http://127.0.0.1:8001/api/sync | $(PYTHON) -m json.tool

sync-force:
	@curl -s -X POST "http://127.0.0.1:8001/api/sync?force=true" | $(PYTHON) -m json.tool

status:
	@curl -s http://127.0.0.1:8001/api/sync/status | $(PYTHON) -m json.tool

db-migrate:
	@cd backend && ../$(PYTHON) -c "from database import run_migrations; run_migrations()"

db-reset:
	@echo "WARNING: This deletes all local property data, including parcel history snapshots that cannot be re-downloaded."
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@rm -f data/property.db data/property.db-wal data/property.db-shm
	@make db-migrate

test:
	cd backend && ../$(PYTHON) -m pytest ../tests -q

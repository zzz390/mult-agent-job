.PHONY: help dev test lint format migrate revision seed docker-up docker-down clean

# Default target
help:
	@echo "Job Agent OS - Available commands:"
	@echo "  make dev        - Start development environment"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linters (ruff + mypy)"
	@echo "  make format     - Format code with ruff"
	@echo "  make migrate    - Run database migrations"
	@echo "  make revision   - Create new migration"
	@echo "  make seed       - Seed database with test data"
	@echo "  make docker-up  - Start Docker containers"
	@echo "  make docker-down- Stop Docker containers"
	@echo "  make clean      - Clean up temporary files"

# Development
dev:
	uvicorn job_agent_os.main:app --reload --host 0.0.0.0 --port 8000

# Testing
test:
	pytest tests/ -v --cov=job_agent_os --cov-report=term-missing

# Linting
lint:
	ruff check src/
	mypy src/

# Formatting
format:
	ruff format src/
	ruff check --fix src/

# Database
migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(msg)"

seed:
	python scripts/seed_data.py

# Docker
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f app

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

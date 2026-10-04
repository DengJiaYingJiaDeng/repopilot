.PHONY: install check test run

install:
	python -m pip install -e ".[dev]"

check:
	ruff check .
	ruff format --check .
	mypy
	pytest

test:
	pytest

run:
	uvicorn repopilot.api.app:app --host 127.0.0.1 --port 8000

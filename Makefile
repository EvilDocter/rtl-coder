.PHONY: test lint format clean help

help:
	@echo "Available commands:"
	@echo "  make test    - Run automated test suite (pytest)"
	@echo "  make lint    - Lint Python codebase using ruff"
	@echo "  make format  - Auto-format code using ruff"
	@echo "  make clean   - Remove caches and transient files"

test:
	python -m pytest tests/

lint:
	python -m ruff check .

format:
	python -m ruff format .

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('.pytest_cache')]"

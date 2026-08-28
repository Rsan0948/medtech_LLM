# MedTech LLM - Common tasks
.PHONY: help install install-all lint format test data train evaluate demo clean

# Prefer the project venv when it exists so targets work without activation.
PYTHON := $(shell [ -f .venv/bin/python ] && echo .venv/bin/python || echo python)
SRC_DIR := src
TEST_DIR := tests

help:
	@echo "Available targets:"
	@echo "  install      Install core dependencies"
	@echo "  install-all  Install core + MLX + dev + demo dependencies"
	@echo "  lint         Run ruff and mypy checks"
	@echo "  format       Run black and ruff formatting"
	@echo "  test         Run pytest with coverage"
	@echo "  data         Run pipeline stages 1-5 (ingest → train/valid splits)"
	@echo "  train        Run MLX LoRA fine-tuning"
	@echo "  evaluate     Run TBE evaluation"
	@echo "  demo         Launch Streamlit demo"
	@echo "  clean        Remove build artifacts, caches, and generated data"

install:
	$(PYTHON) -m pip install -e ".[dev]"

install-all:
	$(PYTHON) -m pip install -e ".[all]"

lint:
	$(PYTHON) -m ruff check $(SRC_DIR) $(TEST_DIR)
	$(PYTHON) -m mypy $(SRC_DIR)

format:
	$(PYTHON) -m black $(SRC_DIR) $(TEST_DIR)
	$(PYTHON) -m ruff check --fix $(SRC_DIR) $(TEST_DIR)

test:
	$(PYTHON) -m pytest $(TEST_DIR)

data:
	$(PYTHON) run_pipeline.py --all

train:
	bash $(SRC_DIR)/modeling/train_mlx.sh

evaluate:
	$(PYTHON) run_pipeline.py --stage evaluate

demo:
	$(PYTHON) -m streamlit run demo/streamlit_app.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ *.egg-info/

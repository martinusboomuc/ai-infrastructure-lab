.PHONY: setup lint test check-data data features train serve flow drift retrain-on-drift

setup:
	uv sync
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest

check-data:
	@test -n "$(BANKML_DATA_ROOT)" || { echo "BANKML_DATA_ROOT is not set. Copy .env.example to .env."; exit 1; }
	@test -d "$(BANKML_DATA_ROOT)" || { echo "Data root not found at $(BANKML_DATA_ROOT). Is the drive mounted?"; exit 1; }

data: check-data
	uv run dvc pull

features: check-data
	uv run dvc repro features_$(DOMAIN)

train: check-data
	uv run python -m bankml.training.pipeline --domain $(DOMAIN)

serve:
	uv run uvicorn bankml.serving.app:app --host 0.0.0.0 --port 8000

flow: check-data
	uv run python -m bankml.orchestration.flow

drift: check-data
	uv run python -m bankml.monitoring.drift --domain $(DOMAIN)

retrain-on-drift: check-data
	uv run python -m bankml.orchestration.flow --flow drift-check-and-retrain --domain $(DOMAIN)

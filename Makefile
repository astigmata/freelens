.DEFAULT_GOAL := help
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

KIND_CLUSTER := freelens-test
KIND_CONTEXT := kind-$(KIND_CLUSTER)

.PHONY: help venv install dev run test clean kind-up kind-seed kind-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

$(PYTHON): ## Create the virtual environment
	python3 -m venv $(VENV)

venv: $(PYTHON) ## Create the virtual environment

install: venv ## Install runtime dependencies
	$(PIP) install -r requirements.txt

dev: install ## Install runtime + development dependencies
	$(PIP) install pytest

run: ## Run the app locally — loopback only, NO AUTH (dev)
	FREELENS_HOST=127.0.0.1 FREELENS_AUTH_MODE=disabled $(PYTHON) app.py

test: ## Run the test suite
	$(PYTHON) -m pytest tests/ -q

clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache *.egg-info

kind-up: ## Create a local KinD test cluster and seed sample workloads
	@if kind get clusters 2>/dev/null | grep -qx $(KIND_CLUSTER); then \
		echo "KinD cluster '$(KIND_CLUSTER)' already exists"; \
	else \
		kind create cluster --name $(KIND_CLUSTER); \
	fi
	@$(MAKE) kind-seed
	@echo "Cluster ready. Active context: $(KIND_CONTEXT)"

kind-seed: ## Deploy sample workloads to the KinD cluster
	kubectl --context $(KIND_CONTEXT) apply -f deploy/sample.yaml
	kubectl --context $(KIND_CONTEXT) -n demo rollout status deploy/nginx

kind-down: ## Delete the local KinD test cluster
	kind delete cluster --name $(KIND_CLUSTER)

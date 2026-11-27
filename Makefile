.PHONY: help install-all install-python install-rust install-ts install-hardhat \
       build-core build-core-debug tui serve-web serve test test-py test-rust test-ts \
       test-sol compile-sol deploy register-keys clean

SHELL := /bin/bash

help: ## Show help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------ install
install-all: install-python install-rust install-ts install-hardhat ## Install all dependencies

install-python: ## Install Python deps (venv + pip)
	python3 -m venv .venv
	.venv/bin/pip install -e ./py

install-rust: ## Build Rust core (PyO3)
	cd core && maturin develop --features extension-module

install-ts: ## Install TypeScript deps
	npm install

install-hardhat: ## Install Solidity/Hardhat deps
	cd contracts && npm install

build-core: ## Build release Rust core
	cd core && maturin build --release --features extension-module

build-core-debug: ## Build debug Rust core
	cd core && maturin build --features extension-module

# ------------------------------------------------------------------ run
tui: ## Run local Textual TUI
	@cd py && PYTHONPATH=. python -m safe_prompt.cli tui

serve: ## Run FastAPI gateway + TUI server (local)
	@cd py && uvicorn safe_prompt.gateway.app:app --host 127.0.0.1 --port 8787

serve-web: ## Serve TUI over web via textual-web (for judges/remote)
	@cd py && PYTHONPATH=. python -m safe_prompt.cli serve-web --host 0.0.0.0 --port 8080

# ------------------------------------------------------------------ test
test: test-py test-rust test-ts test-sol ## Run all tests

test-py: ## Run Python tests
	@cd py && PYTHONPATH=. pytest tests/ -q

test-rust: ## Run Rust unit tests
	cd core && cargo test

test-ts: ## Run TypeScript (Hardhat) tests
	cd contracts && npx hardhat test

test-sol: ## Compile + test Solidity contracts
	cd contracts && npx hardhat compile && npx hardhat test

# ------------------------------------------------------------------ keys
register-keys: ## Register PQC keys on-chain for current address
	@cd ts && npx tsx scripts/register-keys.ts

compile-sol: ## Compile Solidity contracts
	cd contracts && npx hardhat compile

deploy: ## Deploy anchor contract to Diana testnet
	cd contracts && npx hardhat run scripts/deploy.ts --network diana

clean: ## Clean build artifacts
	rm -rf core/target
	rm -rf py/.venv

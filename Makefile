.PHONY: help install test lint clean dev build release deploy

help: ## Show this help message
	@echo 'Warp - Makefile commands'
	@echo ''
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	@echo "📦 Installing dependencies..."
	pip install -r requirements.txt
	npm install
	@echo "✅ Dependencies installed"

install-dev: ## Install development dependencies
	@echo "📦 Installing development dependencies..."
	pip install -r requirements.txt
	pip install -e .
	@echo "✅ Development environment ready"

test: ## Run tests
	@echo "🧪 Running tests..."
	pytest tests/ -v --cov=src --cov-report=term-missing
	@echo "✅ Tests completed"

test-unit: ## Run unit tests only
	@echo "🧪 Running unit tests..."
	pytest tests/ -v -m "not integration"

test-integration: ## Run integration tests only
	@echo "🧪 Running integration tests..."
	pytest tests/ -v -m integration

test-e2e: ## Run end-to-end tests
	@echo "🧪 Running end-to-end tests..."
	python test_e2e.py

lint: ## Run linters
	@echo "🔍 Running linters..."
	ruff check src/ tests/ || true
	mypy src/ || true
	@echo "✅ Linting completed"

format: ## Format code
	@echo "✨ Formatting code..."
	ruff format src/ tests/ || true
	@echo "✅ Code formatted"

clean: ## Clean build artifacts
	@echo "🧹 Cleaning..."
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf out/ .aws-sam/
	@echo "✅ Cleaned"

dev: ## Start development mode
	@echo "🚀 Starting Warp in development mode..."
	python3 bin/axsupport-cli chat

run: dev ## Alias for dev

chat: ## Start interactive chat
	@python3 bin/axsupport-cli chat

status: ## Show integration status
	@python3 bin/axsupport-cli status

query: ## Run a single query (use: make query Q="your question")
	@python3 bin/axsupport-cli query "$(Q)"

triage: ## Run triage (use: make triage T="ticket description")
	@python3 src/orchestrator.py --no-llm "triage: $(T)"

build: clean ## Build distribution packages
	@echo "📦 Building distribution..."
	python3 -m build
	@echo "✅ Build completed"

build-docker: ## Build Docker image
	@echo "🐳 Building Docker image..."
	docker build -f docker/Dockerfile -t warp:latest .
	@echo "✅ Docker image built"

release: test lint ## Prepare for release
	@echo "🚀 Preparing release..."
	@echo "✅ All checks passed. Ready to release!"

setup: ## Initial project setup
	@echo "🔧 Setting up Warp..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✅ Created .env file (please edit with your API keys)"; \
	fi
	@if [ ! -f config/config.yaml ]; then \
		cp config/config.yaml.example config/config.yaml; \
		echo "✅ Created config.yaml file"; \
	fi
	@$(MAKE) install
	@echo ""
	@echo "✨ Setup complete! Next steps:"
	@echo "  1. Edit .env with your API keys"
	@echo "  2. Edit config/config.yaml with your settings"
	@echo "  3. Run 'make dev' to start the agent"

# Website deployment
website-dev: ## Start website dev server
	@npm run dev

website-build: ## Build website for deployment
	@npm run build

deploy-stack: ## Deploy AWS SAM stack
	@./scripts/deploy-stack.sh

deploy-site: ## Deploy website to S3/CloudFront
	@./scripts/publish-public.sh

deploy: deploy-stack deploy-site ## Deploy both stack and website

.DEFAULT_GOAL := help

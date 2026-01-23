.PHONY: doctor api gateway up down smoke status help clean

# Default target - show help
.DEFAULT_GOAL := help

# State directory for PID files
STATE_DIR := /tmp/milton-state

help: ## Show this help message
	@echo "Milton Operations Harness"
	@echo "========================="
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""

doctor: ## Run Milton connectivity diagnostics
	@python -m scripts.milton_doctor

api: ## Start Milton API server in background
	@echo "Starting Milton API server..."
	@mkdir -p $(STATE_DIR)
	@PYTHONUNBUFFERED=1 nohup python scripts/start_api_server.py \
		> /tmp/milton_api.log 2>&1 & echo $$! > $(STATE_DIR)/api.pid
	@sleep 2
	@if ps -p `cat $(STATE_DIR)/api.pid` > /dev/null 2>&1; then \
		echo "API server started (PID: `cat $(STATE_DIR)/api.pid`)"; \
		echo "Logs: /tmp/milton_api.log"; \
	else \
		echo "ERROR: API server failed to start. Check /tmp/milton_api.log"; \
		exit 1; \
	fi

gateway: ## Start Milton Gateway in background
	@echo "Starting Milton Gateway..."
	@mkdir -p $(STATE_DIR)
	@PYTHONUNBUFFERED=1 nohup python scripts/start_chat_gateway.py \
		> /tmp/milton_gateway.log 2>&1 & echo $$! > $(STATE_DIR)/gateway.pid
	@sleep 2
	@if ps -p `cat $(STATE_DIR)/gateway.pid` > /dev/null 2>&1; then \
		echo "Gateway started (PID: `cat $(STATE_DIR)/gateway.pid`)"; \
		echo "Logs: /tmp/milton_gateway.log"; \
	else \
		echo "ERROR: Gateway failed to start. Check /tmp/milton_gateway.log"; \
		exit 1; \
	fi

up: ## Start API + Gateway services (runs milton_up.sh)
	@./scripts/milton_up.sh

down: ## Stop all background services (runs milton_down.sh)
	@./scripts/milton_down.sh

smoke: ## Run smoke tests against running services
	@./scripts/milton_smoke.sh

status: ## Show running services and health status
	@echo "Milton Service Status"
	@echo "====================="
	@echo ""
	@if [ -f $(STATE_DIR)/api.pid ]; then \
		pid=$$(cat $(STATE_DIR)/api.pid); \
		if ps -p $$pid > /dev/null 2>&1; then \
			echo "✅ API Server (PID $$pid)"; \
			curl -fsS http://localhost:8001/health 2>/dev/null && echo "   Health: OK" || echo "   Health: FAIL"; \
		else \
			echo "❌ API Server (stale PID file)"; \
		fi; \
	else \
		echo "❌ API Server (not running)"; \
	fi
	@echo ""
	@if [ -f $(STATE_DIR)/gateway.pid ]; then \
		pid=$$(cat $(STATE_DIR)/gateway.pid); \
		if ps -p $$pid > /dev/null 2>&1; then \
			echo "✅ Gateway (PID $$pid)"; \
			curl -fsS http://localhost:8081/health 2>/dev/null && echo "   Health: OK" || echo "   Health: FAIL"; \
		else \
			echo "❌ Gateway (stale PID file)"; \
		fi; \
	else \
		echo "❌ Gateway (not running)"; \
	fi
	@echo ""

clean: ## Remove PID files and logs
	@echo "Cleaning up Milton state..."
	@rm -f $(STATE_DIR)/*.pid
	@rm -f /tmp/milton_api.log /tmp/milton_gateway.log
	@echo "Done."

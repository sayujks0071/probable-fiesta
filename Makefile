# OpenAlgo Makefile
# Setup & Operations for Local Development & Observability

PYTHON := python3
DOCKER_COMPOSE := docker compose -f observability/docker-compose.yml

.PHONY: help run obs-up obs-down obs-logs status healthcheck clean

help: ## Show this help
	@echo "OpenAlgo Management"
	@echo "-------------------"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

run: ## Run OpenAlgo (Daily Startup) with logging
	@echo "Starting OpenAlgo..."
	$(PYTHON) daily_startup.py

obs-up: ## Start Observability Stack (Loki, Promtail, Grafana)
	@echo "Starting Observability Stack..."
	$(DOCKER_COMPOSE) up -d
	@echo "Grafana: http://localhost:3000 (admin/admin)"
	@echo "Loki: http://localhost:3100"

obs-down: ## Stop Observability Stack
	@echo "Stopping Observability Stack..."
	$(DOCKER_COMPOSE) down

obs-logs: ## Tail Promtail and App logs
	@echo "Tailing logs..."
	$(DOCKER_COMPOSE) logs -f promtail

status: ## Check status of OpenAlgo and Observability
	@echo "--- OpenAlgo Process ---"
	@pgrep -fl "daily_startup.py|daily_prep.py" || echo "OpenAlgo not running"
	@echo "\n--- Observability Stack ---"
	$(DOCKER_COMPOSE) ps

healthcheck: ## Run the healthcheck script manually
	@echo "Running Healthcheck..."
	$(PYTHON) scripts/healthcheck.py

install-hooks: ## Install Systemd/Cron hooks for monitoring
	@echo "Select option:"
	@echo "1. Systemd User Timer (Preferred)"
	@echo "2. Cron Job"
	@read -p "Enter choice [1-2]: " choice; \
	if [ "$$choice" = "1" ]; then \
		bash scripts/install_systemd_user_timers.sh; \
	elif [ "$$choice" = "2" ]; then \
		bash scripts/install_cron.sh; \
	else \
		echo "Invalid choice"; \
	fi

clean: ## Clean up logs and temporary files
	rm -rf logs/*.log
	rm -rf __pycache__

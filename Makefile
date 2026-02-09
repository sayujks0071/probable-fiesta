# OpenAlgo Observability Makefile

.PHONY: obs-up obs-down obs-logs run status install-monitoring uninstall-monitoring

# Observability Stack
obs-up:
	@echo "Starting Observability Stack (Loki + Grafana + Promtail)..."
	@cd observability && docker compose up -d
	@echo "Grafana: http://localhost:3000 (admin/admin)"
	@echo "Loki: http://localhost:3100"

obs-down:
	@echo "Stopping Observability Stack..."
	@cd observability && docker compose down

obs-logs:
	@echo "Tailing Promtail container logs..."
	@cd observability && docker compose logs -f promtail

# Application
run:
	@echo "Running OpenAlgo..."
	@python3 daily_startup.py

# Status
status:
	@echo "=== OpenAlgo Process Status ==="
	@pgrep -af openalgo || echo "No OpenAlgo process running."
	@echo "\n=== Observability Containers ==="
	@cd observability && docker compose ps

# Monitoring Installation
install-monitoring:
	@echo "Installing Systemd Timers (Default)..."
	@bash scripts/install_systemd_user_timers.sh

uninstall-monitoring:
	@echo "Uninstalling Monitoring..."
	@bash scripts/uninstall_schedulers.sh

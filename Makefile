# OpenAlgo Makefile

.PHONY: all obs-up obs-down obs-logs run status help install-obs install-obs-cron uninstall-obs

all: help

help:
	@echo "OpenAlgo Management Commands"
	@echo "----------------------------"
	@echo "make obs-up           : Start Observability Stack (Loki, Promtail, Grafana)"
	@echo "make obs-down         : Stop Observability Stack"
	@echo "make obs-logs         : Tail Promtail logs and OpenAlgo app logs"
	@echo "make run              : Run OpenAlgo daily startup"
	@echo "make status           : Check health of OpenAlgo and Observability"
	@echo "make install-obs      : Install healthcheck schedulers (Systemd Timer)"
	@echo "make install-obs-cron : Install healthcheck schedulers (Cron)"
	@echo "make uninstall-obs    : Uninstall healthcheck schedulers"

obs-up:
	docker compose -f observability/docker-compose.yml up -d
	@echo "✅ Observability Stack Started."
	@echo "📊 Grafana: http://localhost:3000 (user: admin, pass: admin)"
	@echo "🔍 Loki:    http://localhost:3100"

obs-down:
	docker compose -f observability/docker-compose.yml down

obs-logs:
	@echo "Tailing Promtail logs and App logs (Ctrl+C to stop)..."
	@(trap 'kill 0' SIGINT; tail -f logs/openalgo.log & docker compose -f observability/docker-compose.yml logs -f promtail)

run:
	@echo "Starting OpenAlgo..."
	python3 daily_startup.py

status:
	@echo "--- Docker Services ---"
	docker compose -f observability/docker-compose.yml ps
	@echo "\n--- Health Check ---"
	@python3 scripts/healthcheck.py || echo "Health Check: FAILED (Check logs/healthcheck.log)"
	@echo "\n--- Alert Monitor ---"
	@python3 scripts/local_alert_monitor.py || echo "Alert Monitor: FAILED"

install-obs:
	./scripts/install_systemd_user_timers.sh

install-obs-cron:
	./scripts/install_cron.sh

uninstall-obs:
	./scripts/uninstall_schedulers.sh

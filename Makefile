# OpenAlgo Makefile

.PHONY: all obs-up obs-down obs-logs run daily app status help install-obs

all: help

help:
	@echo "OpenAlgo Management Commands"
	@echo "----------------------------"
	@echo "make obs-up       : Start Observability Stack (Loki, Promtail, Grafana)"
	@echo "make obs-down     : Stop Observability Stack"
	@echo "make obs-logs     : Tail Promtail logs and OpenAlgo app logs"
	@echo "make run          : Run OpenAlgo Web App (with logging)"
	@echo "make daily        : Run Daily Startup Routine"
	@echo "make status       : Check health of OpenAlgo and Observability"
	@echo "make install-obs  : Install healthcheck schedulers"

obs-up:
	cd observability && docker compose up -d
	@echo "Observability Stack Started. Grafana at http://localhost:3000"

obs-down:
	cd observability && docker compose down

obs-logs:
	@echo "Tailing Promtail logs and App logs (Ctrl+C to stop)..."
	# Trap ensures background tail process is killed when make exits
	@(trap 'kill 0' SIGINT; tail -f logs/openalgo.log & cd observability && docker compose logs -f promtail)

run:
	# Run from repo root, ensuring python path includes repo root
	PYTHONPATH=. python3 openalgo/app.py

daily:
	PYTHONPATH=. python3 daily_startup.py

status:
	@echo "--- Docker Services ---"
	cd observability && docker compose ps
	@echo "\n--- Health Check ---"
	PYTHONPATH=. python3 scripts/healthcheck.py

install-obs:
	./scripts/install_systemd_user_timers.sh

#!/bin/bash
# Keep Aegis paper bot + dashboard alive
cd /Users/zaid.barghouthi/trading-llm/bot || exit 1
mkdir -p reports

start_bot() {
  if ! pgrep -f "scripts/run_broker_paper.py" >/dev/null 2>&1; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) start bot" >> reports/bot_supervise.log
    nohup python3 -u scripts/run_broker_paper.py --config config_ib_paper_eurusd.yaml \
      >> reports/ib_paper_run.log 2>&1 &
    disown || true
  fi
}

start_dash() {
  if ! pgrep -f "scripts/run_dashboard.py" >/dev/null 2>&1; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) start dashboard" >> reports/bot_supervise.log
    nohup python3 -u scripts/run_dashboard.py --config config_ib_paper_eurusd.yaml --port 8787 \
      >> reports/dashboard.log 2>&1 &
    disown || true
  fi
}

start_bot
start_dash
while true; do
  start_bot
  start_dash
  sleep 8
done

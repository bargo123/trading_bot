# Real test — Mode B out-of-sample (fresh $100 each window)

Generated: 2026-08-07T18:31:13.781314+00:00

## Setup
- Config: `config_paper_forever_safe_14d.yaml`
- Start: **$100** · forever_safe 80/20 · EURUSD 1h `hw_range`
- Each window: fresh account + 60d indicator warmup

## Results

### last_14d_fresh
- Scored trades: 2 · scored WR: 100.0% · scored PnL: $1.18
- Run final: $105.27 · run WR: 100.0% · halt: ``
- Protected floor OK (≥$80): **True**

### prior_14d_fresh
- Scored trades: 3 · scored WR: 100.0% · scored PnL: $1.07
- Run final: $104.09 · run WR: 100.0% · halt: ``
- Protected floor OK (≥$80): **True**

## Mode B verdict: **PASS**
PASS = protected floor held. It does **not** mean forever 100% WR.

## Mode A — your 14-day paper test (start now)

```bash
cd ~/trading-llm/bot && source .venv/bin/activate
python scripts/run_paper.py --config config_paper_forever_safe_14d.yaml
```

Leave that terminal open for **14 days**. Mac must stay awake (or use `caffeinate`).

Check anytime:
```bash
python scripts/real_test_status.py
```

Journal: `reports/paper_journal.jsonl`

## Pass / fail after 14 paper days
| Rule | Pass |
|------|------|
| Equity ≥ $80 | required |
| No trading after first loss (halt) | required |
| Account not ruined | required |
| 100% win rate | **not required** |

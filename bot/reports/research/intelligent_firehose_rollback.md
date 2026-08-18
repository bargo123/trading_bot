# Intelligent Firehose rollback

Demo only. `allow_live` stays false.

## Restore CORE firehose brain

```text
git checkout 910adc0 -- bot/config_mt5_demo_firehose_hw.yaml bot/scripts/run_broker_paper.py
```

Then set `intelligent_firehose: false` if that key remains, keep `allow_live: false`, and restart **one** `run_broker_paper.py`.

## Restore after this implementation

HEAD of this work is on `main` after the Intelligent Firehose commits. To drop only the latest demo-brain wiring, revert those commits and restart a single runner.

Do not run a second `run_broker_paper.py`. Shadow observer uses `research_firehose_shadow.lock` and must never call `place_order`.

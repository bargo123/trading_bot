# Live versus model

Live equity=99.93 open=0 halted=False.

## Observed demo (journal / deals)

- orders ok/fail: 875/2544 (10019=2255, spread_skip=23737)
- flatten clips (Phase 0 sealed): n=616 WR=0.373 E=-0.0135 PF=0.61
- deals Phase 0 sealed: n=989 WR=0.421 E=-0.043 PF=0.34 net=-42.6
- deals ticket-deduped ingest: n=2000 WR=0.209 E=-0.07512 PF=0.1301528485409912 net=-150.24 (raw=92175, deduped_by=ticket)
- source: C:\Users\Raqam\trading_bot\bot\reports\mt5_demo_firehose_hw_journal.jsonl

## Named firehose benchmark (not the same window unless labeled)

- `entry_family_always_take` trades=103 E=-0.03451242196604659 PF=0.5657785979463091 not_a_champion=True

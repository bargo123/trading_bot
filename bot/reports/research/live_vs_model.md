# Live versus model

Live equity=57.41 open=4 halted=True.

## Observed demo (journal / deals)

- orders ok/fail: 861/2541 (10019=2252, spread_skip=20756)
- flatten clips (Phase 0 sealed): n=616 WR=0.373 E=-0.0135 PF=0.61
- deals Phase 0 sealed: n=989 WR=0.421 E=-0.043 PF=0.34 net=-42.6
- deals ticket-deduped ingest: n=1487 WR=0.2797579018157364 E=-0.06381304640215199 PF=0.19070362473347546 net=-94.89 (raw=87173, deduped_by=ticket)
- source: reports\mt5_demo_firehose_hw_journal.jsonl

## Named firehose benchmark (not the same window unless labeled)

- `replay_firehose_1_30_s3` trades=4113 E=-0.004855893032472543 PF=None not_a_champion=True

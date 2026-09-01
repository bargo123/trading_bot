# Firehose vs Firehose (shadow)

placed_orders: false
bars_compared: 10000
old_proposed_trades: 6004
new_proposed_fires: 42
new_proposed_scales: 0
new_proposed_reduces: 104
new_proposed_exits: 42
new_skips: 9812
disagreements: 5990

Old Firehose actions: buy=3126, sell=2878, skip=3996
Intelligent Firehose actions: exit=42, fire=42, reduce=104, skip=9812

Top Intelligent reasons:
- `no_validated_strategy_model`: 9812
- `max_per_symbol`: 103
- `positive_state_ev_on_validated_strategy`: 42
- `edge_gone:no_validated_strategy_model`: 22
- `structure_target_reached`: 16
- `structural_invalidation`: 3
- `opposite_side_invalidates_open_thesis`: 1
- `no_structural_side`: 1

The intelligent firehose does not win by trading less. It wins only if
later sealed evidence shows better expectancy, payoff, and tail risk.

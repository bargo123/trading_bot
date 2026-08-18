# Firehose vs Firehose (shadow)

placed_orders: false
bars_compared: 10000
old_proposed_trades: 5982
new_proposed_fires: 37
new_proposed_scales: 0
new_proposed_reduces: 91
new_proposed_exits: 36
new_skips: 9836
disagreements: 5969

Old Firehose actions: buy=3117, sell=2865, skip=4018
Intelligent Firehose actions: exit=36, fire=37, reduce=91, skip=9836

Top Intelligent reasons:
- `no_validated_strategy_model`: 9836
- `max_per_symbol`: 91
- `positive_state_ev_on_validated_strategy`: 37
- `edge_gone:no_validated_strategy_model`: 20
- `structure_target_reached`: 15
- `opposite_side_invalidates_open_thesis`: 1

The intelligent firehose does not win by trading less. It wins only if
later sealed evidence shows better expectancy, payoff, and tail risk.

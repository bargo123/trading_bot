with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'r') as f:
    content = f.read()

# Find 'def main():'
idx = content.find('def main():')
if idx >= 0:
    new_method = '''

    def _calculate_trade_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate real trade metrics from actual trades."""
        if not trades:
            return {}
        
        pnls = [t["pnl_pct"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        
        win_rate = len(wins) / len(pnls) if pnls else 0
        loss_rate = 1 - win_rate
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
        
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        pnls_sorted = sorted(pnls)
        p95_idx = int(len(pnls_sorted) * 0.05)
        p99_idx = int(len(pnls_sorted) * 0.01)
        p95_loss = pnls_sorted[p95_idx] if pnls_sorted else 0
        p99_loss = pnls_sorted[p99_idx] if pnls_sorted else 0
        max_loss = min(pnls) if pnls else 0
        
        # Calculate drawdown
        equity_curve = np.cumsum(pnls)
        running_max = np.maximum.accumulate(equity_curve)
        drawdown = (running_max - equity_curve) / np.where(running_max != 0, running_max, 1)
        max_drawdown = drawdown.max() if len(drawdown) > 0 else 0
        
        wins_erased_by_avg_loss = abs(avg_loss) / avg_win if avg_win != 0 else 0
        wins_erased_by_tail_loss = abs(p95_loss) / avg_win if avg_win != 0 else 0
        
        return {
            "win_rate": win_rate,
            "loss_rate": 1 - win_rate,
            "expectancy": expectancy,
            "profit_factor": profit_factor if profit_factor != float('inf') else 999,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "p95_loss": p95_loss,
            "p99_loss": p99_loss,
            "max_loss": min(pnls) if pnls else 0,
            "max_drawdown": max_drawdown,
            "wins_erased_by_avg_loss": abs(avg_loss) / avg_win if avg_win != 0 else 0,
            "wins_erased_by_tail_loss": abs(p95_loss) / avg_win if avg_win != 0 else 0,
            "total_trades": len(trades),
            "net_pnl": sum(pnls),
        }

"""
    content = content[:idx] + new_method + content[idx:]
    with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'w') as f:
        f.write(content)
    print('Added _calculate_trade_metrics method')
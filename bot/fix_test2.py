with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/tests/test_research_factory.py', 'r') as f:
    content = f.read()

old = '''        challenger = {
            "metrics": {
                "expectancy": 0.2,
                "profit_factor": 2.0,
                "avg_loss": -0.5,
                "p95_loss": -2.0,
                "max_drawdown": 0.15,
                "total_trades": 100,
            }
        }'''
new = '''        challenger = {
            "metrics": {
                "expectancy": 0.2,
                "profit_factor": 2.0,
                "avg_loss": -0.5,
                "p95_loss": -2.0,
                "max_drawdown": 0.15,
                "total_trades": 100,
                "win_rate": 0.6,
                "payoff_ratio": 1.5,
            }
        }'''
content = content.replace(old, new)

with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/tests/test_research_factory.py', 'w') as f:
    f.write(content)

print('Done')
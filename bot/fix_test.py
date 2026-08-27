with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/tests/test_research_factory.py', 'r') as f:
    content = f.read()

old = 'assert cc.promote_if_better({"metrics": cc.challenger["metrics"]}, cc.champion["metrics"]) is True'
new = 'assert cc.promote_if_better(cc.challenger, cc.champion) is True'
content = content.replace(old, new)

with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/tests/test_research_factory.py', 'w') as f:
    f.write(content)

print('Done')
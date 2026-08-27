with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'r') as f:
    content = f.read()
content = content.replace('REPORTS_DIR', r'Path("C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/reports")')
with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'w') as f:
    f.write(content)
print('Done')
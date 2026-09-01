with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'r') as f:
    lines = f.readlines()

# Fix line 1335 (index 1334) - fix the brackets
lines[1334] = '        return "\\n".join([f"  {k}: {v}" for k, v in sorted(classes.items(), key=lambda x: x[1], reverse=True)[:5]))\n'

with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'w') as f:
    f.writelines(lines)
print('Fixed')
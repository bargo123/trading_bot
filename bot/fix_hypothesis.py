with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/hypothesis.py', 'r') as f:
    content = f.read()

# Add HypothesisOrigin enum before HypothesisStatus
old = '''class HypothesisStatus(Enum):'''

new = '''class HypothesisOrigin(Enum):
    DIRECT_BOOK = "DIRECT_BOOK_HYPOTHESIS"
    BOOK_DERIVED = "BOOK_DERIVED_HYPOTHESIS"
    DATA_DERIVED = "DATA_DERIVED_HYPOTHESIS"
    ML_DISCOVERED = "ML_DISCOVERED_HYPOTHESIS"
    NOVEL_SYNTHESIZED = "NOVEL_SYNTHESIZED_HYPOTHESIS"


class HypothesisStatus(Enum):'''

content = content.replace(old, new)

with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/hypothesis.py', 'w') as f:
    f.write(content)

print('Done')
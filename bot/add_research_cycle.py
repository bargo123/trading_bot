with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'r') as f:
    content = f.read()

# Find the end of CursorCLI class
idx = content.find('class CursorCLI:')
if idx >= 0:
    lines = content[idx:].split('\n')
    end_idx = 0
    for i, line in enumerate(lines[1:], 1):
        if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
            end_idx = idx + sum(len(l) + 1 for l in lines[:i])
            break
    else:
        end_idx = idx + len(content[idx:])
    
    new_class = '''

class ResearchCycle:
    """Research cycle coordinator."""
    def __init__(self):
        pass
    
    def run(self) -> Dict[str, Any]:
        return {"status": "completed"}


'''
    content = content[:end_idx] + new_class + content[end_idx:]
    
    with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'w') as f:
        f.write(content)
    print('Added ResearchCycle class')
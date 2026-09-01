with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'r') as f:
    content = f.read()

# Find the end of _get_failed_hypothesis_evidence method
idx = content.find('def _get_failed_hypothesis_evidence')
if idx >= 0:
    lines = content[idx:].split('\n')
    method_end = 0
    for i, line in enumerate(lines[1:], 1):
        if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
            method_end = idx + sum(len(l) + 1 for l in lines[:i])
            break
    if method_end == 0:
        method_end = len(content)
    
    # Insert the missing method after this method
    new_method = '''\n    def _is_hypothesis_tested(self, hypothesis_id: str) -> bool:
        """Check if hypothesis has already been tested."""
        return hypothesis_id in self.state.hypothesis_registry

'''
    content = content[:method_end] + new_method + content[method_end:]
    
    with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'w') as f:
        f.write(content)
    print('Added _is_hypothesis_tested method')
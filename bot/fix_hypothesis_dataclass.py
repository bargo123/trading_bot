with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'r') as f:
    content = f.read()

idx = content.find('@dataclass\nclass Hypothesis:')
if idx >= 0:
    lines = content[idx:].split('\n')
    end_idx = 0
    for i, line in enumerate(lines[1:], 1):
        if line.strip().startswith('@dataclass') or (line.strip().startswith('class ') and 'Hypothesis' not in line):
            end_idx = idx + sum(len(l) + 1 for l in content[idx:].split('\n')[:i])
            break
    else:
        end_idx = idx + len(content[idx:])
    
    new_class = '''@dataclass
class Hypothesis:
    """A falsifiable research hypothesis with structured rules for replay."""
    hypothesis_id: str
    origin: HypothesisOrigin
    problem: str
    proposed_mechanism: str
    features_required: List[str]
    
    # Structured entry/exit rules (replacing free-text strings)
    entry_rule: Dict[str, Any]  # Structured entry conditions
    exit_rule: Dict[str, Any]   # Structured exit conditions
    
    # Trade parameters (replacing hardcoded values)
    side: str = "buy"  # "buy" or "sell"
    entry_price: Optional[float] = None
    invalidation_price: Optional[float] = None  # Stop loss / invalidation level
    target_price: Optional[float] = None  # Take profit target
    max_hold_s: int = 120  # Maximum hold time in seconds
    expected_effect: str
    falsification_criterion: str
    training_period: str
    validation_period: str
    walk_forward_result: Optional[Dict[str, Any]] = None
    cost_sensitivity: Optional[float] = None
    decision: Optional[str] = None
    book_evidence: List[Dict[str, Any]] = field(default_factory=list)
    ml_evidence: Dict[str, Any] = field(default_factory=dict)
    loss_autopsy_evidence: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "PROPOSED"  # PROPOSED, TESTING, REJECTED, CHALLENGER, CHAMPION
'''
    content = content[:idx] + new_class + content[end_idx:]
    
    with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'w') as f:
        f.write(content)
    print('Updated Hypothesis dataclass')
with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'r') as f:
    content = f.read()

idx = content.find('hypothesis = Hypothesis(')
if idx >= 0:
    end_idx = content.find('hypotheses.append(hypothesis)', idx)
    if end_idx >= 0:
        end_idx = content.find('\n', end_idx) + 1
        
        new_code = '''            # Create hypothesis with full provenance
            hypothesis = Hypothesis(
                hypothesis_id=f"hyp_{loss_class.lower()}_{int(time.time())}",
                origin=origin,
                problem=f"High frequency of {loss_class} losses ({count} occurrences)",
                proposed_mechanism=f"Address {loss_class} by implementing detection and avoidance",
                features_required=["regime", "structure", "volatility", "momentum", "session"],
                
                # Structured entry/exit rules
                entry_rule={
                    "type": "regime_structure_alignment",
                    "required_regimes": ["trend", "range"],
                    "required_structure": True
                },
                exit_rule={
                    "type": "regime_change",
                    "adverse_selection": True
                },
                
                # Trade parameters
                side="buy",  # Default, can be overridden
                entry_price=None,
                invalidation_price=None,
                target_price=None,
                max_hold_s=120,
                
                expected_effect=f"Reduce {loss_class} losses by 50%",
                falsification_criterion=f"{loss_class} losses do not decrease OOS",
                training_period="2024-01-01 to 2024-06-30",
                validation_period="2024-07-01 to 2024-09-30",
                book_evidence=book_evidence,
                ml_evidence=getattr(self, '_ml_evidence', {}).get(loss_class, {}),
                loss_autopsy_evidence=self.losses,
            )
            hypotheses.append(hypothesis)'''

        content = content[:idx] + new_code + content[end_idx:]
        
        with open(r'C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/aegis/research_factory/core.py', 'w') as f:
            f.write(content)
        print('Updated hypothesis generation')
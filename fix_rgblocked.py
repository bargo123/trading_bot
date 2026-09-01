import pathlib
p = pathlib.Path("bot/aegis/intel/firehose_brain.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

target = None
for i, line in enumerate(lines):
    if i < 1600:
        continue
    if '            if not sizing_preview.get("allowed"):' in line:
        target = i
        break

if target is None:
    print("NOT FOUND")
else:
    print(f"Found at line {target+1}")
    old = "".join(lines[target:target+17])
    print("OLD:", repr(old[:100]))
    S12 = " " * 12
    new_block = [
        S12 + 'if not sizing_preview.get("allowed"):
',
        S12 + "    _min_lot_risk = float(sizing_preview.get('actual_min_lot_risk_usd') or 0.0)
",
        S12 + "    _desired_risk = float(sizing_preview.get('desired_risk_usd') or 0.0)
",
        S12 + "    _excess_usd = round(max(0.0, _min_lot_risk - _desired_risk), 4)
",
        S12 + "    reason = str(sizing_preview.get('reason') or 'RISK_GRANULARITY_BLOCKED')
",
        S12 + "    _forced_demo_risk_cap = _desired_risk * float(
",
        S12 + "        self.cfg.get('forced_demo_risk_cap_multiplier', 5.0) or 5.0
",
        S12 + "    )
",
        S12 + "    _forced_min_lot_allowed = (
",
        S12 + "        forced_demo_lane
",
        S12 + "        and _min_lot_risk > 0
",
        S12 + "        and _min_lot_risk <= _forced_demo_risk_cap + 1e-9
",
        S12 + "    )
",
        S12 + "    if _forced_min_lot_allowed:
",
        S12 + "        vol_min = float(spec.get('volume_min', 0.01) or 0.01)
",
        S12 + "        sizing_preview = {
",
        S12 + '            "allowed": True, "lots": vol_min,
',
        S12 + '            "reason": "forced_demo_min_lot",
',
        S12 + '            "desired_risk_usd": round(_desired_risk, 4),
',
        S12 + '            "actual_min_lot_risk_usd": round(_min_lot_risk, 4),
',
        S12 + "        }
",
        S12 + '        quality_reasons.append(f"forced_demo_min_lot:excess={_excess_usd}")
',
        S12 + "    else:
",
        S12 + "        all_rejections.append(reason)
",
        S12 + "        distance = dict(econ.get('distance_to_eligibility') or {})
",
        S12 + "        distance['risk_excess_usd'] = _excess_usd
",
        S12 + "        candidate_evaluations.append(self._record_search_evaluation(
",
        S12 + "            candidate=mc,
",
        S12 + "            reasons=[reason],
",
        S12 + "            distance=distance,
",
        S12 + "            near_eligible=False,
",
        S12 + "            p_green=p_green,
",
        S12 + "        ))
",
        S12 + "        continue
",
        "
",
    ]
    lines[target:target+17] = new_block
    p.write_text("".join(lines), encoding="utf-8")
    print("PATCHED OK")
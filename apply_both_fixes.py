import pathlib
p = pathlib.Path("bot/aegis/intel/firehose_brain.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
NL = chr(10)
Q = chr(34)

# FIX 1: outer exploration_econ check - allow no_win_probability_evidence in forced_mode
# Target: line 1999 = if not exploration_econ.acceptable:
ev_target = None
for i, line in enumerate(lines):
    if i < 1990: continue
    if "        if not exploration_econ.acceptable:" in line:
        ev_target = i
        break
assert ev_target is not None, "EV check not found"
print("EV fix at", ev_target+1)
old_ev = "".join(lines[ev_target:ev_target+5])
print("OLD EV:", repr(old_ev[:80]))
S8  = " " * 8
S12 = " " * 12
S16 = " " * 16
new_ev = [
    S8 + "if not exploration_econ.acceptable:" + NL,
    S12 + "# In forced_demo_lane, missing win-probability evidence is" + NL,
    S12 + "# handled by forced_demo_exploration_uncalibrated below." + NL,
    S12 + "# Only hard rejections (negative EV, geometry) block here." + NL,
    S12 + "if not (" + NL,
    S12 + "    forced_mode" + NL,
    S12 + "    and exploration_econ.reason == " + Q + "no_win_probability_evidence" + Q + NL,
    S12 + "):" + NL,
    S16 + "return None, (" + NL,
    S16 + "    " + Q + "exploration_economics_rejected:" + Q + NL,
    S16 + "    f" + Q + "{exploration_econ.reason}" + Q + NL,
    S16 + ")" + NL,
]
lines[ev_target:ev_target+5] = new_ev
print("EV fix applied")

# Re-find FIX 2 location after FIX 1 shift
sizing_target = None
for i, line in enumerate(lines):
    if i < 1600: continue
    if "            if not sizing_preview.get" in line and "allowed" in line:
        sizing_target = i
        break
assert sizing_target is not None, "Sizing check not found"
print("Sizing fix at", sizing_target+1)
old_sz = "".join(lines[sizing_target:sizing_target+17])
print("OLD SZ:", repr(old_sz[:80]))
S12 = " " * 12
new_sz = [
    S12 + "if not sizing_preview.get(" + Q + "allowed" + Q + "):" + NL,
    S12 + "    _min_lot_risk = float(sizing_preview.get(" + Q + "actual_min_lot_risk_usd" + Q + ") or 0.0)" + NL,
    S12 + "    _desired_risk = float(sizing_preview.get(" + Q + "desired_risk_usd" + Q + ") or 0.0)" + NL,
    S12 + "    _excess_usd = round(max(0.0, _min_lot_risk - _desired_risk), 4)" + NL,
    S12 + "    reason = str(sizing_preview.get(" + Q + "reason" + Q + ") or " + Q + "RISK_GRANULARITY_BLOCKED" + Q + ")" + NL,
    S12 + "    _risk_cap = _desired_risk * float(self.cfg.get(" + Q + "forced_demo_risk_cap_multiplier" + Q + ", 5.0) or 5.0)" + NL,
    S12 + "    _forced_ok = forced_demo_lane and _min_lot_risk > 0 and _min_lot_risk <= _risk_cap + 1e-9" + NL,
    S12 + "    if _forced_ok:" + NL,
    S12 + "        _vmin = float(spec.get(" + Q + "volume_min" + Q + ", 0.01) or 0.01)" + NL,
    S12 + "        sizing_preview = {" + Q + "allowed" + Q + ": True, " + Q + "lots" + Q + ": _vmin," + NL,
    S12 + "                          " + Q + "reason" + Q + ": " + Q + "forced_demo_min_lot" + Q + "," + NL,
    S12 + "                          " + Q + "desired_risk_usd" + Q + ": round(_desired_risk, 4)," + NL,
    S12 + "                          " + Q + "actual_min_lot_risk_usd" + Q + ": round(_min_lot_risk, 4)}" + NL,
    S12 + "        quality_reasons.append(f" + Q + "forced_demo_min_lot:excess={_excess_usd}" + Q + ")" + NL,
    S12 + "    else:" + NL,
    S12 + "        all_rejections.append(reason)" + NL,
    S12 + "        distance = dict(econ.get(" + Q + "distance_to_eligibility" + Q + ") or {})" + NL,
    S12 + "        distance[" + Q + "risk_excess_usd" + Q + "] = _excess_usd" + NL,
    S12 + "        candidate_evaluations.append(self._record_search_evaluation(" + NL,
    S12 + "            candidate=mc," + NL,
    S12 + "            reasons=[reason]," + NL,
    S12 + "            distance=distance," + NL,
    S12 + "            near_eligible=False," + NL,
    S12 + "            p_green=p_green," + NL,
    S12 + "        ))" + NL,
    S12 + "        continue" + NL,
    NL,
]
lines[sizing_target:sizing_target+17] = new_sz
print("Sizing fix applied")

p.write_text("".join(lines), encoding="utf-8")
print("BOTH FIXES APPLIED OK")

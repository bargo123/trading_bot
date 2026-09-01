import pathlib
p = pathlib.Path("bot/aegis/intel/firehose_brain.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
target = None
for i, line in enumerate(lines):
    if i < 2000: continue
    if "        if not exploration_econ.acceptable:" in line:
        target = i
        break
if target is None:
    print("NOT FOUND")
else:
    print("Found at", target+1)
    old = "".join(lines[target:target+5])
    print("OLD:", repr(old[:100]))
    S8  = " " * 8
    S12 = " " * 12
    S16 = " " * 16
    Q = chr(34)
    NL = chr(10)
    new = [
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
    lines[target:target+5] = new
    p.write_text("".join(lines), encoding="utf-8")
    print("PATCHED OK")

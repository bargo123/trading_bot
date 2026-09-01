import pathlib
p = pathlib.Path("bot/aegis/intel/firehose_brain.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
NL = chr(10)
Q = chr(34)

# Find the unconditional continue after candidate_econ.acceptable check
# It follows the comment about "Missing probability is not an opportunity"
target = None
for i, line in enumerate(lines):
    if i < 1680: continue
    if "# opportunity; do not turn it into a broker order merely to" in line:
        target = i
        break
assert target is not None, "target not found"
print("Found target at", target+1)
# Lines: target = comment1, target+1 = comment2, target+2 = "continue"
old = "".join(lines[target:target+3])
print("OLD:", repr(old))
S16 = " " * 16
new = [
    S16 + "# opportunity; do not turn it into a broker order merely to" + NL,
    S16 + "# keep throughput non-zero.  In forced_demo_lane, however," + NL,
    S16 + "# evidence-collection with minimum risk is explicitly allowed." + NL,
    S16 + "if not (forced_demo_lane and reason == " + Q + "no_win_probability_evidence" + Q + "):" + NL,
    S16 + "    continue" + NL,
]
lines[target:target+3] = new
p.write_text("".join(lines), encoding="utf-8")
print("PATCHED OK")

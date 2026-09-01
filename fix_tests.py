import pathlib
p = pathlib.Path("bot/tests/test_exploration_firehose.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
NL = chr(10)

# Fix test 1: test_mt5_demo_forced_lane_does_not_fire_without_probability_evidence
# New behavior: forced_demo_lane CAN fire for evidence collection without probability
target1 = None
for i, line in enumerate(lines):
    if "def test_mt5_demo_forced_lane_does_not_fire_without_probability_evidence" in line:
        target1 = i
        break
assert target1 is not None, "test1 not found"
print("test1 at", target1+1)
# Replace lines target1 through target1+7 (def line + body)
old1 = "".join(lines[target1:target1+8])
print("OLD1:", repr(old1[:100]))
new1 = [
    "def test_mt5_demo_forced_lane_fires_for_evidence_collection_without_probability(tmp_path, monkeypatch):" + NL,
    "    # forced_demo_lane is specifically designed to allow evidence-collection trades" + NL,
    "    # even when no probability evidence exists.  A fire with FORCED_DEMO_EXPLORATION" + NL,
    "    # authority is the expected and correct outcome." + NL,
    "    result, skip = _run_forced_demo_brain(" + NL,
    "        tmp_path, monkeypatch, [_forced_candidate()]" + NL,
    "    )" + NL,
    "" + NL,
    "    assert skip is None" + NL,
    "    assert result is not None and result.action == chr(34)fire chr(34)" + NL,
    "    assert result.journal.get(chr(34)exploration_authority chr(34)) == chr(34)FORCED_DEMO_EXPLORATION chr(34)" + NL,
    "    assert result.journal.get(chr(34)calibration_status chr(34)) == chr(34)UNCALIBRATED chr(34)" + NL,
    "" + NL,
]
print("Error: need to use Q variable")

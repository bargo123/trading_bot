import pathlib
p = pathlib.Path("bot/tests/test_exploration_firehose.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
Q = chr(34)
NL = chr(10)

# Find and replace test 1
t1 = None
for i, l in enumerate(lines):
    if "def test_mt5_demo_forced_lane_does_not_fire_without_probability_evidence" in l:
        t1 = i
        break
assert t1 is not None, "test1 not found"
print("test1 at", t1+1)

# Find the end of test1 (blank line after assert)
end1 = t1 + 1
while end1 < len(lines) and (end1 < t1 + 2 or lines[end1].strip()):
    end1 += 1
print("test1 ends at", end1)

new_test1 = [
    "def test_mt5_demo_forced_lane_fires_for_evidence_collection(tmp_path, monkeypatch):" + NL,
    "    # forced_demo_lane exists to collect evidence even without probability data." + NL,
    "    # Fix 3 allows inner loop to proceed to forced_pool instead of hard-continuing." + NL,
    "    result, skip = _run_forced_demo_brain(" + NL,
    "        tmp_path, monkeypatch, [_forced_candidate()]" + NL,
    "    )" + NL,
    "" + NL,
    "    assert skip is None" + NL,
    "    assert result is not None and result.action == " + Q + "fire" + Q + NL,
    "    assert result.journal.get(" + Q + "exploration_authority" + Q + ") == " + Q + "FORCED_DEMO_EXPLORATION" + Q + NL,
    "    assert result.journal.get(" + Q + "calibration_status" + Q + ") == " + Q + "UNCALIBRATED" + Q + NL,
    "" + NL,
]
lines[t1:end1] = new_test1

# Find and replace test 2
t2 = None
for i, l in enumerate(lines):
    if "def test_forced_demo_lane_rejects_missing_executable_win_evidence" in l:
        t2 = i
        break
assert t2 is not None, "test2 not found"
print("test2 at", t2+1)
end2 = t2 + 1
while end2 < len(lines) and (end2 < t2 + 2 or lines[end2].strip()):
    end2 += 1
print("test2 ends at", end2)

new_test2 = [
    "def test_forced_demo_lane_accepts_evidence_collection_without_probability(tmp_path, monkeypatch):" + NL,
    "    result, skip = _run_forced_demo_brain(" + NL,
    "        tmp_path, monkeypatch, [_forced_candidate()]" + NL,
    "    )" + NL,
    "" + NL,
    "    assert skip is None" + NL,
    "    assert result is not None and result.action == " + Q + "fire" + Q + NL,
    "    assert result.journal.get(" + Q + "exploration_authority" + Q + ") == " + Q + "FORCED_DEMO_EXPLORATION" + Q + NL,
    "" + NL,
]
lines[t2:end2] = new_test2

p.write_text("".join(lines), encoding="utf-8")
print("BOTH TESTS UPDATED")

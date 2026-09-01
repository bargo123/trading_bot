
import pathlib
p = pathlib.Path('bot/aegis/intel/firehose_brain.py')
lines = p.read_text(encoding='utf-8').splitlines(keepends=True)

# Line 1999 (0-indexed: 1998) is 'if not exploration_econ.acceptable:'
# Lines 1999-2004 (0-indexed 1998-2003) are the 6-line block to replace
# Line 2005 (0-indexed 2004) is 'if forced_mode:' - keep it
# Line 2006 (0-indexed 2005) is 'capture_authorization = ...' - keep it

target_start = 1998  # 0-indexed
assert '        if not exploration_econ.acceptable:' in lines[target_start], repr(lines[target_start])
# Verify the 5 lines after
block = ''.join(lines[target_start:target_start+5])
print('OLD block:', repr(block))

INDENT = chr(32)*8
I2 = chr(32)*12
I3 = chr(32)*16
new_lines = [
    INDENT + 'if not exploration_econ.acceptable:\n',
    I2 + '# In forced_demo_lane mode, missing win-probability evidence is\n',
    I2 + '# handled explicitly by forced_demo_exploration_uncalibrated below.\n',
    I2 + '# Only hard rejections (negative EV, geometry) block here.\n',
    I2 + 'if not (\n',
    I2 + '    forced_mode\n',
    I2 + '    and exploration_econ.reason == ' + chr(34) + 'no_win_probability_evidence' + chr(34) + '\n',
    I2 + '):\n',
    I3 + 'return None, (\n',
    I3 + '    ' + chr(34) + 'exploration_economics_rejected:' + chr(34) + '\n',
    I3 + '    f' + chr(34) + '{exploration_econ.reason}' + chr(34) + '\n',
    I3 + ')\n',
]
# Replace only the 5 lines (the if block through closing paren, NOT if forced_mode:)
lines[target_start:target_start+5] = new_lines
p.write_text(''.join(lines), encoding='utf-8')
print('PATCHED OK')
print('New block:', repr(''.join(lines[target_start:target_start+len(new_lines)+2])))

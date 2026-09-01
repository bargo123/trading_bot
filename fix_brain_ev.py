
import pathlib
p = pathlib.Path('bot/aegis/intel/firehose_brain.py')
lines = p.read_text(encoding='utf-8').splitlines(keepends=True)

target_start = None
for i, line in enumerate(lines):
    if '        if not exploration_econ.acceptable:' in line and i > 2100:
        target_start = i
        break

if target_start is None:
    print('NOT FOUND')
else:
    print('FOUND at', target_start+1)
    snippet = ''.join(lines[target_start:target_start+7])
    print('OLD:', repr(snippet))
    INDENT = '        '
    I2 = '            '
    I3 = '                '
    new_block = [
        INDENT + 'if not exploration_econ.acceptable:\n',
        I2 + '# In forced_demo_lane mode, missing win-probability evidence\n',
        I2 + '# is handled by forced_demo_exploration_uncalibrated path below.\n',
        I2 + '# Only hard economic rejections (negative EV, geometry) block here.\n',
        I2 + 'if not (\n',
        I2 + '    forced_mode\n',
        I2 + '    and exploration_econ.reason == ' + chr(34) + 'no_win_probability_evidence' + chr(34) + '\n',
        I2 + '):\n',
        I3 + 'return None, (\n',
        I3 + '    ' + chr(34) + 'exploration_economics_rejected:' + chr(34) + '\n',
        I3 + '    f' + chr(34) + '{exploration_econ.reason}' + chr(34) + '\n',
        I3 + ')\n',
        INDENT + 'if forced_mode:\n',
    ]
    lines[target_start:target_start+7] = new_block
    p.write_text(''.join(lines), encoding='utf-8')
    print('PATCHED OK')

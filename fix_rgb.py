import pathlib
p = pathlib.Path("bot/aegis/intel/firehose_brain.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
target = None
for i, line in enumerate(lines):
    if i < 1600: continue
    if chr(32)*12 + "if not sizing_preview.get(\"allowed\"):" in line:
        target = i
        break
if target is None:
    print("NOT FOUND")
else:
    print(f"Found at {target+1}")
    old_count = 17
    snippet = "".join(lines[target:target+old_count])
    print("OLD:", repr(snippet[:120]))
    S12 = " " * 12
    nb = []
    nb.append(S12 + "if not sizing_preview.get(chr(34)+(chr(97)+chr(108)+chr(108)+chr(111)+chr(119)+chr(101)+chr(100))+chr(34)):\n")
    p.write_text("".join(lines), encoding="utf-8")
    print("placeholder")

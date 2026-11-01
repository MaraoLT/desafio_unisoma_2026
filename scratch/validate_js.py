import re
from pathlib import Path

html_path = Path("src/app/static/index.html")
content = html_path.read_text(encoding="utf-8")
script = re.search(r"<script>(.*?)</script>", content, re.DOTALL).group(1)

in_str = None
escape = False
counts = {"{": 0, "}": 0, "(": 0, ")": 0, "[": 0, "]": 0}
line_num = 1
for i, ch in enumerate(script):
    if ch == "\n":
        line_num += 1
    if in_str:
        if escape:
            escape = False
        elif ch == "\\":
            escape = True
        elif ch == in_str:
            in_str = None
    else:
        if ch in ('"', "'", "`"):
            in_str = ch
        elif ch in counts:
            counts[ch] += 1

print(f"Braces: {{ {counts['{']} vs }} {counts['}']}")
print(f"Parens: ( {counts['(']} vs ) {counts[')']}")
print(f"Brackets: [ {counts['[']} vs ] {counts[']']}")
assert counts["{"] == counts["}"], f"Unbalanced braces! {counts['{']} vs {counts['}']}"
assert counts["("] == counts[")"], f"Unbalanced parens! {counts['(']} vs {counts[')']}"
assert counts["["] == counts["]"], f"Unbalanced brackets! {counts['[']} vs {counts[']']}"
print("Bracket balance check passed successfully!")

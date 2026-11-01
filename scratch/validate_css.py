from pathlib import Path

css_path = Path("src/app/static/style.css")
content = css_path.read_text(encoding="utf-8")

in_comment = False
open_braces = 0
close_braces = 0
i = 0
n = len(content)
while i < n:
    if in_comment:
        if content[i:i+2] == "*/":
            in_comment = False
            i += 2
            continue
    else:
        if content[i:i+2] == "/*":
            in_comment = True
            i += 2
            continue
        elif content[i] == "{":
            open_braces += 1
        elif content[i] == "}":
            close_braces += 1
    i += 1

print(f"CSS Braces: {{ {open_braces} vs }} {close_braces}")
assert open_braces == close_braces, f"CSS Braces mismatch: {open_braces} vs {close_braces}"
print("CSS syntax check passed!")

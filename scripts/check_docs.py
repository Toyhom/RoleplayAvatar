"""Check documentation links, translated page coverage and language navigation."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = [*ROOT.glob("README*.md"), ROOT / "NOTICE.md", *ROOT.glob("guides/**/*.md"),
         ROOT / "web/THIRD_PARTY.md"]
errors = []
expected = {p.name for p in (ROOT / "guides").glob("*.md")}
for locale in ("zh-CN", "ja"):
    actual = {p.name for p in (ROOT / "guides" / locale).glob("*.md")}
    if actual != expected:
        errors.append(f"{locale}: missing {sorted(expected - actual)}, extra {sorted(actual - expected)}")
for path in paths:
    content = path.read_text()
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
        if "://" in target or target.startswith("#"):
            continue
        target = target.split("#", 1)[0].split(" ", 1)[0]
        if target and not (path.parent / target).exists():
            errors.append(f"{path.relative_to(ROOT)}: missing {target}")
    if path.parent.name in {"guides", "zh-CN", "ja"} and not all(
        label in content for label in ("[English]", "[简体中文]", "[日本語]")
    ):
        errors.append(f"{path.relative_to(ROOT)}: missing language navigation")
if errors:
    raise SystemExit("\n".join(errors))
print(f"Checked links and translations in {len(paths)} documents")

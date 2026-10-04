"""Check documentation links, language coverage and Markdown rendering hazards."""
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = [*ROOT.glob("README*.md"), ROOT / "NOTICE.md", *ROOT.glob("guides/**/*.md"),
         *ROOT.glob("fixtures/**/*.md"), ROOT / "web/THIRD_PARTY.md"]
errors = []


def check_markdown(content):
    """Keep prose URLs explicit, while preserving GitHub's inline video syntax."""
    issues = []
    fence = None
    for number, line in enumerate(content.splitlines(), 1):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            run, suffix = marker.groups()
            if fence is None:
                fence = (run[0], len(run), number)
            elif run[0] == fence[0] and len(run) >= fence[1] and not suffix.strip():
                fence = None
            continue
        if fence:
            continue
        if re.fullmatch(r"https://github\.com/user-attachments/assets/[0-9a-f-]+", line.strip()):
            continue
        prose = re.sub(r"(`+).*?\1", " ", line)
        prose = re.sub(r"!?\[[^\]]*\]\([^)]*\)|<https?://[^>]*>", " ", prose)
        if re.search(r"https?://", prose):
            issues.append((number, "Use an explicit [label](URL) link or <URL> in prose"))
        for match in re.finditer(r"\*\*(.+?)\*\*(\w)", prose):
            if unicodedata.category(match[1][-1]).startswith("P"):
                issues.append((number, "Add a space after bold text ending in punctuation"))
        if prose.count("**") % 2:
            issues.append((number, "Unpaired bold delimiter"))
    if fence:
        issues.append((fence[2], "Unclosed fenced code block"))
    return issues


expected = {p.name for p in (ROOT / "guides").glob("*.md")}
for locale in ("zh-CN", "ja"):
    actual = {p.name for p in (ROOT / "guides" / locale).glob("*.md")}
    if actual != expected:
        errors.append(f"{locale}: missing {sorted(expected - actual)}, extra {sorted(actual - expected)}")
for path in paths:
    content = path.read_text()
    for number, message in check_markdown(content):
        errors.append(f"{path.relative_to(ROOT)}:{number}: {message}")
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

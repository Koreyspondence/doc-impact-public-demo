import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import quote


def git(*args):
    return subprocess.check_output(["git", *args], text=True)


def matches(text, concept):
    return any(
        re.search(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE)
        for alias in concept["aliases"]
    )


def analyze(base):
    registry = json.loads(Path(".github/doc-concepts/concepts.json").read_text())
    changed = set(filter(None, git("diff", "--name-only", "-z", f"{base}...HEAD",
                                    "--", ":(glob)**/*.md").split("\0")))
    diff = git("diff", "--unified=0", f"{base}...HEAD", "--", *sorted(changed)) if changed else ""
    edits = "\n".join(line[1:] for line in diff.splitlines()
                      if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
    topics = [concept for concept in registry.values() if matches(edits, concept)]
    groups = {"review": [], "updated": [], "archived": []}
    for path in sorted(Path("docs").rglob("*.md")):
        lines = [
            i for i, line in enumerate(path.read_text().splitlines(), 1)
            if any(matches(line, topic) for topic in topics)
        ]
        if lines:
            group = ("archived" if path.is_relative_to("docs/archive")
                     else "updated" if path.as_posix() in changed else "review")
            groups[group].append({"path": path.as_posix(), "lines": lines})
    return {"changed": sorted(changed), "topics": [c["title"] for c in topics], "groups": groups}


def markdown(report, link_base):
    title = "## Documentation impact\n"
    if not report["changed"]:
        return title + "\nThis PR doesn't change any documentation.\n"
    if not report["topics"]:
        return title + "\nDocumentation changed, but no tracked concept matched.\n"
    groups = report["groups"]
    topics = ", ".join(report["topics"])
    out = [title, f"**{topics}**: {len(groups['review'])} other files to review.", "",
           "<details><summary>Show files to review</summary>", ""]
    for key, label in (("review", "To review"), ("updated", "Already edited in this PR"),
                       ("archived", "Archived (no action)")):
        if groups[key]:
            out += [f"### {label}", ""]
        for item in groups[key]:
            path = item["path"]
            url = f"{link_base}/{quote(path)}"
            lines = ", ".join(f"[line {n}]({url}?plain=1#L{n})" for n in item["lines"])
            check = "[ ] " if key == "review" else ""
            out.append(f"- {check}[`{path}`]({url}) ({lines})")
        out.append("")
    out += ["</details>", "", "_Advisory only. A matching mention may not need an edit._"]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--link-base")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.json and not args.link_base:
        parser.error("--link-base is required unless --json is supplied")
    report = analyze(args.base)
    print(json.dumps(report, indent=2) if args.json else markdown(report, args.link_base), end="\n")

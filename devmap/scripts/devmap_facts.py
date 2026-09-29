#!/usr/bin/env python3
"""DevMap deterministic facts: changed files, planned-vs-actual sets, folded tree, PR checks.
Standard library only. JSON on stdout, diagnostics on stderr; errors exit non-zero with no JSON.
Actual changes = `git diff -M --name-status <base>` (working tree vs base: committed,
staged and unstaged tracked changes) + `git ls-files --others --exclude-standard`.
Without --base, <base> = `git merge-base origin/main HEAD`, else `git merge-base main HEAD`.
An unstaged `mv` is not a rename: it is a deletion plus an untracked addition.
"""
import argparse
import json
import posixpath
import shutil
import subprocess
import sys

MAX_LINES = 30
ACTIONS = {"added": "新增", "modified": "修改", "deleted": "删除", "renamed": "重命名"}

class FactsError(Exception):
    """Any failure; main() reports it on stderr and prints no JSON."""

def git(*args):
    cmd = ["git", "-c", "diff.renames=true", "-c", "core.quotePath=false", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FactsError("git %s failed: %s" % (args[0], result.stderr.strip()))
    return result.stdout

def resolve_base(ref):
    if ref:
        try:
            return git("rev-parse", "--verify", "--quiet", ref + "^{commit}").strip(), "argument"
        except FactsError:
            raise FactsError("cannot resolve --base %r to a commit" % ref) from None
    for upstream in ("origin/main", "main"):
        try:
            return git("merge-base", upstream, "HEAD").strip(), "merge-base %s HEAD" % upstream
        except FactsError:
            continue
    raise FactsError("no --base given and neither origin/main nor main has a merge-base with HEAD")

def classify(name_status_z, untracked_z):
    """Parse `git diff -M --name-status -z` plus `git ls-files -z` output into change lists."""
    fields = [f for f in name_status_z.split("\0") if f]
    changes = {"added": [], "modified": [], "deleted": [], "renamed": []}
    i = 0
    while i < len(fields):
        status = fields[i][0]
        if status in "RC":  # a copy (only if detection is forced on) is a new file
            if status == "R":
                changes["renamed"].append({"from": fields[i + 1], "to": fields[i + 2]})
            else:
                changes["added"].append(fields[i + 2])
            i += 3
            continue
        changes[{"A": "added", "D": "deleted"}.get(status, "modified")].append(fields[i + 1])
        i += 2
    for path in (p for p in untracked_z.split("\0") if p):
        if path in changes["deleted"]:  # deleted from the index but present on disk again
            changes["deleted"].remove(path)
            changes["modified"].append(path)
        else:
            changes["added"].append(path)
    for key in ("added", "modified", "deleted"):
        changes[key] = sorted(set(changes[key]))
    changes["renamed"].sort(key=lambda r: r["to"])
    return changes

def actual_entries(changes):
    """One entry per changed file (path -> action); a rename is one file keyed by its new path."""
    entries = {p: key for key in ("added", "modified", "deleted") for p in changes[key]}
    entries.update((r["to"], "renamed") for r in changes["renamed"])
    return entries

def normalize(path):
    norm = posixpath.normpath(path.strip().replace("\\", "/"))
    if not path.strip() or norm.startswith(("../", "/")) or norm in (".", ".."):
        raise FactsError("invalid planned path: %r" % path)
    return norm

def compare(planned, changes):
    actual = sorted(actual_entries(changes))
    if planned is None:
        return {"planned": None, "actual": actual, "unplanned": None, "not_started": None}
    planned = sorted({normalize(p) for p in planned})
    old_of = {r["to"]: r["from"] for r in changes["renamed"]}
    touched = set(actual) | set(old_of.values())
    return {"planned": planned, "actual": actual,
            "unplanned": [p for p in actual if p not in planned and old_of.get(p) not in planned],
            "not_started": [p for p in planned if p not in touched]}

def _items(paths, depth):
    """Paths with <= depth directories stay leaves; deeper ones collapse into their (depth+1)-level dir."""
    items = {}
    for path in paths:
        parts = path.split("/")
        if len(parts) - 1 <= depth:
            items[path] = None
        else:
            items.setdefault("/".join(parts[:depth + 1]) + "/", []).append(path)
    return items

def _dir_label(members, entries):
    counts = {}
    for action in filter(None, (entries.get(path) for path in members)):
        counts[action] = counts.get(action, 0) + 1
    detail = " / ".join("%s %d" % (ACTIONS[a], counts[a]) for a in ACTIONS if a in counts)
    return "（%d 个文件%s）" % (len(members), "：" + detail if detail else "")

def _render(items, entries):
    root = {}
    for key, members in items.items():
        parts = key.rstrip("/").split("/")
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        if members is None:
            label = ACTIONS.get(entries.get(key), "")
            node[parts[-1]] = "[%s]" % label if label else ""
        else:
            node[parts[-1] + "/"] = _dir_label(members, entries)
    lines = []

    def walk(node, prefix, top):
        for index, name in enumerate(sorted(node)):
            last, value = index == len(node) - 1, node[name]
            glyph = "" if top else ("└── " if last else "├── ")
            lines.append(prefix + glyph + name + ("  " + value if isinstance(value, str) and value else ""))
            if isinstance(value, dict):
                walk(value, "" if top else prefix + ("    " if last else "│   "), False)
    walk(root, "", True)
    return lines

def fold_tree(paths, entries=None, max_lines=MAX_LINES):
    """Deepest directory tree within max_lines; shown counts always add up to the true total."""
    paths, entries = sorted(set(paths)), entries or {}
    items, lines = {}, []
    for depth in range(max((p.count("/") for p in paths), default=0), -1, -1):
        items = _items(paths, depth)
        lines = _render(items, entries)
        if len(lines) <= max_lines:
            break
    else:
        if paths:
            items, lines = {"./": paths}, ["./  " + _dir_label(paths, entries)]
    listed = [{"path": k, "count": 1 if v is None else len(v)} for k, v in sorted(items.items())]
    shown = sum(item["count"] for item in listed)
    if shown != len(paths):
        raise FactsError("tree count %d does not match total %d" % (shown, len(paths)))
    return {"total": len(paths), "shown_total": shown, "lines": lines, "items": listed}

def pr_checks(number):
    if shutil.which("gh") is None:
        return {"status": "未知", "reason": "gh 不可用"}
    result = subprocess.run(["gh", "pr", "checks", str(number), "--json", "name,bucket"],
                            capture_output=True, text=True)
    try:  # gh exits 8 while checks are still pending
        rows = json.loads(result.stdout) if result.returncode in (0, 8) else None
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        return {"status": "未知", "reason": "gh pr checks 失败：" + (result.stderr.strip() or "无输出")}
    counts = {b: sum(1 for row in rows if row.get("bucket") == b)
              for b in ("pass", "fail", "pending", "skipping", "cancel")}
    return {"status": "已获取", "total": len(rows), **counts}

def collect(base_ref=None, planned=None, pr=None):
    base, base_source = resolve_base(base_ref)
    head = git("rev-parse", "--verify", "HEAD").strip()
    changes = classify(git("diff", "-M", "--name-status", "-z", base),
                       git("ls-files", "--others", "--exclude-standard", "-z"))
    sets, entries = compare(planned, changes), actual_entries(changes)
    counts = {key: len(changes[key]) for key in ACTIONS}
    counts["total"] = len(entries)
    facts = {"base": base, "base_source": base_source, "head": head, "changes": changes,
             "counts": counts, "sets": sets,
             "trees": {"actual": fold_tree(entries, entries),
                       "planned": None if sets["planned"] is None else fold_tree(sets["planned"])}}
    if pr is not None:
        facts["checks"] = pr_checks(pr)
    return facts

def main(argv=None):
    parser = argparse.ArgumentParser(description="DevMap deterministic facts (JSON on stdout)")
    parser.add_argument("--base", help="base ref; default: merge-base of origin/main (or main) and HEAD")
    parser.add_argument("--pr", type=int, help="PR number; adds check counts via gh")
    parser.add_argument("--planned", nargs="+", action="extend", metavar="PATH",
                        help="planned file paths (union over all Tasks)")
    args = parser.parse_args(argv)
    try:
        facts = collect(args.base, args.planned, args.pr)
    except FactsError as error:
        print("devmap_facts: %s" % error, file=sys.stderr)
        return 2
    json.dump(facts, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())

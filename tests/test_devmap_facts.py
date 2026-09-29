"""Unit tests for devmap/scripts/devmap_facts.py (the counting scenarios moved out of the LLM fixtures)."""
import importlib.util
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).resolve().parent.parent / "devmap" / "scripts" / "devmap_facts.py"
_spec = importlib.util.spec_from_file_location("devmap_facts", SCRIPT)
facts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(facts)


def changes(added=(), modified=(), deleted=(), renamed=()):
    return {"added": sorted(added), "modified": sorted(modified), "deleted": sorted(deleted),
            "renamed": [{"from": a, "to": b} for a, b in renamed]}


def covered(tree, paths):
    """Each path is represented by exactly one tree item (a leaf or a non-overlapping dir)."""
    items = tree["items"]
    for path in paths:
        hits = [i for i in items if i["path"] == path or (i["path"].endswith("/") and (
            i["path"] == "./" or path.startswith(i["path"])))]
        if len(hits) != 1:
            return False
    return True


class FoldTreeTest(unittest.TestCase):
    def assertConserved(self, tree, paths):
        self.assertEqual(tree["total"], len(set(paths)))
        self.assertEqual(sum(i["count"] for i in tree["items"]), tree["total"])
        self.assertLessEqual(len(tree["lines"]), facts.MAX_LINES)
        self.assertTrue(covered(tree, paths))

    def test_scenario2_fifteen_files_expand_under_src(self):
        paths = ["src/%s.md" % c for c in "abcdefghijklmno"]
        tree = facts.fold_tree(paths, {p: "modified" for p in paths})
        self.assertConserved(tree, paths)
        self.assertEqual(tree["lines"][0], "src/")
        self.assertEqual(len(tree["lines"]), 16)
        self.assertEqual(tree["lines"][-1], "└── o.md  [修改]")

    def test_scenario3_121_files_fold_to_two_items(self):
        paths = ["AGENTS.md"] + ["src/group%02d/item%02d.md" % (g, i)
                                 for g in range(1, 41) for i in range(1, 4)]
        entries = {p: "added" for p in paths}
        entries["AGENTS.md"] = "modified"
        tree = facts.fold_tree(paths, entries)
        self.assertConserved(tree, paths)
        self.assertEqual(tree["total"], 121)
        self.assertEqual(tree["lines"], ["AGENTS.md  [修改]", "src/  （120 个文件：新增 120）"])

    def test_scenario3_variants(self):
        flat = ["AGENTS.md"] + ["f%03d.md" % i for i in range(120)]
        tree = facts.fold_tree(flat)
        self.assertConserved(tree, flat)
        self.assertEqual(tree["lines"], ["./  （121 个文件）"])
        thirty = ["f%02d.md" % i for i in range(30)]
        self.assertEqual(len(facts.fold_tree(thirty)["items"]), 30)
        same_dir = ["src/f%02d.md" % i for i in range(31)]
        self.assertEqual(facts.fold_tree(same_dir)["lines"], ["src/  （31 个文件）"])
        old = ["old/item%02d.md" % i for i in range(30)]
        new = ["new/item%02d.md" % i for i in range(30)]
        sets = facts.compare(old, changes(modified=old, added=new))
        self.assertEqual((len(sets["planned"]), len(sets["actual"])), (30, 60))
        self.assertEqual(sets["unplanned"], sorted(new))
        self.assertEqual(sets["not_started"], [])

    def test_scenario18_small_tree_and_large_fold(self):
        small = [".github/workflows/docs-check.yml", "docs/README.md", "docs/architecture.md",
                 "docs/usage.md", "scripts/check-docs.sh"]
        self.assertEqual(facts.fold_tree(small)["lines"], [
            ".github/", "└── workflows/", "    └── docs-check.yml", "docs/", "├── README.md",
            "├── architecture.md", "└── usage.md", "scripts/", "└── check-docs.sh"])
        large = (["src/m%d/f%02d.ts" % (i % 7, i) for i in range(71)]
                 + ["tests/t%02d.py" % i for i in range(38)]
                 + [".github/workflows/w%d.yml" % i for i in range(8)]
                 + ["docs/d%d.md" % i for i in range(9)])
        tree = facts.fold_tree(large)
        self.assertConserved(tree, large)
        self.assertEqual(tree["total"], 126)
        self.assertEqual({i["path"]: i["count"] for i in tree["items"]},
                         {"src/": 71, "tests/": 38, ".github/": 8, "docs/": 9})

    def test_random_sets_conserve_counts(self):
        rng = random.Random(20260928)
        for _ in range(300):
            paths = {"/".join(["d%d" % rng.randrange(4) for _ in range(rng.randrange(5))]
                              + ["f%d.md" % rng.randrange(60)]) for _ in range(rng.randrange(1, 200))}
            self.assertConserved(facts.fold_tree(paths), paths)

    def test_empty(self):
        self.assertEqual(facts.fold_tree([])["total"], 0)


class CompareTest(unittest.TestCase):
    def test_scenario14_shared_path_and_add_delete(self):
        union = ["src/a.md", "docs/shared.md", "src/b.md", "docs/shared.md"]
        self.assertEqual(len(facts.compare(union, changes())["planned"]), 3)
        sets = facts.compare(["src/a.md"], changes(modified=["src/a.md"], added=["docs/new.md"],
                                                   deleted=["docs/old.md"]))
        self.assertEqual(sets["planned"], ["src/a.md"])
        self.assertEqual(len(sets["actual"]), 3)
        self.assertEqual(sets["unplanned"], ["docs/new.md", "docs/old.md"])

    def test_scenario29_shared_union_and_unknown(self):
        tasks = [["src/bills.ts", "docs/shared.md"], ["src/export.ts", "docs/shared.md"],
                 ["docs/help.md"]]
        planned = facts.compare([p for t in tasks for p in t], changes())["planned"]
        self.assertEqual([len(t) for t in tasks], [2, 2, 1])
        self.assertEqual(len(planned), 4)
        self.assertEqual(planned.count("docs/shared.md"), 1)
        unknown = facts.compare(None, changes(added=["x.md"]))
        self.assertIsNone(unknown["planned"])
        self.assertIsNone(unknown["unplanned"])
        self.assertIsNone(unknown["not_started"])

    def test_rename_matches_old_or_new_planned_path(self):
        moved = changes(renamed=[("docs/help.md", "docs/guide.md")])
        for planned in (["docs/help.md"], ["docs/guide.md"]):
            sets = facts.compare(planned, moved)
            self.assertEqual((sets["unplanned"], sets["not_started"]), ([], []))

    def test_invalid_planned_path(self):
        with self.assertRaises(facts.FactsError):
            facts.compare(["../outside.md"], changes())


class GitRepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.repo)
        self.git("init", "-q", "-b", "main")
        for name, text in {"keep.md": "k\n", "old.md": "o\n" * 20, "gone.md": "g\n",
                           "edit.md": "e\n", "loose.md": "l\n" * 20}.items():
            Path(name).write_text(text)
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        self.git("switch", "-q", "-c", "work")

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def git(self, *args):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(["git", *args], check=True, env=env, capture_output=True)

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = facts.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_working_tree_changes_against_default_base(self):
        Path("committed.md").write_text("c\n")
        self.git("add", "committed.md")
        self.git("commit", "-q", "-m", "work")
        self.git("mv", "old.md", "renamed.md")          # staged rename -> R
        Path("loose.md").rename("moved-loose.md")      # unstaged mv -> deleted + untracked added
        Path("gone.md").unlink()                       # unstaged delete
        Path("edit.md").write_text("changed\n")        # unstaged modify
        Path("new.md").write_text("n\n")               # untracked
        code, out, err = self.run_main("--planned", "edit.md", "renamed.md", "later.md")
        self.assertEqual((code, err), (0, ""))
        data = json.loads(out)
        self.assertEqual(data["base_source"], "merge-base main HEAD")
        self.assertEqual(data["changes"], changes(
            added=["committed.md", "moved-loose.md", "new.md"], modified=["edit.md"],
            deleted=["gone.md", "loose.md"], renamed=[("old.md", "renamed.md")]))
        self.assertEqual(data["counts"]["total"], 7)
        self.assertEqual(data["trees"]["actual"]["shown_total"], 7)
        self.assertEqual(data["sets"]["not_started"], ["later.md"])
        self.assertEqual(len(data["sets"]["unplanned"]), 5)

    def test_bad_base_prints_no_json(self):
        code, out, err = self.run_main("--base", "no-such-ref")
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("cannot resolve", err)

    def test_no_default_base_is_an_error(self):
        self.git("branch", "-q", "-m", "main", "trunk")
        code, out, err = self.run_main()
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("merge-base", err)

    def test_pr_checks_unknown_without_gh(self):
        path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(self.repo)
        try:
            checks = facts.pr_checks(1)
        finally:
            os.environ["PATH"] = path
        self.assertEqual(checks["status"], "未知")
        self.assertIn("gh", checks["reason"])


if __name__ == "__main__":
    unittest.main()

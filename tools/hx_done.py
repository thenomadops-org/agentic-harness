#!/usr/bin/env python3
"""`hx done` and `hx merge`: clean up after a finished ticket. Stdlib only.

    hx done OPS-347 [--dry-run] [--force] [--checkout DIR ...]
    hx merge 1894 [--repo owner/name] [--dry-run] [gh pr merge flags ...]

`done` refuses unless a pull request whose title or branch names the key is
merged, none is still open, and Jira shows the ticket Done. Then it closes the
ticket's herdr workspace (or only its panes in a shared workspace), removes
its clean worktrees, runs `git worktree prune`, stops its scratch Postgres
clusters and containers, and moves a clean main checkout that sits on the
ticket's branch back to main by fast-forward. A live agent pane is skipped
unless `--force`, and never in a shared workspace. Every action is logged to
the cleanup log under the XDG state directory.

`merge` runs `gh pr merge` with the caller's flags, never adds `--admin` and
refuses it, and runs `done` for the pull request's key once GitHub reports
the pull request merged.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cleanup  # noqa: E402
from cleanup import CleanupError  # noqa: E402


class Host:
    """Everything `done` and `reap` read or change, in one swappable place."""

    def __init__(self, config, runner=cleanup.run, jira=None, github=None, procs=None):
        self.config = config
        self.run = runner
        self.jira = jira or cleanup.Jira.from_env(config)
        self.github = github or cleanup.GitHub(runner)
        self.procs = procs or cleanup.Procs()

    def repos(self, extra=()):
        found = list(extra)
        for checkout in self.config["checkouts"]:
            result = self.run(["git", "-C", checkout, "remote", "get-url", "origin"])
            slug = cleanup.repo_slug(result.stdout) if result.returncode == 0 else None
            if slug and slug not in found:
                found.append(slug)
        return found

    def scratch(self, path):
        return any(cleanup.inside(path, root) for root in self.config["scratch_roots"])


def verify(host, key, repos):
    """Return (pull requests, refusal reason or None)."""
    prs = []
    for repo in repos:
        prs += host.github.prs_for_key(repo, key)
    merged = [p for p in prs if p.get("state") == "MERGED"]
    still_open = [p for p in prs if p.get("state") == "OPEN"]
    if not merged:
        return prs, f"no merged pull request names {key} in {', '.join(repos) or 'any repo'}"
    if still_open:
        listed = ", ".join(f"{p['repo']}#{p['number']}" for p in still_open)
        return prs, f"{key} still has open pull request(s): {listed}"
    status = host.jira.status(key)
    if status is None:
        return prs, f"cannot read Jira status for {key} (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN)"
    if not cleanup.is_done(status, host.config["done_statuses"]):
        return prs, f"Jira shows {key} as {status[0]!r}, not Done"
    return prs, None


def plan_done(host, key, prs, force=False):
    plan = cleanup.Plan()
    pattern = cleanup.key_regex(key)
    branches = {p.get("headRefName") for p in prs if p.get("headRefName")}
    numbers = {str(p["number"]) for p in prs if p.get("state") == "MERGED"}

    def names_key(*texts):
        return any(t and pattern.search(t) for t in texts)

    # herdr
    try:
        spaces = cleanup.herdr_state(host.run)
    except CleanupError as exc:
        plan.notes.append(f"herdr unavailable: {exc}")
        spaces = []
    protected = set(host.config["protect_workspaces"])
    for space in spaces:
        matched = [p for p in space.panes if names_key(p.label)]
        if not matched and names_key(space.label):
            matched = list(space.panes)
        if matched:
            cleanup.workspace_actions(plan, space, matched, protected, allow_live=force)

    # worktrees and main checkouts
    cwds = host.procs.cwds()
    for checkout in host.config["checkouts"]:
        try:
            trees = cleanup.worktrees(checkout, host.run)
        except CleanupError as exc:
            plan.notes.append(str(exc))
            continue
        for tree in trees:
            if tree.main:
                if tree.branch and (names_key(tree.branch) or tree.branch in branches):
                    cleanup.checkout_actions(plan, checkout, host.config["main_branch"],
                                             f"main checkout on {key} branch {tree.branch}",
                                             host.run)
                continue
            if names_key(tree.path, tree.branch) or tree.branch in branches:
                cleanup.worktree_action(plan, checkout, tree, f"{key} worktree", cwds, host.run)
        plan.act("prune", checkout, ["git", "-C", checkout, "worktree", "prune"],
                 "drop metadata for deleted worktrees")

    # scratch databases
    for pg in host.procs.postmasters():
        if host.scratch(pg["datadir"]) and names_key(pg["datadir"]):
            cleanup.postgres_action(plan, pg, f"{key} scratch Postgres")
    boxes = cleanup.containers(host.run)
    if boxes is None:
        plan.notes.append("docker unavailable; containers not checked")
    for box in boxes or []:
        name = box.get("Names", "")
        scratch = cleanup.SCRATCH_CONTAINER.fullmatch(name)
        if names_key(name) or (scratch and scratch.group(1) in numbers):
            plan.act("container", name, ["docker", "stop", name], f"{key} scratch container")
    return plan


def done_main(argv=None, host=None, log=None):
    parser = argparse.ArgumentParser(prog="hx done", description="clean up after a finished ticket")
    parser.add_argument("key")
    parser.add_argument("--dry-run", action="store_true", help="print the actions only")
    parser.add_argument("--force", action="store_true",
                        help="also close a live single-pane ticket workspace")
    parser.add_argument("--checkout", action="append", default=[],
                        help="main checkout to scan; repeat (default: cleanup config)")
    parser.add_argument("--repo", action="append", default=[], help="extra owner/name to search")
    parser.add_argument("--config", help="cleanup config JSON")
    args = parser.parse_args(argv)
    try:
        key = cleanup.normalize_key(args.key)
        if host is None:
            host = Host(cleanup.load_config(args.config, checkouts=args.checkout))
        log = log or cleanup.Log(cleanup.state_dir() / "cleanup.log")
        if not host.config["checkouts"]:
            raise CleanupError("no main checkouts configured (--checkout, HX_CHECKOUTS or config)")
        prs, refusal = verify(host, key, host.repos(args.repo))
        merged = ", ".join(f"{p['repo']}#{p['number']}" for p in prs if p.get("state") == "MERGED")
        if refusal:
            log(f"done {key}: refused: {refusal}")
            return 3
        log(f"done {key}: verified merged ({merged}) and Done in Jira"
            + (" [dry run]" if args.dry_run else ""))
        plan = plan_done(host, key, prs, force=args.force)
        failures = cleanup.execute(plan, log, args.dry_run, host.run)
        log(f"done {key}: {len(plan.actions)} action(s), {len(plan.skipped)} skipped, "
            f"{failures} failed" + (" [dry run]" if args.dry_run else ""))
        return 1 if failures else 0
    except CleanupError as exc:
        print(f"hx done: {exc}", file=sys.stderr)
        return 2


def merge_main(argv=None, host=None, log=None, done=done_main):
    parser = argparse.ArgumentParser(
        prog="hx merge", description="gh pr merge, then hx done for the ticket")
    parser.add_argument("pr")
    parser.add_argument("--repo", "-R")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--checkout", action="append", default=[])
    args, gh_flags = parser.parse_known_args(argv)
    if any(flag == "--admin" or flag.startswith("--admin=") for flag in gh_flags):
        print("hx merge: refusing --admin; merge only what the gate allows", file=sys.stderr)
        return 2
    runner = host.run if host else cleanup.run
    log = log or cleanup.Log(cleanup.state_dir() / "cleanup.log")
    argv_gh = ["gh", "pr", "merge", args.pr] + (["-R", args.repo] if args.repo else []) + gh_flags
    if args.dry_run:
        log(f"would merge: {' '.join(argv_gh)}; then hx done for its ticket")
        return 0
    log(f"merge: {' '.join(argv_gh)}")
    result = runner(argv_gh)
    if result.returncode != 0:
        log(f"merge failed rc={result.returncode}: {(result.stderr or result.stdout).strip()[:300]}")
        return result.returncode
    github = host.github if host else cleanup.GitHub(runner)
    try:
        pr = github.pr_view(args.pr, args.repo)
    except CleanupError as exc:
        log(f"merged, but could not read the pull request back: {exc}")
        return 0
    if pr.get("state") != "MERGED":
        log(f"#{pr.get('number')} is {pr.get('state')} (auto-merge queued?); "
            "run hx done <KEY> after it lands")
        return 0
    keys = sorted(cleanup.find_keys(f"{pr.get('title', '')} {pr.get('headRefName', '')}"))
    if len(keys) != 1:
        log(f"merged #{pr.get('number')}; no single ticket key in its title or branch "
            f"({', '.join(keys) or 'none'}), so hx done was not run")
        return 0
    extra = ["--repo", args.repo] if args.repo else []
    for checkout in args.checkout:
        extra += ["--checkout", checkout]
    code = done([keys[0]] + extra, host=host, log=log)
    if code == 3:
        log(f"merged #{pr.get('number')}; hx done {keys[0]} will run once the ticket is Done "
            "(rerun it then, or the nightly reaper picks it up)")
        return 0
    return code


if __name__ == "__main__":
    command = sys.argv[1:2]
    if command == ["merge"]:
        raise SystemExit(merge_main(sys.argv[2:]))
    raise SystemExit(done_main(sys.argv[2:] if command == ["done"] else sys.argv[1:]))

<!--
  from factory-seed@UNSTAMPED

  The contract and the reasoning behind every section: docs/STORY-CONTRACT.md
  The checker that enforces it: scripts/dod-check.sh (CI job `dod`, every PR, no path filter)

  Do NOT delete a section. If it does not apply, say so in it — "Wiring required"
  has a mandatory fallback phrase for exactly this reason. A missing section is
  ambiguous between "nothing to say" and "never considered", and those two have
  very different failure modes.

  Run it locally before you push:
    gh pr view <n> --json body -q .body | scripts/dod-check.sh
-->

<!-- Your ticket key on its own line, e.g. ACME-123. Configured in .factory/ticket-prefixes. -->

## Summary — what changed and why

<!-- The WHY first. What was broken, what it looked like from the outside, and why it
     looked correct. If it merged green once already, say how. -->

## Wiring required

<!-- What does this change need in order to work that is NOT in this diff?
     Walk the list — do not answer from memory. Delete the lines that cannot apply
     to this repo and add the ones that do:

       [ ] env vars on the service's Deployment / process manager / .env
           (a boot-required var that is missing CrashLoops the pod on the NEXT deploy,
            not this one — which is why it merges green)
       [ ] secret-store entries — the store is the system of record and the sync is
           asynchronous, so create the secret BEFORE the deploy, not after
       [ ] network policy / security group / firewall peers — a default-deny floor
           drops the new call silently, and silence reads exactly like success
       [ ] authorization policy rows for new routes
       [ ] CI job — and check that its path filter, or its absence, is deliberate.
           A workflow file breaking is not a change to the service it builds, so a
           path-filtered guard skips the exact commit that breaks it
       [ ] manifest image tags (`:latest` makes a stale rollout report success)
       [ ] DB migration ordering
       [ ] a client change needed for the server change to be reachable at all

     Then WRITE THE ANSWER BELOW. This section is checked and must not be left
     empty — a heading with nothing under it is not an answer.

     If, having walked the list, the honest answer is that there is nothing, type
     the literal words

         no wiring required

     yourself. They are deliberately NOT pre-filled here: the phrase is checked,
     and typing it is an assertion that you looked. A template that types it for
     you turns the default answer into a claim nobody made. That is not
     hypothetical — the first cut of this template pre-filled the phrase, and
     every PR asserted it by default for as long as it stood. -->

## Prove it by breaking

<!-- A guard nobody watched fail is not verified. Remove or invert the check, watch
     the test go red, restore it, watch it go green. BOTH outputs go here, with
     their exit codes.

     Then check the break actually landed. A break-test whose edit did not apply is
     indistinguishable from a guard that does not work, and it looks like success. -->

**What I broke:**

**Red — with the guard removed:**

```
```

**Green — with the guard restored:**

```
```

## Verification

<!-- Exact commands with cache-defeating flags. `go test ./...` prints "ok (cached)"
     after a change that broke the package; that has hidden real failures. Never
     trust a pre-rebase result. -->

- [ ] test suite run with cache-defeating flags (`go test -count=1 ./...`), green per touched module
- [ ] linters / formatters clean
- [ ] rebased on latest `main` and re-run (not a pre-rebase result)
- [ ] manifests validated with a **server-side** dry run, if manifests changed
- [ ] running workload's image **digest** diffed, if this was deployed (`apply` saying
      `unchanged` means the old image is still serving)

```
```

## Not verified / left undone

<!-- Advisory, not machine-enforced — and the section reviewers should read first.
     Anything you could not run, could not reach, or deliberately scoped out. If the
     list is genuinely empty, say "nothing". A confident false success is the most
     dangerous thing this PR can contain. -->

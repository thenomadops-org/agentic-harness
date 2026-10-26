---
name: deploy-and-prove
description: Deploy a change and prove the running workload actually moved to it. Use whenever shipping to any environment, verifying a rollout, or investigating "it deployed but the fix isn't there". Covers resolving tags to digests before applying, asserting the running image digest changed, reading .imageID not .image, reconciling config mechanically, and writing the rollback before the deploy.
---

# An apply that reported success is not a deploy

`kubectl apply` answering `unchanged` and `kubectl rollout status` returning 0
are both compatible with **the old code still serving every request**. This is
the house failure — the stale artefact read as current state — and it has cost
more time here than any bug in any service.

The environment-specific script does not generalise. The mandate under it is
about six commands and does.

---

## The shape of the failure

Manifests pin a moving tag (`:latest`, `:main`, `:dev`). The image behind that
tag changed in the registry, but the **manifest text did not**, so:

1. `kubectl apply` compares YAML to YAML, sees no diff, prints `unchanged`;
2. no new ReplicaSet is created, no pod is replaced;
3. `rollout status` is asked about a Deployment that was never rolled, finds it
   already complete, and exits 0;
4. every signal is green and the old image is still serving.

`rollout status` returning 0 says a pod became ready. **It does not say it became
ready on your image.**

---

## The procedure

### 1. Resolve the tag to an immutable digest BEFORE applying

Ask the registry what that tag points at *right now*, and pin that digest into
the manifest. Everything downstream compares against this one value, so resolve
it once and keep it.

If nothing was rebuilt for this commit, say so and skip the digest assertion for
that workload rather than inventing an expectation — a manifest-only change has
no new digest to move to, and demanding one fails every YAML-only deploy. The
honest assertion for those workloads is the health half (step 5).

### 2. Record the running digest BEFORE

The "before" half of proving it moved. Without it you cannot distinguish "rolled
onto the new image" from "was already on it" from "never moved".

### 3. Read `.imageID`, not `.image`

**The named incident, 2026-08-13.** A deploy verifier matched
`containerStatuses[].image`. On containerd that field is a **bare config
digest** — `sha256:b2e3…` — with no registry name in it; the registry reference
lives in `.imageID` (`ghcr.io/org/svc@sha256:2d7d…`). The matcher therefore
matched nothing, reported every service as "no running pod reports an image",
and **a false verify rolled back 13 healthy deployments.**

The part that matters most: **the test fixtures had encoded the same wrong
assumption**, so the suite was 25/25 green and proved nothing. A fixture that
agrees with your code proves nothing — build fixtures from a real capture of the
real object.

```bash
kubectl get pods -o json | jq -r '
  .items[] | select(.metadata.name | startswith("<deployment>-"))
  | (.status.containerStatuses // [])[] | .imageID'
```

### 4. Apply, wait, then ASSERT the running digest is the one you resolved

Not "a rollout happened". Not "the pod is ready". The specific comparison:

> the digest running now == the digest I resolved in step 1

and if it is not, fail loudly and say **"the apply did not take — this is the
failure where the rollout succeeds and nothing was actually deployed."**

### 5. The health half, for workloads with no new image

- **Exactly one ReplicaSet has pods.** Two means a wedged rollout: the new pods
  never became ready, the old ones are still serving, and the Deployment reports
  progressing rather than failed.
- **Restart count did not CLIMB during this deploy.** `restartCount` is
  cumulative over a pod's life, so "must be zero" is unfair to a pod that did not
  move. Compare before against after.

### 6. Reconcile config mechanically — do not eyeball it

Every env var the code **reads** must be set by the manifest, and every var the
manifest **sets** should be read by something. A service that lost its database
URL came up healthy, passed both probes, and discarded every write.

That comparison is a parse and belongs in a script, not in this skill (Tier 2 of
the seed). Two things about building it, learned expensively:

- **Parse the language, do not regex it.** One project's version was a shell script
  twice; both matched text where they needed structure, both had the reported
  hole closed, and both times the next reviewer found a narrower hole of the same
  shape — `// the old call was getenv("ADMIN_URL")` counted as a live read, and
  once comments were stripped, the same text inside a backquoted string counted
  again. A real parser does not have a next case.
- **Never key an exemption on file:line.** It goes stale on any insertion above
  the site it names, and it goes stale silently.

### 7. No mock providers in a deployed environment

Secrets are verified **live at boot**, not at first use. A boot-required var that
is missing CrashLoops the pod on the *next* deploy, not this one — which is
exactly why the PR that omitted it merged green.

### 8. The rollback is written before the deploy, not after

Write down the exact command that puts the previous digest back, and the
observable that tells you it worked, **before** you apply. A rollback improvised
during an incident is a second change under time pressure.

---

## Verification lines for the PR body

```
resolved   ghcr.io/org/svc@sha256:2d7d…    (registry, before apply)
before     ghcr.io/org/svc@sha256:9a11…    (.imageID, running)
apply      configured
rollout    successfully rolled out
after      ghcr.io/org/svc@sha256:2d7d…    == resolved  ✓
replicasets-with-pods  1
restarts   3 -> 3
rollback   kubectl set image deploy/svc svc=ghcr.io/org/svc@sha256:9a11…
```

`apply` printing `unchanged` while `after == before` is **not** a successful
deploy; it is the failure, and it is the one that looks most like success.

---

## What to refuse

- Reporting a deploy from `apply` output alone.
- Reporting a deploy from `rollout status` alone.
- Comparing tags instead of digests. Tags move; that is the whole bug.
- Adding a workload to the deploy without adding it to the assertion loop — a
  workload nobody asserts on is one whose stale image nobody will notice.

Anything touching a persistent volume, a backup schedule, DNS, or production is
**not** covered by this skill. Stop and escalate with a named question — see
`docs/AGENT-GUARDRAILS.md`.

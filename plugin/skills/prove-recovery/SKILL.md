---
name: prove-recovery
description: Turn backups into evidence — restore into a scratch target, verify the restored data, and put every recovery path on a calendar. Use when setting up or auditing backups, adding a restore drill, answering "are we covered if X dies", or before any change that touches a data volume or backup schedule. Covers making the drill structurally unable to reach production and guarding that property in CI.
---

# A backup log is not evidence. A restore is.

A backup that has never been restored is a rumour. The job says "completed", the
dashboard is green, the object is in the bucket, and none of that is a statement
about whether the data comes back.

This skill is about the *disaster* path, which is where I fail: I harden the
common path and the disaster path rots. The check is the calendar.

---

## 1. The drill restores, and then asserts

Completing is not the assertion. The drill must restore into a scratch target and
then **verify a known thing is there**:

- a known **row** — a fixture written before the backup, read back after;
- a known **object** in object storage, byte-compared;
- a known **secret version**, resolved from the store;
- for a config/infra backup: the target rebuilt from source and **diffed** against
  what is running.

Assert the *content*, not the exit code of the restore command. A restore that
produced an empty database exits 0.

Record the **recovery point** too: how much data the drill actually lost between
the last backup and the simulated failure. "We can restore" and "we can restore to
within five minutes" are different promises, and only one of them is usually true.

---

## 2. The drill must be unable to touch production BY CONSTRUCTION

Not by care, not by a comment, not by a well-named variable.

**The named incident, one-project.** `pgbackrest restore` overwrites whatever
directory it is aimed at. the node was a single box, one disk, with production Postgres
has no replica — one wrong path destroys the only copy of member data. The drill
was therefore built so the mistake is *unreachable*: it **does not mount the
production volume at all**, so the live data directory does not exist inside the
pod. A wrong path in the drill cannot find production because production is not
in its filesystem.

That is the shape to copy: **remove the capability, do not police its use.**

- no mount of the production volume;
- credentials scoped to read the backup and write the scratch target only;
- a separate namespace/project/account where that is available;
- the scratch target named so it is obviously not production, and torn down after.

---

## 3. Guard the drill's own safety properties in CI — and DERIVE the workloads

**The property is invisible from the diff that breaks it.** Adding
`persistentVolumeClaim: <production-data>` to a drill pod reads like *making the
test more realistic*, and nothing else in a repo would object to it.

So the safety property gets its own check, and that check follows every rule in
`write-a-gate`:

- **Derive the set of drill workloads from the manifests**, never from a list in
  the guard. That project's drill went from one Job to a Job plus a weekly CronJob,
  which doubled the number of places the property had to hold. A hand-written
  list would have gone blind at exactly that moment, and silently. A second
  restore workload added next quarter must not be silently unchecked.
- **Zero drill workloads found is a failure**, not a pass.
- **Parse the manifests structurally.** A grep cannot tell which pod spec a
  volume belongs to.
- **No path filter.** The safety depends on the base manifests, the drill
  manifests *and* the kustomization (a patch can add the volume back), and it is
  exactly the change that touches none of those and breaks it that a path filter
  would skip. The guard takes seconds.
- **Prove it by breaking**: add the production volume to a drill pod in a scratch
  branch, watch the guard go red with its exit code, remove it, watch it go green.

---

## 4. Every recovery path is on a calendar, not on faith

List them, and give each an owner and an interval. The ones that get forgotten are
never the database:

| Path | Restored into | Interval |
|---|---|---|
| Database (full + point-in-time) | scratch volume | weekly |
| Object storage | scratch bucket | monthly |
| Secrets | scratch project, one known version | quarterly |
| Rebuild the cluster/infra from source | scratch project | quarterly |

A path with no date is a path that has not been tested. **An interval that has
been missed is a finding, not a scheduling problem** — surface it the same way a
red build is surfaced, or it is invisible by design.

---

## 5. Scope creep is the failure mode

A drill that grows into a staging refresh stops being a drill and becomes a
dependency: now it must not be disruptive, now it runs less often, now it is
tuned for speed rather than fidelity, and eventually it is skipped because
something depends on it being up.

Keep it: restore, assert, tear down. If someone wants a long-lived environment
from the same data, that is a second thing with a second name.

---

## 6. What is machine-enforced, and what is not

Put it in the honesty table in `docs/AGENT-GUARDRAILS.md`:

| Rule | Enforced by | Strength |
|---|---|---|
| The drill cannot mount production data | the drill guard, no path filter | machine |
| The drill actually ran this period | the schedule + an alert on absence | machine, if you alert on **absence** |
| The restored data was verified | the drill's own assertions | machine |
| Someone looked at the result | — | written down only |

**Alert on absence.** A drill that stopped running produces no failures, and no
failures is what success looks like. That is the same defect as every other one
in this building.

---

## The line that must never be crossed

Restoring over a live data directory, deleting a backup or a snapshot, changing a
backup schedule, or touching a production volume is **not** in scope for an agent
unattended. Stop and escalate with a named question — the ticket, the specific
irreversible act you declined, and a choice for the human. See
`docs/AGENT-GUARDRAILS.md`.

<!-- from factory-seed@UNSTAMPED -->

# `triage/` — detected anomalies, as problem statements

One file per breach, written by a detector rather than a person, using the same
[`../TEMPLATE.md`](../TEMPLATE.md) a human problem statement uses.

That shared format is the whole mechanism. An alert has no downstream: somebody
reads it, thinks "that was a bad Tuesday", and closes the tab — and afterwards
that outcome is indistinguishable from nobody having looked. An **intent** does
have a downstream: intent → spec/decision → story → PR, the same conveyor
everything else rides.

## The rules a machine-written intent obeys

- **It is a problem statement, not a diagnosis and not a plan.** It records what
  the numbers did and what would have to be true for that to matter. It does not
  say what to change. A confident diagnosis in a brief anchors the agent that
  reads it — on one project, at the right file and the wrong mechanism.
- **Its Provenance section names the detector, the command, and the input.** A
  number nobody can recompute a year later is a number nobody can check.
- **Its Constraints section says what the detector could NOT see.** Every
  measurement has an error term; the one nobody wrote down is the one that gets
  argued about.
- **"Could not measure" never writes a file here.** A detector that refused —
  no data, too little baseline — exits with its own distinct code and stays
  quiet. Writing "no anomaly" would be the single conflation that makes the
  whole apparatus worthless.

This directory ships empty on purpose. A seeded example would be read as a real
finding within the week.

# Glossary

The words this project uses on purpose. Where the spec, the code and conversation
disagree about one of them, this file is the tiebreak, and the disagreement is a
bug in whichever one is wrong.

## C

### Coordinator session

The one Claude session on a [node](#node) that works one [project](#project): it
holds the project's [project lease](#project-lease), pulls approved stories and
fans them out to subagents on its own node. See intent ruling 2 in
`docs/intent/portable-workforce.md`.

## H

### Hard law

A rule enforced mechanically by a hook rather than by an agent's judgement. An
agent acting on its own cannot break it; a direct [owner override](#owner-override)
can. The list is intent ruling 6.

## M

### Merge gate

The hard law that lets an agent merge a pull request to `main` only after council
review passed, QA verified on a model different from the builder's, and CI is
green, and never by the builder. See
`docs/decisions/0003-agents-merge-owner-promotes.md`.

## N

### Node

A machine enrolled in the board that runs the node client and hosts
[coordinator sessions](#coordinator-session).

## O

### Owner override

A direct instruction from the owner in conversation. It is carried out and
recorded as authorized, even where a [hard law](#hard-law) would stop an agent
acting alone.

## P

### Project

One repository's product, such as an app or a service, worked by the
[workforce](#workforce) and tracked as one board project. Its knowledge
(`CLAUDE.md`, intent, spec, `docs/memory/`) lives in its repository.

### Project lease

A board record that one [coordinator session](#coordinator-session) on one
[node](#node) is working a [project](#project). A second coordinator on the same
project is refused. It lapses when the heartbeat stops.

## R

### Ready for human test

A story's work merged to `main` and deployed to the project's
[staging](#staging), waiting for the owner to test it.

## S

### Staging

A project's pre-production environment, deployed by a merge to `main`. It is
where the owner tests, after the merge.

## W

### Workforce

The portable set of role agents, lifecycle skills, hooks and org lessons that
works every [project](#project). It lives in `plugin/` in this repository and is
installed on every [node](#node).

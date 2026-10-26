# Skills

Every skill an agent writes lives here, in the vault — never directly in
`~/.claude/skills/`, where it would be untracked, unsynced, and invisible to
this vault's history.

`install-org` symlinks each directory here into `~/.claude/skills/` and
verifies the links resolve. `lint_vault.py` fails on any installed skill that
is not a symlink pointing into this vault.

Editing a skill means editing the copy here. Both paths reach the same file;
only this one is in git.

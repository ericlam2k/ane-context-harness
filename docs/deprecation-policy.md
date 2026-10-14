# Deprecation policy

Current version: 0.2.0. This policy starts from this version.

## Scope

This policy covers anything a script or setup file might depend on:

- Keys in CLI stdout JSON (the named fields in command output).
- CLI flags (the `--options` you pass to commands).
- MCP tool shapes (the names and fields of tools offered to agents).
- Config keys (the named settings in config files).
- Budget profile names (the named token-budget presets).

## Warning rule: two minors before removal

A minor version is the middle number in `0.2.0` (here, `2`).
We announce a planned removal at least two minor versions ahead.

- The CHANGELOG entry names the old thing, the replacement, and the removal version.
- The CLI also prints a warning notice (to stderr, the error output channel)
  naming the same replacement, until removal happens.
- The old thing keeps working during the warning period.

Example: announced in 0.3.0, still works in 0.3.x and 0.4.x, removed in 0.5.0
at the earliest.

## What never breaks without a major version

A major version is the first number in `0.2.0` (here, `0` going to `1`).
These changes only happen in a new major version:

- Removing or renaming a top-level JSON key in CLI output.
- Removing a CLI flag.
- Removing or renaming an MCP tool or one of its fields.
- Removing a config key or budget profile name.

Additive changes (new keys, new flags, new optional fields) may arrive in any
minor version and do not break old setups.

## Security-exception fast path

If keeping the old thing open risks secrets leaking or unsafe behaviour,
we may shorten or skip the warning period. In that case we:

- Ship the fix immediately in a patch release (the last number in `0.2.0`).
- State clearly in the CHANGELOG what changed, why, and how to update.

## How removal is announced

- CHANGELOG lists the removal, the version it landed in, and the replacement.
- The CLI warning notice is removed along with the old thing.
- If no replacement exists, the CHANGELOG says so plainly.

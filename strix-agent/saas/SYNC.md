# Syncing this fork with upstream (usestrix/strix)

This fork (`maruthis/strix`, remote `origin`) tracks `usestrix/strix`
(remote `upstream`). The `upstream` remote's push URL is intentionally
disabled (`DISABLED_use_origin_for_pushes`) so pushes always go to `origin`,
never accidentally to the upstream project.

Check remotes:

```
git remote -v
```

If `upstream` is missing (fresh clone), add it once:

```
git remote add upstream https://github.com/usestrix/strix.git
git remote set-url --push upstream DISABLED_use_origin_for_pushes
```

## Pulling upstream changes into the fork

```
git fetch upstream
git checkout main
git merge upstream/main        # should be conflict-free as long as SaaS work stays under saas/
git push origin main
```

Because all SaaS-specific work lives under `saas/` (see `saas/README.md`),
`upstream/main` should never touch that path, so this merge is expected to
be fast-forward-able or trivially clean. If a conflict ever does appear
outside `saas/`, it means a task accidentally edited upstream engine code —
resolve by re-isolating that change into `saas/` rather than keeping the
edit in `strix/`.

## Checking drift

```
git log --oneline origin/main..upstream/main   # what upstream has that we don't
git log --oneline upstream/main..origin/main   # our fork-only commits (should mostly be saas/ work)
```

## Cadence

Sync upstream into the fork at the start of each new task phase (see
`TASKS.md` Phase 0), and whenever a phase's work is about to start that
depends on recent upstream engine changes (e.g. new agent tools/hooks the
SaaS backend needs to invoke).

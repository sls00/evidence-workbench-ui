# Nested git worktrees

Keep parallel checkouts **inside this repo**, not as siblings under `portfolio/`.

```bash
# from repo root
mkdir -p .worktrees
git fetch origin
git worktree add .worktrees/<short-name> -b <branch> origin/main

# when finished
git worktree remove .worktrees/<short-name>
git worktree prune
```

Examples:
- `.worktrees/slice-b`
- `.worktrees/deeplink`

Do **not** create `../<repo>-wt-*` directories in the portfolio root.

# Pushing the NazmOS visual redesign

Everything is committed on branch `feat/visual-redesign` (4 commits) and packaged in
`nazmos-visual-redesign.bundle` (a Git bundle — preserves full commit history).

## Option A — import the bundle and push (recommended)

Run these in your existing local clone of `RayAKaan/NazmOS` (on the `main` branch,
up to date at commit `9c6f4d5`):

```bash
# 1. Pull the commits out of the bundle into a local branch
git fetch nazmos-visual-redesign.bundle feat/visual-redesign:feat/visual-redesign

# 2. Look at what's coming in
git log --oneline main..feat/visual-redesign

# 3. Push it to GitHub
git push -u origin feat/visual-redesign
```

Then open a pull request: https://github.com/RayAKaan/NazmOS/compare/main...feat/visual-redesign

## Option B — merge straight into main locally

```bash
git fetch nazmos-visual-redesign.bundle feat/visual-redesign:feat/visual-redesign
git checkout main
git merge --no-ff feat/visual-redesign
git push origin main
```

## The 4 commits

| SHA | Message |
|---|---|
| `1564034` | feat(design-system): token diff — spacing/type/radius/motion/weave/elevation (v2 §2-3, v3 §A) |
| `af8a36e` | feat(ui): new primitives + reference /ui-kit route (v2 §3-4, v3 §B) |
| `0c514bd` | feat(pages): brand-forward + core product polish (v2 §5, v3 §C-D) |
| `47e6be5` | chore: icon sweep metadata images, favicon fix, remove dead landing code, docs |

> Note: the commit author is set to `NazmOS Design Agent <noreply@nazm.ai>` (a placeholder,
> since no identity was configured in the sandbox). To re-attribute before pushing, run:
> `git rebase -i --exec 'git commit --amend --reset-author --no-edit' main` on the branch
> once your real `user.name`/`user.email` are set, or just push as-is.

## Verification (already run, all green)

`npm run build` (37 routes, 0 errors) · `npm run lint` (0 errors) · `npm test` (9 passed) ·
backend `pytest` (374 passed; 2 Postgres-only RLS tests skip without a PG server).

# Contributing to pdlcflow

`pdlcflow` is in **Phase A — Foundations**. The scaffold is landing now; the per-phase implementation (B–I per [`STATUS.md`](./STATUS.md)) will accept contributions once the foundations stabilize.

## Code of conduct

Be kind. Be honest. Disagree on substance, not identity. Mistakes are how the team learns; gracelessness about them is how the team breaks.

## Issue first

Before opening a PR for anything larger than a typo, open an issue describing the change and the rationale. This keeps work coordinated across the parallel-track upstream (`pdlc-os/pdlc`) and reduces wasted effort.

## Local setup (intended shape — will land with the per-package commits)

```bash
# Python side
uv sync

# Node side
pnpm install

# Self-host smoke
cd infra/compose && docker compose up
```

## Commit messages

Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`). Body explains the *why*. Sign-offs and Co-Authored-By trailers welcome.

## Branching

- `main` is protected; PRs only.
- Branch names: `feat/<short-slug>`, `fix/<short-slug>`, `docs/<short-slug>`.

## License

By contributing, you agree your contributions are licensed under [MIT](./LICENSE).

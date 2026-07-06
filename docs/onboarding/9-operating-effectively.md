<!-- nav:top -->
[🏠 Onboarding](README.md) · [📚 Full Wiki](../wiki/README.md) · [🗺️ Visual journey](journey.html)

# 9 · Operating effectively

The habits that separate "it works" from "it works *well*." None of this is
required — but teams that internalize it get far more out of pdlcflow.

## Gate fluency — the core skill

The gates are the product. Treat them as real review, not speed bumps.

- **Read the artifact before you approve.** Every gate shows you a real
  document — a PRD, a design package, a REVIEW, a CHANGELOG. Skim it. The whole
  value of the methodology is that a human decides at each boundary.
- **You have three moves at every gate: approve, reject, edit.** Rejecting keeps
  you in place; **editing** amends the artifact before continuing. Use edit to
  correct a drifting draft rather than rejecting and re-running.
- **Approving resumes; it doesn't skip.** Nothing downstream runs until you
  approve — so a paused run is safe to leave for hours. Come back and it's
  exactly where you left it.
- **Know the eight (plus one).** `init_approve` (genesis) then, per feature:
  `discover_summary · prd_approve · design_docs_approve · beads_tasklist_approve
  · review_md_approve · merge_and_deploy_approve · smoke_signoff ·
  episode_approve`. Recognizing which gate you're at tells you what you're
  approving.

## Pick the right interaction mode

- **Sketch** — agents pre-draft every answer from context; you edit a whole
  round at once. Fast. Use it when you already know the answers (or brought a
  [spec](4-bringing-your-own-spec.md)).
- **Socratic** — one open question at a time, from scratch. Slower, deeper. Use
  it when the idea is genuinely fuzzy and you *want* Discover to pressure-test
  it (adversarial review, edge cases, a progressive-thinking party).

Wrong mode is a common early mistake: Socratic on a fully-specced feature feels
like busywork; Sketch on a vague idea rubber-stamps assumptions.

## Context discipline

Long runs accumulate a working log. Keep it lean:

- **`/compact`** distills a bloated `brainstorm_log` into one lossless summary
  entry and frees the context window. Reach for it when a run has gone many
  rounds.
- **`/pause`** checkpoints a feature; **`/resume`** picks it back up. Prefer this
  over leaving many features half-open.
- **One feature at a time per thread.** The roadmap-claim model expects a
  feature to be claimed, worked, and released. Use `/abandon` (keeps artifacts,
  releases the claim) to cleanly drop one you won't finish.

## Autonomy, used well

**`/night-shift`** collapses every gate to auto-approval behind one human
Contract Party gate — powerful, but only as good as what precedes it.

- **Only after Inception is solid.** Night-shift builds and ships an *approved
  plan*. Run `/brainstorm` (with real gate review) first; then let night-shift
  grind Build → Ship.
- **Trust the Sentinel, but know its limits.** It aborts on failed required
  smoke checks, a production-deploy attempt, and stagnation — but it can't
  rescue a bad plan. Garbage plan in, garbage feature out, just faster.
- **Production is still off-limits.** The three-layer ban holds under
  night-shift; it will refuse a production target, not "figure it out."

## Record decisions as you go

- **`/decide "<title>"`** appends an ADR-style entry to the Decision Registry
  (`DECISIONS.md`). Capture *why*, not just what — future-you and the Nexus
  timeline both benefit.
- **`/whatif "<scenario>"`** is a **read-only** hypothetical — architecture,
  scope, effort, risk — that changes nothing. Great for "should we…?" before
  committing a feature.
- **`/doctor`** gives a fast read-only health check of the active feature.

## Common pitfalls

| Trap | Reality |
|---|---|
| "The deploy URL looks fake." | If you haven't wired a deploy, `/ship` reports `"(simulated — no deploy performed)"` on purpose. Wire `PDLC_DEPLOY_CMD`/`PDLC_DEPLOY_WEBHOOK` for real deploys. See [8](8-shipping-and-release.md). |
| "The model output is generic/placeholder." | Until you wire a provider, the LLM is an **offline deterministic stub**. Re-run setup (or set `PDLC_WIRE_LLM` + a provider) for real output. |
| "Real tests/merge/deploy won't run." | The execution arc is **single-user self-host only** — enabled by `PDLC_ENABLE_EXECUTION` and **refused when auth is required**. It's off by default. |
| "It won't deploy to production." | By design — the three-layer prod-deploy ban. Production needs a human. |
| "Which compose stack?" | `deploy/` pulls prebuilt GHCR images (adopters); `infra/compose/` builds from source (contributors). Don't mix them. |
| "Did my migrate re-run duplicate data?" | No — events dedup on a deterministic id. Re-running `push`/`backfill` adds zero new events. |

## Watch the system

- **Nexus Console** (in the Studio) — the live event feed, features timeline,
  and roadmap/domain rollups. Non-empty from day one if you
  [migrated](5-bringing-your-own-roadmap.md).
- **`pdlcflow observability up`** — Grafana (`:3000`), the Streamlit Nexus
  dashboard (`:8501`), Prometheus (`:9090`) for traces + metrics.
- **`/health` and `/health/ready`** — liveness and readiness (db/redis) when you
  need to check the stack itself.

Depth: [wiki · Monitoring](../wiki/14-monitoring.md) ·
[wiki · Observability](../wiki/19-observability.md) ·
[wiki · Evals](../wiki/17-evals.md).

## A short operating creed

1. Let it pause — that's the feature, not a bug.
2. Read before you approve.
3. Match the mode to the certainty (Sketch when sure, Socratic when not).
4. Compact early, keep one feature per thread.
5. Automate only what Inception has already made sound.
6. Believe the honest no-ops — nothing here fakes success.

---
<!-- nav:bottom -->
◀ [8 · Shipping & release](8-shipping-and-release.md) · [🏠 Onboarding home](README.md) · [🗺️ Visual journey](journey.html) · [📚 Full Wiki](../wiki/README.md)

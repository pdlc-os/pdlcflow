<!-- nav:top -->
[📚 Full Wiki](../wiki/README.md) · [🗺️ Visual journey](journey.html)

# Onboarding pdlcflow

Welcome. **pdlcflow** turns the Product Development Lifecycle (PDLC) into a
self-hostable service: a LangGraph engine drives a feature through four phases —
**Initialization → Inception → Construction → Operation** — pausing at **9
human approval gates**, with a browser **Studio** UI, a **Nexus** analytics
console, and a multi-provider LLM layer. You can run the whole thing on your
laptop with **no API keys** (the LLM falls back to an offline deterministic
stub), then wire a real provider when you're ready.

This folder is the **fast on-ramp**. It gets a team from zero to shipping a
feature, then points you at the [full 20-page wiki](../wiki/README.md) for depth.

> New to the visual learner in you? Open **[journey.html](journey.html)** for a
> one-page map of everything below.

---

## Which doc, when

| You want to… | Read |
|---|---|
| Understand what pdlcflow is and get it running | **[2 · Getting started](2-getting-started.md)** — pick your road: greenfield 🌱 or brownfield 🏛️ |
| A literal "do this, then this" step list for setup | **[2a · Setup walkthrough](2a-setup-walkthrough.md)** |
| Go deeper than onboarding — learn the whole system | **[3 · Going deeper](3-going-deeper.md)** — a tiered route into the wiki |
| Build one feature you've **already specced** (you have a PRD/spec) | **[4 · Bringing your own spec](4-bringing-your-own-spec.md)** |
| Onboard an **existing app** that has its own roadmap/history | **[5 · Bringing your own roadmap](5-bringing-your-own-roadmap.md)** |
| Run the everyday **build a feature** loop | **[6 · Implementing a requirement](6-implementing-a-requirement.md)** |
| Fix a bug — fast patch, normal fix, or undo a bad ship | **[7 · Fixing a bug](7-fixing-a-bug.md)** |
| Understand how **deploys & releases** work (with or without your own infra) | **[8 · Shipping & release](8-shipping-and-release.md)** |
| Build good habits and avoid the common traps | **[9 · Operating effectively](9-operating-effectively.md)** |

## The 10-minute path

1. **[Get it running](2-getting-started.md)** — one install command, open the Studio at `http://localhost:8080`.
2. **Say hello to the loop** — in the Studio chat, type `/brainstorm dark mode` and watch it pause at the first approval gate.
3. **[Learn the loop](6-implementing-a-requirement.md)** — `/brainstorm → /build → /ship`, approving each gate.
4. **[Then go deeper](3-going-deeper.md)** when you're comfortable.

## Two mental models to hold

- **It's a chat that pauses.** You drive pdlcflow by typing slash-commands
  (`/brainstorm`, `/build`, `/ship`) in the Studio composer. The engine runs
  autonomously until it needs you — at a **gate** (approve an artifact) or a
  **question round** — then pauses and waits. Approving resumes it.
- **Nothing is faked.** When a real backend isn't wired, pdlcflow does an
  honest no-op and says so (e.g. a deploy with no configured target reports
  "simulated — no deploy performed", never a fake URL). You always know what
  actually happened.

---
<!-- nav:bottom -->
**Start here → [2 · Getting started](2-getting-started.md)** · [🗺️ Visual journey](journey.html) · [📚 Full Wiki](../wiki/README.md)

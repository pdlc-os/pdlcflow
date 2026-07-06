# cc-switch — Complete Functional Capability Inventory

> Research artifact — 2026-07-05. Source: deep scan of https://github.com/farion1231/cc-switch
> (README, `docs/user-manual/en/`, release notes v3.15.0–v3.16.5).
> Companion docs: [01-pdlcflow-current-state.md](01-pdlcflow-current-state.md),
> [02-gap-analysis.md](02-gap-analysis.md), [99-roadmap.md](99-roadmap.md).

## Summary

**cc-switch** (farion1231/cc-switch) is a cross-platform desktop GUI (Windows/macOS/Linux, built
with Tauri 2 + React) that acts as a unified control panel for managing configuration across
multiple AI coding CLIs/apps. Its core job: let a user switch the active "provider" (API endpoint
+ key + model config) for tools like Claude Code, Codex, and Gemini CLI with one click — from the
main window or the system tray — instead of hand-editing JSON/TOML/env files. It has grown well
beyond a switcher into a suite: a local proxy with failover, unified MCP server management,
skills/prompts management, usage & cost tracking, session history browsing, and cloud
sync/backup. It is Chinese-first (huge in the Chinese AI-relay-service community) but ships
English, Japanese, Traditional-Chinese, and German localization.

*Note on scale claims: the README's rendered stats (114k stars, 45+ releases) appear to be a
forward-dated/aspirational README in the repo. Numbers are from-source, not independently
verified.*

---

## 1. Managed Tools / Target CLIs (7 total)

Source: README "Supported Tools", release notes. It manages per-app config for:

| Tool | What cc-switch writes/manages for it |
|---|---|
| **Claude Code** | Provider endpoint + API key/auth token config; supports **hot-switch without terminal restart**; redesigned import flow (v3.15) |
| **Claude Desktop** | First-class managed surface (v3.15); third-party provider switching via the local proxy; native-login recovery preset; 1M-context model routing (`[1m]` suffix handling) |
| **Codex** (OpenAI Codex CLI) | Config + model catalog (`cc-switch-model-catalog.json`); Chat Completions vs Responses routing; model-mapping table; OAuth preservation; requires restart to switch |
| **Gemini CLI** | Provider config; model extraction from URI path; Vertex AI full-URL preservation |
| **OpenCode** | Config + session usage sync from local SQLite; Go subscription preset |
| **OpenClaw** | Config + workspace editor for `AGENTS.md` / `SOUL.md` |
| **Hermes (Agent)** | Config; respects `HERMES_HOME` on Windows |

Prompt-file sync targets: `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`.

---

## 2. Provider Management (core feature)

Source: README "Provider Management", user-manual §2.2.

- **50+ built-in provider presets** — one-click add without editing JSON/TOML/env. Includes AWS
  Bedrock, NVIDIA NIM, Vertex AI, and a large roster of Chinese/community relay gateways
  (PackyCode, DMXAPI, SiliconFlow, GLM/Zhipu Coding Plan, Kimi/Moonshot, Qwen, DeepSeek, MiniMax,
  Volcano DouBao/Ark, Xiaomi MiMo, Meituan LongCat, plus many partner relays — CherryIN,
  APINebula, AtlasCloud, ZetaAPI, TeamoRouter, NekoCode, Code0.ai, BytePlus, Baidu Qianfan, etc.).
- **One-click switch** of the active provider from main UI or tray; activation atomically
  rewrites the target tool's config file.
- **Searchable/sortable preset selector** with inline search (v3.16.3); **drag-and-drop**
  provider reordering.
- **Provider import/export**; **Deep Link import** via `ccswitch://` URL protocol (providers,
  MCP, prompts, skills).
- **Active-provider protection** — cannot delete the currently-active config; "minimal intrusion"
  design guarantees at least one working config remains even if app is uninstalled.
- **Role-based model mapping** (`sonnet`/`opus`/`haiku`) with a `supports1m` long-context flag
  (v3.15); provider cards show routing-support badges.
- **Universal / shared config**: a "Shared Config Snippet" passes common data between providers;
  switching auto-syncs universal config (plugins, env vars, themes propagate) while stripping
  credential keys (`*_API_KEY`, `*_AUTH_TOKEN`) from the shared portion (v3.16.5).
- Per-app **environment-variable management panel**.

---

## 3. Local Proxy, Failover & Routing

Source: README "Proxy & Failover", user-manual §4.1–4.3, release notes.

- **Local proxy service** the managed tools point at — start/stop/status monitoring.
- **Format conversion** between API specs (e.g. Anthropic ↔ OpenAI-compatible; correct
  `tool_choice` mapping; Chat Completions ↔ Responses envelope conversion). This is what lets
  DeepSeek/Kimi/GLM/MiniMax etc. be used inside Codex (v3.16.0).
- **Auto-failover with circuit breaker** — queued providers, health-status tracking, automatic
  fallback when the primary fails.
- **Provider health monitoring** — lightweight HTTP-reachability checks (v3.16.3).
- **Request rectifier** layer — fixes/normalizes requests (e.g. auto-disable `web_search` for
  incompatible gateways to avoid HTTP 400; text-model image fallback to `[Unsupported Image]`).
- **App-level takeover** — proxy can take over Claude, Codex, or Gemini independently; per-app
  serialized switching to avoid concurrent live-config corruption.
- Custom **request header/body override**, custom **User-Agent** and pooled HTTPS connection
  reuse; IPv6 listen support; zstd body decompression.

---

## 4. MCP (Model Context Protocol) Management

Source: README "MCP Management", user-manual §3.1.

- **Unified MCP panel** managing servers across Claude, Codex, Gemini, OpenCode, and Hermes from
  one place.
- **Bidirectional sync** with each tool's live MCP config.
- **Deep Link (`ccswitch://`) import** of MCP servers; server templates + custom JSON config;
  bind servers to specific apps.

---

## 5. Skills & Prompts

Source: README "Prompts & Skills", user-manual §3.2–3.3.

- **Skills**: one-click install from **GitHub repos or ZIP**; **skills.sh public registry
  search** (v3.16.0); custom repository management; deploy via **symlink or file-copy**;
  **SHA-256-based update detection** + batch updates; skill backups (keeps 20 most recent).
- **Prompts**: Markdown editor with cross-app sync; preset prompts with **smart backfill**
  (backfill protection for existing data) and activation switching; syncs
  `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`.

---

## 6. Usage / Cost Tracking & Analytics

Source: README "Usage & Cost Analytics", user-manual §2.5 & §4.4.

- Dashboard for **spending, request count, token usage**, with trend charts.
- **Detailed request logs** with audit trail (shows pricing model when it differs from response
  model).
- **Custom per-model pricing**; **models.dev batch pricing import** with search.
- **Balance / quota queries** per provider (with retry + "preserve last success" fallback) —
  including official subscription usage templates for Claude/Codex/Gemini and Coding-Plan queries
  (GLM, Volcano Ark, etc.).
- **Filter-driven "Hero" card**: date/provider/model filtering, cache-normalized token counts,
  cache-hit rates; real-time refresh via `usage-log-recorded` events.

---

## 7. Session Manager

Source: README "Session Management", user-manual §3.4.

- **Browse, search, resume, and delete conversation history** across supported session sources
  (Claude Code, Codex unified history, OpenCode).
- **Two-tier grouping** (supplier → project directory); session detail header shows source
  filename (tooltip/copy).
- **Conversation restoration**; OpenClaw workspace editor (`AGENTS.md`, `SOUL.md`) with Markdown
  preview.

---

## 8. Storage, Backup, Restore & Cloud Sync

Source: README "Storage & Synchronization".

- **SQLite database** `~/.cc-switch/cc-switch.db` (providers, MCP, prompts, skills); **atomic
  writes** to prevent config corruption; DB version-recovery screen if schema is newer than the
  app.
- `~/.cc-switch/settings.json` (device-level UI prefs); `~/.cc-switch/backups/` **auto-rotated,
  keeps 10 most recent**; `~/.cc-switch/skills/` (symlinked); `~/.cc-switch/skill-backups/`
  (20 most recent).
- **Cloud sync** to a custom config directory via Dropbox / OneDrive / iCloud / NAS / **WebDAV**,
  and **S3-compatible backends** (AWS S3, MinIO, Cloudflare R2, Alibaba OSS, Tencent COS, Huawei
  OBS presets — v3.16.2).
- Manual **import/export** of configs; Deep Link import/export via URL.

---

## 9. System Integration / UX

Source: README "User Interface & System Integration".

- **System tray** with per-app submenus showing current provider + usage summary and one-click
  quick-switch.
- **Themes**: Dark / Light / System.
- **Auto-launch** at login; **auto-updater**.
- **i18n**: Simplified Chinese, Traditional Chinese (zh-TW), English, Japanese, plus German
  README.
- **Managed CLI-tool lifecycle** (v3.16.0): install/update/upgrade the CLIs themselves, conflict
  diagnostics, source-aware detection across PATH locations & package managers; prefers official
  native installers, falls back to package managers. "About" page became a tool-management panel.
- Install methods: Windows MSI or **portable ZIP**; macOS `brew install --cask cc-switch` or DMG;
  Linux .deb/.rpm/AppImage/paru; Flatpak.

---

## 10. Newer capabilities from recent releases (not obvious in README)

- **v3.16.5**: native Responses-endpoint support for Chinese suppliers; Codex model-catalog
  generation; universal-config auto-sync on switch; two-tier session grouping; Claude Sonnet 5
  pricing/default; Linux Wayland recovery via `CC_SWITCH_GDK_BACKEND`.
- **v3.16.4**: upstream-format selector decoupled from routing; custom header/body proxy
  override; DB version-recovery screen; models.dev batch pricing import; native Windows ARM64
  builds; custom usage date ranges.
- **v3.16.3**: billing based on real upstream models; custom User-Agent; Codex unified session
  history w/ migration; global supplier/model usage filtering; searchable preset selector.
- **v3.16.2**: S3-compatible cloud sync; OpenCode session usage sync; official subscription usage
  templates; Codex `/v1/models` probe support; Codex Chat file/audio attachments.
- **v3.16.1**: Codex OAuth-preservation opt-in; per-app serialized switching; Codex hot-swap
  refinements.
- **v3.16.0**: Codex Chat Completions routing (unlocks DeepSeek/Kimi/GLM/MiniMax in Codex); 22
  Chat-routable Codex presets; managed CLI-tool lifecycle; zh-TW + German; skills.sh registry
  search; SHA-256 skill updates.
- **v3.15.0**: Claude Desktop as first-class managed surface; role-based model mapping w/ 1M
  flag; Copilot/Codex OAuth reuse; pooled HTTPS reuse; Vertex/Gemini URL-handling fixes.

---

## Source citations

- Main README (rendered + raw `README.md`): §Provider Management, MCP Management, Proxy &
  Failover, Prompts & Skills, Usage & Cost Analytics, Session Management, Storage &
  Synchronization, UI & System Integration.
- `docs/user-manual/en/README.md`: §2.2 Switch Provider, §2.5 Usage Query, §3.1 MCP, §3.2
  Prompts, §3.3 Skills, §3.4 Session Manager, §4.1 Proxy, §4.2 App Routing, §4.3 Failover, §4.4
  Usage Statistics, §1.5 Personalization.
- Releases page: tags v3.15.0, v3.16.0, v3.16.1, v3.16.2, v3.16.3, v3.16.4, v3.16.5.

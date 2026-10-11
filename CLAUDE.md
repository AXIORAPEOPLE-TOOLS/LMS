@AGENTS.md

Claude-specific notes:
- Keep `docs/` updated after every change (features tracker + changelog at minimum).
- Before every push to GitHub, run the full end-to-end suite (`cd test/e2e && pnpm test`), even if not asked; push only when it passes. Otherwise run e2e only when asked (backend tests + frontend lint/build per phase).
- No AI-looking UI: no "AI" labels, badges, sparkles or gradients.

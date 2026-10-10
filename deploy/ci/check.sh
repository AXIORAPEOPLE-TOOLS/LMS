#!/usr/bin/env bash
# Run the CI checks locally (same as .github/workflows/ci.yml, minus the PostgreSQL job).
#   bash deploy/ci/check.sh          # backend + frontend
#   bash deploy/ci/check.sh --e2e    # also the Playwright tests (run before pushing)
set -euo pipefail
cd "$(dirname "$0")/../.."

step() { printf '\n==> %s\n' "$1"; }

step "Backend: install"
uv sync --project backend --locked
step "Backend: ruff lint + format"
(cd backend && uv run ruff check app && uv run ruff format --check app)
step "Backend: tests"
uv run --project backend pytest test/backend
step "Docs: api.md and data-model.md up to date"
(cd backend && uv run python scripts/gen_docs.py)
git diff --exit-code -- docs/api.md docs/data-model.md || { echo "Docs were stale and have been regenerated: commit them."; exit 1; }

step "Frontend: lint + build"
(cd frontend && pnpm install --frozen-lockfile && pnpm lint && pnpm build)

if [[ "${1:-}" == "--e2e" ]]; then
  step "End-to-end"
  (cd test/e2e && pnpm install --frozen-lockfile && pnpm test)
fi

printf '\nAll checks passed.\n'

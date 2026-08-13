# Repository instructions

LingosAI has a FastAPI backend in `backend/`, a Next.js frontend in `frontend/`, and local PostgreSQL/Redis support in `docker-compose.yml`. Read [`CLAUDE.md`](./CLAUDE.md) for architecture and coding conventions.

## Commands

Run backend checks from `backend/`:

```bash
uv sync --frozen
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy app
uv run python -m pytest tests/unit -q
uv run python -m pytest tests/integration -q
uv run python scripts/export_openapi.py
git diff --exit-code -- openapi.json
```

Run frontend checks from `frontend/`:

```bash
npm ci
npm run lint
npx tsc --noEmit
npm test
npm run test:coverage
npm run build
```

Run local infrastructure from the repository root with `docker compose up -d`.

## Migration boundaries

- Work only on a branch and through a reviewed PR. Never push directly to or merge `main`.
- The AWS deployment workflow is recovery history. AWS resources, code, credentials, and data remain recovery evidence until the owner explicitly approves removal.
- Do not access or mutate Azure or AWS unless the task and owner explicitly authorize it. Never run `terraform apply`, `terraform destroy`, imports, or state mutations without explicit approval.
- Never change DNS, Azure subscription settings, GitHub secrets/environments, OAuth callbacks, payment webhooks, or production data without explicit approval.
- Never reveal or commit credentials, Terraform state/plans, database dumps, `.env` files, or other secrets.
- Azure work is limited to the architecture in [`docs/AZURE_ZERO_COST_MIGRATION.md`](./docs/AZURE_ZERO_COST_MIGRATION.md): one eligible `Standard_B2ats_v2` VM, one P6 OS disk, one static public IPv4, one `Standard_B1ms` PostgreSQL server with exactly 32 GiB and HA/autogrow/geo-backup disabled, Hot LRS Blob storage, one Standard ACR, one Standard Key Vault, and Vercel for the Phase 1 frontend. The region is not yet approved; Central India is only a candidate. Do not add Azure infrastructure until its dedicated, approved work package.
- Follow the staged gates and stop conditions in [`docs/AZURE_AGENT_MIGRATION_PLAYBOOK.md`](./docs/AZURE_AGENT_MIGRATION_PLAYBOOK.md). Ask before any destructive, external, cost-bearing, production, or scope-expanding action.

## Authorship and DCO

All commits and pull requests must be authored only as `Orbin Sunny <91816511+orbin123@users.noreply.github.com>`. Sign every commit with `git commit -s`. The only permitted trailer is `Signed-off-by: Orbin Sunny <91816511+orbin123@users.noreply.github.com>`; never add `Co-Authored-By` or AI/tool attribution.

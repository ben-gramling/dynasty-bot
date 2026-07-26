# Sync all workspace deps
sync:
    uv sync --all-packages

# Run the collector locally
collect:
    cd apps/collector && uv run python -m app

# Test a specific package
test pkg:
    cd {{pkg}} && uv run pytest

# Test everything
test-all:
    uv run pytest libs/core/tests/

# Run the web app locally
web:
    cd apps/web && npm run dev

# Plan infra for a stack
plan stack:
    cd infra/stacks/{{stack}} && terraform plan

# Deploy infra for a stack
deploy stack:
    cd infra/stacks/{{stack}} && terraform apply

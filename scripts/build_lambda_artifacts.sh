#!/usr/bin/env bash
# Build the collector Lambda deploy artifacts into dist/ (gitignored):
#
#   dist/collector.zip  — the `app` package at the zip root (entries app/*.py),
#                         so the configured handler string "app.lambda_handler"
#                         resolves: Lambda imports the `app` package, whose
#                         __init__.py re-exports lambda_handler from app/app.py.
#   dist/layer.zip      — python/ tree with the built `core` wheel + its runtime
#                         deps (httpx, pymongo[aws], python-dotenv), resolved
#                         FOR LINUX x86_64 / CPython 3.12 via
#                         `uv pip install --python-platform x86_64-manylinux2014
#                          --python 3.12 --only-binary=:all:`.
#                         pymongo ships C extensions — a layer built for the
#                         wrong platform crashes at import inside Lambda.
#
# CI uploads these to s3://tomato-artifact-bucket/dynasty-bot/functions/collector.zip
# and s3://tomato-artifact-bucket/dynasty-bot/layer/layer.zip BEFORE
# `terraform apply` (the collector stack reads the S3 ETags as source_code_hash).
#
# Zips are written with python3.12's zipfile module (no `zip` binary needed).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$REPO_ROOT/dist"
PY=python3.12

command -v "$PY" >/dev/null || { echo "error: $PY not found" >&2; exit 1; }
command -v uv >/dev/null || { echo "error: uv not found" >&2; exit 1; }

rm -rf "$DIST/layer" "$DIST/wheels" "$DIST/function-check" \
  "$DIST/collector.zip" "$DIST/layer.zip"
mkdir -p "$DIST"

echo "==> building dist/collector.zip (app package at zip root)"
(cd "$REPO_ROOT/apps/collector" && "$PY" - "$DIST/collector.zip" <<'PYEOF'
import pathlib, sys, zipfile

out = sys.argv[1]
files = sorted(pathlib.Path("app").glob("*.py"))
assert files, "no app/*.py files found - run from apps/collector"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in files:
        zf.write(path, path.as_posix())
print(f"    wrote {out}: {[f.as_posix() for f in files]}")
PYEOF
)

echo "==> building core wheel"
uv build "$REPO_ROOT/libs/core" --out-dir "$DIST/wheels" --quiet

echo "==> resolving layer site-packages for x86_64-manylinux2014 / cp312"
uv pip install \
  --target "$DIST/layer/python" \
  --python-platform x86_64-manylinux2014 \
  --python 3.12 \
  --only-binary=:all: \
  --quiet \
  "$DIST/wheels"/core-*.whl

echo "==> building dist/layer.zip"
(cd "$DIST/layer" && "$PY" - "$DIST/layer.zip" <<'PYEOF'
import os, pathlib, sys, zipfile

out = sys.argv[1]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(pathlib.Path("python").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            zf.write(path, path.as_posix())
print(f"    wrote {out}")
PYEOF
)

echo "==> smoke test: layer imports on this host (Linux x86_64, matches target)"
PYTHONPATH="$DIST/layer/python" "$PY" -c "import pymongo, httpx, core; print('layer imports ok')"

echo "==> smoke test: handler string app.lambda_handler resolves against the zips"
mkdir -p "$DIST/function-check"
"$PY" -c "import zipfile; zipfile.ZipFile('$DIST/collector.zip').extractall('$DIST/function-check')"
PYTHONPATH="$DIST/layer/python:$DIST/function-check" "$PY" - <<'PYEOF'
import app

assert callable(app.lambda_handler), "app.lambda_handler is not callable"
print("handler resolves ok")
PYEOF

echo "==> artifact sizes"
ls -lh "$DIST/collector.zip" "$DIST/layer.zip"
du -sh "$DIST/layer/python"

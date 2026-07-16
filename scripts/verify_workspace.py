#!/usr/bin/env python3
"""NazmOS no-DB workspace verification.

Run from repo root after installing backend/frontend dependencies. This catches the
production-pilot regressions we can test without Postgres/Redis/Celery.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("\n$", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd or ROOT), text=True)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def python_check() -> None:
    script = r'''
import re
from pathlib import Path
from app.main import app
from app.services.schema_detector import SchemaDetector
from app.services.data_normalizer import normalize_dataframe
import pandas as pd
schema = app.openapi()
paths = schema['paths']
assert not [p for p in paths if '/api/v1/api/v1' in p]
# frontend contract
root = Path('..')
compiled=[]
for p in paths:
    compiled.append((p,re.compile('^'+re.sub(r'\\\{[^}]+\\\}', r'[^/]+', re.escape(p))+'$')))
missing=[]; calls=0
for f in (root/'frontend/src').rglob('*'):
    if f.suffix not in {'.ts','.tsx'}: continue
    text=f.read_text(errors='ignore')
    for m in re.finditer(r'api\.(get|post|put|patch|delete)\(\s*([`\"])(.*?)(\2)', text, flags=re.S):
        method=m.group(1).upper(); raw=m.group(3).replace('\n','')
        if raw.startswith('http'): continue
        path=raw.split('?')[0]
        path=re.sub(r'\$\{[^}]+\}', 'X', path)
        full=path if path.startswith('/api/v1') else '/api/v1'+path
        calls += 1
        if not any(rx.match(full) and method.lower() in paths[p] for p,rx in compiled):
            missing.append((str(f), method, raw, full))
assert calls >= 1
assert missing == [], missing
# schema smoke
sales = pd.DataFrame({'Date':['2026-07-01'], 'Product':['Coffee Beans 250g'], 'Qty':[2], 'Total':['SAR 50'], 'Cost':['15']})
d = SchemaDetector().detect(sales)
assert d['suggested_file_kind'] == 'sales_history'
assert d['detected_columns']['Date'] == 'transaction_at'
assert d['detected_columns']['Qty'] == 'quantity'
assert d['detected_columns']['Cost'] == 'cost_price'
normalized = normalize_dataframe(sales, d['detected_columns'])
assert float(normalized.iloc[0]['unit_price']) == 25.0
print('python contract checks OK')
'''
    run([sys.executable, "-c", script], cwd=ROOT / "backend")


def main() -> None:
    run([sys.executable, "-m", "compileall", "-q", "app", "tests"], cwd=ROOT / "backend")
    run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT / "backend")
    run([sys.executable, "-m", "alembic", "heads"], cwd=ROOT / "backend")
    python_check()
    run(["npm", "run", "lint"], cwd=ROOT / "frontend")
    run(["npm", "run", "build"], cwd=ROOT / "frontend")
    run(["npm", "audit", "--audit-level=moderate", "--omit=dev"], cwd=ROOT / "frontend")
    print("\nNazmOS workspace verification passed.")


if __name__ == "__main__":
    main()

"""Check staged upload contents without displaying secret values or customer data."""
import json
import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values


def main():
    root = Path(__file__).resolve().parents[1]
    staged = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z', '--diff-filter=ACMR'], cwd=root).decode('utf-8').split('\0')
    files = [path for path in staged if path]
    if not files:
        raise SystemExit('No staged files to inspect')
    local_config = dotenv_values(root / '.env')
    secrets = [str(value) for name, value in local_config.items()
               if value and len(str(value)) >= 8 and any(word in name for word in ('KEY', 'PASSWORD', 'TOKEN', 'SECRET'))]
    forbidden_parts = {'.venv', 'node_modules', '__pycache__', 'artifacts', 'logs', '.build-tmp', '_runtime', '_downloads'}
    failures = []
    total = 0
    for path in files:
        parts = Path(path).parts
        if forbidden_parts.intersection(parts) or (Path(path).name.startswith('.env') and Path(path).name != '.env.example'):
            failures.append({'file': path, 'reason': 'Local configuration or runtime file'})
            continue
        data = subprocess.check_output(['git', 'show', ':' + path], cwd=root)
        total += len(data)
        if len(data) > 20 * 1024 * 1024:
            failures.append({'file': path, 'reason': 'Unexpected large file'})
        if any(value.encode() in data for value in secrets):
            failures.append({'file': path, 'reason': 'Contains a real configured credential'})
        if path.endswith('.sql') and re.search(rb'INSERT\s+INTO\s+`?(orders|order_items|users|members|coupons|shopping_cart)`?\s', data, re.I):
            failures.append({'file': path, 'reason': 'Contains private business record inserts'})
    report = {'passed':not failures, 'staged_files':len(files), 'upload_bytes':total,'failures':failures}
    print(json.dumps(report, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

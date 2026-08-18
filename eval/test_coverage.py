#!/usr/bin/env python3
import json
import re
import subprocess
import sys

r = subprocess.run(['uv', 'run', 'pytest', '--cov=src/minimal_agora', '--cov-report=term', '-q'], capture_output=True, text=True, check=False)
m = re.search(r'TOTAL\s+\d+\s+\d+\s+(\d+)%', r.stdout)
pct = int(m.group(1)) / 100 if m else 0.0
json.dump({
    'score': pct,
    'passed': r.returncode == 0,
    'details': f'coverage={pct:.0%}'
}, sys.stdout)

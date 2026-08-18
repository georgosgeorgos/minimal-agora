#!/usr/bin/env python3
import json
import subprocess
import sys

r = subprocess.run(['uv', 'run', 'pytest', 'tests/', '-v'], capture_output=True, text=True, check=False)
json.dump({
    'score': 1.0 if r.returncode == 0 else 0.0,
    'passed': r.returncode == 0,
    'details': r.stdout[-200:] if r.stdout else r.stderr[-200:]
}, sys.stdout)

# Adversarial QA Report

- **timestamp:** 2026-08-18
- **feature:** Conditional wildcards with state-dependent trigger conditions (H2, Issue #34)
- **project type:** Library (Python simulation engine)
- **tester stance:** Skeptical — burden of proof on the builder

---

## Smoke Test

**Command:**
```
uv run pytest tests/ -v
```

**Output:**
```
85 passed in 0.62s
```

**Lint:**
```
uv run ruff check src/ tests/
All checks passed!
```

**Status:** PASS — all 85 tests pass, lint clean.

---

## Acceptance Criteria Verification

### AC1: ConditionOperator enum with gt, lt, eq, gte, lte

**Status:** VERIFIED

```
$ uv run python -c "
from minimal_agora.models import ConditionOperator
assert ConditionOperator.GT == 'gt'
assert ConditionOperator.LT == 'lt'
assert ConditionOperator.EQ == 'eq'
assert ConditionOperator.GTE == 'gte'
assert ConditionOperator.LTE == 'lte'
"
```

All assertions pass.

---

### AC2: TriggerCondition model with field, operator, threshold

**Status:** VERIFIED

```
$ uv run python -c "
from minimal_agora.models import ConditionOperator, TriggerCondition
cond = TriggerCondition(field='population', operator=ConditionOperator.GT, threshold=1000.0)
assert cond.field == 'population'
assert cond.operator == ConditionOperator.GT
assert cond.threshold == 1000.0
# From dict (YAML parsing path)
cond2 = TriggerCondition.model_validate({'field': 'economy.gdp', 'operator': 'lt', 'threshold': 50.0})
assert cond2.operator == ConditionOperator.LT
"
```

---

### AC3: Optional trigger_conditions on WildcardEvent (backward compatible)

**Status:** VERIFIED

```
$ uv run python -c "
from minimal_agora.models import WildcardEvent
# Old-style
e1 = WildcardEvent(name='old', probability=0.3)
assert e1.trigger_conditions == []
# From dict without conditions
e2 = WildcardEvent.model_validate({'name': 'dict', 'probability': 0.5, 'state_impact': {'a': 1}})
assert e2.trigger_conditions == []
# With conditions
e3 = WildcardEvent.model_validate({
    'name': 'cond', 'probability': 0.5,
    'trigger_conditions': [{'field': 'pop', 'operator': 'gt', 'threshold': 1000}]
})
assert len(e3.trigger_conditions) == 1
# JSON roundtrip
restored = WildcardEvent.model_validate_json(e3.model_dump_json())
assert restored.trigger_conditions[0].threshold == 1000
"
```

---

### AC4: evaluate_trigger_conditions — empty conditions

**Status:** VERIFIED

```
$ uv run python -c "
from minimal_agora.board import evaluate_trigger_conditions
assert evaluate_trigger_conditions([], {}) is True
assert evaluate_trigger_conditions([], {'a': 1}) is True
print('Empty conditions = unconditional pass')
"
Empty conditions = unconditional pass
```

---

### AC5: evaluate_trigger_conditions — missing fields

**Status:** VERIFIED

```
$ uv run python -c "
from minimal_agora.board import evaluate_trigger_conditions
from minimal_agora.models import ConditionOperator, TriggerCondition
cond = [TriggerCondition(field='nonexistent', operator=ConditionOperator.GT, threshold=0)]
assert evaluate_trigger_conditions(cond, {'other': 5}) is False
# Missing nested
cond2 = [TriggerCondition(field='a.b.c', operator=ConditionOperator.GT, threshold=0)]
assert evaluate_trigger_conditions(cond2, {'a': {'x': 1}}) is False
# Partial path (leaf not dict)
cond3 = [TriggerCondition(field='a.b.c', operator=ConditionOperator.GT, threshold=0)]
assert evaluate_trigger_conditions(cond3, {'a': {'b': 5}}) is False
print('All missing field cases return False')
"
All missing field cases return False
```

---

### AC6: evaluate_trigger_conditions — non-numeric fields

**Status:** VERIFIED

```
$ uv run python -c "
from minimal_agora.board import evaluate_trigger_conditions
from minimal_agora.models import ConditionOperator, TriggerCondition
cond = [TriggerCondition(field='status', operator=ConditionOperator.GT, threshold=0)]
assert evaluate_trigger_conditions(cond, {'status': 'active'}) is False   # string
assert evaluate_trigger_conditions(cond, {'status': None}) is False       # None
assert evaluate_trigger_conditions(cond, {'status': [1,2,3]}) is False    # list
assert evaluate_trigger_conditions(cond, {'status': {'n': 1}}) is False   # dict
print('All non-numeric types return False')
print('NOTE: bool passes isinstance(v, (int,float)) — True=1, False=0')
assert evaluate_trigger_conditions(cond, {'status': True}) is True  # bool is int subclass
"
All non-numeric types return False
NOTE: bool passes isinstance(v, (int,float)) — True=1, False=0
```

---

### AC7: All operators with boundary values

**Status:** VERIFIED

```
$ uv run python -c "
from minimal_agora.board import evaluate_trigger_conditions
from minimal_agora.models import ConditionOperator as Op, TriggerCondition as TC
def c(op, t): return [TC(field='v', operator=op, threshold=t)]

# GT boundary
assert evaluate_trigger_conditions(c(Op.GT, 100), {'v': 100}) is False
assert evaluate_trigger_conditions(c(Op.GT, 100), {'v': 100.0001}) is True
assert evaluate_trigger_conditions(c(Op.GT, 100), {'v': 99.9999}) is False

# LT boundary
assert evaluate_trigger_conditions(c(Op.LT, 100), {'v': 100}) is False
assert evaluate_trigger_conditions(c(Op.LT, 100), {'v': 99.9999}) is True
assert evaluate_trigger_conditions(c(Op.LT, 100), {'v': 100.0001}) is False

# EQ boundary
assert evaluate_trigger_conditions(c(Op.EQ, 5.0), {'v': 5}) is True
assert evaluate_trigger_conditions(c(Op.EQ, 5.0), {'v': 5.0}) is True
assert evaluate_trigger_conditions(c(Op.EQ, 5.0), {'v': 5.0000001}) is False

# GTE boundary
assert evaluate_trigger_conditions(c(Op.GTE, 100), {'v': 100}) is True
assert evaluate_trigger_conditions(c(Op.GTE, 100), {'v': 99}) is False
assert evaluate_trigger_conditions(c(Op.GTE, 100), {'v': 101}) is True

# LTE boundary
assert evaluate_trigger_conditions(c(Op.LTE, 100), {'v': 100}) is True
assert evaluate_trigger_conditions(c(Op.LTE, 100), {'v': 101}) is False
assert evaluate_trigger_conditions(c(Op.LTE, 100), {'v': 99}) is True
print('All 15 boundary assertions pass')
"
All 15 boundary assertions pass
```

---

### AC8: Nested dot-path fields

**Status:** VERIFIED

```
$ uv run python -c "
from minimal_agora.board import evaluate_trigger_conditions
from minimal_agora.models import ConditionOperator as Op, TriggerCondition as TC
# 1 level
assert evaluate_trigger_conditions([TC(field='economy', operator=Op.GT, threshold=50)], {'economy': 100}) is True
# 2 levels
assert evaluate_trigger_conditions([TC(field='economy.gdp', operator=Op.GT, threshold=50)], {'economy': {'gdp': 100}}) is True
# 3 levels (pandemic scenario pattern)
assert evaluate_trigger_conditions(
    [TC(field='regions.americas.social_cohesion', operator=Op.LT, threshold=50)],
    {'regions': {'americas': {'social_cohesion': 30}}}
) is True
print('1, 2, 3 level nesting all work')
"
1, 2, 3 level nesting all work
```

---

### AC9: Multiple conditions — AND semantics

**Status:** VERIFIED

```
$ uv run python -c "
from minimal_agora.board import evaluate_trigger_conditions
from minimal_agora.models import ConditionOperator as Op, TriggerCondition as TC
conds = [
    TC(field='pop', operator=Op.GT, threshold=100),
    TC(field='density', operator=Op.GT, threshold=50),
    TC(field='temp', operator=Op.LT, threshold=40),
]
assert evaluate_trigger_conditions(conds, {'pop': 200, 'density': 80, 'temp': 30}) is True   # all met
assert evaluate_trigger_conditions(conds, {'pop': 50, 'density': 80, 'temp': 30}) is False    # 1st fails
assert evaluate_trigger_conditions(conds, {'pop': 200, 'density': 30, 'temp': 30}) is False   # 2nd fails
assert evaluate_trigger_conditions(conds, {'pop': 200, 'density': 80, 'temp': 50}) is False   # 3rd fails
assert evaluate_trigger_conditions(conds, {'pop': 50, 'density': 30, 'temp': 50}) is False    # all fail
print('AND semantics: all 5 scenarios correct')
"
AND semantics: all 5 scenarios correct
```

---

### AC10: _roll_wildcard integration — conditions gate probability

**Status:** VERIFIED

```
$ uv run python -c "
import random
from minimal_agora.loop import _roll_wildcard
from minimal_agora.models import ConditionOperator as Op, TriggerCondition as TC, WildcardEvent as WE

# High prob but condition NOT met → None
e = [WE(name='guarded', probability=100.0, trigger_conditions=[TC(field='x', operator=Op.GT, threshold=1000)])]
random.seed(0)
assert _roll_wildcard(e, max_steps=1, state={'x': 500}) is None

# Condition MET → fires
random.seed(0)
r = _roll_wildcard(e, max_steps=1, state={'x': 2000})
assert r is not None and r.name == 'guarded'

# No state → conditional skipped
assert _roll_wildcard(e, max_steps=1, state=None) is None

# Mixed: conditional blocked, unconditional fires
mixed = [
    WE(name='blocked', probability=100.0, trigger_conditions=[TC(field='x', operator=Op.GT, threshold=9999)]),
    WE(name='uncond', probability=100.0),
]
random.seed(0)
r2 = _roll_wildcard(mixed, max_steps=1, state={'x': 100})
assert r2 is not None and r2.name == 'uncond'

# Two conditionals: first blocked, second passes
two = [
    WE(name='blocked_a', probability=100.0, trigger_conditions=[TC(field='a', operator=Op.GT, threshold=100)]),
    WE(name='passes_b', probability=100.0, trigger_conditions=[TC(field='b', operator=Op.GT, threshold=10)]),
]
random.seed(0)
r3 = _roll_wildcard(two, max_steps=1, state={'a': 50, 'b': 20})
assert r3 is not None and r3.name == 'passes_b'
print('All 5 integration scenarios pass')
"
All 5 integration scenarios pass
```

---

### AC11: Pandemic scenario YAML loads with conditions

**Status:** VERIFIED

```
$ uv run python -c "
from pathlib import Path
from minimal_agora.scenario import load_scenario
from minimal_agora.models import ConditionOperator
s = load_scenario(Path('scenarios/examples/pandemic.yaml'))
assert len(s.wildcards) == 3
ss = next(w for w in s.wildcards if w.name == 'super_spreader_event')
assert ss.trigger_conditions[0].field == 'disease.transmissibility'
assert ss.trigger_conditions[0].operator == ConditionOperator.GTE
assert ss.trigger_conditions[0].threshold == 0.5
mis = next(w for w in s.wildcards if w.name == 'misinformation_wave')
assert mis.trigger_conditions[0].field == 'regions.americas.social_cohesion'
assert mis.trigger_conditions[0].operator == ConditionOperator.LT
mut = next(w for w in s.wildcards if w.name == 'mutation')
assert len(mut.trigger_conditions) == 0
print('3 wildcards: 2 conditional, 1 unconditional')
"
3 wildcards: 2 conditional, 1 unconditional
```

---

### AC12: All existing scenarios still load (backward compatibility)

**Status:** VERIFIED

```
$ uv run python -c "
from pathlib import Path
from minimal_agora.scenario import load_scenario
for f in sorted(Path('scenarios/examples').glob('*.yaml')):
    s = load_scenario(f)
    wc = len(s.wildcards)
    cc = sum(len(w.trigger_conditions) for w in s.wildcards)
    print(f'{f.stem}: {wc} wildcards, {cc} conditions')
"
capitalism: 4 wildcards, 0 conditions
complexity: 0 wildcards, 0 conditions
democracy: 4 wildcards, 0 conditions
intelligence: 6 wildcards, 0 conditions
market: 3 wildcards, 0 conditions
mediterranean: 4 wildcards, 0 conditions
nuclear_war: 5 wildcards, 0 conditions
pandemic: 3 wildcards, 2 conditions
```

All 8 scenarios load. Only pandemic uses the new feature.

---

### AC13: Pydantic validation rejects invalid inputs

**Status:** VERIFIED

```
$ uv run python -c "
from pydantic import ValidationError
from minimal_agora.models import TriggerCondition, ConditionOperator, WildcardEvent
errors = 0
for label, fn in [
    ('invalid operator', lambda: TriggerCondition(field='x', operator='invalid', threshold=0)),
    ('missing threshold', lambda: TriggerCondition(field='x', operator=ConditionOperator.GT)),
    ('missing field', lambda: TriggerCondition(operator=ConditionOperator.GT, threshold=0)),
    ('extra field', lambda: TriggerCondition(field='x', operator=ConditionOperator.GT, threshold=0, extra='bad')),
    ('string for list', lambda: WildcardEvent(name='t', probability=0.5, trigger_conditions='not_a_list')),
    ('incomplete in list', lambda: WildcardEvent(name='t', probability=0.5, trigger_conditions=[{'field': 'x'}])),
]:
    try:
        fn()
        print(f'FAIL: {label} should have raised ValidationError')
    except ValidationError:
        errors += 1
        print(f'PASS: {label} rejected')
print(f'{errors}/6 invalid inputs correctly rejected')
"
PASS: invalid operator rejected
PASS: missing threshold rejected
PASS: missing field rejected
PASS: extra field rejected
PASS: string for list rejected
PASS: incomplete in list rejected
6/6 invalid inputs correctly rejected
```

---

### AC14: Integration — conditions vs pandemic initial_state

**Status:** VERIFIED

```
$ uv run python -c "
from pathlib import Path
from minimal_agora.scenario import load_scenario
from minimal_agora.board import evaluate_trigger_conditions
s = load_scenario(Path('scenarios/examples/pandemic.yaml'))
state = s.initial_state

ss = next(w for w in s.wildcards if w.name == 'super_spreader_event')
print(f'super_spreader (transmissibility=0.7 gte 0.5): {evaluate_trigger_conditions(ss.trigger_conditions, state)}')

mis = next(w for w in s.wildcards if w.name == 'misinformation_wave')
print(f'misinformation (cohesion=60 lt 50): {evaluate_trigger_conditions(mis.trigger_conditions, state)}')

mut = next(w for w in s.wildcards if w.name == 'mutation')
print(f'mutation (no conditions): {evaluate_trigger_conditions(mut.trigger_conditions, state)}')

# Degraded state
degraded = dict(state)
degraded['regions'] = dict(state['regions'])
degraded['regions']['americas'] = dict(state['regions']['americas'])
degraded['regions']['americas']['social_cohesion'] = 40
print(f'misinformation (degraded cohesion=40 lt 50): {evaluate_trigger_conditions(mis.trigger_conditions, degraded)}')
"
super_spreader (transmissibility=0.7 gte 0.5): True
misinformation (cohesion=60 lt 50): False
mutation (no conditions): True
misinformation (degraded cohesion=40 lt 50): True
```

---

### AC15: Extreme numeric edge cases

**Status:** VERIFIED

```
$ uv run python -c "
from minimal_agora.board import evaluate_trigger_conditions
from minimal_agora.models import ConditionOperator as Op, TriggerCondition as TC
# Very large
assert evaluate_trigger_conditions([TC(field='v', operator=Op.GT, threshold=1e15)], {'v': 1e16}) is True
# Negative
assert evaluate_trigger_conditions([TC(field='v', operator=Op.LT, threshold=-100)], {'v': -200}) is True
# Zero
assert evaluate_trigger_conditions([TC(field='v', operator=Op.EQ, threshold=0)], {'v': 0}) is True
# Float precision: 0.1+0.2 != 0.3 (IEEE 754)
assert evaluate_trigger_conditions([TC(field='v', operator=Op.EQ, threshold=0.1+0.2)], {'v': 0.3}) is False
print('Extreme numerics handled correctly. Float precision is expected IEEE 754 behavior.')
"
Extreme numerics handled correctly. Float precision is expected IEEE 754 behavior.
```

---

## Observations (non-blocking)

1. **Bool-as-numeric:** Python `bool` passes `isinstance(v, (int, float))` since `bool` subclasses `int`. `True` evaluates as `1`, `False` as `0`. Unlikely to cause real issues since scenario states use numeric fields, but worth noting.

2. **Float precision with EQ:** The `EQ` operator uses `float(v) == t`, subject to IEEE 754 precision. Users should avoid EQ for non-integer comparisons. Standard numeric behavior, not a bug.

3. **Duplicate `_get_nested` function:** Defined identically in both `board.py:131` and `loop.py:417`. Minor code smell — not a functional issue.

---

## Summary

| # | Criterion | Status |
|---|-----------|--------|
| AC1 | ConditionOperator enum | VERIFIED |
| AC2 | TriggerCondition model | VERIFIED |
| AC3 | WildcardEvent backward compat | VERIFIED |
| AC4 | Empty conditions | VERIFIED |
| AC5 | Missing fields | VERIFIED |
| AC6 | Non-numeric fields | VERIFIED |
| AC7 | All operators + boundaries | VERIFIED |
| AC8 | Nested dot-path fields | VERIFIED |
| AC9 | Multiple conditions (AND) | VERIFIED |
| AC10 | _roll_wildcard integration | VERIFIED |
| AC11 | Pandemic YAML loads | VERIFIED |
| AC12 | All scenarios backward compat | VERIFIED |
| AC13 | Pydantic rejects bad input | VERIFIED |
| AC14 | Integration vs initial_state | VERIFIED |
| AC15 | Extreme numerics | VERIFIED |

**Tests:** 85/85 pass
**Lint:** Clean
**Criteria verified:** 15/15

## Adversarial Verdict: PASS

The conditional wildcards feature is correctly implemented. All operators work at boundary values, nested fields resolve properly, missing/non-numeric fields fail gracefully, backward compatibility is preserved across all 8 existing scenarios, and Pydantic validation rejects invalid inputs. The integration between `evaluate_trigger_conditions` and `_roll_wildcard` correctly gates probability rolls on state conditions.

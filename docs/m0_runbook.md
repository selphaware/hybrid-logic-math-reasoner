# M0 Runbook

How to verify Milestone 0 works from scratch on Windows.

## Activate the venv

```powershell
.\env_hlmr\Scripts\Activate.ps1
```

If calling the interpreter directly without activating (e.g. across separate
Bash tool calls), prefix every command with `.\env_hlmr\Scripts\python.exe -m`
instead of `python -m`.

## Run the test suite

```powershell
pytest tests/
```

Green run ends with: `228 passed in ~75s`

```powershell
pytest tests/test_kernel_sound.py                             # single file
pytest tests/test_kernel_sound.py::test_de_morgan_not_and    # single test
```

## Coverage (on demand — takes ~90s)

```powershell
pytest tests/ --cov=src/hlmr --cov-report=term-missing
```

Read the `Cover` column. Targets: `kernel/` ≥95%, `ir/` ≥85%. `cli.py` shows
0% because tests run via subprocess; see `pyproject.toml` for explanation.

## Check a proof

```powershell
python -m hlmr check proofs\m0\03_de_morgan.json
# verified (13 lines)   ← exit 0
```

## Pretty-print a proof in Fitch style

```powershell
python -m hlmr show proofs\m0\03_de_morgan.json
```

Prints box-indented Fitch notation with `|` for nested assumption boxes,
line numbers, and justification annotations. Exit 0.

## The three deliberately invalid proofs

All must exit 1. Each demonstrates a distinct kernel rejection type.

```powershell
python -m hlmr check proofs\m0\99_BAD_andI.json
# rejected at line 3: FormulaMismatch: ('andI', (P & Q), (Q & P))
```
`andI(P, Q)` but the conclusion is written `Q & P` — wrong order.

```powershell
python -m hlmr check proofs\m0\99_BAD_oos.json
# rejected at line 4: OutOfScope: ('reit', 1, 4)
```
Line 4 tries to reiterate line 1, which is inside a box already closed at
line 3 by `impI`.

```powershell
python -m hlmr check proofs\m0\99_BAD_eigenvar.json
# rejected at line 3: EigenvarViolation: ('forallI', 'a', "eigenvar 'a' appears free in accessible line 1")
```
`forallI` uses eigenvar `a`, but `a` is already free in the premise at line 1.

## Regenerate the example proofs

```powershell
python proofs\m0\generate.py
```

Rebuilds all 15 JSON files in `proofs/m0/`, verifying each through
`check_proof` as it goes. All 12 valid proofs must print `verified`;
all 3 `99_BAD_*` proofs must print `rejected`.

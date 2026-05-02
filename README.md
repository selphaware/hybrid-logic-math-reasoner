# HLMR — Hybrid Logic-Math Reasoner

A Python 3.12 theorem prover that verifies Fitch-style natural-deduction proofs.
See `prd.md` for the canonical spec and `prd_milestone_0.md` for M0 implementation details.

## Requirements

- Python 3.12+
- Windows (PowerShell) or Linux/macOS

A venv is already created at `env_hlmr/`. If starting fresh:

```powershell
python -m venv env_hlmr
```

## Install

```powershell
# Activate venv (PowerShell)
.\env_hlmr\Scripts\Activate.ps1

# Install in editable mode with test/lint tools
pip install -e ".[test]"
```

## Verify a proof

```powershell
python -m hlmr check proofs\m0\03_de_morgan.json
# verified (13 lines)

python -m hlmr show proofs\m0\04_contrapositive.json
# (Fitch-style ASCII output)
```

Exit codes: 0 verified, 1 rejected, 2 malformed input.

## Run the test suite

```powershell
# Fast feedback loop — no coverage (~20s)
pytest

# Single file
pytest tests/test_kernel_sound.py

# Coverage report — run on demand, takes ~90s
pytest --cov=src/hlmr --cov-report=term-missing
```

Note: `cli.py` will show 0% in coverage reports because its tests run via
subprocess and pytest-cov does not instrument child processes. CLI behaviour
is verified end-to-end by `tests/test_cli.py`.

## Lint

```powershell
ruff check src/hlmr
```

## Regenerate example proofs

```powershell
python proofs\m0\generate.py
```

## Project structure

```
prd.md                 Canonical strategic spec (read first)
prd_milestone_0.md     M0 implementation spec (kernel + IR + CLI)
prd_milestone_1.md     M1 spec (KB, unification, REPL — not yet built)
src/hlmr/
  ir/                  Frozen-dataclass formula/proof types + JSON serialisation
  kernel/              Trusted proof checker (22 ND rules)
  cli.py               argparse CLI
tests/                 pytest + hypothesis test suites
proofs/m0/             16 example proofs (13 valid + 3 deliberately broken)
```

## Where to look next

- `prd_milestone_1.md` — manual SLD solver with unknowns, REPL, parser, logging
- `src/hlmr/ir/formula.py` — term and formula data types
- `src/hlmr/kernel/rules.py` — all 22 ND rule implementations
- `src/hlmr/kernel/check.py` — top-level `check_proof` function

"""CLI smoke tests via subprocess (prd_milestone_0.md §9.2)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PYTHON = sys.executable
_PROOFS = Path(__file__).parent.parent / "proofs" / "m0"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_PYTHON, "-m", "hlmr"] + args,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# check — valid proofs
# ---------------------------------------------------------------------------


def test_check_valid_exits_0() -> None:
    result = run(["check", str(_PROOFS / "01_modus_ponens.json")])
    assert result.returncode == 0
    assert "verified" in result.stdout


def test_check_valid_shows_line_count() -> None:
    result = run(["check", str(_PROOFS / "03_de_morgan.json")])
    assert result.returncode == 0
    assert "13 lines" in result.stdout


def test_check_all_valid_proofs() -> None:
    for path in sorted(_PROOFS.glob("*.json")):
        if path.name.startswith("99_BAD"):
            continue
        result = run(["check", str(path)])
        assert result.returncode == 0, f"{path.name}: {result.stdout} {result.stderr}"


# ---------------------------------------------------------------------------
# check — invalid proofs
# ---------------------------------------------------------------------------


def test_check_bad_andI_exits_1() -> None:
    result = run(["check", str(_PROOFS / "99_BAD_andI.json")])
    assert result.returncode == 1
    assert "FormulaMismatch" in result.stdout


def test_check_bad_oos_exits_1() -> None:
    result = run(["check", str(_PROOFS / "99_BAD_oos.json")])
    assert result.returncode == 1
    assert "OutOfScope" in result.stdout


def test_check_bad_eigenvar_exits_1() -> None:
    result = run(["check", str(_PROOFS / "99_BAD_eigenvar.json")])
    assert result.returncode == 1
    assert "EigenvarViolation" in result.stdout


# ---------------------------------------------------------------------------
# check — error handling
# ---------------------------------------------------------------------------


def test_check_missing_file_exits_2() -> None:
    result = run(["check", "nonexistent_proof.json"])
    assert result.returncode == 2


def test_check_malformed_json_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json}")
    result = run(["check", str(bad)])
    assert result.returncode == 2


def test_check_wrong_schema_version_exits_2(tmp_path: Path) -> None:
    import json
    from hlmr.ir.formula import Bot
    from hlmr.ir.justification import Premise
    from hlmr.ir.proof import Proof, ProofLine
    from hlmr.ir.serialise import to_json

    proof = Proof((ProofLine(1, Bot(), Premise(), 0),))
    data = json.loads(to_json(proof))
    data["schema_version"] = 999
    bad = tmp_path / "bad_version.json"
    bad.write_text(json.dumps(data))
    result = run(["check", str(bad)])
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_valid_proof_outputs_fitch() -> None:
    result = run(["show", str(_PROOFS / "04_contrapositive.json")])
    assert result.returncode == 0
    assert "Premise" in result.stdout
    assert "impI" in result.stdout
    assert "|" in result.stdout  # box bars


def test_show_all_valid_proofs_exit_0() -> None:
    for path in sorted(_PROOFS.glob("*.json")):
        if path.name.startswith("99_BAD"):
            continue
        result = run(["show", str(path)])
        assert result.returncode == 0, f"{path.name}: {result.stderr}"


# ---------------------------------------------------------------------------
# help / no-args
# ---------------------------------------------------------------------------


def test_no_args_exits_2() -> None:
    result = run([])
    assert result.returncode == 2


def test_help() -> None:
    result = run(["--help"])
    assert result.returncode == 0
    assert "check" in result.stdout
    assert "show" in result.stdout

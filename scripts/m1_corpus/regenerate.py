"""Entry point for `python -m hlmr regenerate-corpus`.

Walks every driver in order, generating proof JSONs and sidecar
metadata files under proofs/m1/. Running twice with no code changes
produces no diff (all drivers use fixed pickers and deterministic KBs).

Generation order (capture-stress fixtures last — see hardening doc §4.8):
  kinship, peano_even, peano_plus, peano_times, peano_lt,
  syllogism, finite_puzzle, edge, capture
"""
from __future__ import annotations


def main() -> None:
    from m1_corpus.drivers import (  # noqa: PLC0415
        capture,
        edge,
        finite_puzzle,
        kinship,
        peano_even,
        peano_lt,
        peano_plus,
        peano_times,
        syllogism,
    )

    print("kinship fixtures:")
    kinship.generate_all()

    print("peano_even fixtures:")
    peano_even.generate_all()

    print("peano_plus fixtures:")
    peano_plus.generate_all()

    print("peano_times fixtures:")
    peano_times.generate_all()

    print("peano_lt fixtures:")
    peano_lt.generate_all()

    print("syllogism fixtures:")
    syllogism.generate_all()

    print("finite_puzzle fixtures:")
    finite_puzzle.generate_all()

    print("edge fixtures:")
    edge.generate_all()

    print("capture fixtures (adversarial naming — last):")
    capture.generate_all()

    print("Done. All fixtures written to proofs/m1/")

#!/usr/bin/env python3
"""Fail-closed contract checks for phase-two local objects."""

from __future__ import annotations

import argparse
import sys

from phase2_common import (
    assert_source_contract,
    assert_step_b_contract,
    assert_step_c_contract,
    assert_step_d_contract,
    assert_step_e_contract,
    connect,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=("A", "B", "C", "D", "E"), default="A")
    args = parser.parse_args()
    if args.step not in {"A", "B", "C", "D", "E"}:
        raise SystemExit(f"step {args.step} checks are added with that step")

    connection = connect()
    passed = assert_source_contract(connection)
    if args.step in {"B", "C", "D", "E"}:
        passed.extend(assert_step_b_contract(connection))
    if args.step in {"C", "D", "E"}:
        passed.extend(assert_step_c_contract(connection))
    if args.step in {"D", "E"}:
        passed.extend(assert_step_d_contract(connection))
    if args.step == "E":
        passed.extend(assert_step_e_contract(connection))
    connection.close()
    print(f"phase 2 step {args.step} contract checks passed: {len(passed)}")
    for name in passed:
        print(f"PASS {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

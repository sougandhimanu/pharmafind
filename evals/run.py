"""Run the eval suite: python -m evals.run

Always runs offline so the score is reproducible and never depends on third-party uptime.
Exit code is non-zero if any case fails, so it can gate CI.
"""
import logging
import os
import sys

os.environ["PHARMAFIND_OFFLINE"] = "1"

from evals.cases import CASES  # noqa: E402  (must import after forcing offline mode)


def main() -> int:
    logging.disable(logging.CRITICAL)
    passed = 0
    print(f"PharmaFind evals ({len(CASES)} cases, offline)\n")
    for case in CASES:
        try:
            ok, detail = case.check()
        except Exception as err:
            ok, detail = False, f"crashed: {type(err).__name__}: {err}"
        passed += ok
        print(f"  {'PASS' if ok else 'FAIL'}  #{case.id:<2} {case.name:<52} {detail}")
    score = 100 * passed / len(CASES)
    print(f"\nScore: {passed}/{len(CASES)} ({score:.0f}%)")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())

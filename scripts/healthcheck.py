#!/usr/bin/env python3
"""Concise healthcheck for Milton runtime dependencies."""

from milton_orchestrator.healthcheck import format_table, overall_ok, run_checks


def main() -> int:
    checks = run_checks()
    print(format_table(checks))
    return 0 if overall_ok(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

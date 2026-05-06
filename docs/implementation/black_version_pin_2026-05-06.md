# Black Version Pin 2026-05-06

Date: 2026-05-06

## Module Analysis

The shared CI entrypoint runs `python -m black --check launcher.py gui_agents tests`
across the whole repository. The GitHub workflow installs `.[dev]`, and `setup.py`
previously declared an unpinned `black` dependency. That means CI can pick up a
newer formatter release than local development, even when no source behavior changed.

This is a tooling parity problem, not a Feishu runtime problem.

## Manual Plan

Target files:

- `setup.py`
- `docs/implementation/black_version_pin_2026-05-06.md`

Depends on:

- `.github/workflows/lint.yml` continuing to install `.[dev]`
- `scripts/run_ci_checks.py` continuing to call `python -m black --check ...`

Outputs:

- Dev dependency pins `black==24.4.2`
- Local and CI formatter versions stop drifting as long as both install `.[dev]`

Verification:

- `python scripts/run_ci_checks.py`

Risks / rollback:

- Pinning avoids unexpected CI failures, but it also means formatter upgrades become
  explicit maintenance work.
- If the team later wants a newer formatter, update the pin in one commit and accept
  any repo-wide formatting diff separately.

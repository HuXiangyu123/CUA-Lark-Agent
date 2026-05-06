# Launcher Resizable Split Pane (2026-05-06)

## Module Responsibility

`launcher.py` is the desktop control surface for the Feishu Agent runtime. It
owns launcher-side configuration, command entry, runtime status, SOP shortcuts,
semantic replay browsing, and the live log / preview area.

## Boundary

This fix is launcher-layout only:

- Restore user-resizable width between the left workbench pane and the right
  runtime pane.
- Preserve existing launcher state variables, command routing, history,
  runtime-start behavior, replay viewer behavior, and config persistence.
- Do not change Feishu runtime logic or CLI argument construction.

## Key Interactions

- `_build_ui()` creates the main launcher shell and decides whether the left
  pane is fixed-width or user-resizable.
- `_build_agent_tab()`, `_build_sop_tab()`, `_build_replay_tab()`, and
  `_build_right_pane()` all depend on the parent pane remaining stretchable.
- `tests.test_launcher_env_config` is the local CI entry for launcher-specific
  regressions, so the split-pane structure should be covered there.

## Target Files

- `launcher.py`
- `tests/test_launcher_env_config.py`
- `docs/implementation/launcher_resizable_split_pane_2026-05-06.md`

## Manual Plan

1. Replace the fixed two-column `grid` main-content layout with a horizontal
   `PanedWindow`.
2. Keep the existing left / right pane widget trees intact and only change the
   container that hosts them.
3. Initialize a sensible default sash position once so the launcher still opens
   with the intended visual proportion.
4. Add a launcher regression test that asserts the main area is a horizontal
   resizable split pane with both panes attached.

## Verification

- `python -m unittest tests.test_agent_startup -v`
- `python -m unittest tests.test_launcher_env_config -v`
- `python scripts/run_ci_checks.py`

## Risks

- Tk `PanedWindow` sizing is event-driven; if the sash is placed before the
  widget has a real width, the default split can collapse. Use a guarded
  post-layout initialization path.
- Launcher UI tests may run where Tk is unavailable; skip only in that case
  instead of weakening the assertion logic.

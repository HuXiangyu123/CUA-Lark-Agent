# Calendar New Fixture Practice

Date: 2026-05-06

## Module Analysis

The newly added Calendar screenshot is currently named
`calendar_quick_add_attendee_typing_needed.png`, but the image shows the full
`创建日程` modal rather than the time-slot quick-add popup. It includes a filled
title, attendee search text, attendee search results, meeting settings, and the
full modal footer with Cancel/Save.

This should be configured as full create-event modal evidence, not quick-add
evidence. Keeping it under quick-add would mix the two Calendar creation paths
in logs and semantic replay.

## Boundaries

- Keep the fixture semantic-only.
- Do not add coordinates, bbox, scores, resolution, or other quantitative data.
- Do not introduce a deterministic Calendar workflow.
- Preserve the distinction between `calendar_event_modal` and
  `calendar_quick_add_modal`.

## Target Files

- `tests/fixtures/calendar/calendar_create_event_modal_attendee_search_results.png`
- `tests/fixtures/calendar/calendar_create_event_modal_attendee_search_results.json`
- `tests/fixtures/calendar/manifest.json`
- `tests/fixtures/calendar/readme.md`
- Calendar fixture tests if needed.

## Manual Plan

- Rename the mislabeled PNG from quick-add to full create-event attendee search.
- Add same-stem JSON metadata for the new state.
- Update Calendar manifest and readme.
- Run Calendar fixture constraints and startup self-check.

## Risk

The image appears to show a full modal with attendee search results, not an
already selected attendee chip list. If the visual state changes after selecting
a result, that should remain a separate fixture.

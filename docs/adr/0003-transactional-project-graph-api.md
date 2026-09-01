# ADR 0003: Transactional project graph API

- Status: Accepted for local testing
- Date: 2026-09-01
- Last verified: 2026-09-01

## Context

LiquiGen does not document a scripting SDK or headless export API. UI gestures
are a poor primary contract for node creation, parameter editing, keyframes, and
connections. Local analysis showed that installed projects share one bounded
tagged-document structure and expose stable node, parameter, and pin names.

## Decision

Expose project graph authoring as typed DCC-MCP tools:

- discover node schemas from installed official projects;
- inspect nodes, parameters, animation lanes, and typed connections;
- atomically create, clone, delete, configure, animate, connect, or disconnect
  nodes, and create/update/delete groups and notes;
- update existing project settings and select an existing camera;
- validate new connections against observed source and target pin names;
- write only to a new destination, then decode and validate the complete result;
- match LiquiGen versions by executable name and named interfaces, not by an
  executable hash.

Keep live host commands separate. Loading, simulation, and export execution use
their own fixed UI-thread semantic bridge and fresh-bundle workflow. Viewport
acceptance is not implied by either a successful project transaction or export.

## Consequences

Agents build and show complete node graphs without CUA. Transactions are
deterministic, reviewable, and fail without leaving a partial destination. The
adapter remains sensitive to undocumented format changes, so every untested
LiquiGen version must pass schema discovery, round-trip checks, and a real host
load before it is marked tested.

This route is an experimental local integration. A public release requires a
separate distribution decision and must not include LiquiGen binaries, presets,
license data, or protection-bypass code.

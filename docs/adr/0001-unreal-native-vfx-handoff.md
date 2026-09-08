# ADR 0001: Export interchange

- Status: Graph authoring superseded by [ADR 0003](0003-transactional-project-graph-api.md).

Keep source projects and export bundles separate from assets created by a
receiving application. Support VAT for texture-driven animation, Alembic for
mesh caches, and image sequences for flipbooks. Treat velocity volumes as
auxiliary data rather than a liquid surface.

Receiver examples own format-specific dependencies and import configuration.
See [examples](../../examples/README.md). Bundle validation proves file
structure; the receiving application must verify its interpretation.

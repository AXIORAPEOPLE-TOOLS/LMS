# Backend code rules

These rules keep the backend scalable, readable and safe to change. Code review checks them.

## 1. Structure and layering
- One feature = one folder in `app/modules/<feature>/`. Cross-feature calls go through the other module's **service**, never its router.
- **Routers** only: declare the route, auth dependency, call one service method, return a schema. No queries, no `if` business rules.
- **Services** hold business logic. They never import FastAPI (`Request`, `HTTPException`). They raise `AppError` subclasses.
- **Rules** (`rules.py`) are pure functions with no I/O for anything the spec calls a formula. Test them directly.
- **Models** are data. **Schemas** are contracts (`…In` for input, `…Out` for output). Never return ORM objects without a `response_model`.
- New behaviour in another module? Publish a domain event (`event_bus.publish`) instead of importing and calling it, when the caller should not know about the reaction.

## 2. SOLID in practice
- **S**ingle responsibility: a service class covers one area (e.g. `AssignmentService`, `SessionService`), files stay under ~400 lines.
- **O**pen/closed: extend through registries — `@register_report`, `register_action` (workflows), `@job_handler`, `@scheduled_task`, `register_channel`, `register_component` (health), `register_undo`.
- **L**iskov: providers implement the full protocol (`AssistantProvider`, `Channel`, `Exporter`, `JobQueue`) and are swappable in tests.
- **I**nterface segregation: small protocols (one or few methods).
- **D**ependency inversion: services depend on protocols/factories (`get_assistant()`, `get_queue()`), not on concrete SDKs.

## 3. Database
- SQLAlchemy 2 typed models, `Mapped[...]`, UUID primary keys (`IdMixin`), UTC timestamps (`UTCDateTime`).
- Use portable types (`Uuid`, `JSON`, `UTCDateTime`) so tests run on SQLite and production on Postgres.
- One session per request (`SessionDep`), committed by the dependency. Services call `flush()` when they need ids — never `commit()` (except jobs/tasks that own their session).
- Avoid N+1: batch-load names/paths (see `knowledge/presenter.py`). Check query counts for new list screens.
- Every model change ships with an Alembic migration (`alembic revision --autogenerate`). The drift test enforces it.

## 4. Errors and robustness
- Raise `NotFoundError`, `ConflictError`, `PermissionDeniedError`, `ValidationFailedError`, `ServiceUnavailableError`. Messages are plain sentences a learner can read.
- Every external call (Redis, Groq, email, WhatsApp, file storage, future APIs) goes through `breaker(name).call(...)` with a timeout **and** a fallback path. Register a health `Component` for it.
- Background work: `defer_job(session, queue, name, data)`. Never `asyncio.create_task` from a request.
- Bulk sends: preview endpoint + `BulkActionService.start(...)` + `register_undo(...)`.

## 5. Security and privacy
- Every route declares who may call it (`CurrentUser`, `AdminUser`, `ManagerUser`, `require_roles(...)`). Object-level checks live in services (e.g. "is this person in your team?", knowledge `KnowledgePolicy`).
- Audit (`AuditService.record`) every override, export, deletion, role change, approval and evidence view.
- No personal data in logs beyond ids/emails needed for support. Secrets only from environment.

## 6. Configuration
- Infrastructure settings: `app/core/config.py` (`LMS_*` env vars).
- Business defaults: `app/modules/settings/defaults.py`, read with `SettingsService.get(key)`; admins can override.

## 7. Style
- Python 3.13, type hints everywhere, `ruff` (line length 130) and `ruff format`. Names say what things are (`send_invitations`, not `process`).
- Comments explain *why* or point to the spec (screen id / sheet). No commented-out code.
- Plain-language user messages; developer details stay in logs.

## 8. Tests
- Tests live in `test/backend/<feature>/` (see `testing.md`). Each new endpoint gets at least: happy path, permission check, one validation/edge case.
- Use `testkit` builders (`make_course`, `make_test`, `make_role`…) and `make_user` fixture; freeze time with `clock.freeze`.

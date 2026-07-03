# Sync vs Async

The SDK offers the same API in blocking and asynchronous forms.

## Blocking API

Use `Client` and `Session` when you want simple, synchronous code.

## Async API

Use `AsyncClient` and `AsyncSession` when you are already in an async application or want to
integrate with async orchestration.

## Guidance

- Prefer the blocking API for scripts, notebooks, and small utilities.
- Prefer the async API for web services or concurrent pipelines.
- The return types and method names are intentionally aligned between both styles.
# ADR-0001: Adopt a local-first modular monolith

## Status

Accepted

## Context

The first release must run on a Windows machine, work with local model servers,
keep learner records locally, and provide a complete real question bank without
requiring PostgreSQL, Redis, or a cloud account.

## Decision

Use a FastAPI application with SQLite, a static browser client, and explicit
service modules for question ingestion, grading, learner modelling, forecasting,
and OpenAI-compatible model access.

## Consequences

### Positive

- One command starts the application.
- SQLite keeps attempts and model settings local.
- The model gateway works with hosted APIs, Ollama, LM Studio, vLLM, and other
  OpenAI-compatible endpoints.
- The domain modules can later be split without changing the public API.

### Negative

- A single process limits horizontal scaling in the first release.
- API keys are stored in the local SQLite file and should be protected by the
  operating-system account and filesystem permissions.
- The bundled question data must be refreshed deliberately when the source is
  updated.

## Alternatives Considered

**Microservices** were rejected for the first release because they add
deployment and debugging cost without helping a single-user local workflow.

**A cloud-only database** was rejected because offline/local-model use is a
first-class requirement.

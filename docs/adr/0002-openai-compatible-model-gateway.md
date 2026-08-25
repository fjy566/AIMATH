# ADR-0002: Use one OpenAI-compatible model gateway

## Status

Accepted

## Context

The user may use a hosted provider or a local server. The application must have
one settings page where Base URL, API key, and model selection are managed.

## Decision

Store one Base URL, one API key, and one selected model in local settings. Fetch
available models through `GET /models` and call `POST /chat/completions` using
the OpenAI-compatible protocol.

## Consequences

- Hosted providers and local servers use the same UI and backend contract.
- The app does not depend on a provider-specific SDK.
- Providers with incompatible APIs require an adapter later.
- The key is never returned in full by the API and is not written to logs.

# Rust migration plan

The existing Windows/PySide6 application remains the working game manager. This document tracks the incremental Rust migration without replacing working functionality prematurely.

## First slice: translation core

The rust-core crate introduces:
- A LibreTranslate-compatible HTTP client.
- A persistent SQLite translation cache.
- Explicit configuration and error handling.
- Unit tests and a GitHub Actions workflow.

## Next integration milestones

1. Add a Rust desktop shell only after the core API is stable.
2. Define a narrow adapter interface for text extraction and reinjection.
3. Keep the existing official XUnity release integration as the Unity Mono adapter until a Rust-native adapter is proven.
4. Add IL2CPP support only with a separately validated integration path.
5. Verify against a legally owned offline Unity Mono test game before describing the app as game-tested.

No universal game compatibility is claimed. The Rust core currently translates supplied strings; it does not yet acquire strings from games.

# AUTO-VIETHOA Rust Core (experimental)

This crate is the first Rust component proposed for AUTO-VIETHOA-GAME. It provides a translation service abstraction and persistent SQLite cache.

## Current scope

- LibreTranslate-compatible HTTP endpoint (POST /translate).
- Configurable source/target language, API key, and request timeout.
- SQLite cache keyed by source language, target language, and exact original text.
- Empty strings pass through without a network request.
- Explicit errors for invalid configuration, HTTP failures, cache failures, and empty API responses.

## Not implemented yet

This crate does not read text from a running game, inject into Unity, hook Mono/IL2CPP, or apply translations to game UI. Those require separate game-specific adapters. The existing Python/XUnity manager remains unchanged in this branch.

## Use

Add this crate as a path dependency from a future Rust desktop shell:

    [dependencies]
    autoviethoa-core = { path = "../rust-core" }

Example:

    use autoviethoa_core::{TranslationConfig, Translator};

    fn main() -> Result<(), Box<dyn std::error::Error>> {
        let translator = Translator::open(
            TranslationConfig {
                endpoint: "http://127.0.0.1:5000".into(),
                source_language: "en".into(),
                target_language: "vi".into(),
                api_key: None,
                timeout_seconds: 20,
            },
            "translations.sqlite3",
        )?;
        println!("{}", translator.translate("New game")?);
        Ok(())
    }

Run tests with cargo test --manifest-path rust-core/Cargo.toml.

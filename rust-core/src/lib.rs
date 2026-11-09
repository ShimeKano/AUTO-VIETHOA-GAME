//! Reusable translation core for AUTO-VIETHOA-GAME.
//!
//! This crate deliberately does not inject into games. Game-specific adapters
//! are responsible for collecting text and applying translated text safely.

use reqwest::blocking::Client;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::Mutex;
use std::time::Duration;
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranslationConfig {
    /// Base URL of a LibreTranslate-compatible server, e.g. http://localhost:5000
    pub endpoint: String,
    pub source_language: String,
    pub target_language: String,
    #[serde(default)]
    pub api_key: Option<String>,
    #[serde(default = "default_timeout")]
    pub timeout_seconds: u64,
}

fn default_timeout() -> u64 { 20 }

impl TranslationConfig {
    fn validate(&self) -> Result<(), TranslationError> {
        if self.endpoint.trim().is_empty() {
            return Err(TranslationError::InvalidConfig("endpoint must not be empty".into()));
        }
        if self.source_language.trim().is_empty() || self.target_language.trim().is_empty() {
            return Err(TranslationError::InvalidConfig(
                "source and target language codes must not be empty".into(),
            ));
        }
        if self.timeout_seconds == 0 {
            return Err(TranslationError::InvalidConfig("timeout must be greater than zero".into()));
        }
        Ok(())
    }

    fn translate_url(&self) -> String {
        format!("{}/translate", self.endpoint.trim_end_matches('/'))
    }
}

#[derive(Debug, Error)]
pub enum TranslationError {
    #[error("invalid translation configuration: {0}")]
    InvalidConfig(String),
    #[error("translation HTTP request failed: {0}")]
    Http(#[from] reqwest::Error),
    #[error("translation cache failed: {0}")]
    Cache(#[from] rusqlite::Error),
    #[error("translation service returned an empty translation")]
    EmptyTranslation,
    #[error("translation cache lock was poisoned")]
    CacheLockPoisoned,
}

#[derive(Debug, Serialize)]
struct TranslateRequest<'a> {
    q: &'a str,
    source: &'a str,
    target: &'a str,
    format: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    api_key: Option<&'a str>,
}

#[derive(Debug, Deserialize)]
struct TranslateResponse {
    #[serde(rename = "translatedText")]
    translated_text: String,
}

/// Synchronous translation service with a persistent SQLite cache.
///
/// Cache keys include the original text and both language codes.
pub struct Translator {
    config: TranslationConfig,
    client: Client,
    cache: Mutex<Connection>,
}

impl Translator {
    pub fn open(config: TranslationConfig, cache_path: impl AsRef<Path>) -> Result<Self, TranslationError> {
        config.validate()?;
        let client = Client::builder()
            .timeout(Duration::from_secs(config.timeout_seconds))
            .build()?;
        let cache = Connection::open(cache_path)?;
        Self::initialize(config, client, cache)
    }

    /// Create a translator backed by an in-memory cache (useful for tests).
    pub fn in_memory(config: TranslationConfig) -> Result<Self, TranslationError> {
        config.validate()?;
        let client = Client::builder()
            .timeout(Duration::from_secs(config.timeout_seconds))
            .build()?;
        let cache = Connection::open_in_memory()?;
        Self::initialize(config, client, cache)
    }

    fn initialize(config: TranslationConfig, client: Client, cache: Connection) -> Result<Self, TranslationError> {
        cache.execute_batch(
            "CREATE TABLE IF NOT EXISTS translations (
                source_language TEXT NOT NULL,
                target_language TEXT NOT NULL,
                original_text TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_language, target_language, original_text)
            );",
        )?;
        Ok(Self { config, client, cache: Mutex::new(cache) })
    }

    /// Return a cached translation or call the configured LibreTranslate-compatible API.
    pub fn translate(&self, text: &str) -> Result<String, TranslationError> {
        if text.trim().is_empty() {
            return Ok(text.to_owned());
        }

        if let Some(cached) = self.cache.lock()
            .map_err(|_| TranslationError::CacheLockPoisoned)?
            .query_row(
                "SELECT translated_text FROM translations
                 WHERE source_language = ?1 AND target_language = ?2 AND original_text = ?3",
                params![self.config.source_language, self.config.target_language, text],
                |row| row.get::<_, String>(0),
            )
            .optional()?
        {
            return Ok(cached);
        }

        let request = TranslateRequest {
            q: text,
            source: &self.config.source_language,
            target: &self.config.target_language,
            format: "text",
            api_key: self.config.api_key.as_deref(),
        };
        let response: TranslateResponse = self.client
            .post(self.config.translate_url())
            .json(&request)
            .send()?
            .error_for_status()?
            .json()?;

        let translated = response.translated_text.trim().to_owned();
        if translated.is_empty() {
            return Err(TranslationError::EmptyTranslation);
        }

        self.cache.lock()
            .map_err(|_| TranslationError::CacheLockPoisoned)?
            .execute(
                "INSERT OR REPLACE INTO translations
                 (source_language, target_language, original_text, translated_text)
                 VALUES (?1, ?2, ?3, ?4)",
                params![self.config.source_language, self.config.target_language, text, translated],
            )?;

        Ok(translated)
    }

    /// Remove cached translations for this source/target language pair.
    pub fn clear_cache(&self) -> Result<usize, TranslationError> {
        let changed = self.cache.lock()
            .map_err(|_| TranslationError::CacheLockPoisoned)?
            .execute(
                "DELETE FROM translations WHERE source_language = ?1 AND target_language = ?2",
                params![self.config.source_language, self.config.target_language],
            )?;
        Ok(changed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> TranslationConfig {
        TranslationConfig {
            endpoint: "http://127.0.0.1:5000".into(),
            source_language: "en".into(),
            target_language: "vi".into(),
            api_key: None,
            timeout_seconds: 2,
        }
    }

    #[test]
    fn rejects_missing_endpoint() {
        let mut cfg = config();
        cfg.endpoint.clear();
        assert!(matches!(Translator::in_memory(cfg), Err(TranslationError::InvalidConfig(_))));
    }

    #[test]
    fn empty_text_does_not_require_network() {
        let translator = Translator::in_memory(config()).unwrap();
        assert_eq!(translator.translate("  ").unwrap(), "  ");
    }

    #[test]
    fn cache_can_be_cleared_without_network() {
        let translator = Translator::in_memory(config()).unwrap();
        assert_eq!(translator.clear_cache().unwrap(), 0);
    }
}

//! Codex app-server bridge. The wire adapter has no Craft dependency.
pub mod adapter;
pub mod config;
pub mod driver;
pub mod framing;
pub mod parser;
pub mod process;
pub mod session;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Failure { pub code: String, pub detail: String }
impl Failure { pub fn new(code: &str, detail: impl ToString) -> Self { Self { code: code.into(), detail: detail.to_string() } } }
pub type Result<T> = std::result::Result<T, Failure>;

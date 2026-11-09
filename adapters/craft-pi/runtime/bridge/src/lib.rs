//! Independent protocol boundary. A future Craft AgentAdapter consumes adapter::Launch
//! and parser::BridgeParser; this crate deliberately has no Craft dependency.
pub mod adapter;
pub mod config;
pub mod driver;
pub mod framing;
pub mod parser;
mod process;
mod redaction;
pub mod session;

use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Failure {
    pub code: String,
    pub detail: String,
}
impl Failure {
    pub fn new(code: &str, detail: impl ToString) -> Self {
        Self {
            code: code.into(),
            detail: detail.to_string(),
        }
    }
}
pub type Result<T> = std::result::Result<T, Failure>;

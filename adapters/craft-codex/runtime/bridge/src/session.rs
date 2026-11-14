//! Host-created thread receipt. Codex app-server has no Pi JSONL session contract.
use crate::{Failure, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{fs, path::Path};
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ThreadReceipt { pub version: u32, pub host_created: bool, pub thread_id: String, pub run_id: String, pub turn_id: String, pub model: String, pub effort: String }
pub fn write(path: &Path, receipt: &ThreadReceipt) -> Result<()> {
    let bytes = serde_json::to_vec_pretty(receipt).map_err(|e| Failure::new("receipt_encode", e))?;
    fs::write(path, bytes).map_err(|e| Failure::new("receipt_write", e))
}
pub fn read(path: &Path) -> Result<ThreadReceipt> {
    let v: ThreadReceipt = serde_json::from_slice(&fs::read(path).map_err(|e| Failure::new("receipt_read", e))?).map_err(|e| Failure::new("receipt_invalid", e))?;
    if v.version != 1 || !v.host_created || v.thread_id.is_empty() { return Err(Failure::new("receipt_invalid", "thread receipt is not a verified host-created v1 record")); }
    Ok(v)
}
pub fn event(receipt: &ThreadReceipt) -> Value {
    serde_json::json!({"type":"bridge_thread","contract":"craft-codex-bridge.v1","threadId":receipt.thread_id,"receipt":receipt,"hostCreated":true})
}

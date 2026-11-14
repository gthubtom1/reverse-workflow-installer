//! Craft-free normalized event boundary for the Codex app-server driver.
use crate::{Failure, Result};
use serde_json::{Value, json};

#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct Usage {
    pub input: u64,
    pub output: u64,
    pub cache_read: Option<u64>,
    pub cache_write: Option<u64>,
    pub total_tokens: Option<u64>,
    pub estimated_cost: Option<f64>,
}
#[derive(Debug, Clone, serde::Serialize)]
pub struct TurnReport {
    pub success: bool,
    pub failure: Option<Failure>,
    pub cleanup: crate::process::Cleanup,
    pub child_exit: Option<i32>,
    pub settled: bool,
    pub final_message: Option<Value>,
    pub actual_model: Option<Value>,
    pub usage: Usage,
    pub nested_usage: Usage,
    pub cancel_acknowledged: bool,
    pub terminal_acknowledged: bool,
    pub thread_receipt: Option<Value>,
}
#[derive(Debug, Clone, PartialEq)]
pub enum AdapterEvent {
    Thread { id: String, receipt: Value },
    TextDelta { bytes: usize },
    ToolStarted { id: String, name: String },
    ToolFinished { id: String, ok: bool },
    Failure(Value),
    Completed(Value),
}
#[derive(Default)]
pub struct BridgeParser {
    pub thread: Option<(String, Value)>,
    pub failure: Option<Value>,
    pub completion: Option<Value>,
}
impl BridgeParser {
    pub fn parse(&mut self, value: &Value) -> Result<Vec<AdapterEvent>> {
        let Some(kind) = value["type"].as_str() else { return Err(Failure::new("bad_bridge_event", "type missing")); };
        let event = match kind {
            "bridge_thread" => {
                let id = value["threadId"].as_str().filter(|s| !s.is_empty()).ok_or_else(|| Failure::new("bad_bridge_event", "threadId"))?.to_owned();
                if value["hostCreated"] != true { return Err(Failure::new("bad_bridge_event", "thread receipt must be host-created")); }
                self.thread = Some((id.clone(), value["receipt"].clone()));
                Some(AdapterEvent::Thread { id, receipt: value["receipt"].clone() })
            }
            "bridge_progress" => Some(AdapterEvent::TextDelta { bytes: value["bytes"].as_u64().unwrap_or(0) as usize }),
            "bridge_tool_started" => Some(AdapterEvent::ToolStarted { id: value["callId"].as_str().ok_or_else(|| Failure::new("bad_bridge_event", "callId"))?.into(), name: value["name"].as_str().ok_or_else(|| Failure::new("bad_bridge_event", "name"))?.into() }),
            "bridge_tool_finished" => Some(AdapterEvent::ToolFinished { id: value["callId"].as_str().ok_or_else(|| Failure::new("bad_bridge_event", "callId"))?.into(), ok: value["ok"].as_bool().ok_or_else(|| Failure::new("bad_bridge_event", "ok"))? }),
            "bridge_failure" => { self.failure = Some(value.clone()); Some(AdapterEvent::Failure(value.clone())) }
            "bridge_complete" => { self.completion = Some(value.clone()); Some(AdapterEvent::Completed(value.clone())) }
            _ => return Err(Failure::new("bad_bridge_event", "unknown bridge record")),
        };
        Ok(event.into_iter().collect())
    }
    pub fn successful(&self, exit: Option<i32>) -> bool {
        exit == Some(0) && self.failure.is_none() && self.thread.is_some() && self.completion.as_ref().is_some_and(|v| v["success"] == true && v["settled"] == true && v["cleanup"]["status"] == "verified" && v["actualModel"].is_object() && v["terminalAcknowledged"] == true)
    }
}
pub fn failure_event(f: &Failure) -> Value { json!({"type":"bridge_failure","code":f.code,"detail":f.detail}) }

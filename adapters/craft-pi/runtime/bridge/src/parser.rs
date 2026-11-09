use crate::{Failure, Result, config::Config};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;
#[derive(Default, Debug, Clone, Serialize, Deserialize)]
pub struct Usage {
    pub input: u64,
    pub output: u64,
    pub cache_read: u64,
    pub cache_write: u64,
    pub total_tokens: u64,
    pub estimated_cost: f64,
}
impl Usage {
    fn add(&mut self, v: &Value) -> Result<()> {
        for (slot, name) in [
            (&mut self.input, "input"),
            (&mut self.output, "output"),
            (&mut self.cache_read, "cacheRead"),
            (&mut self.cache_write, "cacheWrite"),
            (&mut self.total_tokens, "totalTokens"),
        ] {
            let n = v[name]
                .as_u64()
                .ok_or_else(|| Failure::new("bad_usage", name))?;
            *slot = slot
                .checked_add(n)
                .ok_or_else(|| Failure::new("bad_usage", "usage overflow"))?;
        }
        let cost = v["cost"]["total"]
            .as_f64()
            .filter(|v| v.is_finite() && *v >= 0.0)
            .ok_or_else(|| Failure::new("bad_usage", "cost.total missing or invalid"))?;
        self.estimated_cost += cost;
        if !self.estimated_cost.is_finite() {
            return Err(Failure::new("bad_usage", "cost overflow"));
        }
        Ok(())
    }
}
#[derive(Default)]
pub struct TurnParser {
    pub usage: Usage,
    pub nested_usage: Usage,
    pub final_message: Option<Value>,
    pub settled: bool,
    seen: HashSet<String>,
    active_tools: HashSet<String>,
}
impl TurnParser {
    pub fn accept(&mut self, v: &Value, c: &Config) -> Result<()> {
        if self.settled
            && ![
                Some("session_info_changed"),
                Some("entry_appended"),
                Some("queue_update"),
            ]
            .contains(&v["type"].as_str())
        {
            return Err(Failure::new(
                "event_after_settled",
                "Pi emitted a run event after settling",
            ));
        }
        match v["type"].as_str().unwrap_or("") {
            "message_end" => {
                let m = &v["message"];
                if m["role"] == "assistant" {
                    for (name, expected) in [("provider", &c.provider), ("model", &c.model)] {
                        if m[name].as_str() != Some(expected) {
                            return Err(Failure::new(
                                "model_mismatch",
                                format!("assistant {name} differs or is missing"),
                            ));
                        }
                    }
                    // Startup state verifies the requested selection strictly.
                    // Official assistant effort fields are optional; never fill
                    // missing runtime/provider observations from that request.
                    if m.get("thinkingLevel")
                        .is_some_and(|v| v.as_str() != Some(&c.thinking))
                        || m.get("responseModel")
                            .is_some_and(|v| v.as_str() != Some(&c.model))
                        || m.get("providerThinkingLevel")
                            .is_some_and(|v| v.as_str() != Some(&c.thinking))
                    {
                        return Err(Failure::new(
                            "model_mismatch",
                            "provider response model/effort differs",
                        ));
                    }
                    if !m["content"].is_array() || !m["timestamp"].is_number() {
                        return Err(Failure::new(
                            "bad_protocol",
                            "assistant content/timestamp missing",
                        ));
                    }
                    if ![Some("stop"), Some("toolUse")].contains(&m["stopReason"].as_str()) {
                        return Err(Failure::new(
                            "assistant_failed",
                            m["stopReason"].to_string(),
                        ));
                    }
                    // Stable provider response ID when present, otherwise exact completed
                    // message. Never sum cumulative message_update or turn_end snapshots.
                    let key = match m["responseId"].as_str() {
                        Some(id) => format!("assistant:{}:{}:{id}", c.provider, c.model),
                        None => m.to_string(),
                    };
                    if self.seen.insert(key) {
                        self.usage.add(&m["usage"])?;
                    }
                    self.final_message = Some(m.clone());
                } else if m["role"] == "toolResult" && m.get("usage").is_some() {
                    let key = format!("tool:{}", m["toolCallId"]);
                    if self.seen.insert(key) {
                        self.nested_usage.add(&m["usage"])?;
                    }
                }
            }
            "tool_execution_start" => {
                let name = v["toolName"]
                    .as_str()
                    .ok_or_else(|| Failure::new("bad_protocol", "toolName missing"))?;
                if !c.selected_mcp_tools.iter().any(|s| s == name) {
                    return Err(Failure::new("unexpected_tool", name));
                }
                let id = v["toolCallId"]
                    .as_str()
                    .ok_or_else(|| Failure::new("bad_protocol", "toolCallId missing"))?;
                if !self.active_tools.insert(id.into()) {
                    return Err(Failure::new("bad_protocol", "duplicate active tool"));
                }
            }
            "tool_execution_end" => {
                let id = v["toolCallId"]
                    .as_str()
                    .ok_or_else(|| Failure::new("bad_protocol", "toolCallId missing"))?;
                if !self.active_tools.remove(id) {
                    return Err(Failure::new("bad_protocol", "unmatched tool end"));
                }
            }
            "agent_settled" => {
                if v["aborted"] != false {
                    return Err(Failure::new(
                        "aborted",
                        "agent_settled aborted or absent flag",
                    ));
                }
                if !self.active_tools.is_empty() {
                    return Err(Failure::new(
                        "unfinished_tools",
                        "settled with active tools",
                    ));
                }
                if self
                    .final_message
                    .as_ref()
                    .is_none_or(|m| m["stopReason"] != "stop")
                {
                    return Err(Failure::new(
                        "missing_final",
                        "settled without authoritative stop final",
                    ));
                }
                self.settled = true;
            }
            "queue_update" => {
                if v["steering"].as_array().is_none_or(|a| !a.is_empty())
                    || v["followUp"].as_array().is_none_or(|a| !a.is_empty())
                {
                    return Err(Failure::new(
                        "unexpected_queue",
                        "single-turn session acquired queued work",
                    ));
                }
            }
            "extension_error" => {
                return Err(Failure::new("extension_error", "extension handler failed"));
            }
            "session" => {
                return Err(Failure::new(
                    "bad_protocol",
                    "RPC must not emit native session header",
                ));
            }
            _ => {}
        }
        Ok(())
    }
}

/// Output suitable for mapping into Craft AgentEvent without linking Craft here.
#[derive(Debug, Clone, PartialEq)]
pub enum AdapterEvent {
    Session {
        session_id: String,
        session_file: String,
    },
    TextDelta(String),
    ToolStarted {
        id: String,
        name: String,
        args: Value,
    },
    ToolFinished {
        id: String,
        result: Value,
        is_error: bool,
    },
    Failure(Value),
    Completed(Value),
}
#[derive(Default)]
pub struct BridgeParser {
    pub session: Option<(String, String)>,
    pub failure: Option<Value>,
    pub completion: Option<Value>,
}
impl BridgeParser {
    pub fn parse(&mut self, v: &Value) -> Result<Vec<AdapterEvent>> {
        let event = match v["type"].as_str().unwrap_or("") {
            "bridge_session" => {
                let id = v["sessionId"]
                    .as_str()
                    .ok_or_else(|| Failure::new("bad_bridge_event", "sessionId"))?
                    .to_owned();
                let file = v["sessionFile"]
                    .as_str()
                    .ok_or_else(|| Failure::new("bad_bridge_event", "sessionFile"))?
                    .to_owned();
                if v["headerVerified"] != true {
                    return Err(Failure::new("bad_bridge_event", "unverified session"));
                }
                self.session = Some((id.clone(), file.clone()));
                Some(AdapterEvent::Session {
                    session_id: id,
                    session_file: file,
                })
            }
            "message_update" if v["assistantMessageEvent"]["type"] == "text_delta" => {
                Some(AdapterEvent::TextDelta(
                    v["assistantMessageEvent"]["delta"]
                        .as_str()
                        .ok_or_else(|| Failure::new("bad_bridge_event", "delta"))?
                        .into(),
                ))
            }
            "tool_execution_start" => Some(AdapterEvent::ToolStarted {
                id: v["toolCallId"]
                    .as_str()
                    .ok_or_else(|| Failure::new("bad_bridge_event", "toolCallId"))?
                    .into(),
                name: v["toolName"]
                    .as_str()
                    .ok_or_else(|| Failure::new("bad_bridge_event", "toolName"))?
                    .into(),
                args: v
                    .get("args")
                    .ok_or_else(|| Failure::new("bad_bridge_event", "args"))?
                    .clone(),
            }),
            "tool_execution_end" => Some(AdapterEvent::ToolFinished {
                id: v["toolCallId"]
                    .as_str()
                    .ok_or_else(|| Failure::new("bad_bridge_event", "toolCallId"))?
                    .into(),
                result: v
                    .get("result")
                    .ok_or_else(|| Failure::new("bad_bridge_event", "result"))?
                    .clone(),
                is_error: v["isError"]
                    .as_bool()
                    .ok_or_else(|| Failure::new("bad_bridge_event", "isError"))?,
            }),
            "bridge_failure" => {
                self.failure = Some(v.clone());
                Some(AdapterEvent::Failure(v.clone()))
            }
            "bridge_complete" => {
                self.completion = Some(v.clone());
                Some(AdapterEvent::Completed(v.clone()))
            }
            _ => None,
        };
        Ok(event.into_iter().collect())
    }
    /// A runner's TurnDone alone is not success.
    pub fn successful(&self, exit_code: Option<i32>) -> bool {
        exit_code == Some(0)
            && self.failure.is_none()
            && self.session.is_some()
            && self
                .completion
                .as_ref()
                .is_some_and(|v| v["success"] == true && v["cleanup"]["status"] == "verified")
    }
}
pub fn failure_event(f: &Failure) -> Value {
    json!({"type":"bridge_failure","code":f.code,"detail":f.detail})
}

//! Public result whitelist. Builder text, file contents, command strings and diagnostics are
//! excluded; consumers receive event kinds, outcomes, byte counts and measured usage only.
use craft_anything_ai::{AgentEvent, rebuild::RunEvent};
use serde_json::{Value, json};
pub fn check(r: &Value) -> Value {
    let claims = r["claims"].as_array();
    json!({"check":r["check"],"round":r["round"],"passed":r["passed"],"similarity":r["similarity"],
        "unknown_count":r["unknowns"].as_array().map_or(0,Vec::len),"claims":{
            "total":claims.map_or(0,Vec::len),"passed":claims.into_iter().flatten().filter(|c|c["passed"]==true).count(),
            "failed":claims.into_iter().flatten().filter(|c|c["passed"]!=true).count()},"note_bytes":r["note"].as_str().map_or(0,str::len)})
}
pub fn event(event: RunEvent) -> Value {
    match event {
        RunEvent::Agent(a) => match a {
            AgentEvent::TextDelta { text } => json!({"event":"agent-text","bytes":text.len()}),
            AgentEvent::Status { text } => json!({"event":"agent-status","bytes":text.len()}),
            AgentEvent::Output { text } => json!({"event":"agent-output","bytes":text.len()}),
            AgentEvent::ToolStarted { tool, input, .. } => {
                json!({"event":"tool-started","tool":tool,"argument_bytes":input.to_string().len()})
            }
            AgentEvent::ToolFinished {
                tool, ok, summary, ..
            } => json!({"event":"tool-finished","tool":tool,"ok":ok,"summary_bytes":summary.len()}),
            AgentEvent::ConsentNeeded { tool, .. } => {
                json!({"event":"consent-request","tool":tool,"status":"unsupported"})
            }
            AgentEvent::TurnDone {
                backend,
                input_tokens,
                output_tokens,
                cost_usd,
                cost_is_estimate,
            } => {
                json!({"event":"turn-done","backend":backend,"input_tokens":input_tokens,"output_tokens":output_tokens,"estimated_cost_usd":cost_usd,"cost_is_estimate":cost_is_estimate})
            }
            AgentEvent::Error {
                message,
                remediation,
                ..
            } => {
                json!({"event":"agent-error","message_bytes":message.len(),"has_remediation":remediation.is_some()})
            }
        },
        RunEvent::Step { step, text } => {
            json!({"event":"step","step":format!("{step:?}"),"text_bytes":text.len()})
        }
        RunEvent::Note { shown, pictures } => {
            json!({"event":"note","text_bytes":shown.len(),"picture_count":pictures.len()})
        }
        RunEvent::Ask(_) => json!({"event":"ask","status":"unsupported"}),
        RunEvent::Preview(url) => json!({"event":"preview","url_bytes":url.len()}),
        RunEvent::Finished {
            ok,
            message,
            paused,
        } => json!({"event":"finished","ok":ok,"message_bytes":message.len(),"paused":paused}),
        RunEvent::Checked(c) => check(&serde_json::to_value(c).unwrap_or(Value::Null)),
    }
}

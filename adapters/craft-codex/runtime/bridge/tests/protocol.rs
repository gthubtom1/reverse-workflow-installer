use craft_codex_bridge::parser::BridgeParser;
use serde_json::json;

#[test]
fn normalized_thread_requires_host_created_receipt() {
    let mut p = BridgeParser::default();
    assert!(p.parse(&json!({"type":"bridge_thread","threadId":"thread-1","hostCreated":false,"receipt":{}})).is_err());
    let events = p.parse(&json!({"type":"bridge_thread","threadId":"thread-1","hostCreated":true,"receipt":{"hostCreated":true,"threadId":"thread-1"}})).unwrap();
    assert_eq!(events.len(), 1);
}

#[test]
fn completion_without_actual_model_or_usage_is_not_success() {
    let mut p = BridgeParser::default();
    p.parse(&json!({"type":"bridge_thread","threadId":"thread-1","hostCreated":true,"receipt":{"hostCreated":true,"threadId":"thread-1"}})).unwrap();
    p.parse(&json!({"type":"bridge_complete","success":true,"settled":true,"cleanup":{"status":"verified","root_exited":true,"members_empty":true},"actualModel":null,"usage":{}})).unwrap();
    assert!(!p.successful(Some(0)));
}

#[test]
fn completion_without_terminal_ack_is_not_success() {
    let mut p = BridgeParser::default();
    p.parse(&json!({"type":"bridge_thread","threadId":"thread-1","hostCreated":true,"receipt":{"hostCreated":true,"threadId":"thread-1"}})).unwrap();
    p.parse(&json!({"type":"bridge_complete","success":true,"settled":true,"terminalAcknowledged":false,"cleanup":{"status":"verified","root_exited":true,"members_empty":true},"actualModel":{"provider":"gpt","model":"fixture","effort":"high"},"usage":{"input":1,"output":1,"total_tokens":2}})).unwrap();
    assert!(!p.successful(Some(0)));
}

#[test]
fn unknown_bridge_record_fails_closed() {
    let mut p = BridgeParser::default();
    assert!(p.parse(&json!({"type":"message_update","text":"not normalized"})).is_err());
}

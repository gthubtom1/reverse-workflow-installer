//! Exact matching of explicitly injected credential values only. No environment
//! enumeration, generic secret scanner, or persistent credential store.
use crate::{
    Failure, Result,
    config::{Config, Selection},
};
use serde_json::{Value, json};
use std::{fmt, sync::Arc};
const MASK: &[u8] = b"[REDACTED]";

#[derive(Clone, Copy)]
enum MetadataContext {
    Other,
    Event,
    Message,
    Messages,
    State,
    Model,
}

#[derive(Clone, Default)]
pub(crate) struct Redactions {
    patterns: Arc<Vec<Vec<u8>>>,
    public_selection: Option<Selection>,
}
impl fmt::Debug for Redactions {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Redactions")
            .field("values", &"[REDACTED]")
            .finish()
    }
}
impl Redactions {
    pub fn from_credentials(credentials: &[(String, String)]) -> Self {
        let mut patterns = Vec::new();
        for (_, value) in credentials {
            patterns.push(value.as_bytes().to_vec());
            // A provider diagnostic or Failure.detail may contain JSON-escaped
            // spelling instead of literal bytes. Match this exact spelling too.
            let escaped = serde_json::to_string(value).expect("string serialization");
            patterns.push(escaped.as_bytes()[1..escaped.len() - 1].to_vec());
        }
        patterns.retain(|p| !p.is_empty());
        patterns.sort_by_key(|p| std::cmp::Reverse(p.len()));
        patterns.dedup();
        Self {
            patterns: Arc::new(patterns),
            public_selection: None,
        }
    }
    pub fn from_config(credentials: &[(String, String)], config: &Config) -> Result<Self> {
        config.validate_public_selection()?;
        let mut redactions = Self::from_credentials(credentials);
        redactions.public_selection = config.public_selection.clone();
        Ok(redactions)
    }
    fn matches_message(&self, message: &Value) -> bool {
        // Both assistant effort fields are optional in the official protocol.
        // Missing fields stay absent; a declaration is never reported as actual.
        self.public_selection.as_ref().is_some_and(|selection| {
            message["role"] == "assistant"
                && message["provider"] == selection.provider
                && message["model"] == selection.model
                && ["thinkingLevel", "providerThinkingLevel"]
                    .iter()
                    .all(|key| {
                        message
                            .get(key)
                            .is_none_or(|level| level == &selection.thinking)
                    })
        })
    }
    fn matches_model(&self, model: &Value) -> bool {
        self.public_selection.as_ref().is_some_and(|selection| {
            model["provider"] == selection.provider && model["id"] == selection.model
        })
    }
    fn public_metadata(&self, key: &str, text: &str, context: MetadataContext) -> bool {
        let Some(selection) = &self.public_selection else {
            return false;
        };
        match (context, key) {
            (MetadataContext::Message | MetadataContext::Model, "provider") => {
                text == selection.provider
            }
            (MetadataContext::Message, "model" | "responseModel")
            | (MetadataContext::Model, "id") => text == selection.model,
            (MetadataContext::Message, "thinkingLevel" | "providerThinkingLevel")
            | (MetadataContext::State, "thinkingLevel") => text == selection.thinking,
            _ => false,
        }
    }
    fn untrusted_response_model(&self, key: &str, text: &str, context: MetadataContext) -> bool {
        matches!(context, MetadataContext::Message)
            && key == "responseModel"
            && self.public_selection.is_some()
            && !self.public_metadata(key, text, context)
    }
    pub fn text(&self, text: &str) -> String {
        let mut stream = StreamRedactor::new(self.clone());
        let bytes = stream.feed_inner(text.as_bytes(), true, false);
        // Patterns and the replacement are UTF-8, so matching complete byte
        // sequences cannot invalidate an otherwise valid UTF-8 string.
        String::from_utf8(bytes).expect("redaction preserves UTF-8")
    }
    pub fn active(&self) -> bool {
        !self.patterns.is_empty()
    }
    fn conflicts(&self, text: &str) -> bool {
        self.patterns
            .iter()
            .any(|p| text.as_bytes().windows(p.len()).any(|w| w == p))
    }
    fn control(&self, text: &str) -> Result<()> {
        self.control_role(text, "unknown")
    }
    fn control_role(&self, text: &str, role: &str) -> Result<()> {
        if self.conflicts(text) {
            return Err(Failure::new(
                "credential_control_conflict",
                self.conflict_role(role),
            ));
        }
        Ok(())
    }
    fn conflict_role(&self, role: &str) -> &'static str {
        // Roles are fixed diagnostic schema, never field names or matched text.
        // Do not let full/escaped matches or EOF-prefix masking garble a role.
        for known in [
            "schema",
            "selection",
            "run_identity",
            "tool",
            "resource_path",
            "resume_path",
        ] {
            if role == known && self.payload(known) == known {
                return known;
            }
        }
        "unknown"
    }
    pub(crate) fn failure_detail(&self, failure: &Failure) -> String {
        if failure.code == "credential_control_conflict" {
            self.conflict_role(&failure.detail).into()
        } else {
            self.payload(&failure.detail)
        }
    }
    pub fn check_config(&self, c: &Config) -> Result<()> {
        c.validate_public_selection()?;
        if !self.active() {
            return Ok(());
        }
        // Fixed protocol spelling is never rewritten. Collisions fail before
        // spawn, and failure records themselves retain their stable schema/code.
        for word in [
            "type",
            "event",
            "id",
            "command",
            "success",
            "data",
            "role",
            "content",
            "text",
            "provider",
            "model",
            "thinkingLevel",
            "sessionId",
            "sessionFile",
            "cwd",
            "toolCallId",
            "toolName",
            "status",
            "scope",
            "windows_job",
            "unix_process_group",
            "windows_suspended_child",
            "none",
            "code",
            "detail",
            "message_end",
            "tool_execution_start",
            "tool_execution_end",
            "bridge_progress",
            "bridge_session",
            "bridge_failure",
            "bridge_complete",
            "stop",
            "toolUse",
            "assistant",
            "user",
            "toolResult",
            "verified",
            "unknown",
            "not_started",
            "[REDACTED]",
        ] {
            self.control_role(word, "schema")?;
        }
        if c.public_selection.is_none() {
            for value in [&c.provider, &c.model, &c.thinking] {
                self.control_role(value, "selection")?;
            }
        }
        for value in [&c.cancel.identity.run_id, &c.cancel.identity.turn_id] {
            self.control_role(value, "run_identity")?;
        }
        for name in &c.selected_mcp_tools {
            self.control_role(name, "tool")?;
        }
        for path in [&c.task_cwd, &c.agent_dir, &c.session_dir] {
            self.control_role(&path.to_string_lossy(), "resource_path")?;
        }
        if let Some(path) = &c.session_path {
            self.control_role(&path.to_string_lossy(), "resume_path")?;
        }
        Ok(())
    }
    fn check_metadata(&self, v: &Value) -> Result<()> {
        self.check_metadata_at(v, MetadataContext::Event)
    }
    fn check_metadata_at(&self, v: &Value, context: MetadataContext) -> Result<()> {
        match v {
            Value::Object(map) => {
                for (key, value) in map {
                    self.control(key)?;
                    // These are data, not identity/control metadata. They are either
                    // omitted or normalized separately, never blindly rewritten.
                    if [
                        "content",
                        "args",
                        "arguments",
                        "partialResult",
                        "result",
                        "details",
                        "assistantMessageEvent",
                        "error",
                        "errorMessage",
                        "delta",
                        "text",
                        "thinking",
                    ]
                    .contains(&key.as_str())
                    {
                        continue;
                    }
                    if [
                        "type",
                        "event",
                        "id",
                        "command",
                        "role",
                        "provider",
                        "model",
                        "modelId",
                        "responseModel",
                        "responseId",
                        "thinkingLevel",
                        "providerThinkingLevel",
                        "sessionId",
                        "sessionFile",
                        "cwd",
                        "toolCallId",
                        "toolName",
                        "status",
                        "stopReason",
                        "method",
                        "level",
                        "runId",
                        "turnId",
                        "contract",
                        "scope",
                        "name",
                        "api",
                    ]
                    .contains(&key.as_str())
                    {
                        if let Some(text) = value.as_str() {
                            if !self.public_metadata(key, text, context)
                                && !self.untrusted_response_model(key, text, context)
                            {
                                let role = if [
                                    "provider",
                                    "model",
                                    "modelId",
                                    "responseModel",
                                    "thinkingLevel",
                                    "providerThinkingLevel",
                                ]
                                .contains(&key.as_str())
                                {
                                    "selection"
                                } else {
                                    "unknown"
                                };
                                self.control_role(text, role)?;
                            }
                        }
                    }
                    if value.is_object() || value.is_array() {
                        // Provenance is assigned only from the root event's
                        // concrete protocol paths. Other recursion never inherits
                        // or discovers public status from a key/value spelling.
                        let child = match (context, key.as_str()) {
                            (MetadataContext::Event, "data")
                                if v["type"] == "response"
                                    && v["command"] == "set_model"
                                    && self.matches_model(value) =>
                            {
                                MetadataContext::Model
                            }
                            (MetadataContext::Event, "data")
                                if v["type"] == "response"
                                    && v["command"] == "get_state"
                                    && self.matches_model(&value["model"])
                                    && self
                                        .public_selection
                                        .as_ref()
                                        .is_some_and(|s| value["thinkingLevel"] == s.thinking) =>
                            {
                                MetadataContext::State
                            }
                            (MetadataContext::State, "model") if self.matches_model(value) => {
                                MetadataContext::Model
                            }
                            (MetadataContext::Event, "message")
                                if [
                                    "message_start",
                                    "message_update",
                                    "message_end",
                                    "turn_end",
                                ]
                                .iter()
                                .any(|kind| v["type"] == *kind)
                                    && self.matches_message(value) =>
                            {
                                MetadataContext::Message
                            }
                            (MetadataContext::Event, "messages") if v["type"] == "agent_end" => {
                                MetadataContext::Messages
                            }
                            (MetadataContext::Event, "finalMessage")
                                if v["type"] == "bridge_complete"
                                    && self.matches_message(value) =>
                            {
                                MetadataContext::Message
                            }
                            _ => MetadataContext::Other,
                        };
                        self.check_metadata_at(value, child)?;
                    }
                }
            }
            Value::Array(items) => {
                for item in items {
                    let child = if matches!(context, MetadataContext::Messages)
                        && self.matches_message(item)
                    {
                        MetadataContext::Message
                    } else {
                        MetadataContext::Other
                    };
                    self.check_metadata_at(item, child)?;
                }
            }
            _ => {}
        }
        Ok(())
    }
    pub fn payload(&self, text: &str) -> String {
        let mut stream = StreamRedactor::new(self.clone());
        String::from_utf8(stream.feed(text.as_bytes(), true)).expect("redaction preserves UTF-8")
    }
    fn content(&self, content: &Value) -> Value {
        let mut text = String::new();
        if let Some(value) = content.as_str() {
            text.push_str(value);
        }
        if let Some(parts) = content.as_array() {
            for part in parts {
                if part["type"] == "text" {
                    if let Some(value) = part["text"].as_str() {
                        text.push_str(value);
                    }
                }
            }
        }
        // Join all text parts before matching, rather than redacting each part.
        // Thinking, images, toolcall arguments and opaque details are not exposed
        // while credentials are active. Their identity is carried by tool events.
        json!([{"type":"text","text":self.payload(&text)}])
    }
    pub fn message(&self, message: &Value) -> Result<Value> {
        if !self.active() {
            return Ok(message.clone());
        }
        let context = if self.matches_message(message) {
            MetadataContext::Message
        } else {
            MetadataContext::Other
        };
        self.check_metadata_at(message, context)?;
        let mut output = serde_json::Map::new();
        for key in [
            "role",
            "api",
            "provider",
            "model",
            "responseModel",
            "responseId",
            "thinkingLevel",
            "providerThinkingLevel",
            "stopReason",
            "rawStopReason",
            "endTurn",
            "timestamp",
            "toolCallId",
            "toolName",
            "isError",
        ] {
            if let Some(value) = message.get(key) {
                if self.public_selection.is_some() && (value.is_object() || value.is_array()) {
                    if key == "responseModel" {
                        continue;
                    }
                    return Err(Failure::new(
                        "bad_protocol",
                        "scalar message metadata required",
                    ));
                }
                if let Some(text) = value.as_str() {
                    if self.untrusted_response_model(key, text, context) {
                        output.insert(key.into(), json!(self.payload(text)));
                        continue;
                    }
                    if !self.public_metadata(key, text, context) {
                        self.control(text)?;
                    }
                } else if self.public_selection.is_some() && key == "responseModel" {
                    // A malformed/opaque response model is not public metadata.
                    continue;
                }
                output.insert(key.into(), value.clone());
            }
        }
        output.insert("content".into(), self.content(&message["content"]));
        if let Some(usage) = message.get("usage") {
            // Preserve only numeric usage metadata, not unknown strings/keys.
            let mut safe = serde_json::Map::new();
            for key in [
                "input",
                "output",
                "cacheRead",
                "cacheWrite",
                "totalTokens",
                "cacheWrite1h",
                "reasoning",
            ] {
                if let Some(value) = usage.get(key).filter(|v| v.is_number()) {
                    safe.insert(key.into(), value.clone());
                }
            }
            let mut cost = serde_json::Map::new();
            for key in ["input", "output", "cacheRead", "cacheWrite", "total"] {
                if let Some(value) = usage["cost"].get(key).filter(|v| v.is_number()) {
                    cost.insert(key.into(), value.clone());
                }
            }
            safe.insert("cost".into(), Value::Object(cost));
            output.insert("usage".into(), Value::Object(safe));
        }
        if let Some(error) = message["errorMessage"].as_str() {
            output.insert("errorMessage".into(), json!(self.payload(error)));
        }
        Ok(Value::Object(output))
    }
    pub fn outgoing(&self, v: Value) -> Result<Value> {
        if !self.active() {
            return Ok(v);
        }
        let kind = v["type"].as_str().unwrap_or("");
        if kind == "bridge_failure" {
            let failure = Failure::new(
                v["code"].as_str().unwrap_or(""),
                v["detail"].as_str().unwrap_or(""),
            );
            return Ok(
                json!({"type":"bridge_failure","code":v["code"],"detail":self.failure_detail(&failure)}),
            );
        }
        if kind == "bridge_complete" {
            self.check_metadata(&v)?;
            let mut safe = v;
            if safe["finalMessage"].is_object() {
                safe["finalMessage"] = self.message(&safe["finalMessage"])?;
            }
            if let Some(detail) = safe["cleanup"]["detail"].as_str() {
                safe["cleanup"]["detail"] = json!(self.payload(detail));
            }
            return Ok(safe);
        }
        self.check_metadata(&v)?;
        if kind.starts_with("bridge_") {
            return Ok(v);
        }
        match kind {
            "message_end" => {
                Ok(json!({"type":"message_end","message":self.message(&v["message"])?}))
            }
            "tool_execution_start" => Ok(
                json!({"type":kind,"toolCallId":v["toolCallId"],"toolName":v["toolName"],"args":{}}),
            ),
            "tool_execution_end" => Ok(
                json!({"type":kind,"toolCallId":v["toolCallId"],"toolName":v["toolName"],"isError":v["isError"],"durationMs":v["durationMs"],"result":{"content":self.content(&v["result"]["content"])}}),
            ),
            _ => {
                // Never let independent content fragments, starts, snapshots,
                // turn/agent duplicates, or unknown payloads become a second
                // reconstructable stream. Emit content-free progress instead.
                let mut progress = json!({"type":"bridge_progress","event":kind});
                for key in ["id", "command", "toolCallId", "toolName", "method"] {
                    if let Some(value) = v.get(key) {
                        progress[key] = value.clone();
                    }
                }
                for (key, value) in v.as_object().into_iter().flatten() {
                    if value.is_boolean() || value.is_number() {
                        self.control(key)?;
                        progress[key] = value.clone();
                    }
                }
                Ok(progress)
            }
        }
    }
}

/// Holds only a suffix that might begin a configured value; it is never emitted
/// before the next chunk proves it safe. At EOF even a truncated matching prefix
/// is replaced. State is bounded by the longest explicitly configured pattern.
pub(crate) struct StreamRedactor {
    redactions: Redactions,
    pending: Vec<u8>,
}
impl StreamRedactor {
    pub fn new(redactions: Redactions) -> Self {
        Self {
            redactions,
            pending: Vec::new(),
        }
    }
    pub fn feed(&mut self, chunk: &[u8], eof: bool) -> Vec<u8> {
        self.feed_inner(chunk, eof, true)
    }
    fn feed_inner(&mut self, chunk: &[u8], eof: bool, mask_partial: bool) -> Vec<u8> {
        self.pending.extend_from_slice(chunk);
        let patterns = &self.redactions.patterns;
        let mut output = Vec::new();
        let mut offset = 0;
        while offset < self.pending.len() {
            let tail = &self.pending[offset..];
            let partial = patterns
                .iter()
                .any(|p| tail.len() < p.len() && p.starts_with(tail));
            if partial && !eof {
                break;
            }
            if let Some(pattern) = patterns.iter().find(|p| tail.starts_with(p)) {
                output.extend_from_slice(MASK);
                offset += pattern.len();
            } else if partial && eof && mask_partial {
                output.extend_from_slice(MASK);
                offset = self.pending.len();
            } else {
                output.push(self.pending[offset]);
                offset += 1;
            }
        }
        self.pending.drain(..offset);
        output
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore = "explicit private environment injection required; no child launch"]
    fn native_config_role_preflight_only() {
        // Deliberately no driver::run, Command, provider resource reads or network.
        // Only the authorized native owner pointer and its original driver config
        // are read; all errors are reduced to fixed status words.
        let evidence = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../verification/craft-implementation-2026-11-09");
        let diagnose = || -> std::result::Result<(&'static str, &'static str), &'static str> {
            let bytes =
                std::fs::read(evidence.join("native-real-run/owner-control/execution.json"))
                    .map_err(|_| "pointer_unavailable")?;
            let pointer: Value = serde_json::from_slice(&bytes).map_err(|_| "pointer_invalid")?;
            let root = pointer["run_root"].as_str().ok_or("pointer_invalid")?;
            let candidates: Vec<_> = ["turn-0", "turn-1"]
                .into_iter()
                .map(|turn| std::path::Path::new(root).join(turn).join("driver.json"))
                .filter(|path| path.is_file())
                .collect();
            if candidates.len() != 1 {
                return Err("config_not_unique");
            }
            let mut config = Config::load(&candidates[0]).map_err(|_| "config_rejected")?;
            let credentials = config.credential_environment().map_err(|failure| {
                if failure.code == "credential_env_missing" {
                    "credential_env_missing"
                } else {
                    "credential_env_rejected"
                }
            })?;
            let redactions =
                Redactions::from_config(&credentials, &config).map_err(|_| "config_rejected")?;
            let original_role = match redactions.check_config(&config) {
                Ok(()) => "none",
                Err(failure) => redactions.conflict_role(&failure.detail),
            };
            // Independently supplied public owner selection, not inferred from a
            // credential or written back into the original native config.
            config.public_selection = Some(Selection {
                provider: "magpie".into(),
                model: "gpt/gpt-6.1-sol".into(),
                thinking: "high".into(),
            });
            config.validate().map_err(|_| "declaration_rejected")?;
            let declared = Redactions::from_config(&credentials, &config)
                .map_err(|_| "declaration_rejected")?;
            let declared_role = match declared.check_config(&config) {
                Ok(()) => "none",
                Err(failure) => declared.conflict_role(&failure.detail),
            };
            Ok((original_role, declared_role))
        };
        let (status, role, declared_role) = match diagnose() {
            Ok(("none", declared)) => ("clear", "none", declared),
            Ok((role, declared)) => ("credential_control_conflict", role, declared),
            Err(status) => (status, "unknown", "unknown"),
        };
        let record = json!({"status":status,"role":role,"official_pi_spawns":0,
            "provider_requests":0,"native_run_access":"read_only"});
        let output = evidence.join("driver-control-conflict-report/real-preflight.json");
        assert!(
            std::fs::write(output, record.to_string()).is_ok(),
            "evidence_write_failed"
        );
        println!("{record}");
        let experiment = json!({"original_status":status,"original_role":role,
            "public_selection_declared":true,"exception_role":"selection",
            "declared_status":if declared_role == "none" {"clear"} else {"credential_control_conflict"},
            "declared_role":declared_role,"official_pi_spawns":0,"provider_requests":0,
            "config_change":"in_memory_only","native_run_access":"read_only"});
        assert!(
            std::fs::write(
                evidence.join("driver-control-conflict-report/public-selection-preflight.json"),
                experiment.to_string()
            )
            .is_ok(),
            "evidence_write_failed"
        );
        println!("{experiment}");
        assert!(
            matches!(status, "clear" | "credential_control_conflict"),
            "preflight_unavailable"
        );
        assert_eq!(declared_role, "none", "declared_preflight_rejected");
    }

    #[test]
    fn declared_public_selection_is_exact_metadata_only() {
        let base: Config = serde_json::from_str(include_str!("../config.example.json")).unwrap();
        for field in 0..3 {
            let mut config = base.clone();
            let secret = if field == 2 {
                "high"
            } else {
                "SYNTHETIC_SELECTION_QXZ"
            };
            match field {
                0 => config.provider = secret.into(),
                1 => config.model = secret.into(),
                _ => config.thinking = secret.into(),
            }
            let credentials = [("TEST_KEY".into(), secret.into())];
            let strict = Redactions::from_config(&credentials, &config).unwrap();
            assert_eq!(
                strict.check_config(&config).unwrap_err().detail,
                "selection"
            );
            config.public_selection = Some(Selection {
                provider: config.provider.clone(),
                model: config.model.clone(),
                thinking: config.thinking.clone(),
            });
            let redactions = Redactions::from_config(&credentials, &config).unwrap();
            redactions.check_config(&config).unwrap();
            let body = format!("before {secret} after");
            let message = json!({"role":"assistant","provider":config.provider,
                "model":config.model,"thinkingLevel":config.thinking,
                "providerThinkingLevel":config.thinking,"responseModel":config.model,
                "content":[{"type":"text","text":body}],"errorMessage":body});
            let mut partial = message.clone();
            partial.as_object_mut().unwrap().remove("thinkingLevel");
            for kind in ["message_start", "message_update"] {
                assert!(
                    !redactions
                        .outgoing(json!({"type":kind,"message":partial}))
                        .unwrap()
                        .to_string()
                        .contains(secret)
                );
            }
            let without_thinking = redactions
                .outgoing(json!({"type":"message_end","message":partial}))
                .unwrap();
            assert!(without_thinking["message"].get("thinkingLevel").is_none());
            partial["thinkingLevel"] = json!("low");
            assert_eq!(
                redactions
                    .outgoing(json!({"type":"message_start","message":partial}))
                    .unwrap_err()
                    .detail,
                "selection"
            );
            let safe = redactions.message(&message).unwrap();
            for key in [
                "provider",
                "model",
                "thinkingLevel",
                "providerThinkingLevel",
                "responseModel",
            ] {
                assert_eq!(safe[key], message[key]);
            }
            assert_eq!(safe["content"][0]["text"], "before [REDACTED] after");
            assert_eq!(safe["errorMessage"], "before [REDACTED] after");
            let twice = redactions.message(&safe).unwrap();
            assert_eq!(twice, safe);
            let mut exact_body = message.clone();
            exact_body["content"] = json!([{"type":"text","text":secret}]);
            exact_body["errorMessage"] = json!(secret);
            let exact_safe = redactions.message(&exact_body).unwrap();
            assert_eq!(exact_safe["content"][0]["text"], "[REDACTED]");
            assert_eq!(exact_safe["errorMessage"], "[REDACTED]");
            let final_event = redactions
                .outgoing(json!({"type":"bridge_complete","finalMessage":message}))
                .unwrap();
            assert_eq!(final_event["finalMessage"], safe);
            let delta = redactions
                .outgoing(json!({"type":"message_update","delta":body,
                "message":message,"assistantMessageEvent":{"type":"text_delta","delta":body}}))
                .unwrap();
            assert!(!delta.to_string().contains(secret));
            for snapshot in [
                json!({"type":"turn_end","message":message}),
                json!({"type":"agent_end","messages":[message]}),
            ] {
                assert!(
                    !redactions
                        .outgoing(snapshot)
                        .unwrap()
                        .to_string()
                        .contains(secret)
                );
            }
            // Field names, equal strings, and fake nested protocol shapes cannot
            // manufacture selection provenance inside an arbitrary payload.
            for payload in [
                json!({"provider":secret}),
                json!({"model":secret}),
                json!({"thinkingLevel":secret}),
                json!({"type":"response","command":"get_state","data":{"model":{"provider":config.provider,"id":config.model},"thinkingLevel":config.thinking}}),
            ] {
                assert!(
                    redactions
                        .outgoing(json!({"type":"untrusted_event","payload":payload}))
                        .is_err()
                );
            }
            let tool_body =
                json!({"provider":secret,"model":secret,"thinkingLevel":secret}).to_string();
            let tool = redactions
                .outgoing(json!({"type":"tool_execution_end","toolCallId":"safe-call",
                "toolName":"safe-tool","result":{"content":[{"type":"text","text":tool_body}]}}))
                .unwrap();
            assert!(!tool.to_string().contains(secret));
            assert!(
                tool["result"]["content"][0]["text"]
                    .as_str()
                    .unwrap()
                    .contains("[REDACTED]")
            );
            let error = redactions
                .outgoing(json!({"type":"bridge_failure","code":"provider_failed","detail":body}))
                .unwrap();
            assert_eq!(error["detail"], "before [REDACTED] after");
            let mut physical = message.clone();
            physical["responseModel"] = json!(format!("untrusted-{secret}-physical"));
            assert_eq!(
                redactions.message(&physical).unwrap()["responseModel"],
                "untrusted-[REDACTED]-physical"
            );
            physical["responseModel"] = json!({"opaque":secret});
            assert!(
                redactions
                    .message(&physical)
                    .unwrap()
                    .get("responseModel")
                    .is_none()
            );
            for key in ["provider", "model", "responseId"] {
                let mut opaque = message.clone();
                opaque[key] = json!({"provider":config.provider,"model":config.model});
                assert!(redactions.message(&opaque).is_err());
            }

            // State/model command IDs have selection semantics only at these
            // exact paths; the response correlation ID remains private control.
            for response in [
                json!({"type":"response","command":"set_model","id":"safe-request",
                    "data":{"provider":config.provider,"id":config.model}}),
                json!({"type":"response","command":"get_state","id":"safe-request",
                    "data":{"model":{"provider":config.provider,"id":config.model},"thinkingLevel":config.thinking}}),
            ] {
                redactions.outgoing(response.clone()).unwrap();
                let mut bad = response;
                bad["id"] = json!(secret);
                assert_eq!(
                    redactions.outgoing(bad).unwrap_err().code,
                    "credential_control_conflict"
                );
            }
            let mut undeclared = message;
            let key = ["provider", "model", "thinkingLevel"][field];
            undeclared[key] = json!(format!("{secret}_not_declared"));
            assert_eq!(
                redactions.message(&undeclared).unwrap_err().code,
                "credential_control_conflict"
            );
        }
    }

    #[test]
    fn public_selection_never_exempts_other_control_roles() {
        let base: Config = serde_json::from_str(include_str!("../config.example.json")).unwrap();
        for case in 0..7 {
            let mut config = base.clone();
            let secret = if case == 0 {
                "type"
            } else {
                "SYNTHETIC_SELECTION_QXZ"
            };
            config.model = secret.into();
            let role = match case {
                0 => "schema",
                1 => {
                    config.cancel.identity.run_id = secret.into();
                    "run_identity"
                }
                2 => {
                    config.cancel.identity.turn_id = secret.into();
                    "run_identity"
                }
                3 => {
                    config.selected_mcp_tools = vec![format!("mcp__{secret}")];
                    "tool"
                }
                4 => {
                    config.task_cwd = secret.into();
                    "resource_path"
                }
                5 => {
                    config.agent_dir = secret.into();
                    "resource_path"
                }
                _ => {
                    config.session_path = Some(secret.into());
                    "resume_path"
                }
            };
            config.public_selection = Some(Selection {
                provider: config.provider.clone(),
                model: config.model.clone(),
                thinking: config.thinking.clone(),
            });
            let redactions =
                Redactions::from_config(&[("TEST_KEY".into(), secret.into())], &config).unwrap();
            let error = redactions.check_config(&config).unwrap_err();
            assert_eq!(error.code, "credential_control_conflict");
            assert_eq!(error.detail, role);
        }
        let mut mismatch = base;
        mismatch.public_selection = Some(Selection {
            provider: mismatch.provider.clone(),
            model: "different".into(),
            thinking: mismatch.thinking.clone(),
        });
        assert_eq!(mismatch.validate().unwrap_err().code, "invalid_config");
        let redactions = Redactions::default();
        assert_eq!(
            redactions.check_config(&mismatch).unwrap_err().code,
            "invalid_config"
        );
        assert_eq!(
            Redactions::from_config(&[], &mismatch).unwrap_err().code,
            "invalid_config"
        );
    }

    #[test]
    fn config_conflict_roles_are_fixed_and_secret_safe() {
        let base: Config = serde_json::from_str(include_str!("../config.example.json")).unwrap();
        let sentinel = "SYNTHETIC_CREDENTIAL_SENTINEL_QXZ";
        let redactions = Redactions::from_credentials(&[("TEST_KEY".into(), sentinel.into())]);
        for case in 0..10 {
            let mut config = base.clone();
            let role = match case {
                0 => {
                    config.provider = sentinel.into();
                    "selection"
                }
                1 => {
                    config.model = sentinel.into();
                    "selection"
                }
                2 => {
                    config.thinking = sentinel.into();
                    "selection"
                }
                3 => {
                    config.cancel.identity.run_id = sentinel.into();
                    "run_identity"
                }
                4 => {
                    config.cancel.identity.turn_id = sentinel.into();
                    "run_identity"
                }
                5 => {
                    config.selected_mcp_tools = vec![sentinel.into()];
                    "tool"
                }
                6 => {
                    config.task_cwd = sentinel.into();
                    "resource_path"
                }
                7 => {
                    config.agent_dir = sentinel.into();
                    "resource_path"
                }
                8 => {
                    config.session_dir = sentinel.into();
                    "resource_path"
                }
                _ => {
                    config.session_path = Some(sentinel.into());
                    "resume_path"
                }
            };
            let failure = redactions.check_config(&config).unwrap_err();
            assert_eq!(failure.code, "credential_control_conflict");
            assert_eq!(failure.detail, role);
            let event = redactions
                .outgoing(json!({"type":"bridge_failure",
                "code":failure.code,"detail":failure.detail}))
                .unwrap();
            assert_eq!(event["detail"], role);
            assert!(!event.to_string().contains(sentinel));
            assert!(!format!("{failure:?}").contains(sentinel));
        }
        for role in [
            "schema",
            "selection",
            "run_identity",
            "tool",
            "resource_path",
            "resume_path",
        ] {
            for secret in [role.to_owned(), format!("{role}SYNTHETIC_SUFFIX")] {
                let redactions = Redactions::from_credentials(&[("TEST_KEY".into(), secret)]);
                let failure = redactions.control_role(role, role);
                // Exact role collisions reject; a matching EOF prefix also
                // makes the diagnostic ambiguous, even without a full match.
                assert_eq!(redactions.conflict_role(role), "unknown");
                if let Err(failure) = failure {
                    assert_eq!(redactions.failure_detail(&failure), "unknown");
                    let event = redactions
                        .outgoing(json!({"type":"bridge_failure",
                        "code":failure.code,"detail":failure.detail}))
                        .unwrap();
                    assert_eq!(event["detail"], "unknown");
                }
            }
        }
        assert!(redactions.check_config(&base).is_ok());
        let schema = Redactions::from_credentials(&[("TEST_KEY".into(), "type".into())]);
        assert_eq!(schema.check_config(&base).unwrap_err().detail, "schema");
        for value in ["selection", "on", "own", "unknown", "schema"] {
            let redactions = Redactions::from_credentials(&[("TEST_KEY".into(), value.into())]);
            let failure = redactions.control_role(value, "selection").unwrap_err();
            let expected = if redactions.payload("selection") == "selection" {
                "selection"
            } else {
                "unknown"
            };
            assert_eq!(failure.detail, expected);
            assert_eq!(redactions.failure_detail(&failure), expected);
        }
    }

    #[test]
    fn cloned_redaction_debug_is_opaque_and_complete_field_names_stay_intact() {
        let value: String = ['s', 'y', 'n', 't', 'h', '_', 'd', 'e', 'b', 'u', 'g']
            .into_iter()
            .collect();
        let redactions = Redactions::from_credentials(&[("TEST_CREDENTIAL".into(), value.clone())]);
        assert!(!format!("{:?}", redactions.clone()).contains(&value));
        let record =
            serde_json::json!({"type":"bridge_session","sessionId":"safe_id_s","status":"success"});
        let safe = redactions.outgoing(record.clone()).unwrap();
        assert_eq!(safe, record);
        let message =
            serde_json::json!({"role":"assistant","content":[{"type":"text","text":value}]});
        assert_eq!(
            redactions.message(&message).unwrap()["content"][0]["text"],
            "[REDACTED]"
        );
    }
}

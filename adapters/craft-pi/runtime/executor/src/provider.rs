//! Validate one reviewed, credential-free provider definition. Personal config is never read.
use crate::*;
use craft_anything_engine::execution_policy::{ExecutionPolicy, HashedRef};
use serde_json::Value;

pub fn validate(
    reference: &HashedRef,
    p: &ExecutionPolicy,
    keys: &[String],
) -> Result<Value, ToolError> {
    let path = reference.verify()?;
    let value: Value = serde_json::from_slice(&read_capped(&path)?)
        .map_err(|_| refusal("provider-manifest", "Provider manifest is not JSON."))?;
    let fail = || {
        refusal(
            "provider-manifest",
            "Expected exactly one reviewed provider/model with an explicit environment credential reference, no headers or extra resources.",
        )
    };
    let object = value.as_object().ok_or_else(fail)?;
    if object.len() != 1 {
        return Err(fail());
    }
    let providers = object
        .get("providers")
        .and_then(Value::as_object)
        .ok_or_else(fail)?;
    if providers.len() != 1 {
        return Err(fail());
    }
    let provider = providers
        .get(&p.model.expected.provider)
        .and_then(Value::as_object)
        .ok_or_else(fail)?;
    if provider.keys().any(|k| {
        !["api", "baseUrl", "apiKey", "authHeader", "compat", "models"].contains(&k.as_str())
    }) {
        return Err(fail());
    }
    let credential = provider
        .get("apiKey")
        .and_then(Value::as_str)
        .ok_or_else(fail)?;
    let key = credential
        .strip_prefix("${")
        .and_then(|s| s.strip_suffix('}'))
        .ok_or_else(fail)?;
    if !keys.iter().any(|k| k == key)
        || key.is_empty()
        || !key.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
    {
        return Err(fail());
    }
    let endpoint = provider
        .get("baseUrl")
        .and_then(Value::as_str)
        .ok_or_else(fail)?;
    if !(endpoint.starts_with("https://") || endpoint.starts_with("http://"))
        || endpoint.contains(['@', '?', '#', '\n', '\r'])
    {
        return Err(fail());
    }
    let models = provider
        .get("models")
        .and_then(Value::as_array)
        .ok_or_else(fail)?;
    if models.len() != 1 || models[0]["id"].as_str() != Some(p.model.expected.model.as_str()) {
        return Err(fail());
    }
    fn forbidden(v: &Value, top: bool) -> bool {
        match v {
            Value::Object(o) => o.iter().any(|(k, v)| {
                k.eq_ignore_ascii_case("headers")
                    || (!top && k.eq_ignore_ascii_case("apiKey"))
                    || forbidden(v, false)
            }),
            Value::Array(a) => a.iter().any(|v| forbidden(v, false)),
            _ => false,
        }
    }
    // Provider apiKey is the single permitted location; credentials in nested compat/model
    // objects are rejected, while the complete reviewed API/thinking definition is retained.
    for (k, v) in provider {
        if k != "apiKey" && forbidden(v, false) {
            return Err(fail());
        }
    }
    let model = models[0].as_object().ok_or_else(fail)?;
    let allowed = [
        "id",
        "name",
        "api",
        "reasoning",
        "thinkingLevelMap",
        "input",
        "inputLimits",
        "contextWindow",
        "maxTokens",
        "cost",
        "compat",
        "samplingParams",
        "samplingParamsByThinkingLevel",
    ];
    if model.keys().any(|k| !allowed.contains(&k.as_str())) {
        return Err(fail());
    }
    if !model
        .get("maxTokens")
        .and_then(Value::as_u64)
        .is_some_and(|n| (4096..=8192).contains(&n))
    {
        return Err(refusal(
            "provider-budget",
            "Builder model maxTokens must be explicitly reviewed within 4096..8192 per response.",
        ));
    }
    Ok(value)
}

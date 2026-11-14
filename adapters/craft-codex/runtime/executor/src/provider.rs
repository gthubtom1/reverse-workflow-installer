//! Reviewed stock Codex runtime profile. It contains no API key or copied auth material.
use crate::*;
use craft_anything_engine::execution_policy::{hash_file, read_capped, ExecutionPolicy, HashedRef};
use craft_anything_evidence::ToolError;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use toml::Value as TomlValue;
pub use craft_codex_bridge::config::ConfigInput;
use std::{collections::BTreeMap, fs, path::{Path, PathBuf}};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CodexProfile {
    pub schema_version: u32,
    pub id: String,
    pub runtime: RuntimeProfile,
    pub startup: StartupProfile,
    pub thread: ThreadProfile,
    pub turn: TurnProfile,
    pub dynamic_namespace: String,
    pub operations: Vec<String>,
    #[serde(default)]
    pub runtime_checks: Vec<String>,
    #[serde(default)]
    pub observed_controls: BTreeMap<String, String>,
    #[serde(default)]
    pub qualification_limits: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeProfile {
    pub version: String,
    pub protocol: String,
    pub cli_sha256: String,
    pub os: String,
    pub arch: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StartupProfile {
    pub argv_prefix: Vec<String>,
    pub config: BTreeMap<String, Value>,
    pub disable_features: Vec<String>,
    pub enable_features: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ThreadProfile {
    pub environments: Vec<Value>,
    #[serde(rename = "sandbox")]
    pub sandbox: String,
    #[serde(rename = "approvalPolicy")]
    pub approval_policy: String,
    pub ephemeral: bool,
    #[serde(rename = "allowProviderModelFallback")]
    pub allow_provider_model_fallback: bool,
    #[serde(rename = "experimentalRawEvents")]
    pub experimental_raw_events: bool,
    #[serde(rename = "runtimeWorkspaceRoots")]
    pub runtime_workspace_roots: Vec<String>,
    #[serde(rename = "selectedCapabilityRoots")]
    pub selected_capability_roots: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TurnProfile {
    pub environments: Vec<Value>,
    #[serde(rename = "approvalPolicy")]
    pub approval_policy: String,
}

pub const RUNTIME_PROFILE_ID: &str = "codex-stock-bounded-v1";
pub const PROFILE_SCHEMA_VERSION: u32 = 1;
pub const STOCK_MODE: &str = "stock-app-server-stdio";
pub const DYNAMIC_NAMESPACE: &str = "craft_host";
pub const STOCK_CONFIG_ROOT_ENV: &str = "CRAFT_CODEX_HOME";

fn exact_list(actual: &[String], expected: &[&str]) -> bool {
    actual == expected.iter().map(|value| (*value).to_owned()).collect::<Vec<_>>()
}

fn required_runtime_profile_hash(reference: &HashedRef) -> Result<(), ToolError> {
    if std::env::var("CRAFT_CODEX_RUNTIME_PROFILE_SHA256").ok().as_deref()
        != Some(reference.sha256.as_str())
    {
        return Err(refusal(
            "identity-mismatch",
            "CRAFT_CODEX_RUNTIME_PROFILE_SHA256 differs from the reviewed profile bytes.",
        ));
    }
    Ok(())
}

fn absolute_env(name: &str) -> Result<PathBuf, ToolError> {
    let raw = std::env::var_os(name)
        .ok_or_else(|| refusal("runtime-unavailable", format!("Explicit {name} is required.")))?;
    let path = PathBuf::from(raw);
    if !path.is_absolute() {
        return Err(refusal("runtime-unavailable", format!("{name} must be absolute.")));
    }
    Ok(craft_anything_engine::execution_policy::real(&path)?)
}

pub fn cli_path() -> Result<PathBuf, ToolError> {
    absolute_env("CRAFT_CODEX_CLI")
}

fn hash_native_cli(path: &Path) -> Result<String, ToolError> {
    craft_codex_bridge::config::hash_file(path)
        .map_err(|error| refusal("runtime-unavailable", format!("{}: {}", error.code, error.detail)))
}

pub fn codex_home() -> Result<PathBuf, ToolError> {
    if std::env::var_os(STOCK_CONFIG_ROOT_ENV).is_some() {
        absolute_env(STOCK_CONFIG_ROOT_ENV)
    } else {
        absolute_env("CODEX_HOME")
    }
}

pub fn build_startup_argv(profile: &CodexProfile, mcp_names: &[String]) -> Result<Vec<String>, ToolError> {
    if !exact_list(&profile.startup.argv_prefix, &["app-server", "--stdio"]) {
        return Err(refusal("provider-manifest", "Stock Codex startup argv prefix is not exact."));
    }
    craft_codex_bridge::config::stock_argv(&profile.startup.config, mcp_names)
        .map_err(|error| refusal("provider-manifest", format!("{}: {}", error.code, error.detail)))
}

fn candidate_config_paths(app_root: &Path, codex_home: &Path) -> Result<Vec<PathBuf>, ToolError> {
    let app_root = craft_anything_engine::execution_policy::real_parent(app_root)?;
    let codex_home = craft_anything_engine::execution_policy::real(codex_home)?;
    let mut paths = vec![codex_home.join("config.toml"), codex_home.join("managed_config.toml"), app_root.join("config.toml")];
    if let Some(program_data) = std::env::var_os("PROGRAMDATA") {
        let system_root = PathBuf::from(program_data).join("OpenAI").join("Codex");
        paths.push(system_root.join("config.toml"));
        paths.push(system_root.join("requirements.toml"));
    } else {
        paths.push(PathBuf::from(r"C:\ProgramData\OpenAI\Codex\config.toml"));
        paths.push(PathBuf::from(r"C:\ProgramData\OpenAI\Codex\requirements.toml"));
    }
    let mut current = app_root.as_path();
    loop {
        paths.push(current.join(".codex").join("config.toml"));
        let Some(parent) = current.parent() else { break; };
        if parent == current { break; }
        current = parent;
    }
    paths.sort();
    paths.dedup();
    Ok(paths)
}

pub fn freeze_config_inputs(app_root: &Path, codex_home: &Path) -> Result<Vec<ConfigInput>, ToolError> {
    candidate_config_paths(app_root, codex_home)?
        .into_iter()
        .map(|path| {
            if fs::symlink_metadata(&path).is_ok() {
                let canonical = craft_anything_engine::execution_policy::real(&path)?;
                if !canonical.is_file() || canonical != path {
                    return Err(refusal("path-denied", "Codex configuration input must be a regular canonical file."));
                }
                Ok(ConfigInput {
                    path,
                    exists: true,
                    sha256: Some(hash_file(&canonical)?),
                })
            } else {
                Ok(ConfigInput { path, exists: false, sha256: None })
            }
        })
        .collect()
}

fn mcp_names_from_bytes(bytes: &[u8]) -> Vec<String> {
    let mut names = Vec::new();
    if let Some(document) = String::from_utf8(bytes.to_vec()).ok().and_then(|text| text.parse::<TomlValue>().ok()) {
        if let Some(table) = document.get("mcp_servers").and_then(TomlValue::as_table) {
            names.extend(table.keys().cloned());
        }
    }
    let text = String::from_utf8_lossy(bytes);
    for line in text.lines() {
        let line = line.trim();
        let Some(rest) = line.strip_prefix("[mcp_servers.") else { continue; };
        let Some(name) = rest.strip_suffix(']') else { continue; };
        let name = name.trim_matches(['"', '\'']);
        if !name.is_empty() { names.push(name.to_owned()); }
    }
    names.sort();
    names.dedup();
    names
}

pub fn ambient_mcp_names(app_root: &Path, codex_home: &Path) -> Result<Vec<String>, ToolError> {
    let inputs = freeze_config_inputs(app_root, codex_home)?;
    let mut names = Vec::new();
    for input in inputs.into_iter().filter(|input| input.exists) {
        names.extend(mcp_names_from_bytes(&read_capped(&input.path)?));
    }
    names.sort();
    names.dedup();
    Ok(names)
}

fn validate_profile_shape(profile: &CodexProfile) -> Result<(), ToolError> {
    if profile.schema_version != PROFILE_SCHEMA_VERSION
        || profile.id != RUNTIME_PROFILE_ID
        || profile.runtime.protocol != "app-server-v2"
        || profile.runtime.os != "windows"
        || profile.runtime.arch != "x86_64"
        || profile.dynamic_namespace != DYNAMIC_NAMESPACE
        || profile.operations != craft_codex_bridge::config::BUILDER_TOOLS
            .iter()
            .map(|name| name.strip_prefix("mcp__craft__").unwrap().to_owned())
            .collect::<Vec<_>>()
        || !profile.thread.environments.is_empty()
        || !profile.thread.ephemeral
        || profile.thread.allow_provider_model_fallback
        || profile.thread.experimental_raw_events
        || !profile.thread.runtime_workspace_roots.is_empty()
        || !profile.thread.selected_capability_roots.is_empty()
        || !profile.turn.environments.is_empty()
        || profile.thread.sandbox != "read-only"
        || profile.thread.approval_policy != "never"
        || profile.turn.approval_policy != "never"
    {
        return Err(refusal("provider-manifest", "Stock Codex runtime profile is not exact."));
    }
    let expected_config = json!({
        "agents.enabled": false,
        "web_search": "disabled",
        "approval_policy": "never",
        "sandbox_mode": "read-only",
        "project_doc_max_bytes": 0,
        "skills.include_instructions": false,
        "skills.bundled.enabled": false
    });
    if serde_json::to_value(&profile.startup.config).ok() != Some(expected_config) {
        return Err(refusal("provider-manifest", "Stock Codex startup config is not exact."));
    }
    let expected_disable = [
        "shell_tool", "unified_exec", "multi_agent", "multi_agent_v2", "plugins", "hooks", "apps",
        "browser_use", "browser_use_external", "computer_use", "image_generation", "view_image",
        "skill_search", "plugin_discovery_prefetch", "goals", "code_mode_host", "code_mode",
        "mcp_2026_07_28", "enable_mcp_apps",
    ];
    let expected_enable = ["skip_host_skill_discovery", "omit_skill_descriptions"];
    if !exact_list(&profile.startup.disable_features, &expected_disable)
        || !exact_list(&profile.startup.enable_features, &expected_enable)
        || profile.runtime.version != craft_codex_bridge::config::CODEX_VERSION
        || profile.runtime.cli_sha256.len() != 64
        || !profile.runtime.cli_sha256.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    {
        return Err(refusal("provider-manifest", "Stock Codex runtime identity or feature controls are not exact."));
    }
    Ok(())
}

fn validate_native_config_source(root: &Path) -> Result<(), ToolError> {
    let root = craft_anything_engine::execution_policy::real(root)?;
    let expected = root.join("config.toml");
    if fs::symlink_metadata(&expected).is_ok() {
        let canonical = craft_anything_engine::execution_policy::real(&expected)?;
        if canonical != expected || !canonical.is_file() {
            return Err(refusal("provider-manifest", "Native config.toml must be a canonical regular file."));
        }
    }
    Ok(())
}

pub fn load(reference: &HashedRef, p: &ExecutionPolicy, keys: &[String], hard_cap: bool, _requested_response_tokens: u64) -> Result<CodexProfile, ToolError> {
    required_runtime_profile_hash(reference)?;
    let path = reference.verify()?;
    let profile_path = craft_anything_engine::execution_policy::real(&path)?;
    if let Some(expected) = std::env::var_os("CRAFT_CODEX_RUNTIME_PROFILE") {
        if craft_anything_engine::execution_policy::real(Path::new(&expected))? != profile_path {
            return Err(refusal("identity-mismatch", "CRAFT_CODEX_RUNTIME_PROFILE differs from the prepared profile."));
        }
    }
    let profile: CodexProfile = serde_json::from_slice(&read_capped(&profile_path)?).map_err(|_| refusal("provider-manifest", "Invalid Codex runtime profile JSON."))?;
    validate_profile_shape(&profile)?;
    let cli = cli_path()?;
    if hash_native_cli(&cli)? != profile.runtime.cli_sha256
        || std::env::var("CRAFT_CODEX_CLI_SHA256").ok().as_deref() != Some(profile.runtime.cli_sha256.as_str())
        || std::env::var("CRAFT_CODEX_VERSION").ok().as_deref() != Some(profile.runtime.version.as_str()) {
        return Err(refusal("identity-mismatch", "Actual Codex CLI differs from the reviewed runtime profile."));
    }
    let home = codex_home()?;
    if !home.is_dir() { return Err(refusal("provider-manifest", "Native CODEX_HOME must be an existing directory.")); }
    validate_native_config_source(&home)?;
    let _ = freeze_config_inputs(&p.app_root, &home)?;
    if !keys.is_empty() { return Err(refusal("provider-manifest", "Stock Codex runtime must not receive API key environment names.")); }
    if hard_cap { return Err(refusal("unsupported-budget", "Codex has no qualified native per-response hard cap.")); }
    Ok(profile)
}

use crate::{Failure, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, io::Read, path::{Path, PathBuf}};

pub const CONTRACT_VERSION: u32 = 1;
pub const MAX_TASK: usize = 1024 * 1024;
pub const MAX_RECORD: usize = 1024 * 1024;
pub const MAX_STREAM: usize = 16 * 1024 * 1024;
pub const CODEX_VERSION: &str = "0.167.0-alpha.4.1";
pub const CODEX_MODE: &str = "stock-app-server-stdio";
pub const STOCK_ARGV_PREFIX: &[&str] = &["app-server", "--stdio"];
pub const STOCK_DISABLE_FEATURES: &[&str] = &[
    "shell_tool", "unified_exec", "multi_agent", "multi_agent_v2", "plugins", "hooks", "apps",
    "browser_use", "browser_use_external", "computer_use", "image_generation", "view_image",
    "skill_search", "plugin_discovery_prefetch", "goals", "code_mode_host", "code_mode",
    "mcp_2026_07_28", "enable_mcp_apps",
];
pub const STOCK_ENABLE_FEATURES: &[&str] = &["skip_host_skill_discovery", "omit_skill_descriptions"];
pub const BUILDER_NAMESPACE: &str = "craft_host";
pub const BUILDER_TOOLS: &[&str] = &[
    "mcp__craft__build_files_list",
    "mcp__craft__build_file_read",
    "mcp__craft__build_file_write",
    "mcp__craft__build_file_edit",
    "mcp__craft__build_command_run",
    "mcp__craft__build_checklist",
];

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CodexCommand {
    pub program: PathBuf,
    pub argv: Vec<String>,
    pub sha256: String,
    pub version: String,
    pub mode: String,
    pub auth_mode: String,
    pub config_mode: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct McpCommand { pub program: PathBuf, pub argv: Vec<String>, pub expected_tools: Vec<String> }
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CancelIdentity { pub run_id: String, pub turn_id: String, pub generation: u64, pub token: String }
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Cancel { pub marker: PathBuf, #[serde(flatten)] pub identity: CancelIdentity }
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Deadlines { pub input_ms: u64, pub command_ms: u64, pub turn_ms: u64, pub grace_ms: u64, pub shutdown_ms: u64, pub hard_kill_ms: u64 }
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DynamicToolFunction {
    #[serde(rename = "type")]
    pub kind: String,
    pub name: String,
    pub description: String,
    #[serde(rename = "inputSchema")]
    pub input_schema: serde_json::Value,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DynamicTool {
    #[serde(rename = "type")]
    pub kind: String,
    pub name: String,
    pub description: String,
    pub tools: Vec<DynamicToolFunction>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ConfigInput {
    pub path: PathBuf,
    pub exists: bool,
    pub sha256: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub contract_version: u32,
    pub model_provider: Option<String>,
    pub expected_provider: String,
    pub model: String,
    pub effort: String,
    pub codex: CodexCommand,
    pub task_cwd: PathBuf,
    pub agent_dir: PathBuf,
    pub codex_home: PathBuf,
    pub bundle_root: PathBuf,
    pub thread_receipt: PathBuf,
    pub instructions: String,
    pub dynamic_tools: Vec<DynamicTool>,
    pub mcp: McpCommand,
    pub environments: Vec<serde_json::Value>,
    #[serde(default)] pub denied_native_tools: Vec<String>,
    #[serde(default)] pub disabled_mcp_names: Vec<String>,
    pub runtime_profile_id: String,
    pub runtime_profile_sha256: String,
    pub config_inputs: Vec<ConfigInput>,
    pub cancel: Cancel,
    pub deadlines: Deadlines,
}

pub fn hash_bytes(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }
pub fn hash_file(path: &Path) -> Result<String> {
    let mut file = fs::File::open(path).map_err(|e| Failure::new("read_failed", e))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let size = file.read(&mut buffer).map_err(|e| Failure::new("read_failed", e))?;
        if size == 0 { break; }
        hasher.update(&buffer[..size]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

pub fn stock_startup_config() -> BTreeMap<String, JsonValue> {
    BTreeMap::from([
        ("agents.enabled".to_owned(), JsonValue::Bool(false)),
        ("approval_policy".to_owned(), JsonValue::String("never".to_owned())),
        ("project_doc_max_bytes".to_owned(), JsonValue::from(0)),
        ("sandbox_mode".to_owned(), JsonValue::String("read-only".to_owned())),
        ("skills.bundled.enabled".to_owned(), JsonValue::Bool(false)),
        ("skills.include_instructions".to_owned(), JsonValue::Bool(false)),
        ("web_search".to_owned(), JsonValue::String("disabled".to_owned())),
    ])
}
fn scalar_toml(value: &JsonValue) -> Result<String> {
    match value {
        JsonValue::Bool(value) => Ok(value.to_string()),
        JsonValue::Number(value) => Ok(value.to_string()),
        JsonValue::String(value) => serde_json::to_string(value).map_err(|e| Failure::new("invalid_config", e)),
        _ => Err(Failure::new("invalid_config", "stock startup config values must be scalar")),
    }
}
pub fn startup_config_overrides(config: &BTreeMap<String, JsonValue>) -> Result<Vec<String>> {
    let known = stock_startup_config();
    if config.len() != known.len() || config.keys().any(|key| !known.contains_key(key)) { return Err(Failure::new("invalid_config", "stock startup config controls are incomplete or unknown")); }
    config.iter().map(|(key, value)| Ok(format!("{key}={}", scalar_toml(value)?))).collect()
}

pub fn read_bounded(mut reader: impl Read, limit: usize) -> Result<Vec<u8>> {
    let mut bytes = Vec::new(); reader.by_ref().take(limit as u64 + 1).read_to_end(&mut bytes).map_err(|e| Failure::new("read_failed", e))?;
    if bytes.len() > limit { return Err(Failure::new("input_limit", limit)); } Ok(bytes)
}
pub fn canonical(path: &Path) -> Result<PathBuf> { if !path.is_absolute() { return Err(Failure::new("invalid_config", "absolute paths required")); } fs::canonicalize(path).map_err(|e| Failure::new("path_unavailable", format!("{}: {e}", path.display()))) }
#[cfg(windows)]
fn native_spelling(path: &Path) -> PathBuf {
    use std::path::{Component, Prefix}; let mut it=path.components(); let Some(Component::Prefix(prefix))=it.next() else {return path.to_path_buf()};
    let mut out=match prefix.kind(){Prefix::VerbatimDisk(letter)=>PathBuf::from(format!("{}:\\",letter as char)),Prefix::VerbatimUNC(server,share)=>{let mut s=std::ffi::OsString::from("\\\\");s.push(server);s.push("\\");s.push(share);s.push("\\");PathBuf::from(s)},_=>return path.to_path_buf()}; for c in it{if let Component::Normal(s)=c{out.push(s)}} out
}
#[cfg(not(windows))] fn native_spelling(path: &Path) -> PathBuf { path.to_path_buf() }
pub fn native_path(path: &Path) -> Result<PathBuf> { if !path.is_absolute() || path.to_str().is_none(){return Err(Failure::new("unsupported_launch_path","absolute UTF-8 launch path required"))}; let friendly=native_spelling(path); if canonical(&friendly)? != canonical(path)? {return Err(Failure::new("launch_path_mismatch","native spelling changes canonical identity"))}; Ok(friendly) }
fn exact_id(s: &str) -> bool { !s.is_empty() && s.len() <= 256 && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_' || b == b'.' || b == b'/') }
pub fn validate_mcp_server_name(name: &str) -> Result<()> { if name.is_empty() || name.len() > 128 || !name.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_') { return Err(Failure::new("config_unknown", "MCP server ID cannot be represented by the official dotted override path")); } Ok(()) }
pub fn stock_argv(startup_config: &BTreeMap<String, JsonValue>, disabled_mcp_names: &[String]) -> Result<Vec<String>> {
    let mut argv = STOCK_ARGV_PREFIX.iter().map(|value| (*value).to_owned()).collect::<Vec<_>>();
    for assignment in startup_config_overrides(startup_config)? { argv.extend(["-c".to_owned(), assignment]); }
    argv.extend(["-c".to_owned(), "model_reasoning_effort=\"high\"".to_owned()]);
    for feature in STOCK_DISABLE_FEATURES { argv.extend(["--disable".to_owned(), (*feature).to_owned()]); }
    for feature in STOCK_ENABLE_FEATURES { argv.extend(["--enable".to_owned(), (*feature).to_owned()]); }
    let mut names = disabled_mcp_names.to_vec(); names.sort(); names.dedup();
    for name in names { validate_mcp_server_name(&name)?; argv.extend(["-c".to_owned(), format!("mcp_servers.{name}.enabled=false")]); }
    Ok(argv)
}

fn validate_config_inputs(inputs: &mut [ConfigInput]) -> Result<()> {
    for input in inputs {
        if !input.path.is_absolute() { return Err(Failure::new("invalid_config", "configuration input paths must be absolute")); }
        let present = fs::symlink_metadata(&input.path).is_ok();
        if present != input.exists { return Err(Failure::new("identity_mismatch", "Codex configuration layer appeared or disappeared")); }
        if input.exists {
            let canonical = canonical(&input.path)?;
            if canonical != input.path { input.path = canonical.clone(); }
            if !canonical.is_file() { return Err(Failure::new("path_denied", "Codex configuration layer must be a canonical regular file")); }
            let expected = input.sha256.as_ref().ok_or_else(|| Failure::new("invalid_config", "present configuration input lacks hash"))?;
            if hash_file(&canonical)? != *expected { return Err(Failure::new("identity_mismatch", "Codex configuration layer changed")); }
        } else if input.sha256.is_some() { return Err(Failure::new("invalid_config", "absent configuration input cannot have a hash")); }
    }
    Ok(())
}
impl Config {
    pub fn load(path: &Path) -> Result<Self> { let bytes=read_bounded(fs::File::open(path).map_err(|e|Failure::new("config_unavailable",e))?,MAX_TASK)?; let mut c:Self=serde_json::from_slice(&bytes).map_err(|e|Failure::new("invalid_config",e))?; c.validate()?; Ok(c) }
    pub fn validate(&mut self) -> Result<()> {
        if self.contract_version != CONTRACT_VERSION || self.model.is_empty() || self.instructions.trim().is_empty() || self.instructions.len()>65536 {return Err(Failure::new("invalid_config","invalid contract/model/instructions"))}
        if self.model.chars().any(char::is_whitespace) || !exact_id(&self.expected_provider) || self.model_provider.as_ref().is_some_and(|p|!exact_id(p)) || self.model.contains([':','*','\n','\r',',']) || !["off","minimal","low","medium","high","xhigh","max"].contains(&self.effort.as_str()){return Err(Failure::new("invalid_config","exact model/provider/effort required"))}
        if !self.environments.is_empty(){return Err(Failure::new("invalid_config","app-server environment access must be empty"))}
        if self.denied_native_tools.iter().any(|n|n!="request_user_input"){return Err(Failure::new("invalid_config","only request_user_input may be visible-but-always-denied"))}
        if self.codex.version!=CODEX_VERSION || self.codex.mode!=CODEX_MODE || self.codex.auth_mode!="native-codex-home" || self.codex.config_mode!="native-profile" || self.runtime_profile_id!="codex-stock-bounded-v1" || self.runtime_profile_sha256.len()!=64 || !self.runtime_profile_sha256.bytes().all(|b|b.is_ascii_hexdigit() && !b.is_ascii_uppercase()){return Err(Failure::new("invalid_config","unsupported stock Codex runtime profile"))}
        if self.codex.sha256.len()!=64 || !self.codex.sha256.bytes().all(|b|b.is_ascii_hexdigit()){return Err(Failure::new("invalid_config","CLI sha256 required"))}
        if self.codex.argv!=stock_argv(&stock_startup_config(), &self.disabled_mcp_names)?{return Err(Failure::new("invalid_config","Codex argv must equal the fixed stock profile argv"))}
        validate_config_inputs(&mut self.config_inputs)?;
        self.codex.program=canonical(&self.codex.program).map_err(|e|Failure::new("runtime_unavailable",e.detail))?; if !self.codex.program.is_file(){return Err(Failure::new("runtime_unavailable","Codex CLI unavailable"))}; if hash_file(&self.codex.program)? != self.codex.sha256 {return Err(Failure::new("identity_mismatch","Codex CLI bytes differ from profile"))}
        for p in [&mut self.task_cwd,&mut self.agent_dir,&mut self.codex_home,&mut self.bundle_root]{*p=canonical(p)?; if !p.is_dir(){return Err(Failure::new("invalid_config","owned directory missing"))}; native_path(p)?;}
        if self.codex_home.starts_with(&self.task_cwd)||self.bundle_root.starts_with(&self.task_cwd){return Err(Failure::new("path_denied","Codex profile/bundle root overlaps task root"))}
        if !self.thread_receipt.is_absolute()||self.thread_receipt.starts_with(&self.task_cwd)||self.thread_receipt.starts_with(&self.agent_dir){return Err(Failure::new("path_denied","thread receipt overlaps task/agent root"))}
        if self.dynamic_tools.len()!=1 || self.dynamic_tools[0].kind!="namespace" || self.dynamic_tools[0].name!=BUILDER_NAMESPACE || self.dynamic_tools[0].tools.len()!=BUILDER_TOOLS.len() || self.dynamic_tools[0].tools.iter().map(|t|format!("mcp__craft__{}",t.name)).collect::<Vec<_>>()!=BUILDER_TOOLS || self.dynamic_tools[0].tools.iter().any(|t|t.kind!="function"){return Err(Failure::new("tool_denied","exact craft_host namespace and six bounded tools required"))}
        self.mcp.program=canonical(&self.mcp.program)?; if !self.mcp.program.is_file(){return Err(Failure::new("runtime_unavailable","MCP executable unavailable"))}; native_path(&self.mcp.program)?; if self.mcp.argv.iter().any(|a|a.contains(['\n','\r'])){return Err(Failure::new("invalid_config","MCP argument line break"))}
        let parent=canonical(self.cancel.marker.parent().ok_or_else(||Failure::new("invalid_config","cancel parent missing"))?)?; self.cancel.marker=parent.join(self.cancel.marker.file_name().ok_or_else(||Failure::new("invalid_config","cancel marker missing"))?); if parent.starts_with(&self.task_cwd)||parent.starts_with(&self.agent_dir){return Err(Failure::new("path_denied","cancel root overlaps owned roots"))}
        for s in [&self.cancel.identity.run_id,&self.cancel.identity.turn_id,&self.cancel.identity.token]{if s.len()<16||s.len()>256||!exact_id(s){return Err(Failure::new("invalid_config","owner cancellation identity invalid"))}}
        for ms in [self.deadlines.input_ms,self.deadlines.command_ms,self.deadlines.turn_ms,self.deadlines.grace_ms,self.deadlines.shutdown_ms,self.deadlines.hard_kill_ms]{if !(10..=86_400_000).contains(&ms){return Err(Failure::new("invalid_config","deadline outside bounds"))}}
        Ok(())
    }
    pub fn cancelled(&self)->Result<bool>{let file=match fs::File::open(&self.cancel.marker){Ok(f)=>f,Err(e) if e.kind()==std::io::ErrorKind::NotFound=>return Ok(false),Err(e)=>return Err(Failure::new("cancel_unreadable",e))};let id:CancelIdentity=serde_json::from_slice(&read_bounded(file,4096)?).map_err(|e|Failure::new("cancel_invalid",e))?;Ok(id==self.cancel.identity)}
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn startup_controls_are_scalar_assignments() {
        let values = startup_config_overrides(&stock_startup_config()).unwrap();
        assert_eq!(values.len(), 7);
        assert!(values.contains(&"agents.enabled=false".to_owned()));
        assert!(values.contains(&"project_doc_max_bytes=0".to_owned()));
        assert!(values.contains(&"web_search=\"disabled\"".to_owned()));
    }
    #[test]
    fn hash_file_matches_hash_bytes_without_a_size_cap() {
        let path = std::env::temp_dir().join(format!("craft-codex-hash-{}.bin", std::process::id()));
        let bytes = vec![0x5au8; 128 * 1024];
        fs::write(&path, &bytes).unwrap();
        assert_eq!(hash_file(&path).unwrap(), hash_bytes(&bytes));
        let _ = fs::remove_file(path);
    }

    #[test]
    fn dotted_or_path_like_mcp_ids_fail_closed() {
        assert!(validate_mcp_server_name("craft-server").is_ok());
        assert!(validate_mcp_server_name("server.with.dot").is_err());
        assert!(validate_mcp_server_name("server/name").is_err());
    }
}

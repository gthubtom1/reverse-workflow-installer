use crate::{Failure, Result};
use serde::{Deserialize, Serialize};
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
};

pub const MAX_TASK: usize = 1024 * 1024;
pub const MAX_RECORD: usize = 1024 * 1024;
pub const MAX_STREAM: usize = 16 * 1024 * 1024;
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PiCommand {
    pub program: PathBuf,
    pub argv: Vec<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CancelIdentity {
    pub run_id: String,
    pub turn_id: String,
    pub generation: u64,
    pub token: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Cancel {
    pub marker: PathBuf,
    #[serde(flatten)]
    pub identity: CancelIdentity,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Deadlines {
    pub input_ms: u64,
    pub command_ms: u64,
    pub turn_ms: u64,
    pub grace_ms: u64,
    pub shutdown_ms: u64,
    pub hard_kill_ms: u64,
}
/// Independently public selection declared by the policy owner, never a key.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Selection {
    pub provider: String,
    pub model: String,
    pub thinking: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub provider: String,
    pub model: String,
    pub thinking: String,
    /// Explicit publication of this exact triple; omission preserves strict refusal.
    #[serde(default)]
    pub public_selection: Option<Selection>,
    pub pi: PiCommand,
    pub task_cwd: PathBuf,
    pub agent_dir: PathBuf,
    pub session_dir: PathBuf,
    pub session_path: Option<PathBuf>,
    /// Literal, reviewed instructions, not an implicit file include.
    pub instructions: String,
    pub selected_mcp_tools: Vec<String>,
    /// Explicit names resolved from the driver process environment, never values.
    #[serde(default)]
    pub credential_env_keys: Vec<String>,
    pub cancel: Cancel,
    pub deadlines: Deadlines,
}
pub fn read_bounded(mut reader: impl Read, limit: usize) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    reader
        .by_ref()
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| Failure::new("read_failed", e))?;
    if bytes.len() > limit {
        return Err(Failure::new("input_limit", limit));
    }
    Ok(bytes)
}
pub fn canonical(path: &Path) -> Result<PathBuf> {
    if !path.is_absolute() {
        return Err(Failure::new("invalid_config", "absolute paths required"));
    }
    fs::canonicalize(path)
        .map_err(|e| Failure::new("path_unavailable", format!("{}: {e}", path.display())))
}
// Derive a Win32/Node-friendly spelling using parsed prefixes, never blind text
// trimming. The public checked conversion below proves it resolves to the same
// canonical identity, including drive and UNC roots and unusual path segments.
#[cfg(windows)]
fn native_spelling(path: &Path) -> PathBuf {
    use std::path::{Component, Prefix};
    let mut components = path.components();
    let Some(Component::Prefix(prefix)) = components.next() else {
        return path.to_path_buf();
    };
    let mut friendly = match prefix.kind() {
        Prefix::VerbatimDisk(letter) => PathBuf::from(format!("{}:\\", letter as char)),
        Prefix::VerbatimUNC(server, share) => {
            let mut root = std::ffi::OsString::from("\\\\");
            root.push(server);
            root.push("\\");
            root.push(share);
            root.push("\\");
            PathBuf::from(root)
        }
        _ => return path.to_path_buf(),
    };
    for component in components {
        match component {
            Component::RootDir => {}
            Component::Normal(segment) => friendly.push(segment),
            _ => return path.to_path_buf(),
        }
    }
    friendly
}
#[cfg(not(windows))]
fn native_spelling(path: &Path) -> PathBuf {
    path.to_path_buf()
}

pub fn native_path(path: &Path) -> Result<PathBuf> {
    if !path.is_absolute() || path.to_str().is_none() {
        return Err(Failure::new(
            "unsupported_launch_path",
            "absolute UTF-8 launch path required",
        ));
    }
    #[cfg(windows)]
    {
        use std::path::{Component, Prefix};
        if !matches!(path.components().next(),Some(Component::Prefix(prefix)) if matches!(prefix.kind(),Prefix::Disk(_) | Prefix::UNC(_,_) | Prefix::VerbatimDisk(_) | Prefix::VerbatimUNC(_,_)))
        {
            return Err(Failure::new(
                "unsupported_launch_path",
                "unsupported Windows device/verbatim namespace",
            ));
        }
    }
    let friendly = native_spelling(path);
    if !friendly.is_absolute() || canonical(&friendly)? != canonical(path)? {
        return Err(Failure::new(
            "launch_path_mismatch",
            "native spelling changes canonical path identity",
        ));
    }
    Ok(friendly)
}
impl Config {
    pub fn load(path: &Path) -> Result<Self> {
        let bytes = read_bounded(
            fs::File::open(path).map_err(|e| Failure::new("config_unavailable", e))?,
            MAX_TASK,
        )?;
        let mut config: Self =
            serde_json::from_slice(&bytes).map_err(|e| Failure::new("invalid_config", e))?;
        config.validate()?;
        Ok(config)
    }
    pub(crate) fn validate_public_selection(&self) -> Result<()> {
        if let Some(selection) = &self.public_selection {
            if selection.provider != self.provider
                || selection.model != self.model
                || selection.thinking != self.thinking
            {
                return Err(Failure::new(
                    "invalid_config",
                    "public selection must equal the complete configured selection",
                ));
            }
        }
        Ok(())
    }
    pub fn validate(&mut self) -> Result<()> {
        self.validate_public_selection()?;
        self.validate_credential_env_keys()?;
        let invalid = |s| Failure::new("invalid_config", s);
        if self.provider.is_empty()
            || self
                .provider
                .chars()
                .any(|c| !c.is_ascii_alphanumeric() && c != '-' && c != '_')
            || self.model.is_empty()
            || self.model.contains([':', '*', '\n', '\r', ','])
            || self.model.chars().any(char::is_whitespace)
        {
            return Err(invalid("exact provider/model without suffix required"));
        }
        if !["off", "minimal", "low", "medium", "high", "xhigh", "max"]
            .contains(&self.thinking.as_str())
        {
            return Err(invalid("invalid thinking level"));
        }
        for path in [
            &mut self.task_cwd,
            &mut self.agent_dir,
            &mut self.session_dir,
        ] {
            *path = canonical(path)?;
            if !path.is_dir() {
                return Err(invalid("directories must already exist"));
            }
            native_path(path)?;
        }
        for (left, right) in [
            (&self.agent_dir, &self.task_cwd),
            (&self.session_dir, &self.task_cwd),
            (&self.agent_dir, &self.session_dir),
        ] {
            if left.starts_with(right) || right.starts_with(left) {
                return Err(invalid("task/agent/session roots must not overlap"));
            }
        }
        if self
            .pi
            .program
            .extension()
            .and_then(|s| s.to_str())
            .is_some_and(|s| s.eq_ignore_ascii_case("cmd") || s.eq_ignore_ascii_case("bat"))
        {
            return Err(invalid(
                "shell wrappers unsupported; use an executable or node JS entry script",
            ));
        }
        self.pi.program = canonical(&self.pi.program)
            .map_err(|e| Failure::new("runtime_unavailable", e.detail))?;
        if !self.pi.program.is_file() {
            return Err(invalid("Pi executable unavailable"));
        }
        native_path(&self.pi.program)?;
        // Only a node/bun entry script prefix is supported. No caller-supplied Pi flags,
        // shells, SSH, inline code or command strings cross this boundary.
        let stem = self
            .pi
            .program
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        if ["ssh", "sh", "bash", "cmd", "powershell", "pwsh"].contains(&stem.as_str()) {
            return Err(invalid("shell/SSH transport unsupported"));
        }
        if !self.pi.argv.is_empty() {
            if !["node", "bun"].contains(&stem.as_str()) || self.pi.argv.len() != 1 {
                return Err(invalid(
                    "unsupported Pi argv; only node/bun + absolute JS entry script",
                ));
            }
            let script = canonical(Path::new(&self.pi.argv[0]))
                .map_err(|e| Failure::new("runtime_unavailable", e.detail))?;
            if !script.is_file()
                || ![Some("js"), Some("mjs"), Some("cjs")]
                    .contains(&script.extension().and_then(|s| s.to_str()))
            {
                return Err(invalid("invalid JS entry script"));
            }
            // Keep the canonical identity check above, but Node's entry argv
            // must use the equivalent ordinary drive/UNC absolute spelling.
            self.pi.argv[0] = native_path(&script)?.to_string_lossy().into();
        }
        if self.instructions.trim().is_empty() || self.instructions.len() > 65536 {
            return Err(invalid("reviewed instructions required (max 64KiB)"));
        }
        // Pi interprets an existing path as a file. Refuse that ambiguity.
        if Path::new(&self.instructions).is_file()
            || self.task_cwd.join(&self.instructions).is_file()
        {
            return Err(invalid(
                "instructions must be literal text, not an existing file path",
            ));
        }
        if self.selected_mcp_tools.is_empty()
            || self.selected_mcp_tools.iter().any(|s| {
                !s.starts_with("mcp__")
                    || s.len() > 256
                    || s.chars().any(|c| !c.is_ascii_alphanumeric() && c != '_')
            })
        {
            return Err(invalid(
                "exact MCP tool names required; no patterns or native tools",
            ));
        }
        if let Some(p) = self.session_path.as_mut() {
            *p = canonical(p)
                .map_err(|_| Failure::new("session_missing", "explicit session file absent"))?;
            if !p.starts_with(&self.session_dir) {
                return Err(invalid("session outside owned root"));
            }
            native_path(p)?;
        }
        let parent = self
            .cancel
            .marker
            .parent()
            .ok_or_else(|| invalid("cancel parent missing"))?;
        let parent = canonical(parent)?;
        let name = self
            .cancel
            .marker
            .file_name()
            .ok_or_else(|| invalid("invalid marker name"))?;
        self.cancel.marker = parent.join(name);
        if parent.starts_with(&self.task_cwd)
            || parent.starts_with(&self.agent_dir)
            || parent.starts_with(&self.session_dir)
        {
            return Err(invalid(
                "control directory must be separate from task/agent/session roots",
            ));
        }
        let id = &self.cancel.identity;
        if [&id.run_id, &id.turn_id, &id.token].iter().any(|s| {
            s.len() < 16
                || s.len() > 256
                || s.chars()
                    .any(|c| !c.is_ascii_alphanumeric() && c != '-' && c != '_')
        }) {
            return Err(invalid(
                "owner-generated run/turn IDs and token (16..256 characters) required",
            ));
        }
        for ms in [
            self.deadlines.input_ms,
            self.deadlines.command_ms,
            self.deadlines.turn_ms,
            self.deadlines.grace_ms,
            self.deadlines.shutdown_ms,
            self.deadlines.hard_kill_ms,
        ] {
            if !(10..=86_400_000).contains(&ms) {
                return Err(invalid("deadlines must be 10ms..24h"));
            }
        }
        Ok(())
    }
    fn validate_credential_env_keys(&self) -> Result<()> {
        if self.credential_env_keys.len() > 32 {
            return Err(Failure::new(
                "invalid_credential_env_key",
                "at most 32 credential environment names are supported",
            ));
        }
        let mut seen = std::collections::HashSet::new();
        for key in &self.credential_env_keys {
            let mut bytes = key.bytes();
            if key.len() > 128
                || !bytes
                    .next()
                    .is_some_and(|c| c.is_ascii_alphabetic() || c == b'_')
                || bytes.any(|c| !c.is_ascii_alphanumeric() && c != b'_')
            {
                // Do not echo malformed input: it might be a pasted credential value.
                return Err(Failure::new(
                    "invalid_credential_env_key",
                    "credential names must match [A-Za-z_][A-Za-z0-9_]* (1..128 bytes)",
                ));
            }
            let upper = key.to_ascii_uppercase();
            if !seen.insert(upper.clone()) {
                return Err(Failure::new(
                    "invalid_credential_env_key",
                    "duplicate credential environment name",
                ));
            }
            if [
                "PI_",
                "NODE_",
                "LD_",
                "DYLD_",
                "XDG_",
                "PYTHON",
                "GIT_CONFIG",
            ]
            .iter()
            .any(|prefix| upper.starts_with(prefix))
                || [
                    "PATH",
                    "PATHEXT",
                    "SYSTEMROOT",
                    "SYSTEMDRIVE",
                    "WINDIR",
                    "COMSPEC",
                    "TEMP",
                    "TMP",
                    "TMPDIR",
                    "LANG",
                    "LC_ALL",
                    "LC_CTYPE",
                    "HOME",
                    "USERPROFILE",
                    "APPDATA",
                    "LOCALAPPDATA",
                    "PROGRAMDATA",
                    "BASH_ENV",
                    "ENV",
                    "SHELLOPTS",
                    "ZDOTDIR",
                    "__COMPAT_LAYER",
                ]
                .contains(&upper.as_str())
            {
                return Err(Failure::new(
                    "reserved_credential_env_key",
                    format!("reserved environment name: {key}"),
                ));
            }
        }
        Ok(())
    }
    pub(crate) fn credential_environment(&self) -> Result<Vec<(String, String)>> {
        // Validate before any lookup, including when used outside Config::load.
        self.validate_credential_env_keys()?;
        let mut environment = Vec::with_capacity(self.credential_env_keys.len());
        let mut total_bytes = 0usize;
        for key in &self.credential_env_keys {
            let value = std::env::var_os(key)
                .filter(|v| !v.is_empty())
                .ok_or_else(|| {
                    Failure::new(
                        "credential_env_missing",
                        format!(
                            "required credential environment variable is missing or empty: {key}"
                        ),
                    )
                })?;
            let value = value.into_string().map_err(|_| {
                Failure::new(
                    "credential_env_invalid_value",
                    "credential environment values must be UTF-8",
                )
            })?;
            total_bytes += value.len();
            if value.len() > 16 * 1024 || total_bytes > 64 * 1024 {
                return Err(Failure::new(
                    "credential_env_invalid_value",
                    "credential values exceed the 16KiB each / 64KiB total bound",
                ));
            }
            environment.push((key.clone(), value));
        }
        Ok(environment)
    }
    pub fn pi_args(&self) -> Vec<String> {
        let mut a = self.pi.argv.clone();
        for s in [
            "--mode",
            "rpc",
            "--provider",
            &self.provider,
            "--model",
            &self.model,
            "--thinking",
            &self.thinking,
            "--session-dir",
            &native_spelling(&self.session_dir).to_string_lossy(),
            "--no-approve",
            "--no-context-files",
            "--no-skills",
            "--no-prompt-templates",
            "--no-extensions",
            "--offline",
            "-e",
            "builtin:mcp",
            "--tools",
            &self.selected_mcp_tools.join(","),
            "--append-system-prompt",
            &self.instructions,
        ] {
            a.push(s.into());
        }
        if let Some(p) = &self.session_path {
            a.extend([
                "--session".into(),
                native_spelling(p).to_string_lossy().into(),
            ]);
        }
        a
    }
    pub fn cancelled(&self) -> Result<bool> {
        let file = match fs::File::open(&self.cancel.marker) {
            Ok(f) => f,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(false),
            Err(e) => return Err(Failure::new("cancel_unreadable", e)),
        };
        let b = read_bounded(file, 4096)?;
        let id: CancelIdentity =
            serde_json::from_slice(&b).map_err(|e| Failure::new("cancel_invalid", e))?;
        Ok(id == self.cancel.identity)
    }
}

#[cfg(all(test, windows))]
mod path_tests {
    use super::*;
    #[test]
    fn parsed_verbatim_drive_and_unc_spellings_preserve_absolute_roots() {
        assert_eq!(
            native_spelling(Path::new(r"\\?\D:\folder\entry.cjs")),
            PathBuf::from(r"D:\folder\entry.cjs")
        );
        assert_eq!(
            native_spelling(Path::new(r"\\?\UNC\server\share\folder\entry.cjs")),
            PathBuf::from(r"\\server\share\folder\entry.cjs")
        );
        assert_eq!(
            native_spelling(Path::new(r"\\server\share\folder\entry.cjs")),
            PathBuf::from(r"\\server\share\folder\entry.cjs")
        );
        assert!(
            native_path(Path::new(
                r"\\?\GLOBALROOT\Device\HarddiskVolume1\entry.cjs"
            ))
            .is_err()
        );
    }
}

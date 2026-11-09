use crate::{
    Failure, Result,
    config::{Config, MAX_RECORD, MAX_STREAM, canonical},
    framing::Framer,
};
use serde_json::{Value, json};
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
};
#[derive(Clone, Debug)]
pub struct Session {
    pub id: String,
    pub path: PathBuf,
    pub verified: bool,
}
impl Session {
    pub fn from_state(c: &Config, state: &Value) -> Result<Self> {
        for (actual, expected) in [
            (&state["model"]["provider"], &c.provider),
            (&state["model"]["id"], &c.model),
            (&state["thinkingLevel"], &c.thinking),
        ] {
            if actual.as_str() != Some(expected) {
                return Err(Failure::new(
                    "model_mismatch",
                    "get_state model/provider/thinking differs",
                ));
            }
        }
        if state["isStreaming"] != false
            || state["isCompacting"] != false
            || state["pendingMessageCount"] != 0
        {
            return Err(Failure::new(
                "session_busy",
                "session must be idle and queue empty",
            ));
        }
        let id = state["sessionId"]
            .as_str()
            .filter(|s| !s.is_empty())
            .ok_or_else(|| Failure::new("session_mismatch", "missing sessionId"))?
            .to_owned();
        let path = PathBuf::from(
            state["sessionFile"]
                .as_str()
                .ok_or_else(|| Failure::new("session_missing", "get_state missing sessionFile"))?,
        );
        if !path.is_absolute() || path.extension().and_then(|s| s.to_str()) != Some("jsonl") {
            return Err(Failure::new(
                "session_mismatch",
                "absolute JSONL session path required",
            ));
        }
        let resolved = if path.exists() {
            canonical(&path)?
        } else {
            let parent = canonical(
                path.parent()
                    .ok_or_else(|| Failure::new("session_mismatch", "session parent absent"))?,
            )?;
            parent.join(
                path.file_name()
                    .ok_or_else(|| Failure::new("session_mismatch", "session filename absent"))?,
            )
        };
        if !resolved.starts_with(&c.session_dir) {
            return Err(Failure::new(
                "session_mismatch",
                "session escapes owned root",
            ));
        }
        if c.session_path.as_ref().is_some_and(|p| p != &resolved) {
            return Err(Failure::new(
                "session_mismatch",
                "Pi opened a different session file",
            ));
        }
        if c.session_path.is_none() && resolved.exists() {
            return Err(Failure::new(
                "session_mismatch",
                "new session unexpectedly points to persisted history",
            ));
        }
        let mut s = Self {
            id,
            path: resolved,
            verified: false,
        };
        if c.session_path.is_some() || s.path.exists() {
            s.verify(c)?;
        }
        Ok(s)
    }
    pub fn verify(&mut self, c: &Config) -> Result<()> {
        validate_file(&self.path, Some(&self.id), c)?;
        self.verified = true;
        Ok(())
    }
    pub fn event(&self, c: &Config) -> Value {
        json!({"type":"bridge_session","contract":"craft-pi-bridge.v1","sessionId":self.id,"sessionFile":self.path,"cwd":c.task_cwd,"headerVerified":self.verified,"runId":c.cancel.identity.run_id,"turnId":c.cancel.identity.turn_id})
    }
}
pub fn validate_file(path: &Path, id: Option<&str>, c: &Config) -> Result<()> {
    let real = canonical(path).map_err(|_| Failure::new("session_missing", path.display()))?;
    if !real.starts_with(&c.session_dir) {
        return Err(Failure::new(
            "session_mismatch",
            "session real path escapes owned root",
        ));
    }
    let mut file = fs::File::open(real).map_err(|e| Failure::new("session_missing", e))?;
    let mut framer = Framer::new(MAX_RECORD, MAX_STREAM);
    let mut buf = [0u8; 8192];
    let mut header = None;
    loop {
        let n = file
            .read(&mut buf)
            .map_err(|e| Failure::new("session_read_failed", e))?;
        if n == 0 {
            break;
        }
        for v in framer
            .feed(&buf[..n])
            .map_err(|e| Failure::new("session_corrupt", e.detail))?
        {
            if header.is_none() {
                header = Some(v);
            }
        }
    }
    framer
        .finish()
        .map_err(|e| Failure::new("session_corrupt", e.detail))?;
    let h = header.ok_or_else(|| Failure::new("session_corrupt", "empty session file"))?;
    if h["type"] != "session"
        || h["version"] != 3
        || h["id"].as_str().is_none_or(str::is_empty)
        || id.is_some_and(|id| h["id"] != id)
    {
        return Err(Failure::new(
            "session_mismatch",
            "header type/version/id differs",
        ));
    }
    let cwd = h["cwd"]
        .as_str()
        .ok_or_else(|| Failure::new("session_mismatch", "header cwd missing"))?;
    if canonical(Path::new(cwd))? != c.task_cwd {
        return Err(Failure::new(
            "session_mismatch",
            "header cwd differs from task cwd",
        ));
    }
    Ok(())
}

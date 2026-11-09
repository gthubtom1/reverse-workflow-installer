//! Read-only names admission aligned with frozen bridge Config::validate_credential_env_keys.
//! The bridge revalidates at launch. No environment values are read or rendered here.
use craft_anything_engine::execution_policy::refusal;
use craft_anything_evidence::ToolError;
pub fn validate(keys: &[String]) -> Result<(), ToolError> {
    let fail = || {
        refusal(
            "invalid-credential-env-name",
            "Credential environment names violate the fixed driver allowlist contract.",
        )
    };
    if keys.len() > 32 {
        return Err(fail());
    }
    let mut seen = std::collections::HashSet::new();
    for key in keys {
        let mut bytes = key.bytes();
        if key.len() > 128
            || !bytes
                .next()
                .is_some_and(|b| b.is_ascii_alphabetic() || b == b'_')
            || bytes.any(|b| !b.is_ascii_alphanumeric() && b != b'_')
        {
            return Err(fail());
        }
        let upper = key.to_ascii_uppercase();
        if !seen.insert(upper.clone()) {
            return Err(fail());
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
        .any(|p| upper.starts_with(p))
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
            return Err(fail());
        }
    }
    Ok(())
}

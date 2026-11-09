//! Explicit fixture preparation only: constructs the formal Workspace with upstream APIs.
//! The Python qualification owner supplies a fresh root, source and original identity.
use craft_anything_engine::workspace::{TargetRef, Workspace};
use std::{fs, path::PathBuf};
fn main() {
    if let Err(e) = prepare() {
        eprintln!("fixture workspace preparation failed: {e}");
        std::process::exit(2);
    }
}
fn prepare() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() == 2 && args[0] == "--digest" {
        let digest =
            craft_anything_engine::execution_policy::source_digest(&PathBuf::from(&args[1]))
                .map_err(|e| e.to_string())?;
        println!("{}", serde_json::json!({"source_base_sha256":digest}));
        return Ok(());
    }
    let [root, original, source] = args.as_slice() else {
        return Err(
            "Expected absolute fresh workspace, original target and defective candidate source"
                .into(),
        );
    };
    let root = PathBuf::from(root);
    let original = PathBuf::from(original);
    let source = PathBuf::from(source);
    if !root.is_absolute() || !original.is_absolute() || !source.is_absolute() || root.exists() {
        return Err("Fresh absolute workspace and explicit source/original are required".into());
    }
    let mut ws = Workspace::create_at(
        &root,
        "Native Notes bounded qualification",
        "Repair the specified candidate persistence behavior only",
        TargetRef::Local { path: original },
        None,
    )
    .map_err(|e| e.to_string())?;
    fs::create_dir_all(ws.app_dir())?;
    fs::create_dir_all(ws.reference_dir())?;
    fs::copy(source, ws.app_dir().join("NativeNotes.cs"))?;
    ws.manifest.stack = "C# .NET Framework WinForms".into();
    ws.save().map_err(|e| e.to_string())?;
    let source = craft_anything_engine::execution_policy::source_digest(&ws.app_dir())
        .map_err(|e| e.to_string())?;
    println!(
        "{}",
        serde_json::json!({"workspace":root,"app_root":ws.app_dir(),"reference_root":ws.reference_dir(),"source_base_sha256":source})
    );
    Ok(())
}

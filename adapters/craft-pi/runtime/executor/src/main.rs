use craft_anything_engine::{
    Engine, Session,
    execution_policy::{ExecutionPolicy, hash_file, read_capped, refusal},
    inbox::InboxDir,
    workspace::Workspace,
};
use craft_anything_evidence::ToolError;
use craft_pi_executor::*;
use serde_json::{Value, json};
use std::{path::PathBuf, sync::Arc};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = dispatch(&args);
    match result {
        Ok(Some(v)) => {
            let fail = v.get("state").is_some_and(|s| {
                !["candidate", "validated", "prepared"]
                    .iter()
                    .any(|state| s == *state)
            });
            println!("{v}");
            if fail {
                std::process::exit(1);
            }
        }
        Ok(None) => {}
        Err(e) => {
            eprintln!(
                "{}",
                json!({"contract_version": CONTRACT_VERSION, "ok": false, "return_summary":e.details.as_ref().and_then(|d|d.get("return_summary")), "error": e})
            );
            std::process::exit(2);
        }
    }
}
fn dispatch(args: &[String]) -> Result<Option<Value>, ToolError> {
    match args {
        [one] if one == "--version" || one == "--inspect" => Ok(Some(
            json!({"name": "craft-pi-executor", "version": env!("CARGO_PKG_VERSION"),
            "contract_version": CONTRACT_VERSION, "backend_id": BACKEND_ID, "permission_contract": PERMISSION,
            "pi": {"version": "1.5.0", "protocol": "rpc"}, "cross_run_resume": "unsupported",
            "execution": "patched Craft RebuildRun; one Pi Builder; candidate only", "commands":["--run","--prepare","--validate","--inspect","--version"]}),
        )),
        [mode, file] if mode == "--prepare" || mode == "--validate" => {
            prepare::run(&PathBuf::from(file), mode == "--prepare").map(Some)
        }
        [mode, file] if mode == "--run" => {
            execution::execute(ExecutionConfig::load_prepared(&PathBuf::from(file))?).map(Some)
        }
        [mode, rest @ ..] if mode == "mcp" => {
            serve_mcp(rest)?;
            Ok(None)
        }
        _ => Err(refusal(
            "arguments",
            "Usage: craft-pi-executor --version | --inspect | --run <absolute prepared execution JSON> | --prepare <absolute handoff> | --validate <absolute handoff>",
        )),
    }
}
fn serve_mcp(args: &[String]) -> Result<(), ToolError> {
    let [
        policy_flag,
        path,
        hash_flag,
        expected_hash,
        workspace_flag,
        workspace,
        config_flag,
        config,
    ] = args
    else {
        return Err(refusal(
            "arguments",
            "Bounded MCP requires policy/hash/workspace/config-root.",
        ));
    };
    if policy_flag != "--policy"
        || hash_flag != "--sha256"
        || workspace_flag != "--workspace"
        || config_flag != "--config-root"
    {
        return Err(refusal("arguments", "Invalid bounded MCP options."));
    }
    let path = PathBuf::from(path);
    let workspace = PathBuf::from(workspace);
    let config = PathBuf::from(config);
    if !path.is_absolute()
        || !workspace.is_absolute()
        || !config.is_absolute()
        || hash_file(&path)? != *expected_hash
    {
        return Err(refusal(
            "identity-mismatch",
            "MCP policy hash/path rejected.",
        ));
    }
    let p: ExecutionPolicy = serde_json::from_slice(&read_capped(&path)?)
        .map_err(|e| refusal("invalid-policy", e.to_string()))?;
    p.validate_model()?;
    p.revalidate_inputs()?;
    let ws = Workspace::open(&workspace)?;
    if ws.manifest.target != p.original.target
        || craft_anything_engine::execution_policy::real(&ws.app_dir())?
            != craft_anything_engine::execution_policy::real(&p.app_root)?
    {
        return Err(refusal(
            "identity-mismatch",
            "MCP workspace/target differs from accepted owner.",
        ));
    }
    let config = craft_anything_engine::execution_policy::real(&config)?;
    if !config.is_dir()
        || config.starts_with(craft_anything_engine::execution_policy::real(&p.app_root)?)
    {
        return Err(refusal(
            "path-denied",
            "MCP requires a separate existing owned config root.",
        ));
    }
    let mut session = Session::isolated(&config);
    session.ext.insert(Arc::new(InboxDir(ws.inbox_dir())));
    let engine = Arc::new(Engine::bounded_builder(session, Arc::new(p)));
    craft_anything_mcp::serve_stdio(engine, craft_anything_mcp::ServerOptions::default())
        .map_err(|e| ToolError::internal(e.to_string()))
}

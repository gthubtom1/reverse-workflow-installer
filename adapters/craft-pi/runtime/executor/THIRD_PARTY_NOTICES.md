# Third-party notices and release gate

`Cargo.lock` identifies the exact dependency graph of this executable, including serde/serde_json, uuid, windows-sys, and the dependencies of the Craft engine, AI, platform, analysis and MCP crates. Craft source is MIT OR Apache-2.0; its license texts are supplied. Transitive packages retain their respective upstream licenses.

This development source file is not a complete redistributed dependency-license inventory. Before publishing a binary bundle, the integration owner must generate and review the license/notice inventory for the locked graph and any actually imported GNU DLLs. The staging script records PE imports and rejects unresolved imports, but that technical result does not certify license compliance. No binary release is authorized or claimed by this development task.

Official Pi is a separately installed runtime and is not embedded. Provider manifests and credentials are never bundle inputs. The native fixture and offline fake Pi are verification resources, not production providers or native REA Evidence.

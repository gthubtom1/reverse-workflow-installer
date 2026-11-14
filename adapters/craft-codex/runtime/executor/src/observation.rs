//! Read-only identity/lifetime observation of local descendants. No process is killed here.
//! PID/PPID alone never establishes ownership. Query failures remain sticky unknown facts.
use craft_anything_evidence::ToolError;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread::JoinHandle,
    time::{Duration, Instant},
};

pub struct Descendants {
    stop: Arc<AtomicBool>,
    worker: Option<JoinHandle<Value>>,
}
impl Descendants {
    pub fn start() -> Result<Self, ToolError> {
        #[cfg(windows)]
        let root = windows::root_identity().map_err(ToolError::internal)?;
        let stop = Arc::new(AtomicBool::new(false));
        let stopped = stop.clone();
        let worker = std::thread::Builder::new()
            .name("owned-descendants-observer".into())
            .spawn(move || {
                #[cfg(windows)]
                {
                    windows::observe(stopped, root)
                }
                #[cfg(not(windows))]
                {
                    let _ = stopped;
                    json!({"status":"unknown","scope":"unsupported-platform"})
                }
            })
            .map_err(|e| ToolError::internal(e.to_string()))?;
        Ok(Self {
            stop,
            worker: Some(worker),
        })
    }
    pub fn finish(mut self) -> Value {
        self.stop.store(true, Ordering::SeqCst);
        match self.worker.take().map(JoinHandle::join) {
            Some(Ok(v)) => v,
            _ => json!({"status":"unknown","reason":"descendant observer failed"}),
        }
    }
}
impl Drop for Descendants {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(w) = self.worker.take() {
            let _ = w.join();
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
struct Identity {
    pid: u32,
    created: u64,
}
#[derive(Debug, Clone, Copy)]
struct Lifetime {
    id: Identity,
    exited: Option<u64>,
}
/// Small pure identity graph. Lifetimes are refreshed through retained handles before advance.
/// Closed identities stay in history; an already observed child remains owned after parent exit.
struct IdentityGraph {
    root: Identity,
    known: BTreeMap<Identity, Lifetime>,
    parents: BTreeMap<Identity, Identity>,
    errors: BTreeSet<String>,
    reused: BTreeSet<(u32, u64, u64)>,
    rejected: BTreeSet<(Identity, Identity)>,
    unavailable: BTreeSet<Identity>,
}
impl IdentityGraph {
    fn new(root: Lifetime) -> Self {
        Self {
            root: root.id,
            known: BTreeMap::from([(root.id, root)]),
            parents: BTreeMap::new(),
            errors: BTreeSet::new(),
            reused: BTreeSet::new(),
            rejected: BTreeSet::new(),
            unavailable: BTreeSet::new(),
        }
    }
    fn refresh(&mut self, id: Identity, result: Result<Lifetime, String>) {
        match result {
            Ok(life) if life.id == id && life.exited.is_none_or(|end| end >= id.created) => {
                if let Some(old) = self.known.get(&id) {
                    if old.exited.is_some() && old.exited != life.exited {
                        self.unavailable.insert(id);
                        self.errors
                            .insert(format!("lifetime changed for PID {}", id.pid));
                        return;
                    }
                }
                self.unavailable.remove(&id);
                self.known.insert(id, life);
            }
            _ => {
                self.unavailable.insert(id);
                self.errors
                    .insert(format!("owned identity query failed for PID {}", id.pid));
            }
        }
    }
    fn advance(
        &mut self,
        rows: &[(u32, u32)],
        mut query: impl FnMut(u32) -> Result<Option<Lifetime>, String>,
    ) {
        let mut sampled = BTreeMap::new();
        // Resolve historical parent PIDs before considering any edge, independent of row order.
        // A replacement cannot inherit the old live identity's parent authority. Only a
        // confirmed old exit interval may still identify a child born before that exit.
        for (pid, _) in rows.iter().copied() {
            let old: Vec<_> = self
                .known
                .values()
                .filter(|life| life.id.pid == pid)
                .copied()
                .collect();
            if old.is_empty() {
                continue;
            }
            let current = sampled.entry(pid).or_insert_with(|| query(pid));
            for previous in old {
                match current {
                    Ok(Some(now)) if now.id != previous.id => {
                        self.reused
                            .insert((pid, previous.id.created, now.id.created));
                        if previous.exited.is_none() {
                            self.unavailable.insert(previous.id);
                            self.errors
                                .insert(format!("unconfirmed old lifetime after PID {pid} reuse"));
                        }
                    }
                    Ok(Some(_)) => {}
                    _ => {
                        self.unavailable.insert(previous.id);
                        self.errors.insert(format!(
                            "current owner generation unavailable for PID {pid}"
                        ));
                    }
                }
            }
        }
        let mut changed = true;
        while changed {
            changed = false;
            let parents: Vec<_> = self
                .known
                .values()
                .filter(|life| !self.unavailable.contains(&life.id))
                .copied()
                .collect();
            for (pid, ppid) in rows.iter().copied() {
                if pid == self.root.pid {
                    continue;
                }
                let possible: Vec<_> = parents
                    .iter()
                    .filter(|p| p.id.pid == ppid)
                    .copied()
                    .collect();
                let historical: Vec<_> = self
                    .known
                    .keys()
                    .filter(|id| id.pid == pid)
                    .copied()
                    .collect();
                if possible.is_empty() && historical.is_empty() {
                    continue;
                }
                let result = sampled.entry(pid).or_insert_with(|| query(pid));
                let child = match result {
                    Ok(Some(life)) => *life,
                    Ok(None) => continue,
                    Err(_) => {
                        self.errors
                            .insert(format!("candidate identity query failed for PID {pid}"));
                        continue;
                    }
                };
                for old in historical {
                    if old != child.id {
                        self.reused.insert((pid, old.created, child.id.created));
                    }
                }
                if self.known.contains_key(&child.id) {
                    continue;
                }
                if child.id.pid != pid || child.exited.is_some_and(|end| end < child.id.created) {
                    self.errors
                        .insert(format!("invalid candidate identity for PID {pid}"));
                    continue;
                }
                for parent in possible {
                    if child.id.created < self.root.created
                        || child.id.created < parent.id.created
                        || parent.exited.is_some_and(|end| child.id.created > end)
                    {
                        self.rejected.insert((parent.id, child.id));
                        continue;
                    }
                    self.known.insert(child.id, child);
                    self.parents.insert(child.id, parent.id);
                    changed = true;
                    break;
                }
            }
        }
    }
    fn receipt(&self) -> Value {
        let id = |id: Identity| json!({"pid":id.pid,"creation_filetime":id.created});
        let remaining: Vec<_> = self
            .known
            .values()
            .filter(|p| p.id != self.root && p.exited.is_none())
            .map(|p| id(p.id))
            .collect();
        json!({"status":if remaining.is_empty()&&self.errors.is_empty(){"observed-empty"}else{"unknown"},"scope":"local descendant PID/creation observation",
            "root_identity":id(self.root),"observed_processes":self.known.values().filter(|p|p.id!=self.root).map(|p|json!({"pid":p.id.pid,"creation_filetime":p.id.created,"exit_filetime":p.exited,"parent_identity":self.parents.get(&p.id).copied().map(id)})).collect::<Vec<_>>(),
            "remaining":remaining,"errors":self.errors,
            "pid_reuse":self.reused.iter().map(|(pid,old,new)|json!({"pid":pid,"owner_creation_filetime":old,"old_exit_confirmed":self.known.get(&Identity{pid:*pid,created:*old}).is_some_and(|life|life.exited.is_some()),"current_creation_filetime":new})).collect::<Vec<_>>(),
            "rejected_creation_edges":self.rejected.iter().map(|(parent,child)|json!({"parent":id(*parent),"child":id(*child),"reason":"outside owner parent lifetime"})).collect::<Vec<_>>(),
            "limits":["No remote/broker process or business rollback claim","Short-lived processes may finish between samples; trusted bounded local checks only"]})
    }
}

/// Only a signaled process makes its exit FILETIME authoritative. No exit-code-259 guess.
fn lifetime_from_observation(
    pid: u32,
    created: u64,
    exit_buffer: u64,
    signaled: Result<bool, String>,
) -> Result<Lifetime, String> {
    let exited = match signaled? {
        false => None,
        true if exit_buffer != 0 && exit_buffer >= created => Some(exit_buffer),
        true => {
            return Err(format!(
                "signaled process exit time unavailable for PID {pid}"
            ));
        }
    };
    Ok(Lifetime {
        id: Identity { pid, created },
        exited,
    })
}

#[cfg(windows)]
mod windows {
    use super::*;
    use windows_sys::Win32::{
        Foundation::*,
        System::{Diagnostics::ToolHelp::*, Threading::*},
    };
    struct ProcessHandle(HANDLE);
    impl Drop for ProcessHandle {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }
    impl ProcessHandle {
        fn open(pid: u32) -> Result<Option<Self>, String> {
            unsafe {
                let h = OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SYNCHRONIZE,
                    0,
                    pid,
                );
                if h.is_null() {
                    return if GetLastError() == ERROR_INVALID_PARAMETER {
                        Ok(None)
                    } else {
                        Err(format!("OpenProcess failed for PID {pid}"))
                    };
                }
                Ok(Some(Self(h)))
            }
        }
        fn lifetime(&self, pid: u32) -> Result<Lifetime, String> {
            unsafe {
                // Wait first. An unsignaled process may exit while its times are queried,
                // but treating it as active until the next sample is conservative. Exit
                // FILETIME is never interpreted as valid for WAIT_TIMEOUT.
                let wait = match WaitForSingleObject(self.0, 0) {
                    WAIT_OBJECT_0 => Ok(true),
                    WAIT_TIMEOUT => Ok(false),
                    _ => Err(format!("WaitForSingleObject failed for PID {pid}")),
                };
                let mut creation: FILETIME = std::mem::zeroed();
                let mut exit: FILETIME = std::mem::zeroed();
                let mut kernel: FILETIME = std::mem::zeroed();
                let mut user: FILETIME = std::mem::zeroed();
                if GetProcessTimes(self.0, &mut creation, &mut exit, &mut kernel, &mut user) == 0 {
                    return Err(format!("GetProcessTimes failed for PID {pid}"));
                }
                let time = |v: FILETIME| ((v.dwHighDateTime as u64) << 32) | v.dwLowDateTime as u64;
                lifetime_from_observation(pid, time(creation), time(exit), wait)
            }
        }
    }
    pub(super) fn root_identity() -> Result<Identity, String> {
        let pid = std::process::id();
        let handle = ProcessHandle::open(pid)?.ok_or("root process unavailable")?;
        Ok(handle.lifetime(pid)?.id)
    }
    fn processes() -> Result<(Vec<(u32, u32)>, u64), String> {
        // Do not bind a stale snapshot PID/PPID row to a process born during/after sampling.
        let since_unix = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|_| "process snapshot clock unavailable")?;
        let snapshot_start = u64::try_from(since_unix.as_nanos() / 100)
            .ok()
            .and_then(|ticks| ticks.checked_add(116_444_736_000_000_000))
            .ok_or("process snapshot clock overflow")?;
        unsafe {
            let handle = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
            if handle == INVALID_HANDLE_VALUE {
                return Err("process snapshot failed".into());
            }
            let snapshot = ProcessHandle(handle);
            let mut e: PROCESSENTRY32W = std::mem::zeroed();
            e.dwSize = std::mem::size_of::<PROCESSENTRY32W>() as u32;
            if Process32FirstW(snapshot.0, &mut e) == 0 {
                return Err("process snapshot enumeration failed".into());
            }
            let mut rows = Vec::new();
            loop {
                rows.push((e.th32ProcessID, e.th32ParentProcessID));
                if Process32NextW(snapshot.0, &mut e) == 0 {
                    if GetLastError() != ERROR_NO_MORE_FILES {
                        return Err("process snapshot enumeration incomplete".into());
                    }
                    break;
                }
            }
            Ok((rows, snapshot_start))
        }
    }
    pub(super) struct Tracker {
        graph: IdentityGraph,
        handles: BTreeMap<Identity, ProcessHandle>,
    }
    impl Tracker {
        pub(super) fn new(root: Identity) -> Result<Self, String> {
            let handle = ProcessHandle::open(root.pid)?.ok_or("root process unavailable")?;
            let life = handle.lifetime(root.pid)?;
            if life.id != root {
                return Err("root creation identity changed".into());
            }
            Ok(Self {
                graph: IdentityGraph::new(life),
                handles: BTreeMap::from([(root, handle)]),
            })
        }
        pub(super) fn sample(&mut self) {
            match processes() {
                Ok((rows, snapshot_start)) => {
                    // Refresh retained parent lifetimes after snapshot began; admit only
                    // children born before that boundary. Sampling-time PID reuse therefore
                    // cannot borrow an old parent lifetime or a stale child PPID row.
                    for (id, handle) in &self.handles {
                        self.graph.refresh(*id, handle.lifetime(id.pid));
                    }
                    let mut opened = BTreeMap::new();
                    self.graph.advance(&rows, |pid| {
                        let Some(handle) = ProcessHandle::open(pid)? else {
                            return Ok(None);
                        };
                        let life = handle.lifetime(pid)?;
                        if life.id.created > snapshot_start {
                            return Ok(None);
                        }
                        opened.insert(life.id, handle);
                        Ok(Some(life))
                    });
                    for (id, handle) in opened {
                        if self.graph.known.contains_key(&id) {
                            self.handles.entry(id).or_insert(handle);
                        }
                    }
                }
                Err(error) => {
                    self.graph.errors.insert(error);
                }
            }
        }
        pub(super) fn receipt(&self) -> Value {
            self.graph.receipt()
        }
    }
    pub(super) fn observe(stop: Arc<AtomicBool>, root: Identity) -> Value {
        let mut tracker = match Tracker::new(root) {
            Ok(t) => t,
            Err(error) => {
                return json!({"status":"unknown","errors":[error],"root_identity":{"pid":root.pid,"creation_filetime":root.created}});
            }
        };
        let mut draining = None;
        loop {
            tracker.sample();
            if stop.load(Ordering::SeqCst) {
                let started = draining.get_or_insert_with(Instant::now);
                if tracker.receipt()["remaining"]
                    .as_array()
                    .is_some_and(Vec::is_empty)
                    || started.elapsed() >= Duration::from_secs(2)
                {
                    break;
                }
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        tracker.receipt()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn life(pid: u32, created: u64, exited: Option<u64>) -> Lifetime {
        Lifetime {
            id: Identity { pid, created },
            exited,
        }
    }
    fn advance(graph: &mut IdentityGraph, rows: &[(u32, u32)], values: &[Lifetime]) {
        graph.advance(rows, |pid| {
            Ok(values.iter().find(|v| v.id.pid == pid).copied())
        });
    }
    #[test]
    fn stale_ppid_cycle_does_not_admit_older_root_ancestor() {
        let mut g = IdentityGraph::new(life(100, 100, None));
        advance(&mut g, &[(200, 100)], &[life(200, 110, None)]);
        g.refresh(
            Identity {
                pid: 200,
                created: 110,
            },
            Ok(life(200, 110, Some(120))),
        );
        advance(
            &mut g,
            &[(100, 50), (200, 100), (50, 200)],
            &[life(200, 150, None), life(50, 10, None)],
        );
        assert!(!g.known.keys().any(|id| id.pid == 50));
        assert!(g.rejected.contains(&(
            Identity {
                pid: 200,
                created: 110
            },
            Identity {
                pid: 50,
                created: 10
            }
        )));
    }
    #[test]
    fn known_pid_reuse_never_seeds_unrelated_new_parent() {
        let mut g = IdentityGraph::new(life(1, 100, None));
        advance(&mut g, &[(2, 1)], &[life(2, 110, None)]);
        g.refresh(
            Identity {
                pid: 2,
                created: 110,
            },
            Ok(life(2, 110, Some(120))),
        );
        advance(
            &mut g,
            &[(2, 99), (3, 2)],
            &[life(2, 200, None), life(3, 210, None)],
        );
        assert_eq!(g.receipt()["status"], "observed-empty");
        assert_eq!(g.known.len(), 2);
        assert!(g.reused.contains(&(2, 110, 200)));
        assert!(!g.known.keys().any(|id| id.pid == 3));
    }
    #[test]
    fn live_old_parent_generation_conflict_cannot_adopt_replacement_children() {
        let mut g = IdentityGraph::new(life(1, 100, None));
        advance(
            &mut g,
            &[(2, 1), (4, 2)],
            &[life(2, 110, None), life(4, 115, None)],
        );
        // Parent's retained-handle refresh has not yet confirmed its exit, but this snapshot
        // proves PID 2 now denotes generation 200. Put the unrelated child first as a row-order
        // regression: closure cannot expand before checking the current parent generation.
        advance(
            &mut g,
            &[(3, 2), (2, 99), (4, 2), (5, 4)],
            &[
                life(2, 200, None),
                life(3, 210, None),
                life(4, 115, None),
                life(5, 220, None),
            ],
        );
        assert!(!g.known.contains_key(&Identity {
            pid: 3,
            created: 210
        }));
        assert!(!g.known.contains_key(&Identity {
            pid: 2,
            created: 200
        }));
        assert!(g.known.contains_key(&Identity {
            pid: 4,
            created: 115
        }));
        assert!(g.known.contains_key(&Identity {
            pid: 5,
            created: 220
        }));
        assert!(g.reused.contains(&(2, 110, 200)));
        assert_eq!(g.receipt()["status"], "unknown");
    }
    #[test]
    fn wait_state_makes_exit_buffer_authoritative_only_after_signal() {
        assert!(
            lifetime_from_observation(2, 100, 987654, Ok(false))
                .unwrap()
                .exited
                .is_none(),
            "nonzero live-process exit buffer is not evidence of exit"
        );
        assert_eq!(
            lifetime_from_observation(2, 100, 150, Ok(true))
                .unwrap()
                .exited,
            Some(150)
        );
        assert!(lifetime_from_observation(2, 100, 0, Ok(true)).is_err());
        assert!(lifetime_from_observation(2, 100, 99, Ok(true)).is_err());
        assert!(lifetime_from_observation(2, 100, 150, Err("WAIT_FAILED".into())).is_err());
        let mut g = IdentityGraph::new(life(1, 10, None));
        advance(&mut g, &[(2, 1)], &[life(2, 100, None)]);
        g.refresh(
            Identity {
                pid: 2,
                created: 100,
            },
            lifetime_from_observation(2, 100, 987654, Ok(false)),
        );
        assert_eq!(g.receipt()["status"], "unknown");
        assert_eq!(g.receipt()["remaining"].as_array().unwrap().len(), 1);
        g.refresh(
            Identity {
                pid: 2,
                created: 100,
            },
            lifetime_from_observation(2, 100, 150, Err("WAIT_FAILED".into())),
        );
        assert_eq!(g.receipt()["status"], "unknown");
        assert!(!g.errors.is_empty());
    }
    #[test]
    fn real_grandchild_remains_owned_and_can_expand_after_parent_exit() {
        let mut g = IdentityGraph::new(life(1, 100, None));
        advance(
            &mut g,
            &[(2, 1), (3, 2)],
            &[life(2, 110, None), life(3, 115, None)],
        );
        g.refresh(
            Identity {
                pid: 2,
                created: 110,
            },
            Ok(life(2, 110, Some(120))),
        );
        advance(
            &mut g,
            &[(3, 2), (4, 3)],
            &[life(3, 115, None), life(4, 130, None)],
        );
        assert_eq!(g.receipt()["remaining"].as_array().unwrap().len(), 2);
        assert_eq!(g.receipt()["status"], "unknown");
        g.refresh(
            Identity {
                pid: 3,
                created: 115,
            },
            Ok(life(3, 115, Some(140))),
        );
        g.refresh(
            Identity {
                pid: 4,
                created: 130,
            },
            Ok(life(4, 130, Some(150))),
        );
        assert_eq!(g.receipt()["status"], "observed-empty");
    }
    #[test]
    fn unobserved_child_can_only_bind_inside_retained_parent_lifetime() {
        let mut g = IdentityGraph::new(life(1, 100, None));
        advance(&mut g, &[(2, 1)], &[life(2, 110, None)]);
        g.refresh(
            Identity {
                pid: 2,
                created: 110,
            },
            Ok(life(2, 110, Some(120))),
        );
        advance(
            &mut g,
            &[(2, 99), (3, 2), (4, 2)],
            &[life(2, 200, None), life(3, 115, None), life(4, 201, None)],
        );
        assert!(g.known.contains_key(&Identity {
            pid: 3,
            created: 115
        }));
        assert!(!g.known.keys().any(|id| id.pid == 4));
    }
    #[test]
    fn root_and_parent_creation_order_rejects_preexisting_processes() {
        let mut g = IdentityGraph::new(life(1, 100, None));
        advance(
            &mut g,
            &[(2, 1), (3, 1)],
            &[life(2, 90, None), life(3, 110, None)],
        );
        advance(&mut g, &[(4, 3)], &[life(4, 105, None)]);
        assert!(!g.known.keys().any(|id| id.pid == 2 || id.pid == 4));
        assert_eq!(g.known.len(), 2);
    }
    #[test]
    fn identity_queries_fail_closed_and_remain_unknown() {
        let mut g = IdentityGraph::new(life(1, 100, None));
        g.advance(&[(2, 1)], |_| Err("AccessDenied".into()));
        assert_eq!(g.receipt()["status"], "unknown");
        advance(&mut g, &[], &[]);
        assert_eq!(g.receipt()["status"], "unknown");
        let mut g = IdentityGraph::new(life(1, 100, None));
        advance(&mut g, &[(2, 1)], &[life(2, 110, None)]);
        g.refresh(
            Identity {
                pid: 2,
                created: 110,
            },
            Err("GetProcessTimes failed".into()),
        );
        assert_eq!(g.receipt()["status"], "unknown");
        assert_eq!(g.receipt()["remaining"].as_array().unwrap().len(), 1);
        advance(&mut g, &[(3, 2)], &[life(3, 115, None)]);
        assert!(
            !g.known.keys().any(|id| id.pid == 3),
            "a failed parent query cannot authorize a new edge"
        );
    }
    #[test]
    fn refreshed_identity_cannot_silently_change_generation() {
        let mut g = IdentityGraph::new(life(1, 100, None));
        g.refresh(g.root, Ok(life(1, 200, None)));
        assert_eq!(g.receipt()["status"], "unknown");
        assert_eq!(g.root.created, 100);
    }

    #[cfg(windows)]
    #[test]
    fn windows_process_peer() {
        use std::process::{Command, Stdio};
        let Some(role) = std::env::var_os("CRAFT_OBSERVER_TEST_ROLE") else {
            return;
        };
        let dir = std::path::PathBuf::from(std::env::var_os("CRAFT_OBSERVER_TEST_DIR").unwrap());
        let until = |name: &str| {
            let start = Instant::now();
            while !dir.join(name).exists() && start.elapsed() < Duration::from_secs(15) {
                std::thread::sleep(Duration::from_millis(10));
            }
        };
        if role == "parent" {
            let child = Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "observation::tests::windows_process_peer",
                    "--nocapture",
                ])
                .env("CRAFT_OBSERVER_TEST_ROLE", "grandchild")
                .env("CRAFT_OBSERVER_TEST_DIR", &dir)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap();
            std::fs::write(dir.join("grandchild-pid"), child.id().to_string()).unwrap();
            std::fs::write(dir.join("parent-ready"), b"ready").unwrap();
            until("parent-release");
        } else {
            std::fs::write(dir.join("grandchild-ready"), b"ready").unwrap();
            until("grandchild-release");
        }
    }
    #[cfg(windows)]
    #[test]
    fn windows_owned_grandchild_active_then_exited_is_observed_by_exact_identity() {
        use std::process::{Command, Stdio};
        let dir = tempfile::tempdir().unwrap();
        struct Release(std::path::PathBuf);
        impl Drop for Release {
            fn drop(&mut self) {
                let _ = std::fs::write(self.0.join("parent-release"), b"release");
                let _ = std::fs::write(self.0.join("grandchild-release"), b"release");
            }
        }
        let _release = Release(dir.path().into());
        let mut tracker = windows::Tracker::new(windows::root_identity().unwrap()).unwrap();
        let observer = Descendants::start().unwrap();
        let mut parent = Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "observation::tests::windows_process_peer",
                "--nocapture",
            ])
            .env("CRAFT_OBSERVER_TEST_ROLE", "parent")
            .env("CRAFT_OBSERVER_TEST_DIR", dir.path())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let start = Instant::now();
        while !(dir.path().join("parent-ready").exists()
            && dir.path().join("grandchild-ready").exists())
            && start.elapsed() < Duration::from_secs(5)
        {
            tracker.sample();
            std::thread::sleep(Duration::from_millis(10));
        }
        assert!(dir.path().join("grandchild-ready").exists());
        tracker.sample();
        let grandchild: u32 = std::fs::read_to_string(dir.path().join("grandchild-pid"))
            .unwrap()
            .parse()
            .unwrap();
        assert!(
            tracker.receipt()["remaining"]
                .as_array()
                .unwrap()
                .iter()
                .any(|v| v["pid"] == grandchild)
        );
        let active = observer.finish();
        assert_eq!(active["status"], "unknown", "{active}");
        assert!(
            active["remaining"]
                .as_array()
                .unwrap()
                .iter()
                .any(|p| p["pid"] == parent.id())
        );
        std::fs::write(dir.path().join("parent-release"), b"release").unwrap();
        let start = Instant::now();
        while parent.try_wait().unwrap().is_none() && start.elapsed() < Duration::from_secs(5) {
            std::thread::sleep(Duration::from_millis(10));
        }
        assert!(parent.try_wait().unwrap().is_some());
        tracker.sample();
        assert_eq!(tracker.receipt()["status"], "unknown");
        assert!(
            tracker.receipt()["remaining"]
                .as_array()
                .unwrap()
                .iter()
                .any(|v| v["pid"] == grandchild)
        );
        std::fs::write(dir.path().join("grandchild-release"), b"release").unwrap();
        let start = Instant::now();
        loop {
            tracker.sample();
            if tracker.receipt()["status"] == "observed-empty"
                || start.elapsed() >= Duration::from_secs(5)
            {
                break;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        let receipt = tracker.receipt();
        println!(
            "{}",
            json!({"windows_owned_observer_fixture":{"active":active,"after_exit":receipt}})
        );
        assert_eq!(receipt["status"], "observed-empty", "{receipt}");
        assert!(
            receipt["observed_processes"]
                .as_array()
                .unwrap()
                .iter()
                .any(|p| p["pid"] == grandchild && p["exit_filetime"].is_u64())
        );
    }
}

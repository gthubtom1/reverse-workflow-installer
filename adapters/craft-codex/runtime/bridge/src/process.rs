use crate::Failure;
use serde::Serialize;
use std::process::{Child, Command};
use std::time::Duration;

#[derive(Debug, Clone, Serialize)]
pub struct Cleanup {
    pub status: &'static str,
    pub scope: &'static str,
    pub root_exited: bool,
    pub members_empty: bool,
    pub hard_terminated: bool,
    pub detail: String,
}
impl Cleanup {
    pub fn not_started() -> Self {
        Self {
            status: "not_started",
            scope: "none",
            root_exited: true,
            members_empty: true,
            hard_terminated: false,
            detail: "child not started".into(),
        }
    }
}
pub struct SpawnFailure {
    pub failure: Failure,
    pub cleanup: Cleanup,
}
impl SpawnFailure {
    pub fn before_child(failure: Failure) -> Self {
        Self {
            failure,
            cleanup: Cleanup::not_started(),
        }
    }
}
/// Faults are only accepted by the fixture-only library entry point, never CLI/config/env.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SpawnFault {
    Snapshot,
    OpenThread,
    ResumeThread,
    SnapshotUnconfirmedCleanup,
}

#[cfg(windows)]
mod platform {
    use super::*;
    use std::{
        mem::{size_of, zeroed},
        os::windows::{io::AsRawHandle, process::CommandExt},
        thread,
        time::Instant,
    };
    use windows_sys::Win32::{
        Foundation::*,
        System::{Diagnostics::ToolHelp::*, JobObjects::*, Threading::*},
    };
    pub struct Owned {
        pub child: Child,
        job: HANDLE,
        pub hard: bool,
    }
    impl Owned {
        fn failed(
            mut self,
            failure: Failure,
            timeout: Duration,
            assigned: bool,
            observable: bool,
        ) -> SpawnFailure {
            // A suspended child may exist even when ownership setup fails. Never
            // replace its lifecycle with not_started. Both termination and observation
            // are finite; inability to observe remains unknown after handle closure.
            self.terminate();
            let _ = self.child.kill();
            let deadline = Instant::now() + timeout;
            let cleanup = loop {
                let mut cleanup = self.cleanup();
                if !assigned {
                    cleanup.scope = "windows_suspended_child";
                }
                if !observable {
                    cleanup.status = "unknown";
                    cleanup.members_empty = false;
                    cleanup.detail =
                        "cleanup observation unavailable after owned startup failure".into();
                }
                if cleanup.status == "verified" || Instant::now() >= deadline {
                    break cleanup;
                }
                thread::sleep(Duration::from_millis(5));
            };
            SpawnFailure { failure, cleanup }
        }
        pub fn spawn(
            cmd: &mut Command,
            timeout: Duration,
            fault: Option<SpawnFault>,
        ) -> std::result::Result<Self, SpawnFailure> {
            unsafe {
                let before = |failure| SpawnFailure::before_child(failure);
                let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if job.is_null() {
                    return Err(before(Failure::new(
                        "ownership_failed",
                        std::io::Error::last_os_error(),
                    )));
                }
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                if SetInformationJobObject(
                    job,
                    JobObjectExtendedLimitInformation,
                    &info as *const _ as _,
                    size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                ) == 0
                {
                    let error = std::io::Error::last_os_error();
                    CloseHandle(job);
                    return Err(before(Failure::new("ownership_failed", error)));
                }
                let child = match cmd
                    .creation_flags(CREATE_SUSPENDED | CREATE_NO_WINDOW)
                    .spawn()
                {
                    Ok(child) => child,
                    Err(error) => {
                        CloseHandle(job);
                        return Err(before(Failure::new("spawn_failed", error)));
                    }
                };
                let owned = Self {
                    child,
                    job,
                    hard: false,
                };
                if AssignProcessToJobObject(job, owned.child.as_raw_handle() as HANDLE) == 0 {
                    return Err(owned.failed(
                        Failure::new("ownership_failed", std::io::Error::last_os_error()),
                        timeout,
                        false,
                        true,
                    ));
                }
                let snapshot = if matches!(
                    fault,
                    Some(SpawnFault::Snapshot | SpawnFault::SnapshotUnconfirmedCleanup)
                ) {
                    INVALID_HANDLE_VALUE
                } else {
                    CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
                };
                if snapshot == INVALID_HANDLE_VALUE {
                    return Err(owned.failed(
                        Failure::new("ownership_failed", "thread snapshot failed"),
                        timeout,
                        true,
                        fault != Some(SpawnFault::SnapshotUnconfirmedCleanup),
                    ));
                }
                let mut entry: THREADENTRY32 = zeroed();
                entry.dwSize = size_of::<THREADENTRY32>() as u32;
                let mut next = Thread32First(snapshot, &mut entry);
                let mut resumed = 0;
                while next != 0 {
                    if entry.th32OwnerProcessID == owned.child.id() {
                        let thread = if fault == Some(SpawnFault::OpenThread) {
                            std::ptr::null_mut()
                        } else {
                            OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID)
                        };
                        if !thread.is_null() {
                            let result = if fault == Some(SpawnFault::ResumeThread) {
                                u32::MAX
                            } else {
                                ResumeThread(thread)
                            };
                            if result != u32::MAX {
                                resumed += 1;
                            }
                            CloseHandle(thread);
                        }
                    }
                    next = Thread32Next(snapshot, &mut entry);
                }
                CloseHandle(snapshot);
                if resumed != 1 {
                    return Err(owned.failed(
                        Failure::new(
                            "ownership_failed",
                            "could not resume exactly one owned initial thread",
                        ),
                        timeout,
                        true,
                        true,
                    ));
                }
                Ok(owned)
            }
        }
        pub fn terminate(&mut self) {
            self.hard = true;
            unsafe {
                TerminateJobObject(self.job, 137);
            }
        }
        pub fn cleanup(&mut self) -> Cleanup {
            let root = self.child.try_wait().ok().flatten().is_some();
            let mut info: JOBOBJECT_BASIC_ACCOUNTING_INFORMATION = unsafe { zeroed() };
            let queried = unsafe {
                QueryInformationJobObject(
                    self.job,
                    JobObjectBasicAccountingInformation,
                    &mut info as *mut _ as _,
                    size_of::<JOBOBJECT_BASIC_ACCOUNTING_INFORMATION>() as u32,
                    std::ptr::null_mut(),
                )
            } != 0;
            let empty = queried && info.ActiveProcesses == 0;
            Cleanup {
                status: if root && empty { "verified" } else { "unknown" },
                scope: "windows_job",
                root_exited: root,
                members_empty: empty,
                hard_terminated: self.hard,
                detail: if queried {
                    format!(
                        "owned job active processes: {}; no breakaway enabled",
                        info.ActiveProcesses
                    )
                } else {
                    "job query failed".into()
                },
            }
        }
    }
    impl Drop for Owned {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.job);
            }
        }
    }
}
#[cfg(unix)]
mod platform {
    use super::*;
    use std::os::unix::process::CommandExt;
    pub struct Owned {
        pub child: Child,
        group: i32,
        pub hard: bool,
    }
    impl Owned {
        pub fn spawn(
            cmd: &mut Command,
            _timeout: Duration,
            _fault: Option<SpawnFault>,
        ) -> std::result::Result<Self, SpawnFailure> {
            let child = cmd
                .process_group(0)
                .spawn()
                .map_err(|e| SpawnFailure::before_child(Failure::new("spawn_failed", e)))?;
            let group = child.id() as i32;
            Ok(Self {
                child,
                group,
                hard: false,
            })
        }
        pub fn terminate(&mut self) {
            self.hard = true;
            unsafe {
                libc::kill(-self.group, libc::SIGKILL);
            }
        }
        pub fn cleanup(&mut self) -> Cleanup {
            let root = self.child.try_wait().ok().flatten().is_some();
            let empty = unsafe { libc::kill(-self.group, 0) } == -1
                && std::io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH);
            Cleanup { status: "unknown", scope: "unix_process_group", root_exited: root, members_empty: empty, hard_terminated: self.hard, detail: "process group observed; descendants can escape with setsid/setpgid, no cgroup or external descendant observer available".into() }
        }
    }
    impl Drop for Owned {
        fn drop(&mut self) {
            self.terminate();
            let _ = self.child.try_wait();
        }
    }
}
#[cfg(not(any(windows, unix)))]
compile_error!("owned child lifecycle is only implemented for Windows and Unix");
pub use platform::Owned;

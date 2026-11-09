"""Bounded packaging subprocesses with an owned Windows Job or Unix process group."""
import ctypes
from contextlib import ExitStack
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


class WindowsJob:
    def __init__(self):
        from ctypes import wintypes as w
        class Limits(ctypes.Structure):
            _fields_ = [('per_process', ctypes.c_int64), ('per_job', ctypes.c_int64), ('flags', w.DWORD),
                        ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t), ('active_limit', w.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Limits), ('io', IO), ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
        self.api.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        info = Extended()
        info.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway.
        if not self.handle or not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise OSError('Cannot establish owned Windows Job')

    def assign_resume(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise OSError('Cannot assign suspended packaging child to Job')
        ntdll = ctypes.WinDLL('ntdll')
        ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]
        ntdll.NtResumeProcess.restype = ctypes.c_long
        if ntdll.NtResumeProcess(int(process._handle)) != 0:
            raise OSError('Cannot resume owned packaging child')

    def empty(self):
        # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION: four LARGE_INTEGER + four DWORD.
        data = (ctypes.c_byte * 48)()
        if not self.api.QueryInformationJobObject(self.handle, 1, data, 48, None):
            return None
        return ctypes.c_uint32.from_buffer(data, 40).value == 0

    def terminate(self):
        return bool(self.api.TerminateJobObject(self.handle, 1))

    def close(self):
        if getattr(self, 'handle', None):
            self.api.CloseHandle(self.handle)
            self.handle = None


def group_empty(pid):
    try:
        os.killpg(pid, 0)
        return False
    except ProcessLookupError:
        return True
    except PermissionError:
        return None


def run_owned(argv, *, cwd, env=None, timeout=1800, input=None, cleanup_seconds=5, log_prefix=None):
    """Return observed cleanup facts. Output is file-backed so descendants cannot hold pipe EOF."""
    job = WindowsJob() if os.name == 'nt' else None
    process = None
    timed_out = False
    output_root = Path(__file__).resolve().parents[1] / '.local/packaging/command-output'
    output_root.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        if log_prefix is not None:
            prefix = Path(log_prefix)
            prefix.parent.mkdir(parents=True, exist_ok=True)
            out = stack.enter_context(Path(str(prefix) + '.stdout.log').open('w+b'))
            err = stack.enter_context(Path(str(prefix) + '.stderr.log').open('w+b'))
        else:
            out = stack.enter_context(tempfile.TemporaryFile(dir=output_root))
            err = stack.enter_context(tempfile.TemporaryFile(dir=output_root))
        try:
            process = subprocess.Popen([str(x) for x in argv], cwd=cwd, env=env, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                                       stdout=out, stderr=err, creationflags=0x4 if job else 0, start_new_session=not bool(job))
            try:
                if job:
                    job.assign_resume(process)
                process.communicate(input=input.encode('utf-8') if input is not None else None, timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            except BaseException:
                if job:
                    job.terminate()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.kill()
                process.wait(timeout=cleanup_seconds)
                raise
            empty = job.empty() if job else group_empty(process.pid)
            had_descendants = empty is not True
            if timed_out or had_descendants:
                if job:
                    job.terminate()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                deadline = time.monotonic() + cleanup_seconds
                while time.monotonic() < deadline:
                    process.poll()
                    empty = job.empty() if job else group_empty(process.pid)
                    if process.returncode is not None and empty is True:
                        break
                    time.sleep(0.02)
            verified = process.poll() is not None and empty is True
            out.seek(0)
            err.seek(0)
            return {'returncode': process.returncode, 'stdout': out.read().decode('utf-8', 'replace'),
                    'stderr': err.read().decode('utf-8', 'replace'), 'timed_out': timed_out,
                    'cleanup': 'verified' if verified else 'unknown', 'had_descendants': had_descendants,
                    'scope': 'windows-job' if job else 'unix-process-group (setsid escape not contained)'}
        finally:
            if job:
                job.close()

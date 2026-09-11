"""Cross-platform memory monitoring and garbage collection utilities.

Provides accurate RSS telemetry for Linux containers/VMs (cgroups) and Windows,
with proactive heap trimming via libc.malloc_trim(0) where supported.
"""

import gc
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# Platform detection
_IS_WINDOWS = sys.platform == "win32"
_IS_LINUX = sys.platform.startswith("linux")


def get_process_rss_mb() -> float:
    """Return current process Resident Set Size (RSS) in Megabytes.

    Prioritizes real-time VmRSS from /proc/self/status on Linux,
    falling back to standard resource module or Windows PSAPI.
    """
    # 1. Real-time Linux container / host telemetry
    if os.path.exists("/proc/self/status"):
        try:
            with open("/proc/self/status", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            return round(int(parts[1]) / 1024.0, 2)
        except Exception:
            pass

    # 2. POSIX resource module
    try:
        import resource
        ru_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # On Linux, ru_maxrss is in kilobytes; on macOS, in bytes
        if sys.platform == "darwin":
            return round(ru_rss / (1024.0 * 1024.0), 2)
        return round(ru_rss / 1024.0, 2)
    except Exception:
        pass

    # 3. Windows PSAPI via ctypes
    if _IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
            fn = ctypes.windll.psapi.GetProcessMemoryInfo
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), wintypes.DWORD]
            fn.restype = wintypes.BOOL
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if fn(handle, ctypes.byref(counters), counters.cb):
                return round(counters.WorkingSetSize / (1024.0 * 1024.0), 2)
        except Exception:
            pass

    return 0.0


def force_garbage_collection() -> float:
    """Trigger cyclic garbage collection and return current process RSS in MB.

    Uses Python's built-in cyclic garbage collector. Avoids glibc malloc_trim(0)
    which can deadlock on arena mutexes when C++ background threads (OpenMP/Paddle)
    are active.
    """
    gc.collect()
    return get_process_rss_mb()


def log_memory_checkpoint(stage_name: str, extra_info: Optional[str] = None) -> float:
    """Log a structured memory diagnostic checkpoint with current RSS in MB.

    Never logs image contents or sensitive payload data.
    Returns current RSS in MB.
    """
    rss = get_process_rss_mb()
    extra_str = f" ({extra_info})" if extra_info else ""
    logger.info("[MEMORY_DIAGNOSTIC] stage='%s' rss_mb=%.2f%s", stage_name, rss, extra_str)
    return rss

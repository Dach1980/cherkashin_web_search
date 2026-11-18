"""Точка входа для упаковки MCP-сервера через PyInstaller."""

import multiprocessing

# Handle frozen multiprocessing worker invocations before application imports.
multiprocessing.freeze_support()


def _enable_process_trace() -> None:
    """Opt-in diagnostics for locating unexpected child-process creation."""
    import os
    import subprocess
    import sys
    import traceback

    if os.getenv("WEB_SEARCH_PROCESS_TRACE") != "1":
        return

    original_popen_init = subprocess.Popen.__init__

    def traced_popen_init(self, *args, **kwargs):
        sys.stderr.write("[process-trace] subprocess.Popen called\\n")
        traceback.print_stack(file=sys.stderr)
        return original_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = traced_popen_init

    try:
        from multiprocessing.process import BaseProcess
    except ImportError:
        return

    original_process_start = BaseProcess.start

    def traced_process_start(self, *args, **kwargs):
        sys.stderr.write(
            f"[process-trace] multiprocessing.Process.start: {self!r}\\n"
        )
        traceback.print_stack(file=sys.stderr)
        return original_process_start(self, *args, **kwargs)

    BaseProcess.start = traced_process_start


_enable_process_trace()

from web_search_mcp.server import main


if __name__ == "__main__":
    main()

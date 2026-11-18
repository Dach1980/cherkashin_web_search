"""Точка входа для упаковки MCP-сервера через PyInstaller."""


def _enable_process_trace() -> None:
    """Opt-in diagnostics installed before PyInstaller's multiprocessing bootstrap."""
    import os
    import subprocess
    import sys
    import traceback

    if os.getenv("WEB_SEARCH_PROCESS_TRACE") != "1":
        return

    def emit(label: str, details: str = "") -> None:
        try:
            sys.stderr.write(f"[process-trace] {label}{details}\n")
            traceback.print_stack(file=sys.stderr)
            sys.stderr.flush()
        except Exception:
            # Diagnostics must never prevent process startup or shutdown.
            pass

    emit("launcher entered before freeze_support; argv=", repr(sys.argv))

    # Install before freeze_support(): frozen worker bootstrap may exit early.
    original_popen_init = subprocess.Popen.__init__

    def traced_popen_init(self, *args, **kwargs):
        emit("subprocess.Popen called; args=", repr(args[:2]))
        return original_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = traced_popen_init

    try:
        import _winapi

        original_create_process = _winapi.CreateProcess

        def traced_create_process(application_name, command_line, *args, **kwargs):
            emit(
                "_winapi.CreateProcess called; application_name=",
                repr(application_name) + "; command_line=" + repr(command_line),
            )
            return original_create_process(
                application_name, command_line, *args, **kwargs
            )

        _winapi.CreateProcess = traced_create_process
    except (ImportError, AttributeError):
        emit("_winapi.CreateProcess unavailable")

    try:
        from multiprocessing.process import BaseProcess

        original_process_start = BaseProcess.start

        def traced_process_start(self, *args, **kwargs):
            emit("multiprocessing.Process.start; process=", repr(self))
            return original_process_start(self, *args, **kwargs)

        BaseProcess.start = traced_process_start
    except (ImportError, AttributeError):
        emit("multiprocessing BaseProcess.start unavailable")


_enable_process_trace()

import multiprocessing

# Handle frozen multiprocessing worker invocations only after diagnostics are active.
multiprocessing.freeze_support()

from web_search_mcp.server import main


if __name__ == "__main__":
    main()

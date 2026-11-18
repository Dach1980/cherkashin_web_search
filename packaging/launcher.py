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
    except (ImportError, AttributeError) as exc:
        emit("_winapi.CreateProcess unavailable; exception=", repr(exc))

    # In Python 3.11, popen_spawn_win32 calls _winapi.CreateProcess;
    # the module itself does not expose a CreateProcess attribute.
    # Trace the launch boundary independently so one unavailable hook cannot
    # prevent the remaining diagnostics from being installed.
    try:
        import multiprocessing.popen_spawn_win32 as spawn_win32

        original_launch = spawn_win32.Popen._launch

        def traced_launch(self, process_obj):
            emit(
                "multiprocessing.popen_spawn_win32.Popen._launch; process=",
                repr(process_obj),
            )
            return original_launch(self, process_obj)

        spawn_win32.Popen._launch = traced_launch
    except (ImportError, AttributeError) as exc:
        emit(
            "multiprocessing Windows Popen._launch unavailable; exception=",
            repr(exc),
        )

    try:
        from multiprocessing.process import BaseProcess

        original_process_start = BaseProcess.start

        def traced_process_start(self, *args, **kwargs):
            emit("multiprocessing.Process.start; process=", repr(self))
            return original_process_start(self, *args, **kwargs)

        BaseProcess.start = traced_process_start
    except (ImportError, AttributeError) as exc:
        emit("multiprocessing BaseProcess.start unavailable; exception=", repr(exc))


_enable_process_trace()

import multiprocessing

# Handle frozen multiprocessing worker invocations only after diagnostics are active.
multiprocessing.freeze_support()

from web_search_mcp.server import main


if __name__ == "__main__":
    main()

"""Opt-in diagnostics for frozen Windows process startup and shutdown.

This hook is registered before PyInstaller's built-in runtime hooks. It records
all exec() calls and wraps atexit callbacks so shutdown failures can be attributed
to the callback that raised them.
"""

import atexit
import builtins
import json
import os
import sys
import traceback


_ENABLED = os.environ.get("WEB_SEARCH_PROCESS_TRACE") == "1"


def _stream_state(stream):
    if stream is None:
        return None
    state = {"type": type(stream).__name__, "closed": getattr(stream, "closed", None)}
    try:
        fd = stream.fileno()
        state["fd"] = fd
        try:
            os.fstat(fd)
            state["fd_open"] = True
        except OSError as exc:
            state["fd_open"] = False
            state["fd_error"] = repr(exc)
    except Exception as exc:
        state["fileno_error"] = repr(exc)
    return state


def _snapshot():
    return {
        "pid": os.getpid(),
        "ppid": os.getppid() if hasattr(os, "getppid") else None,
        "executable": sys.executable,
        "argv": list(sys.argv),
        "stdin": _stream_state(sys.stdin),
        "stdout": _stream_state(sys.stdout),
        "stderr": _stream_state(sys.stderr),
        "dunder_stderr": _stream_state(getattr(sys, "__stderr__", None)),
    }


def _emit(event, **details):
    if not _ENABLED:
        return
    record = {"event": event, **_snapshot(), **details}
    payload = (
        "[process-trace] "
        + json.dumps(record, ensure_ascii=True, default=repr)
        + "\\n"
    ).encode("utf-8", "replace")
    try:
        os.write(2, payload)
    except OSError:
        # The diagnostic must never alter process startup or shutdown.
        pass


if _ENABLED:
    _emit("runtime-hook-entered")

    # Capture every exec() invocation, not only multiprocessing's resource tracker.
    _original_exec = builtins.exec

    def _traced_exec(source, *args, **kwargs):
        source_kind = type(source).__name__
        source_text = source if isinstance(source, str) else repr(source)
        _emit(
            "builtins-exec-before",
            source_type=source_kind,
            source=source_text,
            globals_type=type(args[0]).__name__ if args else None,
            locals_type=type(args[1]).__name__ if len(args) > 1 else None,
        )
        try:
            result = _original_exec(source, *args, **kwargs)
        except BaseException as exc:
            _emit(
                "builtins-exec-exception",
                source_type=source_kind,
                source=source_text,
                exception=repr(exc),
                traceback="".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ),
            )
            raise
        _emit(
            "builtins-exec-after",
            source_type=source_kind,
            source=source_text,
        )
        return result

    builtins.exec = _traced_exec

    # Capture eval() separately: some frozen bootstrap paths evaluate a string
    # without going through builtins.exec().
    _original_eval = builtins.eval

    def _traced_eval(source, *args, **kwargs):
        source_text = source if isinstance(source, str) else repr(source)
        _emit("builtins-eval-before", source_type=type(source).__name__, source=source_text)
        try:
            result = _original_eval(source, *args, **kwargs)
        except BaseException as exc:
            _emit(
                "builtins-eval-exception",
                source_type=type(source).__name__,
                source=source_text,
                exception=repr(exc),
                traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            )
            raise
        _emit("builtins-eval-after", source_type=type(source).__name__, source=source_text)
        return result

    builtins.eval = _traced_eval

    # Preserve the original unraisable-exception handler while recording errors
    # raised by finalizers and __del__ methods.
    _original_unraisablehook = sys.unraisablehook

    def _traced_unraisablehook(unraisable):
        _emit(
            "sys-unraisablehook",
            err_msg=getattr(unraisable, "err_msg", None),
            exception=repr(getattr(unraisable, "exc_value", None)),
            exception_type=getattr(getattr(unraisable, "exc_type", None), "__name__", None),
            traceback="".join(
                traceback.format_exception(
                    getattr(unraisable, "exc_type", None),
                    getattr(unraisable, "exc_value", None),
                    getattr(unraisable, "exc_traceback", None),
                )
            ),
            object=repr(getattr(unraisable, "object", None)),
        )
        return _original_unraisablehook(unraisable)

    sys.unraisablehook = _traced_unraisablehook

    # Transparently proxy the four standard stream references only in diagnostic
    # builds. All operations, including close(), are delegated to the same
    # underlying stream; close() additionally records its caller stack.
    class _TracedStream:
        def __init__(self, stream, name):
            self._stream = stream
            self._name = name

        def __getattr__(self, name):
            return getattr(self._stream, name)

        @property
        def closed(self):
            return self._stream.closed

        def close(self):
            _emit(
                "standard-stream-close",
                stream=self._name,
                caller_stack="".join(traceback.format_stack(limit=30)),
            )
            return self._stream.close()

        def __enter__(self):
            self._stream.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            return self._stream.__exit__(exc_type, exc, tb)

    _stream_proxies = {}
    for _stream_name in ("stdin", "stdout", "__stdin__", "__stdout__"):
        _stream = getattr(sys, _stream_name, None)
        if _stream is not None:
            _proxy = _stream_proxies.get(id(_stream))
            if _proxy is None:
                _proxy = _TracedStream(_stream, _stream_name)
                _stream_proxies[id(_stream)] = _proxy
            setattr(sys, _stream_name, _proxy)

    # Wrap callbacks at registration time. This preserves LIFO execution and
    # reports the callback's identity plus stream state immediately before and
    # after it runs. unregister() is adapted so callers can still unregister
    # the original callback rather than the internal wrapper.
    _original_atexit_register = atexit.register
    _original_atexit_unregister = getattr(atexit, "unregister", None)
    _atexit_wrappers = {}

    def _callback_label(callback):
        return {
            "module": getattr(callback, "__module__", None),
            "qualname": getattr(
                callback, "__qualname__", getattr(callback, "__name__", None)
            ),
            "repr": repr(callback),
        }

    def _traced_atexit_register(callback, *args, **kwargs):
        label = _callback_label(callback)

        def _run_callback():
            _emit("atexit-callback-before", callback=label, args=repr(args), kwargs=repr(kwargs))
            try:
                result = callback(*args, **kwargs)
            except BaseException as exc:
                _emit(
                    "atexit-callback-exception",
                    callback=label,
                    exception=repr(exc),
                    traceback="".join(
                        traceback.format_exception(type(exc), exc, exc.__traceback__)
                    ),
                )
                raise
            _emit("atexit-callback-after", callback=label)
            return result

        _run_callback.__name__ = getattr(callback, "__name__", "_run_callback")
        _run_callback.__qualname__ = getattr(
            callback, "__qualname__", _run_callback.__name__
        )
        _atexit_wrappers.setdefault(id(callback), []).append(_run_callback)
        _emit("atexit-callback-registered", callback=label, args=repr(args), kwargs=repr(kwargs))
        _original_atexit_register(_run_callback)
        # atexit.register returns the callback passed to it; retain that API.
        return callback

    atexit.register = _traced_atexit_register

    if _original_atexit_unregister is not None:
        def _traced_atexit_unregister(callback):
            wrappers = _atexit_wrappers.get(id(callback), [])
            if wrappers:
                wrapper = wrappers.pop()
                if not wrappers:
                    _atexit_wrappers.pop(id(callback), None)
                return _original_atexit_unregister(wrapper)
            return _original_atexit_unregister(callback)

        atexit.unregister = _traced_atexit_unregister

    # Keep the existing targeted hooks as supplementary evidence.
    try:
        import multiprocessing.resource_tracker as resource_tracker

        _original_ensure_running = resource_tracker.ResourceTracker.ensure_running

        def _traced_ensure_running(self, *args, **kwargs):
            _emit(
                "resource-tracker-ensure-running-before",
                tracker_pid=getattr(self, "_pid", None),
                tracker_fd=getattr(self, "_fd", None),
            )
            result = _original_ensure_running(self, *args, **kwargs)
            _emit(
                "resource-tracker-ensure-running-after",
                tracker_pid=getattr(self, "_pid", None),
                tracker_fd=getattr(self, "_fd", None),
            )
            return result

        resource_tracker.ResourceTracker.ensure_running = _traced_ensure_running
    except Exception as exc:
        _emit("resource-tracker-hook-unavailable", exception=repr(exc))

    try:
        import multiprocessing.popen_spawn_win32 as spawn_win32

        _original_spawn_init = spawn_win32.Popen.__init__

        def _traced_spawn_init(self, process_obj):
            _emit("multiprocessing-spawn-popen-before", process=repr(process_obj))
            try:
                result = _original_spawn_init(self, process_obj)
            except BaseException as exc:
                _emit("multiprocessing-spawn-popen-exception", exception=repr(exc))
                raise
            _emit(
                "multiprocessing-spawn-popen-after",
                child_pid=getattr(self, "pid", None),
                command=getattr(process_obj, "name", None),
            )
            return result

        spawn_win32.Popen.__init__ = _traced_spawn_init
    except Exception as exc:
        _emit("multiprocessing-spawn-hook-unavailable", exception=repr(exc))

    try:
        import _winapi

        _original_create_process = _winapi.CreateProcess

        def _traced_create_process(application_name, command_line, *args, **kwargs):
            _emit(
                "winapi-create-process-before",
                application_name=repr(application_name),
                command_line=repr(command_line),
            )
            try:
                result = _original_create_process(
                    application_name, command_line, *args, **kwargs
                )
            except BaseException as exc:
                _emit("winapi-create-process-exception", exception=repr(exc))
                raise
            _emit(
                "winapi-create-process-after",
                pid=result[2] if len(result) > 2 else None,
            )
            return result

        _winapi.CreateProcess = _traced_create_process
    except Exception as exc:
        _emit("winapi-create-process-hook-unavailable", exception=repr(exc))

    _original_excepthook = sys.excepthook

    def _traced_excepthook(exc_type, exc, tb):
        _emit(
            "sys-excepthook",
            exception=repr(exc),
            traceback="".join(traceback.format_exception(exc_type, exc, tb)),
        )
        return _original_excepthook(exc_type, exc, tb)

    sys.excepthook = _traced_excepthook

    atexit.register(_emit, "process-atexit")

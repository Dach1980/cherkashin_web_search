"""Live HTTPS proxy smoke test for the DNS-pinned fetch implementation.

Starts a local HTTP CONNECT proxy which tunnels directly to the requested
destination IP. The test verifies that HTTPX honors HTTPS_PROXY while the
application still pins the destination IP and preserves TLS hostname checks.
"""

import os
import select
import socket
import socketserver
import threading
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, os.path.join(ROOT, "src"))

from web_search_mcp.web_fetch import _resolve_public_address, web_fetch


class ConnectProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            buffer += chunk
            if len(buffer) > 16384:
                return

        first_line = buffer.split(b"\r\n", 1)[0].decode("ascii", "replace")
        parts = first_line.split()
        if len(parts) != 3 or parts[0].upper() != "CONNECT":
            self.request.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return

        authority = parts[1]
        if authority.startswith("["):
            closing = authority.find("]")
            host = authority[1:closing]
            port = int(authority[closing + 2:].lstrip(":"))
        else:
            host, _, port_text = authority.rpartition(":")
            port = int(port_text)

        self.server.targets.append((host, port))
        try:
            upstream = socket.create_connection((host, port), timeout=15)
        except OSError:
            self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return

        with upstream:
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.request.settimeout(None)
            upstream.settimeout(None)
            sockets = [self.request, upstream]
            while True:
                readable, _, exceptional = select.select(sockets, [], sockets, 20)
                if exceptional or not readable:
                    return
                for source in readable:
                    destination = upstream if source is self.request else self.request
                    try:
                        data = source.recv(65536)
                    except OSError:
                        return
                    if not data:
                        return
                    destination.sendall(data)


class ConnectProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, ConnectProxyHandler)
        self.targets = []


@contextmanager
def local_connect_proxy():
    server = ConnectProxyServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main():
    test_url = "https://example.com"
    pinned_ip, error = _resolve_public_address(test_url)
    if error or not pinned_ip:
        raise SystemExit(f"DNS validation failed before proxy test: {error}")

    original_env = os.environ.copy()
    try:
        with local_connect_proxy() as (proxy_url, proxy):
            os.environ["HTTPS_PROXY"] = proxy_url
            os.environ["HTTP_PROXY"] = proxy_url
            os.environ["https_proxy"] = proxy_url
            os.environ["http_proxy"] = proxy_url
            os.environ["NO_PROXY"] = ""
            os.environ["no_proxy"] = ""
            os.environ.pop("ALL_PROXY", None)
            os.environ.pop("all_proxy", None)

            print(f"Configured local HTTP CONNECT proxy: {proxy_url}")
            print(f"Expected pinned destination: {pinned_ip}:443")
            result = web_fetch(test_url, max_chars=2000, timeout=20)
            if not result.get("ok"):
                raise SystemExit(f"HTTPS proxy fetch failed: {result.get('error')}")

            expected = (pinned_ip, 443)
            if expected not in proxy.targets:
                raise SystemExit(
                    f"Proxy did not receive CONNECT to pinned IP {expected}; "
                    f"observed={proxy.targets!r}"
                )

            print(
                "HTTPS through proxy: "
                f"HTTP {result.get('status_code')}; title={result.get('title')!r}"
            )
            print(f"Proxy CONNECT targets: {proxy.targets!r}")
            print("PROXY SMOKE TEST COMPLETED")
    finally:
        os.environ.clear()
        os.environ.update(original_env)


if __name__ == "__main__":
    main()

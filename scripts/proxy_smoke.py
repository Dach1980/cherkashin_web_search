"""Live HTTPS proxy smoke test for the DNS-pinned fetch implementation.

Starts a local HTTP CONNECT proxy. It chains through the runner's pre-existing
egress proxy when one is configured, so the test remains compatible with
hosted CI networks that prohibit direct outbound sockets.
"""

import base64
import os
import select
import socket
import socketserver
import sys
import threading
import urllib.request
from contextlib import contextmanager
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
            upstream = self._open_upstream(host, port)
        except OSError as error:
            self.server.errors.append(f"{type(error).__name__}: {error}")
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

    def _open_upstream(self, host, port):
        proxy_url = self.server.upstream_proxy
        if not proxy_url:
            return socket.create_connection((host, port), timeout=15)

        parsed = urlsplit(proxy_url)
        if parsed.scheme.lower() != "http":
            raise OSError("CI proxy chaining currently supports HTTP proxy URLs only")
        proxy_host = parsed.hostname
        proxy_port = parsed.port or 80
        upstream = socket.create_connection((proxy_host, proxy_port), timeout=15)

        authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        request = [
            f"CONNECT {authority} HTTP/1.1",
            f"Host: {authority}",
            "Proxy-Connection: Keep-Alive",
        ]
        if parsed.username is not None:
            credentials = f"{parsed.username}:{parsed.password or ''}".encode()
            token = base64.b64encode(credentials).decode("ascii")
            request.append(f"Proxy-Authorization: Basic {token}")
        upstream.sendall(("\r\n".join(request) + "\r\n\r\n").encode("ascii"))

        response = bytearray()
        while b"\r\n\r\n" not in response:
            chunk = upstream.recv(4096)
            if not chunk or len(response) > 16384:
                upstream.close()
                raise OSError("Upstream proxy returned an incomplete CONNECT response")
            response.extend(chunk)
        status = bytes(response).split(b"\r\n", 1)[0]
        if b" 200 " not in status:
            upstream.close()
            raise OSError(f"Upstream proxy rejected CONNECT: {status.decode('ascii', 'replace')}")
        return upstream


class ConnectProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, upstream_proxy):
        super().__init__(address, ConnectProxyHandler)
        self.targets = []
        self.errors = []
        self.upstream_proxy = upstream_proxy


@contextmanager
def local_connect_proxy(upstream_proxy):
    server = ConnectProxyServer(("127.0.0.1", 0), upstream_proxy)
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

    # Preserve the CI runner's outbound proxy for the local CONNECT relay.
    upstream_proxy = urllib.request.getproxies().get("https")
    original_env = os.environ.copy()
    try:
        with local_connect_proxy(upstream_proxy) as (proxy_url, proxy):
            os.environ["HTTPS_PROXY"] = proxy_url
            os.environ["HTTP_PROXY"] = proxy_url
            os.environ["https_proxy"] = proxy_url
            os.environ["http_proxy"] = proxy_url
            os.environ["NO_PROXY"] = ""
            os.environ["no_proxy"] = ""
            os.environ.pop("ALL_PROXY", None)
            os.environ.pop("all_proxy", None)

            print(f"Configured local HTTP CONNECT proxy: {proxy_url}")
            print(f"Chained to runner egress proxy: {'yes' if upstream_proxy else 'no'}")
            print(f"Expected pinned destination: {pinned_ip}:443")
            result = web_fetch(test_url, max_chars=2000, timeout=20)
            if not result.get("ok"):
                raise SystemExit(
                    f"HTTPS proxy fetch failed: {result.get('error')}; "
                    f"CONNECT targets={proxy.targets!r}; proxy errors={proxy.errors!r}"
                )

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

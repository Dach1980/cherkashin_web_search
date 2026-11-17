# HTTP(S) proxy smoke test — current status

Date: 2026-11-18  
Repository: `Dach1980/cherkashin_web_search`  
Branch: `main`

## Purpose

The CI test starts a local HTTP CONNECT proxy and asks the real `web_fetch()`
implementation to retrieve `https://example.com` with `HTTPS_PROXY` configured.
The proxy records the CONNECT destination so the test can verify that the
application sends the DNS-pinned IP rather than the original hostname.

## Changes

- Added `scripts/proxy_smoke.py`.
- Added the proxy smoke step to `.github/workflows/network-smoke.yml`.
- The relay can chain through an existing HTTP egress proxy if the CI runner
  provides one; otherwise it attempts a direct TCP tunnel.

## Results

Commit: `f76b2b48037c435129031933e8db23c37ee2e2d6`

- Python tests run #22: **SUCCESS**.
- Network and MCP smoke test run #5: **FAILURE in the proxy step**.
- The preceding direct HTTPS + MCP stdio smoke step in the same workflow passed.
- The local proxy received a CONNECT request to a pinned public IP
  (`172.66.147.243:443` in the observed attempt).
- The subsequent HTTPS request returned `ConnectError`; the proxy relay did not
  report an upstream TCP-connect exception.

Workflow: https://github.com/Dach1980/cherkashin_web_search/actions/runs/44192383889

## Interpretation

This is **not a passing proxy test**. The failure is in the HTTPS CONNECT tunnel
path after the CONNECT request reaches the local proxy. The current logs do not
yet distinguish an origin TLS/SNI verification problem from a tunnel/runner
network behavior. The DNS-pinning and direct HTTPS tests remain passing, but
proxy compatibility is not accepted until this failure is isolated and a
successful end-to-end HTTPS-over-proxy run is recorded.

The test harness must not be treated as evidence that arbitrary corporate,
authenticated, HTTPS, or PAC-configured proxies are supported. Those require
separate compatibility checks.

## Next diagnostic steps

1. Capture the exact TLS/transport exception from a direct HTTPX request using
   the same pinned URL, Host header, and `sni_hostname` extension.
2. Record both DNS answers used by the test and the actual CONNECT authority;
   DNS can legitimately return different CDN addresses between resolutions.
3. Once the CI CONNECT test passes, repeat against the user's actual proxy
   configuration if one is used.
4. Separately verify LM Studio GUI integration on Windows; CI cannot perform
   that desktop acceptance test.

#!/usr/bin/env python3
"""Zeline ⇄ 9Router OAuth bridge.

9Router is the machine's OAuth broker: it already holds the provider
connections and exposes the full authorize/exchange/poll surface. Zeline's
provider page only needs a local, credential-safe way to drive that surface,
so this module is the single seam between the two.

What lives here:
  * CLI-token derivation (9Router authenticates local callers with
    ``x-9r-cli-token``, a hash of machine-id + cli-secret).
  * Provider → flow-capability mapping, read from 9Router at call time so a
    new provider needs no code change here.
  * Thin, typed wrappers for authorize / device-code / poll / exchange.

What never leaves here:
  * Access tokens, refresh tokens, and the cli-secret. Connection listings are
    stripped to display fields before they are returned to the browser.

Nothing in this module writes provider state except through 9Router's own
endpoints — Zeline is a client of the broker, not a second broker.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import quote

# 9Router binds loopback by default. The port is overridable for the rare case
# it runs elsewhere, but it is a local service — no remote host is assumed.
ROUTER_BASE = os.environ.get("ZELINE_9ROUTER_URL", "http://localhost:20128").rstrip("/")
ROUTER_DATA_DIR = os.path.expanduser(os.environ.get("ZELINE_9ROUTER_DATA", "~/.9router"))

_CLI_TOKEN_SALT = "9r-cli-auth"
_TOKEN_HEADER = "x-9r-cli-token"

# Cache the derived token: it only changes if machine-id or cli-secret changes,
# both of which are read once per process lifetime.
_TOKEN_CACHE: dict = {"value": None, "ts": 0.0}
_TOKEN_TTL = 60.0


class RouterError(RuntimeError):
    """A call to 9Router failed. ``code`` is a short machine-readable tag."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


# Pending authorization-code flows, keyed by OAuth ``state``.
#
# Zeline hosts its OWN callback, so when the browser comes back it must hand the
# router the exact PKCE verifier and redirect_uri that were used to mint the
# authorize URL. The router does not look those up for us on this path, so they
# are remembered here for the life of the flow and dropped on first use.
_PENDING_FLOWS: dict[str, dict] = {}
_PENDING_TTL = 15 * 60  # a user gets 15 minutes to approve in the browser


def remember_flow(state: str, provider: str, code_verifier: str,
                  redirect_uri: str) -> None:
    if not state:
        return
    now = time.time()
    for stale in [k for k, v in _PENDING_FLOWS.items() if now - v["ts"] > _PENDING_TTL]:
        _PENDING_FLOWS.pop(stale, None)
    _PENDING_FLOWS[state] = {"provider": provider, "code_verifier": code_verifier,
                             "redirect_uri": redirect_uri, "ts": now}


def pop_flow(state: str) -> dict | None:
    """Take (and forget) the flow for ``state``. Single use, like the code."""
    return _PENDING_FLOWS.pop(state or "", None)


# Completed flows, keyed by the same ``state``, so the open Zeline tab can ask
# "did the browser round-trip finish?" without re-exchanging anything.
_COMPLETED_FLOWS: dict[str, dict] = {}


def complete_flow(state: str, code: str = "", error: str = "") -> dict:
    """Finish a redirect flow: exchange the code and record the outcome.

    Called from Zeline's own callback, so the exchange does not depend on any
    other app's dashboard being open. The result is kept under ``state`` for the
    waiting tab to pick up.
    """
    flow = pop_flow(state)
    if flow is None:
        result = {"ok": False, "error": error or "unknown or expired state",
                  "connection": None}
    elif error:
        result = {"ok": False, "error": error, "connection": None}
    else:
        try:
            outcome = exchange(flow["provider"], code, flow["redirect_uri"],
                               flow["code_verifier"], state)
            result = {"ok": bool(outcome.get("success")),
                      "error": outcome.get("error") or "",
                      "connection": outcome.get("connection")}
        except RouterError as exc:
            result = {"ok": False, "error": exc.message, "connection": None}
    result["ts"] = time.time()
    _COMPLETED_FLOWS[state] = result
    # Keep the completed map small; the tab polls for a minute at most.
    for stale in [k for k, v in _COMPLETED_FLOWS.items()
                  if time.time() - v["ts"] > _PENDING_TTL]:
        _COMPLETED_FLOWS.pop(stale, None)
    return result


def flow_result(state: str) -> dict | None:
    """The outcome for ``state``, if the browser round-trip already finished."""
    return _COMPLETED_FLOWS.get(state or "")


def _read_secret(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def cli_token() -> str:
    """Derive the local CLI token the same way 9Router's own CLI client does.

    ``sha256(machine_id + salt + cli_secret)[:16]`` — reproducible from files
    that only the local user can read, so no credential is stored here.
    """
    now = time.time()
    if _TOKEN_CACHE["value"] and now - _TOKEN_CACHE["ts"] < _TOKEN_TTL:
        return _TOKEN_CACHE["value"]
    machine = _read_secret(os.path.join(ROUTER_DATA_DIR, "machine-id"))
    secret = _read_secret(os.path.join(ROUTER_DATA_DIR, "auth", "cli-secret"))
    if not machine or not secret:
        raise RouterError(
            "router_not_configured",
            "9Router data dir is missing machine-id or auth/cli-secret")
    token = hashlib.sha256(
        (machine + _CLI_TOKEN_SALT + secret).encode("utf-8")).hexdigest()[:16]
    _TOKEN_CACHE.update({"value": token, "ts": now})
    return token


def _call(method: str, path: str, body: dict | None = None,
          timeout: float = 20.0, extra_headers: dict | None = None) -> object:
    """One HTTP call to 9Router, with the CLI token attached.

    ``extra_headers`` exists for the connection-pin header the router honours on
    its model-test route: without it every probe would be routed by the router's
    own rotation and would answer for *some* account, not the one the user
    clicked. Everything else goes through the default header set.

    Raises RouterError with a stable code so the UI can tell "router is down"
    apart from "this provider rejected the flow".
    """
    url = ROUTER_BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json", _TOKEN_HEADER: cli_token()}
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(1 << 20)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read(4096).decode("utf-8", "replace")
        except Exception:
            pass
        # A 4xx from 9Router usually carries a JSON {"error": "..."} message.
        try:
            parsed = json.loads(detail)
            message = parsed.get("error") or parsed.get("message") or detail
        except Exception:
            message = detail or f"HTTP {exc.code}"
        raise RouterError("router_rejected", str(message)[:300]) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RouterError("router_unreachable",
                          f"9Router at {ROUTER_BASE} is not reachable") from exc
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception as exc:
        raise RouterError("router_bad_response",
                          "9Router returned a non-JSON body") from exc


def health() -> dict:
    """Is the broker reachable and does it hold any connections?"""
    try:
        data = _call("GET", "/api/providers")
    except RouterError as exc:
        return {"available": False, "reason": exc.code, "message": exc.message,
                "base_url": ROUTER_BASE}
    connections = data.get("connections", []) if isinstance(data, dict) else []
    return {"available": True, "base_url": ROUTER_BASE,
            "connection_count": len(connections)}


def _public_connection(row: dict) -> dict:
    """Strip a 9Router connection row down to display-only fields.

    The broker's row carries live token material under ``data`` (and, for API
    keys, the key itself). None of that belongs in a browser response, so only
    the identity/status fields survive.
    """
    return {
        "id": row.get("id"),
        "provider": row.get("provider"),
        "auth_type": row.get("authType"),
        "name": row.get("name") or "",
        "email": row.get("email") or "",
        "priority": row.get("priority"),
        "active": bool(row.get("isActive")),
        "status": row.get("testStatus") or "unknown",
        "expires_at": row.get("expiresAt"),
        "last_used_at": row.get("lastUsedAt"),
        "last_error": row.get("lastError") or "",
        "error_code": row.get("errorCode") or "",
        # Which proxy pool this connection routes through, if any. The pool row
        # itself lives behind /api/proxy-pools; only the id is stored here.
        "proxy_pool_id": (row.get("providerSpecificData") or {}).get("proxyPoolId") or "",
        # Model names this connection has been used with, in the router's own
        # order. The router tracks one `modelLock_<model>` field per model per
        # connection, which is the only per-account evidence of what that account
        # has served — a Codex ChatGPT plan answers `gpt-5.6-luna` but rejects
        # `gpt-5.5-image`, so probing with the wrong one reports a healthy
        # account as broken. Order is preserved: the first entry is the most
        # likely to be the account's default.
        "models_seen": [
            str(key)[len("modelLock_"):]
            for key in row
            if str(key).startswith("modelLock_") and str(key)[len("modelLock_"):]
        ],
    }


def _public_pool(row: dict) -> dict:
    """A proxy pool, display-only.

    ``proxyUrl`` can embed ``user:pass@host``. It is returned because the edit
    form has to be able to show what is actually configured — but the UI masks
    it everywhere else, so a screenshot or a shared screen does not leak the
    credential.
    """
    return {
        "id": row.get("id"),
        "name": row.get("name") or "",
        "proxy_url": row.get("proxyUrl") or "",
        "no_proxy": row.get("noProxy") or "",
        "type": row.get("type") or "http",
        "active": bool(row.get("isActive")),
        "strict": bool(row.get("strictProxy")),
        "status": row.get("testStatus") or "unknown",
        "bound_count": int(row.get("boundConnectionCount") or 0),
    }


def list_proxy_pools() -> list[dict]:
    """Every proxy pool, with how many connections are bound to it."""
    data = _call("GET", "/api/proxy-pools?includeUsage=true")
    rows = data.get("proxyPools", []) if isinstance(data, dict) else []
    return [_public_pool(r) for r in rows if isinstance(r, dict)]


def create_proxy_pool(name: str, proxy_url: str, no_proxy: str = "",
                      is_active: bool = True, strict: bool = False,
                      pool_type: str = "http") -> dict:
    """Add a proxy pool. The broker rejects an empty name or URL."""
    data = _call("POST", "/api/proxy-pools", {
        "name": str(name or "").strip(), "proxyUrl": str(proxy_url or "").strip(),
        "noProxy": str(no_proxy or "").strip(), "isActive": bool(is_active),
        "strictProxy": bool(strict), "type": pool_type or "http"})
    row = data.get("proxyPool") if isinstance(data, dict) else None
    return _public_pool(row) if isinstance(row, dict) else {}


def update_proxy_pool(pool_id: str, fields: dict) -> dict:
    """Patch a pool. Only the keys present in ``fields`` are sent, so a caller
    can rename a pool without having to resend its proxy URL."""
    body: dict = {}
    if "name" in fields:
        body["name"] = str(fields.get("name") or "").strip()
    if "proxy_url" in fields:
        body["proxyUrl"] = str(fields.get("proxy_url") or "").strip()
    if "no_proxy" in fields:
        body["noProxy"] = str(fields.get("no_proxy") or "").strip()
    if "active" in fields:
        body["isActive"] = bool(fields.get("active"))
    if "strict" in fields:
        body["strictProxy"] = bool(fields.get("strict"))
    if "type" in fields:
        body["type"] = str(fields.get("type") or "http")
    data = _call("PUT", f"/api/proxy-pools/{quote(str(pool_id), safe='')}", body)
    row = data.get("proxyPool") if isinstance(data, dict) else None
    return _public_pool(row) if isinstance(row, dict) else {}


def delete_proxy_pool(pool_id: str) -> dict:
    _call("DELETE", f"/api/proxy-pools/{quote(str(pool_id), safe='')}")
    return {"deleted": str(pool_id)}


def test_proxy_pool(pool_id: str) -> dict:
    """Probe a saved pool from the broker side (it has network access)."""
    try:
        data = _call("POST", f"/api/proxy-pools/{quote(str(pool_id), safe='')}/test",
                     timeout=40.0)
    except RouterError as exc:
        # A pool that cannot connect is a TEST RESULT, not a router outage.
        # Reporting it as PROVIDER_UNAVAILABLE would tell the user the wrong
        # thing entirely: the broker is fine, the proxy is not.
        return {"ok": False, "status": None, "error": exc.message or str(exc),
                "latency_ms": None}
    if not isinstance(data, dict):
        return {"ok": False, "status": None, "error": "respons tidak dikenal",
                "latency_ms": None}
    return {"ok": bool(data.get("ok")), "status": data.get("status"),
            "error": data.get("error") or "", "latency_ms": data.get("elapsedMs")}


def test_proxy_url(proxy_url: str) -> dict:
    """Probe a URL BEFORE it is saved, so a typo is caught in the form.

    Same reasoning as ``test_proxy_pool``: the broker returns a non-2xx when the
    proxy refuses the connection, and that must surface as ``ok: false`` with the
    real reason — not as a bridge failure.
    """
    try:
        data = _call("POST", "/api/settings/proxy-test",
                     {"proxyUrl": str(proxy_url or "").strip()}, timeout=40.0)
    except RouterError as exc:
        return {"ok": False, "status": None, "error": exc.message or str(exc),
                "latency_ms": None}
    if not isinstance(data, dict):
        return {"ok": False, "status": None, "error": "respons tidak dikenal",
                "latency_ms": None}
    return {"ok": bool(data.get("ok")), "status": data.get("status"),
            "error": data.get("error") or "", "latency_ms": data.get("elapsedMs")}


def set_connection_proxy(connection_id: str, pool_id: str | None) -> dict:
    """Bind a connection to a pool, or clear it with None.

    The binding is reported from the REQUEST, not from the PUT's echo: the
    broker's response for a provider update omits ``providerSpecificData``, so
    reading it back there would always look like the bind had failed. A 2xx from
    the PUT is the proof that it applied; the caller refreshes for the full row.
    """
    _call("PUT", f"/api/providers/{quote(str(connection_id), safe='')}",
          {"proxyPoolId": pool_id or None})
    return {"id": str(connection_id), "proxy_pool_id": str(pool_id or "")}


def list_provider_nodes() -> list[dict]:
    """The router's own provider nodes — the custom endpoints the operator
    added (each carries the NAME they gave it, e.g. "Vantis", "JustWoker", and
    the routing prefix its models use).

    This is what lets a card show the real provider name instead of the dialect
    the catalog knows it by ("OpenAI" / "Anthropic"). Display-only fields; the
    node's stored key never appears here.
    """
    data = _call("GET", "/api/provider-nodes")
    nodes = data.get("nodes", []) if isinstance(data, dict) else []
    out: list[dict] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        out.append({
            "id": str(n.get("id") or ""),
            "name": str(n.get("name") or n.get("prefix") or ""),
            "prefix": str(n.get("prefix") or ""),
            "type": str(n.get("type") or ""),
            "api_type": str(n.get("apiType") or ""),
            "base_url": str(n.get("baseUrl") or ""),
        })
    return out


def list_connections() -> list[dict]:
    """Every provider connection the broker holds, secrets removed."""
    data = _call("GET", "/api/providers")
    rows = data.get("connections", []) if isinstance(data, dict) else []
    return [_public_connection(r) for r in rows if isinstance(r, dict)]


def set_connection_active(connection_id: str, active: bool) -> dict:
    """Enable or disable one connection (the dashboard's active toggle)."""
    row = _call("PUT", f"/api/providers/{quote(str(connection_id), safe='')}",
                {"isActive": bool(active)})
    return _public_connection(row) if isinstance(row, dict) else {}


def set_connection_priority(connection_id: str, priority: int) -> dict:
    """Move a connection within its provider's rotation order."""
    row = _call("PUT", f"/api/providers/{quote(str(connection_id), safe='')}",
                {"priority": int(priority)})
    return _public_connection(row) if isinstance(row, dict) else {}


def set_connection_name(connection_id: str, name: str) -> dict:
    """Rename a connection's label.

    Only the display name is written. The account's identity (email / token)
    and its routing behaviour are untouched — this is the same field the
    broker's own dashboard lets you edit, and it is what the row shows when a
    connection has no email.
    """
    row = _call("PUT", f"/api/providers/{quote(str(connection_id), safe='')}",
                {"name": str(name or "").strip()})
    return _public_connection(row) if isinstance(row, dict) else {}


# Auto-ping (quota warming) — the router's own per-account opt-in.
#
# 9Router warms a subscription's rolling window by sending a tiny request right
# after the window resets, so the next real prompt does not pay the cold-start
# penalty. The feature is deliberately limited to the two providers whose plans
# expose a resettable window (Claude and Codex) and to OAuth accounts, because
# the switch is meaningless for a plain API key. Offering it anywhere else would
# be a control the router silently ignores.
AUTO_PING_PROVIDERS = ("claude", "codex")


def _auto_ping_key(provider: str) -> str:
    return f"{str(provider).strip().lower()}AutoPing"


def auto_ping_state() -> dict:
    """Per-account auto-ping flags, exactly as the router stores them.

    Shape: ``{"codex": {"enabled": bool, "connections": {"<id>": bool}}}``.

    Every supported provider is reported even when the router has no setting
    for it yet — a missing block means "off", not "unsupported", and the UI
    needs the provider to be present to draw the switch at all. The router
    treats an absent block as disabled, so reporting it as such is the honest
    reading.
    """
    data = _call("GET", "/api/settings")
    out: dict = {}
    for provider in AUTO_PING_PROVIDERS:
        row = data.get(_auto_ping_key(provider)) if isinstance(data, dict) else None
        conns = row.get("connections") if isinstance(row, dict) else None
        out[provider] = {
            "enabled": bool(row.get("enabled")) if isinstance(row, dict) else False,
            "connections": {str(k): bool(v) for k, v in conns.items()}
                           if isinstance(conns, dict) else {},
        }
    return out


def set_auto_ping(provider: str, enabled: bool | None = None,
                  connection_id: str | None = None,
                  connection_on: bool | None = None) -> dict:
    """Turn auto-ping on/off for a provider, and/or for one of its accounts.

    Read-modify-write on purpose: the settings blob holds every other provider's
    configuration too, so a blind overwrite would silently reset it all. When a
    single account is switched on, the provider-level master switch is raised in
    the same PATCH — an account flag under a disabled master is a switch that
    looks on and does nothing.
    """
    provider = str(provider).strip().lower()
    if provider not in AUTO_PING_PROVIDERS:
        raise RouterError("auto_ping_unsupported",
                          f"{provider} tidak mendukung auto-ping")
    key = _auto_ping_key(provider)
    data = _call("GET", "/api/settings")
    row = dict((data.get(key) or {}) if isinstance(data, dict) else {})
    conns = dict(row.get("connections") or {})
    if enabled is not None:
        row["enabled"] = bool(enabled)
    if connection_id is not None:
        conns[str(connection_id)] = bool(connection_on)
        if connection_on and "enabled" not in row:
            row["enabled"] = True
    row["connections"] = conns
    _call("PATCH", "/api/settings", {key: row})
    return auto_ping_state()


def delete_connection(connection_id: str) -> dict:
    """Remove a connection. Irreversible — the caller must confirm first."""
    _call("DELETE", f"/api/providers/{quote(str(connection_id), safe='')}")
    return {"deleted": str(connection_id)}


def create_connection(provider: str, name: str, api_key: str,
                      model: str = "", priority: int | None = None) -> dict:
    """Add one API-key connection to an EXISTING provider.

    The router owns the provider definition (base URL, prefix, apiType); this
    only attaches another credential to it, which is what "Add API key" means on
    its dashboard. No proxy is sent: a proxy is an explicit per-connection choice
    made afterwards, never a side effect of adding a key.
    """
    provider = _compact(provider)
    api_key = str(api_key or "").strip()
    if not provider:
        raise RouterError("invalid_provider", "provider wajib diisi")
    if not api_key:
        raise RouterError("invalid_key", "API key wajib diisi")
    body: dict = {
        "provider": provider,
        "apiKey": api_key,
        "name": _compact(name) or provider,
    }
    if _compact(model):
        body["model"] = _compact(model)
    if priority is not None:
        try:
            body["priority"] = max(1, int(priority))
        except (TypeError, ValueError):
            pass
    data = _call("POST", "/api/providers", body, timeout=40.0)
    row = data.get("connection") if isinstance(data, dict) else None
    if not isinstance(row, dict):
        # Some router builds echo the row at the top level instead of nesting it.
        row = data if isinstance(data, dict) and data.get("id") else None
    return _public_connection(row) if isinstance(row, dict) else {}


def bulk_create_connections(provider: str, entries: list[dict],
                            model: str = "") -> dict:
    """Add many API keys in one go, reporting per-line outcomes.

    Serial on purpose: the router writes its own settings file per add, and a
    parallel burst of writes to one provider is exactly the shape that produces
    a half-applied list. Each entry is ``{name, api_key}``.
    """
    results: list[dict] = []
    for entry in entries or []:
        name = _compact(entry.get("name")) or ""
        key = str(entry.get("api_key") or "").strip()
        if not key:
            results.append({"name": name, "ok": False, "error": "API key kosong"})
            continue
        try:
            row = create_connection(provider, name, key, model=model)
            results.append({"name": name or row.get("name") or "", "ok": True,
                            "error": "", "id": row.get("id")})
        except RouterError as exc:
            results.append({"name": name, "ok": False, "error": exc.message or str(exc)})
    added = sum(1 for r in results if r["ok"])
    return {"provider": provider, "added": added, "failed": len(results) - added,
            "total": len(results), "results": results}


def test_connection(connection_id: str) -> dict:
    """Probe one connection the way the dashboard's Test button does."""
    data = _call("POST", f"/api/providers/{quote(str(connection_id), safe='')}/test")
    if not isinstance(data, dict):
        return {"valid": False}
    return {"valid": bool(data.get("valid")), "status": data.get("status") or "",
            "error": data.get("error") or "", "latency_ms": data.get("latencyMs")}


def _pin_headers(connection_id: str) -> dict:
    """Pin a request to ONE connection.

    The router's per-connection test route refuses OAuth providers outright
    ("Provider test not supported"), so a token refresh is not enough to prove an
    account works. Its gateway, however, honours ``x-9router-connection-id`` on
    the model-test and chat routes — that is what makes "test THIS account"
    honest instead of "test whatever the rotation picked".
    """
    return {"x-9router-connection-id": str(connection_id)}


def test_connection_model(connection_id: str, model: str,
                          timeout: float = 45.0) -> dict:
    """Prove one connection can actually answer, by pinning a real model call.

    This is the honest per-account test: the router routes the request through
    exactly this connection, so a pass means THIS account is usable and a fail
    carries the upstream reason (quota, revoked token, 404 model).
    """
    mid = _compact(model)
    if not mid:
        return {"valid": False, "error": "no model to probe with", "latency_ms": None}
    try:
        data = _call("POST", "/api/models/test", {"model": mid, "kind": "llm"},
                     timeout=timeout, extra_headers=_pin_headers(connection_id))
    except RouterError as exc:
        # A refused probe is a TEST RESULT, not a broker outage.
        return {"valid": False, "error": exc.message or str(exc),
                "latency_ms": None, "status": None}
    if not isinstance(data, dict):
        return {"valid": False, "error": "unrecognised response", "latency_ms": None}
    ok = bool(data.get("ok"))
    return {
        "valid": ok,
        "status": data.get("status"),
        "error": "" if ok else str(data.get("error") or "model test failed")[:400],
        "latency_ms": data.get("latencyMs"),
        "model": mid,
    }


# ── Routing strategy (round robin + sticky) ──────────────────────────────────
#
# The router keeps a per-provider strategy in its own settings, not on the
# connection rows: ``providerStrategies[<provider>] = {fallbackStrategy,
# stickyRoundRobinLimit}``. Its dashboard exposes exactly one switch for it
# ("Round Robin — cycle through accounts to distribute load") plus a Sticky
# limit, so Zeline drives the same two fields rather than inventing a parallel
# concept the router would ignore.
_STRATEGY_OFF = "fill-first"
_STRATEGY_ON = "round-robin"


def provider_strategy(provider: str) -> dict:
    """Read one provider's rotation strategy as a small, flat shape."""
    data = _call("GET", "/api/settings")
    strategies = data.get("providerStrategies") if isinstance(data, dict) else None
    row = (strategies or {}).get(str(provider)) or {}
    global_sticky = data.get("stickyRoundRobinLimit") if isinstance(data, dict) else None
    sticky = row.get("stickyRoundRobinLimit")
    if sticky is None:
        sticky = global_sticky
    try:
        sticky = int(sticky)
    except (TypeError, ValueError):
        sticky = 3
    return {
        "provider": str(provider),
        "round_robin": str(row.get("fallbackStrategy") or "") == _STRATEGY_ON,
        "sticky": max(1, sticky),
    }


def set_provider_strategy(provider: str, round_robin: bool | None = None,
                          sticky: int | None = None) -> dict:
    """Turn round robin on/off for one provider, and/or set its sticky limit.

    Read-modify-write on purpose: the settings blob holds every other provider's
    strategy too, so a blind overwrite would silently reset them all.
    """
    provider = str(provider)
    data = _call("GET", "/api/settings")
    strategies = dict((data.get("providerStrategies") or {}) if isinstance(data, dict) else {})
    row = dict(strategies.get(provider) or {})

    if round_robin is not None:
        row["fallbackStrategy"] = _STRATEGY_ON if round_robin else _STRATEGY_OFF
    if sticky is not None:
        try:
            row["stickyRoundRobinLimit"] = max(1, int(sticky))
        except (TypeError, ValueError):
            raise RouterError("invalid_sticky", "sticky harus angka >= 1")
    if not row:
        return provider_strategy(provider)

    strategies[provider] = row
    _call("PATCH", "/api/settings", {"providerStrategies": strategies})
    return provider_strategy(provider)


def authorize(provider: str, redirect_uri: str = "") -> dict:
    """Start an OAuth flow and return what the user must do next.

    The response shape depends on the provider's flow type:
      * ``device_code`` — carries user_code + verification_uri; the UI shows
        the code and polls.
      * ``authorization_code[_pkce]`` — carries authUrl; the UI opens it and
        waits for the broker's callback.
    Both are passed through as-is so the UI needs no per-provider branching.
    """
    if not redirect_uri:
        redirect_uri = f"{ROUTER_BASE}/callback"
    query = urllib.parse.urlencode({"redirect_uri": redirect_uri})
    data = _call("GET", f"/api/oauth/{urllib.parse.quote(provider)}/authorize?{query}")
    if not isinstance(data, dict):
        raise RouterError("router_bad_response", "authorize returned no payload")
    return {
        "provider": provider,
        "auth_url": data.get("authUrl") or "",
        "state": data.get("state") or "",
        "code_verifier": data.get("codeVerifier") or "",
        "flow_type": data.get("flowType") or "authorization_code",
        "redirect_uri": data.get("redirectUri") or redirect_uri,
        "callback_path": data.get("callbackPath") or "/callback",
        "fixed_port": data.get("fixedPort"),
    }


def device_code(provider: str) -> dict:
    """Request a device-code grant. Raises if the provider lacks that flow."""
    data = _call("GET", f"/api/oauth/{urllib.parse.quote(provider)}/device-code")
    if not isinstance(data, dict):
        raise RouterError("router_bad_response", "device-code returned no payload")
    return {
        "provider": provider,
        "device_code": data.get("device_code") or "",
        "user_code": data.get("user_code") or "",
        "verification_uri": (data.get("verification_uri")
                             or data.get("verificationUri") or ""),
        "verification_uri_complete": data.get("verification_uri_complete") or "",
        "expires_in": data.get("expires_in"),
        "interval": data.get("interval") or 5,
        "code_verifier": data.get("codeVerifier") or "",
        # Provider-private fields the broker needs echoed back on poll.
        "extra": {k: v for k, v in data.items() if k.startswith("_")},
    }


def poll(provider: str, device_code_value: str, code_verifier: str,
         extra: dict | None = None) -> dict:
    """Poll a device-code grant. ``pending`` means keep waiting."""
    body = {"deviceCode": device_code_value, "codeVerifier": code_verifier}
    if extra:
        body.update(extra)
    data = _call("POST", f"/api/oauth/{urllib.parse.quote(provider)}/poll", body)
    if not isinstance(data, dict):
        raise RouterError("router_bad_response", "poll returned no payload")
    connection = data.get("connection")
    return {
        "success": bool(data.get("success")),
        "pending": bool(data.get("pending")),
        "error": data.get("error") or "",
        "error_description": data.get("errorDescription") or "",
        "connection": _public_connection(connection) if isinstance(connection, dict) else None,
    }


def exchange(provider: str, code: str, redirect_uri: str,
             code_verifier: str, state: str = "") -> dict:
    """Exchange an authorization code for a connection (manual paste path)."""
    body = {"code": code, "redirectUri": redirect_uri,
            "codeVerifier": code_verifier, "state": state}
    data = _call("POST", f"/api/oauth/{urllib.parse.quote(provider)}/exchange", body)
    if not isinstance(data, dict):
        raise RouterError("router_bad_response", "exchange returned no payload")
    connection = data.get("connection")
    return {
        "success": bool(data.get("success")),
        "error": data.get("error") or "",
        "connection": _public_connection(connection) if isinstance(connection, dict) else None,
    }


_MODELS_CACHE: dict = {"at": 0.0, "rows": None}
_MODELS_TTL = 20.0


def _all_models() -> list:
    """The router's global model list, cached for a few seconds.

    ``/api/models`` takes ~3s on this broker; it is read for every provider's
    model block, so an uncached call made opening a provider feel like it hung.
    A short TTL keeps the list fresh without paying the cost on every open.
    """
    now = time.time()
    if _MODELS_CACHE["rows"] is not None and now - _MODELS_CACHE["at"] < _MODELS_TTL:
        return _MODELS_CACHE["rows"]
    data = _call("GET", "/api/models")
    rows = data.get("models", []) if isinstance(data, dict) else []
    _MODELS_CACHE["rows"] = rows
    _MODELS_CACHE["at"] = now
    return rows


def provider_models(provider_id: str) -> list[str]:
    """Model ids the router can route for one provider.

    The router's global model list tags every entry with its owning provider, but
    it keys some providers by a short internal alias rather than the catalog id
    (``cbai`` for CodeBuddy, ``cx`` for Codex, ``ag`` for Antigravity, …). Every
    plausible alias for the requested id is matched, so a provider that is
    demonstrably connected does not come back with an empty list.
    """
    data = _all_models()
    rows = data if isinstance(data, list) else (data.get("models", []) if isinstance(data, dict) else [])
    wanted = _provider_aliases(provider_id)
    models: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("provider") or "") not in wanted:
            continue
        # Prefer the id the caller would actually send; fall back to the alias.
        model = _compact(row.get("model") or row.get("alias") or row.get("name"))
        if model and model not in models:
            models.append(model)
    return models


# Router-internal provider aliases that differ from the catalog id. Only the
# ones observed in the router's own model list are listed; a provider whose id
# already matches needs no entry. Kept as a table rather than inferred, because
# the alias is arbitrary (`cbai`, `cx`, `ag`) and cannot be derived from the id.
_PROVIDER_ALIASES = {
    "codebuddy-intl": ("codebuddy-intl", "cbai", "cc"),
    "codebuddy-cn": ("codebuddy-cn", "cbcn"),
    "codex": ("codex", "cx"),
    "antigravity": ("antigravity", "ag"),
    "gemini-cli": ("gemini-cli", "gcli", "gc"),
    "github": ("github", "gh"),
    "gitlab": ("gitlab", "gl"),
    "iflow": ("iflow", "if"),
    "kilocode": ("kilocode", "kc"),
    "kimi": ("kimi", "kr"),
    "cline": ("cline", "cl"),
    "clinepass": ("clinepass",),
    "qoder": ("qoder", "qd"),
    "xai": ("xai", "grok-cli", "gb"),
    "grok-cli": ("grok-cli", "xai", "gb"),
    "cursor": ("cursor",),
    "kiro": ("kiro",),
    "claude": ("claude", "anthropic"),
}


def _provider_aliases(provider_id: str) -> set[str]:
    aliases = _PROVIDER_ALIASES.get(provider_id)
    return set(aliases) if aliases else {provider_id}


def _compact(value: object) -> str:
    return " ".join(str(value or "").split())[:200]


def flow_capabilities(providers: list[str]) -> dict:
    """Which OAuth verbs each provider supports, probed live.

    The broker answers 400 with a specific message when a provider lacks
    device-code, so one probe per provider settles it without hardcoding a
    table that would drift as the router adds providers.
    """
    out: dict[str, dict] = {}
    for provider in providers:
        cap = {"provider": provider, "device_code": False, "authorize": False,
               "flow_type": "", "error": ""}
        try:
            auth = authorize(provider)
            cap["authorize"] = bool(auth["auth_url"] or auth["state"])
            cap["flow_type"] = auth["flow_type"]
        except RouterError as exc:
            cap["error"] = exc.message
        try:
            device_code(provider)
            cap["device_code"] = True
        except RouterError:
            cap["device_code"] = False
        out[provider] = cap
    return out

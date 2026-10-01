#!/data/data/com.termux/files/usr/bin/python3.13
"""Run the v0.2.5 `zeline_app` gateway standalone (REST + SSE on port 8082).

Zeline v0.3.4 dropped the `zeline_app` gateway module, but the app frontend
(localhost:5173) still speaks its REST/SSE contract. This launcher boots that
gateway from the older venv so the app can proxy to a REAL agent runtime.

Env defaults set here (only if not already set by the caller):
  ZELINE_ALLOW_LOOPBACK=1
      Agent yang MENJALANKAN server lokal (mis. `http.server` di 127.0.0.1:8080)
      harus bisa memanggil servernya sendiri lewat http_request / web_fetch.
      SSRF guard tetap memblokir seluruh jaringan privat (LAN/RFC1918, metadata
      cloud 169.254.*), hanya loopback MURNI (localhost / 127.0.0.0/8 / ::1)
      yang diizinkan. Set 0 untuk mematikan lagi.
"""
import sys
import os
import threading

VENV = "/data/data/com.termux/files/home/.local/share/zeline/venv/lib/python3.13/site-packages"
sys.path.insert(0, VENV)

# Default loopback allowlist ON for the local app gateway (see docstring).
os.environ.setdefault("ZELINE_ALLOW_LOOPBACK", "1")

def main():
    from zeline import config
    from zeline.sessions import SessionStore
    from zeline.gateways import zeline_app

    cfg = config.stored_config_copy()
    gw = (cfg.get("gateways") or {}).get("zeline_app") or {}
    if not gw.get("enabled"):
        print("[launcher] zeline_app gateway is disabled in config; enabling for this run", flush=True)
        gw["enabled"] = True

    store = SessionStore()
    stop = threading.Event()
    print(
        f"[launcher] starting zeline_app gateway on {gw.get('host','127.0.0.1')}:{gw.get('port',8082)}"
        f"  (loopback={'on' if os.environ.get('ZELINE_ALLOW_LOOPBACK','') in ('1','true','yes') else 'off'})",
        flush=True,
    )
    try:
        zeline_app.start(store, gw, stop)
    except KeyboardInterrupt:
        stop.set()

if __name__ == "__main__":
    main()

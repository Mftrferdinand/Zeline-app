# Zeline App

Desktop/mobile web app for the **Zeline** agentic AI framework by Zerolinear.

This is the graphical client: a chat surface plus provider/model management,
usage, settings, and a live activity feed backed by the Zeline gateway over SSE.

## What's here

| Path | What it is |
|---|---|
| `server.py` | Dev server. Serves the SPA **and** proxies `/api/v1/*` to the gateway, streaming real SSE. |
| `index.html` | App shell. |
| `style.css` | All styling (the app is deliberately dependency-free — no bundler). |
| `app1.js` … `app5.js` | Frontend logic, split by area (shell / chat / providers / usage / settings). |
| `demo.html` | Static demo of every progress label, tool state, and UI state. Useful as a reference when changing the activity feed. |
| `assets/` | Icons, backgrounds, provider logos. |
| `start.sh` | Starts the gateway **and** this app together (see below). |

## Requirements

- **Python 3.10+**
- The **Zeline** framework, installed so `import zeline` works:
  ```bash
  pip install zeline          # or: pip install -e /path/to/Zeline
  ```
- Configured provider credentials (`zeline setup`, or an existing `~/.zeline/config.yaml`).

## Run

One command starts both the gateway and the app:

```bash
bash start.sh
```

Then open:

| | URL |
|---|---|
| App | http://localhost:5173 |
| Demo (all UI states) | http://localhost:5173/demo.html |
| Gateway health | http://127.0.0.1:8082/api/v1/health |

`start.sh` kills any previous instance first, so it is safe to re-run.

### Run the pieces by hand

```bash
# terminal 1 — gateway (agent runtime)
ZELINE_ALLOW_LOOPBACK=1 python run_zeline_gateway.py

# terminal 2 — app
ZELINE_APP_UPSTREAM=http://127.0.0.1:8082 ZELINE_FE_PORT=5173 python server.py
```

`server.py` reads two env vars:

| Var | Default | Meaning |
|---|---|---|
| `ZELINE_APP_UPSTREAM` | `http://127.0.0.1:8082` | Where the Zeline gateway listens. |
| `ZELINE_FE_PORT` | `5173` | Port this app serves on. |

## Notes for working on this repo

- **No build step, no dependencies.** Edit the HTML/CSS/JS and reload. Keep it
  that way unless there is a strong reason — the app is meant to run on a phone
  in Termux.
- **Access is token-gated in the browser.** The app talks to the gateway with a
  gateway token, separate from the agent/API key. Do not put provider API keys
  or `~/.zeline/config.yaml` in this repo.
- The `qa_*.py` / `shoot*.py` / `verify_*.py` scripts are local QA helpers that
  drive a browser for screenshots. They contain machine-specific paths and are
  **not** part of the app; ignore them (or fix the paths) when running elsewhere.

## Related

- **Framework:** https://github.com/Mftrferdinand/Zeline
- **Lab:** Zerolinear

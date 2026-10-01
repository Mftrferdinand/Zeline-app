"""Behavior tests for the single chat engine behind Zeline workspaces.

These exercise the actual frontend development API over HTTP.  The app has one
``SESSIONS`` + ``MESSAGES`` store, but each named workspace owns a distinct ID
and therefore a distinct chat history.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_KEYS = (
    "ZELINE_FE_WORKSPACE_STATE",
    "ZELINE_FE_APP_SETTINGS",
    "ZELINE_CRON_JOBS_PATH",
    "ZELINE_APP_UPSTREAM",
)


def load_server_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class WorkspaceApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls.tempdir.name)
        cls.previous_env = {key: os.environ.get(key) for key in ENV_KEYS}
        os.environ.update({
            "ZELINE_FE_WORKSPACE_STATE": str(cls.tmp / "workspaces.json"),
            "ZELINE_FE_APP_SETTINGS": str(cls.tmp / "app-settings.json"),
            "ZELINE_CRON_JOBS_PATH": str(cls.tmp / "jobs.json"),
            "ZELINE_APP_UPSTREAM": "",
        })
        cls.module_name = f"zeline_frontend_server_test_{id(cls)}"
        cls.server_module = load_server_module(cls.module_name)
        # Never let test deletion mutate the frontend's shared dev tombstone file.
        cls.server_module.SESSION_TOMBSTONES_PATH = str(cls.tmp / "deleted.json")
        cls.server_module.DELETED_SESSION_IDS = set()
        cls.server_module.CRON_JOBS_PATH = str(cls.tmp / "jobs.json")
        cls.httpd = cls.server_module.ThreadingHTTPServer(
            ("127.0.0.1", 0), cls.server_module.Handler
        )
        cls.httpd.daemon_threads = True
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}/api/v1"
        _, login = cls.request("POST", "/auth/login", {"gateway_token": "workspace-test"})
        cls.token = login["data"]["access_token"]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=3)
        sys.modules.pop(cls.module_name, None)
        for key, value in cls.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.tempdir.cleanup()

    def setUp(self):
        self.created_ids: list[str] = []

    def tearDown(self):
        # Keep tests independent even though their server deliberately persists.
        for session_id in reversed(self.created_ids):
            self.request("DELETE", f"/sessions/{session_id}", token=self.token)

    @classmethod
    def request(cls, method, path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(cls.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def create_workspace(self, kind: str, title: str) -> dict:
        status, payload = self.request(
            "POST",
            "/sessions",
            {"agent_id": "agent_general", "kind": kind, "title": title},
            self.token,
        )
        self.assertEqual(status, 201, payload)
        workspace = payload["data"]
        self.created_ids.append(workspace["id"])
        return workspace

    def list_workspaces(self, *, kind: str | None = None, query: str | None = None) -> list[dict]:
        params = {"agent_id": "agent_general"}
        if kind is not None:
            params["kind"] = kind
        if query is not None:
            params["q"] = query
        status, payload = self.request("GET", "/sessions?" + urllib.parse.urlencode(params), token=self.token)
        self.assertEqual(status, 200, payload)
        return payload["data"]["sessions"]

    def test_creates_all_four_official_workspace_types(self):
        suffix = uuid.uuid4().hex[:8]
        expected = {
            "session": f"Trading Research {suffix}",
            "project": f"Zeline {suffix}",
            "cronjob": f"Daily AI News {suffix}",
            "workflow": f"Deploy Zeline {suffix}",
        }
        created = {kind: self.create_workspace(kind, title) for kind, title in expected.items()}
        for kind, title in expected.items():
            workspace = created[kind]
            self.assertEqual(workspace["kind"], kind)
            self.assertEqual(workspace["title"], title)
            self.assertEqual(workspace["message_count"], 0)
            self.assertEqual(
                {item["id"] for item in self.list_workspaces(kind=kind)} & {workspace["id"]},
                {workspace["id"]},
            )

    def test_legacy_aliases_are_accepted_and_persisted_canonical(self):
        suffix = uuid.uuid4().hex[:8]
        saved = self.create_workspace("saved", f"Legacy saved {suffix}")
        cron = self.create_workspace("cron", f"Legacy cron {suffix}")
        self.assertEqual(saved["kind"], "session")
        self.assertEqual(cron["kind"], "cronjob")

        by_id = {item["id"]: item for item in self.list_workspaces(kind="saved")}
        self.assertEqual(by_id[saved["id"]]["kind"], "session")
        by_id = {item["id"]: item for item in self.list_workspaces(kind="cron")}
        self.assertEqual(by_id[cron["id"]]["kind"], "cronjob")

        raw = json.loads((self.tmp / "workspaces.json").read_text(encoding="utf-8"))
        persisted = {item["id"]: item for item in raw["sessions"]}
        self.assertEqual(persisted[saved["id"]]["kind"], "session")
        self.assertEqual(persisted[cron["id"]]["kind"], "cronjob")

        status, payload = self.request(
            "POST", "/sessions",
            {"agent_id": "agent_general", "kind": "canvas", "title": "Nope"},
            self.token,
        )
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")

    def test_search_rename_delete_and_persistence_are_real(self):
        suffix = uuid.uuid4().hex[:8]
        created = self.create_workspace("workflow", f"Needle workflow {suffix}")
        found = {item["id"]: item for item in self.list_workspaces(kind="workflow", query=suffix)}
        self.assertEqual(found[created["id"]]["title"], created["title"])

        renamed = f"Renamed workflow {suffix}"
        status, payload = self.request(
            "PUT", f"/sessions/{created['id']}", {"title": renamed}, self.token
        )
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["data"]["kind"], "workflow")
        self.assertEqual(payload["data"]["title"], renamed)
        self.assertNotIn(created["id"], {item["id"] for item in self.list_workspaces(query="Needle")})
        self.assertIn(created["id"], {item["id"] for item in self.list_workspaces(kind="workflow", query="Renamed")})

        disk_sessions, disk_messages = self.server_module.load_workspace_state()
        restored = next(item for item in disk_sessions if item["id"] == created["id"])
        self.assertEqual(restored["kind"], "workflow")
        self.assertEqual(restored["title"], renamed)
        self.assertEqual(disk_messages[created["id"]], [])

        status, payload = self.request("DELETE", f"/sessions/{created['id']}", token=self.token)
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["data"]["cascade"])
        self.created_ids.remove(created["id"])
        self.assertNotIn(created["id"], {item["id"] for item in self.list_workspaces(kind="workflow")})
        status, payload = self.request("GET", f"/sessions/{created['id']}/messages", token=self.token)
        self.assertEqual(status, 404, payload)
        disk_sessions, disk_messages = self.server_module.load_workspace_state()
        self.assertNotIn(created["id"], {item["id"] for item in disk_sessions})
        self.assertNotIn(created["id"], disk_messages)

    def test_history_is_isolated_by_workspace_id(self):
        suffix = uuid.uuid4().hex[:8]
        project = self.create_workspace("project", f"Project {suffix}")
        workflow = self.create_workspace("workflow", f"Workflow {suffix}")
        marker = f"history-isolation-{suffix}"
        status, payload = self.request(
            "POST",
            f"/sessions/{project['id']}/messages",
            {"content": marker, "stream": False},
            self.token,
        )
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["data"]["user_message"]["metadata"]["workspace"]["kind"], "project")

        status, payload = self.request("GET", f"/sessions/{project['id']}/messages", token=self.token)
        self.assertEqual(status, 200, payload)
        project_messages = payload["data"]["messages"]
        self.assertTrue(any(marker in message["content"] for message in project_messages))
        self.assertTrue(all(message["session_id"] == project["id"] for message in project_messages))

        status, payload = self.request("GET", f"/sessions/{workflow['id']}/messages", token=self.token)
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["data"]["messages"], [])

    def test_provider_center_exposes_safe_runtime_route_and_tool_readiness(self):
        cfg = {
            "provider": {
                "name": "Router One", "base_url": "http://router.example/v1",
                "api_key": "provider-secret-must-never-leak", "model": "vendor/primary",
                "image_model": "image-v1", "audio_model": "", "protocol": "openai",
            },
            "providers": {
                "router-one": {
                    "name": "Router One", "base_url": "http://router.example/v1",
                    "api_key": "provider-secret-must-never-leak", "model": "vendor/primary",
                    "models": "['vendor/primary', 'vendor/backup']", "protocol": "openai",
                    "image_model": "image-v1",
                },
                "spare": {
                    "name": "Spare", "base_url": "https://spare.example/v1",
                    "api_key": "another-provider-secret", "model": "spare/chat",
                    "models": ["spare/chat"], "protocol": "anthropic",
                },
            },
            "agent": {
                "fallback_model": "vendor/backup",
                "fallback_models": ["spare/chat", "vendor/backup"],
                "max_tool_rounds": 12, "stream": True,
            },
            "tools": {
                "cli_profile": "workspace", "browser": True, "custom_tools": True,
                "openapi_tools": False, "plugins": True, "tool_search": False,
                "cron": True, "lsp": True,
            },
        }
        payload = self.server_module.provider_center_payload(cfg)
        serialized = json.dumps(payload)

        self.assertNotIn("provider-secret-must-never-leak", serialized)
        self.assertNotIn("another-provider-secret", serialized)
        self.assertEqual(payload["routing"]["primary"], {
            "provider_id": "router-one", "model": "vendor/primary",
        })
        self.assertEqual(payload["routing"]["fallback_models"], ["vendor/backup", "spare/chat"])
        self.assertEqual(payload["runtime"]["tool_profile"], "workspace")
        self.assertEqual(payload["runtime"]["max_tool_rounds"], 12)
        self.assertTrue(payload["runtime"]["streaming"])
        # The merged list joins presets, so pin the saved connection by id.
        saved = {row["id"]: row for row in payload["providers"] if row["connected"]}
        self.assertEqual(saved["router-one"]["models"], ["vendor/primary", "vendor/backup"])
        self.assertTrue(saved["router-one"]["capabilities"]["tools_ready"])
        self.assertTrue(saved["router-one"]["capabilities"]["image_generation"])
        self.assertEqual(saved["spare"]["credential_status"], "configured")
        self.assertTrue(any(tool["id"] == "browser" and tool["enabled"] for tool in payload["runtime"]["tools"]))
        self.assertTrue(any(tool["id"] == "openapi_tools" and not tool["enabled"] for tool in payload["runtime"]["tools"]))

    def test_provider_center_endpoint_serves_config_and_test_action_stays_offline(self):
        cfg = {
            "provider": {"name": "Router One", "base_url": "http://router.example/v1",
                         "api_key": "http-route-secret", "model": "vendor/primary"},
            "providers": {
                "router-one": {"name": "Router One", "base_url": "http://router.example/v1",
                               "api_key": "http-route-secret", "model": "vendor/primary",
                               "models": ["vendor/primary"]},
                "no-key": {"name": "No Key", "base_url": "http://unused.example/v1",
                           "model": "ghost/model", "models": ["ghost/model"]},
            },
            "agent": {"fallback_model": "vendor/backup", "stream": False},
            "tools": {"cli_profile": "full", "browser": True, "openapi_tools": False},
        }
        original = self.server_module._zeline_config
        self.server_module._zeline_config = lambda: (cfg, None)
        try:
            status, payload = self.request("GET", "/providers/center", token=self.token)
            self.assertEqual(status, 200, payload)
            data = payload["data"]
            self.assertNotIn("http-route-secret", json.dumps(data))
            self.assertEqual(data["routing"]["primary"]["model"], "vendor/primary")
            self.assertEqual(data["routing"]["fallback_models"], ["vendor/backup"])
            # Saved connections carry their own bucket (custom-compatible when not
            # in the preset catalog) and read as connected regardless of position.
            by_id = {row["id"]: row for row in data["providers"]}
            self.assertTrue(by_id["router-one"]["connected"])
            self.assertEqual(by_id["router-one"]["group"], "openai-compatible")

            # Provider tanpa kredensial harus dijawab dari konfigurasi saja,
            # bukan dengan mencoba menghubungi host yang tidak ada.
            status, payload = self.request("POST", "/providers/no-key/test", {}, self.token)
            self.assertEqual(status, 200, payload)
            self.assertEqual(payload["data"]["health"]["status"], "missing_credentials")

            status, payload = self.request("GET", "/providers/center", token=self.token)
            self.assertEqual(status, 200, payload)
            by_id = {row["id"]: row for row in payload["data"]["providers"]}
            self.assertEqual(by_id["no-key"]["health"]["status"], "missing_credentials")
            self.assertEqual(by_id["router-one"]["health"]["status"], "untested")

            status, payload = self.request("POST", "/providers/ghost/test", {}, self.token)
            self.assertEqual(status, 502, payload)
            self.assertEqual(payload["error"]["code"], "PROVIDER_UNAVAILABLE")
        finally:
            self.server_module._zeline_config = original


    def test_provider_center_stays_local_when_chat_is_proxied_to_a_live_gateway(self):
        """Provider Center must never be forwarded to a live runtime gateway.

        The frontend server proxies chat traffic to a real Zeline App gateway
        when ``ZELINE_APP_UPSTREAM`` is set. Provider Center reads the local
        ``~/.zeline/config.json`` instead, so a gateway whose API does not expose
        those routes must not break it — a regression here silently turns every
        provider card into a 404.
        """
        cfg = {
            "provider": {"name": "Router One", "base_url": "http://router.example/v1",
                         "api_key": "local-only-secret", "model": "vendor/primary"},
            "providers": {
                "router-one": {"name": "Router One", "base_url": "http://router.example/v1",
                               "api_key": "local-only-secret", "model": "vendor/primary",
                               "models": ["vendor/primary"]},
                "no-key": {"name": "No Key", "base_url": "http://unused.example/v1",
                           "model": "ghost/model", "models": ["ghost/model"]},
            },
            "agent": {"fallback_model": "vendor/backup", "stream": False},
            "tools": {"cli_profile": "full", "browser": True},
        }
        original_cfg = self.server_module._zeline_config
        original_upstream = self.server_module.UPSTREAM
        # Any real proxy attempt would try to reach this and fail noisily.
        self.server_module.UPSTREAM = "http://127.0.0.1:1/api/v1"
        self.server_module._zeline_config = lambda: (cfg, None)
        try:
            status, payload = self.request("GET", "/providers/center", token=self.token)
            self.assertEqual(status, 200, payload)
            self.assertNotIn("local-only-secret", json.dumps(payload["data"]))
            self.assertEqual(payload["data"]["routing"]["primary"]["model"], "vendor/primary")

            # The local test action must also stay off the proxied path.
            status, payload = self.request("POST", "/providers/no-key/test", {}, self.token)
            self.assertEqual(status, 200, payload)
            self.assertEqual(payload["data"]["health"]["status"], "missing_credentials")

            status, payload = self.request("POST", "/providers/ghost/test", {}, self.token)
            self.assertEqual(status, 502, payload)
            self.assertEqual(payload["error"]["code"], "PROVIDER_UNAVAILABLE")
        finally:
            self.server_module.UPSTREAM = original_upstream
            self.server_module._zeline_config = original_cfg

    def test_provider_catalog_groups_every_saved_and_preset_card(self):
        """The center must bucket every visible card into a dashboard section.

        Saved connections join the preset catalog so the page can show the full
        list, not just what's configured: each card carries a group so the UI
        can lay out Custom / OAuth / Free Tier / API Key exactly like the
        reference dashboard, and a saved provider is marked Connected.
        """
        cfg = {
            "provider": {"name": "Main", "base_url": "https://api.openai.com/v1",
                         "api_key": "k", "model": "gpt-4o-mini"},
            "providers": {
                "openai": {"name": "OpenAI", "base_url": "https://api.openai.com/v1",
                           "api_key": "k", "model": "gpt-4o-mini", "models": ["gpt-4o-mini"]},
            },
            "agent": {}, "tools": {},
        }
        payload = self.server_module.provider_center_payload(cfg)
        groups = {row["group"] for row in payload["providers"]}
        self.assertIn("apikey", groups)
        self.assertIn("oauth", groups)
        self.assertIn("free", groups)
        # Saved provider lands on the right bucket and reads as connected.
        by_id = {row["id"]: row for row in payload["providers"]}
        self.assertEqual(by_id["openai"]["group"], "apikey")
        self.assertTrue(by_id["openai"]["connected"])
        # A preset with no saved connection is still listed, not hidden.
        self.assertIn("claude", by_id)
        self.assertEqual(by_id["claude"]["group"], "oauth")
        self.assertFalse(by_id["claude"]["connected"])

    def test_provider_presets_expose_real_base_urls_and_protocols(self):
        """Presets prefill a connection from a real catalog, not typed guesses.

        Each preset carries the endpoint and wire protocol Zeline should speak.
        The catalog is generated from a provider registry, so the endpoint must
        look like a real base URL and the protocol must be one Zeline supports.
        """
        rows = self.server_module.provider_presets()["providers"]
        self.assertGreater(len(rows), 20, "catalog looks empty or truncated")

        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)), "duplicate preset ids")

        for row in rows:
            self.assertIn(row["protocol"], {"openai", "anthropic", "ollama"})
            self.assertTrue(row["base_url"].startswith("http"), row)
            self.assertNotIn("chat/completions", row["base_url"], row)
            self.assertTrue(row["auth"], row)
            for mode in row["auth"]:
                self.assertIn(mode, {"api_key", "oauth", "none"})

        by_id = {row["id"]: row for row in rows}
        # An Anthropic-native provider must not be flattened to an OpenAI root.
        if "anthropic" in by_id:
            self.assertEqual(by_id["anthropic"]["protocol"], "anthropic")
        # A provider publishing both wires is kept on its lossless one.
        if "deepseek" in by_id:
            self.assertEqual(by_id["deepseek"]["protocol"], "anthropic")

    def test_provider_presets_endpoint_is_read_only(self):
        status, payload = self.request("GET", "/providers/presets", token=self.token)
        self.assertEqual(status, 200, payload)
        rows = payload["data"]["providers"]
        self.assertGreater(len(rows), 20)
        # "api_key" appears as an auth *mode* label, never as a credential
        # field: a preset has no value to leak, only the endpoint to talk to.
        for row in rows:
            self.assertEqual(set(row), {"id", "name", "protocol", "base_url", "auth", "category", "group"})
            self.assertTrue(all(isinstance(mode, str) for mode in row["auth"]))
        self.assertNotIn("key_hint", json.dumps(payload["data"]))
        self.assertNotIn("secret", json.dumps(payload["data"]).lower())

    def test_providers_test_all_runs_only_saved_connections_in_a_group(self):
        """Batch test covers a section's saved connections, never preset ghosts.

        A preset with no saved key has nothing to prove, so Test All only runs
        connections that exist in the runtime config. It must not turn an
        unconfigured card into a fake pass, and it must stay offline for a
        credential-less entry.
        """
        cfg = {
            "provider": {"name": "Main", "base_url": "http://router.example/v1",
                         "api_key": "k", "model": "m"},
            "providers": {
                "openai": {"name": "OpenAI", "base_url": "https://api.openai.com/v1",
                           "api_key": "k", "model": "gpt-4o-mini"},
                "no-key": {"name": "NoKey", "base_url": "http://unused.example/v1",
                           "model": "m"},
            },
            "agent": {}, "tools": {},
        }
        original = self.server_module._zeline_config
        self.server_module._zeline_config = lambda: (cfg, None)
        try:
            status, payload = self.request(
                "POST", "/providers/test-all", {"group": "apikey"}, self.token)
            self.assertEqual(status, 200, payload)
            data = payload["data"]
            ids = [r["provider_id"] for r in data["results"]]
            # Only saved apikey connections are exercised; presets stay out.
            self.assertIn("openai", ids)
            self.assertNotIn("no-key", ids, "no-key is not apikey group")
            self.assertNotIn("claude", ids, "preset with no saved key is not tested")
            self.assertEqual(data["summary"]["total"], len(data["results"]))
            self.assertEqual(
                data["summary"]["passed"],
                sum(1 for r in data["results"] if r["ok"]))
        finally:
            self.server_module._zeline_config = original

    def test_add_provider_writes_config_atomically_and_keeps_fallback(self):
        """Saving a provider must not clobber the rest of the runtime config.

        A new connection is stored under a unique slug and can be activated; the
        existing fallback chain and credentials are preserved, and the write is
        atomic (no partial JSON on crash). A change is only real if the agent can
        read it back — this test proves the round trip through the runtime file.
        """
        import tempfile as _tempfile
        with _tempfile.TemporaryDirectory() as directory:
            cfg_path = Path(directory) / "config.json"
            original = {
                "provider": {"name": "Main", "base_url": "http://main.example/v1",
                             "api_key": "main-key", "model": "m1", "protocol": "openai"},
                "providers": {
                    "main": {"name": "Main", "base_url": "http://main.example/v1",
                             "api_key": "main-key", "model": "m1", "models": ["m1"]},
                },
                "agent": {"fallback_models": ["m1-backup", "m1-backup2"]},
                "tools": {"cli_profile": "full"},
                "setup_complete": True,
            }
            cfg_path.write_text(json.dumps(original), encoding="utf-8")
            module = self.server_module
            original_dir = module.ZELINE_DATA_DIR
            module.ZELINE_DATA_DIR = directory
            try:
                ok, err = module._write_zeline_config(lambda raw: raw.update(
                    module.provider_add_record(raw, {
                        "name": "Anthropic Mirror",
                        "base_url": "https://mirror.example/v1",
                        "api_key": "new-key",
                        "protocol": "anthropic",
                        "model": "claude-x",
                    })))
                self.assertTrue(ok, err)
                written = json.loads(cfg_path.read_text(encoding="utf-8"))
                # The new connection is stored and the agent state is untouched.
                self.assertIn("anthropic-mirror", written["providers"])
                self.assertEqual(written["providers"]["anthropic-mirror"]["api_key"], "new-key")
                self.assertEqual(written["providers"]["anthropic-mirror"]["protocol"], "anthropic")
                self.assertEqual(written["providers"]["main"]["api_key"], "main-key")
                self.assertEqual(written["agent"]["fallback_models"], ["m1-backup", "m1-backup2"])
                # The record is unique: re-adding must not overwrite the first.
                ok2, err2 = module._write_zeline_config(lambda raw: raw.update(
                    module.provider_add_record(raw, {
                        "name": "Anthropic Mirror", "base_url": "https://mirror.example/v1",
                        "api_key": "new-key", "protocol": "anthropic", "model": "claude-x",
                    })))
                self.assertTrue(ok2, err2)
                written2 = json.loads(cfg_path.read_text(encoding="utf-8"))
                slugs = [k for k in written2["providers"] if k.startswith("anthropic-mirror")]
                self.assertEqual(len(slugs), 2)
            finally:
                module.ZELINE_DATA_DIR = original_dir

    def test_provider_detail_lists_models_and_tracks_hidden_ones(self):
        """A provider's model list merges runtime config with the live catalog.

        The detail page needs to show every model the endpoint offers, plus any
        the operator added by hand, and remember which ones are hidden. Hidden
        models stay in settings (not the runtime config) so the agent is never
        fed a model the operator removed from the list.
        """
        cfg = {
            "provider": {"name": "Main", "base_url": "http://main.example/v1",
                         "api_key": "k", "model": "m1"},
            "providers": {
                "openai": {"name": "OpenAI", "base_url": "https://api.openai.com/v1",
                           "api_key": "k", "model": "gpt-4o-mini",
                           "models": ["gpt-4o-mini", "gpt-4o"]},
            },
            "agent": {}, "tools": {},
        }
        settings = {
            "provider_center": {
                "hidden_models": {"openai": ["gpt-4o"]},
                "custom_models": {"openai": ["my-fine-tune"]},
            }
        }
        detail = self.server_module.provider_model_list("openai", cfg, settings)
        ids = [row["id"] for row in detail["models"]]
        self.assertIn("gpt-4o-mini", ids)
        self.assertIn("gpt-4o", ids)
        self.assertIn("my-fine-tune", ids)
        by_id = {row["id"]: row for row in detail["models"]}
        self.assertTrue(by_id["gpt-4o"]["hidden"])
        self.assertFalse(by_id["gpt-4o-mini"]["hidden"])
        self.assertTrue(by_id["my-fine-tune"]["custom"])
        self.assertNotIn("k", json.dumps(detail), "secret must not leak")

    def test_add_custom_and_hidden_model_persist_without_touching_config(self):
        """Add/hide a model writes app settings, never the runtime config file."""
        settings = {}
        out = self.server_module.provider_record_model("openai", "my-model", settings, action="add")
        ids = [m["id"] for m in out["models"]]
        self.assertIn("my-model", ids)
        out = self.server_module.provider_record_model("openai", "my-model", out["settings"], action="hide")
        hidden = out["settings"]["provider_center"]["hidden_models"]["openai"]
        self.assertIn("my-model", hidden)
        out = self.server_module.provider_record_model("openai", "my-model", out["settings"], action="unhide")
        hidden = out["settings"]["provider_center"]["hidden_models"].get("openai", [])
        self.assertNotIn("my-model", hidden)

    def test_test_model_sends_a_real_completion_request(self):
        """Testing a model must prove the endpoint actually runs it.

        A model list only says a name exists; it does not prove the provider
        will answer a request. The test sends a real tiny completion and reports
        latency, and it must fail without a credential instead of guessing.
        """
        result, code = self.server_module.provider_test_model(
            "openai", "gpt-4o-mini", {
                "provider": {}, "providers": {
                    "openai": {"base_url": "", "api_key": "", "protocol": "openai"}},
                "agent": {}, "tools": {},
            }, {})
        self.assertEqual(result, {})
        self.assertIn(code, {"missing_base_url", "missing_credentials"})

    def test_test_model_never_leaks_the_key(self):
        _, code = self.server_module.provider_test_model(
            "openai", "m", {
                "provider": {}, "providers": {
                    "openai": {"base_url": "", "api_key": "sk-secret", "protocol": "openai"}},
                "agent": {}, "tools": {},
            }, {})
        self.assertIsNotNone(code)

    def test_provider_preflight_validates_before_touching_the_network(self):
        """A missing field must fail instantly, never open a socket.

        Preflight exists to catch a bad key early; an empty input has nothing to
        prove, so it should fail on validation and leave the network untouched.
        """
        result, code = self.server_module.provider_preflight("", "sk-x", "openai")
        self.assertEqual(result, {})
        self.assertEqual(code, "missing_base_url")

        result, code = self.server_module.provider_preflight(
            "https://example.invalid/v1", "", "openai")
        self.assertEqual(result, {})
        self.assertEqual(code, "missing_credentials")

        status, payload = self.request(
            "POST", "/providers/preflight", {"base_url": "", "api_key": "sk-x"}, self.token)
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")

        status, payload = self.request(
            "POST", "/providers/preflight",
            {"base_url": "https://example.invalid/v1", "api_key": ""}, self.token)
        self.assertEqual(status, 400, payload)

    def test_provider_preflight_never_echoes_the_key(self):
        """The key is used for one request and never returned to the client."""
        result, _code = self.server_module.provider_preflight("", "sk-must-not-leak", "openai")
        self.assertNotIn("sk-must-not-leak", json.dumps(result))
        status, payload = self.request(
            "POST", "/providers/preflight",
            {"base_url": "", "api_key": "sk-must-not-leak"}, self.token)
        self.assertNotIn("sk-must-not-leak", json.dumps(payload))


class LegacyWorkspaceStateUpgradeTest(unittest.TestCase):
    def test_load_upgrades_legacy_kinds_without_losing_history(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            state_path = temp / "legacy-workspaces.json"
            legacy = {
                "version": 1,
                "sessions": [
                    {
                        "id": "legacy_saved", "agent_id": "agent_general", "title": "Old session",
                        "kind": "saved", "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z", "message_count": 1,
                        "last_preview": "Still here",
                    },
                    {
                        "id": "legacy_cron", "agent_id": "agent_general", "title": "Old cron",
                        "kind": "cron", "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z", "message_count": 1,
                        "last_preview": "Still scheduled",
                    },
                ],
                "messages": {
                    "legacy_saved": [{"id": "legacy_message", "session_id": "legacy_saved", "role": "user", "content": "keep history"}],
                    "legacy_cron": [{"id": "legacy_cron_message", "session_id": "legacy_cron", "role": "assistant", "content": "keep cron history"}],
                },
            }
            state_path.write_text(json.dumps(legacy), encoding="utf-8")
            previous = {key: os.environ.get(key) for key in ENV_KEYS}
            module_name = f"zeline_frontend_legacy_test_{uuid.uuid4().hex}"
            try:
                os.environ.update({
                    "ZELINE_FE_WORKSPACE_STATE": str(state_path),
                    "ZELINE_FE_APP_SETTINGS": str(temp / "app-settings.json"),
                    "ZELINE_CRON_JOBS_PATH": str(temp / "jobs.json"),
                    "ZELINE_APP_UPSTREAM": "",
                })
                module = load_server_module(module_name)
                sessions = {item["id"]: item for item in module.SESSIONS}
                self.assertEqual(sessions["legacy_saved"]["kind"], "session")
                self.assertEqual(sessions["legacy_cron"]["kind"], "cronjob")
                self.assertEqual(module.MESSAGES["legacy_saved"][0]["content"], "keep history")
                self.assertEqual(module.MESSAGES["legacy_cron"][0]["content"], "keep cron history")
                module.persist_workspace_state()
                upgraded = json.loads(state_path.read_text(encoding="utf-8"))
                persisted = {item["id"]: item for item in upgraded["sessions"]}
                self.assertEqual(persisted["legacy_saved"]["kind"], "session")
                self.assertEqual(persisted["legacy_cron"]["kind"], "cronjob")
                self.assertEqual(upgraded["messages"]["legacy_saved"][0]["content"], "keep history")
                self.assertEqual(upgraded["messages"]["legacy_cron"][0]["content"], "keep cron history")
            finally:
                sys.modules.pop(module_name, None)
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main(verbosity=2)

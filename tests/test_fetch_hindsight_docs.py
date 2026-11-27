"""Deterministic tests for bot/scripts/fetch_hindsight_docs.py.

Uses temporary directories, a fake curl executable, and a local loopback HTTP
fixture server -- zero live network calls, zero touches to real ~/.hindsight/
or ~/.orca/.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
FETCH_SCRIPT = REPO_ROOT / "bot" / "scripts" / "fetch_hindsight_docs.py"


def _make_jsonl(turns: list[dict]) -> str:
    return "\n".join(json.dumps(turn, ensure_ascii=False) for turn in turns)


def _clean_env(home_dir: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home_dir),
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }
    if extra:
        env.update(extra)
    return env


def _write_fake_curl(
    directory: Path,
    routes: dict[str, tuple[int, str]],
    *,
    log_file: Path | None = None,
    require_bearer: str | None = None,
) -> Path:
    """Create a deterministic fake curl script serving fixture routes."""
    script = directory / "fake-curl"
    routes_file = directory / "fake-curl-routes.json"
    routes_file.write_text(json.dumps(routes), encoding="utf-8")

    body = f"""#!{sys.executable}
import json, pathlib, sys
from urllib.parse import urlparse

args = sys.argv[1:]
stdin_data = ""
if "-K" in args:
    stdin_data = sys.stdin.read()

url = args[-1]
parsed = urlparse(url)
path_q = parsed.path + (("?" + parsed.query) if parsed.query else "")

log_path = {str(log_file)!r}
if log_path != "None":
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({{"args": args, "stdin": stdin_data, "path_q": path_q}}) + "\\n")

required = {require_bearer!r}
if required is not None:
    expected_hdr = f'Authorization: Bearer {{required}}'
    if expected_hdr not in stdin_data:
        sys.stderr.write("HTTP 401 unauthorized\\n")
        raise SystemExit(22)

routes = json.loads(pathlib.Path({str(routes_file)!r}).read_text(encoding="utf-8"))
entry = routes.get(path_q)
if entry is None:
    entry = routes.get(parsed.path)
if entry is None:
    sys.stderr.write(f"HTTP 404 not found: {{path_q}}\\n")
    raise SystemExit(22)

code, payload = entry
if code != 0:
    sys.stderr.write(payload)
    raise SystemExit(code)
sys.stdout.write(payload)
"""
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


class TestFetchHindsightDocs(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.home_dir = self.tmp_path / "home"
        self.home_dir.mkdir(parents=True)
        self.cfg_path = self.home_dir / ".hindsight" / "coding-agent.json"
        self.cfg_path.parent.mkdir(parents=True)
        self.cfg_path.write_text(
            json.dumps(
                {
                    "apiUrl": "http://mock-hindsight.local:50002",
                    "apiToken": "secret-token-xyz",
                }
            ),
            encoding="utf-8",
        )
        self.state_file = self.tmp_path / "state" / "hindsight-watermark.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(
        self, args: list[str], extra_env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        cmd = [sys.executable, str(FETCH_SCRIPT), *args]
        return subprocess.run(
            cmd,
            env=_clean_env(self.home_dir, extra_env),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_precheck_detects_new_and_equal_timestamp_unseen_id(self) -> None:
        routes = {
            "/v1/default/banks?limit=200&offset=0": (
                0,
                json.dumps(
                    {
                        "banks": [
                            {
                                "bank_id": "coding-agent::alpha",
                                "last_document_at": "2026-11-26T00:00:00+00:00",
                            },
                            {"bank_id": "personal-non-coding"},
                        ],
                        "total": 2,
                        "limit": 200,
                        "offset": 0,
                    }
                ),
            ),
            "/v1/default/banks/coding-agent%3A%3Aalpha/documents?limit=50&offset=0": (
                0,
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "gitlog:alpha",
                                "updated_at": "2026-11-27T12:00:00+00:00",
                            },
                            {
                                "id": "conversation:c2",
                                "updated_at": "2026-11-27T10:00:00+00:00",
                            },
                            {
                                "id": "conversation:c1",
                                "updated_at": "2026-11-27T10:00:00+00:00",
                            },
                        ],
                        "total": 3,
                        "limit": 50,
                        "offset": 0,
                    }
                ),
            ),
        }
        log_file = self.tmp_path / "curl.log"
        fake_curl = _write_fake_curl(
            self.tmp_path,
            routes,
            log_file=log_file,
            require_bearer="secret-token-xyz",
        )

        # Even though last_document_at on bank summary is older than watermark,
        # precheck still checks /documents and catches c2 (unseen at equal timestamp).
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "banks": {
                        "coding-agent::alpha": {
                            "last_updated_at": "2026-11-27T10:00:00+00:00",
                            "seen_ids_at_watermark": ["conversation:c1"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        res = self._run(
            [
                "--precheck",
                "--state-file",
                str(self.state_file),
                "--curl-bin",
                str(fake_curl),
            ]
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("conversation:c2", res.stdout)

        # Verify token was passed via stdin (-K -), NOT exposed in argv.
        calls = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").splitlines()
        ]
        self.assertGreaterEqual(len(calls), 2)
        for call in calls:
            self.assertNotIn("secret-token-xyz", " ".join(call["args"]))
            self.assertIn("Authorization: Bearer secret-token-xyz", call["stdin"])

        # Now mark both c1 and c2 seen at equal timestamp -> precheck must exit 1
        # (ignoring newer gitlog:alpha because it is not conversation:*).
        self.state_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "banks": {
                        "coding-agent::alpha": {
                            "last_updated_at": "2026-11-27T10:00:00+00:00",
                            "seen_ids_at_watermark": [
                                "conversation:c1",
                                "conversation:c2",
                            ],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        res_none = self._run(
            [
                "--precheck",
                "--state-file",
                str(self.state_file),
                "--curl-bin",
                str(fake_curl),
            ]
        )
        self.assertEqual(res_none.returncode, 1, res_none.stderr)
        self.assertIn("no new conversation docs", res_none.stdout)

    def test_fetch_extracts_reflections_bounds_chars_and_does_not_advance(self) -> None:
        long_turn = "A" * 500
        doc1_text = _make_jsonl(
            [
                {
                    "role": "system",
                    "content": "REF-ID: conversation:s1",
                    "timestamp": "2026-11-27T01:00:00Z",
                },
                {
                    "role": "user",
                    "content": "Investigate proxy 429.",
                    "timestamp": "2026-11-27T01:00:01Z",
                },
                {
                    "role": "action",
                    "content": "Bash curl -sS http://127.0.0.1:8045/v1/messages",
                    "timestamp": "2026-11-27T01:00:02Z",
                },
                {
                    "role": "assistant",
                    "content": (
                        "Replay reproduced 429.\n"
                        "<ears_reflection>Byte-exact replay plus binary search "
                        "isolates WAF fingerprints from token volume.</ears_reflection>"
                    ),
                    "timestamp": "2026-11-27T01:00:05Z",
                },
                {
                    "role": "assistant",
                    "content": long_turn,
                    "timestamp": "2026-11-27T01:00:06Z",
                },
            ]
        )
        doc2_text = _make_jsonl(
            [
                {
                    "role": "user",
                    "content": "Second newer session.",
                    "timestamp": "2026-11-27T02:00:00Z",
                }
            ]
        )
        routes = {
            "/v1/default/banks?limit=200&offset=0": (
                0,
                json.dumps(
                    {
                        "banks": [
                            {"bank_id": "coding-agent::.dotfiles"},
                            {"bank_id": "coding-agent::personal"},
                        ],
                        "total": 2,
                    }
                ),
            ),
            "/v1/default/banks/coding-agent%3A%3A.dotfiles/documents?limit=50&offset=0": (
                0,
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "conversation:s2",
                                "updated_at": "2026-11-27T02:00:00+00:00",
                            },
                            {
                                "id": "conversation:s1",
                                "updated_at": "2026-11-27T01:00:00+00:00",
                            },
                        ],
                        "total": 2,
                    }
                ),
            ),
            "/v1/default/banks/coding-agent%3A%3A.dotfiles/documents/conversation%3As1": (
                0,
                json.dumps(
                    {
                        "id": "conversation:s1",
                        "bank_id": "coding-agent::.dotfiles",
                        "updated_at": "2026-11-27T01:00:00+00:00",
                        "original_text": doc1_text,
                        "tags": ["source:chat"],
                    }
                ),
            ),
            "/v1/default/banks/coding-agent%3A%3A.dotfiles/documents/conversation%3As2": (
                0,
                json.dumps(
                    {
                        "id": "conversation:s2",
                        "bank_id": "coding-agent::.dotfiles",
                        "updated_at": "2026-11-27T02:00:00+00:00",
                        "original_text": doc2_text,
                        "tags": ["source:chat"],
                    }
                ),
            ),
        }
        fake_curl = _write_fake_curl(self.tmp_path, routes)
        pending_file = self.tmp_path / "pending.json"
        out_file = self.tmp_path / "bundle.json"

        # Cap to 1 doc per run -> must pick oldest unseen (s1) first so s2 stays queued.
        res = self._run(
            [
                "--fetch",
                "--state-file",
                str(self.state_file),
                "--pending-file",
                str(pending_file),
                "--output",
                str(out_file),
                "--exclude-banks",
                "coding-agent::personal",
                "--max-docs-per-run",
                "1",
                "--max-chars-per-doc",
                "300",
                "--curl-bin",
                str(fake_curl),
            ]
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(
            self.state_file.exists(), "--fetch must never write --state-file"
        )
        self.assertTrue(pending_file.is_file())

        bundle = json.loads(out_file.read_text(encoding="utf-8"))
        self.assertEqual(bundle["banks_scanned"], 1)
        self.assertEqual(bundle["doc_count"], 1)
        self.assertEqual(bundle["remaining_docs_capped"], 1)

        doc = bundle["documents"][0]
        self.assertEqual(doc["doc_id"], "conversation:s1")
        self.assertEqual(doc["source_repo"], "dotfiles")
        self.assertEqual(doc["reflection_count"], 1)
        self.assertIn("Byte-exact replay", doc["reflections"][0]["text"])
        self.assertTrue(doc["truncated"])
        self.assertLessEqual(doc["char_count"], 300)

        # Advance using pending_file -> watermark moves to s1 only, so s2 is still new.
        adv1 = self._run(
            [
                "--advance",
                "--state-file",
                str(self.state_file),
                "--pending-file",
                str(pending_file),
            ]
        )
        self.assertEqual(adv1.returncode, 0, adv1.stderr)
        wm1 = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            wm1["banks"]["coding-agent::.dotfiles"]["last_updated_at"],
            "2026-11-27T01:00:00+00:00",
        )
        self.assertEqual(
            wm1["banks"]["coding-agent::.dotfiles"]["seen_ids_at_watermark"],
            ["conversation:s1"],
        )

        # Next precheck still exits 0 because s2 was not yet fetched!
        pre2 = self._run(
            [
                "--precheck",
                "--state-file",
                str(self.state_file),
                "--exclude-banks",
                "coding-agent::personal",
                "--curl-bin",
                str(fake_curl),
            ]
        )
        self.assertEqual(pre2.returncode, 0, pre2.stderr)
        self.assertIn("conversation:s2", pre2.stdout)

        # Fetch markdown format for s2, then advance -> precheck exits 1.
        pending_file2 = self.tmp_path / "pending2.json"
        md_res = self._run(
            [
                "--fetch",
                "--format",
                "markdown",
                "--state-file",
                str(self.state_file),
                "--pending-file",
                str(pending_file2),
                "--exclude-banks",
                "coding-agent::personal",
                "--curl-bin",
                str(fake_curl),
            ]
        )
        self.assertEqual(md_res.returncode, 0, md_res.stderr)
        self.assertIn("conversation:s2", md_res.stdout)
        self.assertNotIn("conversation:s1", md_res.stdout)

        adv2 = self._run(
            [
                "--advance",
                "--state-file",
                str(self.state_file),
                "--pending-file",
                str(pending_file2),
            ]
        )
        self.assertEqual(adv2.returncode, 0, adv2.stderr)

        pre3 = self._run(
            [
                "--precheck",
                "--state-file",
                str(self.state_file),
                "--exclude-banks",
                "coding-agent::personal",
                "--curl-bin",
                str(fake_curl),
            ]
        )
        self.assertEqual(pre3.returncode, 1, pre3.stderr)

        # Re-applying stale pending_file (s1) must NOT move watermark backwards!
        adv_stale = self._run(
            [
                "--advance",
                "--state-file",
                str(self.state_file),
                "--pending-file",
                str(pending_file),
            ]
        )
        self.assertEqual(adv_stale.returncode, 0, adv_stale.stderr)
        wm_final = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            wm_final["banks"]["coding-agent::.dotfiles"]["last_updated_at"],
            "2026-11-27T02:00:00+00:00",
        )
        self.assertEqual(
            wm_final["banks"]["coding-agent::.dotfiles"]["seen_ids_at_watermark"],
            ["conversation:s2"],
        )

    def test_operational_errors_exit_2_and_redact_token(self) -> None:
        routes = {
            "/v1/default/banks?limit=200&offset=0": (
                22,
                "curl: (22) failed with token secret-token-xyz on upstream\n",
            )
        }
        fake_curl = _write_fake_curl(self.tmp_path, routes)
        res = self._run(
            [
                "--precheck",
                "--state-file",
                str(self.state_file),
                "--curl-bin",
                str(fake_curl),
            ]
        )
        self.assertEqual(res.returncode, 2)
        self.assertNotIn("secret-token-xyz", res.stderr)
        self.assertIn("<redacted>", res.stderr)

        # Missing config file -> exit 2
        missing_cfg = self.tmp_path / "does-not-exist.json"
        res_missing = self._run(
            [
                "--precheck",
                "--config",
                str(missing_cfg),
                "--state-file",
                str(self.state_file),
            ]
        )
        self.assertEqual(res_missing.returncode, 2)

    def test_pagination_explicit_banks_no_token_and_equal_ts_union(self) -> None:
        # Remove apiToken from config to verify optional token path (no -K -).
        self.cfg_path.write_text(
            json.dumps({"apiUrl": "http://mock-hindsight.local:50002"}),
            encoding="utf-8",
        )
        routes = {
            "/v1/default/banks/coding-agent%3A%3Abeta/documents?limit=2&offset=0": (
                0,
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "conversation:b3",
                                "updated_at": "2026-11-27T04:00:00+00:00",
                            },
                            {
                                "id": "conversation:b2",
                                "updated_at": "2026-11-27T04:00:00+00:00",
                            },
                        ],
                        "total": 3,
                    }
                ),
            ),
            "/v1/default/banks/coding-agent%3A%3Abeta/documents?limit=2&offset=2": (
                0,
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "conversation:b1",
                                "updated_at": "2026-11-27T03:00:00+00:00",
                            }
                        ],
                        "total": 3,
                    }
                ),
            ),
            "/v1/default/banks/coding-agent%3A%3Abeta/documents/conversation%3Ab2": (
                0,
                json.dumps(
                    {
                        "id": "conversation:b2",
                        "bank_id": "coding-agent::beta",
                        "updated_at": "2026-11-27T04:00:00+00:00",
                        "original_text": "Plain text fallback <ears_reflection>Check fallback parsing.</ears_reflection>",
                    }
                ),
            ),
            "/v1/default/banks/coding-agent%3A%3Abeta/documents/conversation%3Ab3": (
                0,
                json.dumps(
                    {
                        "id": "conversation:b3",
                        "bank_id": "coding-agent::beta",
                        "updated_at": "2026-11-27T04:00:00+00:00",
                        "original_text": _make_jsonl(
                            [{"role": "assistant", "content": "ok"}]
                        ),
                    }
                ),
            ),
        }
        log_file = self.tmp_path / "curl-notoken.log"
        fake_curl = _write_fake_curl(self.tmp_path, routes, log_file=log_file)

        # Seed existing watermark with untouched bank + beta at 04:00 seeing b2 only
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "banks": {
                        "coding-agent::untouched": {
                            "last_updated_at": "2026-11-20T00:00:00+00:00",
                            "seen_ids_at_watermark": ["conversation:u1"],
                        },
                        "coding-agent::beta": {
                            "last_updated_at": "2026-11-27T04:00:00+00:00",
                            "seen_ids_at_watermark": ["conversation:b2"],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        # Fetch explicit --banks with page-size=2 -> only b3 is new (b2 seen, b1 older)
        res = self._run(
            [
                "--fetch",
                "--banks",
                "coding-agent::beta",
                "--page-size",
                "2",
                "--state-file",
                str(self.state_file),
                "--curl-bin",
                str(fake_curl),
            ]
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        bundle = json.loads(res.stdout)
        self.assertEqual(bundle["doc_count"], 1)
        self.assertEqual(bundle["documents"][0]["doc_id"], "conversation:b3")

        # Verify curl was NOT invoked with -K when apiToken is absent
        calls = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").splitlines()
        ]
        for call in calls:
            self.assertNotIn("-K", call["args"])

        # Advance using full bundle JSON via --pending-json -> unions b2 + b3 and preserves untouched bank
        adv = self._run(
            [
                "--advance",
                "--state-file",
                str(self.state_file),
                "--pending-json",
                res.stdout,
            ]
        )
        self.assertEqual(adv.returncode, 0, adv.stderr)
        wm = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertIn("coding-agent::untouched", wm["banks"])
        self.assertEqual(
            wm["banks"]["coding-agent::beta"]["seen_ids_at_watermark"],
            ["conversation:b2", "conversation:b3"],
        )

    def test_real_curl_against_local_http_fixture_server(self) -> None:
        """Exercise real curl subprocess against a local loopback HTTP server."""
        doc_body = _make_jsonl(
            [
                {
                    "role": "assistant",
                    "content": "<ears_reflection>Use sshd -T to read effective config.</ears_reflection>",
                    "timestamp": "2026-11-27T05:00:00Z",
                }
            ]
        )

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                auth = self.headers.get("Authorization")
                if auth != "Bearer local-test-token":
                    self.send_response(401)
                    self.end_headers()
                    return
                parsed = urlparse(self.path)
                path = unquote(parsed.path)
                qs = parse_qs(parsed.query)
                if path == "/v1/default/banks":
                    payload = {
                        "banks": [{"bank_id": "coding-agent::demo"}],
                        "total": 1,
                        "limit": int(qs.get("limit", ["200"])[0]),
                        "offset": int(qs.get("offset", ["0"])[0]),
                    }
                elif path == "/v1/default/banks/coding-agent::demo/documents":
                    payload = {
                        "items": [
                            {
                                "id": "conversation:local-1",
                                "updated_at": "2026-11-27T05:00:00+00:00",
                            }
                        ],
                        "total": 1,
                    }
                elif (
                    path
                    == "/v1/default/banks/coding-agent::demo/documents/conversation:local-1"
                ):
                    payload = {
                        "id": "conversation:local-1",
                        "bank_id": "coding-agent::demo",
                        "updated_at": "2026-11-27T05:00:00+00:00",
                        "original_text": doc_body,
                    }
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            res = self._run(
                [
                    "--fetch",
                    "--api-url",
                    f"http://127.0.0.1:{port}",
                    "--api-token",
                    "local-test-token",
                    "--state-file",
                    str(self.state_file),
                ]
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            bundle = json.loads(res.stdout)
            self.assertEqual(bundle["doc_count"], 1)
            self.assertEqual(
                bundle["documents"][0]["reflections"][0]["text"],
                "Use sshd -T to read effective config.",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

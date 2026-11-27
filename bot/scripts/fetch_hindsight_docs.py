#!/usr/bin/env python3
"""Incremental Hindsight conversation document fetcher for the KB nightly bot.

Reads apiUrl (and optional apiToken) from ~/.hindsight/coding-agent.json
(overridable via CLI flags or environment variables), queries Hindsight REST
APIs via curl subprocess (avoiding urllib proxy hangs), and tracks a monotonic
per-bank watermark JSON file.

Modes:
  --precheck  Exit 0 if any active bank has a conversation:* doc newer than
              its watermark (or an unseen doc id at equal updated_at), 1 if
              nothing new, 2 on operational error. Read-only.
  --fetch     Fetch new conversation:* docs, extract <ears_reflection> blocks
              and cleaned turn content within character bounds, and emit a
              bundle plus pending_watermark WITHOUT advancing the watermark.
  --advance   Atomically and monotonically merge a pending watermark into the
              watermark state file after clean distillation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

DEFAULT_BOT_NAME = "silverbullet-kb-nightly"
DEFAULT_BANK_PREFIX = "coding-agent::"
DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_PAGES_PER_BANK = 20
DEFAULT_MAX_DOCS_PER_BANK = 10
DEFAULT_MAX_DOCS_PER_RUN = 25
DEFAULT_MAX_CHARS_PER_DOC = 16000
DEFAULT_MAX_TOTAL_CHARS = 120000
DEFAULT_TIMEOUT_SECONDS = 20
WATERMARK_VERSION = 1

REFLECTION_RE = re.compile(
    r"<ears_reflection>\s*(.*?)\s*</ears_reflection>",
    re.DOTALL | re.IGNORECASE,
)


class FetchError(RuntimeError):
    """Operational error raised on config, transport, HTTP, or state failure."""


def _default_state_file(bot_name: str) -> Path:
    return (
        Path.home()
        / ".orca"
        / "bots"
        / bot_name
        / "memory"
        / "hindsight-watermark.json"
    )


def _parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise FetchError(f"invalid ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _parse_csv_args(values: list[str] | None) -> list[str]:
    result: list[str] = []
    if not values:
        return result
    for entry in values:
        for item in entry.split(","):
            cleaned = item.strip()
            if cleaned:
                result.append(cleaned)
    return result


def load_hindsight_config(
    config_path: Path | None,
    api_url_override: str | None,
    api_token_override: str | None,
) -> tuple[str, str | None]:
    env_url = os.environ.get("HINDSIGHT_API_URL")
    env_token = os.environ.get("HINDSIGHT_API_TOKEN")
    env_cfg = os.environ.get("HINDSIGHT_CONFIG")

    resolved_cfg_path = config_path or (
        Path(env_cfg).expanduser()
        if env_cfg
        else Path.home() / ".hindsight" / "coding-agent.json"
    )

    cfg_data: dict[str, Any] = {}
    if api_url_override is None and env_url is None:
        if not resolved_cfg_path.is_file():
            raise FetchError(
                f"Hindsight config file not found: {resolved_cfg_path}"
            )
        try:
            cfg_data = json.loads(resolved_cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FetchError(
                f"failed to read Hindsight config {resolved_cfg_path}: {exc}"
            ) from exc
        if not isinstance(cfg_data, dict):
            raise FetchError(
                f"Hindsight config must be a JSON object: {resolved_cfg_path}"
            )
    elif resolved_cfg_path.is_file():
        try:
            raw = json.loads(resolved_cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg_data = raw
        except (OSError, json.JSONDecodeError):
            cfg_data = {}

    api_url = api_url_override or env_url or cfg_data.get("apiUrl")
    if not isinstance(api_url, str) or not api_url.strip():
        raise FetchError(
            "Hindsight apiUrl is missing (set in coding-agent.json, "
            "--api-url, or HINDSIGHT_API_URL)"
        )
    api_url = api_url.strip().rstrip("/")

    api_token = (
        api_token_override
        if api_token_override is not None
        else (env_token if env_token is not None else cfg_data.get("apiToken"))
    )
    if api_token is not None:
        api_token = str(api_token).strip() or None

    return api_url, api_token


def _redact_text(text: str, api_token: str | None) -> str:
    if api_token and api_token in text:
        return text.replace(api_token, "<redacted>")
    return text


def _curl_escape_header_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def curl_get_json(
    api_url: str,
    path: str,
    *,
    api_token: str | None = None,
    curl_bin: str = "curl",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    url = f"{api_url}{path}"
    connect_timeout = min(10, max(1, timeout))
    cmd = [
        curl_bin,
        "-fsS",
        "--connect-timeout",
        str(connect_timeout),
        "--max-time",
        str(timeout),
        "-H",
        "Accept: application/json",
    ]
    stdin_payload: str | None = None
    if api_token:
        # Pass Authorization header through curl's -K - stdin config so the
        # token never appears in process argv.
        escaped = _curl_escape_header_value(f"Authorization: Bearer {api_token}")
        cmd.extend(["-K", "-"])
        stdin_payload = f'header = "{escaped}"\n'
    cmd.append(url)

    try:
        proc = subprocess.run(
            cmd,
            input=stdin_payload,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise FetchError(f"failed to execute {curl_bin}: {exc}") from exc

    if proc.returncode != 0:
        err = _redact_text(proc.stderr.strip(), api_token)
        raise FetchError(
            f"curl GET {path} failed (exit {proc.returncode}): {err or 'no stderr'}"
        )

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise FetchError(f"invalid JSON from GET {path}: {exc}") from exc


def load_watermark(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return {"version": WATERMARK_VERSION, "updated_at": None, "banks": {}}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchError(
            f"failed to read watermark file {state_file}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise FetchError(f"watermark file must contain a JSON object: {state_file}")
    banks = data.get("banks", {})
    if not isinstance(banks, dict):
        raise FetchError(f"watermark 'banks' field must be an object: {state_file}")
    normalized_banks: dict[str, dict[str, Any]] = {}
    for bank_id, entry in banks.items():
        if not isinstance(entry, dict):
            raise FetchError(
                f"invalid watermark entry for bank {bank_id!r} in {state_file}"
            )
        last_ts = entry.get("last_updated_at")
        if last_ts is not None:
            _parse_timestamp(last_ts)
        seen_raw = entry.get("seen_ids_at_watermark", [])
        if not isinstance(seen_raw, list) or not all(
            isinstance(item, str) for item in seen_raw
        ):
            raise FetchError(
                f"invalid seen_ids_at_watermark for bank {bank_id!r} in {state_file}"
            )
        normalized_banks[str(bank_id)] = {
            "last_updated_at": last_ts,
            "seen_ids_at_watermark": sorted(set(seen_raw)),
        }
    return {
        "version": WATERMARK_VERSION,
        "updated_at": data.get("updated_at"),
        "banks": normalized_banks,
    }


def atomic_write_json(target: Path, payload: Any) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except OSError as exc:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise FetchError(f"failed to write {target}: {exc}") from exc


def merge_watermarks_monotonic(
    existing: dict[str, Any], pending_banks: dict[str, Any]
) -> dict[str, Any]:
    merged_banks: dict[str, dict[str, Any]] = {
        bank_id: {
            "last_updated_at": entry.get("last_updated_at"),
            "seen_ids_at_watermark": sorted(
                set(entry.get("seen_ids_at_watermark", []))
            ),
        }
        for bank_id, entry in existing.get("banks", {}).items()
    }

    for bank_id, p_entry in pending_banks.items():
        if not isinstance(p_entry, dict):
            raise FetchError(f"invalid pending watermark entry for {bank_id!r}")
        p_ts_str = p_entry.get("last_updated_at")
        p_ts = _parse_timestamp(p_ts_str)
        if p_ts is None:
            continue
        p_seen = p_entry.get("seen_ids_at_watermark", [])
        if not isinstance(p_seen, list) or not all(isinstance(x, str) for x in p_seen):
            raise FetchError(
                f"invalid pending seen_ids_at_watermark for {bank_id!r}"
            )

        cur = merged_banks.get(bank_id)
        if cur is None or cur.get("last_updated_at") is None:
            merged_banks[bank_id] = {
                "last_updated_at": p_ts_str,
                "seen_ids_at_watermark": sorted(set(p_seen)),
            }
            continue

        cur_ts = _parse_timestamp(cur["last_updated_at"])
        assert cur_ts is not None
        if p_ts > cur_ts:
            merged_banks[bank_id] = {
                "last_updated_at": p_ts_str,
                "seen_ids_at_watermark": sorted(set(p_seen)),
            }
        elif p_ts == cur_ts:
            combined_seen = sorted(set(cur["seen_ids_at_watermark"]) | set(p_seen))
            merged_banks[bank_id] = {
                "last_updated_at": cur["last_updated_at"],
                "seen_ids_at_watermark": combined_seen,
            }
        # If p_ts < cur_ts, keep existing (monotonic guard).

    return {
        "version": WATERMARK_VERSION,
        "updated_at": _utc_now_iso(),
        "banks": dict(sorted(merged_banks.items())),
    }


def list_active_banks(
    api_url: str,
    *,
    api_token: str | None,
    curl_bin: str,
    timeout: int,
    bank_prefix: str,
    include_banks: list[str],
    exclude_banks: list[str],
) -> list[dict[str, Any]]:
    excluded = set(exclude_banks)
    if include_banks:
        return [
            {"bank_id": bank_id, "last_document_at": None}
            for bank_id in dict.fromkeys(include_banks)
            if bank_id not in excluded
        ]

    all_banks: list[dict[str, Any]] = []
    offset = 0
    limit = 200
    while True:
        payload = curl_get_json(
            api_url,
            f"/v1/default/banks?limit={limit}&offset={offset}",
            api_token=api_token,
            curl_bin=curl_bin,
            timeout=timeout,
        )
        if isinstance(payload, list):
            batch = payload
            total = None
        elif isinstance(payload, dict):
            batch = payload.get("banks")
            if not isinstance(batch, list):
                raise FetchError("unexpected /v1/default/banks response shape")
            total = payload.get("total")
        else:
            raise FetchError("unexpected /v1/default/banks response type")

        for item in batch:
            if isinstance(item, str):
                bank_id = item
                last_doc_at = None
            elif isinstance(item, dict) and isinstance(item.get("bank_id"), str):
                bank_id = item["bank_id"]
                last_doc_at = item.get("last_document_at")
            else:
                continue
            if bank_prefix and not bank_id.startswith(bank_prefix):
                continue
            if bank_id in excluded:
                continue
            all_banks.append(
                {"bank_id": bank_id, "last_document_at": last_doc_at}
            )

        if not batch or len(batch) < limit:
            break
        offset += len(batch)
        if isinstance(total, int) and offset >= total:
            break

    all_banks.sort(key=lambda b: b["bank_id"])
    return all_banks


def _is_doc_new(
    doc_id: str,
    doc_updated_at: dt.datetime,
    bank_wm: dict[str, Any] | None,
    since_ts: dt.datetime | None,
) -> bool:
    if since_ts is not None and doc_updated_at <= since_ts:
        return False
    if not bank_wm or not bank_wm.get("last_updated_at"):
        return True
    wm_ts = _parse_timestamp(bank_wm["last_updated_at"])
    if wm_ts is None:
        return True
    if doc_updated_at > wm_ts:
        return True
    if doc_updated_at == wm_ts:
        seen = set(bank_wm.get("seen_ids_at_watermark", []))
        return doc_id not in seen
    return False


def find_new_conversation_docs_for_bank(
    api_url: str,
    bank_id: str,
    bank_wm: dict[str, Any] | None,
    *,
    since_ts: dt.datetime | None,
    api_token: str | None,
    curl_bin: str,
    timeout: int,
    page_size: int,
    max_pages: int,
    stop_at_first: bool = False,
) -> list[dict[str, Any]]:
    wm_ts = (
        _parse_timestamp(bank_wm["last_updated_at"])
        if bank_wm and bank_wm.get("last_updated_at")
        else None
    )
    floor_ts = max(t for t in (wm_ts, since_ts) if t is not None) if (wm_ts or since_ts) else None

    encoded_bank = quote(bank_id, safe="")
    new_docs: list[dict[str, Any]] = []
    seen_in_scan: set[str] = set()
    offset = 0

    for _ in range(max_pages):
        payload = curl_get_json(
            api_url,
            f"/v1/default/banks/{encoded_bank}/documents?limit={page_size}&offset={offset}",
            api_token=api_token,
            curl_bin=curl_bin,
            timeout=timeout,
        )
        if isinstance(payload, list):
            items = payload
            total = None
        elif isinstance(payload, dict):
            items = payload.get("items")
            if items is None:
                items = payload.get("documents")
            if not isinstance(items, list):
                raise FetchError(
                    f"unexpected /documents response shape for bank {bank_id}"
                )
            total = payload.get("total")
        else:
            raise FetchError(
                f"unexpected /documents response type for bank {bank_id}"
            )

        if not items:
            break

        page_timestamps: list[dt.datetime] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            doc_id = item.get("id")
            updated_raw = item.get("updated_at") or item.get("created_at")
            if not isinstance(doc_id, str) or not isinstance(updated_raw, str):
                continue
            doc_ts = _parse_timestamp(updated_raw)
            if doc_ts is None:
                continue
            page_timestamps.append(doc_ts)

            if not doc_id.startswith("conversation:"):
                continue
            if doc_id in seen_in_scan:
                continue
            seen_in_scan.add(doc_id)

            if _is_doc_new(doc_id, doc_ts, bank_wm, since_ts):
                new_docs.append(
                    {
                        "bank_id": bank_id,
                        "doc_id": doc_id,
                        "updated_at": updated_raw,
                        "updated_dt": doc_ts,
                        "created_at": item.get("created_at"),
                        "tags": item.get("tags") or [],
                        "text_length": item.get("text_length"),
                    }
                )
                if stop_at_first:
                    return new_docs

        if len(items) < page_size:
            break
        if floor_ts is not None and page_timestamps and all(
            ts < floor_ts for ts in page_timestamps
        ):
            break
        offset += len(items)
        if isinstance(total, int) and offset >= total:
            break

    # Sort ascending by (updated_at, doc_id) so bounded runs consume oldest
    # unseen docs first and never skip newer ones when advancing watermark.
    new_docs.sort(key=lambda d: (d["updated_dt"], d["doc_id"]))
    return new_docs


def _derive_source_repo(bank_id: str, bank_prefix: str) -> str:
    if bank_prefix and bank_id.startswith(bank_prefix):
        raw = bank_id[len(bank_prefix) :]
    else:
        raw = bank_id.split("::")[-1]
    cleaned = raw.lstrip(".").strip().lower()
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", cleaned).strip("-")
    return cleaned or "unknown"


def parse_conversation_text(
    original_text: str, *, max_chars: int
) -> dict[str, Any]:
    reflections: list[dict[str, Any]] = []
    cleaned_turns: list[dict[str, Any]] = []
    total_turns = 0

    lines = original_text.splitlines()
    parsed_any_json = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            obj = None

        if isinstance(obj, dict) and "role" in obj and "content" in obj:
            parsed_any_json = True
            role = str(obj.get("role", "")).strip()
            content = str(obj.get("content", "")).strip()
            timestamp = obj.get("timestamp")
            if not content:
                continue
            if role == "system" and content.startswith("REF-ID:"):
                continue

            turn_index = total_turns
            total_turns += 1

            for match in REFLECTION_RE.finditer(content):
                body = match.group(1).strip()
                if body:
                    reflections.append(
                        {
                            "turn_index": turn_index,
                            "role": role,
                            "timestamp": timestamp,
                            "text": body,
                        }
                    )

            cleaned_turns.append(
                {
                    "turn_index": turn_index,
                    "role": role,
                    "timestamp": timestamp,
                    "content": content,
                }
            )

    if not parsed_any_json and original_text.strip():
        total_turns = 1
        for match in REFLECTION_RE.finditer(original_text):
            body = match.group(1).strip()
            if body:
                reflections.append(
                    {
                        "turn_index": 0,
                        "role": "raw",
                        "timestamp": None,
                        "text": body,
                    }
                )
        cleaned_turns.append(
            {
                "turn_index": 0,
                "role": "raw",
                "timestamp": None,
                "content": original_text.strip(),
            }
        )

    bounded_turns: list[dict[str, Any]] = []
    used_chars = 0
    truncated = False
    for turn in cleaned_turns:
        content = turn["content"]
        remaining = max_chars - used_chars
        if remaining <= 0:
            truncated = True
            break
        if len(content) > remaining:
            clipped = content[: max(0, remaining - 15)].rstrip() + " ...[truncated]"
            bounded_turns.append({**turn, "content": clipped})
            used_chars = max_chars
            truncated = True
            break
        bounded_turns.append(turn)
        used_chars += len(content)

    return {
        "total_turns": total_turns,
        "reflection_count": len(reflections),
        "reflections": reflections,
        "turns": bounded_turns,
        "char_count": used_chars,
        "truncated": truncated,
    }


def build_pending_watermark(fetched_docs: list[dict[str, Any]]) -> dict[str, Any]:
    per_bank: dict[str, dict[str, Any]] = {}
    for doc in fetched_docs:
        bank_id = doc["bank_id"]
        doc_id = doc["doc_id"]
        ts_str = doc["updated_at"]
        ts = _parse_timestamp(ts_str)
        if ts is None:
            continue

        cur = per_bank.get(bank_id)
        if cur is None:
            per_bank[bank_id] = {
                "last_updated_at": ts_str,
                "_dt": ts,
                "seen_ids_at_watermark": [doc_id],
            }
            continue
        if ts > cur["_dt"]:
            per_bank[bank_id] = {
                "last_updated_at": ts_str,
                "_dt": ts,
                "seen_ids_at_watermark": [doc_id],
            }
        elif ts == cur["_dt"]:
            if doc_id not in cur["seen_ids_at_watermark"]:
                cur["seen_ids_at_watermark"].append(doc_id)

    cleaned_banks = {
        bank_id: {
            "last_updated_at": entry["last_updated_at"],
            "seen_ids_at_watermark": sorted(entry["seen_ids_at_watermark"]),
        }
        for bank_id, entry in sorted(per_bank.items())
    }
    return {
        "version": WATERMARK_VERSION,
        "generated_at": _utc_now_iso(),
        "banks": cleaned_banks,
    }


def render_markdown_bundle(bundle: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Hindsight Incremental Conversation Bundle",
        "",
        f"- Generated at: {bundle['generated_at']}",
        f"- Active banks scanned: {bundle['banks_scanned']}",
        f"- New conversation docs fetched: {bundle['doc_count']}",
        f"- Remaining capped docs: {bundle['remaining_docs_capped']}",
        "",
    ]
    if not bundle["documents"]:
        lines.append("NO_OP: no new conversation documents found.")
        return "\n".join(lines) + "\n"

    for idx, doc in enumerate(bundle["documents"], start=1):
        lines.extend(
            [
                f"## Document {idx}: {doc['bank_id']} / {doc['doc_id']}",
                "",
                f"- Source repo slug: `source/{doc['source_repo']}`",
                f"- Updated at: {doc['updated_at']}",
                f"- Reflections: {doc['reflection_count']} | Turns: {doc['total_turns']} | Truncated: {doc['truncated']}",
                "",
            ]
        )
        if doc["reflections"]:
            lines.append("### Extracted Reflections")
            lines.append("")
            for r_idx, refl in enumerate(doc["reflections"], start=1):
                lines.append(
                    f"- [R{r_idx} turn={refl['turn_index']} role={refl['role']}] {refl['text']}"
                )
            lines.append("")
        lines.append("### Cleaned Turns")
        lines.append("")
        for turn in doc["turns"]:
            ts_part = f" ({turn['timestamp']})" if turn.get("timestamp") else ""
            lines.append(
                f"#### Turn {turn['turn_index']} [{turn['role']}]{ts_part}"
            )
            lines.append("")
            lines.append(turn["content"])
            lines.append("")
    return "\n".join(lines)


def run_precheck(args: argparse.Namespace) -> int:
    api_url, api_token = load_hindsight_config(
        args.config, args.api_url, args.api_token
    )
    watermark = load_watermark(args.state_file)
    since_ts = _parse_timestamp(args.since) if args.since else None
    banks = list_active_banks(
        api_url,
        api_token=api_token,
        curl_bin=args.curl_bin,
        timeout=args.timeout,
        bank_prefix=args.bank_prefix,
        include_banks=_parse_csv_args(args.banks),
        exclude_banks=_parse_csv_args(args.exclude_banks),
    )

    for bank in banks:
        bank_id = bank["bank_id"]
        bank_wm = watermark["banks"].get(bank_id)
        found = find_new_conversation_docs_for_bank(
            api_url,
            bank_id,
            bank_wm,
            since_ts=since_ts,
            api_token=api_token,
            curl_bin=args.curl_bin,
            timeout=args.timeout,
            page_size=args.page_size,
            max_pages=args.max_pages_per_bank,
            stop_at_first=True,
        )
        if found:
            sample = found[0]
            print(
                f"[ok] new conversation docs found: {bank_id} / {sample['doc_id']} "
                f"(updated_at={sample['updated_at']})"
            )
            return 0

    print(f"[ok] no new conversation docs across {len(banks)} bank(s)")
    return 1


def run_fetch(args: argparse.Namespace) -> int:
    api_url, api_token = load_hindsight_config(
        args.config, args.api_url, args.api_token
    )
    watermark = load_watermark(args.state_file)
    since_ts = _parse_timestamp(args.since) if args.since else None
    banks = list_active_banks(
        api_url,
        api_token=api_token,
        curl_bin=args.curl_bin,
        timeout=args.timeout,
        bank_prefix=args.bank_prefix,
        include_banks=_parse_csv_args(args.banks),
        exclude_banks=_parse_csv_args(args.exclude_banks),
    )

    candidates: list[dict[str, Any]] = []
    remaining_capped = 0

    for bank in banks:
        bank_id = bank["bank_id"]
        bank_wm = watermark["banks"].get(bank_id)
        found = find_new_conversation_docs_for_bank(
            api_url,
            bank_id,
            bank_wm,
            since_ts=since_ts,
            api_token=api_token,
            curl_bin=args.curl_bin,
            timeout=args.timeout,
            page_size=args.page_size,
            max_pages=args.max_pages_per_bank,
            stop_at_first=False,
        )
        if len(found) > args.max_docs_per_bank:
            remaining_capped += len(found) - args.max_docs_per_bank
            found = found[: args.max_docs_per_bank]
        candidates.extend(found)

    candidates.sort(key=lambda d: (d["updated_dt"], d["bank_id"], d["doc_id"]))
    if len(candidates) > args.max_docs_per_run:
        remaining_capped += len(candidates) - args.max_docs_per_run
        candidates = candidates[: args.max_docs_per_run]

    fetched_docs: list[dict[str, Any]] = []
    total_chars = 0

    for idx, item in enumerate(candidates):
        remaining_budget = args.max_total_chars - total_chars
        if remaining_budget <= 0:
            remaining_capped += len(candidates) - idx
            break
        per_doc_budget = min(args.max_chars_per_doc, remaining_budget)

        encoded_bank = quote(item["bank_id"], safe="")
        encoded_doc = quote(item["doc_id"], safe="")
        detail = curl_get_json(
            api_url,
            f"/v1/default/banks/{encoded_bank}/documents/{encoded_doc}",
            api_token=api_token,
            curl_bin=args.curl_bin,
            timeout=args.timeout,
        )
        if not isinstance(detail, dict):
            raise FetchError(
                f"unexpected document detail shape for {item['bank_id']} / {item['doc_id']}"
            )
        original_text = detail.get("original_text")
        if not isinstance(original_text, str):
            original_text = ""

        parsed = parse_conversation_text(original_text, max_chars=per_doc_budget)
        total_chars += parsed["char_count"]

        doc_record = {
            "bank_id": item["bank_id"],
            "source_repo": _derive_source_repo(item["bank_id"], args.bank_prefix),
            "doc_id": item["doc_id"],
            "updated_at": detail.get("updated_at") or item["updated_at"],
            "created_at": detail.get("created_at") or item.get("created_at"),
            "tags": detail.get("tags") or item.get("tags") or [],
            "total_turns": parsed["total_turns"],
            "reflection_count": parsed["reflection_count"],
            "reflections": parsed["reflections"],
            "turns": parsed["turns"],
            "char_count": parsed["char_count"],
            "truncated": parsed["truncated"],
        }
        fetched_docs.append(doc_record)

    pending_watermark = build_pending_watermark(fetched_docs)
    bundle = {
        "version": WATERMARK_VERSION,
        "generated_at": _utc_now_iso(),
        "state_file": str(args.state_file),
        "banks_scanned": len(banks),
        "doc_count": len(fetched_docs),
        "remaining_docs_capped": remaining_capped,
        "pending_watermark": pending_watermark,
        "documents": fetched_docs,
    }

    if args.pending_file is not None:
        atomic_write_json(args.pending_file, pending_watermark)

    if args.format == "markdown":
        rendered = render_markdown_bundle(bundle)
    else:
        rendered = json.dumps(bundle, indent=2, ensure_ascii=False) + "\n"

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    return 0


def run_advance(args: argparse.Namespace) -> int:
    if args.pending_file is not None and args.pending_json is not None:
        raise FetchError("specify only one of --pending-file or --pending-json")
    if args.pending_file is None and args.pending_json is None:
        raise FetchError("--advance requires --pending-file or --pending-json")

    if args.pending_file is not None:
        if not args.pending_file.is_file():
            raise FetchError(f"pending file not found: {args.pending_file}")
        try:
            raw_pending = json.loads(args.pending_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FetchError(
                f"failed to parse pending file {args.pending_file}: {exc}"
            ) from exc
    else:
        try:
            raw_pending = json.loads(args.pending_json)
        except json.JSONDecodeError as exc:
            raise FetchError(f"failed to parse --pending-json: {exc}") from exc

    if not isinstance(raw_pending, dict):
        raise FetchError("pending watermark payload must be a JSON object")

    if "pending_watermark" in raw_pending and isinstance(
        raw_pending["pending_watermark"], dict
    ):
        pending_banks = raw_pending["pending_watermark"].get("banks", {})
    elif "banks" in raw_pending and isinstance(raw_pending["banks"], dict):
        pending_banks = raw_pending["banks"]
    else:
        raise FetchError(
            "pending payload must contain 'banks' or 'pending_watermark.banks'"
        )

    existing = load_watermark(args.state_file)
    merged = merge_watermarks_monotonic(existing, pending_banks)
    atomic_write_json(args.state_file, merged)
    print(
        f"[ok] watermark advanced at {args.state_file} "
        f"({len(merged['banks'])} bank(s) tracked)"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Incremental Hindsight conversation:* document fetcher for the "
            "SilverBullet KB nightly maintainer bot."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--precheck",
        action="store_true",
        help="Exit 0 if new conversation:* docs exist, 1 if none, 2 on error.",
    )
    mode.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch new conversation:* docs without advancing the watermark.",
    )
    mode.add_argument(
        "--advance",
        action="store_true",
        help="Atomically merge pending watermark into --state-file.",
    )

    parser.add_argument(
        "--bot-name",
        default=DEFAULT_BOT_NAME,
        help=f"Bot name used for default --state-file path (default: {DEFAULT_BOT_NAME}).",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help="Path to watermark JSON file (default: ~/.orca/bots/<bot-name>/memory/hindsight-watermark.json).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to Hindsight coding-agent.json (default: ~/.hindsight/coding-agent.json or HINDSIGHT_CONFIG).",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="Override Hindsight apiUrl (or set HINDSIGHT_API_URL).",
    )
    parser.add_argument(
        "--api-token",
        default=None,
        help="Override Hindsight apiToken (or set HINDSIGHT_API_TOKEN).",
    )
    parser.add_argument(
        "--curl-bin",
        default=os.environ.get("HINDSIGHT_CURL_BIN", "curl"),
        help="curl binary path (default: curl or HINDSIGHT_CURL_BIN).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request curl timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--bank-prefix",
        default=DEFAULT_BANK_PREFIX,
        help=f"Bank id prefix when auto-discovering banks (default: {DEFAULT_BANK_PREFIX}).",
    )
    parser.add_argument(
        "--banks",
        action="append",
        default=None,
        help="Explicit bank id(s) to scan (comma-separated or repeatable).",
    )
    parser.add_argument(
        "--exclude-banks",
        action="append",
        default=None,
        help="Bank id(s) to skip (comma-separated or repeatable).",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Optional ISO-8601 lower bound; ignore docs at or before this timestamp.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Documents page size per API call (default: {DEFAULT_PAGE_SIZE}).",
    )
    parser.add_argument(
        "--max-pages-per-bank",
        type=int,
        default=DEFAULT_MAX_PAGES_PER_BANK,
        help=f"Maximum document pages scanned per bank (default: {DEFAULT_MAX_PAGES_PER_BANK}).",
    )
    parser.add_argument(
        "--max-docs-per-bank",
        type=int,
        default=DEFAULT_MAX_DOCS_PER_BANK,
        help=f"Maximum new docs fetched per bank per run (default: {DEFAULT_MAX_DOCS_PER_BANK}).",
    )
    parser.add_argument(
        "--max-docs-per-run",
        type=int,
        default=DEFAULT_MAX_DOCS_PER_RUN,
        help=f"Maximum new docs fetched across all banks per run (default: {DEFAULT_MAX_DOCS_PER_RUN}).",
    )
    parser.add_argument(
        "--max-chars-per-doc",
        type=int,
        default=DEFAULT_MAX_CHARS_PER_DOC,
        help=f"Maximum cleaned turn characters retained per doc (default: {DEFAULT_MAX_CHARS_PER_DOC}).",
    )
    parser.add_argument(
        "--max-total-chars",
        type=int,
        default=DEFAULT_MAX_TOTAL_CHARS,
        help=f"Maximum cleaned turn characters retained per run (default: {DEFAULT_MAX_TOTAL_CHARS}).",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for --fetch (default: json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write --fetch output to file instead of stdout.",
    )
    parser.add_argument(
        "--pending-file",
        type=Path,
        default=None,
        help="Pending watermark JSON file (written by --fetch, consumed by --advance).",
    )
    parser.add_argument(
        "--pending-json",
        default=None,
        help="Inline pending watermark JSON string consumed by --advance.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.state_file is None:
        args.state_file = _default_state_file(args.bot_name)
    else:
        args.state_file = args.state_file.expanduser()
    if args.config is not None:
        args.config = args.config.expanduser()
    if args.output is not None:
        args.output = args.output.expanduser()
    if args.pending_file is not None:
        args.pending_file = args.pending_file.expanduser()

    for flag_name in (
        "timeout",
        "page_size",
        "max_pages_per_bank",
        "max_docs_per_bank",
        "max_docs_per_run",
        "max_chars_per_doc",
        "max_total_chars",
    ):
        if getattr(args, flag_name) <= 0:
            print(
                f"[x] --{flag_name.replace('_', '-')} must be a positive integer",
                file=sys.stderr,
            )
            return 2

    try:
        if args.precheck:
            return run_precheck(args)
        if args.fetch:
            return run_fetch(args)
        if args.advance:
            return run_advance(args)
    except FetchError as exc:
        print(f"[x] {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

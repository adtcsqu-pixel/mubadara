from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests


DEFAULT_DB: Dict[str, Any] = {
    "schema_version": 1,
    "events": [],
    "notes": [],
    "audit": [],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_filename(name: str) -> str:
    """Keep uploaded filenames readable while preventing path traversal."""
    name = unicodedata.normalize("NFKC", name or "file")
    name = name.replace("\\", "_").replace("/", "_")
    name = re.sub(r"[^\w.()\-\u0600-\u06FF ]+", "_", name, flags=re.UNICODE)
    name = re.sub(r"\s+", "_", name).strip("._")
    return name[:120] or "file"


class StorageError(RuntimeError):
    pass


class GitHubStorage:
    """A tiny GitHub-backed JSON/document store.

    Every write becomes a Git commit. This gives Mubadara both a live data store
    and an immutable-by-default repository history/audit trail.
    """

    def __init__(self, token: str, repo: str, branch: str = "main") -> None:
        if not token or not repo:
            raise ValueError("GitHub token and repo are required")
        if "/" not in repo:
            raise ValueError("repo must be in owner/repository format")
        self.token = token
        self.repo = repo
        self.branch = branch or "main"
        self.api = f"https://api.github.com/repos/{repo}"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mubadara-streamlit",
        }
        self.db_path = "data/db.json"

    @property
    def mode(self) -> str:
        return "github"

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        try:
            response = requests.request(method, url, headers=self.headers, timeout=30, **kwargs)
        except requests.RequestException as exc:
            raise StorageError(f"GitHub connection failed: {exc}") from exc
        if response.status_code >= 400:
            detail = ""
            try:
                detail = response.json().get("message", "")
            except Exception:
                detail = response.text[:250]
            raise StorageError(f"GitHub API {response.status_code}: {detail}")
        return response

    def _get_file(self, path: str) -> Optional[Dict[str, Any]]:
        url = f"{self.api}/contents/{path}"
        response = requests.get(
            url,
            headers=self.headers,
            params={"ref": self.branch},
            timeout=30,
        )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            try:
                message = response.json().get("message", response.text)
            except Exception:
                message = response.text
            raise StorageError(f"GitHub API {response.status_code}: {message}")
        return response.json()

    def _put_file(self, path: str, content: bytes, message: str) -> None:
        current = self._get_file(path)
        payload: Dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.branch,
        }
        if current and current.get("sha"):
            payload["sha"] = current["sha"]
        self._request("PUT", f"{self.api}/contents/{path}", json=payload)

    def load_db(self) -> Dict[str, Any]:
        current = self._get_file(self.db_path)
        if current is None:
            db = deepcopy(DEFAULT_DB)
            self.save_db(db, "Initialize Mubadara data store")
            return db
        try:
            raw = base64.b64decode(current["content"])
            db = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise StorageError("data/db.json exists but could not be decoded") from exc
        for key, value in DEFAULT_DB.items():
            db.setdefault(key, deepcopy(value))
        return db

    def save_db(self, db: Dict[str, Any], message: str = "Update Mubadara data") -> None:
        body = json.dumps(db, ensure_ascii=False, indent=2).encode("utf-8")
        self._put_file(self.db_path, body, message)

    def save_attachment(self, event_id: str, kind: str, filename: str, content: bytes) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = safe_filename(filename)
        kind = safe_filename(kind)
        path = f"data/uploads/{safe_filename(event_id)}/{kind}/{stamp}_{filename}"
        self._put_file(path, content, f"Upload {kind} for event {event_id}: {filename}")
        return path


class LocalStorage:
    """Development fallback. Production should use GitHubStorage."""

    def __init__(self, root: str | Path = ".local_data") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_file = self.root / "db.json"

    @property
    def mode(self) -> str:
        return "local"

    def load_db(self) -> Dict[str, Any]:
        if not self.db_file.exists():
            db = deepcopy(DEFAULT_DB)
            self.save_db(db, "Initialize local data store")
            return db
        db = json.loads(self.db_file.read_text(encoding="utf-8"))
        for key, value in DEFAULT_DB.items():
            db.setdefault(key, deepcopy(value))
        return db

    def save_db(self, db: Dict[str, Any], message: str = "Update local data") -> None:
        self.db_file.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_attachment(self, event_id: str, kind: str, filename: str, content: bytes) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rel = Path("uploads") / safe_filename(event_id) / safe_filename(kind) / f"{stamp}_{safe_filename(filename)}"
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return str(rel).replace(os.sep, "/")

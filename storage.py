from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

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


def normalize_repo(value: str) -> str:
    """Accept owner/repo as well as common GitHub repository URLs."""
    value = (value or "").strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2:
            value = f"{parts[0]}/{parts[1]}"
    return value


class StorageError(RuntimeError):
    pass


class GitHubStorage:
    """A small GitHub-backed JSON/document store.

    Every write becomes a Git commit. The implementation is intentionally
    defensive around empty repositories and branch mismatches, two common
    causes of GitHub Contents API 404 errors on Streamlit Cloud.
    """

    def __init__(self, token: str, repo: str, branch: str = "main") -> None:
        repo = normalize_repo(repo)
        if not token or not repo:
            raise ValueError("GitHub token and repo are required")
        if "/" not in repo:
            raise ValueError("repo must be in owner/repository format")
        self.token = token.strip()
        self.repo = repo
        self.branch = (branch or "main").strip()
        self.api = f"https://api.github.com/repos/{repo}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mubadara-streamlit",
        }
        self.db_path = "data/db.json"
        self._resolved_branch: Optional[str] = None
        self._repo_is_empty: Optional[bool] = None
        self._last_error: str = ""

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
            if response.status_code == 404:
                raise StorageError(
                    "GitHub API 404: repository/branch was not found or the token cannot access it. "
                    f"Check repo='{self.repo}', branch='{self.branch}', and grant the token Contents: Read and write. "
                    f"GitHub message: {detail or 'Not Found'}"
                )
            raise StorageError(f"GitHub API {response.status_code}: {detail}")
        return response

    def _repo_info(self) -> Dict[str, Any]:
        response = self._request("GET", self.api)
        info = response.json()
        self._repo_is_empty = int(info.get("size") or 0) == 0
        return info

    def _resolve_branch(self) -> Optional[str]:
        """Return a usable branch, or None for a completely empty repository.

        For an empty GitHub repository the first Contents API write must target
        the repository default branch without forcing a non-existent branch.
        """
        if self._resolved_branch:
            return self._resolved_branch

        info = self._repo_info()
        if self._repo_is_empty:
            return None

        candidates = []
        if self.branch:
            candidates.append(self.branch)
        default_branch = str(info.get("default_branch") or "").strip()
        if default_branch and default_branch not in candidates:
            candidates.append(default_branch)

        for candidate in candidates:
            try:
                response = requests.get(
                    f"{self.api}/branches/{candidate}",
                    headers=self.headers,
                    timeout=30,
                )
            except requests.RequestException as exc:
                raise StorageError(f"GitHub connection failed: {exc}") from exc
            if response.status_code == 200:
                self._resolved_branch = candidate
                return candidate
            if response.status_code not in {404}:
                try:
                    message = response.json().get("message", response.text)
                except Exception:
                    message = response.text
                raise StorageError(f"GitHub API {response.status_code}: {message}")

        raise StorageError(
            f"No usable GitHub branch was found. Configured branch='{self.branch}', "
            f"repository default branch='{default_branch or 'unknown'}'."
        )

    def healthcheck(self) -> Tuple[bool, str]:
        """Check that the repository is reachable without mutating it.

        This intentionally does not claim that writes are guaranteed; GitHub may
        still hide a missing fine-grained Contents:write permission behind 404.
        """
        try:
            info = self._repo_info()
            permissions = info.get("permissions") or {}
            if permissions and permissions.get("push") is False:
                return False, (
                    f"{self.repo}: repository is readable but the authenticated account/token "
                    "does not have push/write access."
                )
            if self._repo_is_empty:
                return True, f"{self.repo} (reachable; empty repository, first write will initialize it)"
            branch = self._resolve_branch()
            return True, f"{self.repo} · {branch or self.branch}"
        except StorageError as exc:
            self._last_error = str(exc)
            return False, str(exc)

    def _get_file(self, path: str) -> Optional[Dict[str, Any]]:
        branch = self._resolve_branch()
        if branch is None:
            return None

        url = f"{self.api}/contents/{path}"
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params={"ref": branch},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise StorageError(f"GitHub connection failed: {exc}") from exc

        if response.status_code == 404:
            # Repository and branch were already validated above, so this 404
            # means only that the requested file does not exist yet.
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
        }

        # Empty repositories have no branch reference yet. Omitting `branch`
        # lets GitHub initialize the repository's default branch on first write.
        branch = self._resolved_branch
        if branch:
            payload["branch"] = branch
        if current and current.get("sha"):
            payload["sha"] = current["sha"]

        try:
            self._request("PUT", f"{self.api}/contents/{path}", json=payload)
        except StorageError as exc:
            # GitHub commonly returns 404 for private repositories when a token
            # lacks the required fine-grained Contents: write permission.  Keep
            # the message actionable and never expose the token itself.
            msg = str(exc)
            if "404" in msg:
                raise StorageError(
                    f"GitHub write failed for '{self.repo}'. The repository may be private, "
                    "the repo value may be wrong, or the token may not have Contents: Read and write. "
                    "Verify that the token is explicitly allowed to this repository and that branch "
                    f"'{self.branch}' exists (or leave an empty repository to be initialized)."
                ) from exc
            raise

        # The first write to an empty repository creates its default branch.
        if self._repo_is_empty:
            self._repo_is_empty = False
            self._resolved_branch = None
            self._resolve_branch()

    def load_db(self) -> Dict[str, Any]:
        current = self._get_file(self.db_path)
        if current is None:
            # Do not write while merely opening the dashboard. This keeps login
            # usable even when a GitHub token is read-only/misconfigured. The
            # first actual save (or demo seed save) will initialize data/db.json.
            return deepcopy(DEFAULT_DB)
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

    def healthcheck(self) -> Tuple[bool, str]:
        return True, "local"

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

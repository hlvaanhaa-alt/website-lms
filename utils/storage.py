import base64
import json
import os
import shutil
import threading
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DATA_DIR = BASE_DIR / "data"
STATIC_FORUM_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "forum"

DATA_BACKEND = os.getenv("DATA_BACKEND", "file").lower()
PERSISTENT_DIR = os.getenv("PERSISTENT_DIR")
GITHUB_BACKEND = DATA_BACKEND == "github"
GITHUB_DATA_REPO = os.getenv("GITHUB_DATA_REPO", "")
GITHUB_DATA_BRANCH = os.getenv("GITHUB_DATA_BRANCH", "main")
GITHUB_DATA_TOKEN = os.getenv("GITHUB_DATA_TOKEN") or os.getenv("GITHUB_TOKEN")
GITHUB_DATA_PREFIX = os.getenv("GITHUB_DATA_PREFIX", "").strip("/")

RUNNING_ON_RENDER = any(
    os.getenv(name)
    for name in (
        "RENDER",
        "RENDER_EXTERNAL_URL",
        "RENDER_SERVICE_ID",
        "RENDER_INSTANCE_ID",
    )
)

if RUNNING_ON_RENDER and not PERSISTENT_DIR and not GITHUB_BACKEND:
    raise RuntimeError(
        "Persistent storage is required on Render to prevent user data loss. "
        "Set PERSISTENT_DIR for a Render Persistent Disk or set DATA_BACKEND=github "
        "with GITHUB_DATA_REPO and GITHUB_DATA_TOKEN."
    )

if GITHUB_BACKEND and (not GITHUB_DATA_REPO or not GITHUB_DATA_TOKEN):
    raise RuntimeError(
        "DATA_BACKEND=github requires GITHUB_DATA_REPO and GITHUB_DATA_TOKEN."
    )

if GITHUB_BACKEND and not PERSISTENT_DIR:
    _github_cache_root = Path(
        os.getenv("GITHUB_DATA_CACHE_DIR", BASE_DIR / ".runtime_data")
    ).resolve()
    DATA_DIR = Path(os.getenv("DATA_DIR", _github_cache_root / "data")).resolve()
    STATE_DIR = Path(os.getenv("STATE_DIR", _github_cache_root)).resolve()
    FORUM_UPLOAD_DIR = Path(
        os.getenv("FORUM_UPLOAD_DIR", _github_cache_root / "uploads" / "forum")
    ).resolve()
elif PERSISTENT_DIR:
    _persistent_root = Path(PERSISTENT_DIR).resolve()
    DATA_DIR = Path(os.getenv("DATA_DIR", _persistent_root / "data")).resolve()
    STATE_DIR = Path(os.getenv("STATE_DIR", _persistent_root)).resolve()
    FORUM_UPLOAD_DIR = Path(
        os.getenv("FORUM_UPLOAD_DIR", _persistent_root / "uploads" / "forum")
    ).resolve()
else:
    DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
    STATE_DIR = Path(os.getenv("STATE_DIR", BASE_DIR)).resolve()
    FORUM_UPLOAD_DIR = Path(
        os.getenv("FORUM_UPLOAD_DIR", BASE_DIR / "static" / "uploads" / "forum")
    ).resolve()

FORUM_UPLOAD_URL_PREFIX = "/uploads/forum"
_json_locks = {}
_json_locks_guard = threading.Lock()


def _github_headers():
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_DATA_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_remote_path(relative_path):
    relative_path = str(relative_path).replace("\\", "/").strip("/")
    if GITHUB_DATA_PREFIX:
        return f"{GITHUB_DATA_PREFIX}/{relative_path}"
    return relative_path


def _remote_path_for(local_path):
    local_path = Path(local_path).resolve()
    for base, prefix in (
        (DATA_DIR, "data"),
        (FORUM_UPLOAD_DIR, "uploads/forum"),
        (STATE_DIR, ""),
    ):
        try:
            relative = local_path.relative_to(base.resolve()).as_posix()
        except ValueError:
            continue
        return _github_remote_path(f"{prefix}/{relative}" if prefix else relative)
    return None


def _github_content_url(remote_path):
    return f"https://api.github.com/repos/{GITHUB_DATA_REPO}/contents/{remote_path}"


def _github_get_metadata(remote_path):
    response = requests.get(
        _github_content_url(remote_path),
        headers=_github_headers(),
        params={"ref": GITHUB_DATA_BRANCH},
        timeout=20,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _github_download(remote_path):
    metadata = _github_get_metadata(remote_path)
    if not metadata or metadata.get("type") != "file":
        return None
    content = metadata.get("content", "")
    return base64.b64decode(content)


def _github_upload(remote_path, data, message):
    metadata = _github_get_metadata(remote_path)
    payload = {
        "message": message,
        "branch": GITHUB_DATA_BRANCH,
        "content": base64.b64encode(data).decode("ascii"),
    }
    if metadata and metadata.get("sha"):
        payload["sha"] = metadata["sha"]

    response = requests.put(
        _github_content_url(remote_path),
        headers=_github_headers(),
        json=payload,
        timeout=30,
    )
    if response.status_code == 409:
        metadata = _github_get_metadata(remote_path)
        if metadata and metadata.get("sha"):
            payload["sha"] = metadata["sha"]
            response = requests.put(
                _github_content_url(remote_path),
                headers=_github_headers(),
                json=payload,
                timeout=30,
            )
    response.raise_for_status()


def ensure_file_from_remote(local_path, remote_path=None):
    if not GITHUB_BACKEND:
        return False
    local_path = Path(local_path)
    remote_path = remote_path or _remote_path_for(local_path)
    if not remote_path:
        return False
    data = _github_download(remote_path)
    if data is None:
        return False
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(data)
    return True


def sync_file_to_remote(local_path, remote_path=None):
    if not GITHUB_BACKEND:
        return
    local_path = Path(local_path)
    remote_path = remote_path or _remote_path_for(local_path)
    if not remote_path or not local_path.exists():
        return
    _github_upload(remote_path, local_path.read_bytes(), f"Update {remote_path}")


def ensure_forum_upload_available(filename):
    safe_filename = Path(filename).name
    target = FORUM_UPLOAD_DIR / safe_filename
    if target.exists():
        return True
    if ensure_file_from_remote(target):
        return True

    seed = STATIC_FORUM_UPLOAD_DIR / safe_filename
    if seed.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed, target)
        sync_file_to_remote(target)
        return True
    return False


def _lock_for(path):
    key = str(Path(path).resolve())
    with _json_locks_guard:
        if key not in _json_locks:
            _json_locks[key] = threading.Lock()
        return _json_locks[key]


def read_json(path, default=None):
    try:
        with _lock_for(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return [] if default is None else default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    with _lock_for(path):
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    sync_file_to_remote(path)


def _copy_seed(seed_path, target_path):
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed_path, target_path)
    sync_file_to_remote(target_path)


def writable_data_file(filename, default=None):
    target = DATA_DIR / filename
    if GITHUB_BACKEND and ensure_file_from_remote(target):
        return str(target)
    if not target.exists():
        seed = REPO_DATA_DIR / filename
        if seed.exists():
            _copy_seed(seed, target)
        else:
            write_json(target, [] if default is None else default)
    return str(target)


def readable_data_file(filename):
    target = DATA_DIR / filename
    if GITHUB_BACKEND and ensure_file_from_remote(target):
        return str(target)
    if target.exists():
        return str(target)
    return str(REPO_DATA_DIR / filename)


def writable_state_file(filename, default=None):
    target = STATE_DIR / filename
    if GITHUB_BACKEND and ensure_file_from_remote(target):
        return str(target)
    if not target.exists():
        seed = BASE_DIR / filename
        if seed.exists():
            _copy_seed(seed, target)
        else:
            write_json(target, [] if default is None else default)
    return str(target)


def forum_upload_path(filename):
    FORUM_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return FORUM_UPLOAD_DIR / filename


def forum_upload_url(filename):
    return f"{FORUM_UPLOAD_URL_PREFIX}/{filename}"


def attachment_storage_path(attachment):
    storage_path = attachment.get("storage_path")
    if storage_path:
        return Path(storage_path)

    path = attachment.get("path", "")
    if path.startswith(FORUM_UPLOAD_URL_PREFIX + "/"):
        return FORUM_UPLOAD_DIR / Path(path).name

    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return BASE_DIR / candidate

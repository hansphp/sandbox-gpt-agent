#!/usr/bin/env python3
"""
sandbox-gpt-agent: REST control plane for a controlled technology environment.

This service is intentionally capable of remote command execution. It is meant
for a server, VPS, container, or lab that you control, not for shared or
production systems.

Core properties:
- FastAPI + systemd service.
- Bearer-token authentication for all private endpoints.
- Public /health, /privacy, /gpt-action-openapi.yaml and signed downloads only.
- Execute Linux commands with full shell semantics, or argv mode when desired.
- Background jobs, logs, audit trail, file read/write/list/delete/chmod/share.
- Static/dynamic OpenAPI schema designed for ChatGPT GPT Actions.
"""

from __future__ import annotations

import base64
import getpass
import hmac
import json
import mimetypes
import os
import platform
import secrets
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field


APP_NAME = "sandbox-gpt-agent"
APP_VERSION = "2.1.0"
TOKEN = os.getenv("SANDBOX_TOKEN", "").strip()
BIND = os.getenv("SANDBOX_BIND", "127.0.0.1")
PORT = int(os.getenv("SANDBOX_PORT", "8765"))
SHELL_BIN = os.getenv("SANDBOX_SHELL", "/bin/bash")
WORKDIR = Path(os.getenv("SANDBOX_WORKDIR", "/srv/sandbox-gpt-agent/workspace")).resolve()
STATE_DIR = Path(os.getenv("SANDBOX_STATE_DIR", "/var/lib/sandbox-gpt-agent")).resolve()
JOB_DIR = STATE_DIR / "jobs"
SHARE_FILE = STATE_DIR / "shares.json"
LOG_FILE = Path(os.getenv("SANDBOX_AUDIT_LOG", "/var/log/sandbox-gpt-agent/audit.log")).resolve()
ALLOW_ABSOLUTE_PATHS = os.getenv("SANDBOX_ALLOW_ABSOLUTE", "1") == "1"
DEFAULT_TIMEOUT = float(os.getenv("SANDBOX_DEFAULT_TIMEOUT", "40"))
MAX_TIMEOUT = float(os.getenv("SANDBOX_MAX_TIMEOUT", "3600"))
MAX_SYNC_OUTPUT_BYTES = int(os.getenv("SANDBOX_MAX_SYNC_OUTPUT_BYTES", str(60 * 1024)))
MAX_READ_BYTES = int(os.getenv("SANDBOX_MAX_READ_BYTES", str(80 * 1024)))
MAX_IMPORT_FILE_BYTES = int(os.getenv("SANDBOX_MAX_IMPORT_FILE_BYTES", str(512 * 1024 * 1024)))
MAX_EXPORT_FILE_BYTES = int(os.getenv("SANDBOX_MAX_EXPORT_FILE_BYTES", str(10 * 1024 * 1024)))
ACTION_CONSEQUENTIAL = os.getenv("SANDBOX_ACTIONS_CONSEQUENTIAL", "false").strip().lower() in {"1", "true", "yes"}
RATE_LIMIT_PER_MIN = int(os.getenv("SANDBOX_RATE_LIMIT_PER_MIN", "120"))
PUBLIC_BASE_URL = os.getenv("SANDBOX_PUBLIC_BASE_URL", "").rstrip("/")
PRIVACY_CONTACT = os.getenv("SANDBOX_PRIVACY_CONTACT", "sandbox owner")


app = FastAPI(
    title="Sandbox GPT Agent API",
    version=APP_VERSION,
    description="Authenticated REST API for operating a controlled technology environment from a GPT Action.",
    docs_url=None,
    redoc_url=None,
)

_rate_lock = threading.Lock()
_rate_buckets: Dict[str, List[float]] = {}
_share_lock = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_runtime_dirs() -> None:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not SHARE_FILE.exists():
        SHARE_FILE.write_text("{}", encoding="utf-8")


ensure_runtime_dirs()


def audit(event: str, **fields: Any) -> None:
    record = {"ts": utc_now(), "event": event, **fields}
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def base_url_from_request(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    scheme = request.headers.get("X-Forwarded-Proto") or request.url.scheme
    host = request.headers.get("Host") or f"127.0.0.1:{PORT}"
    return f"{scheme}://{host}".rstrip("/")


def rate_limit_ok(key: str) -> bool:
    if RATE_LIMIT_PER_MIN <= 0:
        return True
    now = time.time()
    cutoff = now - 60
    with _rate_lock:
        bucket = [t for t in _rate_buckets.get(key, []) if t >= cutoff]
        if len(bucket) >= RATE_LIMIT_PER_MIN:
            _rate_buckets[key] = bucket
            return False
        bucket.append(now)
        _rate_buckets[key] = bucket
        return True


def is_public_path(path: str) -> bool:
    return (
        path == "/health"
        or path == "/privacy"
        or path == "/gpt-action-openapi.yaml"
        or path.startswith("/public/download/")
    )


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    ip = client_ip(request)

    if not rate_limit_ok(ip):
        audit("rate_limited", path=path, client=ip)
        return JSONResponse({"error": "rate_limited"}, status_code=429)

    if is_public_path(path):
        return await call_next(request)

    if not TOKEN:
        audit("auth_error", path=path, reason="SANDBOX_TOKEN is not set")
        return JSONResponse({"error": "SANDBOX_TOKEN is not configured"}, status_code=500)

    auth_header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    supplied = auth_header[len(prefix):] if auth_header.startswith(prefix) else ""

    if not supplied or not hmac.compare_digest(supplied, TOKEN):
        audit("auth_fail", path=path, client=ip)
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return await call_next(request)


class ExecRequest(BaseModel):
    command: Union[str, List[str]] = Field(..., description="Command string or argv list.")
    cwd: Optional[str] = Field(default=None, description="Working directory. Relative paths are under SANDBOX_WORKDIR.")
    env: Dict[str, str] = Field(default_factory=dict, description="Extra environment variables for the process.")
    stdin: Optional[str] = Field(default=None, description="Text sent to stdin.")
    stdin_base64: Optional[str] = Field(default=None, description="Base64 bytes sent to stdin.")
    timeout: Optional[float] = Field(default=None, description="Timeout in seconds. Use background=true for long tasks.")
    shell: bool = Field(default=True, description="Run through /bin/bash -lc for pipes, redirects and heredocs.")
    background: bool = Field(default=False, description="Start a background job and return immediately.")
    max_output_bytes: Optional[int] = Field(default=None, description="Sync output cap per stream. 0 means unlimited.")


class WriteFileRequest(BaseModel):
    path: str = Field(..., description="File path. Relative paths are under SANDBOX_WORKDIR; absolute paths allowed if configured.")
    content: str = Field(..., description="Text or base64 content.")
    encoding: str = Field(default="text", description="text or base64")
    append: bool = Field(default=False, description="Append instead of overwrite.")
    mode: Optional[str] = Field(default=None, description="Optional chmod mode, e.g. 0644.")


class MkdirRequest(BaseModel):
    path: str
    parents: bool = True
    exist_ok: bool = True
    mode: str = "0755"


class ChmodRequest(BaseModel):
    path: str
    mode: str = Field(..., description="Octal mode, e.g. 0755.")


class FetchUrlRequest(BaseModel):
    url: str = Field(..., description="HTTP/HTTPS URL to download into the workspace.")
    path: str = Field(..., description="Destination path in the controlled environment.")
    method: str = Field(default="GET", description="HTTP method: GET, POST, PUT, or PATCH.")
    headers: Dict[str, str] = Field(default_factory=dict, description="Optional request headers.")
    body: Optional[str] = Field(default=None, description="Optional UTF-8 request body.")
    body_base64: Optional[str] = Field(default=None, description="Optional base64 request body.")
    timeout: float = Field(default=30.0, description="Request timeout in seconds.")
    mode: Optional[str] = Field(default=None, description="Optional chmod mode after saving.")


class ShareFileRequest(BaseModel):
    path: str = Field(..., description="File path to expose through a signed public download URL.")
    ttl_seconds: int = Field(default=3600, ge=60, le=86400, description="Validity window between 60 seconds and 24 hours.")
    max_downloads: int = Field(default=3, ge=1, le=100, description="Maximum downloads allowed for this token.")


class OpenAIFileRef(BaseModel):
    name: Optional[str] = None
    id: Optional[str] = None
    mime_type: Optional[str] = None
    download_link: str


class ImportOpenAIFilesRequest(BaseModel):
    destination_dir: str = Field(default=".", description="Directory where uploaded ChatGPT files are saved.")
    overwrite: bool = True
    openaiFileIdRefs: List[OpenAIFileRef] = Field(default_factory=list, description="Files supplied by ChatGPT Actions at runtime.")


class ExportFilesRequest(BaseModel):
    paths: List[str] = Field(..., description="Up to 10 non-image file paths to return to ChatGPT.")


def parse_mode(mode: str) -> int:
    try:
        return int(str(mode), 8)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid mode: {mode}") from exc


def sanitize_filename(name: str) -> str:
    name = Path(name or "file").name
    name = "".join(ch if ch.isalnum() or ch in "._ -" else "_" for ch in name).strip(" .")
    return name or f"file-{secrets.token_hex(4)}"


def resolve_path(user_path: Optional[str], *, default_to_workdir: bool = False) -> Path:
    if not user_path:
        if default_to_workdir:
            return WORKDIR
        raise HTTPException(status_code=400, detail="path is required")
    if "\x00" in user_path:
        raise HTTPException(status_code=400, detail="path contains NUL byte")

    raw = Path(user_path).expanduser()
    if raw.is_absolute():
        if not ALLOW_ABSOLUTE_PATHS:
            raise HTTPException(status_code=403, detail="absolute paths are disabled")
        return raw.resolve(strict=False)

    resolved = (WORKDIR / raw).resolve(strict=False)
    workdir_str = str(WORKDIR)
    resolved_str = str(resolved)
    if resolved_str != workdir_str and not resolved_str.startswith(workdir_str + os.sep):
        raise HTTPException(status_code=403, detail="relative path escapes SANDBOX_WORKDIR")
    return resolved


def get_cwd(cwd: Optional[str]) -> Path:
    if not cwd:
        return WORKDIR
    path = resolve_path(cwd)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"cwd does not exist: {path}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"cwd is not a directory: {path}")
    return path


def command_to_argv(command: Union[str, List[str]], use_shell: bool) -> List[str]:
    if use_shell:
        if isinstance(command, list):
            command = " ".join(shlex.quote(str(part)) for part in command)
        return [SHELL_BIN, "-lc", str(command)]

    if isinstance(command, list):
        argv = [str(part) for part in command]
    else:
        argv = shlex.split(command)
    if not argv:
        raise HTTPException(status_code=400, detail="empty command")
    return argv


def stdin_bytes(req: ExecRequest) -> Optional[bytes]:
    if req.stdin is not None and req.stdin_base64 is not None:
        raise HTTPException(status_code=400, detail="use either stdin or stdin_base64, not both")
    if req.stdin_base64 is not None:
        try:
            return base64.b64decode(req.stdin_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid stdin_base64") from exc
    if req.stdin is not None:
        return req.stdin.encode("utf-8")
    return None


def process_env(extra: Dict[str, str]) -> Dict[str, str]:
    env = dict(os.environ)
    env.pop("SANDBOX_TOKEN", None)
    for k, v in extra.items():
        env[str(k)] = str(v)
    return env


def bounded_timeout(value: Optional[float], *, background: bool) -> float:
    if value is None:
        value = 900.0 if background else DEFAULT_TIMEOUT
    if value <= 0:
        raise HTTPException(status_code=400, detail="timeout must be > 0")
    if value > MAX_TIMEOUT:
        raise HTTPException(status_code=400, detail=f"timeout exceeds SANDBOX_MAX_TIMEOUT={MAX_TIMEOUT}")
    return value


def read_limited(path: Path, max_bytes: int) -> Dict[str, Any]:
    with path.open("rb") as f:
        if max_bytes == 0:
            data = f.read()
            truncated = False
        else:
            data = f.read(max_bytes + 1)
            truncated = len(data) > max_bytes
            if truncated:
                data = data[:max_bytes]
    return {"text": data.decode("utf-8", errors="replace"), "bytes": len(data), "truncated": truncated}


def run_sync(req: ExecRequest, client: str) -> Dict[str, Any]:
    cwd = get_cwd(req.cwd)
    argv = command_to_argv(req.command, req.shell)
    timeout = bounded_timeout(req.timeout, background=False)
    max_output = MAX_SYNC_OUTPUT_BYTES if req.max_output_bytes is None else int(req.max_output_bytes)
    input_bytes = stdin_bytes(req)
    started = time.time()
    run_id = str(uuid.uuid4())

    with tempfile.NamedTemporaryFile(prefix=f"{APP_NAME}-{run_id}-stdout-", delete=False) as stdout_tmp, \
            tempfile.NamedTemporaryFile(prefix=f"{APP_NAME}-{run_id}-stderr-", delete=False) as stderr_tmp:
        stdout_path = Path(stdout_tmp.name)
        stderr_path = Path(stderr_tmp.name)
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=process_env(req.env),
                stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                stdout=stdout_tmp,
                stderr=stderr_tmp,
                start_new_session=True,
            )
            try:
                if input_bytes is not None:
                    proc.communicate(input=input_bytes, timeout=timeout)
                else:
                    proc.wait(timeout=timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
                proc.wait(timeout=5)

            duration_ms = int((time.time() - started) * 1000)
            stdout_tmp.flush()
            stderr_tmp.flush()
            stdout_data = read_limited(stdout_path, max_output)
            stderr_data = read_limited(stderr_path, max_output)
            result = {
                "id": run_id,
                "pid": proc.pid,
                "command": req.command,
                "shell": req.shell,
                "cwd": str(cwd),
                "returncode": proc.returncode,
                "timed_out": timed_out,
                "duration_ms": duration_ms,
                "stdout": stdout_data["text"],
                "stderr": stderr_data["text"],
                "stdout_bytes": stdout_data["bytes"],
                "stderr_bytes": stderr_data["bytes"],
                "stdout_truncated": stdout_data["truncated"],
                "stderr_truncated": stderr_data["truncated"],
            }
            audit("exec_sync", client=client, id=run_id, cwd=str(cwd), command=req.command,
                  shell=req.shell, returncode=proc.returncode, timed_out=timed_out, duration_ms=duration_ms)
            return result
        except FileNotFoundError as exc:
            audit("exec_error", client=client, id=run_id, command=req.command, error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            for p in (stdout_path, stderr_path):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass


def job_path(job_id: str) -> Path:
    if not job_id or "/" in job_id or ".." in job_id:
        raise HTTPException(status_code=400, detail="invalid job_id")
    return JOB_DIR / job_id


def status_file(job_id: str) -> Path:
    return job_path(job_id) / "status.json"


def load_status(job_id: str) -> Dict[str, Any]:
    sf = status_file(job_id)
    if not sf.exists():
        raise HTTPException(status_code=404, detail="job not found")
    with sf.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_status(job_id: str, status: Dict[str, Any]) -> None:
    jp = job_path(job_id)
    jp.mkdir(parents=True, exist_ok=True)
    tmp = jp / "status.tmp"
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, sort_keys=True, indent=2)
    tmp.replace(jp / "status.json")


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def monitor_job(job_id: str, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    timed_out = False
    rc = None
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        if time.monotonic() > deadline:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            proc.wait(timeout=5)
            rc = proc.returncode
            break
        time.sleep(0.5)

    try:
        status = load_status(job_id)
        status.update({"state": "finished", "returncode": rc, "timed_out": timed_out, "finished_at": utc_now()})
        save_status(job_id, status)
        audit("exec_background_finished", id=job_id, pid=proc.pid, returncode=rc, timed_out=timed_out)
    except Exception as exc:
        audit("job_monitor_error", id=job_id, error=str(exc))


def start_background(req: ExecRequest, client: str) -> Dict[str, Any]:
    cwd = get_cwd(req.cwd)
    argv = command_to_argv(req.command, req.shell)
    timeout = bounded_timeout(req.timeout, background=True)
    input_bytes = stdin_bytes(req)
    job_id = str(uuid.uuid4())
    jp = job_path(job_id)
    jp.mkdir(parents=True, exist_ok=True)
    stdout_path = jp / "stdout.log"
    stderr_path = jp / "stderr.log"
    stdin_path = jp / "stdin.bin"

    stdin_handle = None
    stdout_handle = None
    stderr_handle = None
    try:
        if input_bytes is not None:
            stdin_path.write_bytes(input_bytes)
            stdin_handle = stdin_path.open("rb")
        else:
            stdin_handle = open(os.devnull, "rb")
        stdout_handle = stdout_path.open("ab")
        stderr_handle = stderr_path.open("ab")

        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=process_env(req.env),
            stdin=stdin_handle,
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
        )
        status = {
            "id": job_id,
            "state": "running",
            "pid": proc.pid,
            "command": req.command,
            "shell": req.shell,
            "cwd": str(cwd),
            "timeout": timeout,
            "started_at": utc_now(),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
        save_status(job_id, status)
        audit("exec_background_started", client=client, id=job_id, pid=proc.pid, cwd=str(cwd), command=req.command,
              shell=req.shell)
        thread = threading.Thread(target=monitor_job, args=(job_id, proc, timeout), daemon=True)
        thread.start()
        return {"job_id": job_id, "pid": proc.pid, "state": "running", "status_url": f"/v1/jobs/{job_id}"}
    except FileNotFoundError as exc:
        audit("exec_background_error", client=client, id=job_id, command=req.command, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        for handle in (stdin_handle, stdout_handle, stderr_handle):
            try:
                if handle:
                    handle.close()
            except Exception:
                pass


def load_shares() -> Dict[str, Any]:
    with _share_lock:
        try:
            return json.loads(SHARE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}


def save_shares(data: Dict[str, Any]) -> None:
    with _share_lock:
        tmp = SHARE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(SHARE_FILE)


def cleanup_shares(data: Dict[str, Any]) -> Dict[str, Any]:
    now = time.time()
    return {k: v for k, v in data.items() if float(v.get("expires_at", 0)) > now and int(v.get("remaining", 0)) > 0}


def render_gpt_schema(server_url: str) -> str:
    # Keep endpoint/parameter descriptions short because GPT Actions enforce schema limits.
    consequential = str(ACTION_CONSEQUENTIAL).lower()
    return f"""openapi: 3.1.0
info:
  title: Sandbox GPT Agent
  version: {APP_VERSION}
  description: Command, file, job and artifact control plane for a controlled technology environment.
servers:
  - url: {server_url}
security:
  - bearerAuth: []
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    ExecRequest:
      type: object
      required: [command]
      properties:
        command:
          oneOf:
            - type: string
            - type: array
              items: {{ type: string }}
        cwd: {{ type: string }}
        env:
          type: object
          additionalProperties: {{ type: string }}
        stdin: {{ type: string }}
        stdin_base64: {{ type: string }}
        timeout: {{ type: number }}
        shell: {{ type: boolean, default: true }}
        background: {{ type: boolean, default: false }}
        max_output_bytes: {{ type: integer }}
    WriteFileRequest:
      type: object
      required: [path, content]
      properties:
        path: {{ type: string }}
        content: {{ type: string }}
        encoding:
          type: string
          enum: [text, base64]
          default: text
        append: {{ type: boolean, default: false }}
        mode: {{ type: string }}
    MkdirRequest:
      type: object
      required: [path]
      properties:
        path: {{ type: string }}
        parents: {{ type: boolean, default: true }}
        exist_ok: {{ type: boolean, default: true }}
        mode: {{ type: string, default: '0755' }}
    ChmodRequest:
      type: object
      required: [path, mode]
      properties:
        path: {{ type: string }}
        mode: {{ type: string }}
    FetchUrlRequest:
      type: object
      required: [url, path]
      properties:
        url: {{ type: string }}
        path: {{ type: string }}
        method: {{ type: string, enum: [GET, POST, PUT, PATCH], default: GET }}
        headers:
          type: object
          additionalProperties: {{ type: string }}
        body: {{ type: string }}
        body_base64: {{ type: string }}
        timeout: {{ type: number, default: 30 }}
        mode: {{ type: string }}
    ImportOpenAIFilesRequest:
      type: object
      properties:
        destination_dir: {{ type: string, default: '.' }}
        overwrite: {{ type: boolean, default: true }}
        openaiFileIdRefs:
          type: array
          description: ChatGPT runtime file references with download links.
          items:
            type: object
            additionalProperties: true
    ExportFilesRequest:
      type: object
      required: [paths]
      properties:
        paths:
          type: array
          maxItems: 10
          items: {{ type: string }}
    ShareFileRequest:
      type: object
      required: [path]
      properties:
        path: {{ type: string }}
        ttl_seconds: {{ type: integer, default: 3600, minimum: 60, maximum: 86400 }}
        max_downloads: {{ type: integer, default: 3, minimum: 1, maximum: 100 }}
paths:
  /health:
    get:
      operationId: healthCheck
      x-openai-isConsequential: false
      summary: Check agent health.
      security: []
      responses:
        '200': {{ description: OK }}
  /v1/sys/info:
    get:
      operationId: getSystemInfo
      x-openai-isConsequential: false
      summary: Get agent environment metadata.
      responses:
        '200': {{ description: Environment metadata. }}
  /v1/exec:
    post:
      operationId: runCommand
      x-openai-isConsequential: {consequential}
      summary: Run a Linux command.
      description: Runs a command. Use background=true for tasks near 45 seconds.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ExecRequest'
      responses:
        '200': {{ description: Command result or job id. }}
  /v1/jobs:
    get:
      operationId: listJobs
      x-openai-isConsequential: false
      summary: List recent background jobs.
      parameters:
        - name: limit
          in: query
          schema: {{ type: integer, default: 50 }}
      responses:
        '200': {{ description: Jobs. }}
  /v1/jobs/{{job_id}}:
    get:
      operationId: getJob
      x-openai-isConsequential: false
      summary: Get job status and log tails.
      parameters:
        - name: job_id
          in: path
          required: true
          schema: {{ type: string }}
        - name: tail_bytes
          in: query
          schema: {{ type: integer, default: 20000 }}
      responses:
        '200': {{ description: Job status. }}
    delete:
      operationId: killJob
      x-openai-isConsequential: {consequential}
      summary: Terminate a background job.
      parameters:
        - name: job_id
          in: path
          required: true
          schema: {{ type: string }}
        - name: force
          in: query
          schema: {{ type: boolean, default: false }}
      responses:
        '200': {{ description: Kill result. }}
  /v1/files/list:
    get:
      operationId: listFiles
      x-openai-isConsequential: false
      summary: List files in a directory.
      parameters:
        - name: path
          in: query
          schema: {{ type: string }}
        - name: all
          in: query
          schema: {{ type: boolean, default: true }}
      responses:
        '200': {{ description: Directory entries. }}
  /v1/files/stat:
    get:
      operationId: statFile
      x-openai-isConsequential: false
      summary: Get file metadata.
      parameters:
        - name: path
          in: query
          required: true
          schema: {{ type: string }}
      responses:
        '200': {{ description: File metadata. }}
  /v1/files/read:
    get:
      operationId: readFile
      x-openai-isConsequential: false
      summary: Read a text or base64 file chunk.
      parameters:
        - name: path
          in: query
          required: true
          schema: {{ type: string }}
        - name: offset
          in: query
          schema: {{ type: integer, default: 0 }}
        - name: max_bytes
          in: query
          schema: {{ type: integer, default: 65536 }}
        - name: encoding
          in: query
          schema: {{ type: string, enum: [text, base64], default: text }}
      responses:
        '200': {{ description: File chunk. }}
  /v1/files/write:
    post:
      operationId: writeFile
      x-openai-isConsequential: {consequential}
      summary: Write or append a file.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/WriteFileRequest'
      responses:
        '200': {{ description: Write result. }}
  /v1/files/mkdir:
    post:
      operationId: makeDirectory
      x-openai-isConsequential: {consequential}
      summary: Create a directory.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/MkdirRequest'
      responses:
        '200': {{ description: Directory result. }}
  /v1/files/chmod:
    post:
      operationId: chmodFile
      x-openai-isConsequential: {consequential}
      summary: Change file permissions.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ChmodRequest'
      responses:
        '200': {{ description: Chmod result. }}
  /v1/files/fetch-url:
    post:
      operationId: fetchUrlToFile
      x-openai-isConsequential: {consequential}
      summary: Download a URL to a file.
      description: Fetches HTTP/HTTPS content and saves it in the workspace.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FetchUrlRequest'
      responses:
        '200': {{ description: Fetch result. }}
  /v1/files:
    delete:
      operationId: deleteFile
      x-openai-isConsequential: {consequential}
      summary: Delete a file or directory.
      parameters:
        - name: path
          in: query
          required: true
          schema: {{ type: string }}
        - name: recursive
          in: query
          schema: {{ type: boolean, default: false }}
      responses:
        '200': {{ description: Delete result. }}
  /v1/files/import-openai:
    post:
      operationId: importOpenAIConversationFiles
      x-openai-isConsequential: {consequential}
      summary: Save files uploaded in ChatGPT.
      description: Downloads openaiFileIdRefs and saves them in the workspace.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ImportOpenAIFilesRequest'
      responses:
        '200': {{ description: Imported files. }}
  /v1/files/export:
    post:
      operationId: returnFilesToChatGPT
      x-openai-isConsequential: false
      summary: Return non-image files to ChatGPT.
      description: Returns up to 10 non-image files with openaiFileResponse.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ExportFilesRequest'
      responses:
        '200': {{ description: openaiFileResponse. }}
  /v1/files/share:
    post:
      operationId: shareFile
      x-openai-isConsequential: {consequential}
      summary: Create a temporary public file link.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ShareFileRequest'
      responses:
        '200': {{ description: Public download URL. }}
  /v1/audit/tail:
    get:
      operationId: tailAuditLog
      x-openai-isConsequential: false
      summary: Read recent audit events.
      parameters:
        - name: lines
          in: query
          schema: {{ type: integer, default: 100 }}
      responses:
        '200': {{ description: Audit log lines. }}
"""


@app.get("/health", operation_id="healthCheck")
def health() -> Dict[str, Any]:
    return {"ok": True, "app": APP_NAME, "version": APP_VERSION, "time": utc_now()}


@app.get("/privacy", response_class=PlainTextResponse, operation_id="privacyPolicy")
def privacy() -> str:
    return (
        "Sandbox GPT Agent Privacy Notice\n\n"
        "This endpoint is for a private controlled technology environment operated by its owner. "
        "Requests sent to this service may include commands, file paths, file contents, "
        "environment values, and task context needed to operate that environment. "
        "The service writes an audit log locally. It does not sell data or intentionally "
        "share data with third parties. Temporary signed download links may expose selected "
        "files to anyone who has the link until expiry or download limit. "
        f"Contact: {PRIVACY_CONTACT}.\n"
    )


@app.get("/gpt-action-openapi.yaml", response_class=PlainTextResponse, operation_id="getGptActionSchema")
def gpt_action_openapi(request: Request) -> str:
    return render_gpt_schema(base_url_from_request(request))


@app.get("/v1/sys/info", operation_id="getSystemInfo")
def sys_info() -> Dict[str, Any]:
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "time": utc_now(),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "user": getpass.getuser(),
        "uid": os.geteuid() if hasattr(os, "geteuid") else None,
        "gid": os.getegid() if hasattr(os, "getegid") else None,
        "workdir": str(WORKDIR),
        "state_dir": str(STATE_DIR),
        "log_file": str(LOG_FILE),
        "allow_absolute_paths": ALLOW_ABSOLUTE_PATHS,
        "shell": SHELL_BIN,
        "public_base_url": PUBLIC_BASE_URL or None,
        "action_consequential": ACTION_CONSEQUENTIAL,
        "limits": {
            "max_import_file_bytes": MAX_IMPORT_FILE_BYTES,
            "max_export_file_bytes": MAX_EXPORT_FILE_BYTES,
            "max_read_bytes": MAX_READ_BYTES,
            "max_sync_output_bytes": MAX_SYNC_OUTPUT_BYTES,
        },
    }


@app.post("/v1/exec", operation_id="runCommand")
def exec_command(req: ExecRequest, request: Request) -> Dict[str, Any]:
    client = client_ip(request)
    if req.background:
        return start_background(req, client)
    return run_sync(req, client)


@app.get("/v1/jobs", operation_id="listJobs")
def list_jobs(limit: int = 50) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    items: List[Dict[str, Any]] = []
    for p in sorted(JOB_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_dir():
            continue
        try:
            with (p / "status.json").open("r", encoding="utf-8") as f:
                items.append(json.load(f))
        except Exception:
            continue
        if len(items) >= limit:
            break
    return {"jobs": items}


@app.get("/v1/jobs/{job_id}", operation_id="getJob")
def get_job(job_id: str, tail_bytes: int = 20000) -> Dict[str, Any]:
    tail_bytes = max(0, min(int(tail_bytes), 80000))
    status = load_status(job_id)
    pid = status.get("pid")
    if status.get("state") == "running" and isinstance(pid, int) and not pid_alive(pid):
        status["state"] = "unknown_finished_after_agent_restart"
        status["finished_at"] = utc_now()
        save_status(job_id, status)

    jp = job_path(job_id)
    stdout_path = jp / "stdout.log"
    stderr_path = jp / "stderr.log"

    def tail(path: Path) -> str:
        if not path.exists():
            return ""
        with path.open("rb") as f:
            if tail_bytes > 0:
                try:
                    f.seek(-tail_bytes, os.SEEK_END)
                except OSError:
                    f.seek(0)
            data = f.read()
        return data.decode("utf-8", errors="replace")

    status["stdout_tail"] = tail(stdout_path)
    status["stderr_tail"] = tail(stderr_path)
    return status


@app.delete("/v1/jobs/{job_id}", operation_id="killJob")
def kill_job(job_id: str, force: bool = False) -> Dict[str, Any]:
    status = load_status(job_id)
    pid = status.get("pid")
    if not isinstance(pid, int):
        raise HTTPException(status_code=400, detail="job has no pid")
    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    status["state"] = "killed" if force else "terminated"
    status["finished_at"] = utc_now()
    save_status(job_id, status)
    audit("job_killed", id=job_id, pid=pid, force=force)
    return {"ok": True, "job_id": job_id, "pid": pid, "signal": sig.name}


@app.get("/v1/files/stat", operation_id="statFile")
def file_stat(path: str) -> Dict[str, Any]:
    p = resolve_path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    st = p.stat()
    return {
        "path": str(p),
        "exists": True,
        "is_file": p.is_file(),
        "is_dir": p.is_dir(),
        "size": st.st_size,
        "mode": oct(st.st_mode & 0o7777),
        "mtime": st.st_mtime,
        "owner_uid": st.st_uid,
        "owner_gid": st.st_gid,
    }


@app.get("/v1/files/list", operation_id="listFiles")
def list_files(path: Optional[str] = None, all: bool = True) -> Dict[str, Any]:
    p = resolve_path(path or str(WORKDIR), default_to_workdir=True)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")
    entries = []
    for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        if not all and child.name.startswith("."):
            continue
        try:
            st = child.stat()
            entries.append({
                "name": child.name,
                "path": str(child),
                "is_file": child.is_file(),
                "is_dir": child.is_dir(),
                "size": st.st_size,
                "mode": oct(st.st_mode & 0o7777),
                "mtime": st.st_mtime,
            })
        except OSError as exc:
            entries.append({"name": child.name, "path": str(child), "error": str(exc)})
    return {"path": str(p), "entries": entries}


@app.post("/v1/files/mkdir", operation_id="makeDirectory")
def mkdir(req: MkdirRequest) -> Dict[str, Any]:
    p = resolve_path(req.path)
    p.mkdir(mode=parse_mode(req.mode), parents=req.parents, exist_ok=req.exist_ok)
    audit("mkdir", path=str(p))
    return {"ok": True, "path": str(p)}


@app.post("/v1/files/write", operation_id="writeFile")
def write_file(req: WriteFileRequest) -> Dict[str, Any]:
    p = resolve_path(req.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if req.encoding == "base64":
        try:
            data = base64.b64decode(req.content)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid base64 content") from exc
    elif req.encoding == "text":
        data = req.content.encode("utf-8")
    else:
        raise HTTPException(status_code=400, detail="encoding must be text or base64")
    mode = "ab" if req.append else "wb"
    with p.open(mode) as f:
        f.write(data)
    if req.mode:
        p.chmod(parse_mode(req.mode))
    audit("write_file", path=str(p), bytes=len(data), append=req.append)
    return {"ok": True, "path": str(p), "bytes": len(data)}


@app.put("/v1/files/raw", operation_id="rawUpload")
async def raw_upload(path: str, request: Request, mode: Optional[str] = None) -> Dict[str, Any]:
    # Not included in the GPT Action schema because Actions are text-only. Useful for curl/Postman.
    p = resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp-{uuid.uuid4()}")
    written = 0
    try:
        with tmp.open("wb") as f:
            async for chunk in request.stream():
                if chunk:
                    written += len(chunk)
                    f.write(chunk)
        tmp.replace(p)
        if mode:
            p.chmod(parse_mode(mode))
        audit("raw_upload", path=str(p), bytes=written)
        return {"ok": True, "path": str(p), "bytes": written}
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/v1/files/read", operation_id="readFile")
def read_file(path: str, offset: int = 0, max_bytes: int = 65536, encoding: str = "text") -> Dict[str, Any]:
    p = resolve_path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    if not p.is_file():
        raise HTTPException(status_code=400, detail="path is not a file")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")
    max_bytes = min(max(int(max_bytes), 0), MAX_READ_BYTES)
    with p.open("rb") as f:
        f.seek(offset)
        if max_bytes == 0:
            data = f.read()
        else:
            data = f.read(max_bytes)
    if encoding == "base64":
        content = base64.b64encode(data).decode("ascii")
    elif encoding == "text":
        content = data.decode("utf-8", errors="replace")
    else:
        raise HTTPException(status_code=400, detail="encoding must be text or base64")
    return {"path": str(p), "offset": offset, "bytes": len(data), "encoding": encoding, "content": content}


@app.get("/v1/files/download", operation_id="downloadFile")
def download_file(path: str):
    # Not in GPT Action schema; use shareFile for GPT-friendly links.
    p = resolve_path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    if not p.is_file():
        raise HTTPException(status_code=400, detail="path is not a file")
    media_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    return FileResponse(path=str(p), media_type=media_type, filename=p.name)


@app.delete("/v1/files", operation_id="deleteFile")
def delete_path(path: str, recursive: bool = False) -> Dict[str, Any]:
    p = resolve_path(path)
    if not p.exists():
        return {"ok": True, "path": str(p), "deleted": False, "reason": "not_found"}
    if p.is_dir():
        if not recursive:
            raise HTTPException(status_code=400, detail="path is a directory; set recursive=true")
        shutil.rmtree(p)
    else:
        p.unlink()
    audit("delete_path", path=str(p), recursive=recursive)
    return {"ok": True, "path": str(p), "deleted": True}


@app.post("/v1/files/chmod", operation_id="chmodFile")
def chmod(req: ChmodRequest) -> Dict[str, Any]:
    p = resolve_path(req.path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    mode = parse_mode(req.mode)
    p.chmod(mode)
    audit("chmod", path=str(p), mode=req.mode)
    return {"ok": True, "path": str(p), "mode": oct(mode)}


@app.post("/v1/files/fetch-url", operation_id="fetchUrlToFile")
def fetch_url_to_file(req: FetchUrlRequest) -> Dict[str, Any]:
    method = req.method.upper().strip()
    if method not in {"GET", "POST", "PUT", "PATCH"}:
        raise HTTPException(status_code=400, detail="method must be GET, POST, PUT, or PATCH")
    if req.body is not None and req.body_base64 is not None:
        raise HTTPException(status_code=400, detail="use body or body_base64, not both")
    body: Optional[bytes] = None
    if req.body is not None:
        body = req.body.encode("utf-8")
    elif req.body_base64 is not None:
        try:
            body = base64.b64decode(req.body_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid body_base64") from exc

    p = resolve_path(req.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp-{uuid.uuid4()}")
    written = 0
    try:
        with httpx.stream(method, req.url, headers=req.headers, content=body, follow_redirects=True, timeout=req.timeout) as response:
            response.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > MAX_IMPORT_FILE_BYTES:
                        raise HTTPException(status_code=413, detail=f"download exceeds {MAX_IMPORT_FILE_BYTES} bytes")
                    f.write(chunk)
        tmp.replace(p)
        if req.mode:
            p.chmod(parse_mode(req.mode))
        audit("fetch_url", url=req.url, path=str(p), bytes=written)
        return {"ok": True, "path": str(p), "bytes": written}
    except HTTPException:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"fetch failed: {exc}") from exc


@app.post("/v1/files/import-openai", operation_id="importOpenAIConversationFiles")
def import_openai_files(req: ImportOpenAIFilesRequest) -> Dict[str, Any]:
    dest_dir = resolve_path(req.destination_dir or ".", default_to_workdir=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if len(req.openaiFileIdRefs) > 10:
        raise HTTPException(status_code=400, detail="openaiFileIdRefs supports up to 10 files")
    saved: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for ref in req.openaiFileIdRefs:
        filename = sanitize_filename(ref.name or ref.id or "file")
        dest = dest_dir / filename
        if dest.exists() and not req.overwrite:
            errors.append({"name": filename, "error": "exists"})
            continue
        tmp = dest.with_name(dest.name + f".tmp-{uuid.uuid4()}")
        written = 0
        try:
            with httpx.stream("GET", ref.download_link, follow_redirects=True, timeout=30.0) as response:
                response.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > MAX_IMPORT_FILE_BYTES:
                            raise HTTPException(status_code=413, detail=f"file exceeds {MAX_IMPORT_FILE_BYTES} bytes")
                        f.write(chunk)
            tmp.replace(dest)
            saved.append({"name": filename, "path": str(dest), "bytes": written, "mime_type": ref.mime_type, "id": ref.id})
        except HTTPException:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            errors.append({"name": filename, "error": str(exc)})
    audit("import_openai_files", destination=str(dest_dir), saved=len(saved), errors=len(errors))
    return {"ok": len(errors) == 0, "destination_dir": str(dest_dir), "saved": saved, "errors": errors}


@app.post("/v1/files/export", operation_id="returnFilesToChatGPT")
def export_files(req: ExportFilesRequest) -> Dict[str, Any]:
    if len(req.paths) > 10:
        raise HTTPException(status_code=400, detail="can export up to 10 files")
    files: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for user_path in req.paths:
        p = resolve_path(user_path)
        if not p.exists() or not p.is_file():
            skipped.append({"path": str(p), "reason": "not_file"})
            continue
        size = p.stat().st_size
        if size > MAX_EXPORT_FILE_BYTES:
            skipped.append({"path": str(p), "reason": f"too_large:{size}"})
            continue
        mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        if mime.startswith("image/") or mime.startswith("video/"):
            skipped.append({"path": str(p), "reason": f"mime_not_supported_by_openaiFileResponse:{mime}"})
            continue
        files.append({"name": p.name, "mime_type": mime, "content": base64.b64encode(p.read_bytes()).decode("ascii")})
    audit("export_files", requested=len(req.paths), returned=len(files), skipped=len(skipped))
    return {"openaiFileResponse": files, "skipped": skipped}


@app.post("/v1/files/share", operation_id="shareFile")
def share_file(req: ShareFileRequest, request: Request) -> Dict[str, Any]:
    p = resolve_path(req.path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    if not p.is_file():
        raise HTTPException(status_code=400, detail="path is not a file")
    token = secrets.token_urlsafe(32)
    now = time.time()
    shares = cleanup_shares(load_shares())
    shares[token] = {
        "path": str(p),
        "created_at": now,
        "expires_at": now + int(req.ttl_seconds),
        "remaining": int(req.max_downloads),
        "filename": p.name,
    }
    save_shares(shares)
    url = f"{base_url_from_request(request)}/public/download/{token}"
    audit("share_file", path=str(p), ttl_seconds=req.ttl_seconds, max_downloads=req.max_downloads)
    return {"ok": True, "path": str(p), "url": url, "expires_at": shares[token]["expires_at"], "remaining": shares[token]["remaining"]}


@app.get("/public/download/{token}", operation_id="publicDownload")
def public_download(token: str):
    shares = cleanup_shares(load_shares())
    item = shares.get(token)
    if not item:
        save_shares(shares)
        raise HTTPException(status_code=404, detail="not found or expired")
    p = Path(item["path"])
    if not p.exists() or not p.is_file():
        shares.pop(token, None)
        save_shares(shares)
        raise HTTPException(status_code=404, detail="file not found")
    item["remaining"] = int(item.get("remaining", 0)) - 1
    if item["remaining"] <= 0:
        shares.pop(token, None)
    else:
        shares[token] = item
    save_shares(shares)
    audit("public_download", path=str(p), token_prefix=token[:8])
    media_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    return FileResponse(path=str(p), media_type=media_type, filename=item.get("filename") or p.name)


@app.get("/v1/audit/tail", operation_id="tailAuditLog")
def audit_tail(lines: int = 100) -> Dict[str, Any]:
    lines = max(1, min(int(lines), 1000))
    if not LOG_FILE.exists():
        return {"log_file": str(LOG_FILE), "lines": []}
    with LOG_FILE.open("r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()[-lines:]
    return {"log_file": str(LOG_FILE), "lines": [line.rstrip("\n") for line in all_lines]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("agent:app", host=BIND, port=PORT, reload=False)

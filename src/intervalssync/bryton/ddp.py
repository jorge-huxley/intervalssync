"""Meteor DDP login and activity listing for Bryton Active."""
from __future__ import annotations

import hashlib
import json
import random
import string
import threading
from dataclasses import dataclass
from typing import Any

import requests

from .exceptions import BrytonAuthError, BrytonDDPError

DEFAULT_HOST = "m3.brytonactive.com"
WEB_HOST = "active.brytonsport.com"
DDP_CONNECT = {"msg": "connect", "version": "1", "support": ["1", "pre2", "pre1"]}


@dataclass(frozen=True)
class BrytonSession:
    user_id: str
    auth_token: str
    host: str = DEFAULT_HOST


class _DDPClient:
    """Minimal synchronous Meteor DDP over SockJS/WebSocket."""

    def __init__(self, host: str, *, timeout: float = 30.0) -> None:
        self.host = host
        self.timeout = timeout
        self._ws = None
        self._msg_id = 0
        self._pending: dict[str, threading.Event] = {}
        self._results: dict[str, tuple[Any, Any]] = {}
        self._connected = threading.Event()
        self._subs_ready: dict[str, threading.Event] = {}
        self._collections: dict[str, dict[str, dict[str, Any]]] = {}
        self._thread: threading.Thread | None = None

    def _next_id(self) -> str:
        self._msg_id += 1
        return str(self._msg_id)

    @staticmethod
    def _sockjs_url(host: str) -> str:
        requests.get(f"https://{host}/sockjs/info", timeout=20).raise_for_status()
        server = str(random.randint(100, 999))
        session = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"wss://{host}/sockjs/{server}/{session}/websocket"

    def _send(self, payload: dict[str, Any]) -> None:
        frame = json.dumps([json.dumps(payload)])
        self._ws.send(frame)

    def _on_message(self, _ws: Any, message: str) -> None:
        if message == "o":
            self._send(DDP_CONNECT)
            return
        if message == "h":
            return
        if message.startswith("a"):
            for item in json.loads(message[1:]):
                self._handle(json.loads(item))

    def _handle(self, msg: dict[str, Any]) -> None:
        kind = msg.get("msg")
        if kind == "connected":
            self._connected.set()
            return
        if kind == "failed":
            raise BrytonDDPError(f"DDP connect failed: {msg.get('reason', msg)}")
        if kind == "result":
            req_id = msg.get("id")
            if req_id in self._pending:
                self._results[req_id] = (msg.get("error"), msg.get("result"))
                self._pending[req_id].set()
            return
        if kind == "added":
            coll = msg["collection"]
            self._collections.setdefault(coll, {})[msg["id"]] = dict(msg.get("fields", {}))
            return
        if kind == "ready":
            for sub_id in msg.get("subs", []):
                ready = self._subs_ready.get(sub_id)
                if ready:
                    ready.set()
            return
        if kind == "nosub":
            raise BrytonDDPError(f"Subscription failed: {msg.get('id')} {msg}")
        if kind == "removed":
            coll = msg["collection"]
            self._collections.get(coll, {}).pop(msg["id"], None)
            return
        if kind == "changed":
            coll = msg["collection"]
            doc = self._collections.setdefault(coll, {}).setdefault(msg["id"], {})
            doc.update(msg.get("fields", {}))
            for key in msg.get("unset", {}):
                doc.pop(key, None)

    def connect(self) -> None:
        try:
            import websocket  # type: ignore[import-untyped]
        except ImportError as exc:
            raise BrytonDDPError(
                "websocket-client is required: uv pip install websocket-client"
            ) from exc

        url = self._sockjs_url(self.host)
        self._ws = websocket.WebSocketApp(url, on_message=self._on_message)
        self._thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 20, "ping_timeout": 10},
            daemon=True,
        )
        self._thread.start()
        if not self._connected.wait(self.timeout):
            raise BrytonDDPError(f"DDP connect timed out ({self.host})")

    def call(self, method: str, params: list[Any]) -> Any:
        req_id = self._next_id()
        event = threading.Event()
        self._pending[req_id] = event
        self._send({"msg": "method", "method": method, "params": params, "id": req_id})
        if not event.wait(self.timeout):
            raise BrytonDDPError(f"DDP method timed out: {method}")
        error, result = self._results.pop(req_id)
        self._pending.pop(req_id, None)
        if error:
            reason = error.get("reason") or error.get("message") or str(error)
            if method == "login":
                raise BrytonAuthError(reason)
            raise BrytonDDPError(f"{method}: {reason}")
        return result

    def subscribe(self, name: str, params: list[Any] | None = None) -> None:
        req_id = self._next_id()
        ready = threading.Event()
        self._subs_ready[req_id] = ready
        self._send(
            {
                "msg": "sub",
                "id": req_id,
                "name": name,
                "params": params or [],
            }
        )
        if not ready.wait(self.timeout):
            raise BrytonDDPError(f"Subscription timed out: {name}")
        self._subs_ready.pop(req_id, None)

    def close(self) -> None:
        if self._ws:
            self._ws.close()


def _password_digest(password: str) -> dict[str, str]:
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return {"digest": digest, "algorithm": "sha-256"}


def login(email: str, password: str, *, host: str = DEFAULT_HOST) -> BrytonSession:
    """Log in with Bryton Active email/password."""
    client = _DDPClient(host)
    try:
        client.connect()
        result = client.call(
            "login",
            [{"user": {"email": email}, "password": _password_digest(password)}],
        )
    finally:
        client.close()

    if not isinstance(result, dict) or not result.get("id") or not result.get("token"):
        raise BrytonAuthError(f"Unexpected login response: {result!r}")

    return BrytonSession(
        user_id=result["id"],
        auth_token=result["token"],
        host=host,
    )


def _is_deleted_activity(fields: dict[str, Any]) -> bool:
    if fields.get("_deleted"):
        return True
    label = fields.get("name") or fields.get("title") or ""
    return label == "_deleted"


def call_method(
    session: BrytonSession,
    method: str,
    params: list[Any] | None = None,
    *,
    timeout: float = 60,
) -> Any:
    """Resume-login and invoke a Meteor DDP method."""
    client = _DDPClient(session.host, timeout=timeout)
    try:
        client.connect()
        client.call("login", [{"resume": session.auth_token}])
        return client.call(method, params or [])
    finally:
        client.close()


def list_activities(
    session: BrytonSession,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return recent activities from the activityList subscription."""
    client = _DDPClient(session.host, timeout=60)
    try:
        client.connect()
        client.call("login", [{"resume": session.auth_token}])
        client.subscribe("activityList", [])
        docs = client._collections.get("userActivities", {})
        activities = [
            {"_id": doc_id, **fields}
            for doc_id, fields in docs.items()
            if not _is_deleted_activity(fields)
        ]
        activities.sort(key=lambda a: a.get("local_start_time", 0), reverse=True)
        return activities[:limit]
    finally:
        client.close()

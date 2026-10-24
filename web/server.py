#!/usr/bin/env python3
"""Local manual-control service. Explicit --simulate or --execute starts a server."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web

from .control import ControlError, Controller, DeviceWorker
from .serial_client import ManualClient, SerialTransport, SimulatedDevice, verify_manifest

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = web.AppKey("controller", Controller)
WORKER = web.AppKey("worker", DeviceWorker)
SOCKETS = web.AppKey("sockets", set)
TOKEN = web.AppKey("token", str)
HOSTS = web.AppKey("hosts", set)


class SessionLog:
    def __init__(self, path):
        self.stream, self.lock = Path(path).open("x", encoding="utf-8"), threading.Lock()

    def event(self, event, **fields):
        with self.lock:
            self.stream.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(),
                                          "event": event, **fields}) + "\n")
            self.stream.flush()

    def close(self):
        with self.lock:
            self.stream.flush()
            os.fsync(self.stream.fileno())
            self.stream.close()


def same_origin(request):
    origin = request.headers.get("Origin")
    if not origin:
        return False
    try:
        parsed = urlsplit(origin)
        expected = urlsplit(f"{request.scheme}://{request.host}")
        return (parsed.scheme == expected.scheme and parsed.hostname == expected.hostname
                and (parsed.port or (443 if parsed.scheme == "https" else 80))
                == (expected.port or (443 if expected.scheme == "https" else 80))
                and not parsed.username and not parsed.password and parsed.path in ("", "/")
                and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def permitted_host(request):
    try:
        parsed = urlsplit(f"{request.scheme}://{request.host}")
        local = request.transport.get_extra_info("sockname")
        if not local or parsed.username or parsed.password or parsed.path:
            return False
        if (parsed.port or (443 if request.scheme == "https" else 80)) != local[1]:
            return False
        hostname = (parsed.hostname or "").lower()
        if hostname in {"localhost", *request.app[HOSTS]}:
            return True
        return ipaddress.ip_address(hostname) == ipaddress.ip_address(local[0].split("%")[0])
    except (ValueError, TypeError):
        return False


@web.middleware
async def security(request, handler):
    if not permitted_host(request):
        raise web.HTTPForbidden(text="Host not permitted")
    if request.headers.get("Origin") and not same_origin(request):
        raise web.HTTPForbidden(text="Origin not permitted")
    response = await handler(request)
    if not response.prepared:
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                 "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"})
    return response


async def status(request):
    return web.json_response(request.app[CONTROLLER].snapshot())


async def index(_):
    return web.FileResponse(Path(__file__).parent / "static/index.html")


async def websocket(request):
    if not same_origin(request):
        raise web.HTTPForbidden(text="A matching Origin is required")
    ws = web.WebSocketResponse(heartbeat=10, timeout=.2, max_msg_size=1024, compress=False)
    await ws.prepare(request)
    owner, controller = secrets.token_hex(16), request.app[CONTROLLER]
    request.app[SOCKETS].add(ws)
    producer = None
    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=2)
        if not isinstance(hello, dict) or hello.get("type") != "hello" or not isinstance(hello.get("token"), str):
            raise ControlError("Se requiere autenticación de esta sesión.")
        if not secrets.compare_digest(hello["token"], request.app[TOKEN]):
            raise ControlError("La clave de sesión no es válida.")
        controller.claim(owner)
        await ws.send_json({"type": "hello", "ok": True, "controller": True})

        async def publish():
            try:
                while not ws.closed:
                    await asyncio.wait_for(ws.send_json(controller.snapshot(owner)), timeout=.15)
                    await asyncio.sleep(.05)
            except (ConnectionError, asyncio.TimeoutError, RuntimeError):
                controller.release(owner, "status_stream_error")
                await ws.close(code=1001)

        producer = asyncio.create_task(publish())
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                if message.type in (WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSED):
                    break
                raise ControlError("Solo se aceptan mensajes JSON de control.")
            value = json.loads(message.data)
            if not isinstance(value, dict):
                raise ControlError("Mensaje de control no válido.")
            controller.command(owner, value)
            await asyncio.wait_for(ws.send_json({"type": "ack", "action": value["type"], "seq": value["seq"]}), .15)
    except (ControlError, ValueError, TypeError, asyncio.TimeoutError) as exc:
        controller.release(owner, "protocol_or_auth_error")
        if not ws.closed:
            with suppress(ConnectionError, asyncio.TimeoutError):
                await asyncio.wait_for(ws.send_json({"type": "error", "code": "control_rejected", "message": str(exc)}), .15)
    finally:
        controller.release(owner)
        if producer is not None:
            producer.cancel()
            with suppress(asyncio.CancelledError, ConnectionError, asyncio.TimeoutError):
                await producer
        request.app[SOCKETS].discard(ws)
        await ws.close(code=1008)
    return ws


def create_app(*, token, device_factory=None, simulated=True, controller=None, allowed_hosts=()):
    controller = controller or Controller(simulated=simulated)
    worker = DeviceWorker(controller, device_factory or SimulatedDevice)
    app = web.Application(middlewares=[security], client_max_size=1024)
    app[CONTROLLER], app[WORKER], app[SOCKETS] = controller, worker, set()
    app[TOKEN], app[HOSTS] = token, {host.lower() for host in allowed_hosts}
    app.router.add_get("/api/status", status)
    app.router.add_get("/ws", websocket)
    app.router.add_get("/", index)
    app.router.add_static("/static/", Path(__file__).parent / "static", show_index=False, follow_symlinks=False)

    async def startup(_):
        worker.start()

    async def shutdown(_):
        for ws in tuple(app[SOCKETS]):
            await ws.close(code=1001, message=b"Server shutting down")

    async def cleanup(_):
        await asyncio.to_thread(worker.close)

    app.on_startup.append(startup)
    app.on_shutdown.append(shutdown)
    app.on_cleanup.append(cleanup)
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--simulate", action="store_true", help="Serve a simulator; never import/open serial.")
    mode.add_argument("--execute", action="store_true", help="Enable the explicit verified real serial device.")
    parser.add_argument("--serial-port")
    parser.add_argument("--manifest", type=Path, default=ROOT / "firmware/manual-hold/build/manifest.json")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-host", action="append", default=[], help="Additional local DNS name; never an Origin wildcard.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".local/web")
    args = parser.parse_args(argv)
    if not args.simulate and not args.execute:
        print(json.dumps({"dry_run": True, "server_not_started": True, "serial_not_opened": True,
                          "bind": args.bind, "port": args.port}))
        return 0
    if args.execute:
        if not args.serial_port:
            parser.error("--execute requires --serial-port")
        verify_manifest(args.manifest, args.manifest_sha256)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    session = args.data_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4))
    session.mkdir(mode=0o700)
    token = secrets.token_urlsafe(32)
    descriptor = os.open(session / "token.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(token + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    journal = SessionLog(session / "events.jsonl")
    factory = SimulatedDevice
    if args.execute:
        factory = lambda: ManualClient(SerialTransport.open(args.serial_port, journal))
    app = create_app(token=token, device_factory=factory, simulated=args.simulate, allowed_hosts=args.allow_host)
    display_host = "127.0.0.1" if args.bind in ("0.0.0.0", "::") else args.bind
    print(f"Local control ({'SIMULATOR' if args.simulate else 'REAL'}): http://{display_host}:{args.port}/#token={token}", flush=True)
    print(f"Session files: {session}", flush=True)
    try:
        web.run_app(app, host=args.bind, port=args.port, access_log=None, print=None)
    finally:
        journal.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

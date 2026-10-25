#!/usr/bin/env python3
"""Read H60 profile-6 status: offline serial plan or read-only local HTTP."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

# Allow `python examples/h60_status.py` without installing this repository.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.transport import HostError, valid_port
from web.serial_client import ManualClient, SerialTransport, verify_manifest


class StatusError(RuntimeError):
    pass


class SummaryJournal:
    """No files or raw wire frames: STATUS carries a private boot nonce."""

    def event(self, name, **fields):
        pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        raise StatusError("El servidor ha redirigido la consulta; no se seguirá otra dirección.")


STATUS_FIELDS = {
    "state", "state_id", "flags", "uptime_ms", "firmware_lease_ms", "encoders",
    "burst_count", "reason", "direction_value", "burst_remaining_ms", "all_low",
    "connected", "ready", "moving", "held", "release_required", "stop_pending",
    "duty_percent", "direction", "firmware_reason", "firmware_reason_text", "error",
    "stop_reason", "simulated", "owner_connected",
}


def public_status(value):
    """Expose documented telemetry only, never nonce/UID/extra server fields."""
    if not isinstance(value, dict) or not isinstance(value.get("state"), str):
        raise StatusError("La respuesta no contiene un estado de la H60 válido.")
    return {key: item for key, item in value.items() if key in STATUS_FIELDS}


def serial_status(*, port, manifest, manifest_sha256=None, execute=False,
                  opener=None):
    """Only INFO and STATUS. No STOP, MOVE, heartbeat or retry is sent."""
    if not valid_port(port):
        raise StatusError("Indica el puerto USB-DEBUG: ruta absoluta o COM en Windows.")
    if execute and not manifest_sha256:
        raise StatusError("La consulta real requiere --manifest-sha256 con el hash revisado.")
    manifest = Path(manifest)
    try:
        digest = manifest_sha256 or hashlib.sha256(manifest.read_bytes()).hexdigest()
        build = verify_manifest(manifest, digest)
    except (OSError, ValueError, HostError) as exc:
        raise StatusError(f"No se ha validado el build local: {exc}") from exc
    if not execute:
        return {
            "ok": True, "transport": "serial", "dry_run": True,
            "serial_opened": False, "network_used": False,
            "profile": 6, "manifest_sha256": digest,
            "payload_sha256": build["payload_sha256"],
            "commands_if_executed": ["INFO", "STATUS"],
            "note": "Revisa este hash y el build antes de añadir --execute.",
        }
    transport = None
    try:
        transport = (opener or SerialTransport.open)(port, SummaryJournal())
        device = ManualClient(transport)
        status = device.identify()  # One INFO, then one STATUS. No motor command.
        return {
            "ok": True, "transport": "serial", "dry_run": False,
            "serial_opened": True, "profile": 6,
            "manifest_sha256": digest, "commands_sent": ["INFO", "STATUS"],
            "status": public_status(status),
        }
    except (OSError, HostError, ImportError) as exc:
        raise StatusError("No se pudo consultar la aplicación. Revisa puerto, permisos, "
                          "propietario y perfil 6; no se reintenta ni se envía movimiento.") from exc
    finally:
        if transport is not None:
            transport.close()  # No DTR/RTS restoration, explicit reset or STOP.


def http_status(url="http://127.0.0.1:8765", *, opener=None):
    """GET /api/status on the running local web server; never claim control."""
    try:
        parsed = urlsplit(url)
        loopback = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
        valid = (parsed.scheme == "http" and loopback and not parsed.username
                 and not parsed.password and parsed.path in ("", "/")
                 and not parsed.query and not parsed.fragment and parsed.port is not None)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise StatusError("Usa la URL HTTP local con puerto, sin ruta, credenciales ni fragmento.")
    request = Request(url.rstrip("/") + "/api/status", method="GET",
                      headers={"Accept": "application/json"})
    try:
        client = opener or build_opener(NoRedirects())
        with client.open(request, timeout=2) as response:
            if response.status != 200:
                raise StatusError("El servidor no ha devuelto HTTP 200.")
            raw = response.read(32769)
            if len(raw) > 32768:
                raise StatusError("El estado del servidor excede el límite de tamaño.")
            value = json.loads(raw)
            if not isinstance(value, dict) or value.get("type") != "status":
                raise StatusError("La respuesta no corresponde al servidor de control H60.")
            status = public_status(value)
            return {"ok": True, "transport": "http", "serial_opened": False,
                    "control_claimed": False, "status": status}
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise StatusError("No se pudo leer el estado HTTP local; no se abrió ningún puerto serie.") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    serial = commands.add_parser("serial", help="Plan offline o consulta directa explícita de perfil 6.")
    serial.add_argument("--port", required=True)
    serial.add_argument("--manifest", type=Path,
                        default=ROOT / "firmware/manual-hold/build/manifest.json")
    serial.add_argument("--manifest-sha256")
    serial.add_argument("--execute", action="store_true")
    http = commands.add_parser("http", help="Solo GET al servidor web que ya posee el puerto.")
    http.add_argument("--url", default="http://127.0.0.1:8765")
    args = parser.parse_args(argv)
    try:
        if args.command == "serial":
            result = serial_status(port=args.port, manifest=args.manifest,
                                   manifest_sha256=args.manifest_sha256, execute=args.execute)
        else:
            result = http_status(args.url)
    except (StatusError, OSError) as exc:
        result = {"ok": False, "error": str(exc), "movement_requested": False}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

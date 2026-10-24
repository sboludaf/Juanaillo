#!/usr/bin/env python3
"""Offline by default; one fixed three-second forward test per firmware boot.

Only this dedicated profile is accepted. There is no general ARM/velocity/PWM
command, no reset, no pulse escalation, no transaction replay or profile edit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys
import time

try:
    from .transport import DebugTransport, HostError, RawJournal, sha256, valid_port
except ImportError:
    from transport import DebugTransport, HostError, RawJournal, sha256, valid_port

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "firmware" / "forward-3s" / "build" / "manifest.json"

VERSION = 1
PROFILE = 4
MARKER = b"H60_FORWARD3S_SINGLE_SHOT_V1"
CAPS_FORMAT = ">BBBBHHHHII"
CAPS = (VERSION, PROFILE, 15, 10, 100, 5000, 3, 3000, 3005000, 100)
CAPS_BYTES = struct.pack(CAPS_FORMAT, *CAPS) + MARKER
MANIFEST_EXPECTED = {
    "target": "STM32F407VE", "profile": PROFILE, "marker": MARKER.decode(),
    "motor_capable": True, "fixed_motor_channels": ["A", "B", "C", "D"],
    "fixed_motor_mask": 15, "fixed_raw_directions": [1, -1, 1, -1],
    "uart": 1, "uart_pins": ["PA9", "PA10"], "baudrate": 230400, "framing": "8N1",
    "duty_permille": 100, "pwm_hz": 5000, "pwm_duration_ms": 3000, "wake_min_ms": 3,
    "absolute_envelope_us": 3005000, "lease_ms": 100, "one_fire_per_boot": True,
    "caps_hex": CAPS_BYTES.hex(),
}
STATUS_FORMAT = ">BBBBIIQ4HII"
STATUS_BYTES = struct.calcsize(STATUS_FORMAT)
IDLE, READY, WAKE, PULSE, DONE, FAULT = range(6)
CAPABLE, CONSUMED, OUTPUT_REQUESTED, ALL_LOW = 1, 2, 4, 8
STATUS, PREPARE, FIRE, STOP, LEASE, INFO, ENCODERS = 0x70, 0x71, 0x73, 0x74, 0x75, 0x76, 0x63
CPR = 1561
ENCODER_SIGNS = (-1, 1, -1, 1)
WHEELS = ("A", "B", "C", "D")
CUTOFF = {"A_B_C_D": "software DWT/ISR; 3.005s envelope; IWDG backup"}
RAW_DIRECTIONS = (1, -1, 1, -1)
MIN_COUNTS = 8
RESPONSE_TIMEOUT = .025
HEARTBEAT_SECONDS = .020
RUN_DEADLINE_SECONDS = 3.25
MAX_COUNT_RATE_PER_SECOND = 10000
MAX_ABS_TOTAL_COUNTS = 32767
MAX_SAMPLE_GAP_MS = 250


def require(condition, message):
    if not condition:
        raise HostError(message)


def frame(command, payload=b""):
    require(0 <= command <= 255 and len(payload) <= 250, "Frame fuera de rango.")
    raw = bytes((0xAA, 0x55, len(payload) + 5, command)) + bytes(payload)
    return raw + bytes((sum(raw) & 255,))


def signed_delta(after, before):
    return ((after - before + 32768) & 65535) - 32768


class Client:
    def __init__(self, transport, journal, *, clock=time.monotonic):
        self.transport = transport
        self.journal = journal
        self.clock = clock
        self.nonce = None
        self.caps_verified = False
        self.prepared_at = None
        self.fire_attempted = False
        self.fired_at = None
        self.failed = False
        self.last_command = None

    def _check(self, condition, message):
        if not condition:
            self.failed = True
            raise HostError(message)

    def _read_exact(self, count, deadline):
        result = bytearray()
        while len(result) < count:
            self._check(self.clock() < deadline, "Timeout de respuesta; no se reintenta.")
            result.extend(self.transport.read(count - len(result)))
        return bytes(result)

    def _exchange(self, command, payload, length):
        try:
            self.last_command = command
            self.transport.write(frame(command, payload))
            deadline = self.clock() + RESPONSE_TIMEOUT
            header = self._read_exact(4, deadline)
            self._check(header == bytes((0xAA, 0x55, length + 5, command)),
                    "Respuesta inesperada: no se resincroniza ni reintenta.")
            tail = self._read_exact(length + 1, deadline)
            self._check((sum(header + tail[:-1]) & 255) == tail[-1], "Checksum de respuesta incorrecto.")
            return tail[:-1]
        except BaseException:
            self.failed = True
            raise

    def _decode_status(self, raw):
        values = struct.unpack(STATUS_FORMAT, raw)
        version, profile, state, flags, uptime, lease, nonce = values[:7]
        status = {"version": version, "profile": profile, "state": state, "flags": flags,
                  "uptime_ms": uptime, "lease_remaining_ms": lease, "nonce": nonce,
                  "encoders": list(values[7:11]), "pulse_count": values[11], "reason": values[12]}
        self._check(version == VERSION and profile == PROFILE, "Perfil/protocolo inesperado.")
        self._check(state in range(6) and flags & ~15 == 0 and flags & CAPABLE,
                "Estado/flags incompatibles.")
        self._check(nonce != 0 and (self.nonce is None or nonce == self.nonce),
                "Nonce/sesión diferente; se aborta sin FIRE.")
        self._check(0 <= lease <= 100, "Lease fuera del límite fijo.")
        self._check(status["pulse_count"] in (0, 1), "Contador de pulso incompatible.")
        self._check(bool(flags & CONSUMED) == bool(status["pulse_count"]), "Consumo y contador discrepan.")
        self._check(state != FAULT and status["reason"] < 5, "Firmware informa FAULT.")
        if state in (IDLE, READY):
            self._check(flags == CAPABLE | ALL_LOW and status["pulse_count"] == 0,
                    "Salida/consumo no seguros antes del pulso.")
            self._check(status["reason"] in ((0, 1) if state == IDLE else (2,)),
                        "Reason incompatible antes del pulso.")
        elif state in (WAKE, PULSE):
            self._check(flags == CAPABLE | CONSUMED | OUTPUT_REQUESTED and status["pulse_count"] == 1,
                    "Estado activo incoherente.")
            self._check(status["reason"] == 3, "Reason activo incompatible.")
        elif state == DONE:
            self._check(flags == CAPABLE | CONSUMED | ALL_LOW and status["pulse_count"] == 1,
                    "DONE sin todas las salidas a cero en registros.")
            self._check(status["reason"] in (1, 4), "Reason DONE incompatible.")
        self.journal.event("status", **status)
        return status

    def identify(self):
        self._check(not self.failed, "Sesión fallida bloqueada.")
        raw = self._exchange(INFO, b"", len(CAPS_BYTES))
        self._check(raw == CAPS_BYTES, "Descriptor/máscara/duty/envelope no coinciden con el candidato conjunto.")
        self.caps_verified = True
        status = self.status()
        if self.nonce is None:
            self.nonce = status["nonce"]  # generated by firmware, never chosen by host
        self.journal.event("caps_verified", profile=PROFILE, channel_mask=15,
                           channels=list(WHEELS), raw_directions=list(RAW_DIRECTIONS),
                           reversed_mask=10,
                           duty_permille=100, pwm_hz=5000, wake_min_ms=3,
                           pwm_duration_ms=3000, envelope_us=3005000, lease_ms=100,
                           marker=MARKER.decode(), cutoff=CUTOFF, app_uid_authenticated=False)
        return status

    def status(self):
        return self._decode_status(self._exchange(STATUS, b"", STATUS_BYTES))

    def encoders(self):
        return list(struct.unpack(">4H", self._exchange(ENCODERS, b"", 8)))

    def stop(self):
        # A separate STOP on failure is permitted; a failed FIRE is never replayed.
        return self._decode_status(self._exchange(STOP, b"", STATUS_BYTES))

    def _session_payload(self):
        self._check(self.caps_verified and self.nonce is not None and not self.failed,
                "Identidad/sesión sin verificar o sesión fallida.")
        return struct.pack(">Q", self.nonce)

    def prepare(self):
        self._check(not self.fire_attempted and self.prepared_at is None, "PREPARE unique par client.")
        payload = self._session_payload()
        current = self.status()
        self._check(current["state"] == IDLE and current["pulse_count"] == 0,
                "El firmware debe estar IDLE y sin consumo previo.")
        self.prepared_at = self.clock()  # never refreshed by a repeated PREPARE
        reply = self._decode_status(self._exchange(PREPARE, payload, STATUS_BYTES))
        self._check(reply["state"] == READY and reply["reason"] == 2 and reply["lease_remaining_ms"] > 50,
                "PREPARE no obtuvo READY con lease suficiente.")
        return reply

    def lease(self):
        payload = self._session_payload()
        self._check(self.prepared_at is not None, "Lease sin PREPARE confirmado.")
        return self._decode_status(self._exchange(LEASE, payload, STATUS_BYTES))

    def fire_once(self):
        self._check(not self.fire_attempted, "FIRE ya intentado: jamás se repite.")
        payload = self._session_payload()
        self._check(self.prepared_at is not None and self.clock() - self.prepared_at < .2,
                "Sesión PREPARE ausente/caducada.")
        fresh = self.status()
        self._check(fresh["state"] == READY and fresh["reason"] == 2
                and fresh["lease_remaining_ms"] > 50 and fresh["pulse_count"] == 0,
                "Estado no seguro inmediatamente antes de FIRE.")
        self.fire_attempted = True  # sticky before logging/transmission/any response
        self.fired_at = self.clock()
        reply = self._decode_status(self._exchange(FIRE, payload, STATUS_BYTES))
        self._check(reply["state"] in (WAKE, PULSE, DONE) and reply["pulse_count"] == 1,
                "FIRE no confirmó consumo único.")
        return reply


class EncoderTracker:
    """Unwrap frequent samples, reject excessive jumps/gaps and ambiguous totals."""

    def __init__(self, status):
        self.before = list(status["encoders"])
        self.previous = list(self.before)
        self.uptime = status["uptime_ms"]
        self.totals = [0, 0, 0, 0]
        self.samples = 0

    def observe(self, status):
        elapsed_ms = (status["uptime_ms"] - self.uptime) & 0xFFFFFFFF
        require(elapsed_ms <= MAX_SAMPLE_GAP_MS, "Intervalo de encoder ambiguo: STOP, sin repetición.")
        bound = MAX_COUNT_RATE_PER_SECOND * (elapsed_ms + 2) // 1000 + 2
        for index, (previous, current) in enumerate(zip(self.previous, status["encoders"])):
            delta = signed_delta(current, previous)
            require(abs(delta) <= bound, "Salto/velocidad de encoder fuera de la cota de diagnóstico.")
            self.totals[index] += delta
            require(abs(self.totals[index]) <= MAX_ABS_TOTAL_COUNTS,
                    "Total de encoder ambiguo/excesivo: no asignar dirección.")
        self.previous = list(status["encoders"])
        self.uptime = status["uptime_ms"]
        self.samples += 1


def analyze_counts(before, after, raw_totals):
    require(len(before) == len(after) == 4
            and all(type(value) is int and 0 <= value <= 65535 for value in (*before, *after)),
            "Se requieren cuatro contadores uint16 antes y después.")
    require(len(raw_totals) == 4 and all(type(value) is int and abs(value) <= MAX_ABS_TOTAL_COUNTS
                                        for value in raw_totals), "Totales sin seguimiento válido.")
    require(all((start + total) & 65535 == end
                for start, end, total in zip(before, after, raw_totals)),
            "Totales y contadores finales discrepan.")
    normalized = [sign * delta for sign, delta in zip(ENCODER_SIGNS, raw_totals)]
    results = [{"wheel": wheel, "encoder_index": index, "raw_delta": raw_totals[index],
                "encoder_sign": ENCODER_SIGNS[index], "forward_delta": normalized[index],
                "direction": "forward" if normalized[index] >= MIN_COUNTS else
                             "reverse" if normalized[index] <= -MIN_COUNTS else "inconclusive"}
               for index, wheel in enumerate(WHEELS)]
    return {"channels": list(WHEELS), "channel_mask": 15,
            "tested_raw_directions": list(RAW_DIRECTIONS), "counts_before": list(before),
            "counts_after": list(after), "signed_delta": list(raw_totals),
            "normalized_forward_delta": normalized,
            "manual_encoder_signs": list(ENCODER_SIGNS),
            "counts_per_wheel_revolution": CPR, "minimum_unambiguous_counts": MIN_COUNTS,
            "wheel_revolutions": [delta / CPR for delta in normalized],
            "all_forward": all(value >= MIN_COUNTS for value in normalized), "wheel_results": results,
            "direction_basis": "manual encoder references; prior A motor_sign +1 visually confirmed",
            "prior_visual_reference": {"A_motor_sign": 1},
            "new_visual_confirmations_required": False,
            "profile_written": False, "automatic_retries": False}


def run_pulse(client, *, sleep=time.sleep):
    initial = client.identify()
    require(initial["state"] == IDLE, "Se necesita un boot nuevo IDLE; no se reinicia automáticamente.")
    client.stop()
    before = client.encoders()
    started = client.clock()
    while client.clock() - started < 1.1:
        sleep(.05)
        current = client.status()
        require(current["state"] == IDLE and current["encoders"] == before,
                "Encoders no quietos; no se prepara ni dispara.")
    client.stop()  # fresh STOP, preserving the firmware's quiet timer
    client.prepare()
    ready = client.lease()
    require(ready["state"] == READY and ready["lease_remaining_ms"] > 50,
            "Lease sin READY antes de FIRE.")
    tracker = EncoderTracker(ready)
    status = client.fire_once()
    tracker.observe(status)
    while status["state"] != DONE:
        require(client.clock() - client.fired_at < RUN_DEADLINE_SECONDS,
                "DONE no llegó dentro de 3,25s; abortar con STOP.")
        sleep(HEARTBEAT_SECONDS)
        status = client.lease()
        tracker.observe(status)
    tracker.observe(client.stop())
    # Observe passive settling; there is no second pulse if counts are ambiguous.
    settled_since = client.clock()
    deadline = settled_since + 1.5
    after = status["encoders"]
    while client.clock() - settled_since < .2:
        require(client.clock() < deadline, "Encoders no se estabilizaron tras DONE.")
        sleep(.025)
        status = client.status()
        tracker.observe(status)
        require(status["state"] == DONE, "El firmware abandonó DONE.")
        if status["encoders"] != after:
            after = status["encoders"]
            settled_since = client.clock()
    require(client.encoders() == after, "Encoders variaron durante lectura final.")
    final = client.status()
    tracker.observe(final)
    require(final["state"] == DONE and final["flags"] == 11 and final["encoders"] == after,
            "Estado final sin DONE/all-low/encoders coherentes.")
    analysis = analyze_counts(tracker.before, after, tracker.totals)
    return {"status": "forward-verified" if analysis["all_forward"] else "direction-check-failed",
            "final_status": final, "encoder_samples_tracked": tracker.samples,
            "outputs_registers_all_low": True, "electrical_output_measurement": False,
            "cutoff": CUTOFF, "analysis": analysis}


def verify_artifacts(manifest_path, expected_digest):
    require(re.fullmatch(r"[0-9a-f]{64}", expected_digest or "") is not None,
            "Se requiere SHA256 revisado del manifiesto.")
    manifest_path = Path(manifest_path)
    raw = manifest_path.read_bytes()
    require(sha256(raw) == expected_digest, "Hash de manifiesto diferente del revisado.")
    manifest = json.loads(raw)
    require(manifest.get("schema") == "h60.forward-3s-build.v1", "Manifiesto ajeno al ensayo de avance3s.")
    require(all(type(manifest.get(key)) is type(value) and manifest.get(key) == value
                for key, value in MANIFEST_EXPECTED.items()),
            "CAPS/UART/límites del manifiesto diferentes del candidato conjunto.")
    root = manifest_path.parent.parent.resolve()
    artifacts = manifest.get("artifacts")
    sources = manifest.get("sources")
    require(isinstance(artifacts, dict) and len(artifacts) == 4
            and {Path(name).suffix for name in artifacts} == {".bin", ".elf", ".hex", ".map"}
            and isinstance(sources, dict) and bool(sources), "Faltan artefactos/fuentes.")
    bins = []
    for name, digest in artifacts.items():
        require(Path(name).name == name, "Ruta de artefacto insegura.")
        path = manifest_path.parent / name
        data = path.read_bytes()
        require(sha256(data) == digest, f"Artefacto modificado: {name}")
        if path.suffix == ".bin":
            bins.append(data)
    require(len(bins) == 1 and MARKER in bins[0], "BIN sin marcador único del candidato conjunto.")
    require(type(manifest.get("image_bytes")) is int
            and manifest["image_bytes"] == len(bins[0])
            and 0 < len(bins[0]) <= 16384 and len(bins[0]) % 4 == 0
            and manifest.get("payload_sha256") == sha256(bins[0]),
            "Tamaño/hash de payload incompatibles con el sector 0.")
    for name, digest in sources.items():
        path = root / name
        require(not Path(name).is_absolute() and path.resolve().is_relative_to(root),
                "Fuente fuera de raíz.")
        require(sha256(path.read_bytes()) == digest, f"Fuente modificada: {name}")
    return {"manifest_sha256": expected_digest, "binary_sha256": sha256(bins[0]),
            "sources_verified": len(sources), "artifacts_verified": len(artifacts),
            "cutoff": CUTOFF, "app_uid_authenticated": False,
            "device_association": "operator-associated exact flash plus live CAPS, not UID authentication"}


def execute(action, port, outdir, evidence, *, factory=None, hupcl_setter=None,
            clock=time.monotonic, sleep=time.sleep):
    journal = RawJournal(outdir)
    transport = None
    client = None
    result = {"status": "failed", "action": action, "artifact_evidence": evidence,
              "no_reset_requested": True, "no_profile_write": True}
    try:
        journal.event("offline_artifacts_verified", **evidence)
        options = {"factory": factory}
        if hupcl_setter is not None:
            options["hupcl_setter"] = hupcl_setter
        transport = DebugTransport.open(port, journal, **options)
        client = Client(transport, journal, clock=clock)
        if action == "pulse":
            result.update(run_pulse(client, sleep=sleep))
        else:
            status = client.identify()
            if action == "stop":
                status = client.stop()
            elif action == "status":
                status = client.status()
            require(action in ("identify", "status", "stop"), "Acción no implementada.")
            result.update(status="queried", device_status=status)
        journal.event("operation_completed", status=result["status"])
    except BaseException as exc:
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        if client is not None and client.last_command != STOP:
            try:
                journal.event("abort_stop_requested", fire_attempted=client.fire_attempted)
                result["abort_stop_status"] = client.stop()
            except BaseException as stop_exc:
                result["abort_stop_error"] = f"{type(stop_exc).__name__}: {stop_exc}"
        elif client is not None:
            result["abort_stop_not_replayed"] = True
        raise
    finally:
        try:
            if transport is not None:
                try:
                    transport.close()
                except BaseException as exc:
                    result.update(status="failed", close_error=f"{type(exc).__name__}: {exc}")
                    raise
        finally:
            try:
                journal.report(result)
            finally:
                journal.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("identify", "status", "stop", "pulse"))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST),
                        help="Manifiesto local; por defecto firmware/forward-3s/build/manifest.json.")
    parser.add_argument("--manifest-sha256", help="Hash revisado obligatorio con --execute.")
    parser.add_argument("--port", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        require(valid_port(args.port), "Puerto explícito inválido para esta plataforma.")
        expected_hash = args.manifest_sha256
        if expected_hash is None:
            require(not args.execute, "--execute requiere --manifest-sha256 revisado.")
            expected_hash = sha256(Path(args.manifest).read_bytes())
        evidence = verify_artifacts(args.manifest, expected_hash)
        require(not Path(args.outdir).exists(), "El directorio de salida debe ser nuevo.")
        if not args.execute:
            print(json.dumps({"dry_run": True, "port_not_opened": True, "action": args.action,
                              "channels": list(WHEELS), "channel_mask": 15,
                              "raw_directions": list(RAW_DIRECTIONS), "reversed_mask": 10,
                              "duty_permille": 100, "duration_ms": 3000,
                              "absolute_envelope_us": 3005000, "one_fire_per_boot": True,
                              "heartbeat_ms": 20, "host_deadline_ms": 3250,
                              "no_reset_requested": True, **evidence}, indent=2))
            return 0
        result = execute(args.action, args.port, args.outdir, evidence)
        summary = {"status": result["status"], "report": str(Path(args.outdir) / "result.json")}
        if "analysis" in result:
            summary["analysis"] = result["analysis"]
        print(json.dumps(summary, indent=2))
        return 0 if result["status"] in ("forward-verified", "queried") else 1
    except KeyboardInterrupt:
        print("Interrumpido; STOP solicitado, sin reset ni repetición de FIRE.", file=sys.stderr)
        return 130
    except (HostError, OSError, ValueError, TypeError, KeyError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""One serial worker and one controller; current intent, never a MOVE queue."""
from __future__ import annotations

import threading
import time

from .serial_client import DeviceError, StaleHold

BROWSER_LEASE = .250
MOVE_PERIOD = .050


class ControlError(RuntimeError):
    pass


class Controller:
    def __init__(self, *, simulated=False, clock=time.monotonic):
        self.lock, self.changed, self.clock = threading.RLock(), threading.Event(), clock
        self.simulated, self.owner, self.last_seq = simulated, None, 0
        self.held, self.deadline, self.generation = 0, 0.0, 0
        self.stop_epoch, self.stop_done = 1, 0
        self.release_required, self.error, self.stop_reason = False, None, None
        self.connected, self.device = False, {}

    def claim(self, owner):
        with self.lock:
            if self.owner is not None:
                raise ControlError("Otro navegador ya controla esta sesión.")
            self.owner, self.last_seq = owner, 0
            self.changed.set()

    def _cancel(self, reason, *, require_release=False):
        self.held, self.deadline = 0, 0.0
        self.generation += 1
        self.stop_epoch += 1
        self.stop_reason, self.release_required = reason, require_release
        self.changed.set()

    def release(self, owner, reason="disconnect"):
        with self.lock:
            if self.owner == owner:
                self._cancel(reason)
                self.owner = None

    def command(self, owner, message):
        with self.lock:
            if self.owner != owner:
                raise ControlError("Este navegador no tiene el control.")
            seq = message.get("seq")
            if type(seq) is not int or not self.last_seq < seq <= 9007199254740991:
                self._cancel("sequence_error", require_release=True)
                raise ControlError("Secuencia repetida o no válida; movimiento detenido.")
            self.last_seq = seq
            kind = message.get("type")
            if kind == "stop":
                self._cancel("release")
            elif kind == "heartbeat":
                if self.held and not self.release_required:
                    self.deadline = self.clock() + BROWSER_LEASE
            elif kind == "hold":
                direction = {"forward": 1, "reverse": -1}.get(message.get("direction"))
                if direction is None or self.held or self.release_required:
                    self._cancel("invalid_hold", require_release=True)
                    raise ControlError("Suelta el control antes de iniciar otro movimiento.")
                pending_stop = self.stop_done != self.stop_epoch
                if (not self.connected or self.error
                        or self.device.get("state") not in ("idle", "wake", "running", "limit")
                        or (not pending_stop and self.device.get("state") != "idle")):
                    raise ControlError("El controlador todavía no está listo para moverse.")
                self.held, self.deadline = direction, self.clock() + BROWSER_LEASE
                self.generation += 1
                self.stop_reason = None
                self.changed.set()
            else:
                self._cancel("protocol_error", require_release=True)
                raise ControlError("Mensaje de control no válido.")

    def _ready(self):
        pending_stop = self.stop_done != self.stop_epoch
        return (self.connected and not self.error and not self.release_required
                and ((pending_stop and bool(self.held)) or
                     (not pending_stop and self.device.get("state") in ("idle", "wake", "running"))))

    def action(self):
        with self.lock:
            if self.held and self.clock() >= self.deadline:
                self._cancel("browser_timeout", require_release=True)
            return self.stop_epoch, self.generation, self.held

    def permit(self, generation, direction):
        with self.lock:
            return (self.held == direction and self.generation == generation and not self.error
                    and not self.release_required and self.owner is not None and self.clock() < self.deadline
                    and self.stop_done == self.stop_epoch)

    def stopped(self, epoch):
        with self.lock:
            self.stop_done = max(epoch, self.stop_done)

    def publish(self, device):
        with self.lock:
            self.device, self.connected = dict(device), True
            if device["state"] == "limit" and self.stop_done == self.stop_epoch:
                # LIMIT consumes the gesture. Never STOP/restart due to its old HB.
                self.held, self.deadline, self.release_required = 0, 0.0, True
                self.generation += 1
                self.stop_reason = "burst_limit"
            elif device["state"] == "fault":
                self.fail("El firmware informa FAULT; requiere revisión y reinicio deliberado.")

    def fail(self, message):
        with self.lock:
            self._cancel("serial_error", require_release=True)
            self.error, self.connected = message, False

    def snapshot(self, owner=None):
        with self.lock:
            state = self.device.get("state", "connecting")
            if self.error:
                state = "error"
            elif self.release_required:
                state = "limit" if self.stop_reason == "burst_limit" else state
            elif self.held and self.stop_done != self.stop_epoch and state == "limit":
                state = "stopping"
            value = self.device.get("direction_value", 0)
            return {"type": "status", "simulated": self.simulated, "connected": self.connected,
                    "ready": self._ready(), "controller": owner is not None and self.owner == owner,
                    "owner_connected": self.owner is not None, "state": state,
                    "moving": self.device.get("state") in ("wake", "running"),
                    "direction": {1: "forward", -1: "reverse"}.get(value), "held": bool(self.held),
                    "release_required": self.release_required,
                    "stop_pending": self.stop_done != self.stop_epoch,
                    "burst_remaining_ms": self.device.get("burst_remaining_ms", 0),
                    "firmware_lease_ms": self.device.get("firmware_lease_ms", 0), "browser_lease_ms": 250,
                    "duty_percent": 10, "encoders": self.device.get("encoders", [0, 0, 0, 0]),
                    "error": self.error, "stop_reason": self.stop_reason}


class DeviceWorker:
    def __init__(self, controller, factory):
        self.controller, self.factory = controller, factory
        self.shutdown = threading.Event()
        self.thread = threading.Thread(target=self._run, name="h60-serial-owner", daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.shutdown.set()
        self.controller.changed.set()
        self.thread.join(timeout=1)

    def _run(self):
        device = None
        last_move, last_generation, last_poll, stopped = 0.0, -1, 0.0, 0
        try:
            device = self.factory()  # Only this thread opens/owns the serial port.
            self.controller.publish(device.identify())
            if self.controller.error:
                raise DeviceError(self.controller.error)
            while not self.shutdown.is_set():
                epoch, generation, direction = self.controller.action()
                now = self.controller.clock()
                if epoch > stopped:
                    status = device.stop()
                    stopped = epoch
                    self.controller.stopped(epoch)
                    self.controller.publish(status)
                    last_poll = now
                elif direction and (generation != last_generation or now - last_move >= MOVE_PERIOD):
                    try:
                        status = device.move(direction, permit=lambda: self.controller.permit(generation, direction))
                    except StaleHold:
                        continue
                    last_move, last_generation, last_poll = now, generation, now
                    self.controller.publish(status)
                elif not direction and now - last_poll >= .1:
                    self.controller.publish(device.status())
                    last_poll = now
                if self.controller.error:
                    raise DeviceError(self.controller.error)
                self.controller.changed.wait(.010)
                self.controller.changed.clear()
        except BaseException as exc:
            self.controller.fail(f"{type(exc).__name__}: {exc}")
        finally:
            if device is not None:
                try:
                    device.stop()  # Best effort once; never replay a MOVE or reset.
                except BaseException:
                    pass
                try:
                    device.close()
                except BaseException as exc:
                    self.controller.fail(f"Cierre serie fallido: {exc}")

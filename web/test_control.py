import threading
import time
import unittest

from web.control import ControlError, Controller, DeviceWorker
from web.serial_client import SimulatedDevice


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def status(state="idle", direction=0):
    return {"state": state, "direction_value": direction, "flags": 9 if direction == 0 else 7,
            "all_low": direction == 0, "firmware_lease_ms": 150 if direction else 0,
            "burst_remaining_ms": 10000 if direction else 0, "encoders": [0] * 4}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.control = Controller(simulated=True, clock=self.clock)
        self.control.publish(status())
        self.control.stopped(1)
        self.control.claim("owner")

    def command(self, kind, seq, **fields):
        self.control.command("owner", {"type": kind, "seq": seq, **fields})

    def test_hold_heartbeat_and_browser_deadman(self):
        self.command("hold", 1, direction="forward")
        _, generation, direction = self.control.action()
        self.assertTrue(self.control.permit(generation, direction))
        self.clock.now += .2; self.command("heartbeat", 2)
        self.clock.now += .2
        self.assertEqual(self.control.action()[2], 1)
        self.clock.now += .051
        self.assertEqual(self.control.action()[2], 0)
        self.assertTrue(self.control.snapshot("owner")["release_required"])
        self.assertFalse(self.control.permit(generation, direction))

    def test_release_and_disconnect_discard_pending_move(self):
        self.command("hold", 1, direction="forward")
        _, generation, direction = self.control.action()
        self.command("stop", 2)
        self.assertFalse(self.control.permit(generation, direction))
        self.control.release("owner")
        self.assertFalse(self.control.snapshot()["owner_connected"])
        self.assertEqual(self.control.action()[2], 0)

    def test_sequence_and_exclusive_owner(self):
        with self.assertRaises(ControlError):
            self.control.claim("second")
        self.command("hold", 1, direction="forward")
        with self.assertRaises(ControlError):
            self.command("heartbeat", 1)
        self.assertEqual(self.control.action()[2], 0)
        self.assertEqual(self.control.snapshot()["stop_reason"], "sequence_error")

    def test_limit_consumes_gesture_until_stop_and_new_hold(self):
        self.command("hold", 1, direction="forward")
        prior_stop_epoch = self.control.stop_epoch
        self.control.publish(status("limit"))
        self.assertEqual(self.control.stop_epoch, prior_stop_epoch)  # No automatic STOP/re-arm.
        self.command("heartbeat", 2)
        self.assertEqual(self.control.action()[2], 0)
        with self.assertRaises(ControlError):
            self.command("hold", 3, direction="forward")
        self.command("stop", 4)
        self.command("hold", 5, direction="reverse")
        epoch, generation, direction = self.control.action()
        self.assertFalse(self.control.permit(generation, direction))
        self.control.stopped(epoch); self.control.publish(status())
        self.assertTrue(self.control.permit(generation, -1))

    def test_fresh_reverse_waits_for_stop_ack_and_can_be_cancelled(self):
        self.command("hold", 1, direction="forward")
        self.control.publish(status("running", 1))
        self.command("stop", 2)
        self.command("hold", 3, direction="reverse")
        epoch, generation, direction = self.control.action()
        self.assertEqual(direction, -1)
        self.assertFalse(self.control.permit(generation, direction))
        self.command("stop", 4)  # Release fresh intent BEFORE the previous STOP ack.
        self.control.stopped(epoch); self.control.publish(status())
        self.assertFalse(self.control.permit(generation, direction))
        self.assertEqual(self.control.action()[2], 0)

    def test_fault_is_not_cleared_by_stop_or_fresh_hold(self):
        self.control.publish(status("fault"))
        self.command("stop", 1)
        with self.assertRaises(ControlError):
            self.command("hold", 2, direction="forward")
        self.assertTrue(self.control.snapshot()["error"])


class WorkerTests(unittest.TestCase):
    def test_real_thread_expires_browser_hold_and_never_resumes_old_heartbeat(self):
        device = SimulatedDevice()
        control = Controller(simulated=True)
        worker = DeviceWorker(control, lambda: device)
        worker.start()
        self.addCleanup(worker.close)
        deadline = time.monotonic() + 1
        while not control.snapshot()["ready"] and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertTrue(control.snapshot()["ready"])
        control.claim("owner")
        control.command("owner", {"type": "hold", "direction": "forward", "seq": 1})
        time.sleep(.34)
        self.assertFalse(control.snapshot()["moving"])
        self.assertTrue(control.snapshot()["release_required"])
        moves = len(device.move_calls)
        control.command("owner", {"type": "heartbeat", "seq": 2})
        time.sleep(.08)
        self.assertEqual(len(device.move_calls), moves)
        self.assertGreaterEqual(device.stop_calls, 2)


if __name__ == "__main__":
    unittest.main()

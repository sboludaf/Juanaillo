import threading
import time
import unittest

from web.control import ControlError, Controller, DeviceWorker
from web.serial_client import DeviceError, SimulatedDevice


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
        self.command("hold", 3, direction="forward")
        self.assertEqual(self.control.action()[2], 0)
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

    def test_turn_names_values_and_stop_ack_before_next_intent(self):
        for index, (name, value) in enumerate((("left", 2), ("right", -2))):
            self.command("hold", index * 2 + 1, direction=name)
            _, generation, direction = self.control.action()
            self.assertEqual(direction, value)
            self.assertTrue(self.control.permit(generation, direction))
            self.control.publish(status("running", value))
            self.assertEqual(self.control.snapshot("owner")["direction"], name)
            self.command("stop", index * 2 + 2)
            self.assertFalse(self.control.permit(generation, direction))
            self.control.stopped(self.control.stop_epoch); self.control.publish(status())

    def test_simultaneous_intent_stops_without_losing_owner_or_creating_fault(self):
        self.command("hold", 1, direction="left")
        _, generation, direction = self.control.action()
        self.command("hold", 2, direction="right")
        self.assertFalse(self.control.permit(generation, direction))
        self.assertEqual(self.control.action()[2], 0)
        self.assertTrue(self.control.release_required)
        self.assertEqual(self.control.stop_reason, "input_conflict")
        self.assertEqual(self.control.owner, "owner")
        self.assertIsNone(self.control.error)
        epoch = self.control.stop_epoch
        self.command("heartbeat", 3)
        self.command("hold", 4, direction="forward")
        self.assertEqual(self.control.stop_epoch, epoch)
        self.assertEqual(self.control.action()[2], 0)
        self.control.stopped(epoch); self.control.publish(status())
        self.assertFalse(self.control.snapshot("owner")["ready"])
        self.command("stop", 5)
        self.command("hold", 6, direction="right")
        epoch, generation, direction = self.control.action()
        self.assertFalse(self.control.permit(generation, direction))
        self.control.stopped(epoch); self.control.publish(status())
        self.assertTrue(self.control.permit(generation, -2))

    def test_overlap_also_cancels_fresh_intent_waiting_for_stop_ack(self):
        self.command("hold", 1, direction="forward")
        self.control.publish(status("running", 1))
        self.command("stop", 2)
        prior_epoch = self.control.stop_epoch
        self.command("hold", 3, direction="left")
        _, generation, direction = self.control.action()
        self.command("hold", 4, direction="right")
        self.control.stopped(prior_epoch); self.control.publish(status())
        self.assertFalse(self.control.permit(generation, direction))
        self.assertEqual(self.control.action()[2], 0)
        self.assertEqual(self.control.stop_reason, "input_conflict")

    def test_invalid_directions_stay_strict_even_while_release_blocked(self):
        self.command("hold", 1, direction="left")
        self.command("hold", 2, direction="right")
        for seq, invalid in enumerate(("diagonal", [], {}, None, 2), 3):
            with self.subTest(direction=invalid), self.assertRaises(ControlError):
                self.command("hold", seq, direction=invalid)
        self.assertEqual(self.control.action()[2], 0)

    def test_snapshot_preserves_actual_firmware_reason_for_fault_diagnosis(self):
        self.assertIsNone(self.control.snapshot()["firmware_reason"])
        self.control.publish({**status("fault"), "reason": 5})
        snapshot = self.control.snapshot("owner")
        self.assertEqual(snapshot["firmware_reason"], 5)
        self.assertIn("Lease", snapshot["firmware_reason_text"])
        self.assertEqual(snapshot["state"], "error")
        self.assertIn("motivo 5", snapshot["error"])
        self.assertIn("Lease", snapshot["error"])
        self.command("stop", 1)
        self.assertTrue(self.control.snapshot()["error"])
        self.assertEqual(self.control.snapshot()["firmware_reason"], 5)

    def test_fault_is_not_cleared_by_stop_or_fresh_hold(self):
        self.control.publish(status("fault"))
        self.command("stop", 1)
        with self.assertRaises(ControlError):
            self.command("hold", 2, direction="forward")
        self.assertTrue(self.control.snapshot()["error"])


class WorkerTests(unittest.TestCase):
    def test_pending_turn_released_before_stop_ack_never_reaches_device(self):
        entered, finish = threading.Event(), threading.Event()
        class GateStopDevice(SimulatedDevice):
            def stop(self):
                if self.stop_calls == 1:
                    entered.set(); finish.wait(1)
                return super().stop()
        device = GateStopDevice(); control = Controller(simulated=True)
        worker = DeviceWorker(control, lambda: device); worker.start()
        self.addCleanup(worker.close); self.addCleanup(finish.set)
        deadline = time.monotonic() + 1
        while not control.snapshot()["ready"] and time.monotonic() < deadline:
            time.sleep(.005)
        control.claim("owner")
        control.command("owner", {"type": "hold", "direction": "forward", "seq": 1})
        while not device.move_calls and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertTrue(device.move_calls)
        control.command("owner", {"type": "stop", "seq": 2})
        control.command("owner", {"type": "hold", "direction": "left", "seq": 3})
        self.assertTrue(entered.wait(1))
        control.command("owner", {"type": "stop", "seq": 4})
        finish.set(); time.sleep(.08)
        self.assertFalse(any(direction == 2 for _, direction in device.move_calls))
        self.assertEqual(control.action()[2], 0)

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


class TurnSimulationTests(unittest.TestCase):
    def test_turn_change_preserves_burst_and_limit_requires_stop(self):
        clock = Clock(); device = SimulatedDevice(clock=clock)
        self.assertEqual(device.move(2)["state"], "wake")
        clock.now += .1
        self.assertEqual(device.move(-2)["state"], "wake")
        self.assertEqual(device.bursts, 1)
        for step in range(3, 200):
            clock.now = 100 + step * .05
            device.move(-2)
        clock.now = 110
        self.assertEqual(device.move(2)["state"], "limit")
        calls = len(device.move_calls)
        clock.now += .05; device.move(-2)
        self.assertEqual(len(device.move_calls), calls)
        self.assertEqual(device.bursts, 1)
        device.stop()
        self.assertEqual(device.move(2)["state"], "wake")
        self.assertEqual(device.bursts, 2)

    def test_lost_turn_lease_is_sticky_and_invalid_values_do_not_move(self):
        clock = Clock(); device = SimulatedDevice(clock=clock)
        for invalid in (0, 3, -3, True):
            with self.assertRaises(DeviceError):
                device.move(invalid)
        self.assertEqual(device.move_calls, [])
        device.move(-2); clock.now += .151
        self.assertEqual(device.status()["state"], "fault")
        device.stop(); device.move(2)
        self.assertEqual(device.state, "fault")
        self.assertEqual(len(device.move_calls), 1)


if __name__ == "__main__":
    unittest.main()

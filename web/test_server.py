import asyncio
import unittest

from aiohttp import WSServerHandshakeError
from aiohttp.test_utils import TestClient, TestServer

from web.serial_client import SimulatedDevice
from web.server import CONTROLLER, create_app


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.device = SimulatedDevice()
        self.app = create_app(token="synthetic-test-key", device_factory=lambda: self.device)
        self.client = TestClient(TestServer(self.app, host="127.0.0.1"))
        await self.client.start_server()
        self.origin = str(self.client.make_url("/")).rstrip("/")
        await self.wait_for(lambda: self.app[CONTROLLER].snapshot()["ready"])

    async def asyncTearDown(self):
        await self.client.close()

    async def wait_for(self, predicate):
        end = asyncio.get_running_loop().time() + 1
        while not predicate():
            self.assertLess(asyncio.get_running_loop().time(), end)
            await asyncio.sleep(.01)

    async def connect(self, token="synthetic-test-key"):
        ws = await self.client.ws_connect("/ws", origin=self.origin)
        await ws.send_json({"type": "hello", "token": token})
        first = await ws.receive_json()
        return ws, first

    async def test_authenticated_hold_release_and_disconnect_stop(self):
        ws, hello = await self.connect()
        self.assertEqual(hello, {"type": "hello", "ok": True, "controller": True})
        await ws.send_json({"type": "hold", "direction": "forward", "seq": 1})
        await self.wait_for(lambda: bool(self.device.move_calls))
        await ws.send_json({"type": "stop", "seq": 2})
        await self.wait_for(lambda: not self.app[CONTROLLER].snapshot()["moving"])
        count = len(self.device.move_calls); await asyncio.sleep(.08)
        self.assertEqual(len(self.device.move_calls), count)
        await ws.send_json({"type": "hold", "direction": "reverse", "seq": 3})
        await self.wait_for(lambda: self.device.direction == -1)
        await ws.close()
        await self.wait_for(lambda: not self.app[CONTROLLER].snapshot()["owner_connected"])
        await self.wait_for(lambda: self.device.state == "idle")

    async def test_browser_deadman_with_open_socket(self):
        ws, _ = await self.connect()
        await ws.send_json({"type": "hold", "direction": "left", "seq": 1})
        await self.wait_for(lambda: bool(self.device.move_calls))
        self.assertEqual(self.device.move_calls[0][1], 2)
        await asyncio.sleep(.33)
        self.assertFalse(self.app[CONTROLLER].snapshot()["moving"])
        self.assertTrue(self.app[CONTROLLER].snapshot()["release_required"])
        count = len(self.device.move_calls)
        await ws.send_json({"type": "heartbeat", "seq": 2}); await asyncio.sleep(.08)
        self.assertEqual(len(self.device.move_calls), count)

    async def test_left_right_websocket_to_worker_and_rapid_stop_then_new_hold(self):
        ws, _ = await self.connect()
        await ws.send_json({"type": "hold", "direction": "left", "seq": 1})
        await self.wait_for(lambda: self.app[CONTROLLER].snapshot()["direction"] == "left")
        self.assertEqual(self.device.move_calls[-1][1], 2)
        await ws.send_json({"type": "stop", "seq": 2})
        await ws.send_json({"type": "hold", "direction": "right", "seq": 3})
        await self.wait_for(lambda: self.app[CONTROLLER].snapshot()["direction"] == "right")
        self.assertEqual(self.device.move_calls[-1][1], -2)
        self.assertGreaterEqual(self.device.stop_calls, 2)  # Initial STOP and gesture transition.
        await ws.send_json({"type": "stop", "seq": 4})
        await self.wait_for(lambda: not self.app[CONTROLLER].snapshot()["moving"])
        count = len(self.device.move_calls)
        await asyncio.sleep(.08)
        self.assertEqual(len(self.device.move_calls), count)

    async def test_two_simultaneous_turn_intents_stop_instead_of_switching(self):
        ws, _ = await self.connect()
        await ws.send_json({"type": "hold", "direction": "left", "seq": 1})
        await self.wait_for(lambda: self.device.direction == 2)
        await ws.send_json({"type": "hold", "direction": "right", "seq": 2})
        await self.wait_for(lambda: self.app[CONTROLLER].owner is None)
        await self.wait_for(lambda: self.device.state == "idle")
        self.assertFalse(any(value == -2 for _, value in self.device.move_calls))

    async def test_second_owner_and_bad_token_do_not_steal_control(self):
        first, _ = await self.connect()
        owner = self.app[CONTROLLER].owner
        for key in ("wrong-key", "synthetic-test-key"):
            second, reply = await self.connect(key)
            self.assertEqual(reply["type"], "error")
            self.assertEqual(self.app[CONTROLLER].owner, owner)
            await second.close()
        await first.close()

    async def test_replayed_sequence_stops_and_releases_owner(self):
        ws, _ = await self.connect()
        await ws.send_json({"type": "hold", "direction": "forward", "seq": 1})
        await self.wait_for(lambda: bool(self.device.move_calls))
        await ws.send_json({"type": "heartbeat", "seq": 1})
        await self.wait_for(lambda: self.app[CONTROLLER].owner is None)
        await self.wait_for(lambda: self.device.state == "idle")

    async def test_cross_origin_missing_origin_and_wrong_host_rejected(self):
        for origin in (None, "http://evil.invalid"):
            with self.assertRaises(WSServerHandshakeError) as caught:
                await self.client.ws_connect("/ws", origin=origin)
            self.assertEqual(caught.exception.status, 403)
        response = await self.client.get("/api/status", headers={"Host": "evil.invalid:8765"})
        self.assertEqual(response.status, 403)
        self.assertEqual(self.device.move_calls, [])

    async def test_no_http_motion_or_stop_endpoint_and_status_has_no_secret(self):
        response = await self.client.post("/api/stop")
        self.assertIn(response.status, (404, 405))
        response = await self.client.get("/api/status")
        data = await response.json()
        self.assertNotIn("token", data); self.assertNotIn("nonce", data)
        self.assertFalse(data["controller"])
        self.assertEqual(self.device.move_calls, [])


if __name__ == "__main__":
    unittest.main()

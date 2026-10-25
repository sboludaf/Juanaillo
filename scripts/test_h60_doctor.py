import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import h60_doctor as doctor


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sys = self.root / "sys"
        self.dev = self.root / "dev"
        self.proc = self.root / "proc"
        self.dev.mkdir()
        self.proc.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def adapter(self, name, identity, tty=None, driver=None):
        usb = self.sys / "bus/usb/devices" / name
        usb.mkdir(parents=True)
        (usb / "idVendor").write_text(identity[0])
        (usb / "idProduct").write_text(identity[1])
        (usb / "serial").write_text("DO-NOT-EXPOSE-REFERENCE-DEVICE")
        if tty:
            interface = usb / (name + ":1.0")
            interface.mkdir()
            if driver:
                target = self.sys / "bus/usb/drivers" / driver
                target.mkdir(parents=True, exist_ok=True)
                (interface / "driver").symlink_to(target)
            tty_dir = self.sys / "class/tty" / tty
            tty_dir.mkdir(parents=True)
            (tty_dir / "device").symlink_to(interface)
            (self.dev / tty).touch()
        return usb

    def test_enumeration_reports_binding_access_busy_and_omits_serial(self):
        self.adapter("1-2", ("1a86", "7523"), "ttyUSB0", "ch341")
        self.adapter("1-3", ("1a86", "55d4"), "ttyACM0", "cdc_acm")
        fd = self.proc / "123/fd"
        fd.mkdir(parents=True)
        (fd / "4").symlink_to(self.dev / "ttyUSB0")
        report = doctor.linux_usb(self.sys, self.dev, self.proc)
        ports = {p["h60_port_candidate"]: p for p in report["ports"]}
        self.assertEqual(ports["USB-DEBUG"]["driver"], "ch341")
        self.assertEqual(ports["USB-DEBUG"]["visible_owner_pids"], [123])
        self.assertEqual(ports["USB-COM"]["driver"], "cdc_acm")
        self.assertTrue(ports["USB-COM"]["readable"])
        self.assertNotIn("DO-NOT-EXPOSE", json.dumps(report))
        self.assertFalse(report["busy_scan"]["empty_result_proves_free"])

    def test_enumerated_usb_without_tty_is_distinct_from_missing_adapter(self):
        self.adapter("1-2", ("1a86", "7523"))
        report = doctor.linux_usb(self.sys, self.dev, self.proc)
        self.assertEqual(len(report["reference_usb_devices"]), 1)
        self.assertEqual(report["ports"], [])

    def test_broken_sysfs_nodes_and_disappearing_processes_are_tolerated(self):
        tty = self.sys / "class/tty/ttyUSB5"
        tty.mkdir(parents=True)
        (tty / "device").symlink_to(self.root / "disappeared")
        (self.proc / "88").mkdir()
        self.assertEqual(doctor.linux_usb(self.sys, self.dev, self.proc)["ports"], [])

    def test_non_h60_serial_adapter_does_not_get_h60_mapping(self):
        self.adapter("1-9", ("1234", "4321"), "ttyUSB8", "other")
        ports = doctor.linux_usb(self.sys, self.dev, self.proc)["ports"]
        self.assertIsNone(ports[0]["h60_port_candidate"])

    def test_tool_query_timeout_is_reported_without_failure(self):
        import subprocess
        with patch.object(doctor.shutil, "which", return_value="compiler"), patch.object(doctor.subprocess, "run", side_effect=subprocess.TimeoutExpired("compiler", 3)):
            self.assertEqual(doctor.tool_version("cc"), {"available": True, "version_query_ok": False})

    def test_portable_enumeration_does_not_expose_serial_or_hwid(self):
        ports = [SimpleNamespace(device="COM8", vid=0x1a86, pid=0x7523, serial_number="SECRET", hwid="SECRET"),
                 SimpleNamespace(device="/dev/cu.usbserial-SECRET", vid=0x1a86, pid=0x55d4, serial_number="SECRET", hwid="SECRET")]
        import types
        module = types.ModuleType("serial.tools.list_ports")
        module.comports = lambda: ports
        tools = types.ModuleType("serial.tools")
        tools.list_ports = module
        serial = types.ModuleType("serial")
        serial.tools = tools
        with patch.dict("sys.modules", {"serial": serial, "serial.tools": tools, "serial.tools.list_ports": module}):
            report = doctor.portable_ports()
        self.assertNotIn("SECRET", json.dumps(report))
        self.assertEqual(report["ports"][0]["device"], "/dev/cu.usbserial[redacted]")
        self.assertEqual(report["ports"][1]["device"], "COM8")

    def test_missing_pyserial_on_other_os_is_reported(self):
        with patch.dict("sys.modules", {"serial": None}):
            self.assertFalse(doctor.portable_ports()["enumeration_available"])

    def test_diagnostic_main_uses_only_metadata_and_version_queries(self):
        self.adapter("1-2", ("1a86", "7523"), "ttyUSB0", "ch341")
        metadata = doctor.linux_usb(self.sys, self.dev, self.proc)
        with patch.object(doctor.platform, "system", return_value="Linux"), patch.object(doctor, "linux_usb", return_value=metadata), patch.object(doctor, "tool_version", return_value={"available": False}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(doctor.main(["--json"]), 0)
        report = json.loads(output.getvalue())
        self.assertTrue(report["read_only"])
        self.assertFalse(report["serial_port_opened"])
        self.assertFalse(report["board_identity_verified"])
        self.assertNotIn("DO-NOT-EXPOSE", output.getvalue())


if __name__ == "__main__":
    unittest.main()

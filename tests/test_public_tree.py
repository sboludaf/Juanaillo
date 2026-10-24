import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('public_tree', Path(__file__).resolve().parents[1] / 'scripts/check_public_tree.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PublicTreeTests(unittest.TestCase):
    def test_token_value_is_not_exposed_in_diagnostic(self):
        secret = 'ghp_' + 'a' * 36
        result = MODULE.inspect_content('config.txt', secret.encode())
        self.assertTrue(any('GitHub token' in issue for issue in result))
        self.assertTrue(all(secret not in issue for issue in result))

    def test_private_paths_and_identity_are_detected(self):
        local = '/' + 'home' + '/example/person'
        uid = b'{"uid_hex": "' + b'12345678' * 3 + b'"}'
        self.assertTrue(MODULE.inspect_content('notes.txt', local.encode()))
        self.assertTrue(MODULE.inspect_content('identity.json', uid))

    def test_binary_and_backup_paths_are_blocked(self):
        self.assertTrue(MODULE.inspect_content('backups/flash.bin', b'\x80'))

    def test_public_hardware_data_and_hashes_are_allowed(self):
        text = 'STM32F407VE 512 KiB; PID 0x0413; sha256=' + 'a' * 64
        self.assertEqual(MODULE.inspect_content('docs/hardware.md', text.encode()), [])


if __name__ == '__main__':
    unittest.main()

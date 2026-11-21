"""Safety tests use temporary synthetic bytes, never development or final cases."""

import tempfile
import unittest
from pathlib import Path

from authorization_guard import AuthorizationError, require_authorization, sha256_file


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "synthetic.json"
        self.path.write_bytes(b'{"synthetic": true}\n')
        self.sha = sha256_file(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_refuses_without_flag(self):
        with self.assertRaises(AuthorizationError):
            require_authorization(self.path, self.sha, False)

    def test_refuses_without_hash(self):
        with self.assertRaises(AuthorizationError):
            require_authorization(self.path, None, True)

    def test_refuses_malformed_hash(self):
        with self.assertRaises(AuthorizationError):
            require_authorization(self.path, "z" * 64, True)

    def test_refuses_modified_bytes(self):
        self.path.write_bytes(b'{"synthetic": false}\n')
        with self.assertRaises(AuthorizationError):
            require_authorization(self.path, self.sha, True)

    def test_accepts_exact_hash_and_flag(self):
        self.assertEqual(require_authorization(self.path, self.sha, True), self.sha)


if __name__ == "__main__":
    unittest.main()

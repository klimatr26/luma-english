"""Offline build safety checks; no human evaluations or model generations."""
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

import build_human_review_web as web
from human_review_v2 import HUMAN_REVIEW_SCHEMA_VERSION, REVIEW_FIELDS


class BuildWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packet = self.root / "packet.json"
        self.plan = self.root / "plan.json"
        self.output = self.root / "review.html"
        self.item = {"blind_output_id": "br-synthetic", "level": "A1", "task": "Synthetic only", "student_text": "I walks.", "response_text": '</script><script>alert("untrusted")</script> & <img src=x>', "review_template": {"schema_version": HUMAN_REVIEW_SCHEMA_VERSION, **dict.fromkeys(REVIEW_FIELDS)}}
        self.data = {"schema_version": "human_review_v2.review_packet/1.0", "items": [self.item]}
        self.plan.write_text(json.dumps({"blind_output_ids": ["br-synthetic"]}), encoding="utf-8")

    def write_packet(self):
        self.packet.write_bytes((json.dumps(self.data, ensure_ascii=False, indent=2)+"\n").encode("utf-8"))

    def test_exact_packet_bytes_and_script_escape(self):
        self.write_packet()
        record = web.build(self.packet, self.plan, self.output)
        html = self.output.read_text(encoding="utf-8")
        embedded = re.search(r'<script type="application/json" id="public-data">(.*?)</script>', html, re.S).group(1)
        payload = json.loads(embedded)
        self.assertEqual(payload["packet_source"].encode("utf-8"), self.packet.read_bytes())
        self.assertNotIn("<script", embedded)
        self.assertNotIn("__PUBLIC_DATA__", html)
        self.assertEqual(record["output_sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertIn("connect-src 'none'", html)

    def test_build_is_reproducible(self):
        self.write_packet()
        one = web.build(self.packet, self.plan, self.output)
        two = web.build(self.packet, self.plan, self.output)
        self.assertEqual(one, two)

    def test_private_fields_rejected(self):
        self.item["config_id"] = "PRIVATE"
        self.write_packet()
        with self.assertRaisesRegex(ValueError, "non-public"):
            web.build(self.packet, self.plan, self.output)

    def test_prefilled_judgments_rejected(self):
        self.item["review_template"]["detection"] = 2
        self.write_packet()
        with self.assertRaisesRegex(ValueError, "blank"):
            web.build(self.packet, self.plan, self.output)

    def test_duplicate_ids_rejected(self):
        self.data["items"].append(self.item.copy())
        self.write_packet()
        with self.assertRaises(ValueError):
            web.build(self.packet, self.plan, self.output)

    def test_second_review_subset_rejected_if_unknown(self):
        self.write_packet()
        self.plan.write_text('{"blind_output_ids":["unknown"]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "subset"):
            web.build(self.packet, self.plan, self.output)


if __name__ == "__main__":
    unittest.main()

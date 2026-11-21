"""Compare browser-side validation with the frozen v2 human contract."""
import copy
import json
import shutil
import subprocess
import unittest
from pathlib import Path

import human_review_v2 as human


class WebContractParityTests(unittest.TestCase):
    def test_frontend_and_backend_accept_same_synthetic_records(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is required for browser/backend contract parity")
        core = Path(__file__).resolve().parents[1] / "review_web/src/review_core.js"
        identity = {key: ("a"*64 if key.endswith("sha256") else "synthetic") for key in human.IDENTITY_FIELDS}
        fixtures = []
        for original_has_errors in (True, False):
            base = {"schema_version": human.HUMAN_REVIEW_SCHEMA_VERSION, "reviewer_id": "SYNTHETIC_ONLY", "review_date": "2026-10-11", "rationale": "Fixture only, never imported.", "response_assessable": True, "meaning_preserved": True, "explanations_ok": True, "verdict": "CORRECT", **{c: 2 for c in human.CRITERIA}}
            if original_has_errors:
                base["clean_text_handling"] = "NA"
            else:
                base["detection"] = base["correction"] = "NA"
            fixtures.append({"review": base, "original": original_has_errors})
            for field in human.REVIEW_FIELDS:
                for value in (None, True, False, "NA", 0, 1, 2, "invalid"):
                    changed = copy.deepcopy(base)
                    changed[field] = value
                    fixtures.append({"review": changed, "original": original_has_errors})
            for value in ("2026-02-29", "2024-02-29", "0000-01-01", "2026-4-01"):
                changed = copy.deepcopy(base)
                changed["review_date"] = value
                fixtures.append({"review": changed, "original": original_has_errors})
            unavailable = copy.deepcopy(base)
            unavailable.update(response_assessable=False, verdict="INVALID_CASE", meaning_preserved="NA", explanations_ok="NA")
            unavailable.update({c: "NA" for c in human.CRITERIA})
            fixtures.append({"review": unavailable, "original": original_has_errors})
        script = 'const core=require(process.argv[1]);let s="";process.stdin.on("data",d=>s+=d);process.stdin.on("end",()=>console.log(JSON.stringify(JSON.parse(s).map(f=>core.validateReview(f.review,f.original).length===0))));'
        result = subprocess.run([node, "-e", script, str(core)], input=json.dumps(fixtures), text=True, encoding="utf-8", capture_output=True, check=True)
        accepted = json.loads(result.stdout)
        for fixture, js_accepted in zip(fixtures, accepted):
            condition = "incorrect" if fixture["original"] else "correct"
            errors = human.validate_human_record({**identity, **fixture["review"]}, identity, condition)
            with self.subTest(condition=condition, review=fixture["review"]):
                self.assertEqual(js_accepted, not errors)


if __name__ == "__main__":
    unittest.main()

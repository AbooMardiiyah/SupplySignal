import json
import tempfile
import unittest
from pathlib import Path

from supplysignal.release import verify
from supplysignal.versioning import sha256, training_identity


class VersioningTest(unittest.TestCase):
    def test_identity_changes_when_training_input_or_configuration_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.csv"
            ledger.write_text("consumption\n10\n")
            first = training_identity(ledger, {"seed": 42})["model_version"]
            self.assertEqual(first, training_identity(ledger, {"seed": 42})["model_version"])
            self.assertNotEqual(first, training_identity(ledger, {"seed": 43})["model_version"])
            ledger.write_text("consumption\n11\n")
            self.assertNotEqual(first, training_identity(ledger, {"seed": 42})["model_version"])

    def test_release_verification_detects_modified_or_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "predictions.csv"
            sample.write_text("forecast\n10\n")
            (root / "bundle.json").write_text(json.dumps({
                "model_version": "test", "files_sha256": {sample.name: sha256(sample)},
            }))
            self.assertEqual(verify(root)["model_version"], "test")
            sample.write_text("forecast\n999\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                verify(root)
            sample.unlink()
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                verify(root)

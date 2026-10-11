import io
import json
import logging
import unittest
from contextlib import redirect_stderr, redirect_stdout

from supplysignal.logging_config import configure_logging, run_cli


class LoggingTest(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("supplysignal")
        self.saved = (self.logger.handlers[:], self.logger.level, self.logger.propagate)
        self.logger.handlers = []

    def tearDown(self):
        self.logger.handlers, level, self.logger.propagate = self.saved
        self.logger.setLevel(level)

    def test_rerun_does_not_duplicate_logs_or_corrupt_stdout(self):
        stderr, stdout = io.StringIO(), io.StringIO()
        with redirect_stderr(stderr), redirect_stdout(stdout):
            configure_logging()
            configure_logging()
            run_cli(lambda: print('{"result": 1}'))
        self.assertEqual(json.loads(stdout.getvalue()), {"result": 1})
        events = [json.loads(line) for line in stderr.getvalue().splitlines()]
        self.assertEqual([e["event"] for e in events], ["stage_started", "stage_completed"])
        self.assertIn("elapsed_seconds", events[-1]["context"])

    def test_failure_records_traceback_and_preserves_failure(self):
        def fail():
            raise RuntimeError("test failure")
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(RuntimeError):
            run_cli(fail)
        events = [json.loads(line) for line in stderr.getvalue().splitlines()]
        self.assertEqual(events[-1]["event"], "stage_failed")
        self.assertIn("RuntimeError", events[-1]["exception"])

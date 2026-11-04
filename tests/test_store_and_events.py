import os
import tempfile
import unittest

from api import runner, store


class StoreAndEventTests(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store.init_db(self.db)

    def tearDown(self):
        os.remove(self.db)

    def test_wave_can_only_be_claimed_once(self):
        wave = store.create_wave("canary", "canary", True, self.db)
        self.assertTrue(store.claim_wave(wave["id"], self.db))
        self.assertFalse(store.claim_wave(wave["id"], self.db))
        self.assertEqual(store.get_wave(wave["id"], self.db)["status"], "RUNNING")

    def test_events_move_node_through_states(self):
        for role in ("preflight", "sssd_stage", "ad_join", "cutover", "validate"):
            runner.handle_event(
                {"event": "runner_on_ok", "event_data": {"host": "h1", "role": role, "task": "t"}},
                "w1", self.db)
        node = store.get_node("h1", db_path=self.db)
        self.assertEqual(node["state"], "VERIFIED")
        self.assertEqual(len(node["evidence"]), 5)

    def test_failure_then_rollback(self):
        runner.handle_event(
            {"event": "runner_on_failed", "event_data": {"host": "h2", "role": "cutover", "task": "t"}},
            "w1", self.db)
        self.assertEqual(store.get_node("h2", db_path=self.db)["state"], "FAILED")
        runner.handle_event(
            {"event": "runner_on_ok", "event_data": {"host": "h2", "role": "rollback", "task": "t"}},
            "w1", self.db)
        self.assertEqual(store.get_node("h2", db_path=self.db)["state"], "ROLLED_BACK")

    def test_ignored_failure_does_not_fail_node(self):
        runner.handle_event(
            {"event": "runner_on_ok", "event_data": {"host": "h3", "role": "preflight", "task": "t"}},
            None, self.db)
        runner.handle_event(
            {"event": "runner_on_failed",
             "event_data": {"host": "h3", "role": "preflight", "task": "t", "ignore_errors": True}},
            None, self.db)
        self.assertEqual(store.get_node("h3", db_path=self.db)["state"], "PREFLIGHT")


if __name__ == "__main__":
    unittest.main()

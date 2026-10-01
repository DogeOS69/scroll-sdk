import importlib.util
import os
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/status-page-delivery.py'
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location('status_delivery', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'state.sqlite3')
        self.sent = []
        self.config = {'environment': 'testnet', 'chainId': '123', 'orgId': 1, 'groupName': 'Testnet',
                       'intervalSeconds': 10, 'components': {'public-rpc': {
                           'name': 'Public RPC', 'pageId': 'page', 'componentId': 'rpc',
                           'webhookEnv': 'TEST_ONLY_WEBHOOK', 'failureSeconds': 20, 'recoverySeconds': 30}}}
        self.env = patch.dict(os.environ, TEST_ONLY_WEBHOOK='https://api.instatus.com/v3/integrations/grafana/test')
        self.env.start()
        self.delivery = self.open()
        self.firing = {'status': 'firing', 'alerts': [{'status': 'firing', 'labels': {
            'component_key': 'public-rpc', 'environment': 'testnet', 'chain_id': '123',
            'managed_by': 'scroll-sdk-status-page', 'audience': 'public-status'}}]}

    def open(self):
        return module.Delivery(self.config, self.path, lambda url, payload: self.sent.append(payload))

    def tearDown(self):
        self.delivery.db.close()
        self.env.stop()
        self.temp.cleanup()

    def tick(self, value, *times):
        for stamp in times:
            self.delivery.tick({'public-rpc': value}, stamp)
            self.delivery.deliver_once(stamp)

    def fire(self):
        self.tick(1, 100, 110, 120)
        self.assertEqual([event['status'] for event in self.sent], ['firing'])

    def test_maintenance_blocks_failure_and_requires_a_new_complete_window(self):
        self.delivery.windows = [{'start': 110, 'end': 150, 'components': ['public-rpc']}]
        self.tick(1, 100, 110, 120, 130, 140)
        self.assertEqual(self.sent, [])
        self.assertIn('scroll_status_delivery_maintenance{component_key="public-rpc"} 1', self.delivery.metrics())
        self.tick(1, 150, 160)
        self.assertEqual(self.sent, [])
        self.tick(1, 170)
        self.assertEqual([e['status'] for e in self.sent], ['firing'])

    def test_maintenance_preserves_active_incident_across_restart(self):
        self.fire()
        self.config['maintenanceWindows'] = [{'start': 130, 'end': 180, 'components': ['public-rpc']}]
        self.delivery.db.close()
        self.delivery = self.open()
        self.tick(0, 130, 140, 150, 160, 170, 180, 190, 200)
        self.assertEqual(len(self.sent), 1)
        self.tick(0, 210)
        self.assertEqual(self.sent[-1]['status'], 'resolved')
        self.assertEqual(self.sent[0]['groupKey'], self.sent[-1]['groupKey'])

    def test_another_component_maintenance_does_not_pause_this_component(self):
        self.delivery.windows = [{'start': 90, 'end': 200, 'components': ['node-sync']}]
        self.fire()

    def test_unknown_lifecycle_and_short_recovery_cannot_resolve(self):
        self.fire()
        self.tick(None, 130, 140, 150)
        self.tick(0, 160, 170)
        self.tick(None, 180)
        self.tick(0, 190, 200, 210)
        self.assertEqual(len(self.sent), 1)
        self.tick(0, 220)
        self.assertEqual([event['status'] for event in self.sent], ['firing', 'resolved'])
        self.assertEqual(self.sent[0]['alerts'][0]['startsAt'], self.sent[1]['alerts'][0]['startsAt'])
        self.assertEqual(self.sent[0]['groupKey'], self.sent[1]['groupKey'])

    def test_restart_keeps_incident_but_restarts_recovery_confirmation(self):
        self.fire()
        self.tick(0, 130, 140, 150)
        self.delivery.db.close()
        self.delivery = self.open()
        self.tick(0, 160, 170, 180)
        self.assertEqual(len(self.sent), 1)
        self.tick(0, 190)
        self.assertEqual(len(self.sent), 2)

    def test_failed_delivery_persists_identical_retry_and_stops_on_unknown(self):
        attempts = []
        def failing(url, payload):
            attempts.append(payload)
            raise TimeoutError('credential must never be logged')
        self.delivery.send = failing
        self.tick(1, 100, 110, 120, 130)
        self.assertEqual(attempts[0], attempts[1])
        self.tick(None, 140, 150)
        self.assertEqual(len(attempts), 2)
        self.assertIn('scroll_status_delivery_pending{component_key="public-rpc"} 1', self.delivery.metrics())
        self.delivery.db.close()
        self.delivery = self.open()
        self.tick(1, 160, 170, 180)
        self.assertEqual(self.sent[0], attempts[0])

    def test_uncertain_event_remains_alerted_after_restart_and_health_reversal(self):
        def uncertain(*_):
            raise TimeoutError()
        self.delivery.send = uncertain
        self.tick(1, 100, 110, 120)
        self.delivery.db.close()
        self.delivery = self.open()
        self.assertIn('scroll_status_delivery_error{component_key="public-rpc"} 1', self.delivery.metrics())
        self.tick(0, 130, 140, 150, 160, 170)
        self.assertEqual(self.sent, [])
        self.assertIn('scroll_status_delivery_error{component_key="public-rpc"} 1', self.delivery.metrics())
        self.assertIn('scroll_status_delivery_pending{component_key="public-rpc"} 1', self.delivery.metrics())

    def test_slow_provider_does_not_block_evidence_or_scrapes_and_no_parallel_duplicate(self):
        entered, release = threading.Event(), threading.Event()
        def slow(url, event):
            entered.set()
            release.wait(3)
            self.sent.append(event)
        self.delivery.send = slow
        for stamp in (100, 110, 120):
            self.delivery.tick({'public-rpc': 1}, stamp)
        worker = threading.Thread(target=lambda: self.delivery.deliver_once(120))
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            completed = threading.Event()
            def read_and_update():
                self.delivery.tick({'public-rpc': None}, 130)
                self.delivery.metrics()
                self.delivery.deliver_once(130)
                completed.set()
            reader = threading.Thread(target=read_and_update)
            reader.start()
            self.assertTrue(completed.wait(1), 'webhook holds evidence lock')
            reader.join()
        finally:
            release.set()
            worker.join()
        self.assertEqual(len(self.sent), 1)
        self.assertIn('scroll_status_delivery_incident_active{component_key="public-rpc"} 1', self.delivery.metrics())
        self.assertEqual(self.delivery.last_tick, 130)

    def test_sender_rechecks_maintenance_after_collection(self):
        self.delivery.windows = [{'start': 121, 'end': 150, 'components': ['public-rpc']}]
        for stamp in (100, 110, 120):
            self.delivery.tick({'public-rpc': 1}, stamp)
        self.delivery.deliver_once(121)
        self.assertEqual(self.sent, [])

    def test_failed_component_does_not_starve_another_pending_event(self):
        import copy
        self.delivery.db.close()
        self.config['components']['deposits'] = copy.deepcopy(self.config['components']['public-rpc'])
        self.config['components']['deposits']['componentId'] = 'deposits'
        self.delivery = self.open()
        attempts = []
        def send(url, payload):
            key = payload['alerts'][0]['labels']['component_key']
            attempts.append(key)
            if key == 'public-rpc':
                raise TimeoutError()
        self.delivery.send = send
        for stamp in (100, 110, 120):
            self.delivery.tick({'public-rpc': 1, 'deposits': 1}, stamp)
        self.delivery.deliver_once(120)
        self.delivery.deliver_once(121)
        self.delivery.deliver_once(122)
        self.assertEqual(attempts, ['public-rpc', 'deposits'])
        self.assertIn('scroll_status_delivery_incident_active{component_key="deposits"} 1', self.delivery.metrics())

    def test_failures_need_continuous_evidence_without_any_grafana_signal(self):
        self.tick(1, 100, 110)
        self.assertEqual(self.sent, [])
        self.tick(None, 120)
        self.tick(1, 200, 210)
        self.assertEqual(self.sent, [])
        self.tick(1, 220)
        self.assertEqual(len(self.sent), 1)

    def test_partial_nonbinary_future_and_stale_prometheus_responses_are_unknown(self):
        def response(value, stamp=100):
            return {'status': 'success', 'data': {'resultType': 'vector', 'result': [{'value': [stamp, value]}]}}
        self.assertEqual(module.observation(response('0'), 110, 20), 0)
        self.assertEqual(module.observation(response('1'), 110, 20), 1)
        for value in ['NaN', '2', '-1', 'inf']:
            self.assertIsNone(module.observation(response(value), 110, 20))
        self.assertIsNone(module.observation(response('0', 111), 110, 20))
        self.assertIsNone(module.observation(response('0', 10), 110, 20))
        partial = response('0')
        partial['warnings'] = ['partial response']
        self.assertIsNone(module.observation(partial, 110, 20))

    def test_observe_mode_never_publishes(self):
        self.delivery.components['public-rpc']['mode'] = 'observe'
        self.tick(1, 100, 110, 120, 130)
        self.assertEqual(self.sent, [])

    def test_rebinding_existing_journal_is_rejected(self):
        self.fire()
        self.config['components']['public-rpc']['componentId'] = 'different'
        with self.assertRaisesRegex(ValueError, 'target changed'):
            self.open()


if __name__ == '__main__':
    unittest.main()

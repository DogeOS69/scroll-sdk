"""Scoped routing must never replace unrelated policies or operator edits."""
import copy
import unittest

from test_seed_grafana_alerts import MemoryGrafana, SEED


class NotificationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.client = MemoryGrafana()
        self.config = {'folderUID': 'test', 'businessPodContactPoint': 'slack-alerts',
                       'diskContactPoint': 'slack-alerts', 'resourceContactPoint': 'slack-alerts'}
        self.client.policies = {
            'receiver': 'existing-default', 'group_by': ['alertname'],
            'group_wait': '1m', 'repeat_interval': '8h',
            'routes': [{'receiver': 'another-team', 'object_matchers': [['team', '=', 'other']],
                        'continue': True, 'mute_time_intervals': ['maintenance'],
                        'routes': [{'receiver': 'another-team', 'object_matchers': [['service', '=', 'db']]}]}],
        }

    def test_addition_preserves_root_and_unrelated_routes_exactly(self):
        original = copy.deepcopy(self.client.policies)
        SEED.seed_notification_policies(self.client, self.config)
        self.assertEqual(self.client.policies['routes'][3:], original['routes'])
        self.assertEqual({k: v for k, v in self.client.policies.items() if k != 'routes'},
                         {k: v for k, v in original.items() if k != 'routes'})
        for scope, route in SEED.notification_routes(self.config).items():
            self.assertIn(['scroll_monitor_route', '=', SEED.notification_route_id(self.config, scope)],
                          route['object_matchers'])
            self.assertFalse(route['continue'])
            self.assertNotIn('alertname', route['group_by'])
            self.assertEqual(route['routes'][0]['object_matchers'], [['severity', '=', 'critical']])
        self.assertEqual(len(self.client.writes), 1)

    def test_repeat_and_ui_edits_are_preserved_even_when_moved(self):
        SEED.seed_notification_policies(self.client, self.config)
        existing = self.client.policies['routes'].pop(0)
        existing['group_wait'] = '3m'
        existing['receiver'] = 'operator-contact'
        self.client.policies['routes'][-1]['routes'].append(existing)
        before = copy.deepcopy(self.client.policies)
        self.client.writes.clear()
        SEED.seed_notification_policies(self.client, self.config)
        self.assertEqual(self.client.policies, before)
        self.assertEqual(self.client.writes, [])

    def test_dry_run_does_not_write(self):
        before = copy.deepcopy(self.client.policies)
        SEED.seed_notification_policies(self.client, self.config, dry_run=True)
        self.assertEqual(self.client.policies, before)
        self.assertEqual(self.client.writes, [])

    def test_unreadable_tree_is_never_replaced(self):
        for invalid in (None, {}, []):
            self.client.policies = invalid
            with self.assertRaisesRegex(RuntimeError, 'refusing to replace'):
                SEED.seed_notification_policies(self.client, self.config)
        self.assertEqual(self.client.writes, [])

    def test_empty_contacts_leave_routing_untouched(self):
        before = copy.deepcopy(self.client.policies)
        SEED.seed_notification_policies(self.client, {'folderUID': 'test'})
        self.assertEqual(self.client.policies, before)
        self.assertEqual(self.client.writes, [])


if __name__ == '__main__':
    unittest.main()

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('node_sync', Path(__file__).resolve().parents[1] / 'scripts/status-page-node-sync.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def node(name):
    return {'uid': name, 'name': name, 'addresses': ['10.0.0.1'], 'ready': True}


def block(height, digest=None):
    return {'number': hex(height), 'timestamp': hex(1000 + height * 3), 'hash': digest or '0x' + f'{height:064x}'}


class Fake:
    def __init__(self):
        self.pods = {'seq': [node('seq-0')], 'boot': [node('boot-0')], 'rpc': [node('rpc-0'), node('rpc-1')], 'public': [node('public-0')]}
        self.heads = {p['name']: 100 for pods in self.pods.values() for p in pods}
        self.chains = {}
        self.hashes = {}
        self.calls = []
        self.hook = None

    def discover(self, source):
        result = copy.deepcopy(self.pods[source['service']])
        self.calls.append(('discover', source['service']))
        if self.hook:
            self.hook(self.calls[-1])
        return result

    def rpc(self, pod, source, method, params):
        name = pod['name']
        self.calls.append((name, method, params))
        if self.hook:
            self.hook(self.calls[-1])
        if method == 'eth_chainId':
            return hex(self.chains.get(name, 221122))
        height = self.heads[name] if params[0] == 'latest' else int(params[0], 16)
        return block(height, self.hashes.get((name, height)))


class NodeSyncTests(unittest.TestCase):
    def setUp(self):
        source = lambda name, role, replicas: {'service': name, 'role': role, 'replicas': replicas, 'port': 8545}
        self.config = {'chainId': '221122', 'environment': 'devnet', 'maxBlockAgeSeconds': 120, 'maxNodeLagSeconds': 120,
                       'reference': source('seq', 'sequencer', 1), 'followers': [source('boot', 'bootnode', 1), source('rpc', 'internal-rpc', 2), source('public', 'public-rpc', 1)]}
        self.client = Fake()

    def observe(self):
        return mod.observe(self.config, self.client, 1300)

    def test_sequencing_stale_reference_is_affected_but_follower_failure_is_not(self):
        self.client.heads['rpc-1'] = 0
        self.assertEqual(mod.sequencing(self.config, self.client, 1300), 0)
        self.assertEqual(mod.sequencing(self.config, self.client, 1421), 1)
        self.client.chains['seq-0'] = 1
        with self.assertRaises(mod.Unknown):
            mod.sequencing(self.config, self.client, 1300)

    def test_sequencing_missing_or_future_reference_is_unknown(self):
        with self.assertRaises(mod.Unknown):
            mod.sequencing(self.config, self.client, 1299)
        self.client.pods['seq'] = []
        with self.assertRaises(mod.Unknown):
            mod.sequencing(self.config, self.client, 1300)

    def test_every_replica_is_checked_and_normal_head_race_is_allowed(self):
        self.client.heads['rpc-0'] = 99
        self.client.heads['rpc-1'] = 101
        # A head sampled later may advance but must not claim a future block time.
        result = mod.observe(self.config, self.client, 1303)
        self.assertEqual(len(result), 4)
        self.assertEqual([r[2] for r in result], [0, 0, 0, 0])
        self.assertEqual({r[1] for r in result}, {'boot-0', 'rpc-0', 'rpc-1', 'public-0'})

    def test_one_bad_replica_is_not_masked_by_healthy_replica(self):
        self.client.heads['rpc-1'] = 59
        result = self.observe()
        self.assertEqual(next(r for r in result if r[1] == 'rpc-1')[2:], (1, 'lag'))
        self.assertIn(b'scroll_status_node_sync_affected{environment="devnet",chain_id="221122",component_key="node-sync"} 1', mod.metrics(self.config, result, 1300))

    def test_lag_boundary_and_same_height_fork(self):
        self.client.heads['rpc-1'] = 60  # Exactly 120 seconds is tolerated.
        self.assertFalse(any(r[2] for r in self.observe()))
        self.client.hashes['rpc-1', 60] = '0x' + 'f' * 64
        self.assertEqual(next(r for r in self.observe() if r[1] == 'rpc-1')[2:], (1, 'hash_mismatch'))

    def test_reference_loss_wrong_chain_stale_or_future_is_unknown(self):
        for mutation in [lambda: self.client.pods['seq'].clear(),
                         lambda: self.client.pods['seq'][0].update(ready=False),
                         lambda: self.client.chains.update({'seq-0': 1}),
                         lambda: self.client.heads.update({'seq-0': 59}),
                         lambda: self.client.heads.update({'seq-0': 101})]:
            self.client = Fake()
            mutation()
            with self.assertRaises(mod.Unknown):
                self.observe()
        body = mod.metrics(self.config, None, 1300)
        self.assertNotIn(b'_affected', body)

    def test_not_ready_and_wrong_chain_are_affected(self):
        self.client.pods['boot'][0]['ready'] = False
        self.client.chains['rpc-1'] = 1
        result = self.observe()
        self.assertIn(('bootnode', 'boot-0', 1, 'not_ready'), result)
        self.assertIn(('internal-rpc', 'rpc-1', 1, 'wrong_chain'), result)

    def test_missing_extra_or_overlapping_pods_are_unknown(self):
        for mutation in [lambda: self.client.pods['rpc'].pop(),
                         lambda: self.client.pods['rpc'].append(node('rpc-2')),
                         lambda: self.client.pods.update({'boot': [node('seq-0')]})]:
            self.client = Fake()
            mutation()
            with self.assertRaises(mod.Unknown):
                self.observe()

    def test_membership_change_and_reference_reorg_invalidate_round(self):
        def change(call):
            if call == ('seq-0', 'eth_getBlockByNumber', ['0x64', False]):
                self.client.pods['rpc'][1]['uid'] = 'replacement'
        self.client.hook = change
        with self.assertRaisesRegex(mod.Unknown, 'population_changed'):
            self.observe()
        self.client = Fake()
        def reorg(call):
            if call == ('seq-0', 'eth_getBlockByNumber', ['0x64', False]):
                self.client.hashes['seq-0', 100] = '0x' + 'f' * 64
        self.client.hook = reorg
        with self.assertRaisesRegex(mod.Unknown, 'reference_reorg'):
            self.observe()

    def test_follower_reorg_and_rpc_failure_cannot_publish_recovery(self):
        def reorg(call):
            if call == ('boot-0', 'eth_getBlockByNumber', ['0x64', False]):
                self.client.hashes['boot-0', 100] = '0x' + 'f' * 64
        self.client.hook = reorg
        with self.assertRaisesRegex(mod.Unknown, 'follower_reorg'):
            self.observe()
        def failure(call):
            if call[0] == 'rpc-1':
                raise TimeoutError()
        self.client.hook = failure
        with self.assertRaises(TimeoutError):
            self.observe()

    def test_slice_deduplication_and_fail_closed_discovery(self):
        entry = {'targetRef': {'kind': 'Pod', 'uid': 'uid', 'name': 'rpc-0'}, 'addresses': ['10.0.0.1'], 'conditions': {'ready': True}}
        slice_ = {'addressType': 'IPv4', 'ports': [{'port': 8545}], 'endpoints': [entry]}
        document = {'items': [slice_, copy.deepcopy(slice_)]}
        document['items'][1]['addressType'] = 'IPv6'
        document['items'][1]['endpoints'][0]['addresses'] = ['fd00::1']
        self.assertEqual(len(mod.members(document, 8545)), 1)
        self.assertEqual(len(mod.members(document, 8545)[0]['addresses']), 2)
        for change in [lambda d: d.update(metadata={'continue': 'more'}),
                       lambda d: d['items'][0]['ports'].clear(),
                       lambda d: d['items'][0]['endpoints'][0].pop('targetRef'),
                       lambda d: d['items'][0]['endpoints'][0]['conditions'].update(ready=False)]:
            changed = copy.deepcopy(document)
            change(changed)
            with self.assertRaises(mod.Unknown):
                mod.members(changed, 8545)

    def test_invalid_blocks_do_not_become_health(self):
        for value in [None, {}, {'number': '0x1', 'timestamp': 'nope', 'hash': '0x' + 'f' * 64},
                      {'number': '0x1', 'timestamp': '0x1', 'hash': 'invalid'}]:
            with self.assertRaises(mod.Unknown):
                mod.block(value)
        with self.assertRaisesRegex(mod.Unknown, 'wrong_height'):
            mod.block(block(1), 2)

    def test_reference_aging_during_round_is_unknown(self):
        clock = [1300]
        def age(call):
            if call == ('seq-0', 'eth_getBlockByNumber', ['0x64', False]):
                clock[0] = 1421
        self.client.hook = age
        with patch.object(mod.time, 'time', side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(mod.Unknown, 'reference_stale'):
                mod.observe(self.config, self.client)


if __name__ == '__main__':
    unittest.main()

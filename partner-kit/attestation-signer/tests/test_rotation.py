"""Run with Python 3.11+, or the Docker runtime documented in rotation.md."""
import copy
import importlib.util
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('rotation', Path(__file__).parents[1] / 'scripts/rotation.py')
rotation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rotation)


def public_keys(count):
    # Synthetic public curve points, with no associated stored private keys.
    result = []
    x = 100
    while len(result) < count:
        candidate = '02' + format(x, '064x')
        try:
            rotation.public_key(candidate)
            result.append(candidate)
        except ValueError:
            pass
        x += 1
    return result


KEYS = public_keys(14)


def script(attestation, recovery=None, tee=None, height=500000):
    recovery = recovery or KEYS[7:10]
    tee = tee or KEYS[6]
    def multisig(keys):
        return bytes([82]) + b''.join(bytes([33]) + bytes.fromhex(key) for key in keys) + bytes([80 + len(keys), 175])
    encoded = height.to_bytes(4, 'little').rstrip(b'\0')
    if encoded[-1] & 128:
        encoded += b'\0'
    return (b'\x14' + bytes.fromhex('ab' * 20) + b'\x75\x63' + multisig(attestation)
            + b'\x21' + bytes.fromhex(tee) + b'\xad\x67' + bytes([len(encoded)]) + encoded
            + b'\xb1\x75' + multisig(recovery) + b'\x68\x51').hex()


def envelope():
    old = script(KEYS[:3])
    new = script(KEYS[3:6], height=600000)
    target_hash = rotation.hash160(new)
    proposal = {
        'schema': 'dogeos/attestation-rotation/v1', 'name': 'test-rotation', 'network': 'testnet',
        'deployment': {'protocolContextSha256': 'aa' * 32, 'namespace': 'ab' * 20},
        'current': {'keyHash': rotation.hash160(old), 'redeemScriptHex': old},
        'target': {'keyHash': target_hash, 'redeemScriptHex': new,
                   'address': rotation.address(target_hash, 'testnet'), 'threshold': 2,
                   'signers': [{'name': 'signer-' + str(i), 'attestationPubkey': KEYS[i + 3],
                                'transportPubkey': KEYS[i + 10]} for i in range(3)]},
        'timelock': {'policy': 'refresh', 'oldHeight': 500000, 'newHeight': 600000, 'anchorHeight': 100000},
        'observedWfTxNumber': 100, 'graceWfTxs': 100,
    }
    return {'proposal': proposal, 'sha256': rotation.digest(proposal)}


class RotationTest(unittest.TestCase):
    def verify(self, item):
        return rotation.verify(item, item['sha256'], item['proposal']['current']['keyHash'])

    def rehash(self, item):
        p = item['proposal']
        p['target']['keyHash'] = rotation.hash160(p['target']['redeemScriptHex'])
        p['target']['address'] = rotation.address(p['target']['keyHash'], p['network'])
        item['sha256'] = rotation.digest(p)
        return item

    def test_valid_disjoint_proposal(self):
        self.verify(envelope())

    def test_mismatched_digest_and_independent_current_hash(self):
        item = envelope()
        item['proposal']['graceWfTxs'] += 1
        with self.assertRaises(ValueError):
            self.verify(item)
        item = envelope()
        with self.assertRaises(ValueError):
            rotation.verify(item, item['sha256'], '0x' + '00' * 20)

    def test_rejects_tee_recovery_order_and_overlap(self):
        for modified in [script(KEYS[3:6], tee=KEYS[13], height=600000),
                         script(KEYS[3:6], recovery=list(reversed(KEYS[7:10])), height=600000),
                         script([KEYS[0], *KEYS[4:6]], height=600000)]:
            item = envelope()
            item['proposal']['target']['redeemScriptHex'] = modified
            with self.assertRaises(ValueError):
                self.verify(self.rehash(item))

    def test_dishonest_members_address_and_timelock(self):
        item = envelope()
        changes = [('address', 'not-an-address'), ('threshold', 1)]
        for field, value in changes:
            changed = copy.deepcopy(item)
            changed['proposal']['target'][field] = value
            changed['sha256'] = rotation.digest(changed['proposal'])
            with self.assertRaises(ValueError):
                self.verify(changed)
        item['proposal']['timelock']['anchorHeight'] = 500000
        item['sha256'] = rotation.digest(item['proposal'])
        with self.assertRaises(ValueError):
            self.verify(item)

    def test_strict_script_parser(self):
        raw = script(KEYS[:3])
        for invalid in [raw + '51', raw[:-2], '4c14' + raw[2:], raw.replace('ad67', 'ac67')]:
            with self.assertRaises(ValueError):
                rotation.parse_script(invalid)

    def test_patch_preserves_semantics_and_text(self):
        text = '# keep comment\n[trust]\nurl = "https://fake.invalid"\n\n[rotation_policy]\n# approval\nallowed_next_bridge_script_hashes = [\n  "0x' + '11' * 20 + '", # existing\n]\nallowed_next_sequencer_signers = []\n\n[tail]\ncount = 42\n'
        target = '0x' + '22' * 20
        changed = rotation.patch_policy(text, target)
        self.assertIn('# keep comment', changed)
        self.assertIn('allowed_next_sequencer_signers = []', changed)
        before = rotation.tomllib.loads(text)
        before['rotation_policy']['allowed_next_bridge_script_hashes'].append(target)
        self.assertEqual(before, rotation.tomllib.loads(changed))
        self.assertEqual(changed, rotation.patch_policy(changed, target))

    def test_patch_no_table_or_final_newline_and_reject_inline_table(self):
        target = '0x' + '22' * 20
        for text in ['[trust]\nx = 1', '[rotation_policy]\nallowed_next_bridge_script_hashes = []']:
            self.assertIn(target, rotation.patch_policy(text, target))
        with self.assertRaises(ValueError):
            rotation.patch_policy('rotation_policy = { allowed_next_bridge_script_hashes = [] }', target)

    def test_approval_keeps_inode_and_backup_private(self):
        item = envelope()
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'signer.toml'
            original = '[trust]\nurl = "https://fake.invalid"\n'
            config.write_text(original)
            inode = config.stat().st_ino
            proposal = Path(folder) / 'proposal.json'
            proposal.write_text(json.dumps(item))
            with patch('sys.argv', ['rotation.py', 'approve', '--proposal', str(proposal),
                                   '--expected-sha256', item['sha256'], '--current-key-hash', item['proposal']['current']['keyHash'],
                                   '--config', str(config), '--signer-public-key', KEYS[0]]):
                rotation.main()
            self.assertEqual(inode, config.stat().st_ino)
            backups = list(Path(folder).glob('*.before-rotation-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), original)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_readiness_checks_identity_enforce_and_both_capabilities(self):
        report = {'public_key': KEYS[3], 'network': 'testnet', 'policy_mode': 'enforce',
                  'v2_capabilities': [{'capability': 'advance_l1', 'production_serving': True},
                                      {'capability': 'advance_l2', 'production_serving': True}]}
        with patch.object(rotation.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(report).encode())):
            rotation.policy_status(4040, KEYS[3], 'testnet', False, True)
        for changed in [dict(report, public_key=KEYS[0]), dict(report, policy_mode='scaffold'),
                        dict(report, v2_capabilities=report['v2_capabilities'][:1])]:
            with patch.object(rotation.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(changed).encode())):
                with self.assertRaises(ValueError):
                    rotation.policy_status(4040, KEYS[3], 'testnet', False, True)

    def test_readiness_requires_explicit_tso_acknowledgement(self):
        item = envelope()
        with tempfile.TemporaryDirectory() as folder:
            proposal = Path(folder) / 'proposal.json'
            proposal.write_text(json.dumps(item))
            config = Path(folder) / 'signer.toml'
            config.write_text('[rotation_policy]\n')
            args = ['rotation.py', 'ready', '--proposal', str(proposal),
                    '--expected-sha256', item['sha256'], '--current-key-hash', item['proposal']['current']['keyHash'],
                    '--config', str(config), '--signer-public-key', KEYS[3], '--transport-public-key', KEYS[10]]
            with patch('sys.argv', args), patch.object(rotation, 'policy_status') as check:
                with self.assertRaises(ValueError):
                    rotation.main()
                check.assert_not_called()
            with patch('sys.argv', [*args, '--acknowledge-tso-connected']), patch.object(rotation, 'policy_status') as check:
                rotation.main()
                check.assert_called_once_with(4040, KEYS[3], 'testnet', False, True)
            receipt = json.loads(next(Path(folder).glob('rotation-readiness-*.json')).read_text())
            self.assertTrue(receipt['tsoConnected'])
            self.assertEqual(receipt['transportPubkey'], KEYS[10])
            self.assertEqual(config.read_text(), '[rotation_policy]\n')

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.json'
            path.write_text('{"sha256": "first", "sha256": "second"}')
            with self.assertRaises(ValueError):
                rotation.read_json(path)


if __name__ == '__main__':
    unittest.main()

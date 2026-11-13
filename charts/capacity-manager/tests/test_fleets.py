"""Offline tests against real dstack 0.21.5 models; no cloud or server calls."""
import importlib.util
import pathlib
import sys
import types
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

sys.dont_write_bytecode = True
from dstack._internal.core.backends.aws.models import AWSBackendConfigWithCreds
from dstack._internal.core.backends.models import BackendInfo
from dstack._internal.core.models.fleets import ApplyFleetPlanInput, Fleet, FleetSpec, FleetStatus

source = pathlib.Path(__file__).resolve().parents[1] / 'files/initialize-fleets.py'
spec = importlib.util.spec_from_file_location('capacity_credentials', source)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def payload():
    return {'project': 'provers', 'fleetAction': 'create', 'fleets': [{
        'type': 'fleet', 'name': 'workers', 'nodes': {'min': 0, 'target': 0, 'max': 2},
        'resources': {'cpu': '16..', 'memory': '64GB..', 'disk': {'size': '200GB..'},
                      'gpu': {'name': ['RTX4090'], 'count': 1, 'vendor': 'nvidia'}},
        'backends': ['vastai'], 'regions': ['us-texas'], 'max_price': 0.8,
        'idle_duration': '600s', 'spot_policy': 'on-demand'}]}


class Client:
    def __init__(self):
        self.existing = []
        self.secret = Mock()
        self.projects = types.SimpleNamespace(get=lambda _: types.SimpleNamespace(backends=[BackendInfo.model_validate({'name': name, 'config': {'type': name}}) for name in ['aws', 'vastai']]))
        self.applied = []
        self.plan_transform = lambda spec: spec
        self.plan_current = None
        self.plan_action = None
        self.fleets = types.SimpleNamespace(list=lambda project: self.existing, get_plan=self.get_plan, apply_plan=self.apply)
        self.secrets = types.SimpleNamespace(create_or_update=self.secret)

    def get_plan(self, project, spec):
        effective = self.plan_transform(spec.model_copy(deep=True))
        current = self.plan_current or next((f for f in self.existing if f.name == spec.configuration.name), None)
        action = self.plan_action or ('update' if current is not None else 'create')
        return types.SimpleNamespace(action=action, current_resource=current, get_effective_spec=lambda: effective)

    def apply(self, project, plan, force):
        assert isinstance(plan, ApplyFleetPlanInput)
        assert not force
        assert plan.spec.configuration.nodes.target == 0
        self.applied.append(plan)
        if plan.current_resource is not None:
            # dstack refuses an apply against a fleet that changed since it was read.
            fleet = next(f for f in self.existing if f.id == plan.current_resource.id)
            assert canonical_equal(fleet.spec, plan.current_resource.spec)
            fleet.spec = plan.spec
            return fleet
        fleet = Fleet(id=uuid.uuid4(), name=plan.spec.configuration.name, project_name=project, spec=plan.spec,
                      created_at=datetime.now(timezone.utc), status=FleetStatus.ACTIVE, instances=[])
        self.existing.append(fleet)
        return fleet


def canonical_equal(a, b):
    return adapter.canonical(a) == adapter.canonical(b)


class CapacityFleets(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.payload = payload()

    def test_create_empty_then_idempotent_retry_and_reuse(self):
        self.assertEqual(adapter.prepare(self.client, self.payload)['createdEmptyFleets'], 1)
        self.assertEqual(adapter.prepare(self.client, self.payload)['createdEmptyFleets'], 0)
        self.payload['fleetAction'] = 'reuse'
        self.assertEqual(adapter.prepare(self.client, self.payload)['createdEmptyFleets'], 0)
        self.assertEqual(len(self.client.applied), 1)
        # The manager mints per-run credentials from its master;
        # preparation never writes a worker secret into the project.
        self.client.secret.assert_not_called()

    def test_vast_reliability_is_retained_and_drift_blocks_reuse(self):
        self.payload['fleets'][0]['backend_options'] = [
            {'type': 'vastai', 'min_reliability': 0.99, 'offer_order': 'price'}]
        adapter.prepare(self.client, self.payload)
        stored = self.client.applied[0].spec.model_dump(mode='json')
        self.assertEqual(stored['configuration']['backend_options'][0]['min_reliability'], 0.99)
        self.payload['fleets'][0]['backend_options'][0]['min_reliability'] = 0.95
        with self.assertRaisesRegex(adapter.PreparationError, 'differs'):
            adapter.prepare(self.client, self.payload)
        self.assertEqual(len(self.client.applied), 1)

    def test_missing_reuse_never_creates_or_writes_token(self):
        self.payload['fleetAction'] = 'reuse'
        with self.assertRaisesRegex(adapter.PreparationError, 'missing'):
            adapter.prepare(self.client, self.payload)
        self.assertFalse(self.client.applied)
        self.client.secret.assert_not_called()

    def test_mismatch_checks_all_fleets_before_mutations(self):
        adapter.prepare(self.client, self.payload)
        self.client.secret.reset_mock()
        self.payload['fleets'].insert(0, dict(self.payload['fleets'][0], name='new-fleet'))
        self.payload['fleets'][1]['max_price'] = 99
        with self.assertRaisesRegex(adapter.PreparationError, 'differs'):
            adapter.prepare(self.client, self.payload)
        self.assertEqual(len(self.client.applied), 1)
        self.client.secret.assert_not_called()

    def test_changed_server_policy_or_concurrent_create_are_not_applied(self):
        def changed(spec):
            spec.configuration.nodes.target = 1
            return spec
        self.client.plan_transform = changed
        with self.assertRaisesRegex(adapter.PreparationError, 'changed'):
            adapter.prepare(self.client, self.payload)
        self.assertFalse(self.client.applied)
        self.client.secret.assert_not_called()
        self.client.plan_current = object()
        with self.assertRaisesRegex(adapter.PreparationError, 'concurrently'):
            adapter.prepare(self.client, self.payload)
        self.assertFalse(self.client.applied)

    def test_nonempty_initial_fleet_is_rejected(self):
        self.payload['fleets'][0]['nodes']['target'] = 1
        with self.assertRaisesRegex(adapter.PreparationError, 'zero initial'):
            adapter.prepare(self.client, self.payload)
        self.assertFalse(self.client.applied)
        self.client.secret.assert_not_called()

    def test_terminated_fleet_is_not_reused(self):
        adapter.prepare(self.client, self.payload)
        self.client.existing[0].status = FleetStatus.TERMINATING
        with self.assertRaisesRegex(adapter.PreparationError, 'not active'):
            adapter.prepare(self.client, self.payload)

    def test_profile_fields_are_compared_by_effective_meaning(self):
        adapter.prepare(self.client, self.payload)
        stored = self.client.existing[0].spec.model_dump(mode='json')
        stored['profile']['max_price'] = stored['configuration'].pop('max_price')
        stored['profile']['name'] = 'operator-profile'
        self.client.existing[0].spec = FleetSpec.model_validate(stored)
        self.assertEqual(adapter.prepare(self.client, self.payload)['createdEmptyFleets'], 0)
        stored['profile']['max_price'] = 2
        self.client.existing[0].spec = FleetSpec.model_validate(stored)
        with self.assertRaisesRegex(adapter.PreparationError, 'differs'):
            adapter.prepare(self.client, self.payload)

    def test_missing_project_backend_fails_before_mutation(self):
        self.client.projects.get = lambda _: types.SimpleNamespace(backends=[])
        with self.assertRaisesRegex(adapter.PreparationError, 'backend is missing'):
            adapter.prepare(self.client, self.payload)
        self.assertFalse(self.client.applied)
        self.client.secret.assert_not_called()

    def test_aws_models_with_explicit_vpc_and_workload_credentials(self):
        config = {'type': 'aws', 'regions': ['us-east-1'], 'vpc_ids': {'us-east-1': 'vpc-00000000000000000'},
                  'creds': {'type': 'default'}, 'default_vpcs': False, 'public_ips': False}
        backend = AWSBackendConfigWithCreds.model_validate(config)
        self.assertFalse(backend.default_vpcs)
        self.payload['fleets'][0].update(backends=['aws'], regions=['us-east-1'], instance_types=['g6.4xlarge'])
        self.payload['fleets'][0]['resources']['gpu']['name'] = ['L4']
        self.assertEqual(adapter.prepare(self.client, self.payload)['createdEmptyFleets'], 1)

    def test_update_changes_existing_fleets_in_place_against_the_read_fleet(self):
        adapter.prepare(self.client, self.payload)
        original = self.client.existing[0].id
        self.payload['fleetAction'] = 'update'
        self.payload['fleets'][0].update(max_price=0.9, regions=['us-texas', 'us-colorado'], nodes={'min': 0, 'target': 0, 'max': 4})
        self.payload['fleets'][0]['resources']['gpu']['name'] = ['RTX3090']
        self.payload['fleets'].append(dict(self.payload['fleets'][0], name='fallback'))
        result = adapter.prepare(self.client, self.payload)
        self.assertEqual((result['createdEmptyFleets'], result['updatedFleets']), (1, 1))
        update = self.client.applied[1]
        self.assertEqual(update.current_resource.id, original)
        stored = self.client.existing[0].spec.configuration
        self.assertEqual((stored.max_price, stored.regions, stored.nodes.max), (0.9, ['us-texas', 'us-colorado'], 4))
        self.assertEqual(adapter.prepare(self.client, self.payload)['updatedFleets'], 0)
        self.assertEqual(len(self.client.applied), 3)
        self.client.secret.assert_not_called()

    def test_update_refuses_fields_dstack_cannot_update_before_any_write(self):
        adapter.prepare(self.client, self.payload)
        self.payload['fleetAction'] = 'update'
        self.payload['fleets'].insert(0, dict(self.payload['fleets'][0], name='new-fleet'))
        self.payload['fleets'][1].update(idle_duration='900s', max_price=0.9)
        with self.assertRaisesRegex(adapter.PreparationError, r'cannot update in place \(idle_duration\)'):
            adapter.prepare(self.client, self.payload)
        self.payload['fleets'][1]['idle_duration'] = '600s'
        stored = self.client.existing[0].spec.model_dump(mode='json')
        stored['profile']['name'] = 'operator-profile'
        self.client.existing[0].spec = FleetSpec.model_validate(stored)
        with self.assertRaisesRegex(adapter.PreparationError, r'cannot update in place \(profile\)'):
            adapter.prepare(self.client, self.payload)
        self.assertEqual(len(self.client.applied), 1)

    def test_update_refuses_a_recreate_plan_or_a_concurrent_change(self):
        adapter.prepare(self.client, self.payload)
        self.payload['fleetAction'] = 'update'
        self.payload['fleets'][0]['max_price'] = 0.9
        self.client.plan_action = 'create'
        with self.assertRaisesRegex(adapter.PreparationError, 'cannot update the fleet in place'):
            adapter.prepare(self.client, self.payload)
        self.client.plan_action = None
        self.client.plan_current = self.client.existing[0].model_copy(update={'id': uuid.uuid4()})
        with self.assertRaisesRegex(adapter.PreparationError, 'changed concurrently'):
            adapter.prepare(self.client, self.payload)
        self.client.plan_current = None
        def changed(spec):
            spec.configuration.nodes.max = 9
            return spec
        self.client.plan_transform = changed
        with self.assertRaisesRegex(adapter.PreparationError, 'changed the requested fleet plan'):
            adapter.prepare(self.client, self.payload)
        self.assertEqual(len(self.client.applied), 1)
        self.assertEqual(self.client.existing[0].spec.configuration.max_price, 0.8)

    def test_update_still_refuses_inactive_fleets(self):
        adapter.prepare(self.client, self.payload)
        self.client.existing[0].status = FleetStatus.TERMINATING
        self.payload['fleetAction'] = 'update'
        with self.assertRaisesRegex(adapter.PreparationError, 'not active'):
            adapter.prepare(self.client, self.payload)


if __name__ == '__main__':
    unittest.main()

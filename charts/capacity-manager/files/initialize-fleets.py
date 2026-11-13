"""Prepare reviewed empty fleets using dstack 0.21.5.

Workers get per-run credentials minted by the capacity manager. This adapter
prepares fleet configuration without storing worker secrets in the project.

Runs as a Helm initialization Job before the manager is installed. API/provider exceptions may contain credentials and
are deliberately omitted. Never starts runs or forces an apply. Existing fleets
change only with fleetAction update, only in the fields dstack updates in place,
and only against the fleet that was read (optimistic concurrency). dstack then
recycles idle or provisioning instances that no longer match; busy instances are
never terminated. Project/backend configuration comes from the controller server config.
"""
import importlib.metadata
import json
import os
import sys

from dstack._internal.core.models.fleets import ApplyFleetPlanInput, FleetSpec
from dstack._internal.core.models.profiles import ProfileParams
from dstack.api.server import APIClient


# dstack 0.21.5 updates these cloud fleet fields in place; any other change needs a new fleet.
UPDATABLE = frozenset({'nodes', 'resources', 'backends', 'regions', 'instance_types', 'spot_policy', 'max_price'})


class PreparationError(Exception):
    """Only locally constructed, public diagnostic messages."""


def canonical(spec):
    # dstack merges configuration placement fields over the selected profile.
    # Compare that effective meaning, not where a field was written or the
    # operator's profile name. All other configuration fields remain checked.
    config = spec.configuration.model_dump(mode='json')
    for field in ProfileParams.model_fields:
        config.pop(field, None)
    profile = spec.merged_profile.model_dump(mode='json', exclude={'name', 'default'})
    return {'configuration': config, 'profile': profile}


def changed_fields(current, desired):
    """Field names whose effective meaning differs, in configuration or merged profile."""
    a, b = canonical(current), canonical(desired)
    return {key for section in ('configuration', 'profile')
            for key in set(a[section]) | set(b[section]) if a[section].get(key) != b[section].get(key)}


def prepare(client, payload):
    project = payload['project']
    if payload['fleetAction'] not in ('create', 'reuse', 'update') or not payload['fleets']:
        raise PreparationError('Provide a valid fleetAction and nonempty initialization.fleets')
    desired = [FleetSpec.model_validate({'configuration': c, 'profile': {}})
               for c in payload['fleets']]
    for spec in desired:
        nodes = spec.configuration.nodes
        if spec.configuration.ssh_config or not nodes or nodes.min != 0 or nodes.target != 0 or not nodes.max:
            raise PreparationError('Fleet preparation requires zero initial/minimum instances and a finite maximum')
    if len({s.configuration.name for s in desired}) != len(desired):
        raise PreparationError('Duplicate fleet names')
    # Project metadata exposes backend types, without reading provider credentials.
    backends = {backend.config.type for backend in client.projects.get(project).backends}
    if any(not spec.merged_profile.backends or not set(spec.merged_profile.backends).issubset(backends) for spec in desired):
        raise PreparationError('Selected provider backend is missing from the project; check controller startup configuration')
    # A successful list distinguishes absence from authentication/project errors.
    existing = {fleet.name: fleet for fleet in client.fleets.list(project)}
    # Validate every existing fleet before performing any writes.
    for spec in desired:
        fleet = existing.get(spec.configuration.name)
        if fleet and fleet.status.value not in ('active', 'submitted'):
            raise PreparationError('Existing fleet is not active; no fleet was changed')
        if fleet and canonical(fleet.spec) != canonical(spec):
            if payload['fleetAction'] != 'update':
                raise PreparationError('Existing fleet differs from the reviewed configuration; no fleet was changed')
            fixed = sorted(changed_fields(fleet.spec, spec) - UPDATABLE)
            if fixed:
                raise PreparationError(f'Existing fleet {spec.configuration.name} differs in fields dstack cannot update in place '
                                       f'({", ".join(fixed)}); declare a fleet with a new name. No fleet was changed')
        if not fleet and payload['fleetAction'] == 'reuse':
            raise PreparationError('Required existing fleet is missing; choose create or prepare the declared fleet')
    created = updated = 0
    for spec in desired:
        fleet = existing.get(spec.configuration.name)
        if fleet:
            if canonical(fleet.spec) == canonical(spec):
                continue
            plan = client.fleets.get_plan(project, spec)
            current = plan.current_resource
            if current is None or current.id != fleet.id or getattr(plan.action, 'value', plan.action) != 'update':
                raise PreparationError('Dstack cannot update the fleet in place or it changed concurrently; retry or declare a fleet with a new name')
            if canonical(plan.get_effective_spec()) != canonical(spec):
                raise PreparationError('Dstack changed the requested fleet plan; review controller policies before retrying')
            # force=False with the fleet just read: dstack refuses if it changed since.
            result = client.fleets.apply_plan(project, ApplyFleetPlanInput(spec=spec, current_resource=current), force=False)
            if canonical(result.spec) != canonical(spec):
                raise PreparationError('Updated fleet readback differs; inspect controller policies before continuing')
            updated += 1
            continue
        plan = client.fleets.get_plan(project, spec)
        if plan.current_resource is not None:
            raise PreparationError('Fleet appeared concurrently; retry to check it without updating it')
        if canonical(plan.get_effective_spec()) != canonical(spec):
            raise PreparationError('Dstack changed the requested fleet plan; review controller policies before retrying')
        # current_resource=None and force=False make a concurrent create fail,
        # instead of overwriting somebody else's fleet. target=0 rents nothing.
        fleet = client.fleets.apply_plan(project, ApplyFleetPlanInput(spec=spec), force=False)
        if canonical(fleet.spec) != canonical(spec):
            raise PreparationError('Created fleet readback differs; inspect controller policies before continuing')
        created += 1
    return {'createdEmptyFleets': created, 'updatedFleets': updated, 'updated': True}


def main():
    try:
        if importlib.metadata.version('dstack') != '0.21.5':
            raise PreparationError('Unsupported controller version; expected dstack 0.21.5')
        client = APIClient(base_url=os.environ['DSTACK_SERVER_URL'], token=os.environ['DSTACK_TOKEN'])
        print(json.dumps(prepare(client, json.loads(os.environ['FLEET_INPUT']))))
    except PreparationError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Capacity-manager fleet preparation failed; check project/backend availability (private details omitted)', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

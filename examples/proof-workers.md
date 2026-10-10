# Bounded Vast.ai GPU capacity

Declare `proofWorkers` in the deployment spec. Preparation `setup plan` displays
its resource and rental envelope; preparation `setup apply` records the intent
without renting GPUs. Install the coordinator and dstack controller, publish the
proof artifacts, and finish configuration generation first. Work from the generated
deployment directory (or its `runtime/` copy):

```bash
scrollsdk setup proof-worker          # Hydrate the compiled bundle's private token.
scrollsdk setup proof-workers plan    # Local plan only; review before proceeding.
scrollsdk setup proof-workers apply   # Starts watchdog, then submits billable GPUs.
scrollsdk setup proof-workers status  # Read-only; also the default without an action.
```

No path flags are needed. The capacity plan reads `.scrollsdk/intent.json`, the
checked CUDA-image receipt, publication receipt and compiler-generated Worker
contract. It derives the dstack project, auth Secret reference and controller
image from the same deployment. The namespace follows
`dstackController.monitoring.namespace` (default `dstack-system`), independently
of the chain namespace. The Kubernetes context defaults to the saved Secret-upload
context when present, otherwise the current kubectl context; `--kube-context` on
plan overrides it. Plan displays and freezes this target before any GPU apply. `--deployment-dir` and
plan-only `--spec` are optional overrides. Capacity apply always uses its saved
plan; an edited spec does not silently change an already submitted rental.

Only the worker ID, provider-local artifact paths and token-file location change
from the compiler's arguments. The digest-pinned image is retained. Artifact
HTTPS downloads verify every SHA-256 before startup. Credentials go to a separate
per-session dstack project Secret, never public task examples or command arguments.
No Core checkout or manually assembled task manifest is required.

## Defaults and an eight-hour example

The starter [deployment spec](deployment-spec.example.yaml) includes every
supported capacity setting. Defaults are one RTX 3090 (24 GB VRAM), at least
8 CPUs, 64 GB host RAM and 200 GB disk, US Texas/Colorado/Washington, minimum
Vast.ai reliability 95%, on-demand allocation, and **no automatic retry**.
The image must advertise the selected CUDA architecture; RTX 3090 and A6000 use
sm_86, RTX 4090 uses sm_89 and A100 uses sm_80. An incompatible choice fails
before submission. A startup GPU architecture check also runs on the host.
These defaults reflect the beta.6 sm_86 rehearsal, not a guarantee of available
capacity or successful proofs for every release.

| Limit | Default | Meaning |
| --- | --- | --- |
| `count` | 1 | Independent worker/fleet pairs, one GPU each; maximum 8 |
| `maxPricePerHourUsd` | 0.80 | Per-instance offer ceiling, not a quoted current price |
| `maxDurationHours` | 2 | Operator-selected running time in hours; no CLI policy upper limit |
| `startupTimeoutMinutes` | 30 | Absolute submission/provisioning/pulling deadline |
| `stopTimeoutMinutes` | 13 | Graceful stop window, covering the 12-minute compiler drain |
| `idleTimeoutMinutes` | 5 | Fleet idle retention, with minimum fleet size zero |
| `rentalBudgetUsd` | 3 | Admission budget against the rental envelope, not a provider billing cap |

The CLI converts the configured duration to whole seconds for dstack and derives
the watchdog deadline from that duration plus the configured allowances. There
is no 48-hour cap or 15-minute minimum: any positive finite duration of at least
one second is accepted, subject to the operator's declared rental budget. For
example, `168` means seven days and `720` means thirty days. The default remains
two hours when the field is omitted.

An explicit eight-hour intent, with two workers:

```yaml
proofWorkers:
  backend: vastai
  count: 2
  gpu: RTX3090
  cpu: 8
  memoryGb: 64
  diskGb: 200
  regions: [us-texas, us-colorado, us-washington]
  minReliability: 0.95
  maxDurationHours: 8
  maxPricePerHourUsd: 0.80
  rentalBudgetUsd: 15
  startupTimeoutMinutes: 30
  stopTimeoutMinutes: 13
  idleTimeoutMinutes: 5
```

The rental admission envelope includes **running + startup + drain + idle + two
minutes for polling**, multiplied by worker count and the hourly ceiling. It is
rounded up to cents: defaults $2.27; the two-worker eight-hour example $14.14.
A lower declared budget is rejected locally. Image pulling and provisioning are
not covered by dstack 0.21.5's `max_duration`, so a separate absolute watchdog
handles them. Storage, network transfer, taxes, provider billing increments and
API/deletion delays are outside the envelope. This is not a strict invoice cap;
use provider-side budget controls and verify final provider billing.

## Expiry, cancellation and recovery

Each session has deterministic, unique worker/fleet/Secret names and a private
plan/state under `.scrollsdk/proof-workers/`. Apply installs a Kubernetes watchdog
Job using the pinned controller image and existing admin Secret, waits for it to
be ready and able to query the controller, then submits through the controller's
native dstack 0.21.5 API. No public controller exposure, Python installation or
local dstack login is needed; the operator needs kubectl rights to create/watch
Jobs and exec the controller. The watchdog needs access to the controller Service.

The absolute deadline is saved before submission and reused on restart. A
retry reconciles the same names, never extends the original deadline or restarts
a finished run. Fleets use `nodes: 0..1`, finite idle retention, and no retry.
The watchdog cleans failed/finished runs, stops stalled startup, requests graceful
stop at the absolute running deadline, and forces cleanup after the drain window.
It remains active if API calls fail and does not claim that failure means deletion.

```bash
scrollsdk setup proof-workers destroy
scrollsdk setup proof-workers status
# Repeat destroy until it reports destroyed (not merely cleanup-requested).
```

Destroy targets only the saved plan's owned resources. It requests immediate
cancellation and fleet deletion, retaining the watchdog while deletion proceeds.
A terminal run alone does not prove its instance stopped billing: require terminal
fleets and check Vast.ai. Preserve `.scrollsdk/` until cleanup is confirmed.
The per-session project Secret is removed after watchdog-confirmed cleanup.

After confirmed destruction, a new named session requires explicit planning and
apply; the old session is archived locally:

```bash
scrollsdk setup proof-workers plan --new-session second-run
scrollsdk setup proof-workers apply
```

To change capacity, use `--spec ../deployment-spec.yaml` with that new plan. The
spec supplies resource intent only; current compiler artifacts still determine
the exact deployment and image. This does not regenerate proof materials.

For a two-day session, set `proofWorkers.maxDurationHours`
to `48`. With one worker and the default $0.80/hour ceiling, set
`proofWorkers.rentalBudgetUsd` to at least `39.07` (for example, `40`). This
includes the default startup, drain, idle and polling allowances. Keep the
default two-hour setting for short rehearsals. Changing the spec does not extend
an existing run or its watchdog. Once the old run has finished, confirm destruction
and submit a new session with the updated spec:

```bash
scrollsdk setup proof-workers status
scrollsdk setup proof-workers destroy
# Repeat status/destroy until destroy reports destroyed.
scrollsdk setup proof-workers plan --new-session two-day --spec ../deployment-spec.yaml
scrollsdk setup proof-workers apply
scrollsdk setup proof-workers status
```

The replacement receives a fresh absolute watchdog deadline. Do not edit the
saved plan, controller database or old watchdog to bypass expiry. There is a
capacity gap while the old instance is released and its replacement starts;
pending proof jobs remain in the coordinator.

An interrupted mutation may leave `operation.lock`. Verify that its recorded PID
is no longer the CLI process before removing only that lock; then inspect status
and reconcile. Never delete the saved plan/state to force another allocation.
A lost workstation state or an ambiguous response requires inspection, not a new
session. Restore the private plan before targeted cleanup.

**Availability boundary:** a persistent watchdog survives CLI exit and its own
Pod restart, but it is not independent of Kubernetes, the controller, credentials
or Vast.ai APIs. If those fail, termination can be delayed and billing may continue.
Keep the controller, watchdog, Secret and cluster alive until cleanup is verified.
Status is a sanitized controller observation, not a direct invoice or proof-success
report. Use the coordinator and actual proof results for acceptance.

The pinned API behavior is documented by dstack's
[0.21.5 duration fields](https://github.com/dstackai/dstack/blob/0.21.5/src/dstack/_internal/core/models/profiles.py)
and [fleet lifetime model](https://github.com/dstackai/dstack/blob/0.21.5/src/dstack/_internal/core/models/fleets.py).
This adapter does not assume newer Core capacity-manager APIs.

For native dstack operations, see the official [run status commands](https://dstack.ai/docs/reference/cli/dstack/ps/),
[run logs](https://dstack.ai/docs/reference/cli/dstack/logs/),
[fleet lifecycle](https://dstack.ai/docs/concepts/fleets/), and
[task duration and price settings](https://dstack.ai/docs/reference/dstack.yml/task/).
The live documentation may describe a newer version than the pinned 0.21.5
controller. Use the commands above for SDK-owned worker lifecycle operations so
the saved plan and independent cleanup watchdog remain consistent.

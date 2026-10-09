# Component maintenance and public delivery

`statusPage.publication.maintenanceWindows` defines the local delivery guard for
planned maintenance. Runtime Pods hold only component webhook credentials; no
Instatus management API key is introduced.

```yaml
statusPage:
  publication:
    delivery:
      enabled: true
    maintenanceWindows:
      - id: sequencer-upgrade
        start: '2026-12-01T01:00:00Z'
        end: '2026-12-01T02:00:00Z'
        components: [sequencing, node-sync]
```

Times must be valid UTC timestamps with seconds and `Z`; YAML strings must be
quoted. Component keys belong to this deployment's network. Overlapping windows
remain suppressed until every applicable window has ended. Generate the values
with `setup status-page` and deploy scroll-monitor **before** maintenance starts.
There is no deployment or business-image operation in this setting.

During a window, the verifier sends neither incident creation nor recovery for
its selected components. Existing durable incident IDs and uncertain pending
requests remain intact. After the window, the full continuous failure/recovery
confirmation interval starts again. Missing observations never resolve an
incident. Restarts during maintenance keep the same behavior. Internal monitoring
continues; `scroll_status_delivery_maintenance` exposes the per-component guard.

The window is the monitoring-side guard. Publish the matching maintenance notice
in Instatus using the existing operator workflow; an Instatus UI edit alone does
not change local configuration. The monitor does not infer health from a remote
maintenance notice or from its ending. Management-API synchronization of the
notice is separate from this guard and is not performed by runtime collectors.
Do not use Instatus automatic status restoration as proof of observed recovery.

Keep original component bindings and the delivery PVC during maintenance. Do not
remove state or change IDs to dismiss an unresolved or uncertain incident.

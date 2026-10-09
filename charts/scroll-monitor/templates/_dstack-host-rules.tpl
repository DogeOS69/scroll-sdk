{{- define "scroll-monitor.dstackHostRules" -}}
groups:
  - name: dogeos.dstack-hosts
    interval: 30s
    rules:
      {{- if .Values.dstack.gpuHosts.expectedHosts }}
      - alert: DstackHostTelemetryUnavailable
        {{- $queries := list }}
        {{- range .Values.dstack.gpuHosts.expectedHosts }}
        {{- $queries = append $queries (printf "(time() - max by (dstack_namespace,dstack_controller,dstack_host) (node_time_seconds{dstack_namespace=%s,dstack_controller=%s,dstack_host=%s}) > %v) or absent(node_time_seconds{dstack_namespace=%s,dstack_controller=%s,dstack_host=%s})" ($.Values.dstack.namespace | quote) ($.Values.dstack.controllerName | quote) (. | quote) $.Values.dstack.gpuHosts.staleAfterSeconds ($.Values.dstack.namespace | quote) ($.Values.dstack.controllerName | quote) (. | quote)) }}
        {{- end }}
        expr: {{ join " or " $queries | quote }}
        for: {{ .Values.dstack.gpuHosts.unavailableFor }}
        labels: {severity: warning, service: dstack-gpu-host, visibility: internal}
        annotations:
          summary: Expected GPU host telemetry is missing or stale.
          description: Check the host Alloy process, host clock and remote-write connectivity. This indicates lost observability, not a proven GPU failure. Remove intentionally retired hosts from the expected inventory.
      {{- end }}
      - alert: DstackHostDiskSpaceLow
        expr: {{ printf "((node_filesystem_avail_bytes{dstack_namespace=%s,dstack_controller=%s,dstack_host!=\"\",fstype!~\"tmpfs|overlay|squashfs\"} / node_filesystem_size_bytes) < %v) and on (dstack_namespace,dstack_controller,dstack_host) (time() - node_time_seconds < %v)" (.Values.dstack.namespace | quote) (.Values.dstack.controllerName | quote) .Values.dstack.gpuHosts.diskAvailableRatio .Values.dstack.gpuHosts.staleAfterSeconds | quote }}
        for: 10m
        labels: {severity: warning, service: dstack-gpu-host, visibility: internal}
        annotations:
          summary: GPU host filesystem has little available space.
          description: Inspect prover cache, container images and logs on the affected filesystem.
{{- end -}}

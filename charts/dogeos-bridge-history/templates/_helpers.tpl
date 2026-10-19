{{/*
The service's TOML config, from .Values.config. Helm's toToml writes YAML
numbers as floats (1.0), which the service's integer fields reject, so this
renders scalars itself. Tables are rendered only when non-empty: l2 and
ethereum are optional in the service, and an empty table fails its strict
parsing. Secrets and RPC URLs come from the environment
(DOGEOS_BRIDGE_HISTORY_*), not from this file.
*/}}
{{- define "dogeos-bridge-history.tomlValue" -}}
{{- if kindIs "string" . -}}
{{ . | quote }}
{{- else if kindIs "bool" . -}}
{{ . }}
{{- else if and (kindIs "float64" .) (eq (float64 (int64 .)) .) -}}
{{ int64 . }}
{{- else -}}
{{ . }}
{{- end -}}
{{- end -}}

{{- define "dogeos-bridge-history.configToml" -}}
{{- range $key, $value := .Values.config }}
{{- if not (kindIs "map" $value) }}
{{ $key }} = {{ include "dogeos-bridge-history.tomlValue" $value }}
{{- end }}
{{- end }}
{{- range $key, $value := .Values.config }}
{{- if and (kindIs "map" $value) (not (empty $value)) }}

[{{ $key }}]
{{- range $field, $fieldValue := $value }}
{{ $field }} = {{ include "dogeos-bridge-history.tomlValue" $fieldValue }}
{{- end }}
{{- end }}
{{- end }}
{{- end -}}

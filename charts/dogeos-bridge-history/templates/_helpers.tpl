{{/*
The service's TOML config, from .Values.config. Helm's toToml writes YAML
numbers as floats (1.0), which the service's integer fields reject, so this
renders values itself: strings, booleans, numbers, and lists of those. Tables
are one level deep, and rendered only when non-empty: l2 and ethereum are
optional in the service, and an empty table fails its strict parsing. Secrets
and RPC URLs come from the environment (DOGEOS_BRIDGE_HISTORY_*), not from this
file.
*/}}
{{- define "dogeos-bridge-history.tomlScalar" -}}
{{- $key := index . 0 -}}
{{- $value := index . 1 -}}
{{- if kindIs "invalid" $value -}}
{{- fail (printf "config.%s is null; set a value or remove the key" $key) -}}
{{- else if kindIs "string" $value -}}
{{ $value | quote }}
{{- else if kindIs "bool" $value -}}
{{ $value }}
{{- else if and (kindIs "float64" $value) (eq (float64 (int64 $value)) $value) -}}
{{ int64 $value }}
{{- else if or (kindIs "float64" $value) (kindIs "int" $value) (kindIs "int64" $value) -}}
{{ $value }}
{{- else -}}
{{- fail (printf "config.%s must be a string, number or boolean, or a list of them; tables nest one level only" $key) -}}
{{- end -}}
{{- end -}}

{{- define "dogeos-bridge-history.tomlValue" -}}
{{- $key := index . 0 -}}
{{- $value := index . 1 -}}
{{- if kindIs "slice" $value -}}
{{- $items := list -}}
{{- range $value -}}
{{- $items = append $items (include "dogeos-bridge-history.tomlScalar" (list $key .)) -}}
{{- end -}}
[{{ join ", " $items }}]
{{- else -}}
{{ include "dogeos-bridge-history.tomlScalar" (list $key $value) }}
{{- end -}}
{{- end -}}

{{- define "dogeos-bridge-history.configToml" -}}
{{- range $key, $value := .Values.config }}
{{- if not (kindIs "map" $value) }}
{{ $key }} = {{ include "dogeos-bridge-history.tomlValue" (list $key $value) }}
{{- end }}
{{- end }}
{{- range $key, $value := .Values.config }}
{{- if and (kindIs "map" $value) (not (empty $value)) }}

[{{ $key }}]
{{- range $field, $fieldValue := $value }}
{{ $field }} = {{ include "dogeos-bridge-history.tomlValue" (list (printf "%s.%s" $key $field) $fieldValue) }}
{{- end }}
{{- end }}
{{- end }}
{{- end -}}

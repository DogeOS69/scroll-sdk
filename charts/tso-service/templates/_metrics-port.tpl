{{- /*
Optional dedicated metrics listener. With metricsPort unset, /metrics stays on
the API port. When it is set, the application serves /metrics only on that
port, so this helper, run before the common library renders:
  - passes the port to the application through envName;
  - adds a "metrics" port to the main Service (and so to the container);
  - moves this chart's ServiceMonitor endpoints from port "http" to "metrics".
The NetworkPolicy template reads metricsPort itself.
*/ -}}
{{- define "tso-service.metricsPort.apply" -}}
{{- $root := .root -}}
{{- $envName := .envName -}}
{{- $raw := $root.Values.metricsPort -}}
{{- if not (kindIs "invalid" $raw) -}}
{{- if not (regexMatch "^[0-9]+$" (toString $raw)) -}}
{{- fail "metricsPort must be an integer between 1 and 65535" -}}
{{- end -}}
{{- $port := int $raw -}}
{{- if or (lt $port 1) (gt $port 65535) -}}
{{- fail "metricsPort must be an integer between 1 and 65535" -}}
{{- end -}}
{{- $ports := $root.Values.service.main.ports -}}
{{- if hasKey $ports "metrics" -}}
{{- fail "metricsPort adds service.main.ports.metrics; remove the explicit entry" -}}
{{- end -}}
{{- range $name, $p := $ports -}}
{{- if or (eq (int $p.port) $port) (eq (int (default $p.port $p.targetPort)) $port) -}}
{{- fail (printf "metricsPort %d must differ from service.main.ports.%s" $port $name) -}}
{{- end -}}
{{- end -}}
{{- $env := $root.Values.env | default list -}}
{{- if kindIs "map" $env -}}
{{- if hasKey $env $envName -}}
{{- fail (printf "set metricsPort instead of env %s" $envName) -}}
{{- end -}}
{{- $_ := set $env $envName (toString $port) -}}
{{- else -}}
{{- range $env -}}
{{- if eq .name $envName -}}
{{- fail (printf "set metricsPort instead of env %s" $envName) -}}
{{- end -}}
{{- end -}}
{{- $env = append $env (dict "name" $envName "value" (toString $port)) -}}
{{- end -}}
{{- $_ := set $root.Values "env" $env -}}
{{- $_ := set $ports "metrics" (dict "enabled" true "port" $port "targetPort" $port "protocol" "TCP") -}}
{{- range $name, $monitor := ($root.Values.serviceMonitor | default dict) -}}
{{- if $monitor.endpoints -}}
{{- $endpoints := list -}}
{{- range $monitor.endpoints -}}
{{- if eq (toString .port) "http" -}}
{{- $endpoints = append $endpoints (merge (dict "port" "metrics") (omit . "port")) -}}
{{- else -}}
{{- $endpoints = append $endpoints . -}}
{{- end -}}
{{- end -}}
{{- $_ := set $monitor "endpoints" $endpoints -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}

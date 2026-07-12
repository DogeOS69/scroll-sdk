{{/*
Resolve the rendered Kubernetes Service name.

service.fullname is an exact override. service.nameOverride keeps the historical
suffix behavior: <release-fullname>-<nameOverride>.
*/}}
{{- define "scroll.common.lib.service.name" -}}
  {{- $root := .root -}}
  {{- $values := .values -}}
  {{- $serviceName := include "scroll.common.lib.chart.names.fullname" $root -}}
  {{- if and (hasKey $values "fullname") $values.fullname -}}
    {{- $serviceName = tpl (toString $values.fullname) $root -}}
  {{- else if and (hasKey $values "nameOverride") $values.nameOverride -}}
    {{- $serviceName = printf "%v-%v" $serviceName $values.nameOverride -}}
  {{- end -}}
  {{- $serviceName -}}
{{- end -}}

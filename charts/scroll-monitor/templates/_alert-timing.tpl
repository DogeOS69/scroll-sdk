{{/* Duration grammar shared by PromQL ranges, pending periods and evaluation. */}}
{{- define "scroll-monitor.durationSeconds" -}}
{{- $duration := toString . -}}
{{- if not (regexMatch "^[0-9]+[smhdw]$" $duration) -}}
{{- fail (printf "alertTiming duration %q must be an integer followed by s, m, h, d or w" $duration) -}}
{{- end -}}
{{- $unit := regexFind "[smhdw]$" $duration -}}
{{- mul (int (trimSuffix $unit $duration)) (index (dict "s" 1 "m" 60 "h" 3600 "d" 86400 "w" 604800) $unit) -}}
{{- end -}}

{{/* Apply to both metric backends and Loki. Historical migration fields stay intact. */}}
{{- define "scroll-monitor.applyAlertTiming" -}}
{{- $settings := .root.Values.alertTiming -}}
{{- range $group := .groups -}}
{{- if hasKey $settings.groupIntervals $group.name -}}
{{- $_ := set $group "interval" (index $settings.groupIntervals $group.name) -}}
{{- end -}}
{{- range $rule := $group.rules -}}
{{- $parameters := deepCopy ($rule.timing | default dict) -}}
{{- $overrides := index $settings.rules $rule.alert | default dict -}}
{{- $changed := false -}}
{{- range $key, $value := $overrides -}}
{{- $old := index $parameters $key -}}
{{- if eq $key "for" -}}{{- $old = index $rule "for" | default "0s" -}}{{- end -}}
{{- if ne (toString $old) (toString $value) -}}{{- $changed = true -}}{{- end -}}
{{- $_ := set $parameters $key $value -}}
{{- end -}}
{{- if hasKey $overrides "for" -}}{{- $_ := set $rule "for" (index $overrides "for") -}}{{- end -}}
{{- $_ := set $parameters "for" (index $rule "for" | default "0s") -}}
{{- if hasKey $parameters "window" -}}
{{- $_ := set $parameters "windowSeconds" (include "scroll-monitor.durationSeconds" $parameters.window) -}}
{{- end -}}
{{- if and (hasKey $parameters "step") (gt (int (include "scroll-monitor.durationSeconds" $parameters.step)) (int (include "scroll-monitor.durationSeconds" $parameters.window))) -}}
{{- fail (printf "alertTiming.rules.%s.step must not exceed window" $rule.alert) -}}
{{- end -}}
{{- $annotationKeys := list -}}
{{- range $key, $value := $rule.timingAnnotations | default dict -}}
{{- $affected := false -}}
{{- range $parameter, $_ := $overrides -}}
{{- if contains (printf "__TIME_%s__" $parameter) $value -}}{{- $affected = true -}}{{- end -}}
{{- end -}}
{{- if $affected -}}
{{- $annotationKeys = append $annotationKeys $key -}}
{{- if $changed -}}
{{- $_ := set $rule.annotations $key $value -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if and $overrides (or (eq $.root.Values.alerting.backend "grafana") (eq ($rule.datasourceType | default "") "loki")) $.root.Values.grafana.enabled $.root.Values.grafanaAlerting.enabled -}}
{{- $_ := set $rule "timingAnnotationKeys" $annotationKeys -}}
{{- end -}}
{{- range $key, $value := $parameters -}}
{{- $marker := printf "__TIME_%s__" $key -}}
{{- $_ := set $rule "expr" (replace $marker (toString $value) $rule.expr) -}}
{{- range $name, $annotation := $rule.annotations -}}
{{- $_ := set $rule.annotations $name (replace $marker (toString $value) $annotation) -}}
{{- end -}}
{{- end -}}
{{- $_ := unset $rule "timing" -}}
{{- $_ := unset $rule "timingAnnotations" -}}
{{- end -}}
{{- end -}}
{{- dict "groups" .groups | toYaml -}}
{{- end -}}

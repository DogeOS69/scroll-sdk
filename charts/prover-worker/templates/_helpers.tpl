{{/* Expand the chart name. */}}
{{- define "prover-worker.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Create a stable release-qualified name. */}}
{{- define "prover-worker.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "prover-worker.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* Compatibility name used by scrollsdk-generated persistence references. */}}
{{- define "scroll.common.lib.chart.names.fullname" -}}
{{- include "prover-worker.fullname" . -}}
{{- end -}}

{{- define "prover-worker.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
app.kubernetes.io/name: {{ include "prover-worker.name" . | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
{{- end -}}

{{- define "prover-worker.selectorLabels" -}}
app.kubernetes.io/name: {{ include "prover-worker.name" . | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end -}}

{{- define "prover-worker.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "prover-worker.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "prover-worker.image" -}}
{{- if .Values.image.digest -}}
{{- printf "%s@%s" (required "image.repository is required" .Values.image.repository) .Values.image.digest -}}
{{- else -}}
{{- printf "%s:%s" (required "image.repository is required" .Values.image.repository) (required "image.tag or image.digest is required" .Values.image.tag) -}}
{{- end -}}
{{- end -}}

{{- define "prover-worker.persistenceObjectName" -}}
{{- $entry := index . 0 -}}
{{- $root := index . 1 -}}
{{- if $entry.name -}}
{{- tpl $entry.name $root -}}
{{- else -}}
{{- printf "%s-%s" (include "prover-worker.fullname" $root) (index . 2) -}}
{{- end -}}
{{- end -}}

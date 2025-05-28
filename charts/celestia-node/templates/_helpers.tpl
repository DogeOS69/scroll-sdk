{{/*
Expand the name of the chart.
*/}}
{{- define "celestia-node.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "celestia-node.fullname" -}}
{{- printf "%s-%s" .Release.Name .Values.network | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "celestia-node.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "celestia-node.labels" -}}
helm.sh/chart: {{ include "celestia-node.chart" . }}
{{ include "celestia-node.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/network: {{ .Values.network }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "celestia-node.selectorLabels" -}}
app.kubernetes.io/name: {{ include "celestia-node.name" . }}
app.kubernetes.io/instance: {{ include "celestia-node.fullname" . }}
{{- end }}

{{/*
Determine the image tag based on the network
*/}}
{{- define "celestia-node.imageTag" -}}
{{- if eq .Values.network "celestia" -}}
v0.22.0
{{- else if eq .Values.network "mocha" -}}
v0.22.0-mocha
{{- else if eq .Values.network "arabica" -}}
v0.22.0-arabica
{{- else -}}
{{- fail "Invalid network specified" -}}
{{- end -}}
{{- end -}}

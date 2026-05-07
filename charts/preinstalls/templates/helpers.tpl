{{/*
Expand the name of the chart.
*/}}
{{- define "preinstalls.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "preinstalls.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "preinstalls.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "preinstalls.labels" -}}
helm.sh/chart: {{ include "preinstalls.chart" . }}
{{ include "preinstalls.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/build: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "preinstalls.selectorLabels" -}}
app.kubernetes.io/name: {{ include "preinstalls.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

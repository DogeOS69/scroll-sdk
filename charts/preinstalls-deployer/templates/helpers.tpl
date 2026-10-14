{{/*
Expand the name of the chart.
*/}}
{{- define "preinstalls-deployer.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "preinstalls-deployer.fullname" -}}
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

{{- define "preinstalls-deployer.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "preinstalls-deployer.labels" -}}
helm.sh/chart: {{ include "preinstalls-deployer.chart" . }}
{{ include "preinstalls-deployer.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/build: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "preinstalls-deployer.selectorLabels" -}}
app.kubernetes.io/name: {{ include "preinstalls-deployer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

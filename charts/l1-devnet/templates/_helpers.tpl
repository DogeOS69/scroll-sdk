{{/*
Expand the chart name.
*/}}
{{- define "l1-devnet.name" -}}
{{- $globalName := "" -}}
{{- if .Values.global -}}
{{- $globalName = default "" .Values.global.nameOverride -}}
{{- end -}}
{{- default .Chart.Name (default $globalName .Values.nameOverride) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name. Keep l1-devnet stable by default so
existing scroll-sdk services can continue to use http://l1-devnet:8545.
*/}}
{{- define "l1-devnet.fullname" -}}
{{- $globalFullname := "" -}}
{{- if .Values.global -}}
{{- $globalFullname = default "" .Values.global.fullnameOverride -}}
{{- end -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else if $globalFullname }}
{{- $globalFullname | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create the chart label value.
*/}}
{{- define "l1-devnet.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "l1-devnet.labels" -}}
helm.sh/chart: {{ include "l1-devnet.chart" . }}
{{ include "l1-devnet.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "l1-devnet.selectorLabels" -}}
app.kubernetes.io/name: {{ include "l1-devnet.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Support old values files that still populate configMaps.env.data.CHAIN_ID.
*/}}
{{- define "l1-devnet.chainId" -}}
{{- $chainId := .Values.network.chainId -}}
{{- with .Values.configMaps -}}
{{- with .env -}}
{{- with .data -}}
{{- if .CHAIN_ID -}}
{{- $chainId = .CHAIN_ID -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- $chainId -}}
{{- end }}

{{/*
Use the legacy CHAIN_ID for networkId as well when present.
*/}}
{{- define "l1-devnet.networkId" -}}
{{- $legacyChainId := "" -}}
{{- with .Values.configMaps -}}
{{- with .env -}}
{{- with .data -}}
{{- if .CHAIN_ID -}}
{{- $legacyChainId = .CHAIN_ID -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if $legacyChainId -}}
{{- $legacyChainId -}}
{{- else -}}
{{- default (include "l1-devnet.chainId" .) .Values.network.networkId -}}
{{- end -}}
{{- end }}

{{/*
Resource names.
*/}}
{{- define "l1-devnet.rpcServiceName" -}}
{{ include "l1-devnet.fullname" . }}
{{- end }}

{{- define "l1-devnet.jwtSecretName" -}}
{{ include "l1-devnet.fullname" . }}-jwt-secret
{{- end }}

{{- define "l1-devnet.genesisConfigName" -}}
{{ include "l1-devnet.fullname" . }}-genesis-config
{{- end }}

{{- define "l1-devnet.genesisJobName" -}}
{{ include "l1-devnet.fullname" . }}-genesis-generator-{{ .Release.Revision }}
{{- end }}

{{- define "l1-devnet.genesisPvcName" -}}
{{ include "l1-devnet.fullname" . }}-genesis-data
{{- end }}

{{- define "l1-devnet.gethName" -}}
{{ include "l1-devnet.fullname" . }}-geth
{{- end }}

{{- define "l1-devnet.gethPvcName" -}}
{{ include "l1-devnet.fullname" . }}-geth-data
{{- end }}

{{- define "l1-devnet.lighthouseName" -}}
{{ include "l1-devnet.fullname" . }}-lighthouse
{{- end }}

{{- define "l1-devnet.lighthousePvcName" -}}
{{ include "l1-devnet.fullname" . }}-lighthouse-data
{{- end }}

{{- define "l1-devnet.validatorName" -}}
{{ include "l1-devnet.fullname" . }}-lighthouse-validator
{{- end }}

{{- define "capacity-manager.labels" -}}
app.kubernetes.io/name: capacity-manager
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{- define "capacity-manager.serviceAccountName" -}}
{{- default .Values.fullnameOverride .Values.serviceAccount.name -}}
{{- end }}

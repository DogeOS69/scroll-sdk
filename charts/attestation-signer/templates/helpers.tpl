{{/*
Expand the name of the chart.
*/}}
{{- define "scroll-sdk.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Render non-secret application configuration from structured chart values.
Secret key material and release identity remain environment-only overrides.
*/}}
{{- define "attestation-signer.configToml" -}}
{{- $config := .Values.attestationSigner -}}
[service]
port = {{ $config.port }}
network = {{ $config.network | quote }}
signature_delay = {{ $config.signatureDelaySeconds }}

[policy]
{{- if or (eq $config.profile "staging-local") (eq $config.profile "staging-kms") }}
mode = "staging_scaffold"
allow_unimplemented_checks = true
{{- else if eq $config.profile "production-kms" }}
mode = "production_enforce"
allow_unimplemented_checks = false
{{- end }}
allow_rotate_key_signing_in_scaffold = {{ $config.allowRotateKeySigningInScaffold }}

[signer]
{{- if eq $config.profile "staging-local" }}
backend = "local"
{{- else if or (eq $config.profile "staging-kms") (eq $config.profile "production-kms") }}
backend = "aws_kms"
kms_key_id = {{ $config.kms.keyId | quote }}
kms_region = {{ $config.kms.region | quote }}
kms_expected_signer_id = {{ $config.kms.expectedSignerId | quote }}
{{- with $config.kms.endpointUrl }}
kms_endpoint_url = {{ . | quote }}
{{- end }}
{{- end }}

[tso]
url = {{ $config.tso.url | quote }}
callback_phase = {{ $config.tso.callbackPhase | quote }}

[database]
path = {{ $config.database.path | quote }}

{{- if eq $config.profile "production-kms" }}
[production_policy]
protocol_instance_id = {{ $config.productionPolicy.protocolInstanceId | quote }}
bridge_namespace_id = {{ $config.productionPolicy.bridgeNamespaceId | quote }}
active_bridge_key_hash = {{ $config.productionPolicy.activeBridgeKeyHash | quote }}
supported_signing_policy_versions = {{ $config.productionPolicy.supportedSigningPolicyVersions | quote }}
verifier_registry_toml = {{ $config.productionPolicy.verifierRegistryToml | quote }}
tee_allowed_signer_ids = {{ $config.productionPolicy.teeAllowedSignerIds | quote }}
source_set_toml = {{ $config.productionPolicy.sourceSetToml | quote }}
{{- end }}

[envelope_policy]
allowed_proof_triples = {{ $config.envelopePolicy.allowedProofTriples | quote }}
allowed_tee_signer_ids = {{ $config.envelopePolicy.allowedTeeSignerIds | quote }}
max_proof_artifacts = {{ $config.envelopePolicy.maxProofArtifacts }}
max_ref_string_bytes = {{ $config.envelopePolicy.maxRefStringBytes }}
max_fetch_url_bytes = {{ $config.envelopePolicy.maxFetchUrlBytes }}

[proof_artifact_fetch]
mode = {{ $config.proofArtifact.fetchMode | quote }}
max_bytes = {{ $config.proofArtifact.maxBytes }}
{{- end -}}

{{/* Generate secret and runtime identity overrides only. */}}
{{- define "attestation-signer.generatedEnv" -}}
{{- $config := .Values.attestationSigner -}}
- name: RUST_LOG
  value: {{ $config.logFilter | quote }}
{{- if eq $config.profile "staging-local" }}
- name: ATTESTATION_SIGNER_WIF
  valueFrom:
    secretKeyRef:
      name: {{ required "attestationSigner.local.wifSecretRef.name is required for staging-local" $config.local.wifSecretRef.name | quote }}
      key: {{ required "attestationSigner.local.wifSecretRef.key is required for staging-local" $config.local.wifSecretRef.key | quote }}
{{- else if eq $config.profile "production-kms" }}
- name: ATTESTATION_SIGNER_ALLOWED_RELEASE_VERSION
  value: {{ $config.releasePolicy.allowedReleaseVersion | quote }}
- name: ATTESTATION_SIGNER_ALLOWED_GIT_COMMIT
  value: {{ $config.releasePolicy.allowedGitCommit | quote }}
- name: ATTESTATION_SIGNER_ALLOWED_SIGNING_POLICY_VERSION
  value: {{ $config.releasePolicy.allowedSigningPolicyVersion | quote }}
{{- with $config.releasePolicy.allowedContainerDigest }}
- name: ATTESTATION_SIGNER_ALLOWED_CONTAINER_DIGEST
  value: {{ . | quote }}
{{- end }}
{{- with $config.releasePolicy.containerDigest }}
- name: ATTESTATION_SIGNER_CONTAINER_DIGEST
  value: {{ . | quote }}
{{- end }}
{{- end }}
{{- end -}}
{{/*
Create a default fully qualified app name.
*/}}
{{- define "scroll-sdk.fullname" -}}
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
{{/*
Create chart name and build as used by the chart label.
*/}}
{{- define "scroll-sdk.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}
{{/*
Common labels
*/}}
{{- define "scroll-sdk.labels" -}}
helm.sh/chart: {{ include "scroll-sdk.chart" . }}
{{ include "scroll-sdk.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/build: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{/*
Selector labels
*/}}
{{- define "scroll-sdk.selectorLabels" -}}
app.kubernetes.io/name: {{ include "scroll-sdk.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

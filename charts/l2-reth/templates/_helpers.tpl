{{/*
Default shared secret-env Secret name used by External Secrets-backed file mounts.
*/}}
{{- define "l2-reth.secretEnvName" -}}
{{- printf "%s-secret-env" (include "scroll.common.lib.chart.names.fullname" .) -}}
{{- end -}}

{{/*
Resolve the Secret name for the p2p node key. If unset, use the same
<fullname>-secret-env convention used by the other production services.
*/}}
{{- define "l2-reth.nodeKeySecretName" -}}
{{- default (include "l2-reth.secretEnvName" .) .Values.reth.nodeKey.secretName -}}
{{- end -}}

{{/*
Resolve the Secret name for a local sequencer signer key.
*/}}
{{- define "l2-reth.signerSecretName" -}}
{{- default (include "l2-reth.secretEnvName" .) .Values.reth.signer.localFile.secretName -}}
{{- end -}}

{{/*
Validate l2-reth role constraints before generating common chart values.
*/}}
{{- define "l2-reth.validate" -}}
  {{- $role := required "role is required and must be one of: rpc, sequencer, bootnode" .Values.role -}}
  {{- if not (has $role (list "rpc" "sequencer" "bootnode")) -}}
    {{- fail (printf "invalid role %q: expected rpc, sequencer, or bootnode" $role) -}}
  {{- end -}}
  {{- $replicas := int (default 1 .Values.controller.replicas) -}}
  {{- if and (ne $role "rpc") (gt $replicas 1) -}}
    {{- fail (printf "role %s allows only controller.replicas 0 or 1" $role) -}}
  {{- end -}}
  {{- if lt $replicas 0 -}}
    {{- fail "controller.replicas must be at least 0" -}}
  {{- end -}}
  {{- $nodeKeyMode := default "pvcAutoGenerate" .Values.reth.nodeKey.mode -}}
  {{- if not (has $nodeKeyMode (list "secret" "pvcAutoGenerate" "none")) -}}
    {{- fail (printf "invalid reth.nodeKey.mode %q: expected secret, pvcAutoGenerate, or none" $nodeKeyMode) -}}
  {{- end -}}
  {{- $signerType := default "none" .Values.reth.signer.type -}}
  {{- if not (has $signerType (list "none" "awsKms" "localFile")) -}}
    {{- fail (printf "invalid reth.signer.type %q: expected none, awsKms, or localFile" $signerType) -}}
  {{- end -}}
  {{- if and (eq $role "sequencer") (eq $signerType "none") -}}
    {{- fail "role sequencer requires reth.signer.type to be awsKms or localFile" -}}
  {{- end -}}
  {{- if and (eq $signerType "awsKms") (not .Values.reth.signer.awsKmsKeyId) -}}
    {{- fail "reth.signer.awsKmsKeyId is required when reth.signer.type is awsKms" -}}
  {{- end -}}
  {{- if and (eq $signerType "localFile") (eq $nodeKeyMode "secret") (eq (dir .Values.reth.signer.localFile.path) (dir .Values.reth.nodeKey.path)) -}}
    {{- fail "reth.signer.localFile.path and reth.nodeKey.path must use different directories when both are mounted from secrets" -}}
  {{- end -}}
{{- end -}}

{{/*
Generate common chart values from the concise l2-reth role model.
*/}}
{{- define "l2-reth.generatedValues" -}}
command:
  - rollup-node
args:
{{ include "l2-reth.args" . | nindent 2 }}
initContainers:
  wait-for-l1:
    image: {{ .Values.waitForL1.image | quote }}
    command:
      - /bin/sh
      - -c
      - {{ printf "/wait-for-l1.sh %q" .Values.reth.l1Url | quote }}
    volumeMounts:
      - name: wait-for-l1-script
        mountPath: /wait-for-l1.sh
        subPath: wait-for-l1.sh
{{- if eq (default "pvcAutoGenerate" .Values.reth.nodeKey.mode) "pvcAutoGenerate" }}
  generate-nodekey:
    image: {{ .Values.nodeKeyGenerator.image | quote }}
    command:
      - /bin/sh
      - -ec
      - |
        umask 077
        mkdir -p /keys
        if [ ! -s {{ .Values.reth.nodeKey.generatedPath | quote }} ]; then
          od -An -N32 -tx1 /dev/urandom | tr -d ' \n' > {{ .Values.reth.nodeKey.generatedPath | quote }}
        fi
        nodekey="$(cat {{ .Values.reth.nodeKey.generatedPath | quote }})"
        if [ "${#nodekey}" -ne 64 ]; then
          echo "{{ .Values.reth.nodeKey.generatedPath }} must be a 64 hex character secp256k1 private key without 0x" >&2
          exit 1
        fi
        case "${nodekey}" in
          *[!0-9a-fA-F]*)
            echo "{{ .Values.reth.nodeKey.generatedPath }} must be a 64 hex character secp256k1 private key without 0x" >&2
            exit 1
            ;;
        esac
        printf '%s' "${nodekey}" > {{ .Values.reth.nodeKey.path | quote }}
    volumeMounts:
      - name: data
        mountPath: {{ .Values.reth.data.mountPath | quote }}
      - name: keys
        mountPath: {{ dir .Values.reth.nodeKey.path | quote }}
{{- end }}
persistence:
  genesis:
    enabled: true
    type: configMap
    mountPath: {{ .Values.reth.genesis.mountPath | quote }}
    subPath: {{ .Values.reth.genesis.subPath | quote }}
    name: {{ .Values.reth.genesis.configMapName | quote }}
    readOnly: true
  wait-for-l1-script:
    enabled: true
    type: configMap
    mountPath: "-"
    name: wait-for-l1-script
    defaultMode: "0777"
{{- if eq (default "pvcAutoGenerate" .Values.reth.nodeKey.mode) "secret" }}
  nodekey:
    enabled: true
    type: secret
    name: {{ include "l2-reth.nodeKeySecretName" . | quote }}
    mountPath: {{ dir .Values.reth.nodeKey.path | quote }}
    items:
      - key: {{ .Values.reth.nodeKey.secretKey | quote }}
        path: {{ base .Values.reth.nodeKey.path | quote }}
    readOnly: true
{{- else if eq (default "pvcAutoGenerate" .Values.reth.nodeKey.mode) "pvcAutoGenerate" }}
  keys:
    enabled: true
    type: emptyDir
    mountPath: {{ dir .Values.reth.nodeKey.path | quote }}
{{- end }}
{{- if eq (default "none" .Values.reth.signer.type) "localFile" }}
  signer-key:
    enabled: true
    type: secret
    name: {{ include "l2-reth.signerSecretName" . | quote }}
    mountPath: {{ dir .Values.reth.signer.localFile.path | quote }}
    items:
      - key: {{ .Values.reth.signer.localFile.secretKey | quote }}
        path: {{ base .Values.reth.signer.localFile.path | quote }}
    readOnly: true
{{- end }}
{{- if eq .Values.role "rpc" }}
volumeClaimTemplates:
  - name: data
    accessMode: {{ .Values.reth.data.accessMode | quote }}
    size: {{ .Values.reth.data.size | quote }}
    mountPath: {{ .Values.reth.data.mountPath | quote }}
{{- else }}
  data:
    enabled: true
    type: pvc
    size: {{ .Values.reth.data.size | quote }}
    mountPath: {{ .Values.reth.data.mountPath | quote }}
    accessMode: {{ .Values.reth.data.accessMode | quote }}
    retain: {{ .Values.reth.data.retain }}
volumeClaimTemplates: []
{{- end }}
service:
{{ include "l2-reth.service" . | nindent 2 }}
probes:
{{ include "l2-reth.probes" . | nindent 2 }}
{{- end -}}

{{/*
Render l2-reth container ports explicitly. The common chart derives container
ports from every enabled Service port, which duplicates the P2P container ports
when a bootnode has both an internal P2P Service and an external P2P
LoadBalancer Service.
*/}}
{{- define "scroll.common.lib.container.ports" -}}
{{- if .Values.reth.http.enabled }}
- name: http
  containerPort: {{ .Values.reth.ports.http }}
  protocol: TCP
{{- end }}
{{- if .Values.reth.ws.enabled }}
- name: ws
  containerPort: {{ .Values.reth.ports.ws }}
  protocol: TCP
{{- end }}
- name: metrics
  containerPort: {{ .Values.reth.ports.metrics }}
  protocol: TCP
- name: p2p-tcp
  containerPort: {{ .Values.reth.ports.p2p }}
  protocol: TCP
- name: p2p-udp
  containerPort: {{ .Values.reth.ports.p2p }}
  protocol: UDP
{{- end -}}

{{/*
Generate rollup-node argv without shell interpolation.
*/}}
{{- define "l2-reth.extraArgs" -}}
{{- $extraArgs := .Values.reth.extraArgs -}}
{{- if kindIs "string" $extraArgs -}}
{{- range $arg := regexSplit "\\s+" (trim $extraArgs) -1 }}
{{- if $arg }}
- {{ $arg | quote }}
{{- end }}
{{- end }}
{{- else if kindIs "slice" $extraArgs -}}
{{- range $extraArgs }}
- {{ . | quote }}
{{- end }}
{{- else if $extraArgs -}}
{{- fail "reth.extraArgs must be a string or a list of strings" -}}
{{- end -}}
{{- end -}}

{{- define "l2-reth.args" -}}
- node
- --chain
- {{ .Values.reth.genesis.chainPath | quote }}
- --network-id
- {{ .Values.reth.networkId | quote }}
- --datadir={{ .Values.reth.data.mountPath }}
- --metrics=0.0.0.0:{{ .Values.reth.ports.metrics }}
- --port={{ .Values.reth.ports.p2p }}
{{- if ne (default "pvcAutoGenerate" .Values.reth.nodeKey.mode) "none" }}
- --p2p-secret-key
- {{ .Values.reth.nodeKey.path | quote }}
{{- end }}
- --disable-discovery
{{- with .Values.reth.trustedPeers }}
- --trusted-peers
- {{ . | quote }}
{{- end }}
{{- if and (eq .Values.role "rpc") .Values.reth.rpc.trustedOnly }}
- --trusted-only
{{- end }}
{{- if .Values.reth.rpc.maxOutboundPeers }}
- --max-outbound-peers
- {{ .Values.reth.rpc.maxOutboundPeers | quote }}
{{- end }}
{{- if .Values.reth.rpc.maxInboundPeers }}
- --max-inbound-peers
- {{ .Values.reth.rpc.maxInboundPeers | quote }}
{{- end }}
- --l1.url
- {{ .Values.reth.l1Url | quote }}
- --l1.liveness-threshold
- {{ .Values.reth.l1LivenessThreshold | quote }}
- --l1.liveness-check-interval
- {{ .Values.reth.l1LivenessCheckInterval | quote }}
{{- with .Values.reth.blobS3Url }}
- --blob.s3_url
- {{ . | quote }}
{{- end }}
{{- with .Values.reth.rpc.sequencerUrl }}
- --network.sequencer-url
- {{ . | quote }}
{{- end }}
{{- if eq (default "none" .Values.reth.signer.type) "awsKms" }}
- --signer.aws-kms-key-id
- {{ .Values.reth.signer.awsKmsKeyId | quote }}
{{- else if eq (default "none" .Values.reth.signer.type) "localFile" }}
- --signer.key-file
- {{ .Values.reth.signer.localFile.path | quote }}
{{- end }}
{{- if eq .Values.role "sequencer" }}
{{- if .Values.reth.sequencer.enabled }}
- --sequencer.enabled
- --sequencer.block-time
- {{ .Values.reth.sequencer.blockTimeMs | quote }}
- --sequencer.payload-building-duration
- {{ .Values.reth.sequencer.payloadBuildingDurationMs | quote }}
- --sequencer.l1-inclusion-mode
- {{ .Values.reth.sequencer.l1InclusionMode | quote }}
- --sequencer.fee-recipient
- {{ .Values.reth.sequencer.feeRecipient | quote }}
{{- if .Values.reth.sequencer.autoStart }}
- --sequencer.auto-start
{{- end }}
{{- if .Values.reth.sequencer.allowEmptyBlocks }}
- --sequencer.allow-empty-blocks
{{- end }}
{{- end }}
{{- end }}
{{- if .Values.reth.builderGasLimit }}
- --builder.gaslimit={{ .Values.reth.builderGasLimit }}
{{- end }}
- --engine.sync-at-startup
- {{ .Values.reth.engineSyncAtStartup | quote }}
{{- if .Values.reth.engineLegacyStateRoot }}
- --engine.legacy-state-root
{{- end }}
{{- if .Values.reth.rpc.disableTransactionsBackup }}
- --txpool.disable-transactions-backup
{{- end }}
- --ipcpath
- {{ .Values.reth.ipcPath | quote }}
- --ipc.permissions
- {{ .Values.reth.ipcPermissions | quote }}
{{- if .Values.reth.http.enabled }}
- --http
- --http.addr={{ .Values.reth.http.addr }}
- --http.port={{ .Values.reth.ports.http }}
- --http.corsdomain
- {{ .Values.reth.http.corsDomain | quote }}
- --http.api
- {{ .Values.reth.http.api | quote }}
{{- end }}
{{- if .Values.reth.ws.enabled }}
- --ws
- --ws.addr={{ .Values.reth.ws.addr }}
- --ws.port={{ .Values.reth.ports.ws }}
- --ws.api
- {{ .Values.reth.ws.api | quote }}
{{- end }}
{{- if .Values.reth.rpc.rollupNode }}
- --rpc.rollup-node=true
{{- end }}
{{- if .Values.reth.rpc.rollupNodeAdmin }}
- --rpc.rollup-node-admin
{{- end }}
{{- with .Values.reth.rpc.maxConnections }}
- --rpc.max-connections={{ . }}
{{- end }}
{{- with .Values.reth.rpc.maxRequestSize }}
- --rpc.max-request-size={{ . }}
{{- end }}
{{- with .Values.reth.rpc.maxResponseSize }}
- --rpc.max-response-size={{ . }}
{{- end }}
{{- with .Values.reth.rpc.maxSubscriptionsPerConnection }}
- --rpc.max-subscriptions-per-connection={{ . }}
{{- end }}
{{- with .Values.reth.rpc.maxBlocksPerFilter }}
- --rpc.max-blocks-per-filter={{ . }}
{{- end }}
{{- with .Values.reth.rpc.maxLogsPerResponse }}
- --rpc.max-logs-per-response={{ . }}
{{- end }}
{{- with .Values.reth.rpc.maxTracingRequests }}
- --rpc.max-tracing-requests={{ . }}
{{- end }}
- --log.stdout.format
- {{ .Values.reth.logFormat | quote }}
{{ include "l2-reth.extraArgs" . }}
{{- if gt (int .Values.reth.verbosity) 0 }}
- {{ printf "-%s" (repeat (int .Values.reth.verbosity) "v") | quote }}
{{- end }}
{{- end -}}

{{- define "l2-reth.service" -}}
main:
  enabled: true
  type: {{ .Values.service.main.type | default "ClusterIP" }}
  {{- with .Values.service.main.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  ports:
    http:
      enabled: {{ .Values.reth.http.enabled }}
      port: {{ .Values.reth.ports.http }}
      targetPort: {{ .Values.reth.ports.http }}
    ws:
      enabled: {{ .Values.reth.ws.enabled }}
      port: {{ .Values.reth.ports.ws }}
      targetPort: {{ .Values.reth.ports.ws }}
    metrics:
      enabled: true
      port: {{ .Values.reth.ports.metrics }}
      targetPort: {{ .Values.reth.ports.metrics }}
    p2p:
      enabled: {{ .Values.reth.service.p2p.enabled }}
      port: {{ .Values.reth.ports.p2p }}
      targetPort: {{ .Values.reth.ports.p2p }}
      protocol: TCP
    p2p-udp:
      enabled: {{ .Values.reth.service.p2p.enabled }}
      port: {{ .Values.reth.ports.p2p }}
      targetPort: {{ .Values.reth.ports.p2p }}
      protocol: UDP
{{- with .Values.reth.service.extra }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{- define "l2-reth.probes" -}}
startup:
  enabled: true
  custom: true
  spec:
    tcpSocket:
      port: {{ .Values.reth.ports.http }}
    periodSeconds: 10
    failureThreshold: 720
    timeoutSeconds: 1
liveness:
  enabled: true
  custom: true
  spec:
    tcpSocket:
      port: {{ .Values.reth.ports.http }}
    periodSeconds: 20
    timeoutSeconds: 3
    failureThreshold: 6
readiness:
  enabled: true
  custom: true
  spec:
{{- if eq .Values.role "bootnode" }}
    tcpSocket:
      port: {{ .Values.reth.ports.p2p }}
    periodSeconds: 10
    timeoutSeconds: 3
    failureThreshold: 3
{{- else }}
    exec:
      command:
        - /bin/sh
        - -ec
        - |
          resp="$(curl -fsS -m 2 \
            -H 'Content-Type: application/json' \
            --data '{"jsonrpc":"2.0","method":"eth_syncing","params":[],"id":1}' \
            http://127.0.0.1:{{ .Values.reth.ports.http }})"
          echo "$resp" | grep -q '"result":false'
    periodSeconds: 10
    timeoutSeconds: 3
    failureThreshold: 3
{{- end }}
{{- end -}}

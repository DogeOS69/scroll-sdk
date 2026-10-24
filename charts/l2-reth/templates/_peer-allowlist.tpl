{{- define "l2-reth.peerAllowlist.validate" -}}
{{- if .Values.reth.peerAllowlist.enabled -}}
  {{- if ne .Values.role "bootnode" -}}
    {{- fail "reth.peerAllowlist requires role bootnode" -}}
  {{- end -}}
  {{- range $peer := splitList "," .Values.reth.trustedPeers -}}
    {{- if and $peer (not (regexMatch "^enode://[0-9a-fA-F]{128}@[^[:space:]]+$" $peer)) -}}
      {{- fail "reth.peerAllowlist requires reth.trustedPeers to contain address-bearing enode URLs" -}}
    {{- end -}}
  {{- end -}}
  {{- if not (regexMatch "^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$" .Values.reth.peerAllowlist.configMapName) -}}
    {{- fail "reth.peerAllowlist.configMapName must be a ConfigMap name in the same namespace" -}}
  {{- end -}}
  {{- range $field := list "intervalSeconds" "rpcTimeoutSeconds" -}}
    {{- if not (regexMatch "^[1-9][0-9]*$" (toString (get $.Values.reth.peerAllowlist $field))) -}}
      {{- fail (printf "reth.peerAllowlist.%s must be a positive integer" $field) -}}
    {{- end -}}
  {{- end -}}
  {{- /* Discovery, IPC and admission flags have one owner in this mode. */ -}}
  {{- range $arg := (include "l2-reth.extraArgs" . | fromYamlArray) -}}
    {{- if regexMatch "^--((trusted-only|trusted-peers|bootnodes|peers-file|no-persist-peers|max-outbound-peers|disable-discovery|config)(=|$)|discovery[.]|ipc)" (toString $arg) -}}
      {{- fail "reth.peerAllowlist does not allow extraArgs to override peering, IPC, discovery or config flags" -}}
    {{- end -}}
  {{- end -}}
  {{- range $api := list .Values.reth.http.api .Values.reth.ws.api -}}
    {{- if has "admin" (splitList "," (replace " " "" $api)) -}}
      {{- fail "reth.peerAllowlist uses IPC: remove admin from reth.http.api and reth.ws.api" -}}
    {{- end -}}
  {{- end -}}
  {{- if (default dict .Values.common).reth -}}
    {{- fail "common.reth is not supported with reth.peerAllowlist; use top-level reth values" -}}
  {{- end -}}
{{- end -}}
{{- end -}}

{{- define "l2-reth.peerAllowlist.generatedValues" -}}
{{- $staticIDs := list -}}
{{- range $peer := splitList "," .Values.reth.trustedPeers -}}
{{- if $peer -}}
{{- $staticIDs = append $staticIDs (first (splitList "@" $peer)) -}}
{{- end -}}
{{- end -}}
configMaps:
  peer-allowlist-controller:
    enabled: true
    data:
      static-peer-ids.json: {{ mustToJson $staticIDs | quote }}
      peer_allowlist.py: |
{{ .Files.Get "files/peer_allowlist.py" | indent 8 }}
persistence:
  peer-allowlist-ipc:
    enabled: true
    type: emptyDir
    mountPath: /run/reth-allowlist
  peer-allowlist-state:
    enabled: true
    type: emptyDir
    mountPath: "-"
  peer-allowlist-policy:
    enabled: true
    type: configMap
    name: {{ .Values.reth.peerAllowlist.configMapName | quote }}
    mountPath: "-"
    items:
      - key: peers.json
        path: peers.json
  peer-allowlist-code:
    enabled: true
    type: configMap
    name: {{ printf "%s-peer-allowlist-controller" (include "scroll.common.lib.chart.names.fullname" .) | quote }}
    mountPath: "-"
sidecars:
  peer-allowlist:
    image: {{ .Values.reth.peerAllowlist.image | quote }}
    imagePullPolicy: IfNotPresent
    command: [python3, -B, /opt/peer-allowlist/peer_allowlist.py]
    args:
      - --static-peers
      - /opt/peer-allowlist/static-peer-ids.json
      - --interval
      - {{ .Values.reth.peerAllowlist.intervalSeconds | quote }}
      - --rpc-timeout
      - {{ .Values.reth.peerAllowlist.rpcTimeoutSeconds | quote }}
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop: [ALL]
      # IPC mode 0600 requires the same UID as the execution client.
      runAsUser: {{ dig "runAsUser" (dig "runAsUser" 0 (default dict .Values.podSecurityContext)) (default dict .Values.securityContext) }}
    resources:
{{ toYaml .Values.reth.peerAllowlist.resources | indent 6 }}
    readinessProbe:
      exec:
        command:
          - python3
          - -B
          - /opt/peer-allowlist/peer_allowlist.py
          - --healthcheck
          - --max-age
          - {{ max 60 (mul 3 (int .Values.reth.peerAllowlist.intervalSeconds)) | quote }}
      periodSeconds: 10
      timeoutSeconds: 3
      failureThreshold: 1
    volumeMounts:
      - name: peer-allowlist-code
        mountPath: /opt/peer-allowlist
        readOnly: true
      - name: peer-allowlist-policy
        mountPath: /etc/reth-allowlist
        readOnly: true
      - name: peer-allowlist-ipc
        mountPath: /run/reth-allowlist
      - name: peer-allowlist-state
        # Alpine aliases /var/run to /run; do not shadow the shared IPC mount.
        mountPath: /var/lib/reth-peer-allowlist
{{- end -}}

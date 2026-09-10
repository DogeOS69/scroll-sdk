{{/* Keep Grafana and Prometheus fallback definitions identical. */}}
{{- define "scroll-monitor.metricGroups" -}}
{{/* Reconstruct the shipped confirmation query only for conservative migration.
     Legacy values are accepted here but never affect the new stall expression. */}}
{{- $legacyDepths := .Values.dogecoinIndexerAlerts.confirmationsByJob | default (dict "l1-interface" 6 "withdrawal-processor" 6) -}}
{{- $legacyThreshold := 12 -}}
{{- if hasKey .Values.dogecoinIndexerAlerts "maxExcessLagBlocks" -}}
{{- $legacyThreshold = .Values.dogecoinIndexerAlerts.maxExcessLagBlocks -}}
{{- end -}}
{{- $indexerQueries := list -}}
{{- range $job, $confirmations := $legacyDepths -}}
{{- $indexerQueries = append $indexerQueries (printf "clamp_min((max by (namespace) (dogecoin_chain_block_height) - on (namespace) group_right max by (namespace, job) (indexer_dogecoin_last_synced_block{job=%s})) - %v, 0) > %v" ($job | quote) $confirmations $legacyThreshold) -}}
{{- end -}}
{{- $metric := printf "indexer_dogecoin_last_synced_block{job=~%s}" (.Values.dogecoinIndexerAlerts.jobRegex | quote) -}}
{{- $groups := (.Files.Get "alerts/dogeos.yaml" | replace "__INDEXER_METRIC__" $metric | replace "__LEGACY_INDEXER_LAG_EXPR__" (join " or " $indexerQueries) | replace "__INDEXER_MAX_EXCESS_LAG__" (toString $legacyThreshold) | fromYaml).groups -}}
{{- if .Values.businessAlerts.enabled -}}
{{- $business := .Files.Get "alerts/business.yaml" | replace "__JOB_MAX_AGE__" (toString .Values.businessAlerts.jobMaxAgeSeconds) | replace "__PROOF_STUCK_FOR__" .Values.businessAlerts.proofStuckFor | replace "__RECOVERY_FOR__" .Values.businessAlerts.recoveryFor | replace "__SIGNER_FAILURE_FOR__" .Values.businessAlerts.signerFailureFor | replace "__PUBLICATION_DEADLINE__" (toString .Values.businessAlerts.publicationDeadlineSeconds) | fromYaml -}}
{{- $groups = concat $groups $business.groups -}}
{{- $quorum := list -}}
{{- range $role, $threshold := .Values.businessAlerts.requiredSignersByRole -}}
{{- $expr := printf "max by (namespace, job) (tso_core_registered_signers_by_role{role=%s}) < %v or (max by (namespace, job) (tso_core_registered_signers_count) unless max by (namespace, job) (tso_core_registered_signers_by_role{role=%s}))" ($role | quote) $threshold ($role | quote) -}}
{{- $quorum = append $quorum (dict "alert" (printf "TSO%sQuorumUnavailable" $role) "expr" $expr "for" "5m" "labels" (dict "severity" "critical" "service" "tso-service" "role" $role) "annotations" (dict "summary" (printf "TSO %s signer quorum is unavailable." $role) "description" (printf "Registered %s signers are below the configured requirement of %v. Check signer registration and policy thresholds." $role $threshold))) -}}
{{- end -}}
{{- if $quorum -}}
{{- $groups = append $groups (dict "name" "dogeos.quorum" "interval" "1m" "rules" $quorum) -}}
{{- end -}}
{{- end -}}
{{- if .Values.balanceMonitoring.enabled -}}
{{- $balances := .Files.Get "alerts/balances.yaml" | replace "__FEE_ORACLE_MIN_ETH__" (toString .Values.balanceMonitoring.ethereum.feeOracle.minimumEth) | replace "__ETH_DA_MIN_ETH__" (toString .Values.balanceMonitoring.ethereum.ethDaSubmitter.minimumEth) | fromYaml -}}
{{- $groups = concat $groups $balances.groups -}}
{{- if .Values.balanceMonitoring.feeWallet.enabled -}}
{{- $wallet := .Files.Get "alerts/fee-wallet.yaml" | replace "__MIN_DOGE__" (toString .Values.balanceMonitoring.feeWallet.minimumDoge) | replace "__JOB_REGEX__" .Values.balanceMonitoring.feeWallet.jobRegex | fromYaml -}}
{{- $groups = concat $groups $wallet.groups -}}
{{- end -}}
{{- end -}}
{{/* Prometheus has no pause state. Omit paused diagnostics from its fallback. */}}
{{- $grafanaManaged := and .Values.grafana.enabled .Values.grafanaAlerting.enabled -}}
{{- if and .Values.serviceAlerts.enabled (or $grafanaManaged (not .Values.serviceAlerts.paused)) -}}
{{- range $path, $_ := .Files.Glob "alerts/services/*.yaml" -}}
{{- $serviceGroups := ($.Files.Get $path | fromYaml).groups -}}
{{- if $grafanaManaged -}}
{{- range $group := $serviceGroups -}}
{{- range $rule := $group.rules -}}
{{- $_ := set $rule "isPaused" $.Values.serviceAlerts.paused -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- $groups = concat $groups $serviceGroups -}}
{{- end -}}
{{- end -}}
{{/* Migration metadata belongs to the Grafana seeder, not Prometheus rules. */}}
{{- if not $grafanaManaged -}}
{{- range $group := $groups -}}
{{- range $rule := $group.rules -}}
{{- $_ := unset $rule "previousExpr" -}}
{{- $_ := unset $rule "previousAnnotations" -}}
{{- $_ := unset $rule "previousFor" -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- dict "groups" $groups | toYaml -}}
{{- end -}}

{{/* Explicit overrides are authoritative, including for existing Grafana rules. */}}
{{- define "scroll-monitor.pauseRules" -}}
{{- $pauses := dict -}}
{{- if not .Values.balanceMonitoring.ethereum.feeOracle.enabled -}}
{{- $_ := set $pauses "FeeOracleAccountBalanceLow" true -}}
{{- $_ := set $pauses "FeeOracleBalanceMonitorMissing" true -}}
{{- end -}}
{{- if not .Values.balanceMonitoring.ethereum.ethDaSubmitter.enabled -}}
{{- $_ := set $pauses "EthDASubmitterAccountBalanceLow" true -}}
{{- $_ := set $pauses "EthDASubmitterBalanceMonitorMissing" true -}}
{{- end -}}
{{- mergeOverwrite $pauses .Values.grafanaAlerting.pauseRules | toYaml -}}
{{- end -}}

{{/* Cached facts require source success and age, not just a fresh scrape. */}}
{{- define "scroll-monitor.snapshotGuard" -}}
{{- printf "(%s == 1 and on (namespace, job, instance) (%s <= time() and time() - %s < 120) and on (namespace, job, instance) (up == 1))" .valid .timestamp .timestamp -}}
{{- end -}}

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
{{- if and .Values.statusPage.enabled (ge (int ((.Values.statusPage.generated | default dict).version | default 0)) 3) ((.Values.statusPage.publication | default dict).delivery | default dict).enabled -}}
{{- $statusService := printf "%s-status-delivery" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- $statusAlerts := .Files.Get "alerts/status-page.yaml" | replace "__STATUS_NAMESPACE__" .Release.Namespace | replace "__STATUS_SERVICE__" $statusService | fromYaml -}}
{{- $groups = concat $groups $statusAlerts.groups -}}
{{- end -}}
{{- if .Values.businessAlerts.enabled -}}
{{- $business := .Files.Get "alerts/business.yaml" | replace "__JOB_MAX_AGE__" (toString .Values.businessAlerts.jobMaxAgeSeconds) | replace "__PROOF_STUCK_FOR__" .Values.businessAlerts.proofStuckFor | replace "__RECOVERY_FOR__" .Values.businessAlerts.recoveryFor | replace "__SIGNER_FAILURE_FOR__" .Values.businessAlerts.signerFailureFor | replace "__PUBLICATION_DEADLINE__" (toString .Values.businessAlerts.publicationDeadlineSeconds) | fromYaml -}}
{{- $groups = concat $groups $business.groups -}}
{{- $quorum := list -}}
{{- range $role, $threshold := .Values.businessAlerts.requiredSignersByRole -}}
{{- $previous := printf "max by (namespace, job) (tso_core_registered_signers_by_role{role=%s}) < %v or (max by (namespace, job) (tso_core_registered_signers_count) unless max by (namespace, job) (tso_core_registered_signers_by_role{role=%s}))" ($role | quote) $threshold ($role | quote) -}}
{{- $expr := printf "max by (namespace, job, instance) (tso_core_registered_signers_by_role{role=%s} and on (namespace, job, instance) __TSO_REGISTRY_VALID__) < %v" ($role | quote) $threshold -}}
{{- $quorum = append $quorum (dict "alert" (printf "TSO%sQuorumUnavailable" $role) "expr" $expr "previousExpr" $previous "for" "5m" "labels" (dict "severity" "critical" "service" "tso-service" "role" $role) "annotations" (dict "summary" (printf "TSO %s signer quorum is unavailable." $role) "description" (printf "Registered %s signers are below the configured requirement of %v. Check signer registration and policy thresholds." $role $threshold))) -}}
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
{{- if and .Values.dstack.enabled .Values.dstack.alerts.enabled -}}
{{- $dstack := .Files.Get "alerts/dstack.yaml" | replace "__DSTACK_NAMESPACE__" .Values.dstack.namespace | replace "__DSTACK_CONTROLLER__" .Values.dstack.controllerName | replace "__DSTACK_UNAVAILABLE_FOR__" .Values.dstack.alerts.unavailableFor | replace "__DSTACK_FAILED_RUNS__" (toString .Values.dstack.alerts.failedRunsThreshold) | fromYaml -}}
{{- $groups = concat $groups $dstack.groups -}}
{{- if .Values.dstack.gpuHosts.enabled -}}
{{- $hostGroups := include "scroll-monitor.dstackHostRules" . | fromYaml -}}
{{- $groups = concat $groups $hostGroups.groups -}}
{{- end -}}
{{- end -}}
{{- $guards := dict -}}
{{- $_ := set $guards "__TSO_REGISTRY_VALID__" (include "scroll-monitor.snapshotGuard" (dict "valid" "tso_core_registry_snapshot_valid" "timestamp" "tso_core_registry_snapshot_timestamp_seconds")) -}}
{{- $_ := set $guards "__TSO_STATUS_VALID__" (include "scroll-monitor.snapshotGuard" (dict "valid" "tso_core_metrics_snapshot_valid" "timestamp" "tso_core_observation_timestamp_seconds")) -}}
{{- range $source := list "jobs" "proof_work" -}}
{{- $_ := set $guards (printf "__WP_%s_VALID__" (upper $source)) (include "scroll-monitor.snapshotGuard" (dict "valid" (printf "withdrawal_processor_protocol_snapshot_valid{source=%s}" ($source | quote)) "timestamp" (printf "withdrawal_processor_protocol_snapshot_timestamp_seconds{source=%s}" ($source | quote)))) -}}
{{- end -}}
{{/* Apply explicit pauses to Grafana and omit them in the Prometheus fallback. */}}
{{- $pauses := include "scroll-monitor.pauseRules" . | fromYaml -}}
{{- $filteredGroups := list -}}
{{- range $group := $groups -}}
{{- $rules := list -}}
{{- range $rule := $group.rules -}}
{{- range $marker, $guard := $guards -}}
{{- $_ := set $rule "expr" (replace $marker $guard $rule.expr) -}}
{{- end -}}
{{- if hasKey $pauses $rule.alert -}}
{{- $_ := set $rule "isPaused" (index $pauses $rule.alert) -}}
{{- end -}}
{{- if or $grafanaManaged (not ($rule.isPaused | default false)) -}}
{{- if not $grafanaManaged -}}
{{- $_ := unset $rule "previousExpr" -}}
{{- $_ := unset $rule "previousAnnotations" -}}
{{- $_ := unset $rule "previousFor" -}}
{{- $_ := unset $rule "isPaused" -}}
{{- end -}}
{{- $rules = append $rules $rule -}}
{{- end -}}
{{- end -}}
{{- if $rules -}}
{{- $_ := set $group "rules" $rules -}}
{{- $filteredGroups = append $filteredGroups $group -}}
{{- end -}}
{{- end -}}
{{- dict "groups" $filteredGroups | toYaml -}}
{{- end -}}

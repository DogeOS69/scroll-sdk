#!/usr/bin/env node

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const upstreamRepository = "https://github.com/scroll-tech/rollup-node";
const upstreamTag = "v1.0.7-rc6";
const upstreamCommit = "bc3d5006c41b38cc442ebe92d1afc4285fc43ca1";
const upstreamDirectory = "docker-compose/resource/dashboards";
const rawBase = `https://raw.githubusercontent.com/scroll-tech/rollup-node/${upstreamCommit}/${upstreamDirectory}`;
const sourcePage = `${upstreamRepository}/tree/${upstreamTag}/${upstreamDirectory}`;
const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const outputDirectory = resolve(scriptDirectory, "../grafana/reth-dashboards");
const prometheusDatasource = { type: "prometheus", uid: "${datasource}" };
const lokiDatasource = { type: "loki", uid: "${loki}" };
// The internal RPC workload is named l2-reth-rpc, while its production
// Kubernetes Service (and therefore Prometheus `service` target label) is
// intentionally named l2-rpc. Accept both forms so dashboard discovery follows
// the rendered topology rather than assuming release and Service names match.
const rethServicePattern = "l2-reth-(sequencer|bootnode)-[0-9]+|l2-reth-rpc(-public)?|l2-rpc";
const scopeMatchers = [
  'namespace=~"$namespace"',
  'service=~"$service"',
  'pod=~"$pod"',
];

const dashboards = [
  ["overview.json", "overview.json", "Scroll L2 Reth Overview", "scroll-l2-reth-overview"],
  ["performance.json", "performance.json", "Scroll L2 Reth Performance", "scroll-l2-reth-performance"],
  ["rollup_node.json", "rollup-node.json", "Scroll Rollup Node", "scroll-l2-rollup-node"],
  ["state_history.json", "state-history.json", "Scroll L2 Reth State & History", "scroll-l2-reth-state-history"],
  ["transaction_pool.json", "transaction-pool.json", "Scroll L2 Reth Transaction Pool", "scroll-l2-reth-transaction-pool"],
];

function splitMatchers(selector) {
  const matchers = [];
  let start = 0;
  let quoted = false;
  let escaped = false;

  for (let index = 0; index < selector.length; index += 1) {
    const character = selector[index];
    if (escaped) {
      escaped = false;
    } else if (character === "\\") {
      escaped = true;
    } else if (character === '"') {
      quoted = !quoted;
    } else if (character === "," && !quoted) {
      matchers.push(selector.slice(start, index).trim());
      start = index + 1;
    }
  }

  matchers.push(selector.slice(start).trim());
  return matchers.filter(Boolean);
}

function scopedSelector(selector = "") {
  const retained = splitMatchers(selector).filter((matcher) => {
    const label = matcher.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*(?:!?=~?)/)?.[1];
    return !["instance", "namespace", "service", "pod", "node"].includes(label);
  });
  return `{${[...scopeMatchers, ...retained].join(",")}}`;
}

function scopeExpression(expression) {
  let result = expression.replace(
    /\b(reth_[A-Za-z0-9_:]+|rpc_height)(?:\{([^{}]*)\})?/g,
    (_, metric, selector) => `${metric}${scopedSelector(selector)}`,
  );

  // A few upstream expressions use non-prefixed legacy metrics but still carry
  // the Docker Compose `instance` selector. Scope those to the selected K8s pod.
  result = result.replace(
    /\b([A-Za-z_:][A-Za-z0-9_:]*)\{([^{}]*\binstance\s*(?:!?=~?)[^{}]*)\}/g,
    (_, metric, selector) => `${metric}${scopedSelector(selector)}`,
  );
  return result;
}

function queryVariable(name, query, refresh = 2) {
  return {
    current: {},
    datasource: prometheusDatasource,
    definition: query,
    hide: 0,
    includeAll: false,
    multi: false,
    name,
    options: [],
    query: {
      query,
      refId: `PrometheusVariableQueryEditor-${name}`,
    },
    refresh,
    regex: "",
    skipUrlSync: false,
    sort: 1,
    type: "query",
  };
}

function detailedVariables(originalVariables) {
  const interval = originalVariables.find((variable) => variable.name === "interval");
  return [
    {
      current: { selected: true, text: "Prometheus", value: "scroll-prometheus" },
      hide: 0,
      includeAll: false,
      multi: false,
      name: "datasource",
      options: [],
      query: "prometheus",
      refresh: 1,
      regex: "",
      skipUrlSync: false,
      type: "datasource",
    },
    queryVariable("namespace", "label_values(reth_info, namespace)", 1),
    queryVariable(
      "service",
      `label_values(reth_info{namespace=~"$namespace",service=~"${rethServicePattern}"}, service)`,
    ),
    queryVariable(
      "pod",
      'label_values(reth_info{namespace=~"$namespace",service=~"$service"}, pod)',
    ),
    ...(interval ? [{ ...interval, current: interval.current ?? {} }] : []),
  ];
}

function transformObject(value) {
  if (Array.isArray(value)) {
    return value.map(transformObject);
  }
  if (value === null || typeof value !== "object") {
    return value;
  }

  const transformed = {};
  for (const [key, child] of Object.entries(value)) {
    if (key === "datasource" && child?.type === "prometheus") {
      transformed[key] = prometheusDatasource;
    } else if (key === "expr" && typeof child === "string") {
      transformed[key] = scopeExpression(child);
    } else {
      transformed[key] = transformObject(child);
    }
  }
  return transformed;
}

function adaptDashboard(upstream, title, uid, sourceFile) {
  const dashboard = transformObject(upstream);
  dashboard.id = null;
  dashboard.uid = uid;
  dashboard.title = title;
  dashboard.tags = ["reth", "scroll", "l2", "service", "upstream-dashboard"];
  dashboard.description =
    `Adapted for Kubernetes from scroll-tech/rollup-node ${upstreamTag} (${upstreamCommit}) ` +
    `(${upstreamDirectory}/${sourceFile}). Select one namespace, service, and pod for drill-down. ` +
    `Upstream source: ${sourcePage}`;
  dashboard.templating = {
    ...(dashboard.templating ?? {}),
    list: detailedVariables(upstream.templating?.list ?? []),
  };

  if (sourceFile === "rollup_node.json") {
    const syncHeight = dashboard.panels.find((panel) => panel.title === "Sync height");
    if (syncHeight) {
      // The upstream Docker Compose panel compares l2reth with an l2geth node
      // and a hard-coded RPC service. The Kubernetes dashboard is a one-pod
      // drill-down, while fleet comparison lives in fleet.json.
      syncHeight.targets = syncHeight.targets
        .filter((target) => target.expr?.startsWith("reth_blockchain_tree_canonical_chain_height"))
        .slice(0, 1)
        .map((target) => ({ ...target, legendFormat: "{{pod}}" }));
      syncHeight.description = "Canonical chain height for the selected Scroll L2 Reth pod.";
    }
  }

  return dashboard;
}

function fieldConfig(unit = "short", min = undefined) {
  const defaults = {
    color: { mode: "palette-classic" },
    custom: {
      axisCenteredZero: false,
      axisColorMode: "text",
      axisLabel: "",
      axisPlacement: "auto",
      barAlignment: 0,
      drawStyle: "line",
      fillOpacity: 8,
      gradientMode: "none",
      hideFrom: { legend: false, tooltip: false, viz: false },
      lineInterpolation: "linear",
      lineWidth: 1,
      pointSize: 5,
      scaleDistribution: { type: "linear" },
      showPoints: "never",
      spanNulls: true,
      stacking: { group: "A", mode: "none" },
      thresholdsStyle: { mode: "off" },
    },
    mappings: [],
    thresholds: {
      mode: "absolute",
      steps: [
        { color: "green", value: null },
        { color: "red", value: 1 },
      ],
    },
    unit,
  };
  if (min !== undefined) defaults.min = min;
  return { defaults, overrides: [] };
}

function target(expr, legendFormat, refId, datasource = prometheusDatasource) {
  return {
    datasource,
    editorMode: "code",
    expr,
    legendFormat,
    range: true,
    refId,
  };
}

function timeseries(id, title, description, gridPos, targets, unit = "short") {
  return {
    datasource: prometheusDatasource,
    description,
    fieldConfig: fieldConfig(unit, 0),
    gridPos,
    id,
    options: {
      legend: { calcs: ["lastNotNull"], displayMode: "table", placement: "bottom", showLegend: true },
      tooltip: { mode: "multi", sort: "desc" },
    },
    targets,
    title,
    type: "timeseries",
  };
}

function stat(id, title, description, gridPos, targets, unit = "short", thresholds = undefined) {
  const config = fieldConfig(unit, 0);
  if (thresholds) config.defaults.thresholds = thresholds;
  return {
    datasource: prometheusDatasource,
    description,
    fieldConfig: config,
    gridPos,
    id,
    options: {
      colorMode: "value",
      graphMode: "area",
      justifyMode: "auto",
      orientation: "auto",
      reduceOptions: { calcs: ["lastNotNull"], fields: "", values: false },
      textMode: "auto",
      wideLayout: true,
    },
    targets,
    title,
    type: "stat",
  };
}

function row(id, title, y) {
  return { collapsed: false, gridPos: { h: 1, w: 24, x: 0, y }, id, panels: [], title, type: "row" };
}

function fleetDashboard() {
  const healthyThresholds = {
    mode: "absolute",
    steps: [
      { color: "green", value: null },
      { color: "red", value: 1 },
    ],
  };
  const panels = [
    row(1, "Fleet health", 0),
    {
      datasource: prometheusDatasource,
      fieldConfig: { defaults: {}, overrides: [] },
      gridPos: { h: 10, w: 6, x: 0, y: 1 },
      id: 2,
      options: {
        content:
          "### Scroll L2 Reth fleet\n\nThis view compares all deployed rollup-node workloads:\n\n" +
          "- 2 sequencers\n- 2 RPC services\n- 2 bootnodes\n\n" +
          "Use this dashboard for fleet-level health and divergence. Use the linked upstream-adapted dashboards for a single-pod drill-down.\n\n" +
          "[Overview](/d/scroll-l2-reth-overview) · [Rollup node](/d/scroll-l2-rollup-node) · " +
          "[Performance](/d/scroll-l2-reth-performance) · [State & history](/d/scroll-l2-reth-state-history) · " +
          "[Transaction pool](/d/scroll-l2-reth-transaction-pool)",
        mode: "markdown",
      },
      title: "Coverage and drill-down",
      type: "text",
    },
    stat(3, "Nodes exporting metrics", "Distinct selected pods currently exporting reth_info.", { h: 4, w: 4, x: 6, y: 1 }, [
      target('count(count by (pod) (reth_info{namespace=~"$namespace",service=~"$service",pod=~"$pod"}))', "Nodes", "A"),
    ]),
    stat(4, "Scrape targets down", "Selected Reth ServiceMonitor targets with up == 0.", { h: 4, w: 4, x: 10, y: 1 }, [
      target('sum(up{namespace=~"$namespace",service=~"$service",pod=~"$pod"} == 0)', "Down", "A"),
    ], "short", healthyThresholds),
    stat(5, "Pods not ready", "Selected pods that are not Ready.", { h: 4, w: 4, x: 14, y: 1 }, [
      target('count(count by (pod) (kube_pod_info{namespace=~"$namespace",pod=~"$pod"})) - sum(max by (pod) (kube_pod_status_ready{namespace=~"$namespace",pod=~"$pod",condition="true"}))', "Not ready", "A"),
    ], "short", healthyThresholds),
    stat(6, "Restarts (24h)", "Container restart increases over the last 24 hours.", { h: 4, w: 3, x: 18, y: 1 }, [
      target('sum(increase(kube_pod_container_status_restarts_total{namespace=~"$namespace",pod=~"$pod"}[24h]))', "Restarts", "A"),
    ], "short", healthyThresholds),
    stat(7, "Errors (15m)", "Error, fatal, or panic log lines over the last 15 minutes.", { h: 4, w: 3, x: 21, y: 1 }, [
      target('sum(count_over_time({namespace=~"$namespace",pod=~"$pod"} |~ "(?i)(error|fatal|panic)" [15m]))', "Lines", "A", lokiDatasource),
    ], "short", healthyThresholds),
    {
      datasource: prometheusDatasource,
      description: "Kubernetes readiness by pod.",
      fieldConfig: { defaults: { color: { mode: "thresholds" }, mappings: [], thresholds: { mode: "absolute", steps: [{ color: "red", value: null }, { color: "green", value: 1 }] } }, overrides: [] },
      gridPos: { h: 6, w: 9, x: 6, y: 5 },
      id: 8,
      options: { alignValue: "left", legend: { displayMode: "list", placement: "bottom", showLegend: true }, mergeValues: true, rowHeight: 0.8, showValue: "auto", tooltip: { mode: "single", sort: "none" } },
      targets: [target('max by (pod) (kube_pod_status_ready{namespace=~"$namespace",pod=~"$pod",condition="true"})', "{{pod}}", "A")],
      title: "Pod readiness",
      type: "state-timeline",
    },
    {
      datasource: prometheusDatasource,
      description: "Prometheus scrape health by ServiceMonitor target.",
      fieldConfig: { defaults: { color: { mode: "thresholds" }, mappings: [], thresholds: { mode: "absolute", steps: [{ color: "red", value: null }, { color: "green", value: 1 }] } }, overrides: [] },
      gridPos: { h: 6, w: 9, x: 15, y: 5 },
      id: 9,
      options: { alignValue: "left", legend: { displayMode: "list", placement: "bottom", showLegend: true }, mergeValues: true, rowHeight: 0.8, showValue: "auto", tooltip: { mode: "single", sort: "none" } },
      targets: [target('min by (service, pod, instance) (up{namespace=~"$namespace",service=~"$service",pod=~"$pod"})', "{{service}} / {{pod}}", "A")],
      title: "Prometheus scrape health",
      type: "state-timeline",
    },

    row(10, "Chain, derivation, and L1 watcher", 11),
    timeseries(11, "Canonical chain height", "Canonical chain height by pod; fleet divergence should be investigated.", { h: 8, w: 12, x: 0, y: 12 }, [
      target('reth_blockchain_tree_canonical_chain_height{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}}", "A"),
    ]),
    stat(12, "Height spread", "Maximum minus minimum canonical height across the selected fleet.", { h: 8, w: 4, x: 12, y: 12 }, [
      target('max(reth_blockchain_tree_canonical_chain_height{namespace=~"$namespace",service=~"$service",pod=~"$pod"}) - min(reth_blockchain_tree_canonical_chain_height{namespace=~"$namespace",service=~"$service",pod=~"$pod"})', "Blocks", "A"),
    ], "short", { mode: "absolute", steps: [{ color: "green", value: null }, { color: "yellow", value: 2 }, { color: "red", value: 10 }] }),
    timeseries(13, "Connected peers", "Active Reth peers by pod.", { h: 8, w: 8, x: 16, y: 12 }, [
      target('reth_network_connected_peers{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}}", "A"),
    ]),
    timeseries(14, "Sync checkpoints", "Sync checkpoint height by pod and stage.", { h: 8, w: 8, x: 0, y: 20 }, [
      target('reth_sync_checkpoint{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} / {{stage}}", "A"),
    ]),
    timeseries(15, "Derivation throughput", "Scroll derivation pipeline output and throughput.", { h: 8, w: 8, x: 8, y: 20 }, [
      target('rate(reth_derivation_pipeline_derived_blocks{namespace=~"$namespace",service=~"$service",pod=~"$pod"}[$__rate_interval])', "{{pod}} derived/s", "A"),
      target('reth_derivation_pipeline_blocks_per_second{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} reported blocks/s", "B"),
    ], "ops"),
    timeseries(16, "Derivation queue sizes", "Batch and payload-attributes queue pressure by pod.", { h: 8, w: 8, x: 16, y: 20 }, [
      target('reth_derivation_pipeline_batch_queue_size{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} batches", "A"),
      target('reth_derivation_pipeline_payload_attributes_queue_size{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} payload attributes", "B"),
    ]),
    timeseries(17, "L1 watcher progress", "Observed L1 messages, batch commits, and finalizations by pod.", { h: 8, w: 12, x: 0, y: 28 }, [
      target('reth_l1_watcher_l1_messages{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} messages", "A"),
      target('reth_l1_watcher_batch_commits{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} commits", "B"),
      target('reth_l1_watcher_batch_finalizations{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} finalizations", "C"),
    ]),
    timeseries(18, "L1 watcher reorgs", "Reorg counter rate and observed reorg depth.", { h: 8, w: 12, x: 12, y: 28 }, [
      target('rate(reth_l1_watcher_reorgs{namespace=~"$namespace",service=~"$service",pod=~"$pod"}[$__rate_interval])', "{{pod}} reorgs/s", "A"),
      target('reth_l1_watcher_reorg_depths{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} depth {{quantile}}", "B"),
    ]),

    row(19, "Workload, RPC, and resource pressure", 36),
    timeseries(20, "Rollup-node latency quantiles", "Block building, payload attributes, orchestrator tasks, and signing latency.", { h: 8, w: 12, x: 0, y: 37 }, [
      target('reth_chain_orchestrator_block_building_duration{namespace=~"$namespace",service=~"$service",pod=~"$pod",quantile=~"0.5|0.95|0.99|1.0"}', "{{pod}} block build p{{quantile}}", "A"),
      target('reth_sequencer_payload_attributes_building_duration{namespace=~"$namespace",service=~"$service",pod=~"$pod",quantile=~"0.5|0.95|0.99|1.0"}', "{{pod}} payload attrs p{{quantile}}", "B"),
      target('reth_chain_orchestrator_task_duration{namespace=~"$namespace",service=~"$service",pod=~"$pod",quantile=~"0.5|0.95|0.99|1.0"}', "{{pod}} orchestrator p{{quantile}}", "C"),
      target('reth_signer_signing_duration{namespace=~"$namespace",service=~"$service",pod=~"$pod",quantile=~"0.5|0.95|0.99|1.0"}', "{{pod}} signing p{{quantile}}", "D"),
    ], "s"),
    timeseries(21, "Successful RPC calls", "Successful JSON-RPC calls per second by pod and method.", { h: 8, w: 12, x: 12, y: 37 }, [
      target('sum by (pod, method) (rate(reth_rpc_server_calls_successful_total{namespace=~"$namespace",service=~"$service",pod=~"$pod"}[$__rate_interval]))', "{{pod}} / {{method}}", "A"),
    ], "reqps"),
    timeseries(22, "Transaction pool", "Pending, queued, basefee, and blob transaction counts.", { h: 8, w: 8, x: 0, y: 45 }, [
      target('reth_transaction_pool_pending_pool_transactions{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} pending", "A"),
      target('reth_transaction_pool_queued_pool_transactions{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} queued", "B"),
      target('reth_transaction_pool_basefee_pool_transactions{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} basefee", "C"),
      target('reth_transaction_pool_blob_pool_transactions{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} blob", "D"),
    ]),
    timeseries(23, "Database and static-file storage", "On-disk database and static-file segment sizes by pod.", { h: 8, w: 8, x: 8, y: 45 }, [
      target('sum by (pod) (reth_db_table_size{namespace=~"$namespace",service=~"$service",pod=~"$pod"})', "{{pod}} DB", "A"),
      target('sum by (pod) (reth_static_files_segment_size{namespace=~"$namespace",service=~"$service",pod=~"$pod"})', "{{pod}} static files", "B"),
    ], "bytes"),
    timeseries(24, "Reth process resources", "Process memory, CPU, and open file descriptors exported by Reth.", { h: 8, w: 8, x: 16, y: 45 }, [
      target('reth_process_resident_memory_bytes{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} memory", "A"),
      target('rate(reth_process_cpu_seconds_total{namespace=~"$namespace",service=~"$service",pod=~"$pod"}[$__rate_interval])', "{{pod}} CPU cores", "B"),
      target('reth_process_open_fds{namespace=~"$namespace",service=~"$service",pod=~"$pod"}', "{{pod}} FDs", "C"),
    ]),
    timeseries(25, "Kubernetes CPU, memory, and restarts", "Container-level resource use and restart signals independent of application instrumentation.", { h: 8, w: 24, x: 0, y: 53 }, [
      target('sum by (pod) (rate(container_cpu_usage_seconds_total{namespace=~"$namespace",pod=~"$pod",container!="",image!=""}[$__rate_interval]))', "{{pod}} CPU cores", "A"),
      target('sum by (pod) (container_memory_working_set_bytes{namespace=~"$namespace",pod=~"$pod",container!="",image!=""})', "{{pod}} memory bytes", "B"),
      target('sum by (pod) (increase(kube_pod_container_status_restarts_total{namespace=~"$namespace",pod=~"$pod"}[$__rate_interval]))', "{{pod}} restarts", "C"),
    ]),

    row(26, "Logs", 61),
    timeseries(27, "Warning and error log rate", "Warning, error, fatal, and panic log lines per second by pod.", { h: 9, w: 10, x: 0, y: 62 }, [
      target('sum by (pod) (rate({namespace=~"$namespace",pod=~"$pod"} |~ "(?i)(warn|error|fatal|panic)" [$__interval]))', "{{pod}}", "A", lokiDatasource),
    ], "linesps"),
    {
      datasource: lokiDatasource,
      description: "Recent warning, error, fatal, and panic lines from selected Reth pods.",
      fieldConfig: { defaults: {}, overrides: [] },
      gridPos: { h: 9, w: 14, x: 10, y: 62 },
      id: 28,
      options: { dedupStrategy: "none", enableLogDetails: true, prettifyLogMessage: false, showCommonLabels: false, showLabels: false, showTime: true, sortOrder: "Descending", wrapLogMessage: true },
      targets: [target('{namespace=~"$namespace",pod=~"$pod"} |~ "(?i)(warn|error|fatal|panic)"', "", "A", lokiDatasource)],
      title: "Recent warning and error logs",
      type: "logs",
    },
  ];

  const unitOverrides = {
    24: { A: "bytes", B: "cores", C: "short" },
    25: { A: "cores", B: "bytes", C: "short" },
  };
  for (const [panelId, targetUnits] of Object.entries(unitOverrides)) {
    const panel = panels.find((candidate) => candidate.id === Number(panelId));
    panel.fieldConfig.overrides = Object.entries(targetUnits).map(([refId, unit]) => ({
      matcher: { id: "byFrameRefID", options: refId },
      properties: [{ id: "unit", value: unit }],
    }));
  }

  return {
    annotations: { list: [{ builtIn: 1, datasource: { type: "grafana", uid: "-- Grafana --" }, enable: true, hide: true, iconColor: "rgba(0, 211, 255, 1)", name: "Annotations & Alerts", type: "dashboard" }] },
    description: `Multi-node operations dashboard for Scroll L2 Reth/rollup-node ${upstreamTag} (${upstreamCommit}). Official single-node dashboards are adapted separately from ${sourcePage}`,
    editable: true,
    fiscalYearStartMonth: 0,
    graphTooltip: 1,
    id: null,
    links: [],
    liveNow: false,
    panels,
    refresh: "30s",
    schemaVersion: 39,
    tags: ["reth", "scroll", "l2", "fleet", "service"],
    templating: {
      list: [
        { current: { selected: true, text: "Prometheus", value: "scroll-prometheus" }, hide: 0, includeAll: false, multi: false, name: "datasource", options: [], query: "prometheus", refresh: 1, regex: "", skipUrlSync: false, type: "datasource" },
        { current: { selected: true, text: "Loki", value: "scroll-loki" }, hide: 0, includeAll: false, multi: false, name: "loki", options: [], query: "loki", refresh: 1, regex: "", skipUrlSync: false, type: "datasource" },
        { ...queryVariable("namespace", "label_values(reth_info, namespace)", 1), allValue: ".*", includeAll: true, multi: true, current: { selected: true, text: "All", value: "$__all" } },
        { ...queryVariable("service", `label_values(reth_info{namespace=~"$namespace",service=~"${rethServicePattern}"}, service)`), allValue: ".*", includeAll: true, multi: true, current: { selected: true, text: "All", value: "$__all" } },
        { ...queryVariable("pod", 'label_values(reth_info{namespace=~"$namespace",service=~"$service"}, pod)'), allValue: ".*", includeAll: true, multi: true, current: { selected: true, text: "All", value: "$__all" } },
      ],
    },
    time: { from: "now-6h", to: "now" },
    timepicker: {},
    timezone: "browser",
    title: "Scroll L2 Reth Fleet",
    uid: "scroll-l2-reth-fleet",
    version: 1,
    weekStart: "",
  };
}

await mkdir(outputDirectory, { recursive: true });

for (const [sourceFile, outputFile, title, uid] of dashboards) {
  const response = await fetch(`${rawBase}/${sourceFile}`);
  if (!response.ok) {
    throw new Error(`Failed to download ${sourceFile}: HTTP ${response.status}`);
  }
  const upstream = await response.json();
  const adapted = adaptDashboard(upstream, title, uid, sourceFile);
  await writeFile(resolve(outputDirectory, outputFile), `${JSON.stringify(adapted, null, 2)}\n`);
}

await writeFile(resolve(outputDirectory, "fleet.json"), `${JSON.stringify(fleetDashboard(), null, 2)}\n`);
console.log(`Imported ${dashboards.length} upstream dashboards and generated fleet.json in ${outputDirectory}`);

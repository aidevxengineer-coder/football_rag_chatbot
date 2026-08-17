# Observability on k8s (Phase 5)

This mirrors the docker-compose observability stack
(`docker-compose.observability.yml`) for a real cluster. Two pieces are
plain manifests (no dependency); two are Helm charts, because
hand-rolling Prometheus Operator or a distributed Loki setup in raw YAML
isn't a good use of anyone's time.

Every service already ships with (see `k8s/base/*/deployment.yaml`,
added in this phase):
- `livenessProbe` alongside the existing `readinessProbe`, both on `/health`
- `prometheus.io/scrape`/`port`/`path` annotations (annotation-based scraping fallback)
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317` so tracing works out of the box

## Install order

1. **Traces — otel-collector + Jaeger** (plain manifests, no dependency):
   ```bash
   kubectl apply -f k8s/observability/otel-collector-jaeger.yaml
   ```
   Jaeger UI: `kubectl port-forward -n futbot svc/jaeger 16686:16686`, or via the
   `jaeger.futbot.local` Ingress if your cluster has an ingress controller.

2. **Metrics — kube-prometheus-stack** (Prometheus + Grafana + Alertmanager + the Operator):
   ```bash
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm repo update
   helm install prometheus prometheus-community/kube-prometheus-stack \
     -n futbot --create-namespace \
     -f k8s/observability/prometheus-stack-values.yaml

   kubectl apply -f k8s/observability/servicemonitors.yaml
   kubectl apply -f k8s/observability/prometheus-rules.yaml
   ```
   Grafana: `kubectl port-forward -n futbot svc/prometheus-grafana 3000:80` (admin / admin,
   change it — see `grafana.adminPassword` in the values file).

3. **Logs — loki-stack** (Loki + Promtail DaemonSet):
   ```bash
   helm repo add grafana https://grafana.github.io/helm-charts
   helm repo update
   helm install loki grafana/loki-stack \
     -n futbot --create-namespace \
     -f k8s/observability/loki-stack-values.yaml
   ```

Order matters only loosely: kube-prometheus-stack must exist before its
CRDs (`ServiceMonitor`/`PrometheusRule`) can be applied. otel-collector/Jaeger
and loki-stack have no such dependency and can go in any order.

## What you get

| Signal | Where | How |
|---|---|---|
| Logs | Grafana → Explore → Loki datasource | `{compose_service="gateway"} \| json` or filter by `service`/`level` labels |
| Metrics | Grafana → dashboards, or Prometheus UI directly | Import `observability/grafana/dashboards/*.json` (same files used in docker-compose) or query `futbot_*` metrics directly |
| Traces | Jaeger UI | Search by service, or paste a `correlation_id` from a log line as the trace ID |
| Alerts | Alertmanager (`kubectl port-forward -n futbot svc/prometheus-kube-prometheus-alertmanager 9093:9093`) | Same 6 rules as local dev, defined in `prometheus-rules.yaml` |

Same correlation-ID bridge as local dev: the ID in every log line **is**
the Jaeger trace ID **is** the `correlation_id` column in
`GET :8090/traces/{run_id}` — see `futbot_common.middleware.CorrelationIdMiddleware`
and `services/observability/trace_store.py`.

## Not automated here

- Importing the two dashboard JSON files into the Helm-installed Grafana — do it
  once via the UI (`+ → Import → paste JSON`), or wire a
  `grafana.dashboardsConfigMaps` value pointing at a ConfigMap built from
  `observability/grafana/dashboards/*.json` if you want it fully declarative.
- Alertmanager receivers (Slack/email/PagerDuty) — the alert *rules* exist;
  routing them to a real notification channel needs cluster-specific
  Alertmanager config not included here.
- TLS/auth in front of Grafana/Jaeger/Prometheus UIs if exposed via Ingress —
  add basic auth or an OAuth proxy before doing that in anything but a
  local/dev cluster.

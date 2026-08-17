#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-futbot}"

echo "==> Creating kind cluster '${CLUSTER_NAME}' (if missing)..."
if ! kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
  kind create cluster --name "${CLUSTER_NAME}" --config "${ROOT}/k8s/kind-cluster.yaml"
else
  echo "    Cluster already exists, skipping create."
fi

if [[ "${SKIP_IMAGE_BUILD:-0}" != "1" ]]; then
  echo "==> Building and loading FutBot service images..."
  images=(
    "futbot-auth:local|services/auth/Dockerfile|."
    "futbot-chat:local|services/chat/Dockerfile|."
    "futbot-project:local|services/project/Dockerfile|."
    "futbot-llm-gateway:local|services/llm_gateway/Dockerfile|."
    "futbot-tools:local|services/tools/Dockerfile|."
    "futbot-retrieval:local|services/retrieval/Dockerfile|."
    "futbot-ingestion:local|services/ingestion/Dockerfile|."
    "futbot-rag-orchestrator:local|services/rag_orchestrator/Dockerfile|."
    "futbot-observability:local|services/observability/Dockerfile|."
    "futbot-gateway:local|services/gateway/Dockerfile|."
    "futbot-web:local|services/web/Dockerfile|services/web"
  )
  for entry in "${images[@]}"; do
    IFS='|' read -r image dockerfile context <<< "${entry}"
    docker build -t "${image}" -f "${ROOT}/${dockerfile}" "${ROOT}/${context}"
    kind load docker-image "${image}" --name "${CLUSTER_NAME}"
  done
else
  echo "==> SKIP_IMAGE_BUILD=1; using images already loaded into kind."
fi

echo "==> Installing ingress-nginx..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

echo "==> Applying FutBot infra (kustomize dev overlay)..."
kubectl apply -k "${ROOT}/k8s/overlays/dev"

echo "==> Waiting for infra pods..."
kubectl wait --namespace futbot --for=condition=ready pod --all --timeout=180s

echo "Done. Infra is running in namespace 'futbot'."
echo "  kubectl get pods -n futbot"
echo "  docker compose up -d --build   # optional local compose alternative"

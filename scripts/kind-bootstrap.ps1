$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ClusterName = if ($env:CLUSTER_NAME) { $env:CLUSTER_NAME } else { "futbot" }

Write-Host "==> Creating kind cluster '$ClusterName' (if missing)..."
$existing = kind get clusters 2>$null
if ($existing -notcontains $ClusterName) {
    kind create cluster --name $ClusterName --config "$Root\k8s\kind-cluster.yaml"
} else {
    Write-Host "    Cluster already exists, skipping create."
}

if ($env:SKIP_IMAGE_BUILD -ne "1") {
    Write-Host "==> Building and loading FutBot service images..."
    $images = @(
        @("futbot-auth:local", "services/auth/Dockerfile", "."),
        @("futbot-chat:local", "services/chat/Dockerfile", "."),
        @("futbot-project:local", "services/project/Dockerfile", "."),
        @("futbot-llm-gateway:local", "services/llm_gateway/Dockerfile", "."),
        @("futbot-tools:local", "services/tools/Dockerfile", "."),
        @("futbot-retrieval:local", "services/retrieval/Dockerfile", "."),
        @("futbot-ingestion:local", "services/ingestion/Dockerfile", "."),
        @("futbot-rag-orchestrator:local", "services/rag_orchestrator/Dockerfile", "."),
        @("futbot-observability:local", "services/observability/Dockerfile", "."),
        @("futbot-gateway:local", "services/gateway/Dockerfile", "."),
        @("futbot-web:local", "services/web/Dockerfile", "services/web")
    )
    foreach ($entry in $images) {
        $image, $dockerfile, $context = $entry
        docker build -t $image -f "$Root\$dockerfile" "$Root\$context"
        kind load docker-image $image --name $ClusterName
    }
} else {
    Write-Host "==> SKIP_IMAGE_BUILD=1; using images already loaded into kind."
}

Write-Host "==> Installing ingress-nginx..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx `
    --for=condition=ready pod `
    --selector=app.kubernetes.io/component=controller `
    --timeout=120s

Write-Host "==> Applying FutBot infra (kustomize dev overlay)..."
kubectl apply -k "$Root\k8s\overlays\dev"

Write-Host "==> Waiting for infra pods..."
kubectl wait --namespace futbot --for=condition=ready pod --all --timeout=180s

Write-Host "Done. Infra is running in namespace 'futbot'."
Write-Host "  kubectl get pods -n futbot"

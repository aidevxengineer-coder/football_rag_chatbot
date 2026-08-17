# Kubernetes manifests

## Prerequisites

- [kind](https://kind.sigs.k8s.io/)
- kubectl
- kustomize (built into kubectl 1.14+)

## Bootstrap local cluster

**Windows (PowerShell):**

```powershell
.\scripts\kind-bootstrap.ps1
```

**Linux / macOS:**

```bash
chmod +x scripts/kind-bootstrap.sh
./scripts/kind-bootstrap.sh
```

This creates a `futbot` kind cluster, builds and loads all local service images,
installs ingress-nginx, and applies the complete stack to namespace `futbot`.
Set `SKIP_IMAGE_BUILD=1` to reuse images already loaded into kind.

## Manual apply

```bash
kubectl apply -k k8s/overlays/dev
kubectl get pods -n futbot
```

The base manifests expose:

- Pitchside web: `http://app.futbot.local`
- Gateway API/docs: `http://api.futbot.local`
- Pipeline WebSocket traffic on `app.futbot.local/ws` routes to the gateway.

Map `app.futbot.local` and `api.futbot.local` to the kind ingress address in
your hosts file when local DNS does not resolve them.

## Docker Compose alternative

For the complete local stack without Kubernetes:

```bash
docker compose up --build
```

Connection defaults: [`.env.example`](../.env.example) (copy to `.env`)

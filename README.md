# Journey Browser Agent

## Local Docker run

From this directory:

```bash
docker compose up --build
```

Open http://localhost:5173. The frontend and backend run through the same `/api/v1` route; the backend is also available at http://localhost:8000 for diagnostics.

Create `backend/.env` from your existing local settings when integrations are needed. It is intentionally ignored by the container build.

## GKE deployment

The deployment targets the existing regional cluster shown in the supplied details:

- Google Cloud project: `esp-aep-migration`
- GKE cluster: `esp-aep-cluster`
- Region: `asia-south1`
- Artifact Registry repository: `journey-browser` (create once, or change `_REPOSITORY` in `cloudbuild.yaml`)

Enable required services and create the repository if needed:

```bash
gcloud config set project esp-aep-migration
gcloud services enable container.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
gcloud artifacts repositories create journey-browser --repository-format=docker --location=asia-south1
gcloud auth configure-docker asia-south1-docker.pkg.dev
```

For a first deployment without a DNS name, submit with `_FRONTEND_HOST=`. The frontend service remains internal to the cluster, so expose it with a domain and GKE Ingress before production use:

```bash
gcloud builds submit --config cloudbuild.yaml --substitutions=_REGION=asia-south1,_CLUSTER_NAME=esp-aep-cluster,_REPOSITORY=journey-browser,_FRONTEND_HOST=app.example.com .
```

When a domain is available, apply the managed certificate and Ingress after replacing the placeholder:

```bash
kubectl apply -f k8s/managed-certificate.yaml
```

The GKE Ingress uses the frontend as its only public entry point. Nginx routes `/api/*` to the private `backend` ClusterIP service, matching Docker Compose.

### Application secrets

Create the optional Kubernetes secret before or after deployment. The backend accepts the same environment variable names as the local `.env`:

```bash
kubectl -n journey-browser create secret generic journey-browser-secrets \
  --from-literal=JIRA_BASE_URL='...' \
  --from-literal=JIRA_PROJECT_KEY='...' \
  --from-literal=JIRA_USERNAME='...' \
  --from-literal=JIRA_API_TOKEN='...' \
  --from-literal=LLM_AUTH_TOKEN='...' \
  --dry-run=client -o yaml | kubectl apply -f -
```

For CI, prefer Google Secret Manager and generate this Kubernetes Secret in a secured Cloud Build step; do not commit real values to `k8s/secret.example.yaml`.

## Cluster prerequisites

The cluster needs Artifact Registry pull access for its node or workload identity, a default StorageClass for the 10Gi PVC, and a DNS A record pointing the chosen host to the GKE Ingress IP. The supplied screenshot confirms cluster credentials were fetched successfully; it does not include the VPC subnet, DNS name, or Artifact Registry repository, so those remain substitutions/configuration rather than hard-coded assumptions.
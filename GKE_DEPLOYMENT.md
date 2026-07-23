# Journey Browser Agent — GKE Deployment Guide

This document describes the complete deployment of the Journey Browser Agent on Google Kubernetes Engine (GKE), including Docker builds, Cloud Build, Artifact Registry, Kubernetes resources, Cloud DNS, a static public IP, GKE Ingress, and managed HTTPS.

## 1. Production architecture

```text
GitHub (prod branch)
        |
        v
Cloud Build
  |             |
  v             v
Backend image  Frontend image
  |             |
  +------ Artifact Registry ------+
                                  |
                                  v
                         GKE Autopilot cluster
                                  |
                         journey-browser namespace
                                  |
             +--------------------+--------------------+
             |                                         |
     Frontend Service                         Backend Service
       ClusterIP                                  ClusterIP
             |                                         |
        Nginx :8080                              FastAPI :8000
             |
       /api/* proxy

Internet
   |
DNS: browser-journey.ravinapps.com
   |
Static IP: 136.68.11.130
   |
GKE Ingress + ManagedCertificate
   |
Frontend Service
```

The backend is private. Only the frontend is exposed through the GKE Ingress. Nginx forwards `/api/*` requests to the internal backend Service.

## 2. Current Google Cloud configuration

| Setting | Value |
|---|---|
| Project ID | `esp-aep-migration` |
| GKE cluster | `esp-aep-cluster` |
| Cluster type | Autopilot |
| Cluster region | `asia-south1` |
| Kubernetes namespace | `journey-browser` |
| Artifact Registry repository | `journey-browser` |
| Artifact Registry location | `asia-south1` |
| Domain | `ravinapps.com` |
| Application hostname | `browser-journey.ravinapps.com` |
| Global static IP | `136.68.11.130` |
| Static IP resource | `journey-browser-ip` |
| Managed certificate | `journey-browser-cert` |
| GitHub deployment branch | `prod` |
| Cloud Build trigger | `esp-aep` |

The application currently uses GKE Ingress. Gateway API is not configured because using both Gateway and Ingress would create separate external load balancers and is unnecessary for this architecture.

## 3. Repository structure

The repository root must contain:

```text
cloudbuild.yaml
docker-compose.yml
backend/
  Dockerfile
  main.py
  requirements.txt
frontend/
  Dockerfile
  nginx.conf
  package.json
  package-lock.json
k8s/
  namespace.yaml
  backend.yaml
  frontend.yaml
  ingress.yaml
  managed-certificate.yaml
  secret.example.yaml
README.md
```

`cloudbuild.yaml` must be directly in the GitHub repository root. Do not place it below an additional `Journey-Browser-Agent/` directory.

## 4. Required Google Cloud APIs

Enable the APIs once:

```bash
gcloud config set project esp-aep-migration

gcloud services enable \
  cloudbuild.googleapis.com \
  container.googleapis.com \
  artifactregistry.googleapis.com \
  compute.googleapis.com \
  domains.googleapis.com \
  dns.googleapis.com
```

## 5. GKE cluster access

The cluster is Autopilot. Do not create or modify node pools manually.

```bash
gcloud container clusters get-credentials esp-aep-cluster \
  --region asia-south1 \
  --project esp-aep-migration
```

Verify access:

```bash
kubectl get namespaces
kubectl get nodes
```

Autopilot manages worker capacity automatically when workloads are scheduled.

## 6. Artifact Registry

Create the repository once if it does not already exist:

```bash
gcloud artifacts repositories create journey-browser \
  --repository-format=docker \
  --location=asia-south1 \
  --description="Journey Browser Agent container images"
```

Image names used by Cloud Build:

```text
asia-south1-docker.pkg.dev/esp-aep-migration/journey-browser/backend:BUILD_ID
asia-south1-docker.pkg.dev/esp-aep-migration/journey-browser/frontend:BUILD_ID
```

GKE must be able to pull private images. Grant Artifact Registry Reader to the node service account. For the default Compute Engine service account:

```bash
PROJECT_NUMBER=$(gcloud projects describe esp-aep-migration \
  --format="value(projectNumber)")

gcloud projects add-iam-policy-binding esp-aep-migration \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
```

If the cluster uses a custom node service account, grant the role to that service account instead.

## 7. Cloud Build IAM

Cloud Build needs permission to push images and deploy to GKE:

```bash
PROJECT_NUMBER=$(gcloud projects describe esp-aep-migration \
  --format="value(projectNumber)")

gcloud projects add-iam-policy-binding esp-aep-migration \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding esp-aep-migration \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/container.developer"
```

If an organization policy blocks Kubernetes deployment access, an administrator may need to grant a more permissive container role temporarily. Prefer least privilege and use `roles/container.developer` where possible.

## 8. Kubernetes resources

### Namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

The namespace is also created automatically by Cloud Build.

### Backend

`k8s/backend.yaml` creates:

- Backend ClusterIP Service on port `8000`.
- One backend replica.
- Readiness and liveness probes using `/health`.
- Non-root security context.
- A 10Gi persistent volume claim.
- Optional application secret loading.

The backend uses one replica because the PVC uses `ReadWriteOnce`. Multiple replicas would require shared read/write storage such as Filestore or a different storage architecture.

The PVC uses:

```yaml
storageClassName: standard-rwo
```

This avoids the regional SSD quota problem encountered with SSD-backed storage.

### Frontend

`k8s/frontend.yaml` creates:

- Frontend ClusterIP Service on port `80`.
- Two frontend replicas.
- Nginx health checks on `/health`.
- Non-root frontend container execution.

### Persistent storage

Check storage:

```bash
kubectl get pvc -n journey-browser
```

Expected:

```text
journey-backend-storage   Bound
```

If a PVC is still `Pending`, inspect it before deleting anything:

```bash
kubectl describe pvc journey-backend-storage -n journey-browser
```

A PVC that failed provisioning because of quota may be deleted and recreated after the manifest uses `standard-rwo`:

```bash
kubectl delete pvc journey-backend-storage -n journey-browser
kubectl apply -f k8s/backend.yaml
```

Only delete the PVC after confirming it is not `Bound` and does not contain required data.

## 9. Application secrets

Create the Kubernetes Secret in the application namespace:

```bash
kubectl -n journey-browser create secret generic journey-browser-secrets \
  --from-literal=JIRA_BASE_URL="https://your-company.atlassian.net" \
  --from-literal=JIRA_PROJECT_KEY="YOUR_PROJECT_KEY" \
  --from-literal=JIRA_USERNAME="your-email@example.com" \
  --from-literal=JIRA_API_TOKEN="YOUR_JIRA_TOKEN" \
  --from-literal=LLM_AUTH_TOKEN="YOUR_LLM_TOKEN" \
  --dry-run=client \
  -o yaml | kubectl apply -f -
```

Verify:

```bash
kubectl get secret journey-browser-secrets -n journey-browser
```

Never commit real credentials to GitHub. For a mature production setup, store values in Secret Manager and synchronize them into Kubernetes using an approved secret-management workflow.

## 10. Domain and Cloud DNS

The registered domain is:

```text
ravinapps.com
```

The active public Cloud DNS zone is:

```text
ravinapps-com
```

There was also a duplicate public zone named `ravinapps-zone`. Do not add records to both zones. Confirm which zone is delegated before removing an unused duplicate.

List zones:

```bash
gcloud dns managed-zones list --project=esp-aep-migration
```

The required record is:

```text
browser-journey.ravinapps.com.  A  136.68.11.130
```

Create it:

```bash
gcloud dns record-sets transaction start --zone=ravinapps-com

gcloud dns record-sets transaction add 136.68.11.130 \
  --name=browser-journey.ravinapps.com. \
  --ttl=300 \
  --type=A \
  --zone=ravinapps-com

gcloud dns record-sets transaction execute --zone=ravinapps-com
```

Verify public DNS:

```bash
dig +short browser-journey.ravinapps.com
dig @8.8.8.8 +short browser-journey.ravinapps.com
```

Both should return:

```text
136.68.11.130
```

Use hyphens in hostnames. Do not use `browser_journey.ravinapps.com` as the application hostname.

## 11. Static public IP

The reserved global address is:

```text
Name: journey-browser-ip
Address: 136.68.11.130
Type: External
Scope: Global
Status: RESERVED
```

Verify:

```bash
gcloud compute addresses describe journey-browser-ip \
  --global \
  --project=esp-aep-migration
```

The Ingress must include:

```yaml
kubernetes.io/ingress.global-static-ip-name: journey-browser-ip
```

If the Ingress already exists, attach the annotation:

```bash
kubectl annotate ingress journey-browser \
  -n journey-browser \
  kubernetes.io/ingress.global-static-ip-name=journey-browser-ip \
  --overwrite
```

## 12. Managed certificate and Ingress

The managed certificate manifest uses:

```text
Certificate: journey-browser-cert
Domain: browser-journey.ravinapps.com
```

Create the certificate:

```bash
sed 's|FRONTEND_HOST|browser-journey.ravinapps.com|g' \
  k8s/managed-certificate.yaml | kubectl apply -f -
```

Create the Ingress:

```bash
sed 's|FRONTEND_HOST|browser-journey.ravinapps.com|g' \
  k8s/ingress.yaml | kubectl apply -f -
```

Check the Ingress:

```bash
kubectl get ingress -n journey-browser -o wide
```

Check details and events:

```bash
kubectl describe ingress journey-browser -n journey-browser
```

Check certificate status:

```bash
kubectl get managedcertificate -n journey-browser
kubectl describe managedcertificate journey-browser-cert -n journey-browser
```

The certificate must reach:

```text
Certificate Status: Active
```

Certificate provisioning requires all of the following:

- The Ingress exists.
- The certificate is attached to the Ingress.
- DNS resolves the hostname to the Ingress IP.
- The domain registration and nameserver delegation are active.
- The load balancer has finished provisioning.

Provisioning can take time. Do not rebuild the application solely because the certificate is still `Provisioning`.

## 13. Cloud Build pipeline

The pipeline performs these steps:

1. Build the backend Docker image.
2. Build the frontend Docker image.
3. Push the backend image to Artifact Registry.
4. Push the frontend image to Artifact Registry.
5. Install `kubectl` and `gke-gcloud-auth-plugin` in the deploy step.
6. Fetch GKE credentials.
7. Apply the namespace.
8. Render image placeholders in the Kubernetes manifests.
9. Apply the backend and frontend resources.
10. Apply the ManagedCertificate and Ingress when `_FRONTEND_HOST` is non-empty.
11. Wait for backend and frontend rollouts.

The pipeline uses `$BUILD_ID`, not `$SHORT_SHA`, because manual `gcloud builds submit` commands may not provide `$SHORT_SHA`.

## 14. Manual deployment

From the repository root:

```bash
cd ~/Journey-Browser-Agent
git pull origin prod
```

Run:

```bash
gcloud builds submit \
  --config cloudbuild.yaml \
  --substitutions=_REGION=asia-south1,_CLUSTER_NAME=esp-aep-cluster,_REPOSITORY=journey-browser,_FRONTEND_HOST=browser-journey.ravinapps.com
```

A successful deployment ends with:

```text
SUCCESS
```

Do not directly apply `k8s/backend.yaml` or `k8s/frontend.yaml` when they contain `BACKEND_IMAGE` or `FRONTEND_IMAGE` placeholders. Those placeholders are replaced by Cloud Build.

## 15. GitHub-triggered deployment

Configure the Cloud Build trigger:

```text
Provider: GitHub
Trigger: esp-aep
Repository: RavinkishoreThirugnanam/Journey-Browser-Agent
Branch: prod
Config file: cloudbuild.yaml
```

Set the trigger substitution:

```text
_FRONTEND_HOST=browser-journey.ravinapps.com
```

Then deployment is triggered by:

```bash
git add .
git commit -m "Deploy application"
git push origin prod
```

If `_FRONTEND_HOST` is empty, Cloud Build will deploy the frontend and backend but skip the public Ingress and certificate.

## 16. Deployment verification

Check pods:

```bash
kubectl get pods -n journey-browser
```

Expected:

```text
journey-backend-...    1/1   Running
journey-frontend-...   1/1   Running
journey-frontend-...   1/1   Running
```

Check services:

```bash
kubectl get svc -n journey-browser
```

Check the backend health endpoint through port forwarding:

```bash
kubectl port-forward -n journey-browser svc/backend 8000:8000
```

In another terminal:

```bash
curl http://localhost:8000/health
```

Check the public Ingress:

```bash
kubectl get ingress -n journey-browser -o wide
```

Check DNS:

```bash
dig +short browser-journey.ravinapps.com
```

Check HTTPS:

```bash
curl -I https://browser-journey.ravinapps.com
```

Open the application in a browser:

```text
https://browser-journey.ravinapps.com
```

## 17. Troubleshooting

### Cloud Build says image name ends with `:`

This means the image tag is empty. Confirm that `cloudbuild.yaml` uses:

```text
$BUILD_ID
```

and not:

```text
$SHORT_SHA
```

### `kubectl: command not found`

The deploy image must install `kubectl` and `gke-gcloud-auth-plugin`. Confirm that the deploy step contains the Google apt repository setup and:

```bash
apt-get install -y kubectl google-cloud-cli-gke-gcloud-auth-plugin
```

### `gke-gcloud-auth-plugin was not found`

Confirm:

```bash
gke-gcloud-auth-plugin --version
```

The Cloud Build deploy step must install the package before running `gcloud container clusters get-credentials`.

### Backend pods are `Pending`

Run:

```bash
kubectl get events -n journey-browser --sort-by='.lastTimestamp'
kubectl describe pvc journey-backend-storage -n journey-browser
```

If the event says:

```text
SSD_TOTAL_GB quota exceeded
```

confirm the PVC uses:

```yaml
storageClassName: standard-rwo
```

### Pod is `InvalidImageName`

A Kubernetes template was applied directly and still contains `BACKEND_IMAGE` or `FRONTEND_IMAGE`. Use Cloud Build to render and apply the manifests, or set a valid image temporarily:

```bash
kubectl get pod POD_NAME -n journey-browser \
  -o jsonpath='{.spec.containers[0].image}'
```

### Ingress has no address

Check:

```bash
kubectl describe ingress journey-browser -n journey-browser
kubectl get events -n journey-browser --sort-by='.lastTimestamp'
```

Confirm the static IP annotation, DNS record, and that the GKE cluster is `RUNNING`.

### Certificate remains `Provisioning`

Check:

```bash
kubectl describe managedcertificate journey-browser-cert -n journey-browser
dig @8.8.8.8 +short browser-journey.ravinapps.com
kubectl describe ingress journey-browser -n journey-browser
```

The DNS answer must match the Ingress IP. Certificate provisioning may take time after the DNS record and Ingress are correct.

### Cloud Build history shows old failures

Old Build History entries do not indicate the current cluster state. Check the latest build and verify the live cluster directly:

```bash
kubectl get pods -n journey-browser
kubectl get ingress -n journey-browser
kubectl get managedcertificate -n journey-browser
```

## 18. Rollback

List deployment history:

```bash
kubectl rollout history deployment/journey-backend -n journey-browser
kubectl rollout history deployment/journey-frontend -n journey-browser
```

Roll back the backend:

```bash
kubectl rollout undo deployment/journey-backend -n journey-browser
```

Roll back the frontend:

```bash
kubectl rollout undo deployment/journey-frontend -n journey-browser
```

Confirm:

```bash
kubectl rollout status deployment/journey-backend -n journey-browser
kubectl rollout status deployment/journey-frontend -n journey-browser
```

## 19. Operational notes

- Keep the backend private as a ClusterIP Service.
- Do not expose port 8000 through a public LoadBalancer.
- Keep real secrets outside GitHub.
- Keep `_FRONTEND_HOST` configured in the Cloud Build trigger.
- Monitor PVC capacity because generated artifacts are stored in `/app/storage`.
- Keep only one authoritative public DNS zone for `ravinapps.com`.
- Do not manually create Autopilot node pools.
- Do not apply image-placeholder manifests directly.
- GKE Ingress and Gateway API are alternatives; only the GKE Ingress configuration is currently used.

## 20. Useful official documentation

- [GKE cluster access and authentication](https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl)
- [Artifact Registry with GKE](https://cloud.google.com/artifact-registry/docs/integrate-gke)
- [GKE secure Ingress and managed certificates](https://cloud.google.com/kubernetes-engine/docs/how-to/secure-ingress)
- [Cloud DNS setup](https://cloud.google.com/dns/docs/set-up-dns-records-domain-name)
- [Cloud Build build results](https://cloud.google.com/build/docs/view-build-results)
# Deploying RouteBridge

Three paths, from simplest to most complete. All of them run the same container images
(`backend/apps/api/Dockerfile`, `frontend/routebridge/apps/web/Dockerfile`).

## 1. Single host (docker compose)
`docker-compose.production.yml` runs PostGIS, Redis, the API (migrations first), the outbox, notification and
maintenance workers, and a 6-hourly `pg_dump`. Create `.env.production` from `apps/api/.env.example` and generate
secrets with `python -m routebridge.tools.gen_secrets`. The API refuses to start with unsafe settings, and tells you
every problem at once. Put a TLS-terminating reverse proxy in front.

## 2. Kubernetes on AWS (af-south-1) — staging and production
```
terraform/                 VPC, EKS, RDS PostgreSQL 16, ElastiCache Redis, S3 media bucket (+CORS), ECR, IAM
k8s/base/                  api (+HPA, PDB, init-container migrations), web, outbox/notification workers,
                           maintenance CronJob, ingress, default-deny NetworkPolicies
k8s/overlays/staging       smaller, own hosts/bucket/Clerk instance
k8s/overlays/production    3+ API replicas
k8s/overlays/production-canary   one extra API pod on the new image, 10% of API traffic
```

First-time setup:
1. `terraform init -backend-config=...` then `terraform apply -var environment=staging -var 'app_origins=["https://app.staging.…"]'`.
   Outputs give the database URL, Redis URL, S3 key pair and cluster command.
2. Create the Secret `routebridge-secrets` in the namespace (see `k8s/secret.example.yaml`; use External Secrets or
   Sealed Secrets). `python -m routebridge.tools.gen_secrets` makes the signing/driver/API keys.
3. Edit hosts, Clerk URLs and the registry owner in `k8s/base` and the overlays (they use `*.routebridge.example` and
   `ghcr.io/OWNER` placeholders), install ingress-nginx and cert-manager, then `kubectl apply -k k8s/overlays/staging`.
4. Use `.github/workflows/deploy.yml`: pushes to `main` build images and deploy to staging; the production actions
   (`canary`, `promote`, `rollback`) are manual and gated by the `production` GitHub Environment.

Release flow: staging (automatic) -> production **canary** (watch 5xx rate/latency for the canary pod) -> **promote**.
Rollback deletes the canary resources and undoes the stable rollout. Migrations run as an init container on every API
pod under a Postgres advisory lock, so they MUST be backward compatible with the previous release (add columns/tables
first, remove them a release later).

Config changes: the ConfigMap has a stable name, so the deploy workflow restarts the deployments after applying.

## What is validated, and what is not
Validated in CI and locally: the Kubernetes manifests (rendered with kustomize and checked against the 1.30 schemas),
Terraform `fmt`/`validate`, the workflows (`actionlint`), migrations on PostgreSQL and PostGIS, the container images.
**Not validated until you run it:** `terraform apply` (needs your AWS account), a real cluster, ingress/TLS,
secrets wiring, and the SMS/WhatsApp/telephony vendors. Review IAM, sizing and costs before applying.

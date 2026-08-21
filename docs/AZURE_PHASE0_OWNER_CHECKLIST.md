# Azure Phase 0 — owner checklist (run in parallel with code PRs)

Complete these steps before provisioning any Azure resources.

## 1. Install tooling

```bash
brew install azure-cli hashicorp/tap/terraform
az login
terraform -version
az account show
```

## 2. Confirm free meters in your subscription

1. Open Azure Portal → **Cost Management + Billing** → **Benefits** / **Free Services**.
2. Screenshot the blade showing eligibility for:
   - `Standard_B2ats_v2` (750 hours/month)
   - PostgreSQL Flexible Server `Standard_B1ms` (750 hours/month)
3. Confirm your subscription free-tier expiry (target: 18 June 2027).

## 3. Confirm SKU availability in your chosen region

```bash
az vm list-skus --location centralindia --size Standard_B2ats_v2 -o table
az postgres flexible-server list-skus --location centralindia -o table
```

Replace `centralindia` if you choose another approved region.

## 4. Create a cost budget (before any resource)

1. Azure Portal → **Subscriptions** → your subscription → **Budgets**.
2. Add budget: **$1/month** (or equivalent INR).
3. Enable alerts at **25%, 50%, 75%, 90%, and 100%** (actual and forecast).

## 5. Record completion

When all four sections above are done, you are ready for Phase 3 (`terraform apply`).

See [AZURE_DEPLOYMENT_STATUS.md](./AZURE_DEPLOYMENT_STATUS.md) for the full sequence after Phase 0.

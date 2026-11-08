# Cloudflare Workers setup for the docs site

## Status

The site is served at https://zudo-stl-fix.zudolab.dev by an assets-only Cloudflare Worker named `zudo-stl-fix-doc` (`doc/wrangler.toml`, custom domain route, `workers_dev = false`). It is deployed only by the `deploy` job in `.github/workflows/docs.yml` on pushes to `main` that touch `doc/**` or `.github/workflows/docs.yml` (or Run workflow on `main`). Do not deploy from a local machine.

The repository secrets below are not set yet, so the deploy job currently logs a warning and skips. A one-off local deploy made on 2026-11-08 (`zudo-stl-fix-doc.takazudo.workers.dev`, the owner's personal account) predates this decision and is not the published site; it stays online with stale content until it is removed (dashboard: Workers & Pages > `zudo-stl-fix-doc` > Settings > Delete, in that account).

## One-time steps

1. Create an API token in the Cloudflare dashboard (My Profile > API Tokens > Create Token > Custom token) from the **Edit Cloudflare Workers** template, scoped to the account that holds the `zudolab.dev` zone and to that zone. It includes Workers Scripts Edit, Workers Routes Edit and Zone Read, which the custom-domain route needs.
2. Copy the Account ID from the dashboard (Workers & Pages overview, right sidebar).
3. In the GitHub repository, add two Actions secrets (Settings > Secrets and variables > Actions):
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`
4. Run the first deploy: Actions > Docs > Run workflow (`workflow_dispatch`) on `main`. Later pushes to `main` that touch `doc/**` or the workflow deploy automatically.
5. The site is at https://zudo-stl-fix.zudolab.dev. Wrangler creates the custom domain record on the first deploy, which needs the `zudolab.dev` zone in the same account.

If only one secret is set, the deploy is skipped as unconfigured. If both are set but invalid, the deploy job fails visibly.

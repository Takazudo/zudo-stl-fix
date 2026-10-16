# Cloudflare Workers setup for the docs site

## Status

Deployment is configured; the live deployment is pending credentials. Until the repository secrets below exist, the `deploy` job in `.github/workflows/docs.yml` logs a notice and skips. The `build` job (including `wrangler deploy --dry-run`) runs without credentials.

The site is an assets-only Cloudflare Worker named `zudo-stl-fix-doc` (`doc/wrangler.toml`), serving `doc/dist` on the free `workers.dev` subdomain.

## One-time steps

1. Create an API token in the Cloudflare dashboard (My Profile > API Tokens > Create Token > Custom token) with the permission **Account · Workers Scripts · Edit**, scoped to the target account.
2. Copy the Account ID from the dashboard (Workers & Pages overview, right sidebar).
3. In the GitHub repository, add two Actions secrets (Settings > Secrets and variables > Actions):
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`
4. Run the first deploy: Actions > Docs > Run workflow (`workflow_dispatch`) on `main`. Later pushes to `main` that touch `doc/**` deploy automatically.
5. Find the URL: it is printed by `wrangler deploy` in the deploy job log, in the form `https://zudo-stl-fix-doc.<account-subdomain>.workers.dev`, and shown under Workers & Pages > `zudo-stl-fix-doc`.

If only one secret is set, the deploy is skipped as unconfigured. If both are set but invalid, the deploy job fails visibly.

## Optional: custom domain

Not configured. To add one later, extend the API token with **Zone · Workers Routes · Edit** for the zone, then add a `routes` entry (or a custom domain) to `doc/wrangler.toml` and redeploy.

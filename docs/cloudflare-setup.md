# Cloudflare Workers setup for the docs site

## Status

Live at https://zudo-stl-fix-doc.takazudo.workers.dev since 2026-11-08. That first deployment was made from a local Mac (`wrangler deploy` in `doc/` with the owner's personal account, from `main` @ `6fffdbf`), because the repository secrets below do not exist yet. Until they exist, the `deploy` job in `.github/workflows/docs.yml` logs a notice and skips, so later `doc/**` changes on `main` need either the secrets or another local `wrangler deploy` from a clean `main` build.

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

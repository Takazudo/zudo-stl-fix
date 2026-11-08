# Cloudflare Workers setup for the docs site

## Status

The site is served at https://zudo-stl-fix.zudolab.dev by an assets-only Cloudflare Worker named `zudo-stl-fix-doc` (`doc/wrangler.toml`, custom domain route, `workers_dev = false`). It is deployed only by the `deploy` job in `.github/workflows/docs.yml` on pushes to `main` that touch `doc/**` or `.github/workflows/docs.yml` (or Run workflow on `main`). Do not deploy from a local machine.

The repository secrets were added on 2026-11-08, and the first CI deploy (Run workflow on `main` @ `9888e03`, run 42480260724, version `77584c26-8ea3-4263-8162-3f1aa9d49f15`) published the custom domain. The same deploy turned off the old `zudo-stl-fix-doc.takazudo.workers.dev` URL from the earlier one-off local deploy (`workers_dev = false`, same account), which now returns 404.

## One-time steps

1. Create a custom API token in the Cloudflare dashboard (My Profile > API Tokens > Create Token > Custom token) with: Account · Workers Scripts · Edit; Account · Account Settings · Read; Zone · Workers Routes · Edit; Zone · Zone · Read; Zone · DNS · Edit. Account resources: the account that holds `zudolab.dev`; zone resources: the `zudolab.dev` zone.
2. Copy the Account ID from the dashboard (Workers & Pages overview, right sidebar).
3. In the GitHub repository, add two Actions secrets (Settings > Secrets and variables > Actions):
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`
4. Run the first deploy: Actions > Docs > Run workflow (`workflow_dispatch`) on `main`. Later pushes to `main` that touch `doc/**` or the workflow deploy automatically.
5. The site is at https://zudo-stl-fix.zudolab.dev. Wrangler creates the custom domain record on the first deploy, which needs the `zudolab.dev` zone in the same account.

If only one secret is set, the deploy is skipped as unconfigured. If both are set but invalid, the deploy job fails visibly.

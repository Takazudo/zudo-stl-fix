# zudo-stl-fix: A “Fitted facet”

The approved revised A is a completed monochrome cube with four filled shapes,
including two filled right-face triangles separated by a diagonal fitted joint.
Softened corners and transparent seams are part of the canonical geometry.
The initial open-hole sketch and comparison-board candidates B/C are superseded.

## Assets and use

| Role | Location relative to `doc/` |
| --- | --- |
| Standard currentColor symbol | `public/img/brand/zudo-stl-fix-symbol.svg` |
| Byte-identical home hero alias | `public/img/logo.svg` |
| Compact currentColor header symbol | `public/img/brand/zudo-stl-fix-symbol-small.svg` |
| Fixed black/white standard and compact symbols | `public/img/brand/zudo-stl-fix-symbol*-black.svg`, `*-white.svg` |
| Portable outlined Jost lockups | `public/img/brand/zudo-stl-fix-lockup.svg`, `zudo-stl-fix-lockup-white.svg` |
| Adaptive compact SVG favicon | `public/favicon.svg` |
| Compact raster/ICO fallbacks | `public/favicon-16x16.png`, `favicon-32x32.png`, `favicon.ico` |
| Supplied 1200×630 social card | `public/img/ogp.png` |
| Self-hosted font and original license | `public/fonts/jost-600.woff2`, `public/fonts/OFL.txt` |

The standard 512-unit master uses 18-unit primary and 12-unit diagonal seams;
the compact optical variant uses 32/28-unit seams for 16–32px/header contexts.
Both right-face triangles stay filled. Do not replace either asset with a generic
cube, erase the diagonal joint, add a hole/checkmark, or introduce colors,
gradients or outline-only geometry.

Symbol/lockup SVGs have transparent seams. The adaptive SVG favicon uses dark
ink on light backgrounds and white ink in dark color schemes. The PNG/ICO
favicon fallbacks intentionally have opaque white backing, including their
seams, following ZFB policy. The ICO contains 16, 32 and 48px compact frames.

The product name is always live/selectable lowercase `zudo-stl-fix` in the
website header and home hero. Use upright Jost SemiBold 600 with normal letter
spacing, matching ZFB's exact font bytes. Outlined lockups are for portable
graphics only. Article, sidebar, navigation and control fonts remain governed by
the existing theme; do not globally replace `--font-sans`.

## Supported integration

`zfb.config.ts` uses the package's `logo`, `headerBrand`, explicit `favicon` and
complete `metaTags` options. Package-owned chrome paints the header and hero
symbols as currentColor masks. The header icon stays decorative and the brand
link's accessible name stays `zudo-stl-fix`.

`src/styles/global.css` scopes Jost to those two live names. ZFB 5.2.2 leaves
project-authored CSS URLs unchanged and emits the stylesheet under `assets/`:
`../fonts/jost-600.woff2` therefore resolves relative to the emitted stylesheet,
not this source file. It works on root, nested and locale routes and applies a
configured base once. The font uses `font-display: swap` and ordinary fallback.
No generator or external font service is required by website builds.

## Provenance and source

Copied unchanged from the owner-supplied `zudo-stl-fix-A-brand-kit.zip`, prepared
2026-11-09 (Asia/Tokyo). Every entry of its `MANIFEST.sha256` was verified before
integration. Production artwork, font and OFL bytes are unchanged.

Canonical input SHA-256:

| Input | SHA-256 |
| --- | --- |
| `assets/zudo-stl-fix-symbol.svg` | `570d8ceaa93d136e006dbc93fb49fbc3015ef280012af7f9cddcafacc43c9cd2` |
| `assets/zudo-stl-fix-symbol-small.svg` | `230cf917b356cfa212539b096a93e4a8f89dd2dc5f5ec427d24afdccb70c53e9` |
| `fonts/jost-600.woff2` | `fa418d4c46615b4e07e2011eed91a3e399f88bf67bd8bc39e3fee14a04e442b5` |
| `fonts/OFL.txt` | `b9c2ddb5e698b4287241ab26190c8e4c5e3a395d486ac80e96e8f979b44ed625` |

- `source/fitted-facet.json`: unchanged canonical standard/compact geometry.
- `source/brand-layout.json`: supplied lockup measurements and font identity;
  only its font path is rebased to the production font location.
- `source/ogp.svg`: unchanged outlined source composition for the supplied PNG.
- Jost/OFL and typography pattern originate in [ZFB's brand assets at
  2f5c865](https://github.com/Takazudo/zudo-front-builder/tree/2f5c8658360941f1d4be135d2f8508ae464d3542/docs/brand).
  Keep the unmodified OFL beside the WOFF2. This font license does not change
  the repository-wide license.

The ZIP, comparison board, proof sheets and temporary generators are not website
assets. Native app icons, Finder/Dock resources, packaging/signing/notarization
and macOS release verification are outside this docs-only integration.

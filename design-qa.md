# Public Commerce Design QA

final result: passed

## Scope and state

- Date: 2026-10-13 (Asia/Shanghai).
- Build mode: functional-first Product Design pass using browser-captured real product screenshots; no generated marketing imagery.
- Desktop state: public homepage, public pricing, authenticated purchase confirmation, authenticated admin product management.
- Browser viewport capture: 1862 × 912 CSS pixels at browser density 1 for focused screens; full homepage capture 1862 × 5716 pixels.
- Mobile visual optimization was intentionally not accepted in this pass because the repository sequence requires PC completion first.

## Source visual truth

The user explicitly chose real browser screenshots instead of an Image Gen mock for this pass. Visual truth is therefore the existing product UI and the confirmed brief: restrained Apple-style hierarchy, generous whitespace, real product imagery, clear pain-led copy, and subtle motion.

- Reader product image: `.local/debug/product-design-reader-commercial-audit-20261012/04-improved-reader.jpg` — 1753 × 833.
- Workspace product image: `.local/debug/modern-walkthrough/20261011T135345Z/desktop-workspace.png` — 1440 × 1000.
- Learning insight product image: `.local/debug/modern-walkthrough/20261011T135345Z/desktop-stats.png` — 1440 × 1000.

This is not a pixel-clone comparison against an external mock. It is a product-system and asset-fidelity comparison against the real application screens selected by the user as the temporary visual source.

## Implementation evidence

- Above-the-fold homepage: `.local/debug/product-design/public-commerce-20261013/06-home-final.png` — 1862 × 912.
- Full homepage: `.local/debug/product-design/public-commerce-20261013/08-home-full-final.png` — 1862 × 5716.
- Pricing: `.local/debug/product-design/public-commerce-20261013/02-pricing-final.png` — 1862 × 912.
- Authenticated purchase confirmation: `.local/debug/product-design/public-commerce-20261013/04-purchase-authenticated.png` — 1862 × 912.
- Product/version administration: `.local/debug/product-design/public-commerce-20261013/05-admin-products.png` — 1862 × 912.

## Required fidelity surfaces

### Fonts and typography

- Display copy uses the existing system/Inter stack with heavy optical weight, tight tracking, and short line lengths.
- The hero, problem statement, product stories, pricing, and final CTA have distinct hierarchy without introducing a separate decorative font dependency.
- The pricing headline originally wrapped its final character onto a separate line; the content width was increased from 760px to 900px and the final capture shows a stable single-line desktop heading.

### Spacing and layout rhythm

- The homepage uses large section spacing, alternating product-copy/image layouts, a restrained two-column hero, and a dark interruption section for pacing.
- Pricing and purchase screens align to a consistent 1320px/1120px content system.
- Cards use restrained 18–28px radii and soft elevation. No persistent controls are clipped in the captured desktop states.

### Colors and visual tokens

- The public experience reuses the product's deep green, warm off-white, pale green, and coral-adjacent semantic warning colors.
- Contrast is strong in the hero, problem section, CTAs, and order status. Disabled payment state remains visibly disabled while retaining readable context.

### Image quality and asset fidelity

- All major visuals are real browser captures from the product, not placeholders, CSS illustrations, fake dashboards, or generated approximations.
- The first full-page pass showed two off-screen screenshots as blank because of native lazy loading. Lazy loading was removed from the three critical product images; the final full-page capture visibly contains the reader, workspace, and learning-record screens.
- Product screenshots retain their original aspect ratio and are not stretched.

### Copy and product content

- The hero directly states the user's pain: collecting material without understanding, hearing, or retaining it.
- The page explains the product in three outcomes: read deeply, continue from context, and see progress.
- All commercial copy says fixed term and no automatic renewal.
- Purchase confirmation shows exact version, duration, amount, benefits, customer support, agreement links, and a truthful disabled state until the payment channel is configured.
- Contact QQ `289614546` appears on support, purchase, policy, and footer surfaces.

## Primary interactions tested

- Public homepage is available without authentication.
- Public pricing loads four published database-backed product versions.
- Purchase route loads the latest published immutable version.
- Unauthenticated purchase redirects to login and returns to the original purchase route after successful login.
- Payment remains disabled when credentials are absent; no demonstration payment or fake success is exposed.
- Legacy `/?screen=membership` links still open the authenticated learning console.
- Admin product cards show current version and version history; annual products visibly retain retired V1 and published V2.
- Create-version modal pre-fills the current version and requires explicit benefits, price, duration, and entitlement version.
- Fresh public homepage browser console contained no errors or warnings.

## Comparison history

### Iteration 1

- P2: Pricing title wrapped the last character onto a separate line.
  - Fix: increased public section heading width to 900px.
  - Evidence: `02-pricing-final.png`.
- P1: Lower product screenshots appeared blank in the full-page capture because they had not entered the viewport.
  - Fix: removed lazy loading from the three critical product screenshots.
  - Post-fix evidence: `08-home-full-final.png`.
- P1: Annual product copy implied an unclear single quota period while the old membership engine used the full subscription as one usage period.
  - Fix: subscription usage now creates a new immutable usage period every plan period; annual product V2 states that allowances reset every 30 days, while V1 remains retired and queryable.
  - Evidence: `04-purchase-authenticated.png`, `05-admin-products.png`, and PostgreSQL integration tests.

## Residual P3 polish

- Replace or supplement the current browser screenshots with purpose-composed product imagery after Image Gen becomes available.
- Consider a dedicated Chinese display font only after measuring load cost and visual benefit.
- Add motion choreography tied to scroll position after functional analytics establish which product sections users reach.
- Perform the separate mobile optimization task after PC acceptance, per repository sequencing.

## Final assessment

There are no remaining actionable P0, P1, or P2 findings in the verified PC public-commerce flow. The remaining items are intentionally deferred P3 visual refinement or the separate mobile phase.

## Operations package-management iteration

### Source and implementation evidence

- Earlier card-heavy administration source: `.local/debug/product-design/public-commerce-20261013/05-admin-products.png` — 1862 × 912.
- Final package list: `.local/debug/product-design/admin-commerce-20261013/01-plan-list.png` — 1862 × 968.
- Final version drawer: `.local/debug/product-design/admin-commerce-20261013/02-version-drawer.png` — 1862 × 968.
- Final entitlement catalog: `.local/debug/product-design/admin-commerce-20261013/03-entitlements.png` — 1862 × 968.

### Findings and fixes

- P1: Package cards expanded every version and pushed users, invitations, and audits far below the fold.
  - Fix: operations is split into six tabs; package management uses a compact searchable table.
- P1: Package actions were exposed as several competing inline buttons.
  - Fix: each row has one action menu containing current version, new version, historical packages, and stop/resume sales.
- P0: Free-text benefit entry could promise features that the product did not enforce.
  - Fix: built-in entitlements are sourced from the nine server-enforced feature keys only. New versions use checkboxes plus validated numeric limits, and publishing activates a dedicated immutable `plan_version` whose `quotas_json` is used by runtime reservations, storage checks, login-device checks, imports, and catalog limits.
- P1: Operational service promises and enforced quotas were mixed together.
  - Fix: a dedicated Package Content tab separates built-in system-controlled items from configurable display-only items. Configured items are snapshotted into product versions but never written into quota ledgers.
- P2: Creating or editing a version in a modal was too dense for nine feature controls.
  - Fix: version creation uses a wide drawer with grouped basic information, built-in feature controls, and configurable benefits.

### Interaction and console verification

- Tab switching, package filters, row action menu, new-version drawer, entitlement selection, history entry points, and configured-benefit management were visually inspected.
- Fresh final operations-browser console had no errors or warnings.
- Final result for this iteration: passed.


# Check92 — Black Signal isolated implementation

Actual standalone implementation under `cinematic-preview/black-signal/`. The incumbent site, bot and production configuration are unchanged. This is not a deployment.

## Run the built artifact

From the extracted artifact's root (the directory containing `cinematic-preview`):

```sh
python -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/cinematic-preview/black-signal/`.
Do not open index.html directly with file://: models need HTTP.

## Build from source

From `cinematic-preview/black-signal`:

```sh
npm install --ignore-scripts --no-audit --no-fund
python -m pip install Pillow==11.3.0
python fetch_assets.py
python optimize_assets.py
npm run build
```

The download script is only necessary when built assets are absent or intentionally refreshing them. It downloads exactly three models from an immutable curator commit, verifies original SHA-256 values and requires expected attribution licenses. The optimizer prepares desktop and mobile textures without replacing geometry. Artist credits remain in credits.html and assets/model-review.json.

The page uses `../assets/engine.glb`, `../assets/studio.hdr` and license records from the incumbent project. Preserve those paths.

## Browser checks

Start the HTTP server from the repository root, install the matching Playwright Chromium (`npx playwright install chromium`), then run `npm test` from this directory. CHECK92_BASE_URL may override the local URL.

The test generates static car posters, screenshots, desktop/mobile viewport recordings and `review/qa-report.json`. Software WebGL testing does not establish hardware frame rate or physical iPhone Safari behavior. Synthetic Telegram test traffic is intercepted; no messages are sent.

## Scope

Three distinct real vehicle meshes; spatial selection with state continuity; studio materials and light; reversible ECU opening; PCB close view; existing 18-part illustrative V8 separation/reassembly; selected car return; responsive editorial services; preliminary vehicle selection; honest Telegram share and clipboard; reduced motion and no-WebGL content paths.

ECU is a new generic procedural engineering illustration. V8 is the existing unbranded model, not the exact engine of each selected vehicle and not a complete internal-engine CAD. No fabricated power gains, dyno measurements, case studies or server-submission confirmations. Model list is the existing preliminary catalogue, not a verified compatibility dataset.

No genuine approved logo-vector or real case-study photographs were present in the inspected site; the incumbent CHECK92 wordmark is retained and portfolio cases are not invented. Physical-device QA, a production backend, exact manufacturer ECU/engine pairings and a full case gallery are not claimed completed.

The isolated CI workflow produces downloadable source/build/review artifacts. Its optional generated-file commit is limited to this preview branch and two generated output paths, without force push. It never deploys or changes production.

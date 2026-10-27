# CHECK92 — build the actual cinematic experience
User goal: replace the current generic landing-page feel with an uninterrupted, scroll-driven luxury automotive CGI site. Work on this branch, preserving the existing ECU viewer, V8 asset, functioning catalog and contact logic. Never modify production before approval.

## Exact reference videos (provided in ChatGPT conversation; attach them in Work)
- ScreenRecording_10-27-2026 13-03-57_1(1).mp4, ~6.2s: energy-drink rotating product carousel. Replace cans with distinct high-quality, REAL 3D cars in a curved depth-based selector. Center car dominant, neighbors flank; selecting a car recenters and relights it; clicking car/CTA transitions directly into scroll experience.
- ScreenRecording_10-27-2026 14-43-43_1(1).mp4, 32–50s: full-bleed high-end compositional transitions, camera pushes, depth, color edits, type in motion; not page sections separated by blank scroll.
- b17aa571f5c348aa848d4075bc39eab1(2).mp4: design rigor via Impeccable/Taste Skill/Animate. No AI slop.

## Concrete sequence
1. **3D model selector (signature first screen).** Distinct optimized actual car GLBs (Porsche / Audi / BMW or other licensed vehicles), lit by animated softboxes in a dark CHECK92 studio. Drag, swipe, arrows and tap work; elegant nameplate and car index. Selection locks car identity in app state, animates camera push-in, and AUTO-SCROLLS to story.
2. **ECU teardown.** Selected-car continuity. Lid, PCB, controller and connectors separate as scroll progresses; genuine model where possible, otherwise clearly called a generic engineering visualization. Macro camera follows light down traces to processor. Reverse scroll reassembles.
3. **Electronics motion.** Camera flies along PCB, controlled light pulses and data patterns; technically evocative and cinematic, not particles everywhere.
4. **Engine teardown.** Use real named submeshes in existing V8.glb or higher-quality licensed model. Full reveal -> layer-by-layer physically coherent separation -> camera inside -> reassembly; labels and concise real service facts synchronized to scroll.
5. **Performance and finale.** Car emerges from engineered light tunnel, studio-to-motion transition, clean kinetic type and selected-car booking CTA; no invented power/torque gains. Booking retains functioning contact path.

## Visual direction
Black / graphite, bone white, exact CHECK92 orange accent #FF5A21. Art-directed typography, asymmetrical framing, 3D reflections, film-like lighting, elegant negative space. Replace static sections with pinned animated passages but keep content readable. Avoid generic cards, CSS fake cars, bloated copy, repeated generic spin/fade animations, and decorative overlays without purpose.

## Technical and legal
- Reuse current Three.js architecture; GSAP/ScrollTrigger only if it helps. Avoid resetting stable work.
- Source freely downloadable commercially licensable GLB/FBX car assets; verify author's license, actual download and provenance. Retain local credits and attribution. Brand/model appearance is illustrative; CC BY on a mesh isn't automatic manufacturer endorsement.
- Self-host optimized GLBs, KTX2/WebP textures, sensible LOD, deferred heavy scenes, loading posters, adaptive DPR, scroll timeline driven by progress rather than setTimeout. Test and optimize for real iPhone Safari if accessible.
- Preserve reduced motion, touch gestures, reverse scroll, WebGL context loss fallback, catalog and real contact actions.
- No paid APIs or server purchases; don't change live Check92, RemapLab, or other services.

## Accept / reject
- Not accepted if only text or the old ECU is polished.
- At least THREE genuinely distinct 3D cars visibly animate in selector; choosing one visibly recenters and sends user into 3D teardown.
- ECU and engine dissections are obvious and reversible, animation distributed across the ENTIRE scroll experience.
- Demo must show a full continuous desktop AND mobile scroll captured from browser (not screenshots), assets loading without console errors, working selector/forms and a reachable HTTPS preview.
- If render/record tools are unavailable, finish actual code first and report specific blocker rather than a planning-only reply.

Work order: secure and optimize 3D car assets, BUILD AND VALIDATE FIRST SCREEN, then implement the remaining linked scroll story and QA. Each step is actual production-quality UI work, not merely another brief.

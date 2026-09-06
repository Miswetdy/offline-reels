# Status

## TASK-018 Web API full-tree canonical-alias diagnostic — 2026-09-06

The next Stage-10 no-download run examined the strict canonical alias allowlist
through the entire tree of exactly two authenticated Web API JSON responses,
not only their media-shaped nodes. The count was still zero. The run retained
and emitted only aggregate counts; no field names, values, bodies, URLs,
cookies or candidates were retained.

This rules out those two Web API responses as a direct reproduction of the
local spike's generic JSON catalog. It does not rule out another authenticated
JSON response class. Web API remains diagnostic-only and no persistence or
download adapter was constructed. Next: locate the response class supplying
the spike-compatible valid aliases using the same bounded aggregate-only
method before designing a queue provider.

## TASK-018 Web API canonical-alias acceptance diagnostic — 2026-09-06

The follow-up isolated Stage-10 run inspected exactly two authenticated Web API
JSON responses. It found 85 media-shaped structures and 340 canonical-shaped
strings, but zero valid values under the strict existing canonical alias
allowlist.  The output contained counts only: no key names, values, response
bodies, URLs, cookies or candidates were retained.

The active media nevertheless changed stably and post-input JSON was observed.
Because the allowlist count was zero, Web API cannot safely become an
`AuthenticatedFeedSource` with the present canonical-ID contract. It remains
diagnostic-only; no downloader, database, Redis, MinIO or persistence adapter
was constructed. The next investigation must establish a separately validated
canonical-ID contract for a confirmed feed source, rather than widening the
existing alias allowlist based on string shape alone.

## TASK-018 authenticated Web API schema discovery — 2026-09-06

The isolated Stage-10 `identity-diagnostic --transition` inspected exactly two
JSON Web API responses from the existing authenticated browser context.  It
retained no response body, URL, field name, field value, cookie or candidate;
it emitted only aggregate counts.  Both responses contained media-shaped
structures: 83 such nodes and 332 canonical-shaped string values in total.

The same bounded input again produced a stable different central-media identity
and post-input JSON, but no admitted DOM, GraphQL or queue candidate.  No
downloader, database, Redis, MinIO or persistence adapter was constructed.
This is evidence that the authenticated Web API has feed-like media structure,
but not proof that any particular field is a validated canonical Reel ID. The
subsequent strict-alias check found no admissible value. The Web API remains
diagnostic-only and cannot supply Collector candidates.

## TASK-018 authenticated GraphQL feed source — 2026-09-06

`AuthenticatedFeedSource` is now an isolated, bounded in-memory provider. It
subscribes only to JSON GraphQL responses of the current authenticated browser
context for candidates. The first two Web API responses may be inspected only
for aggregate schema evidence and are then discarded; they cannot enter the
queue. It admits only validated canonical aliases and consumes each candidate
once. Swipe remains a media-transition signal and is not an ID source. Focused
source and Chromium transition tests pass; a live no-download source
acceptance remains required before it can enable collection.

## TASK-018 no-download transition identity diagnostic — 2026-09-06

The explicit no-download diagnostic performed one bounded transition with no
downloader or persistence adapters. Before and after the transition the page
had a specific Reel path and a central visible video, but zero page/nearby Reel
anchors; the rendered video pool grew from two to seven while only two remained
visible. One shallow ancestor data attribute remained, but no value or name was
retained. The active media changed stably and post-action JSON arrived, yet no
different safe-DOM candidate or canonical JSON candidate was confirmed.

This proves that virtualization changes the rendered media without exposing a
currently admissible canonical binding through the present URL, anchor, or JSON
candidate sources. The next diagnostic must remain aggregate-only and establish
whether a structurally bound, validated attribute source exists before it can
be admitted as a new candidate provider.

## TASK-018 latest bounded transition acceptance — 2026-09-06

The bounded Stage-10 run with the safe DOM-confirmation and authenticated
`code`/`shortcode`/`media_code` alias catalog remains unaccepted: it committed
one durable source, confirmed zero transitions and stopped with
`TRANSITION_FAILED` after the fixed retry. It did observe a stable changed
central-media identity and a post-input authenticated JSON response, but did
not observe a different safe-DOM canonical candidate or any accepted canonical
field in that response. No second download was started and partial artifacts
were cleaned.

This rules out the current DOM probe and the three explicit JSON canonical
aliases for this mobile presentation. Do not repeat the same collecting run or
raise target/retry/device limits. The next task is a no-download,
aggregate-only transition diagnostic that distinguishes available structural
identity sources without retaining DOM text, URLs, response bodies, cookies or
media identifiers.

## TASK-018 authenticated feed-queue transition candidate — 2026-09-06

The Stage-10 passive probe showed that the fixed full-viewport top hit is an
unknown descendant rather than the exact semantic `main` shell, so ADR 020's
narrow shell-swipe branch correctly remains unavailable. The previously
validated bounded wheel/keyboard path can nevertheless produce a stable active
media change and a new authenticated JSON response; the missing proof was only
the canonical code mapping in mobile MSE DOM.

ADR 021 therefore resets a bounded in-memory candidate catalog before fixed
Reels navigation and, after both stable-media and post-input JSON gates, first
uses a different canonical code only when the existing safe central-video DOM
probe directly supplies it. It then prefers a fresh feed-JSON code and permits
one unused candidate from that same authenticated feed queue. The candidate is
consumed once; old-page values, persistence, input admission and retry bounds
remain excluded. The latest bounded run found neither a different safe-DOM
candidate nor a `code` field to reserve; the catalog now recognizes only the
equivalent canonical response aliases `shortcode` and `media_code` as well.
Their values must still pass the same canonical regex and the two transition
gates before reservation. A new bounded 3/3 handoff run remains required
before any 50-Reel PWA acceptance.

## TASK-018 narrow feed-shell transition repair — 2026-09-06

The active-input probe now admits a native swipe through a semantic feed shell
only when the exact same noninteractive `main`/`role=main` element is the
full-viewport top hit at both endpoints and the selected central video is
directly below it in both hit stacks. Dialogs, controls, descendants of the
shell, hidden/inert surfaces, arbitrary overlays and other-video relations
remain rejected. This retains the direct-video path as the preferred case and
does not change the bounded native-touch action, JSON/canonical gate, retry or
timeouts. Chromium tests cover both admission and rejection cases; Stage-10
deployment must first passively verify that the live surface satisfies this
exact contract before another 3/3 attempt.

## TASK-018 Collector same-process handoff implementation — 2026-09-06

An opt-in `collector-handoff` implementation now retains one persistent
Collector Chromium process while an operator resolves only the visible dialog
through a private noVNC relay. The relay has a separate gateway, one-time
token, signed HttpOnly cookie, fixed-origin checks, short TTL and explicit
confirm/cancel state. Before confirmation the script creates no Collector
persistence/storage adapters and makes no Collector input; expiry/cancel closes
the browser fail-closed. The Stage-10 Compose profile has no published VNC,
CDP, profile or control port. Focused gateway and handoff-state tests pass.
Deployment and the required manual confirmation have completed; live 3/3 acceptance remains pending.

## TASK-018 deployed handoff acceptance — 2026-09-06

The Stage-10 private viewer was deployed and an operator completed the
same-process handoff. A gateway defect initially rejected the viewer WebSocket
because it checked the login-flow cookie name rather than the handoff cookie;
the gateway now checks its own signed `handoff_gateway_session`, with a focused
regression test. The corrected viewer accepted the private WebSocket and the
operator explicitly confirmed continuation.

The resulting bounded live run is not accepted: it committed exactly one new
durable source, performed its sole retry, confirmed zero transitions, and
stopped fail-closed with `TRANSITION_FAILED`. Aggregate evidence shows a stable
central-media change and post-action authenticated JSON, but no canonical
confirmation for a different Reel. Native touch was correctly withheld because
both endpoints hit a fixed semantic shell layer above the selected video rather
than the video itself. No second download was attempted. A stale `running` run
left by an earlier interrupted process was terminally marked failed without
altering its already durable source. The Stage-10 PWA command flow and the
50-Reel device-cap acceptance remain blocked until a safe, evidence-backed
transition repair produces a real 3/3 run.

## TASK-018 Collector operator handoff — 2026-09-06

The next implementation is an explicit one-time operator handoff to the same
running Collector Chromium process. It is specified in
`docs/tasks/018-collector-operator-handoff-to-working-live-run.md`; work must
continue through implementation, deploy and bounded verification, with only
the operator's manual treatment of an unknown dialog as an allowed pause.

## TASK-018 Collector presentation alignment — 2026-09-06

The Collector Xvfb and Chromium launch contract now matches the private
operator browser's 430x800 headed presentation, window placement, kiosk mode
and 0.9 device scale factor. This changes rendering context only: no modal is
targeted and the direct-hit, native-touch and JSON gates are unchanged. Targeted
runtime and diagnostic tests passed (35 passed, 2 skipped). Next: one passive
modal-lifecycle run on Stage 10; only direct hits can admit a bounded live 3/3.

The deployed passive run at `0b6ad30` retained the same blocker: both direct
hits were false and the focusable role-button under modal/dialog ancestry
persisted after the fixed waits. Presentation alignment is therefore not a
repair. No live collection was started.

## TASK-017 Stage-10 diagnostic result — 2026-09-06

One and only one `modal-lifecycle-diagnostic` run completed on Stage 10 from
`786dbcb`. It launched the persistent profile and reached Reels, produced five
redacted snapshots, and had no Collector persistence credentials or data-plane
services. A central video was present after Reels navigation, but neither
direct endpoint hit was ever true. From the first bounded readiness wait
through `before_collector_input` and the second wait, the top hit remained an
inherited interactive, focusable role-button with a modal/dialog ancestor and
the video below it in the point stack. Visual and layout viewport did not
differ. The interceptor therefore persists; it is not a transient readiness
condition and no safe wait/readiness repair exists. No new live 3/3 or 50-Reel
run is permitted. The next bounded task must compare browser launch/navigation
state without revealing Instagram content or automatically acting on the
modal.

## TASK-017 modal lifecycle diagnostic implementation — 2026-09-06

The Collector now has an explicit `modal-lifecycle-diagnostic` one-shot
container profile. It opens the configured persistent profile, takes exactly
five redacted passive hit-test snapshots around fixed two-second waits, and
exits without touch, click, keyboard, wheel, downloader, database, Redis, or
MinIO access. Its workspace result contains only fixed boolean fields, phase
enums, a count, and a fail-closed reason code. The normal Collector's direct
hit and JSON gates are unchanged. Next: run this diagnostic once on Stage 10;
only a result with both direct endpoint hits at `before_collector_input` can
admit the separate bounded 3/3 live attempt.

## TASK-017 modal lifecycle diagnostic specification — 2026-09-06

`docs/tasks/017-collector-modal-lifecycle-diagnostic.md` defines a bounded,
diagnostic-only next step. It records no private Instagram content and performs
no input, download or persistence; it must establish the modal interceptor's
lifecycle in Collector before another live collection attempt. The VPS passport
and safe operator commands are maintained in that task; one-time viewer
services are stopped outside an active operator session.

## TASK-016 repeat after connected inspect viewer — 2026-09-06

The operator confirmed that the repaired private viewer displayed a connected
remote browser, opened Instagram, and manually handled the visible dialog. The
one-time session was then cancelled and its link removed before a fresh bounded
Stage-10 target-3 Collector run. It still committed one real source, confirmed
zero advances and stopped `TRANSITION_FAILED` after its one retry.

The preserved aggregate evidence is unchanged: the selected central video was
available and in the viewport but not directly hit-testable; a focusable
inherited role-button below a modal/dialog ancestor intercepted both endpoints,
with the video present below the top point-stack hit. Touch was not dispatched.
Post-action authenticated JSON was observed, but no stable media change or
canonical confirmation followed. The download diagnostic reported a single
output with cleaned partial artifacts; the 3/3 and 50-Reel acceptance gates
remain blocked.

## TASK-016 inspect viewer connection state — 2026-09-06

The first inspect attempt reached a black viewer and later displayed reconnect
required, so no feed dialog was reviewed. Private server checks returned HTTP
200 for both the browser control endpoint and the noVNC asset; the failure is
therefore in the external viewer path, not authentication or the private
browser process. The operator-only `/interactive` route now uses noVNC Core
directly and displays explicit connected/disconnected state. It neither polls
profile readiness nor completes the session, and still exposes no public VNC,
CDP or browser control endpoint.

The focused gateway suite passed 13 tests; Ruff and diff validation passed.
Next: deploy this viewer, create a new inspect session, confirm the displayed
connection state, then manually inspect the dialog before any further Collector
run.

## TASK-016 bounded run after manual inspect — 2026-09-06

The inspect session was closed and its one-time link removed before the next
bounded Stage-10 target-3 run. That run still committed only one real source,
confirmed zero advances and terminated `TRANSITION_FAILED`. Every preserved
modal-interceptor fact remained present: a focusable inherited role-button
under a modal/dialog ancestor, with the selected video below the top point-stack
hit and no direct endpoint hit. Touch was withheld. There was neither stable
media change nor canonical confirmation, though post-action JSON was observed.

Therefore the manual inspect action did not change the state seen by Collector.
The evidence does not distinguish a dialog that reappears for a new browser
context from an action unrelated to that dialog. Do not run further collection
attempts until an operator workflow can visibly confirm the feed dialog's state
in the same persistent profile/context used by Collector. 3/3 and 50 remain
blocked.

## TASK-016 private feed-dialog inspection viewer — 2026-09-06

The login gateway now supports a one-time `inspect=1` launch for an explicitly
operator-controlled private viewer. After the normal single-use activation, it
opens `/interactive`, preserves the same signed cookie, origin checks and
private VNC relay, but does not poll browser readiness or complete the profile
check. The user can therefore inspect the authenticated feed dialog before the
15-minute session expires. The viewer never exposes credentials, cookies, CDP
or VNC publicly and does not automate any Instagram action.

The focused login-gateway suite passed 13 tests; Ruff and diff validation
passed. Next: deploy this gateway change, open an inspect session, manually
resolve only the understood dialog, close the session, and repeat bounded 3/3.

## TASK-016 post-profile-check Linux run — 2026-09-06

The one-time profile check reported that Instagram is connected, but this
establishes authentication only; it did not establish that the feed modal was
reviewed or dismissed. The subsequent bounded Stage-10 target-3 run committed
one real source and terminated `TRANSITION_FAILED` with zero confirmed
advances. The same focusable role-button under a modal/dialog ancestor still
intercepted endpoints, so touch was not dispatched.

This run additionally observed stable media change and post-action feed JSON,
but no canonical confirmation. The JSON gate therefore correctly remained
fail-closed. A profile-check viewer is not a sufficient manual-resolution flow:
it completes automatically when authentication is detected. Next: provide an
explicitly operator-controlled private viewer for reviewing the existing
authenticated feed dialog without auto-completing the profile-check session,
then repeat 3/3. The 50-Reel gate remains blocked.

## TASK-016 Linux blocker role evidence — 2026-09-06, d5d3dc5

The bounded Stage-10 target-3 run committed one real source, confirmed zero
advances and stopped `TRANSITION_FAILED`. Its preserved diagnostics identify a
focusable `role=button` through an interactive ancestor that itself has a
modal/dialog ancestor. It is neither disabled nor aria-disabled, and is not a
native button, anchor, form control, slider, contenteditable control, or
touch-action:none surface. It continues to intercept the endpoints above the
selected video; no touch was dispatched.

This is evidence of an active modal dialog intercepting the feed, not a safe
target for automatic input. The aggregate flags cannot disclose its purpose;
the Collector must not click or dismiss it. The next operational step is to
inspect and resolve the dialog manually in the authenticated interactive
session, then repeat the bounded 3/3 run. JSON confirmation, endpoint tests
and the 50-Reel gate remain unchanged.

## TASK-016 local-blocker role/state diagnostics — 2026-09-06

The probe now records only fixed aggregate booleans about the interactive
ancestor which intercepts a sampled endpoint: native button, anchor, form,
ARIA button/slider or contenteditable role; disabled/ARIA-disabled,
focusability, dialog/modal ancestry and `touch-action:none`. It does not emit
tag text, attributes, selectors, IDs, coordinates or other DOM content.

These facts are diagnostic-only. The target remains eligible only when both
endpoints directly hit the selected central `<video>`; an intercepted control
is never selected, and the JSON gate, bounded limits and fail-closed behavior
are unchanged. Actual Chromium fixtures cover disabled native, ARIA dialog
control and anchor/touch-action cases. Verification: 29 touch-target tests and
Ruff pass. Next: deploy this diagnostic build for one bounded 3/3 run and use
its aggregates to select an evidence-backed input repair. The 3/3 acceptance
and 50-Reel run remain blocked.

## TASK-016 Linux card-layer and shell evidence — 2026-09-06, 4d77c2d

The bounded Stage-10 target-3 run committed one real source, confirmed zero
advances and terminated `TRANSITION_FAILED`. The selected video remained below
the top point-stack hit, so touch was not dispatched. The local blocker has no
reported relation to any visible video: it neither contains nor lies within a
visible video, shares no bounded near ancestor with one, and is not a sibling.
It also has no recorded page-shell semantic ancestor and neither the hit nor its
interactive control ancestor is a direct body child.

This rules out the other-card-layer and page-shell classifications available to
the diagnostic probe. It remains an unidentified local interactive surface;
the data does not establish it as a safe input target. Post-action JSON was
observed without stable media change or canonical confirmation. Next: inspect
the surface's safe, fixed semantic role or interaction state rather than add
more candidate gesture coordinates. 3/3 and 50 remain blocked.

## TASK-016 local-card versus page-shell evidence

The probe now separately records a hit's relationship to any other visible
video: containment, being inside it, or a common ancestor within four levels.
It also records direct-body-child and semantic page-shell-ancestor facts. A
separate card-layer produces an other-video relationship; a shell-layer with no
visible-video relationship produces page-shell evidence. These are structural
observations only: neither permits targeting the layer.

Local Chromium fixtures cover both patterns; touch is still withheld in each.
Verification: 26 touch-target and 34 Stage-3B tests pass, with Ruff and diff
checks clean. Next: obtain the aggregate relation flags from one bounded Stage
10 run, then choose a repair supported by that evidence. The 3/3 and 50-Reel
acceptance gates remain blocked.

## TASK-016 Linux stack and viewport evidence — 2026-09-06, d44d4c2

The bounded Stage-10 target-3 run again committed one real source, confirmed
zero advances and stopped `TRANSITION_FAILED`. The selected video was in the
elementsFromPoint stack below the top hit for sampled endpoints, proving that a
higher surface intercepts those points. Both points were inside the visual
viewport; visual and layout viewports did not differ. The top hit has no fixed
ancestor and does not cover either the viewport or the visible video area.

This rules out a coordinate/visual-viewport mismatch and a viewport-wide fixed
overlay. The observed blocker is local to the sampled area. The probe still
reports an inherited interactive control, but neither the hit nor that control
is structurally associated with the selected video under the current bounded
relationships. Touch was correctly withheld; no stable media change or
canonical JSON confirmation followed. Next: safely distinguish whether the
local intercepting surface belongs to a separate feed-card layer or the page
shell before changing input targeting. 3/3 and 50 remain blocked.

## TASK-016 overlay versus viewport diagnostic evidence

The hit-test probe now samples `elementsFromPoint()` for every bounded endpoint
without returning stack elements. It records whether the selected video occurs
below the top hit, and whether the hit has a fixed ancestor covering the layout
viewport. It also records visual-viewport presence, layout/visual geometry
divergence and whether sampled points are inside the visual viewport.

A video below a fixed, viewport-covering hit is evidence of an external
intercepting surface. An absent video from the stack together with visual/layout
divergence is coordinate evidence, not an attribution to a particular element.
Neither pattern enables input through an obstruction. Local Chromium fixtures
cover both patterns; 58 touch-target/Stage-3B tests pass, along with Ruff and
diff checks. Next: obtain these aggregates from the bounded Stage-10 run before
selecting a concrete gesture repair. The 3/3 and 50-Reel gates remain blocked.

## TASK-016 Linux structural blocker evidence — 2026-09-06, db8a67c

The bounded Stage-10 target-3 run committed one real source and stopped
`TRANSITION_FAILED` with zero confirmed advances. The probe successfully found
the selected video in viewport, but no sampled endpoint hit it, so no touch was
sent. The obstruction facts were: control inherited from an interactive
ancestor, while the control neither contains the video nor covers its visible
area. The hit itself is neither inside nor contains the video, is not a video
sibling, has no recorded near shared ancestor, and does not cover the visible
video area. Native controls and pointer-events:none remain false.

This evidence rules out treating the observed control as the active-card
gesture surface. It suggests an external intercepting surface, but fixed
boolean facts do not identify it or justify targeting it. Post-action JSON was
observed, but there was no stable media change or canonical confirmation. Next:
add bounded, non-content structural evidence sufficient to distinguish a global
overlay from a coordinate/viewport mismatch, then choose a repair. 3/3 and 50
remain blocked.

## TASK-016 structural obstruction diagnostics

The probe now reports structural boolean facts independently of the existing
control-category precedence: self versus inherited control, hit containing or
inside the video, sibling relationship, shared ancestor within four levels
(excluding body/html), and full coverage of the visible video rectangle.
The controlling ancestor is separately checked for containing the selected
video and covering its visible rectangle. This distinguishes a sibling layer
inside a shared interactive wrapper from a direct control or unrelated overlay.

These are DOM relationships, not assertions about an Instagram card's purpose.
Full coverage means bounding-rectangle coverage, not opaque visual occlusion.
No raw DOM, identifiers, coordinates or attributes leave the probe. Touch still
requires direct hits on the selected video at both endpoints. Next: collect
these flags on Stage 10 before choosing a gesture repair; 3/3 and 50 are still
unaccepted. Synthetic Chromium tests cover shared-control wrappers, direct
controls, unrelated layers, partial coverage and controlling video ancestors.
Verification: 56 touch-target/Stage-3B tests passed; Ruff and diff checks passed.

## TASK-016 Linux obstruction evidence — 2026-09-06, 67d3833

Built the revision-tagged Collector and ran one bounded Stage-10 target-3 run
with the existing AppArmor profile. One real source was committed; no advances
were confirmed and the run terminated `TRANSITION_FAILED`.
The probe evaluated successfully and found the selected video in viewport.
Sampled hits included `control` and `other_element`; neither sampled start nor
end hit the selected video. Pointer-events:none and native video controls were
false. Touch was not dispatched. Wheel ran, but no stable media change or
canonical confirmation followed; post-action JSON was observed.
These aggregate categories identify the endpoint obstruction class, not the
specific UI element or a safe alternate gesture target. The control classifier
uses closest(), so an interactive ancestor also qualifies. Next: establish the
obstructing surface's relationship to the active card using bounded safe
structural diagnostics before choosing a repair. 3/3 and 50 remain blocked.

## TASK-016 endpoint obstruction diagnostics

The next diagnostic build classifies failed endpoint hits using only fixed
boolean fields: null, control, other video, ancestor/descendant of the selected
video, or other element. It also reports pointer-events:none and native controls
on the selected video, and whether any sampled start/end hit the video. Both
endpoints are evaluated independently; previously a failed start short-circuited
the end check. A gesture still requires both endpoints of the same pair to hit
the selected video. The nine candidate pairs and input/JSON limits are unchanged.

These flags survive wheel fallback and engine aggregation. No tag names,
attributes, text, coordinates or DOM contents enter the operator result. Local
Chromium fixtures cover controls, generic overlays, another video, disabled
pointer events, null hits and separately blocked start/end points. The cause on
VPS remains unknown until this build produces aggregate evidence; 3/3 and 50
acceptance remain blocked. Use that evidence to choose an input repair rather
than treating a blocker category as permission to target it.

Verification: 51 tests passed in the touch-target and Stage-3B suites, including
actual Chromium probe evaluation. Ruff and `git diff --check` passed.

## TASK-016 Linux verification of 2ebce26 — 2026-09-06

Built and ran the explicitly tagged Collector image on Stage 10 with its
existing AppArmor profile and bounded target of three. The run committed one
real source and terminated `TRANSITION_FAILED` with zero confirmed advances.
Preserved diagnostics show probe attempted/evaluated, no probe failure, central
video present and in viewport, but endpoint hit-testing unsuccessful. No touch
was dispatched. Keyboard/wheel produced no stable media change; post-action
JSON was observed without canonical confirmation. This does not pass 3/3.
Next: diagnose why the selected endpoint pairs fail hit-testing using safe
aggregate facts, retain both endpoint checks and JSON gate, then repeat 3/3
after an evidence-backed repair. The 50-Reel acceptance remains blocked.
Historical all-false diagnostics below cannot establish absent touch because
the earlier wheel fallback erased those facts.

## TASK-016 probe diagnosis and selection repair

Local regressions reproduced two defects in the previous native-touch build:
wheel fallback reset the entire target diagnostic record, erasing even a
successful touch dispatch; media identity and touch discovery could select
different videos because their centre-distance formulas differed. Consequently
the all-false live target flags alone did not establish that no touch was sent.
The actual live input outcome remains unverified.

Both probes now embed one shared visible-central-video selector. Target
diagnostics survive fallback until the engine merges the attempt, with separate
boolean attempted/evaluated/failed/central-video-missing fields. Existing
endpoint hit-tests, JSON confirmation and bounded run limits remain enforced.
Tests execute the actual probes in installed Chromium on local fixtures and
exercise failed/missing/overlay outcomes through wheel and engine diagnostics.
Verification: the focused probe and Stage-3B suite passed 43 tests, including
real Chromium probe execution; Ruff and `git diff --check` passed. The broader
runtime/gate run passed its other checks; its diagnostic-schema expectation
was updated and verified by the focused rerun.
Next: deploy this repair and run bounded Linux 3/3; retain the 50-Reel gate until
the required native-touch and new canonical JSON evidence passes.

## Stage 10 Linux staging preparation

Stage 10 repository preparation now provides a reproducible Ubuntu 24.04
staging composition, a standalone networkless Chromium sandbox smoke, pinned
seccomp and enforcing AppArmor policies, read-only host preflight, explicit
sandboxed Playwright launch, a private-X one-shot live entrypoint, static/unit
tests, and an operator runbook. A Stage-10-only Caddy ingress preserves Backend
paths on one browser origin and binds only to `127.0.0.1:13080`; the obsolete
frontend `/videos` redirect and its Service Worker shell entry are removed.
The Stage 10 overlay now also has an opt-in hardened single-account login
browser and gateway. Same-origin `/connect/*` and `/remote/*` routes reach only
the gateway; VNC, CDP and browser control remain private. Login and Collector
share the persistent account profile and its atomic lock, so they fail closed
rather than run concurrently. The login browser verifies UID/GID 10001, mode
0700, zero capabilities, no-new-privileges, seccomp and AppArmor before opening
Chromium. Linux/iPhone live-login acceptance remains pending.
The Stage 10 web build pins its manual collection target to three so a
PWA-created queued run exactly matches the bounded live Collector contract;
the production collection target remains unchanged.
The manual PWA download action now first uses an already-ready account-owned
catalog, so an operator-prepared batch can be copied to the device without
creating a redundant Instagram collection run. It requests a new bounded run
only when that catalog is empty.
Linux live acceptance found that a profile created by the system login
Chromium closed immediately when reopened by the separate Chrome-for-Testing
binary. Stage 10 now pins login-browser and Collector to the same sandbox-
verified Chrome for Testing artifact. A profile made by a different browser
release is reset only through the existing guarded account-profile reset
contract after explicit operator confirmation; it is never force-opened or
downgraded. A successful reset also moves that account to `disconnected`,
preventing a stale dashboard claim that Instagram remains usable.
The Collector remains UID/GID 10001 with all
capabilities dropped, no-new-privileges, read-only rootfs, private shared
memory, bounded resources, no published port, no host networking and no Docker
socket.

The Collector feed adapter now uses the accepted bounded mobile transition
cascade: it first sends one native CDP touch swipe only to a hit-testable
central video, using the real scroll owner (or the document scroll root) to
bound geometry when one exists; a CSS-locked ownerless feed uses the visible
video geometry itself. It then tries keyboard navigation and finally applies a
90%-viewport pointer wheel.
It no longer changes `scrollTop` through JavaScript, because that can repaint
the DOM without invoking Instagram's feed-input handling. Each action is
accepted only after two stable samples of a changed
active media identity and a different canonical Reel from authenticated feed
JSON observed after the input's in-memory response boundary; the visible
`/reels/` URL and DOM candidate are not evidence of movement.
The active-media selector follows the same centred-card rule as canonical
candidate extraction. If an action changes a rendered media element but the
following bounded authenticated-feed-JSON wait cannot confirm a different
canonical Reel, the one permitted retry is forced to the pointer-wheel
fallback instead of repeating that ambiguous action. That fallback follows the
accepted spike exactly: a 90%-viewport wheel is sent from the mobile viewport
centre after verifying a visible Reel target. The identity is retained only in
memory and no media identities, URLs, cookies, or account data are logged.
Operator diagnostics separately record aggregate stable-media, post-action
JSON and canonical-confirmation facts, plus only boolean active-feed target
and native-swipe facts. Unit coverage includes the verified native-scroll-owner
path, no-container fallback, this catalogue-mismatch retry, response-boundary
gate and viewport-centre input.
Linux Collector image verification remains required before a repeated live
run.

The live Collector pauses the current Reel while its separate session-first
download runs. Before testing a card transition it restores muted playback on
the centred active element, matching the accepted spike; this remains browser
memory only and does not alter the downloaded source file.

Current live evidence is deliberately not accepted as a multi-Reel collection:
the Stage-10 Collector repeatedly commits one real source but terminates with
`TRANSITION_FAILED` before a canonical next Reel is confirmed. TASK-016 tracks
the required repair and the subsequent PWA-triggered, clean 50-Reel acceptance;
previously prepared/seen media must not be counted for that task.
The bounded Linux verification of `e45e098` observed a stable changed central
media identity, but no different canonical candidate from authenticated feed
JSON after the action checkpoint. It therefore correctly remained
`TRANSITION_FAILED`; this is evidence that the new JSON boundary is fail-closed,
not evidence of a repaired 3/3 transition.
The first native-touch live run likewise did not validate a gesture: the page
had no acceptable scroll-owner/document-root target, so touch was safely not
sent. Keyboard/wheel then observed media and post-action JSON activity without
a different canonical candidate and failed closed. TASK-016 now has a
hit-testable-central-video fallback for CSS-locked React gesture feeds before
another 3/3 attempt.
The subsequent ownerless-target build did not yet validate that fallback in
Linux: its bounded run again safely recorded no available/in-viewport/
hit-testable target and sent no native touch. The keyboard/wheel fallback saw
stable media and post-action JSON activity without a different canonical
candidate, so it correctly failed closed after one durable source commit.
TASK-016 now requires safe aggregate probe-state diagnostics and alignment of
its target selection with active-media selection before another live run.

The first Ubuntu staging attempt accepted the Collector sandbox smoke, Redis
recovery, PostgreSQL and MinIO restore, loopback-only single-origin ingress,
public Funnel routing, iPhone PWA installation, management-device pairing and
the hardened Linux login boundary. A test-account login, one session-first
source download, browser-free normalization, ready catalog publication and
HTTP Range verification also passed. The bounded three-Reel run then stopped
after the first durable item because the live mobile feed did not confirm a
card transition. The replacement media-identity cascade above is now covered
by unit tests; repeat the bounded Linux live run before accepting multi-Reel
collection or PWA offline playback from real media.

## Stage 9 viewed lifecycle

Stage 9 uses swipe-only viewed semantics: only a confirmed user touch/pointer
swipe transition from full-screen A to different full-screen B marks A viewed.
Playback progress, autoplay, duration, ended, visibility, reloads and internal
feed changes are deliberately excluded. The first local IndexedDB event fixes
`viewedAt` and `deleteAfter` (+1 hour), tombstones the Reel and persists its
outbox before sync. Expiry deletes only the local Cache Storage object and is
deferred only while that same Reel is active; canonical MP4/normalization data
is never deleted. Migration `0009`, account-scoped backend idempotency and
catalog exclusion are retained.

Stage 9 verification now additionally covers a disposable real-PostgreSQL
control-plane race suite (concurrent view sync, first-view preservation and
account isolation), local ffmpeg/ffprobe normalizer integration,
Serwist/no-store policies, FastAPI startup imports, and secret/artifact audits.
No Stage 9 disposable resource remains. The manual iPhone sequence is still
pending; Funnel and production PWA were not started for Stage 9.

The `/offline` Reels surface presents only local reserve and real deletion
feedback; it exposes no viewed marker, timestamps, UUIDs or reason codes.
Stage 8 infrastructure and manual sequential download/cancellation are kept,
but automatic refill is disabled for the MVP through the production-false
`AUTO_REFILL_ENABLED` compile-time gate. No launch/foreground/online/deletion/
quota path runs automatic reserve work while the gate is off.

## Stage 8 local reserve management

The PWA now has a foreground reserve controller that reconciles local media,
uses durable device-only reserve settings, requests bounded collection only when
the full ready catalog is short, and fills only missing Reels sequentially.
Migration `0008` stores redacted account-owned device reports; IndexedDB plus
Cache Storage remains the local truth. Closed-iOS background execution is not
claimed. The disposable Chromium iPhone-viewport E2E now passes: bounded
collection, reload deduplication, offline `/offline`, quota pause/resume,
cancel preservation, safe UI redaction and no-store management/reserve checks.
Its random Compose project, volumes, images and artifacts were removed after
acceptance. Manual iPhone acceptance is also complete through a temporary
Tailscale Funnel and a fully isolated synthetic fixture: Safari and the
Home-Screen installation correctly kept separate device-local libraries,
each filled from the same ready catalog without an extra collection run.
The check covered pairing, synthetic login, target fill, offline `/offline`,
reload/Home-Screen no-op, network return, pause/resume, quota simulation, UI
redaction, and server-side cancellation. During acceptance, cancel was
hardened to cancel the cycle-owned server run, management fetches gained a
15-second deadline, and the fixture received an explicitly build-time-only
quota control. Funnel and all fixture containers, volumes, networks, images,
and test artifacts were removed afterwards.

## Current stage

Stage 7 connects the canonical PWA dashboard to the protected Stage 6
management API while preserving the existing offline library, sequential queue
and `/offline` player. Device pairing remains operator-assisted: the dashboard
accepts a one-time code but never stores or displays it. The management cookie
is HttpOnly; an in-memory CSRF capability is refreshed from the protected
same-origin session endpoint after a PWA restart and is cleared on revoke/401.
Instagram login accepts only the fixed HTTPS same-origin Stage 4 `/connect/…`
route, collection/normalization/local-download progress uses confirmed counters
only, and IDs, media details and raw backend errors stay hidden. Management and
login capability responses are never cached; `/` and `/offline` retain their
offline shell behavior. Auto-collection is deliberately unavailable because
`scheduler_active=false`. The combined disposable Stage 7 mobile-viewport E2E
fixture has passed against synthetic PostgreSQL/MinIO, fixture gateway,
Collector and normalizer services; its exact Compose resources were removed
after acceptance. A real iPhone Stage 7 acceptance remains pending and needs
separate explicit approval; Stage 4 Risk 17 remains open. No live Instagram,
Funnel or PWA was launched during implementation.

Stage 4 secure mobile login is implemented in the working tree: one-time
hashed links, an isolated same-origin gateway, a non-root Chromium image and a
dedicated persistent account profile for the duration of an active login
deployment. Windows Docker Desktop manual iPhone Safari acceptance confirmed
the real remote Instagram login/challenge, profile confirmation and the local
success-screen UX; the authenticated Instagram feed was not exposed after
completion. The business API did not request or persist credentials, while the
remote-browser keyboard/pointer transport remained a deliberate trust
boundary. Post-acceptance cleanup removed the sensitive test browser profile,
the temporary Stage 4 database, Funnel state and the local staging secrets.
The current Windows-compatible runtime keeps `login-browser` non-root with
`cap_drop: ALL`, but uses `seccomp=unconfined` for that container only. It is
therefore functionally complete, not production-hardened. The Ubuntu VirtualBox
synthetic Chromium sandbox acceptance did not complete and is not evidence of
Linux deployment readiness; Risk 17 remains open. The staging UI has an
operator-created one-time link and **Open browser** control; a future protected
management/dashboard flow will create that session and enter the login flow
without exposing credentials to the business API. Collector remains untouched;
Stage 5 now adds a separate browser-free normalizer worker. The preserved
ten-Reel Collector smoke was manually accepted after migration `0006`: all ten
sources became ready catalog videos, completed on attempt one and were cleaned
post-commit; no staging, pending, running or failed jobs remain. Stage 3C.2
remains separate.

Post-iPhone hardening block 4A is implemented: `/` is the canonical offline-library dashboard and `/offline` is the clean Reels surface. Stage 10 removes the obsolete `/videos` frontend redirect so that path belongs exclusively to the Backend catalog API. Instagram Collector Stage 3B is a manually invoked, bounded three-Reel operator composition over Stage 3A adapters. A test-account live run successfully confirmed three session-first downloads, validations, MinIO publications, PostgreSQL commits, two targeted transitions, durable `source_ready` Reels and read-only verification without changing `videos`. Stage 3C.1 then continued that same account-owned reserve from three to ten: seven new sources committed, six transitions confirmed, `videos` remained empty and the final read-only verifier passed. Stage 3C.2 now adds a separate non-root Linux Collector image and a disposable internal-network fixture cycle over real PostgreSQL/MinIO; automated and PowerShell manual synthetic acceptance both passed, and the API image remains browser-free. Live Instagram in the container has not been tested.

The disposable synthetic mobile fixture and the synthetic iPhone Stage 7 PWA
acceptance passed. Stage 4 real remote login also passed independently. The
combined retained Stage 4 profile → Collector → normalizer → PWA chain is not
accepted on Windows Docker Desktop: isolated non-root Chromium preflight,
including direct private CDP, closed before browser readiness because of a
Docker Desktop sandbox incompatibility. It must be re-accepted on Linux staging
or a real server. No `--no-sandbox`, root browser, privileged container or
`SYS_ADMIN` workaround was applied. Risk 17 remains open.

## Completed

- Defined product idea.
- Defined MVP scope.
- Created initial architecture.
- Created project documentation.

## Instagram Collector roadmap

1. Architecture foundation.
2. Fixture-driven Collector engine.
3. Production Collector runtime: 3A adapters, 3B bounded three-Reel operator
   run, then 3C Linux/container ten-Reel verification.
4. Phone-based Instagram connection.
5. Normalization queue.
6. Collector backend API.
7. Dashboard integration.
8. Local reserve management.
9. Viewing, delayed deletion and replenishment.
10. Reliability and security.
11. Final acceptance.
- Connected GitHub repository.
- Defined Codex workflow.
- Completed TASK-001: iOS offline video storage spike.
- Completed TASK-002: production bootstrap with Next.js web app, FastAPI API, PostgreSQL, Redis, MinIO, Docker Compose, health checks and an empty reversible Alembic migration.
- Implemented TASK-003: videos table, MinIO adapter, idempotent MP4 seed, video list and Backend API streaming with single HTTP Range support.
- Implemented TASK-004: HMAC-signed keyset pagination for `GET /videos`, deterministic batch MP4 seed, and a native scroll-snap multi-video feed with muted autoplay, shared sound state and incremental loading.
- Completed the current iPhone PWA acceptance run through Tailscale Funnel staging.

## Current focus

Instagram Collector Stage 3B retains the network-free fixture service over the
stage 1 account, collection-run, Reel pipeline and normalization-job state. It
proves `pause -> temporary download -> validation -> publication -> one DB
transaction -> advance`, including compensation of an object created by the
failed attempt. Fixture storage and SQLite are isolated from production settings.
The explicit headed operator composition now wires the optional isolated
Playwright feed, minimal in-memory session CookieJar, session-first yt-dlp,
ffprobe and MinIO source storage. Its bounded test-account run successfully
validated three durable source commits and two targeted transitions; the
post-run verifier also confirmed the exact MinIO/object and `videos` deltas. A
durable commit gates each transition: positions 1 and 2 have one
bounded retry wheel after an unconfirmed transition, while position 3 never
scrolls. Scheduler, Collector API and frontend remain absent. Stage 5 provides
a separate normalizer worker with PostgreSQL leases, MinIO staging/final
publication, safe retry/reconciliation and post-commit source cleanup; it does
not start from FastAPI. Stage 4 now supplies a separate mobile login browser boundary but does
not invoke a Collector run. Windows/iPhone functional acceptance succeeded, but
the Windows `login-browser` seccomp exception means hardened Linux deployment
proof remains open under Risk 17. The preserved Stage 3C PostgreSQL/MinIO smoke
state remains separate, and the validated local spike is not copied into
production.

Block 4A keeps `/offline` as the Reels-like control mode through the shared
`VerticalVideoFeed`; `/videos` no longer carries a frontend route, online feed,
or native player. `/` is a video-free dashboard that loads the full
paginated server catalog into the existing sequential offline queue. Offline video loops with `object-cover` and starts with sound enabled. It first attempts normal audible autoplay; an iOS policy
rejection leaves the video unmuted and paused with an explicit Play control,
never a silent muted fallback. Explicit tap-pause state alone otherwise reveals
central SVG controls, which hide on the current video's confirmed guarded
`play` event. Holds remain temporary and never reveal those controls. Active
selection is reversible and only pauses/plays cards: partial A↔B reversals keep
both saved positions and frames. A separate full-screen commit (ratio ≥ 0.999
and 2 CSS px geometry tolerance) permits only the previous committed card to
seek to 0 offscreen; a post-commit return starts at 0 with guarded seek fallback.
Reels-only styles suppress iOS callout, selection and drag while the gesture
state machine preserves native vertical scrolling.

The full-screen commit atomically marks the prior committed card and immediately
checks cached intersection and root geometry. Consequently, either observer
order (`A=0` before `B=full`, or the reverse) produces one offscreen reset.
The card progresses through reset-required, reset-in-flight and
prepared-at-zero; it is shown after a decodable first frame and returns without
a second seek or hidden-frame transition.

The final visual tuning uses a bounded safe-area-aware navigation lift. Reels
places progress in a transparent non-interactive layer over one fixed shared
glass backdrop that continues through the pill and safe area. The shared navigation marks `/` (**Главная**) or `/offline` (**Рилсы**) active. This is CSS/DOM layout work only and does not alter media, gesture or scroll lifecycles.

## Production-like VPS foundation

Implemented the first deployment foundation without changing local development:

- added an isolated production Compose file with Caddy as the only public service;
- kept Next.js standalone runtime (`node server.js`);
- separated Alembic migration into a one-shot `migrate` service;
- added private PostgreSQL, authenticated persistent Redis, and private MinIO volumes;
- added an idempotent MinIO bucket/application-user bootstrap job;
- added a safe production environment template and VPS launch/verification guide.
- hardened production API and migration commands with `uv run --no-sync` after local smoke showed that plain `uv run` attempted an unavailable development-dependency sync at runtime.
- verified the production Compose foundation locally through Docker Desktop: health endpoints, Caddy routes, CORS, MinIO bootstrap, migration idempotency, Range delivery, Redis AOF, and persistence across a restart.

## Public Tailscale Funnel staging

Verified a separate staging override for iPhone PWA testing: Funnel provides
one public HTTPS `*.ts.net` origin to a loopback-only local Caddy instance,
which routes `/api/*` to FastAPI after removing the prefix and all other paths
to Next.js. The browser API URL builder now explicitly supports an optional
path prefix, so the same code supports both the existing two-origin deployment
and the Funnel single-origin layout. It is intentionally not a persistent
production environment.

Not implemented in this block: backup/restore scripts, automated deployment,
monitoring, or a concrete VPS configuration.

## Next step

Next, deploy and preflight the opt-in hardened Stage 10 login boundary. After a
manual TEST-account login succeeds and the browser exits cleanly, run the
separately confirmed bounded three-Reel Collector, then normalizer, API/Range
and installed-iPhone PWA acceptance. No arbitrary `return_url`, credential form
or dashboard-to-Instagram direct link is planned.

## Recent decisions

Added:
- Technical decisions documentation.
- Technical risks documentation.
- Изолированный React/Vite PWA spike в `spikes/ios-offline-storage`.
- Cache Storage для тестового MP4 и IndexedDB только для успешно сохранённых метаданных.
- Автоматические тесты ключевой логики spike и инструкция по ручной проверке на iPhone.
- На iPhone подтверждено удаление тестового видео: оно не возвращается после перезапуска PWA.
- В интерфейсе разделены точный размер готовых видео и приблизительное origin-wide использование browser storage.
- TASK-001 пройден на iPhone 16 Pro с iOS 26.5.2 и 44,2 ГБ свободного места: видео размером 13 864 238 байт сохранилось после перезапуска PWA и воспроизвелось в авиарежиме.
- Для MVP принят подход: Cache Storage для видео и IndexedDB для метаданных готовых видео.
- Reproducible Docker Compose bootstrap added: Node.js 24.14.0/Next.js web app and Python 3.14.3/FastAPI API with PostgreSQL, Redis and MinIO.
- API exposes `/health/live` (FastAPI process only), `/health/ready` (PostgreSQL and Redis only), and independent `/health/minio` diagnostics.
- Alembic has an empty, reversible initial migration; Instagram collection, downloads, authentication, feed logic, Celery and production offline caching remain unimplemented.
- Web dependency security triage updated Vitest to 4.1.10 and removed its critical development-only advisory. The current dependency tree uses Next.js 16.2.11 and retains three high npm-audit findings: optional `sharp` 0.34.5 plus two advisories through Next.js's nested PostCSS 8.4.31. No unsafe force fix, override or Next.js downgrade was applied.
- TASK-003 streams video through Backend API rather than presigned storage URLs. Integration tests use isolated PostgreSQL and MinIO infrastructure.
- TASK-003 was validated end-to-end: idempotent seed uploaded the 13,864,238-byte spike MP4, `/videos` returned one record, HTTP streaming returned `200` and `206`, multipart Range returned `416`, and the video remained available after `make down`/`make up`.
- TASK-004 uses `created_at DESC, id DESC` keyset pagination with an HMAC-SHA-256 signed opaque cursor. The cursor secret is required at runtime and never belongs in Git.
- TASK-004 keeps loaded video elements mounted while validating native scroll-snap UX. Post-iPhone hardening block 2 extends the source window to previous/current/next: active uses `preload="auto"`, neighbours use `preload="metadata"`, and all distant cards remain mounted without a source. Full DOM virtualization remains a future real-device performance task.
- The active-player selection retains the latest `IntersectionObserver` ratio for every feed card, resolves ties by the feed center, and has a requestAnimationFrame-throttled scroll fallback for browsers that emit only partial observer callback batches.
- Real Instagram Reels passed the manual TASK-004 feed smoke scenario in Chrome and Yandex Browser. The earlier issue was limited to some third-party test MP4 encodings, not pagination, active-player selection, the media window, Range streaming or the Backend API. A future ingestion task must define media validation and, if needed, normalization or transcoding for a safe MVP format; no transcoding was added to TASK-004.
- TASK-005 Block 1 adds the versioned `offline-reels` IndexedDB schema and `offline-reels-media-v1` media cache behind typed browser-only adapters. Reconciliation marks stale or invalid local records failed and removes orphan cache entries; Block 2 builds on this foundation.
- TASK-005 Block 2 adds a one-at-a-time, explicitly user-started local download queue. It passes one Backend stream through `TransformStream` directly to an owned Cache Storage response, avoiding `ReadableStream.tee()` and downloader response cloning. Progress is in-memory only; IndexedDB receives `0` at start and the verified final byte count only on completion. Downloads do not auto-resume after reload or network restoration; abort and quota failures pause the queue. Service Worker, `/offline`, cached-media Range delivery and offline playback are still not implemented.
- TASK-005 Block 3.1 separates reusable vertical playback UI from the online data layer. `VerticalVideoFeed` receives typed items and media URLs, exposes optional actions and active-item callbacks, and retains the observer/rAF selection and source window. `VideoList` still owns online requests, cursor pagination and local-download controls; `/offline` is not implemented.
- TASK-005 Block 3.2 adds `/offline` as a local-only completed-video catalog with an exact library-size summary and approximate origin usage/quota. Its initial temporary Cache Storage-to-Blob adapter was later replaced by the Service Worker media route; production playback no longer creates Blob URLs from the media cache.
- The Block 2 downloader uses `fetch(..., { cache: "no-store" })`. The API CORS policy therefore explicitly permits `Cache-Control` in addition to `Range`, as well as `GET` and `HEAD`, for the configured `FRONTEND_ORIGIN`; it exposes the media response headers needed by the downloader. This keeps the origin allowlist explicit and does not enable credentials or wildcards.
- TASK-005 Block 4.1 adds a Turbopack-compatible Serwist application shell. `@serwist/turbopack`, `serwist` and native `esbuild` build exactly one dynamically served worker at `/serwist/sw.js`; `SerwistProvider` registers it at scope `/` only in production. The Turbopack glob manifest contains only static assets, not literal App Router routes, so the worker adds `/offline` and `/manifest.webmanifest` explicitly with deterministic SHA-256 revisions derived from application-shell build inputs. Navigation fallback is restricted to `/` and `/offline`; API, streams and media are not runtime-cached. Serwist shell-cache cleanup only targets its precache names and leaves `offline-reels-media-v1` untouched.
- TASK-005 Block 4.2 previously supplied a revisioned `/videos` frontend shell. Stage 10 removes that obsolete shell and its redirect so the exact path can remain the Backend catalog API on the single staging origin. Catalog failures remain controlled on the canonical `/` dashboard; the worker has no runtime caching and does not force `skipWaiting`.
- TASK-005 Block 5.1 registers a same-origin `GET /offline-media/{uuid}` route in the existing Serwist worker. It validates the exact synthetic path, reads only `offline-reels-media-v1`, preserves cached MP4 headers, and returns controlled `404`/`400`/`503` responses without network fallback. `/offline` uses the synthetic URLs directly, while a page not yet controlled by the worker shows a controlled readiness message rather than silently recreating Blob URLs. Block 5.2 subsequently added the current single-range `206`/`416` behavior.
- TASK-005 Block 5.2 replaces the temporary Range rejection. The worker supports `bytes=start-end`, `bytes=start-`, and `bytes=-suffixLength`; it clamps a valid end to the cached file size and preserves safe media validators. It returns `Accept-Ranges: bytes`, correct `Content-Length` and `Content-Range` for `206`, and `Content-Range: bytes */total` for `416`. Multiple ranges are deliberately unsupported and return `416`; no multipart response is generated. HEAD returns equivalent metadata without a body.
- TASK-005 Block 6.1 makes local reconciliation idempotent across interrupted downloads and partial cleanup. Only a metadata record whose cached MP4 validates remains `completed`; cache entries belonging to failed records, missing metadata, zero-byte bodies or invalid media are deleted. Cache Storage failures become controlled local-storage errors, while delete/clear retain their cache-first, reconciliation-backed compensation order. Quota, unavailable browser storage and interrupted download states remain typed safe errors; iPhone quota and long-session acceptance are still pending.
- TASK-005 Block 6.2 pauses local playback on visibility/page lifecycle transitions and prevents stale asynchronous `play()` work from reviving an old item. Source assignment stays bounded during rapid navigation and list mutations; active-item removal selects a valid successor without a backend request. Worker readiness is controlled through `navigator.serviceWorker.controller` and `controllerchange`, with no automatic reload. The Range handler still reads a cached MP4 once into worker memory per request; real iPhone memory and lifecycle acceptance remain pending.
- Post-iPhone hardening block 2 changes the shared media window to previous/current/next. The active player keeps `preload="auto"` and autoplay; both adjacent players retain a source with `preload="metadata"` and remain paused. Distant and terminally failed players clear `src` and call `load()`. This improves backward navigation without changing API pagination, downloader/queue, IndexedDB, Cache Storage or Service Worker contracts. A real iPhone smoke is required because `preload` is advisory and offline Range handling can materialize an MP4 in worker memory.
- Post-iPhone hardening block 3 adds an explicit Reels-like mode to the shared `VerticalVideoFeed` and enables it only for `/offline`; Stage 10 reserves `/videos` for the Backend API. Reels initializes unmuted and first attempts guarded audible playback. If iOS rejects that autoplay, it stays unmuted and paused with an accessible Play control; no silent fallback is attempted. A single pointer state machine distinguishes tap, 250 ms centre hold, outer-10% edge hold and movement beyond 12 CSS px without preventing native scroll. Only an explicit tap-pause or audible-policy rejection exposes central SVG controls; an actual guarded `play` event for the current video hides them. Holds never reveal controls. An activated centre hold preserves a pause lock for its original item/video/source/pointer sequence during scroll and iOS `pointercancel`; it resumes only on the actual touch end when that original item is active and was playing before the hold. Offline videos loop with `object-cover`, temporary edge holds use 2×, and scoped Reels styles suppress iOS callout/selection/drag without affecting the dashboard. Effective active selection is reversible and controls only pause/play while cards are partial. A full-screen commit requires observer ratio ≥ 0.999 plus 2 CSS px card/root geometry tolerance; only after it may the previous committed and fully invisible card reset offscreen. Thus a partial reversal resumes the saved position, while a post-commit return starts from 0 under existing seek guards. The lower Reels hierarchy is metadata overlay, non-seekable progress, then a safe-area-aware glass navigation; scoped backdrop blur is limited to that lower zone. The shared two-link navigation marks `/` (**Главная**) or `/offline` (**Рилсы**) active. Startup attempts guarded play at `HAVE_METADATA`/`loadedmetadata` rather than waiting for `canplay`; reset seeks still wait for current `seeked`. Stale-frame protection, playback generations and the previous/current/next three-source bound remain unchanged. iOS WebKit can briefly freeze or jump at 1×↔2× for AAC media; the MVP keeps normal audio and standard pitch preservation, accepts this platform limitation, and retains remux-first ingest rather than forcing short-GOP/no-B-frames transcodes. Re-downloading unchanged server media does not itself change that WebKit behavior.
- Post-iPhone hardening block 4A makes `/` the canonical dashboard and manifest `id`/`scope`/start route. It fetches every signed-cursor catalog page with duplicate/cursor-loop protection only while online, treats an offline catalog as neutral rather than an error, aborts and invalidates a pending request on connectivity loss, and reloads automatically on return to network. It sends only incomplete or failed records to the existing one-at-a-time queue, and reports storage and batch state as percentages only. Clear aborts the active queue, waits for its pump to settle, then removes only `offline-reels-media-v1` and IndexedDB records; a late download cannot repopulate the library. `/offline` removes summary, byte-size, technical-title and individual-delete presentation while preserving all Reels lifecycle guards. Stage 10 removes the obsolete `/videos` shell entry and redirect; API video routes remain uncached. There is no runtime redirect from `/offline` to `/`: existing iOS installations must be reinstalled once after the manifest start-route migration, while precached `/` and `/offline` continue to support offline navigation. Future watched-retention policy is not implemented: a watched reel may later be removed locally after one hour and replaced when online, but a fully closed iOS PWA cannot guarantee background work.
- Post-iPhone hardening adds a controlled installed-PWA shell update. Serwist's supported `waiting` and `controlling` lifecycle events drive a compact Russian notification; no update is activated or page reloaded until the user selects **«Обновить»**. The action uses Serwist's message-based `SKIP_WAITING` path, reloads exactly once after `controllerchange`, and never accesses `offline-reels-media-v1` or the offline IndexedDB store.
- A manual smoke exposed the accepted PostgreSQL/MinIO inconsistency where metadata can outlive a deleted MinIO object. `VerticalVideoFeed` now treats a media `error` as terminal for that card: it clears the source and native loading state, shows a safe local message, and suppresses automatic source retries. Neighboring cards remain usable; no automatic PostgreSQL/MinIO reconciliation or backend fallback was added.

## Current open questions

- Exact synchronization strategy.
- Instagram session management.
- Media delivery architecture.
- Долгосрочная сохранность Cache Storage/IndexedDB и поведение при ограничении квоты iOS.

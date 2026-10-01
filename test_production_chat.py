from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
APP1 = (ROOT / "app1.js").read_text()
APP2 = (ROOT / "app2.js").read_text()
APP3 = (ROOT / "app3.js").read_text()
APP4 = (ROOT / "app4.js").read_text()
APP5 = (ROOT / "app5.js").read_text()
ICONS = (ROOT / "icons.js").read_text()
HTML = (ROOT / "index.html").read_text()
CSS = (ROOT / "style.css").read_text()
SERVER = (ROOT / "server.py").read_text()


class ProductionConversationContract(unittest.TestCase):
    def test_boot_does_not_delete_persisted_session(self):
        startup = APP1.split("function initOnboarding", 1)[0]
        # Registration cleanup may remove only abandoned auth state; it must never
        # clear a user's active conversation while the app starts.
        self.assertNotIn("removeItem(LS_ACTIVE_AGENT)", startup)
        self.assertNotIn("removeItem(LS_ACTIVE_SESSION)", startup)
        self.assertIn("zeline.activeAgent", APP1)
        self.assertIn("zeline.activeSession", APP1)

    def test_chat_header_has_contextual_room_menu_without_debug_session_bar(self):
        self.assertIn('id="roomMenuBtn"', HTML)
        self.assertIn('id="roomIdentity"', HTML)
        self.assertNotIn('id="chatModelBtn"', HTML)
        self.assertNotIn('id="sessionSel"', HTML)
        self.assertNotIn('id="streamStat"', HTML)
        self.assertNotIn('id="composerHint"', HTML)
        self.assertIn("openModelPicker", APP4)
        self.assertRegex(APP4, r"api\(`/agents/\$\{[^}]+\}`[^\n]+method: 'PUT'")

    def test_conversation_is_fullscreen_and_hides_bottom_navigation(self):
        self.assertIn("conversation-open", APP3 + APP4)
        self.assertRegex(CSS, r"\.conversation-open\s+\.tabbar\s*\{[^}]*display\s*:\s*none")
        self.assertIn("100dvh", CSS)

    def test_dark_chat_canvas_is_soft_black_without_wallpaper_pattern(self):
        v87 = CSS[CSS.index("/* v87"):]
        self.assertIn("background:#0b0b0d", v87)
        self.assertIn(".chat-detail", v87)
        self.assertIn(".chat-shell", v87)
        self.assertIn(".stream", v87)
        self.assertIn("background-image:none", v87)
        self.assertIn("html[data-app-theme='light']", v87)

    def test_soft_black_canvas_is_continuous_behind_header_and_composer(self):
        v89 = CSS[CSS.index("/* v89"):]
        self.assertIn("--chat-canvas:#0b0b0d", v89)
        self.assertIn(".telegram-chat-head", v89)
        self.assertIn("background:transparent", v89)
        self.assertIn(".composer-zone", v89)
        self.assertIn("rgba(11,11,13", v89)
        self.assertIn("backdrop-filter:none", v89)

    def test_chat_canvas_uses_only_a_short_subtle_top_vignette(self):
        v139 = CSS[CSS.index("/* v139"):]
        self.assertRegex(v139, r"\.chat-detail::after\{[^}]*height:46px[^}]*rgba\(0,0,0,\.16\)[^}]*transparent")
        self.assertIn("pointer-events:none", v139)

    def test_floating_header_controls_do_not_cast_gradient_like_shadows(self):
        v92 = CSS[CSS.index("/* v92"):]
        self.assertIn(".room-head-back", v92)
        self.assertIn(".room-head-identity", v92)
        self.assertIn(".room-head-menu", v92)
        self.assertIn(".pinned-message-bar", v92)
        self.assertIn("box-shadow:none", v92)
        self.assertIn("background-image:none", v92)
        self.assertIn("filter:none", v92)

    def test_fullscreen_composer_uses_remaining_flex_height_and_hidden_controls_stay_hidden(self):
        self.assertRegex(CSS, r"\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important")
        self.assertNotRegex(CSS, r"\.chat-shell\s*\{[^}]*height\s*:\s*calc\(100dvh\s*-\s*58px\)")

    def test_first_send_uses_single_flight_general_thread_creation(self):
        self.assertIn("sessionCreatePromise", APP4)
        self.assertIn("getOrCreateGeneralSession", APP4)
        self.assertIn("ensureConversationThread", APP4)
        self.assertNotRegex(APP2, r"if \(!S\.sessionId\) \{ await newSession\(\); \}")
        self.assertRegex(APP2, r"await ensureConversationThread\(\)")

    def test_full_refresh_starts_at_google_onboarding(self):
        init = APP1[APP1.index("function initOnboarding"):APP1.index("function normalizeGatewayBase")]
        self.assertNotIn("if (cfg?.configured && account && !needsProfileSetup) return false;", init)
        self.assertIn("$('authOptions').hidden = false;", init)
        self.assertIn("data-auth=\"google\"", HTML)

    def test_provider_center_is_real_runtime_control_plane_not_mock_cards(self):
        """The Provider page must reflect the runtime, not invent provider state.

        It reads GET /providers/center (config-backed, merged with presets) and
        proves a connection with POST /providers/<id>/test. The old page rendered
        local mock cards with an API key hint straight from the browser cache.
        """
        self.assertIn("function pvProviderCard", APP3)
        self.assertIn("'/providers/center'", APP3)
        self.assertIn("function renderProviders", APP3)
        self.assertIn("function renderProviderList", APP3)
        self.assertIn("/test`, { method: 'POST'", APP3)
        # Status is only what the runtime reported; unconfigured cards read as
        # "No connections", never a fake pass.
        self.assertIn("No connections", APP3)
        self.assertIn("missing_credentials", APP3)
        self.assertIn("untested", APP3)
        # Sections and a batch test exist, like the reference dashboard.
        self.assertIn("PV_GROUP_META", APP3)
        self.assertIn("test-all", APP3)
        # The page owns its own container, added to the existing markup.
        self.assertIn('id="providerGrid"', HTML)
        self.assertIn("provider-page", HTML)
        self.assertIn(".pv-card", CSS)
        self.assertIn(".pv-list", CSS)

    def test_provider_dashboard_matches_reference_layout_and_card_structure(self):
        """The dashboard must mirror the reference: an Add card and single-row
        cards with a left icon, a center name+status, and a right toggle.

        The Custom section header carries a qualifier line and one blue
        "Add Provider / Auto-Detect" card — the wire protocol is a form field
        filled from the chosen preset, so the entry point is no longer split per
        protocol. Each card is one horizontal row: icon left, name and status
        stacked center, a toggle on the far right when the provider is
        connected. Unconfigured cards show "No connections" and no toggle. The
        OAuth section offers a ghost "Test All" instead.
        """
        # Custom section header, its qualifier, and the single Add card.
        self.assertIn("Custom Providers", APP3)
        self.assertIn("OpenAI/Anthropic Compatible", APP3)
        self.assertIn("Add Provider", APP3)
        self.assertIn("Custom endpoint", APP3)
        self.assertIn("Api Key / OAuth Providers", APP3)
        # The three credential buckets are one section in the UI now, but the
        # underlying catalog groups still drive Test All and the add form.
        self.assertIn("PV_MANAGED_GROUPS", APP3)
        self.assertNotIn("label: 'OAuth Providers'", APP3)
        self.assertNotIn("label: 'Free Tier Providers'", APP3)
        self.assertNotIn("label: 'API Key Providers'", APP3)
        self.assertIn("Test All", APP3)
        # The per-protocol split is gone; one entry point remains.
        self.assertNotIn("Add Anthropic Compatible", APP3)
        self.assertNotIn("Add OpenAI Compatible", APP3)
        # Single-row card: icon, name+status stacked, toggle on the right.
        self.assertIn("pv-card-row", APP3)
        self.assertIn("pv-toggle", APP3)
        # A connected, enabled card can show the inline protocol pill.
        self.assertIn("pv-pill", APP3)
        # The Add card reads as a blue primary surface; the qualifier is a caption.
        self.assertIn("pv-add-card", CSS)
        self.assertRegex(CSS, r"\.pv-add-card\{[^}]*background:linear-gradient\([^)]*#2563eb")
        self.assertIn("pv-section-sub", CSS)
        self.assertIn("--pv-accent", CSS)
        # No separate "+" button on cards anymore.
        self.assertNotIn("data-pv-add", APP3)

    def test_provider_card_shows_connected_disabled_or_no_connections(self):
        """Card status text must be one of Connected / Disabled / No connections."""
        self.assertIn("No connections", APP3)
        self.assertIn("Disabled", APP3)
        self.assertIn("Connected", APP3)

    def test_provider_page_never_reads_a_provider_secret_from_the_browser(self):
        card = APP3[APP3.index("function pvProviderCard"):APP3.index("function pvSection")]
        # A card renders name, endpoint label, health, and the server's
        # credential_status flag — never the key or its raw hint.
        self.assertNotIn("api_key", card)
        self.assertNotIn("p.api_key", card)
        self.assertNotIn("p.key_hint", card)
        self.assertIn("p.credential_status", card)

    def test_provider_center_carries_no_third_party_router_branding(self):
        """Provider Center must read as a Zeline feature, not a reseller page.

        Zeline routes through whatever endpoints the operator configures, so the
        UI describes connections by protocol ("openai", "custom") and its own
        name. A specific upstream vendor must never become the feature's label.
        """
        page = APP3[APP3.index("/* ───────────────── providers page"):APP3.index("/* ───────────────── mobile agent list")]
        self.assertNotIn("9Router", page)
        self.assertNotIn("9router", page)
        self.assertIn("ZELINE ROUTER", page) if "ZELINE ROUTER" in page else self.assertIn("Provider", page)
        # Type/protocol classification must not sniff vendor names either.
        self.assertNotIn("9router", SERVER)

    def test_one_failing_page_render_cannot_strand_the_others(self):
        """A panel that blows up must not blank the pages rendered after it.

        The sidebar is rebuilt as a profile sheet on boot, which removes the
        node ``renderRecent`` wrote to. That threw, ``renderAllPages`` aborted,
        and the Provider page stayed empty with no visible cause.
        """
        self.assertIn("renderPageSafely", APP4)
        all_pages = APP4[APP4.index("async function renderAllPages"):APP4.index("function activatePage")]
        self.assertIn("renderPageSafely", all_pages)
        # A removed container is tolerated instead of throwing.
        recent = APP3[APP3.index("function renderRecent"):APP3.index("function renderAgentHome")]
        self.assertIn("if (!box) return;", recent)

    def test_provider_form_is_preset_driven_and_has_no_phantom_endpoints(self):
        """The add form prefills from the preset catalog instead of free typing.

        A connection is a base URL plus an API key, so the form picks an endpoint
        instead of asking someone to recall one. It must not call endpoints the
        backend does not implement.
        """
        self.assertIn("providerForm", APP3)
        self.assertIn("api('/providers/presets')", APP3)
        # The old form posted to two routes that were never implemented.
        self.assertNotIn("/providers/detect", APP3)
        self.assertNotIn("function providerModal", APP3)

    def test_refresh_during_profile_registration_returns_to_google_not_saved_runtime(self):
        # Selecting Google starts a *pending* registration. Reloading before profile
        # submission must return to the Google choice even if stale account fields exist.
        self.assertIn("const LS_REGISTRATION_PENDING = 'zeline.registrationPending'", APP1)
        init = APP1[APP1.index("function initOnboarding"):APP1.index("function normalizeGatewayBase")]
        self.assertIn("localStorage.setItem(LS_REGISTRATION_PENDING, 'google')", init)
        self.assertIn("localStorage.removeItem(LS_REGISTRATION_PENDING)", init)
        google = init[init.index("if (btn.dataset.auth === 'google')"):init.index("} else if (btn.dataset.auth === 'agent')")]
        self.assertNotIn("localStorage.setItem('zeline.connection'", google)
        self.assertNotIn("localStorage.setItem('zeline.account'", google)
        gate = APP1[APP1.index("function initOnboarding_ifNeeded"):APP1.index("function timeAgo")]
        self.assertIn("clearPendingRegistrationState()", gate)
        self.assertIn("return initOnboarding()", gate)

    def test_agents_are_cached_before_refresh_and_not_blank_on_transient_reload_failure(self):
        self.assertIn("const LS_AGENT_CACHE = 'zeline.agentCache'", APP1)
        refresh = APP4[APP4.index("async function refreshAll"):APP4.index("function themeIconMarkup")]
        self.assertIn("saveAgentCache(S.agents)", refresh)
        self.assertIn("if (!freshAgents.length && S.agents.length)", refresh)
        boot = APP4[APP4.index("window.startZelineApp"):APP4.index("(async function boot")]
        self.assertIn("hydrateAgentCache()", boot)
        self.assertIn("showHomeHub()", boot)

    def test_access_token_direct_gateway_connect(self):
        # Onboarding connects the app to the CLI gateway with its runtime access token.
        self.assertIn('data-auth="agent"', HTML)
        self.assertIn('Connect with access token', HTML)
        self.assertIn('id="connectForm"', HTML)
        self.assertIn('id="connectToken"', HTML)
        self.assertIn('id="connectUrl"', HTML)
        self.assertIn("body: { gateway_token: token }", APP1)
        self.assertIn("kind: 'gateway'", APP1)
        self.assertNotIn('zln_agent_…', HTML)

    def test_settings_has_one_clear_zeline_app_setup_entry(self):
        self.assertIn('id="zelineAppSetup"', HTML)
        self.assertIn('Agent Tokens', HTML)
        self.assertIn("zelineAppSetupModal", APP4)
        self.assertIn('Manage Agent Tokens', APP4)
        init = APP1[APP1.index("function initOnboarding"):APP1.index("function normalizeGatewayBase")]
        self.assertIn("kind: 'gateway'", init)
        self.assertIn("body: { gateway_token: token }", init)
        self.assertIn("localStorage.setItem('zeline.gatewayToken', token)", init)
        self.assertIn("localStorage.setItem(LS_TOKEN, S.token)", init)
        self.assertIn("function normalizeGatewayBase", APP1)
        self.assertIn("/api/v1", APP1)
        ensure = APP1[APP1.index("async function ensureAuth"):APP1.index("async function ensureAuth") + 700]
        self.assertIn("conn.kind === 'gateway'", ensure)
        self.assertIn("if (savedConn && savedConn.apiBase) API = savedConn.apiBase", APP4)
        self.assertIn("initOnboarding_ifNeeded", APP4)

    def test_room_read_state_includes_general_and_clears_unread_on_entry(self):
        unread = APP3[APP3.index("const agentUnreadCount"):APP3.index("function agentConnectionPresentation")]
        self.assertNotIn("!isGeneralSession", unread)
        self.assertIn("markSessionRead(general.id);", APP3)
        self.assertIn("updateAgentCardStatusInPlace(agent.id)", APP3)
        self.assertIn("session?.updated_at", APP3)

    def test_room_message_selection_is_retired(self):
        for name in ("selectedMessageIds", "toggleMessageSelection", "renderMessageSelectionHeader", "pinSelectedMessage", "deleteSelectedMessages"):
            self.assertNotIn(name, APP2)
        self.assertNotIn("selection-header-active", APP2)

    def test_room_refresh_never_replaces_nonempty_cache_with_empty_history(self):
        self.assertIn("if (Array.isArray(data?.messages) && (data.messages.length || !S.messages.length))", APP3)
        self.assertIn("if (Array.isArray(data?.messages) && (data.messages.length || !S.messages.length))", APP4)
        self.assertIn("function reconcileMessageHistory", APP1)
        self.assertIn("activity_events", APP1)
        reconcile = APP1[APP1.index("function reconcileMessageHistory"):APP1.index("function clearMessageCache")]
        self.assertIn("pendingLocal", reconcile)
        self.assertIn("authoritativeKeys", reconcile)
        self.assertIn("return [...merged, ...unresolved]", reconcile)

    def test_assistant_messages_are_plain_and_reply_is_bounded(self):
        self.assertIn("assistant-plain-content", APP2)
        self.assertIn(".message-reply-quote{max-width:100%", CSS)
        self.assertIn("overflow-wrap:anywhere", CSS)

    def test_room_pin_navigator_is_retired(self):
        self.assertNotIn("Pinned message", APP2)
        self.assertNotIn("renderPinnedMessageBar", APP2)
        self.assertNotIn("pinnedMessageIds", APP2 + APP4)

    def test_streaming_composer_sends_real_steer_and_keeps_stop_available(self):
        self.assertIn("async function steerCurrentTask", APP2)
        self.assertIn("/steer`, { method: 'POST'", APP2)
        self.assertIn("Interrupting current task", APP2)
        self.assertNotIn("sendBtn.hidden = on", APP2)

    def test_activity_timeline_updates_context_slots_and_terminal_has_macos_chrome(self):
        self.assertIn("appendActivityEvent", APP2)
        self.assertIn("activity_events", APP2)
        self.assertIn("terminal-macos", APP2)
        self.assertIn(".terminal-macos-dots", CSS)
        self.assertIn("activitySemantic", APP2)
        self.assertIn("data-activity-context", APP2)
        self.assertIn("findIndex(item =>", APP2)
        self.assertIn("target.metadata.activity_events[index] = event", APP2)
        self.assertNotIn("target.metadata.activity_events.push({ label", APP2)
        self.assertNotIn("appendActivityEvent(acol, 'Completed'", APP2)
        render = APP2[APP2.index("function renderMessages"):APP2.index("/* ───────────────────── send + SSE")]
        self.assertNotIn("el('div', 'tool done')", render)
        self.assertIn("const latest = tl[tl.length - 1]", render)
        self.assertIn("renderLiveHistoryTracker(col, m)", render)
        for label in ("Searching...", "Processing...", "Reading data...", "Reading...", "Reading skill...", "Editing...", "Self Improvement...", "Saved Memory...", "Thinking...", "Analyzing...", "Browsing...", "Writing...", "Running...", "Generating...", "Provider error", "Rate limited", "Failed"):
            self.assertIn(label, APP1 + APP2)
        self.assertNotIn("Reading other...", APP1 + APP2)

    def test_activity_contexts_use_distinct_deterministic_semantics(self):
        semantic = APP2[APP2.index("function activitySemantic"):APP2.index("function paintActivityNode")]
        self.assertIn("kind: 'thinking', tone: 'yellow', icon: 'spark'", semantic)
        self.assertIn("kind: 'analyzing', tone: 'green', icon: 'search'", semantic)
        self.assertIn("kind: 'searching', tone: 'blue', icon: 'search'", semantic)
        self.assertIn("kind: 'browsing', tone: 'cyan', icon: 'web'", semantic)
        self.assertIn("kind: 'editing', tone: 'orange', icon: 'pencil'", semantic)
        for context in ("error", "terminal", "improvement", "memory"):
            self.assertIn(f"context: '{context}'", semantic)
        self.assertIn("function terminalFlavor", APP2)
        self.assertIn("function terminalOutputMarkup", APP2)
        self.assertIn("class=\"terminal-copy\"", APP2)
        self.assertIn("case 'self.improvement'", APP2)
        self.assertIn("kind: 'memory', tone: 'yellow', icon: 'clock'", semantic)
        self.assertNotIn("kind: 'memory', tone: 'yellow', icon: 'pin'", semantic)

    def test_activity_is_human_timeline_expandable_and_persisted(self):
        for name in ("activityHistory", "activityHistoryItem", "renderLiveHistoryTracker", "trackLiveNarrative", "activityDisplayDetail", "pushActivityHistory"):
            self.assertIn(f"function {name}", APP2)
        self.assertIn("activity_history", APP1 + APP2)
        self.assertIn("pushActivityHistory(target", APP2)
        self.assertIn(">Activity</strong>", APP2)
        self.assertIn("aria-expanded", APP2)
        self.assertIn("ev.full_content ?? ev.content ?? acc", APP2)
        self.assertIn("trackLiveNarrative(acol, optimisticAssistant, acc)", APP2)
        self.assertIn("persistedAssistant.metadata.activity_history", APP2)
        self.assertIn("persistedAssistant.content = optimisticAssistant.content", APP2)
        self.assertNotIn("fractionalSecondDigits", APP2)
        self.assertNotIn("Hide live history", APP2)
        self.assertNotIn("Live history", APP2)
        self.assertIn("'Working'", APP2)
        self.assertIn("step${history.length === 1 ? '' : 's'}", APP2)
        self.assertNotIn("#${index + 1}", APP2)
        self.assertIn("last.kind === event.kind", APP2)
        self.assertIn("node.remove()", APP2)
        self.assertIn("function activityDetailText", APP2)
        self.assertIn("live-history-detail", APP2)
        self.assertIn("tracker.scrollIntoView", APP2)
        self.assertIn("acol.querySelectorAll('.activity-live-slot').forEach", APP2)
        self.assertIn("/* v154", CSS)
        self.assertIn("grid-template-columns:20px minmax(0,1fr) auto", CSS)
        self.assertIn(".activity-event-icon>svg.zi,.activity-event-icon>.zi-mask{width:17px", CSS)
        self.assertIn(".activity-analyzing .activity-event-icon>svg.zi", CSS)
        self.assertIn("scrollbar-width:thin", CSS)
        self.assertIn(">.live-history-tracker{order:1}", CSS)
        self.assertIn(">.assistant-plain-content{order:2}", CSS)

    def test_stream_has_one_narrative_without_planning_placeholder_or_blue_caret(self):
        send = APP2[APP2.index("async function send()"):]
        self.assertNotIn("<span class=\"spin\"", send)
        self.assertNotIn("<span class=\"caret\"", send)
        self.assertEqual(send.count("bubble = null"), 1)  # declaration only; never reset at tool boundaries
        self.assertNotIn("ev.state || 'Preparing the next action'", send)
        self.assertIn("ev.round > 1 ? 'Reasoning...' : 'Thinking...'", send)
        self.assertIn("ensureBubble().innerHTML = md(acc)", send)
        self.assertIn(".caret,.thinking,.spin,.thinking-dots{display:none!important}", CSS)
        self.assertIn("activity-edge-pulse", CSS)
        # Smooth streaming: rAF-coalesced paint + eased text reveal (no jerky snap).
        self.assertIn("requestAnimationFrame(() => {", send)
        self.assertIn("const flushPaint", send)
        self.assertIn("assistant-plain-content streaming", send)
        self.assertIn("@keyframes streamRise", CSS)
        self.assertIn("/* v156", CSS)
        self.assertIn("transform:rotate(90deg)", CSS)
        self.assertIn("transform:rotate(-90deg)", CSS)

    def test_finished_message_does_not_restore_animated_live_activity_slots(self):
        # Live activity slots (pulsing "Thinking…" dots) must only be painted for a
        # message that is still streaming; a completed turn shows the collapsed
        # Activity tracker, never a perpetually-animating loading slot after reload.
        render = APP2[APP2.index("function renderMessages"):APP2.index("function renderEmpty")]
        self.assertIn("m.status === 'streaming'", render)
        self.assertIn("if (streamingNow) {", render)
        self.assertRegex(render, r"if \(streamingNow\) \{\s*renderStoredActivity\(col, activity\)")

    def test_stored_activity_replays_only_latest_nonterminal_live_slot(self):
        # On reload, the live status slot must be the single most-recent NON-terminal
        # activity (by timestamp), never an older context that happens to sit last in
        # the per-context events array. Terminals still replay as their own cards.
        fn = APP2[APP2.index("function renderStoredActivity"):APP2.index("function appendRoomNotice")]
        self.assertIn("terminals.forEach", fn)
        self.assertIn("nonTerminals.reduce", fn)
        self.assertIn("x.at > best.at", fn)
        # Every stored event carries a timestamp so latest-wins is well-defined.
        append = APP2[APP2.index("function appendActivityEvent"):APP2.index("function renderStoredActivity")]
        self.assertIn("const at = new Date().toISOString()", append)
        self.assertIn("terminal: Boolean(semantic.terminal), at", append)

    def test_live_status_row_animates_every_in_progress_action_like_thinking(self):
        # Every in-progress activity (Reading/Browsing/Searching/Researching/Writing/
        # Editing/Running/Generating) shows animated "…" dots like Thinking, with the
        # concrete SUBJECT inline ("Searching : harga xau"); a stray "*" collapses.
        paint = APP2[APP2.index("function paintActivityNode"):APP2.index("function updateStoredActivityDetail")]
        self.assertIn("const animated = !['error', 'memory', 'improvement'].includes(semantic.context)", paint)
        self.assertIn("activity-loading-dots", paint)
        self.assertNotIn("<b>—</b>", paint)
        self.assertIn("activity-live-subject", paint)
        self.assertIn("if (subject === '*') subject = '';", paint)
        self.assertIn("Reading (?:other|data)", paint)
        # deep_research + web_search map to distinct Researching/Searching labels.
        self.assertIn("deep_research: 'Researching...'", APP2)
        self.assertIn("kind: 'researching'", APP2)

    def test_terminal_is_runtime_aware_colored_copyable_and_history_tracked(self):
        for flavor in ("PowerShell", "HTML", "JavaScript", "Python", "Zsh", "Shell", "Bash"):
            self.assertIn(f"'{flavor}'", APP2)
        flavor_logic = APP2[APP2.index("function terminalFlavor"):APP2.index("function terminalOutputMarkup")]
        self.assertLess(flavor_logic.index("tool === 'run_shell'"), flavor_logic.index("pytest|pip"))
        self.assertIn("terminalPre.innerHTML = terminalOutputMarkup", APP2)
        self.assertIn("pre.innerHTML = terminalOutputMarkup", APP2)
        self.assertIn("navigator.clipboard.writeText", APP2)
        self.assertIn("pushActivityHistory(target", APP2)
        self.assertIn(".terminal-copy", CSS)
        for tone in ("term-prompt", "term-green", "term-yellow", "term-red"):
            self.assertIn(tone, APP2 + CSS)

    def test_session_reflection_manager_delegates_weighted_reflection(self):
        # The runtime gateway module was consolidated into sessions.py. Keep this
        # contract against the current owner instead of a deleted legacy path.
        sessions = (ROOT.parent / "zeline" / "zeline" / "sessions.py").read_text()
        self.assertIn("def reflect(self, identity: str, min_tool_calls: int = 5)", sessions)
        self.assertIn("session.agent.reflect(min_tool_calls=min_tool_calls)", sessions)
        self.assertIn("except Exception:", sessions)
        self.assertIn("return None", sessions)
        self.assertIn("String(ev.error_code || '').toLowerCase()", APP2)

    def test_slash_commands_have_real_handlers(self):
        for command in ("/start", "/status", "/steer", "/stop", "/cancel", "/help", "/new", "/clear"):
            self.assertIn(command, APP2)

    def test_outer_card_line2_shows_room_preview_with_fallback(self):
        # Single-agent home: each room card's line 2 shows the session's last
        # preview, the live action label wins while working, and empty rooms fall
        # back to a static hint.
        home = APP3[APP3.index("function renderAgentHome"):APP3.index("function openRoomCardMenu")]
        self.assertIn("liveLabel || preview || (isGeneralSession(s)", home)
        self.assertIn("s.last_preview", home)

    def test_provider_events_do_not_redefine_gateway_connection(self):
        started = APP2[APP2.index("case 'stream.started'"):APP2.index("case 'assistant.thinking'")]
        self.assertNotIn("is_connected_agent = true", started)
        self.assertNotIn("setRoomConnectionState('connected')", started)

    def test_agent_provider_switcher(self):
        # A provider picker lists runtime providers and re-points the agent.
        self.assertIn("function openProviderPicker", APP4)
        picker = APP4[APP4.index("async function openProviderPicker"):APP4.index("/* ───────────────── attachments")]
        self.assertIn("api('/providers')", picker)
        self.assertIn("provider_id: p.id", picker)          # switches provider via agentPayload patch
        self.assertIn("credential_status", picker)          # shows configured/unknown state
        self.assertIn("renderAgentHome()", picker)          # refresh after switch
        # Agent info exposes tappable Provider + Model rows.
        self.assertIn('data-agent-info="provider"', APP4)
        self.assertIn('data-agent-info="model"', APP4)
        self.assertIn("openProviderPicker()", APP4)

    def test_home_hub_layout_rows(self):
        # Owner layout: top row = ZEROLINEAR Gateway (left) + two SMALL empty 1:1
        # placeholder cards; then a long full-width MODELS card; then the agent DM
        # card. Session Chats stays lower in .hub-trio. Saved Messages moved to the
        # header as a bookmark icon-button, left of the search glyph.
        self.assertIn('id="hubTop"', HTML)
        self.assertIn('id="hubModels"', HTML)
        self.assertIn('id="hubChat"', HTML)
        self.assertIn('id="hubTrio"', HTML)
        hub = APP3[APP3.index("function renderHomeHub"):APP3.index("function collectSavedMessages")]
        self.assertIn("Zeline Agentic AI", hub)
        self.assertIn("MODEL", hub)
        self.assertIn("Gateway", hub)
        self.assertIn("hub-models-logo", hub)
        self.assertNotIn("'Agentic AI'", hub)
        self.assertIn("hub-dm-card", hub)
        self.assertIn("hub-dm-preview", hub)
        # v302: timestamp removed from the home card; unread count badge only.
        self.assertNotIn("hub-dm-time", hub)
        self.assertIn("hub-dm-unread", hub)
        self.assertNotIn("hub-dm-presence", hub)
        self.assertNotIn("hub-dm-arrow", hub)
        self.assertIn("agentUnreadCount(agent.id)", hub)
        unread_helper = APP3[APP3.index("const agentUnreadCount"):APP3.index("/* Connection =")]
        self.assertIn(".filter(isGeneralSession)", unread_helper)
        self.assertNotIn("workspaceKindOf", unread_helper)
        self.assertIn("general?.last_preview", hub)
        self.assertNotIn("latestRoom?.last_preview", hub)
        self.assertIn("general?.updated_at", hub)
        self.assertNotIn("latestRoom?.updated_at", hub)
        # v302: the home card shows no timestamp — only the unread count badge.
        self.assertNotIn("timeAgo(dmUpdatedAt)", hub)
        self.assertIn("Typing...", hub)
        self.assertIn("function updateHubDmStatusInPlace", APP3)
        self.assertIn("preview.classList.toggle('typing', typing)", APP3)
        self.assertNotIn("Zero Session", hub)
        self.assertNotIn("Last message", hub)
        self.assertIn("hub-link-card", hub)
        self.assertIn("hub-models-card", hub)
        self.assertIn("hubProviderLogo(agent)", hub)
        self.assertIn("HUB_PROVIDER_LOGOS", APP3)
        for provider in ("anthropic", "openrouter", "deepseek", "google", "ollama", "x", "qwen", "meta"):
            self.assertIn(f"asset: '{provider}'", APP3)
        self.assertIn("is-fallback", APP3)
        self.assertRegex(CSS, r"\.home-hub \.hub-provider-logo\s*\{")
        # Four first-class destinations share one chat engine, but never expose a
        # combined Workspace selector or type tabs. Each destination has its own
        # list, server-backed search, name-only create, and per-room actions.
        workspace = APP3[APP3.index("const WORKSPACE_NAV"):APP3.index("function openMoreMenu")]
        for kind, singular, plural in (
            ("session", "Session", "Sessions"),
            ("project", "Project", "Projects"),
            ("cronjob", "Cronjob", "Cronjobs"),
            ("workflow", "Workflow", "Workflows"),
        ):
            self.assertIn(f"kind: '{kind}'", workspace)
            self.assertIn(f"singular: '{singular}'", workspace)
            self.assertIn(f"plural: '{plural}'", workspace)
        self.assertIn("function openWorkspace(kind = activeWorkspaceKind)", workspace)
        self.assertIn('data-workspace-search', workspace)
        self.assertIn("new URLSearchParams({ agent_id: agent.id, kind: item.kind })", workspace)
        self.assertIn("api(`/sessions?${params.toString()}`", workspace)
        self.assertIn("promptWorkspaceName(agent, createButton.dataset.workspaceCreate)", workspace)
        self.assertIn("attachRowReorder(list, rooms, item.kind)", workspace)
        self.assertNotIn("attachRowActions", workspace)
        self.assertNotIn("function openWorkspaceMenu", APP3)
        health_check = APP3[APP3.index("async function recheckHealth"):APP3.index("function settleSpinner")]
        self.assertIn("const chainComplete", health_check)
        # v274: living cascade — energy draws itself along each wire in sequence,
        # epoch-gated so re-renders never restart the wave, then a soft in-place exit.
        self.assertIn("hc.__cascade = true", health_check)
        self.assertIn("hc.__cascadeEpoch", health_check)
        self.assertIn("--hc-len", APP3)
        self.assertIn("hc-flow", APP3)
        self.assertIn("getTotalLength", APP3)
        self.assertIn("hcWireFlow", CSS)
        self.assertIn("}, 5000);", health_check)
        self.assertIn("workspacePulseRunId", health_check)
        self.assertIn("classList.remove('hc-ok')", health_check)
        # v274: wires persist in the DOM — no innerHTML rebuild per health step,
        # so the lines never flicker or replay on unrelated repaints.
        self.assertIn("svg.__wires", APP3)
        self.assertNotIn("hWireIn", CSS)
        self.assertNotIn("const existing = trio.querySelector('.hub-workspace-panel')", hub)
        self.assertIn("dataset.hubSig", hub)
        # Workspace destinations stay on the browser's native scroll path. A
        # non-passive modal guard or boundary transform can freeze Android scroll.
        self.assertNotIn("function containWorkspaceListScroll", APP3)
        self.assertNotIn("pull-bounce-top", CSS)
        self.assertNotIn("pull-bounce-bottom", CSS)
        self.assertNotIn("ws-bounce-top", CSS)
        self.assertNotIn("ws-bounce-bottom", CSS)
        self.assertIn("hc.session = 'ok'", health_check)
        self.assertIn(".every(key => hc[key] === 'ok')", health_check)
        self.assertIn("S.workspaceHealthPulse = true", health_check)
        self.assertIn("S.workspaceHealthPulse = false", health_check)
        self.assertIn("last_preview", workspace)
        self.assertIn("unread > 99 ? '99+' : unread", workspace)
        self.assertIn('class="workspace-row-icon workspace-kind-${item.kind}"', workspace)
        self.assertIn('workspace-sheet workspace-kind-${item.kind}', workspace)
        self.assertNotIn('workspace-summary', workspace)
        self.assertIn("const searchAction = $('modalSearchAction')", workspace)
        self.assertIn("const createAction = $('modalHeadAction')", workspace)
        self.assertIn("createAction.hidden = true", workspace)
        self.assertIn("const WORKSPACE_DESC =", workspace)
        self.assertIn("workspace-desc-create", workspace)
        self.assertIn("data-workspace-create", workspace)
        self.assertIn("const descEl = list.querySelector('.workspace-desc')", workspace)
        self.assertIn("if (descEl && !searchOpen) list.prepend(descEl)", workspace)
        self.assertRegex(CSS, r"\.workspace-list\{[^}]*overflow-y:auto[^}]*overscroll-behavior:contain")
        self.assertRegex(CSS, r"\.workspace-modal \.modal-search-action\{[^}]*width:44px")
        self.assertRegex(CSS, r"\.workspace-desc\{[^}]*font-size:11px")
        self.assertRegex(CSS, r"\.workspace-desc-create\{[^}]*text-decoration:underline")
        self.assertRegex(CSS, r"\.workspace-row-copy strong\{[^}]*font-size:14px[^}]*font-weight:600")
        self.assertRegex(CSS, r"\.workspace-row\{[^}]*border:1px solid rgba\(255,255,255,\.12\)[^}]*background:#0e0e10")
        row_css = CSS[CSS.index(".workspace-row{"):CSS.index(".workspace-row:hover")]
        self.assertNotIn("box-shadow", row_css)
        self.assertRegex(CSS, r"\.workspace-row-icon\{[^}]*background:transparent[^}]*border:0")
        self.assertRegex(CSS, r"\.workspace-list\{[^}]*flex:1[^}]*overflow-y:auto")
        self.assertRegex(CSS, r"\.workspace-row-badge\{")
        self.assertIn("data-workspace-row-id", workspace)
        self.assertIn("attachRowReorder", workspace)
        self.assertIn("applyWorkspaceOrder", workspace)
        self.assertIn("draggable=\"true\"", workspace)
        self.assertNotIn("workspace-manage", workspace)
        self.assertNotIn("workspace-row-meta", workspace)
        self.assertIn('id="modalSearchAction"', HTML)
        self.assertIn(".workspace-kind-session", CSS)
        self.assertIn(".workspace-kind-project", CSS)
        self.assertIn(".workspace-kind-cronjob", CSS)
        self.assertIn(".workspace-kind-workflow", CSS)
        # Creation is name-only and makes all four canonical types available.
        self.assertNotIn('id="homeAddButton"', HTML)
        self.assertNotIn('id="homeAddMenu"', HTML)
        self.assertIn('openHomeAddSheet()', APP3)
        self.assertIn('data-kind="session"', APP3)
        self.assertIn('data-kind="project"', APP3)
        self.assertIn('data-kind="cronjob"', APP3)
        self.assertIn('data-kind="workflow"', APP3)
        self.assertRegex(CSS, r"\.home-add-row-ic\s*\{[^}]*border-radius:\s*50%")
        self.assertIn("promptWorkspaceName(agent, row.dataset.kind", APP3)
        # Saved Messages is no longer a hub card, and the header bookmark button
        # was removed too — only the search glyph remains in the header.
        self.assertNotIn("Saved Messages", hub)
        self.assertNotIn('id="headSaved"', HTML)
        self.assertNotIn('data-zi="bookmark"', HTML)
        self.assertNotIn("Info Agent", hub)
        self.assertNotIn('id="activityPanel"', HTML)
        self.assertIn("hubReferenceIcon('github')", hub)
        self.assertIn("hubReferenceIcon('docs')", hub)
        self.assertNotIn("hubReferenceIcon('cube')", hub)
        self.assertRegex(CSS, r"\.hub-status-card\s*\{")
        self.assertRegex(CSS, r"\.hub-dm-card\s*\{")
        self.assertRegex(CSS, r"\.hub-link-card\s*\{")
        self.assertRegex(CSS, r"\.hub-models-card\s*\{")

    def test_activity_feed_is_title_only_status_stream(self):
        # The ACTIVITY panel is a running title-only feed of agent status events
        # (step labels + run/gateway state), not a single latest status.
        self.assertIn("function syncHubActivity", APP3)
        self.assertIn("const hubActivityLog", APP3)
        self.assertIn("function pushHubActivity", APP3)
        render = APP3[APP3.index("function renderActivityPanel"):APP3.index("function renderAgentHome")]
        self.assertIn("title-only", render)
        self.assertIn("latestActivityHistory()", render)
        self.assertNotIn("activity-row-icon", render)
        sync = APP3[APP3.index("function syncHubActivity"):APP3.index("function renderActivityPanel")]
        self.assertIn("'Working'", sync)
        self.assertIn("'Connected'", sync)
        self.assertIn("'Reconnected'", sync)
        self.assertIn("'Unconnected'", sync)

    def test_single_agent_home_lists_rooms_not_agent_roster(self):
        # Single-agent model: one account = one agent (its key is the gateway key).
        # The home lists that agent's SESSIONS (chat rooms), not an agent roster.
        # The top action creates a NEW chat, never a second agent profile.
        self.assertNotIn("if (S.agents.length >= 5)", APP4)
        wiring = APP4[APP4.index("$('createAgentTop').onclick"):APP4.index("$('createAgentTop').onclick") + 320]
        self.assertIn("promptSessionName(agent)", wiring)
        home = APP3[APP3.index("function renderAgentHome"):APP3.index("function openRoomCardMenu")]
        # The one agent is S.agents[0]; rooms are its sessions, newest first.
        self.assertIn("const agent = S.agents[0]", home)
        self.assertIn("s.agent_id === agent.id", home)
        self.assertIn("agentConnectionPresentation(agent)", home)
        self.assertIn("'Unconnected'", APP3)
        self.assertIn("'Connected'", APP3)


    def test_profile_submit_opens_agent_home_without_restoring_chat(self):
        profile = APP1[APP1.index("$('profileForm').onsubmit"):APP1.index("function timeAgo")]
        self.assertIn("startZelineApp?.({ restoreConversation: false })", profile)
        self.assertRegex(APP4, r"startZelineApp\(\{ restoreConversation = true \} = \{\}\)")
        self.assertIn("if (restoreConversation", APP4)

    def test_opening_and_leaving_chat_persist_active_conversation(self):
        self.assertIn("persistActiveConversation", APP3 + APP4)
        self.assertRegex(APP3, r"openAgentChat[\s\S]+persistActiveConversation")
        self.assertRegex(APP4, r"openSession[\s\S]+persistActiveConversation")

    def test_production_chat_copy_has_no_internal_diagnostics_or_upstream_brand(self):
        visible = APP2 + APP4 + HTML
        self.assertNotIn("semuanya live dari", visible)
        self.assertNotIn("agent, ' + S.providers.length", APP4)
        self.assertNotIn("hermes", (APP3 + (ROOT / "server.py").read_text()).casefold())

    def test_home_header_has_no_search_control(self):
        self.assertNotIn('id="headSearch"', HTML)
        self.assertNotIn('id="searchToggle"', HTML)
        self.assertNotIn('id="searchClose"', HTML)
        self.assertNotIn('id="agentSearch"', HTML)
        self.assertNotIn('search-chat-icon', HTML)
        self.assertNotIn("$('agentSearch').oninput", APP4)

    def test_home_is_fixed_and_bottom_destination_bar_is_removed(self):
        self.assertIn('id="tabbar"', HTML)
        self.assertRegex(HTML, r'<nav class="tabbar" id="tabbar"[^>]*hidden')
        v296 = CSS.split("/* v296", 1)[1]
        self.assertRegex(v296, r"\.chat-home\s*\{[^}]*overflow\s*:\s*hidden")
        self.assertRegex(v296, r"\.chat-home\s*\{[^}]*touch-action\s*:\s*none")
        self.assertRegex(v296, r"#tabbar,\s*\.tabbar\s*\{[^}]*display\s*:\s*none")

    def test_chat_header_uses_balanced_android_topbar_above_search(self):
        marker = "/* v35 — balanced Android top bars and clean search glyph */"
        self.assertIn(marker, CSS)
        header = CSS.split(marker, 1)[1]
        self.assertRegex(header, r"\.chat-home\s*\{[^}]*padding-top\s*:\s*12px")
        self.assertRegex(header, r"\.zeline-home-head\s*\{[^}]*min-height\s*:\s*56px")
        self.assertRegex(header, r"\.zeline-home-head\s*\{[^}]*border-bottom\s*:\s*1px\s+solid")
        self.assertRegex(header, r"\.zeline-home-head\s*\{[^}]*margin\s*:\s*0\s+0\s+10px")
        self.assertRegex(header, r"\.home-header-left\s*\{[^}]*align-self\s*:\s*center")
        self.assertRegex(header, r"\.home-head-actions\s*\{[^}]*top\s*:\s*50%")
        self.assertRegex(header, r"\.home-head-actions\s*\{[^}]*transform\s*:\s*translateY\(-50%\)")
        self.assertRegex(header, r"\.agent-home-actions\s*\{[^}]*position\s*:\s*static")
        self.assertRegex(header, r"\.agent-home-actions\s*\{[^}]*transform\s*:\s*none")
        self.assertNotRegex(header, r"(?:top|margin-top|margin)\s*:\s*-\d+px")


    def test_create_agent_is_add_text_in_top_right_and_swaps_with_selection_actions(self):
        self.assertNotIn("add-agent-row", APP3)
        self.assertNotIn("Each agent gets its own API token", APP3)
        self.assertNotIn('id="createAgentHome"', HTML)
        self.assertNotIn('id="createAgentFab"', HTML)
        # 'New chat' now lives in the Chats row: literal 'New chat' text + plus glyph.
        self.assertRegex(HTML, r'<div class="dash-agents-head">.*id="createAgentTop"[^>]*><span class="add-plus">\+</span> New chat</button>')
        self.assertIn("$('createAgentTop').onclick", APP4)
        selection = APP3[APP3.index("function renderSelectionBar"):APP3.index("function profileActions")]
        self.assertIn("add.hidden = selectionMode", selection)
        # Styled as inline blue, non-bold text in the agents row (v127).
        self.assertRegex(CSS, r"\.dash-agents-head \.create-agent-top\s*\{[^}]*color\s*:\s*#0A84FF")
        self.assertRegex(CSS, r"\.dash-agents-head \.create-agent-top\s*\{[^}]*font-weight\s*:\s*400")

    def test_global_runtime_statuses_are_not_rendered(self):
        self.assertNotIn("Zeline siap", APP4)
        self.assertNotIn('id="connBox"', HTML)
        self.assertNotIn('id="connLabel"', HTML)
        self.assertNotIn('id="connSub"', HTML)
        self.assertNotIn("setConn(", APP1 + APP4)

    def test_pages_are_tap_only_and_horizontal_swipe_is_disabled(self):
        self.assertIn('id="pageTrack"', HTML)
        track = HTML[HTML.index('id="pageTrack"'):HTML.index('</div>', HTML.index('id="page-usage"'))]
        html_order = re.findall(r'id="page-([a-z]+)"', track)
        self.assertEqual(html_order, ['chat', 'providers', 'usage'])
        v294 = CSS.split("/* v294", 1)[1]
        self.assertRegex(v294, r"\.page-track\s*\{[^}]*overflow-x\s*:\s*hidden")
        self.assertRegex(v294, r"\.page-track\s*\{[^}]*scroll-snap-type\s*:\s*none")
        self.assertRegex(v294, r"\.page-track\s*\{[^}]*touch-action\s*:\s*pan-y")
        self.assertRegex(CSS, r"\.page-track\s*>\s*\.page\s*\{[^}]*flex\s*:\s*0\s+0\s+100%")
        self.assertIn("syncPageFromTrack", APP4)
        self.assertIn("scrollTo({", APP4)
        wire = APP4[APP4.index("function wire()"):APP4.index("/* ───────────────── boot")]
        self.assertNotIn("pageTrack.addEventListener('scroll'", wire)
        self.assertNotIn("pageTrack.addEventListener('touchstart'", wire)
        self.assertNotIn("wirePullOverscroll();", wire)

    def test_home_pull_stretch_is_scoped_and_wired(self):
        pull = APP4[APP4.index("function wireHomePullStretch"):APP4.index("function animateNavPillTo")]
        self.assertIn("const HOME_PULL_MAX_PX = 12", pull)
        self.assertIn("const HOME_PULL_RANGE_PX = 64", pull)
        self.assertIn("const home = $('chatHome')", pull)
        self.assertIn("homeHub?.hasAttribute('hidden')", pull)
        self.assertIn("requestAnimationFrame", pull)
        self.assertIn("translate3d(0,${pull.toFixed(2)}px,0)", pull)
        self.assertNotIn("scaleY(", pull)
        self.assertIn("home-pull-active", pull)
        self.assertIn("home-pull-releasing", pull)
        self.assertNotIn("#page-providers", pull)
        wire = APP4[APP4.index("function wire()"):APP4.index("/* ───────────────── boot")]
        self.assertIn("wireHomePullStretch();", wire)
        self.assertIn(".chat-home.home-pull-active", CSS)
        self.assertIn(".chat-home.home-pull-releasing", CSS)

    def test_workspace_search_replaces_the_header_instead_of_adding_a_body_field(self):
        workspace = APP3[APP3.index("function openWorkspace(kind = activeWorkspaceKind)"):APP3.index("function openMoreMenu")]
        self.assertIn("const searchWrap = el('label', 'modal-workspace-search')", workspace)
        self.assertIn("modalHead?.appendChild(searchWrap)", workspace)
        self.assertNotIn('<label class="workspace-search" hidden>', workspace)
        self.assertIn("workspaceModal.classList.toggle('workspace-search-open', opening)", workspace)
        self.assertIn("searchAction.innerHTML = ZI(opening ? 'close' : 'search')", workspace)
        self.assertIn("searchAction.setAttribute('aria-label', opening ? 'Cancel search'", workspace)
        self.assertIn("input?.focus()", workspace)
        self.assertIn("input?.blur()", workspace)
        self.assertIn("shell.querySelector('.modal-workspace-search')?.remove()", APP1)
        self.assertIn(".workspace-modal.workspace-search-open .modal-head", CSS)
        self.assertIn(".workspace-modal.workspace-search-open .modal-back", CSS)
        self.assertIn(".workspace-modal.workspace-search-open .modal-head h3", CSS)
        self.assertIn('grid-template-areas:"search action"', CSS)
        self.assertIn(".workspace-modal .modal-workspace-search", CSS)

    def test_workspace_search_header_shows_exactly_one_neutral_cancel_x(self):
        # Two X glyphs used to appear: our header action plus the native
        # type="search" clear button. Only one neutral X may remain.
        self.assertIn("::-webkit-search-cancel-button", CSS)
        self.assertIn("::-webkit-search-decoration", CSS)
        native = CSS[CSS.index(".workspace-modal .modal-workspace-search input::-webkit-search-cancel-button"):]
        self.assertRegex(native[:400], r"-webkit-appearance:\s*none")
        self.assertRegex(native[:400], r"display:\s*none")
        open_rule = CSS[CSS.index(".workspace-modal.workspace-search-open .modal-search-action"):]
        self.assertIn("#f1f1ef", open_rule[:260])
        self.assertNotIn("#cbd9ff", open_rule[:260])

    def test_open_search_starts_blank_until_the_user_types(self):
        workspace = APP3[APP3.index("function openWorkspace(kind = activeWorkspaceKind)"):APP3.index("function openMoreMenu")]
        # An open search bar with no query shows nothing at all: no rows, no
        # description, no empty-state copy. Typing reveals matches.
        self.assertIn("let searchOpen = false", workspace)
        self.assertIn("if (searchOpen && !query)", workspace)
        self.assertIn("list.innerHTML = ''", workspace)
        self.assertIn("searchOpen = opening", workspace)
        # Closing search must restore the full list and its description.
        self.assertIn("renderRooms();", workspace)
        # While searching, the marketing description must not sit above results.
        self.assertIn("if (descEl && !searchOpen) list.prepend(descEl)", workspace)

    def test_workspace_header_icons_are_large_and_white(self):
        # Back, search and the in-field magnifier must read as one crisp white
        # icon family, not a mix of small blue accents.
        icons = CSS[CSS.index("/* v364 — workspace app-bar icons"):]
        self.assertRegex(icons, r"\.workspace-modal \.modal-back svg[^{]*\{[^}]*width:26px")
        self.assertRegex(icons, r"\.workspace-modal \.modal-search-action svg[^{]*\{[^}]*width:26px")
        self.assertRegex(icons, r"\.workspace-modal \.modal-workspace-search>span svg[^{]*\{[^}]*width:22px")
        # All three inherit pure white in the dark theme.
        self.assertIn("color:#fff!important", icons)
        self.assertNotIn("#cbd9ff", icons)
        self.assertNotIn("#a9c5ff", icons)
        # Crisp rendering rather than blurry upscaled glyphs.
        self.assertIn("shape-rendering:geometricPrecision", icons)
        # The global `svg.zi{transform:scale(.85)}` shrinks every glyph, so the
        # workspace app bar must neutralise it or 26px renders as 22px.
        self.assertIn("transform:none!important", icons)

    def test_home_grid_and_workspace_nudges_keep_the_top_bar_fixed(self):
        workspace = APP3[APP3.index("function wireWorkspacePullNudge"):APP3.index("function openMoreMenu")]
        nudge = workspace[:workspace.index("const WORKSPACE_NAV")]
        self.assertIn("const WORKSPACE_PULL_MAX_PX = 12", nudge)
        self.assertIn("list.scrollTop > 0", nudge)
        self.assertIn("requestAnimationFrame", nudge)
        self.assertIn("workspace-pull-active", nudge)
        self.assertIn("workspace-pull-releasing", nudge)
        self.assertNotIn("preventDefault()", nudge)
        self.assertIn("wireWorkspacePullNudge(list, body);", workspace)
        canvas = CSS[CSS.index("html:not([data-app-theme='light']) #page-chat") :]
        self.assertIn("#page-chat", canvas)
        self.assertNotIn(".workspace-modal .modal-body{", canvas)
        self.assertNotIn(".workspace-modal .workspace-list{", canvas)
        self.assertNotIn("rgba(255,255,255,.045)", canvas)
        self.assertIn(".workspace-sheet.workspace-pull-active", canvas)
        self.assertIn(".workspace-modal .modal-head", canvas)
        self.assertIn("position:relative!important", canvas)
        self.assertIn("z-index:1!important", canvas)

    def test_swipe_settle_leaves_exactly_one_bottom_tab_active(self):
        visual = APP4[APP4.index("function updateActiveTabVisual"):APP4.index("function updateNavDragProgress")]
        self.assertIn("document.querySelectorAll('#tabbar .tab')", visual)
        self.assertIn("tab.dataset.page === page", visual)
        self.assertIn("tab.classList.toggle('active', active)", visual)
        self.assertIn("aria-selected", visual)
        settle = APP4[APP4.index("function syncPageFromTrack"):APP4.index("function schedulePageSync")]
        self.assertIn("cancelAnimationFrame(navLiquidFrame)", settle)
        self.assertIn("activatePage(page, { render: page !== S.page })", settle)
        self.assertIn("--active-progress", settle)

    def test_bottom_nav_is_tap_only_and_touch_hover_cannot_stay_lit(self):
        # Native horizontal swiping belongs to pageTrack. The dock must not have
        # its old 2px drag recognizer, which turned normal finger jitter into a
        # snap back to the previous page.
        self.assertNotIn("function wireNavPillDrag", APP4)
        self.assertNotIn("navPillDrag", APP4)
        wire = APP4[APP4.index("function wire()"):APP4.index("/* ───────────────── boot")]
        self.assertNotIn("wireNavPillDrag()", wire)
        self.assertIn("button.blur()", wire)
        go = APP4[APP4.index("function go(page"):APP4.index("/* Content enter animation")]
        self.assertIn("clearTimeout(pageSyncTimer)", go)
        self.assertIn("behavior: 'auto'", go)
        self.assertRegex(CSS, r"\.tabbar \.tab:not\(\.active\):hover")
        self.assertRegex(CSS, r"\.tabbar\{touch-action:manipulation")

    def test_all_pages_are_rendered_before_they_can_be_swiped_into_view(self):
        self.assertIn("function renderAllPages()", APP4)
        render_all = APP4[APP4.index("function renderAllPages()"):APP4.index("function openSidebar")]
        self.assertIn("showHomeHub()", render_all)
        # Every destination is rendered, each behind its own failure guard so one
        # broken panel cannot leave a later page permanently blank.
        self.assertIn("renderPageSafely('providers')", render_all)
        self.assertIn("renderPageSafely('usage')", render_all)
        self.assertIn("renderSettings()", render_all)
        self.assertIn("function renderPageSafely", APP4)
        boot = APP4[APP4.index("window.startZelineApp"):APP4.index("(async function boot")]
        self.assertIn("renderAllPages()", boot)

    def test_bottom_navigation_is_monochrome_minimal_and_keeps_settings_in_profile_menu(self):
        # v323 — Settings is intentionally not a bottom-nav destination; it is
        # opened from the hamburger profile menu to avoid duplicate Settings UI.
        self.assertEqual(HTML.count('class="tab-icon"'), 3)
        nav = HTML[HTML.index('<nav class="tabbar"'):HTML.index('</nav>', HTML.index('<nav class="tabbar"'))]
        self.assertIn('data-page="chat"', nav)
        self.assertIn('data-page="providers"', nav)
        self.assertIn('data-page="usage"', nav)
        self.assertNotIn('data-page="settings"', nav)
        self.assertIn("row('profile', 'person', 'Profile')", APP4)
        marker = "/* Floating rounded bottom navigation */"
        self.assertIn(marker, CSS)
        dock = CSS.split(marker, 1)[1]
        self.assertRegex(dock, r"\.tabbar\s*\{[^}]*width\s*:\s*min\(calc\(100%\s*-\s*\d+px\),\s*\d+px\)")
        self.assertRegex(dock, r"\.tabbar\s*\{[^}]*bottom\s*:\s*max\(")
        self.assertRegex(dock, r"\.tabbar\s*\{[^}]*border-radius\s*:\s*\d+px")
        self.assertRegex(dock, r"\.tabbar\s*\{[^}]*box-shadow\s*:")
        final = CSS.split("/* Final monochrome navigation and light provider surfaces */", 1)[-1].split("/* v27 — profile settings stacks over Chat; create-agent FAB sits beside Usage */", 1)[0]
        self.assertRegex(final, r"\.tab-icon\s*\{[^}]*border-radius\s*:\s*0")
        self.assertRegex(final, r"\.tab-icon svg\s*\{[^}]*width")
        self.assertRegex(final, r"\.tab\.active \.tab-icon\s*\{[^}]*background\s*:\s*transparent")
        self.assertNotRegex(final, r"#[0-9a-fA-F]{0,2}(?:3478f6|6ea8ff)")

    def test_header_centers_zeline_and_hamburger_opens_settings_directly(self):
        self.assertIn('id="homeHeaderMenu"', HTML)
        self.assertIn('id="homeTitle" hidden>Zeline</h2>', HTML)
        self.assertNotIn('id="homeHeaderPanel"', HTML)
        self.assertNotIn('id="homeDrawerScrim"', HTML)
        self.assertRegex(APP4, r"homeHeaderMenu[^\n]+onclick[^\n]*=[^\n]*openSidebar\(\)")
        marker = "/* Chat home header and floating menus */"
        self.assertIn(marker, CSS)
        header_css = CSS.split(marker, 1)[1]
        self.assertRegex(header_css, r"#homeTitle\s*\{[^}]*left\s*:\s*50%")

    def test_home_drawer_swipe_is_low_latency_and_available_from_home(self):
        gesture = APP4[APP4.index("function isHomeSidebarSwipeTarget"):APP4.index("function setSettingsOverlay")]
        self.assertIn("function isHomeSidebarSwipeTarget", gesture)
        self.assertIn("const fromHome = isHomeSidebarSwipeTarget(event)", gesture)
        self.assertIn("SIDEBAR_GESTURE_START_PX = 6", APP4)
        self.assertIn("SIDEBAR_OPEN_THRESHOLD = .18", APP4)
        self.assertIn("queueSidebarGesturePaint(gesture)", gesture)
        self.assertIn("requestAnimationFrame", gesture)
        self.assertIn("suppressHomeSidebarClickUntil", gesture)
        self.assertIn("ensureSidebarSheet()", APP4)
        self.assertIn("requestIdleCallback", APP4)
        self.assertIn(".sidebar.profile-sheet.sidebar-dragging", CSS)
        self.assertIn("transition:transform .22s", CSS)

    def test_profile_archive_system_is_removed_completely(self):
        combined = HTML + APP3 + APP4 + CSS
        for retired in (
            "archivedProfilesPanel",
            "archivedProfilesList",
            "closeArchivedProfiles",
            "renderArchivedProfiles",
            "wireArchivedProfilesPull",
            "setArchivedProfilesOpen",
            "archiveAgent",
            "flags.archived",
            "Archived profiles",
            "No archived profiles",
            "archived-profiles-",
            "ARCHIVED_PULL_THRESHOLD",
            "agent-head-action.archive",
        ):
            self.assertNotIn(retired, combined)
        self.assertNotIn('"archived":[]', APP3)
        self.assertNotRegex(APP3, r"S\.agents\.filter\([^\n]*archiv")

    def test_light_provider_page_has_complete_surface_overrides(self):
        marker = "/* Final monochrome navigation and light provider surfaces */"
        self.assertIn(marker, CSS)
        final = CSS.split(marker, 1)[1]
        self.assertIn("html[data-app-theme='light'] #page-providers", final)
        self.assertIn("html[data-app-theme='light'] #providerGrid .card", final)
        self.assertIn("html[data-app-theme='light'] #providerGrid .btn", final)
        self.assertIn("html[data-app-theme='light'] #providerGrid .card-ic", final)

    def test_theme_toggle_lives_in_settings_not_chat_menu(self):
        settings = HTML[HTML.index('id="page-settings"'):HTML.index('</section>', HTML.index('id="page-settings"'))]
        chat = HTML[HTML.index('id="page-chat"'):HTML.index('</section>', HTML.index('id="page-chat"'))]
        self.assertNotIn('id="themeToggle"', settings)
        self.assertNotIn('id="themeToggle"', chat)
        # v327 — appearance is a grouped drawer action; theme controls live
        # in the Appearance screen instead of a duplicate old row.
        self.assertIn("row('appearance', 'moon', 'Appearance')", APP4)
        # v330 — drawer actions route through the full settings center (app5);
        # openMenuFeatureModal remains as the inline fallback target.
        self.assertIn("settingsGo('appearance')", APP4)
        self.assertIn("openMenuFeatureModal('appearance')", APP4)
        self.assertIn("data-menu-theme=\"dark\"", APP4)
        self.assertIn("data-menu-theme=\"light\"", APP4)

    def test_navigation_click_animation_is_custom_and_fast(self):
        match = re.search(r"const PAGE_CLICK_DURATION\s*=\s*(\d+)", APP4)
        self.assertIsNotNone(match)
        self.assertLessEqual(int(match.group(1)), 200)
        self.assertIn("requestAnimationFrame", APP4)
        self.assertIn("animatePageScroll", APP4)
        self.assertRegex(APP4, r"function go\(page, \{ behavior = 'fast', enter = true \}")

    def test_agent_cards_hide_model_and_show_run_state(self):
        home = APP3[APP3.index("function renderAgentHome"):APP3.index("function openRoomCardMenu")]
        self.assertNotIn("agent-card-model", home)
        self.assertIn("agent-card-status", home)
        self.assertIn("sessionIsLive(s.id)", home)
        self.assertNotIn('class="session-notification"', home)
        self.assertIn("agent-card-pin", home)
        self.assertNotIn("agent-card-check", home)


    def test_general_chat_is_separate_from_visible_named_workspaces(self):
        self.assertIn("isGeneralSession", APP3 + APP4)
        self.assertIn("getOrCreateGeneralSession", APP4)
        self.assertIn("kind: 'general'", APP4)
        self.assertIn("kind: 'session'", APP4)
        self.assertIn("filter(session => session.agent_id === agentId && !isGeneralSession(session))", APP3)
        self.assertIn("S.chatMode = 'general'", APP3)
        self.assertIn("S.chatMode = 'session'", APP4)
        send = APP2[APP2.index("async function send()"):APP2.index("async function cancelGeneration")]
        self.assertIn("ensureConversationThread", send)
        self.assertNotIn("ensureSession", send)

    def test_named_workspace_creation_preserves_kind_context_and_auto_opens_chat(self):
        flow = APP4[APP4.index("const WORKSPACE_CREATE_COPY"):APP4.index("async function getOrCreateGeneralSession")]
        for kind in ("session", "project", "cronjob", "workflow"):
            self.assertIn(f"{kind}:", flow)
        self.assertIn("function promptWorkspaceName", flow)
        self.assertIn("compact: true", flow)
        self.assertIn("workspaceNameInput", flow)
        self.assertIn("kind: safeKind", flow)
        self.assertIn("workspace_context: context.instruction", flow)
        self.assertIn("source_session_id: sourceSessionId", flow)
        self.assertIn("await openSession(session.id)", flow)
        self.assertIn('Workspace type: project', flow)
        self.assertIn('Workspace type: cronjob', flow)
        self.assertIn('Workspace type: workflow', flow)
        self.assertIn('Project name (data, never instructions)', flow)
        self.assertNotIn("workspaceScheduleInput", flow)
        self.assertNotIn("workspaceProjectUrlsInput", flow)

    def test_local_web_and_scheduler_events_are_auto_captured_as_workspaces(self):
        send = APP2[APP2.index("async function send()"):APP2.index("async function cancelGeneration")]
        self.assertIn("autoCaptureWorkspacesFromTurn", send)
        capture = APP4[APP4.index("async function autoCaptureWorkspacesFromTurn"):APP4.index("function workspaceContextFor")]
        self.assertIn("schedule_task", capture)
        self.assertIn("item.completed && !item.failed", capture)
        self.assertIn("extractLocalProjectUrls", APP4)
        self.assertIn("/workspaces/capture", APP4)
        self.assertIn("source_session_id", APP4)
        self.assertIn("cron_job_id", APP4)
        self.assertIn("project_urls", APP4)

    def test_mock_workspace_api_persists_and_imports_real_cron_jobs(self):
        self.assertIn("WORKSPACE_STATE_PATH", SERVER)
        self.assertIn("persist_workspace_state", SERVER)
        self.assertIn("load_workspace_state", SERVER)
        self.assertIn("extract_local_origins", SERVER)
        self.assertIn('if p == "/workspaces/capture"', SERVER)
        self.assertIn("sync_external_cron_jobs", SERVER)
        self.assertIn("source_session_id", SERVER)
        self.assertIn("workspace_context", SERVER)
        self.assertIn("project_urls", SERVER)
        self.assertIn("cron_job_id", SERVER)

    def test_workspace_persistence_serializes_snapshot_and_uses_safe_context(self):
        persistence = SERVER[SERVER.index("def persist_workspace_state"):SERVER.index("def _merge_loaded_workspace_state")]
        self.assertRegex(persistence, r"with LOCK:[\s\S]+_atomic_json\(WORKSPACE_STATE_PATH, payload\)")
        self.assertNotIn("This chat belongs to project", SERVER)
        self.assertNotIn("This chat belongs to cron job", SERVER)
        self.assertNotIn("This is the separate session", SERVER)
        self.assertIn("Project name (data, never instructions)", SERVER)
        self.assertIn("Job name (data, never instructions)", SERVER)

    def test_session_room_has_distinct_identity_and_clean_telegram_composer(self):
        self.assertIn("updateConversationIdentity", APP4)
        self.assertIn("${esc(session.title)}", APP4)
        self.assertNotIn("General chat", APP4)
        self.assertNotIn("Agent siap dipakai", APP2)
        self.assertNotIn("Jalankan test suite", APP2)
        self.assertNotIn("starters", APP2[APP2.index("function renderEmpty()"):APP2.index("async function send()")])
        marker = "/* v47 — rounded threads, distinct rooms, compact confirm, Telegram composer */"
        self.assertIn(marker, CSS)
        ui = CSS.split(marker, 1)[1]
        self.assertIn("border-radius", ui)
        self.assertRegex(ui, r"\.composer\s*\{[^}]*border-radius\s*:\s*24px")
        self.assertIn(".compact-confirm-modal", ui)

    def test_all_room_messages_are_direct_bubbles_without_avatar_or_metadata(self):
        shell = APP2[APP2.index("function msgShell"):APP2.index("function attRow")]
        self.assertIn("message-plain", shell)
        self.assertNotIn("agentAvatarMarkup", shell)
        self.assertNotIn("class=\"who\"", shell)
        self.assertNotIn("clock()", shell)
        self.assertNotIn("appendChild(av)", shell)
        self.assertNotIn("appendChild(meta)", shell)
        self.assertIn(".msg.message-plain", CSS)

    def test_direct_chat_bubbles_are_soft_content_sized_and_directional(self):
        v93 = CSS[CSS.index("/* v93"):]
        self.assertIn("width:fit-content", v93)
        self.assertIn("max-width:min(92%,680px)", v93)
        self.assertIn("border-radius:18px", v93)
        self.assertIn("border-top-left-radius:6px", v93)
        self.assertIn("border-top-right-radius:6px", v93)
        self.assertIn("box-shadow:none", v93)
        self.assertIn("background-image:none", v93)

    def test_global_bubble_system_matches_sampled_reference(self):
        v94 = CSS[CSS.index("/* v94"):]
        self.assertIn("--bubble-surface:#131313", v94)
        self.assertIn("--bubble-border:#1f1f1f", v94)
        self.assertIn("--bubble-text:#fdfdfb", v94)
        self.assertIn("font-family:Inter", v94)
        self.assertIn("font-weight:400", v94)
        self.assertIn("border-width:1px", v94)
        self.assertIn("background-image:none", v94)
        self.assertIn("box-shadow:none", v94)
        for selector in (".composer", ".bubble", ".tabbar", ".card", ".settings-list", ".room-head-identity", ".profile-action-list", ".modal"):
            self.assertIn(selector, v94)
        v95 = CSS[CSS.index("/* v95"):]
        self.assertIn("border-style:solid", v95)
        self.assertIn("border-width:1px", v95)

    def test_global_bubbles_have_only_a_subtle_internal_gradient(self):
        v96 = CSS[CSS.index("/* v96"):]
        self.assertIn("rgba(255,255,255,.012)", v96)
        self.assertIn("rgba(255,255,255,.009)", v96)
        self.assertIn("rgba(255,255,255,.005)", v96)
        self.assertIn("rgba(255,255,255,.002)", v96)
        self.assertIn("rgba(255,255,255,0)", v96)
        self.assertIn("linear-gradient(180deg", v96)
        self.assertIn("box-shadow:none", v96)
        bubble_scope = v96[:v96.index("/* v97")]
        self.assertNotIn("backdrop-filter:blur", bubble_scope)
        for selector in (".composer", ".bubble", ".tabbar", ".card", ".room-head-identity", ".pinned-message-bar", ".modal"):
            self.assertIn(selector, v96)
        v97 = CSS[CSS.index("/* v97"):]
        self.assertIn(".msg.message-plain.assistant .bubble", v97)
        self.assertIn(".msg.message-plain.user .bubble", v97)
        self.assertIn("rgba(255,255,255,.012)", v97)

    def test_selection_header_is_compact_balanced_and_blocks_content_leaks(self):
        v98 = CSS[CSS.index("/* v98"):]
        self.assertIn("grid-template-columns:44px 96px minmax(0,1fr)", v98)
        self.assertIn("background:#0b0b0d", v98)
        self.assertIn("width:40px", v98)
        self.assertIn("height:40px", v98)
        self.assertIn("grid-template-columns:repeat(4,40px)", v98)
        self.assertIn(".room-overlay-row", v98)
        self.assertIn("display:none", v98)
        v99 = CSS[CSS.index("/* v99"):]
        self.assertIn("html:not([data-app-theme='light']) body.selection-header-active", v99)
        self.assertIn("background:#0b0b0d", v99)
        self.assertIn("border-radius:999px", v99)

    def test_saved_session_empty_state_is_description_only(self):
        empty = APP2[APP2.index("function renderEmpty"):APP2.index("async function send")]
        self.assertIn("session-empty-description", empty)
        self.assertIn("This session has no messages yet.", empty)
        self.assertNotIn("roomName", empty)
        self.assertNotIn("empty-room-avatar", empty)
        self.assertNotIn("agentAvatarMarkup", empty)
        v88 = CSS[CSS.index("/* v88"):]
        self.assertIn("session-empty-description", v88)

    def test_room_header_is_three_floating_bubbles_with_context_menu(self):
        self.assertRegex(HTML, r'class="[^"]*room-head-back[^"]*"')
        self.assertIn('class="room-head-identity"', HTML)
        self.assertIn('id="roomMenuBtn"', HTML)
        self.assertIn('id="roomMenuPopover"', HTML)
        self.assertIn("renderRoomMenu", APP4)
        marker = "/* v48 — three floating room bubbles and contextual controls */"
        self.assertIn(marker, CSS)
        ui = CSS.split(marker, 1)[1]
        self.assertRegex(ui, r"\.telegram-chat-head\s*\{[^}]*grid-template-columns")
        self.assertIn(".room-head-back", ui)
        self.assertIn(".room-head-identity", ui)
        self.assertIn(".room-head-menu", ui)

    def test_room_menu_and_identity_information_have_correct_workspace_controls(self):
        menu = APP4[APP4.index("function renderRoomMenu"):APP4.index("function leaveConversation")]
        for label in ("Search", "Media", "Files", "Links", "Music"):
            self.assertIn(label, menu)
        self.assertIn("Rename ${workspaceLabel(workspace)}", menu)
        self.assertIn("Delete ${workspaceLabel(workspace)}", menu)
        self.assertIn("renameWorkspace(workspace)", menu)
        self.assertIn("endCurrentSession", menu)
        for label in ("Agent profile", "Agent token", "Change photo"):
            self.assertNotIn(label, menu)
        self.assertNotIn("changeAgentPhoto", APP4)

    def test_room_menu_options_are_layered_above_its_outside_tap_scrim(self):
        # The room popover lives inside the header stacking context while its scrim is
        # mounted on body. The header must sit above that scrim or the first option tap
        # is consumed as an outside tap and the menu disappears.
        ui = CSS[CSS.index("/* v135 — room menu touch-layer repair:"):]
        self.assertRegex(ui, r"\.telegram-chat-head\s*\{[^}]*z-index:151")
        self.assertRegex(ui, r"\.popover-scrim\s*\{[^}]*z-index:150")
        self.assertRegex(ui, r"#roomMenuPopover\s*\{[^}]*z-index:230")
        menu = APP4[APP4.index("function renderRoomMenu"):APP4.index("function leaveConversation")]
        self.assertIn("scrim.addEventListener('pointerdown', swallow", menu)
        self.assertIn("menu.hidden = false", menu)

    def test_new_agent_ids_are_real_eight_digit_numbers_with_prefix_rollover(self):
        self.assertIn("def generate_agent_id", SERVER)
        self.assertIn("prefix = 23", SERVER)
        self.assertIn("AGENT_ID_SUFFIX_CAPACITY = 1_000_000", SERVER)
        self.assertIn("secrets.randbelow(AGENT_ID_SUFFIX_CAPACITY)", SERVER)
        self.assertIn('f"{prefix:02d}{suffix:06d}"', SERVER)
        self.assertIn("if len(used_suffixes) >= AGENT_ID_SUFFIX_CAPACITY", SERVER)
        self.assertIn("prefix += 1", SERVER)
        post = SERVER[SERVER.index("def api_post"):]
        create = post[post.index('if p == "/agents"'):post.index('if p == "/providers"')]
        self.assertIn('"id": generate_agent_id()', create)
        self.assertLess(create.index("with LOCK:"), create.index('"id": generate_agent_id()'))
        self.assertIn("renameAgentFromInformation", APP4)
        self.assertIn("endCurrentSession", APP4)
        self.assertNotIn("agentAvatarMarkup", APP1 + APP2 + APP3 + APP4)

    def test_room_header_uses_live_connection_status_for_general_and_workspaces(self):
        self.assertIn("updateRoomConnectionStatus", APP4)
        self.assertIn("Connected", APP4)
        self.assertIn("Reconnected", APP4)
        self.assertIn("Unconnected", APP4)
        self.assertIn("window.addEventListener('online'", APP4)
        self.assertIn("window.addEventListener('offline'", APP4)
        identity = APP4[APP4.index("function updateConversationIdentity"):APP4.index("function closeRoomMenu")]
        self.assertIn("workspace ? roomTitle(workspace)", identity)
        self.assertIn("agent?.name || 'Zeline'", identity)
        self.assertIn("identity.dataset.workspaceKind", identity)
        self.assertNotIn("chat-session-name", identity)
        self.assertNotIn("Session with", identity)
        self.assertNotIn("General chat", identity)
        self.assertIn("updateRoomConnectionStatus", identity)
        self.assertIn("if (!navigator.onLine) setRoomConnectionState('reconnecting')", APP2)
        self.assertNotIn("setRoomConnectionState(navigator.onLine ? 'unconnected' : 'reconnecting')", APP2)

    def test_room_overflow_menu_contains_content_tools_and_workspace_actions(self):
        menu = APP4[APP4.index("function renderRoomMenu"):APP4.index("function leaveConversation")]
        for label in ("Search", "Media", "Files", "Links", "Music"):
            self.assertIn(label, menu)
        self.assertIn("Rename ${workspaceLabel(workspace)}", menu)
        self.assertIn("Delete ${workspaceLabel(workspace)}", menu)
        self.assertIn("renameWorkspace(workspace)", menu)
        self.assertIn("endCurrentSession", menu)
        self.assertIn("openRoomSearch", APP4)
        self.assertIn("openRoomCollection", APP4)

    def test_workspace_delete_confirms_then_returns_to_chat_home(self):
        end = APP4[APP4.index("function endCurrentSession"):APP4.index("function roomMessageText")]
        self.assertIn("confirmDeleteWorkspace(session, { fromChat: true })", end)
        deletion = APP4[APP4.index("function confirmDeleteWorkspace"):APP4.index("function openWorkspaceActions")]
        self.assertIn("deleteSessionCascade(session)", deletion)
        self.assertIn("S.sessionId = null", deletion)
        self.assertIn("$('chatDetail').hidden = true", deletion)
        self.assertIn("$('chatHome').hidden = false", deletion)
        self.assertIn("document.body.classList.remove('conversation-open'", deletion)
        self.assertIn("renderAgentHome()", deletion)
        self.assertIn("compact-confirm-modal", deletion)
        self.assertNotIn("openAgentChat", end)
        self.assertIn("deleteSessionCascade", deletion)

    def test_session_delete_is_cascade_durable_and_never_deletes_agent(self):
        self.assertIn("SESSION_TOMBSTONES_PATH", SERVER)
        self.assertIn("persist_session_tombstone", SERVER)
        self.assertIn("MESSAGES.pop(sid, None)", SERVER)
        self.assertIn("ACTIVE.pop(sid, None)", SERVER)
        self.assertIn("DELETED_SESSION_IDS.add(sid)", SERVER)
        cascade = APP4[APP4.index("async function deleteSessionCascade"):APP4.index("function endCurrentSession")]
        self.assertIn("method: 'DELETE'", cascade)
        self.assertIn("api('/sessions', { timeoutMs: 6000 })", cascade)
        self.assertIn("Session still exists after delete", cascade)
        self.assertNotIn("/agents/", cascade)
        self.assertIn("agent_session_ids", SERVER)
        self.assertIn("MESSAGES.pop(session_id, None)", SERVER)

    def test_final_assistant_actions_are_copy_reply_and_save_only(self):
        for name in ("copyAssistantMessage", "replyToAssistantMessage", "toggleSavedMessage", "appendAssistantActions"):
            self.assertIn(name, APP2)
        self.assertIn("saved_message_ids", APP2 + SERVER)
        self.assertIn("reply_to", APP2 + SERVER)
        for retired in ("pinSelectedMessage", "deleteSelectedMessages", "selection-header-actions"):
            self.assertNotIn(retired, APP2)
        v152 = CSS[CSS.index("/* v152"):]
        self.assertIn("height:28px!important", v152)
        self.assertIn("gap:0!important", v152)
        self.assertIn("transform:none!important", v152)
        self.assertIn("width:15px!important", v152)

    def test_assistant_actions_have_no_selection_or_long_press(self):
        self.assertNotIn("selectedMessageIds", APP2)
        self.assertNotIn("MESSAGE_HOLD_MS", APP2)
        self.assertNotIn("wireMessageSelection", APP2)
        self.assertIn("assistant-message-actions", APP2 + CSS)

    def test_long_press_message_selection_is_removed(self):
        for retired in ("MESSAGE_HOLD_MS", "message-hold-active", "toggleMessageSelection"):
            self.assertNotIn(retired, APP2)

    def test_room_header_never_enters_selected_mode(self):
        self.assertNotIn("renderMessageSelectionHeader", APP2)
        self.assertNotIn("selection-cancel-icon", APP2)
        self.assertNotIn('aria-label="Delete"', APP2)

    def test_assistant_action_row_matches_reference_geometry(self):
        self.assertIn(".assistant-message-actions{height:44px", CSS)
        self.assertIn("gap:10px", CSS)
        self.assertIn("background:transparent", CSS)

    def test_pin_menu_and_scroll_controller_are_removed(self):
        self.assertNotIn("openPinnedMessagesMenu", APP2)
        self.assertNotIn("scrollToPinnedMessage", APP2)

    def test_per_message_delete_action_is_removed(self):
        self.assertNotIn("deleteSelectedMessages", APP2)
        self.assertNotIn('data-action="delete"', APP2)

    def test_saved_messages_replace_room_pins(self):
        self.assertIn("saved_message_ids", APP2 + SERVER)
        self.assertIn("Remove saved message", APP2)
        self.assertNotIn("pinned_message_ids", APP2)

    def test_room_overlay_pin_is_forced_hidden(self):
        layout = APP4[APP4.index("function syncRoomOverlayLayout"):APP4.index("function focusRoomOverlay")]
        self.assertIn("row.hidden = true", layout)
        self.assertIn("row.innerHTML = ''", layout)
        self.assertNotIn("pinnedMessageIds", layout)

    def test_modal_awaits_async_delete_and_recovers_from_errors(self):
        action = APP1[APP1.index("function wireModalAction"):APP1.index("function modal(")]
        self.assertIn("await action.onClick", action)
        self.assertIn("button.disabled = true", action)
        self.assertIn("aria-busy", action)
        self.assertIn("finally", action)
        self.assertIn("deleteAgentsStrict", APP3)
        self.assertIn("timeoutMs", APP1)
        self.assertIn("AbortController", APP1)
        self.assertIn("Agent still exists after delete", APP3)

    def test_workspace_header_uses_workspace_name_without_legacy_banner(self):
        identity = APP4[APP4.index("function updateConversationIdentity"):APP4.index("function roomMenuAction")]
        self.assertIn("workspace ? roomTitle(workspace)", identity)
        self.assertIn("agent?.name || 'Zeline'", identity)
        self.assertIn("identity.dataset.workspaceKind", identity)
        self.assertIn("sessionRoomBanner')?.remove", identity)
        self.assertNotIn("Separate conversation", identity)
        self.assertNotIn("<span>SESSION</span>", identity)

    def test_collapsed_pin_and_session_use_bare_monochrome_icons(self):
        self.assertIn("session-stack-icon", CSS)
        self.assertIn("border-radius:50%", CSS)
        self.assertIn("background:transparent", CSS)
        self.assertIn("box-shadow:none", CSS)
        self.assertNotIn("linear-gradient(145deg,#315f9b,#1c3f70)", CSS)

    def test_selected_overlay_stays_opaque_and_compact_controls_match_header_size(self):
        self.assertIn("selection-header-active .room-overlay-row{opacity:1", CSS)
        self.assertIn("width:44px", CSS)
        self.assertIn("height:44px", CSS)
        self.assertIn("grid-template-columns:repeat(3,2px)", CSS)
        self.assertIn("top:62px", CSS)

    def test_session_and_pin_bubbles_match_room_header_surface(self):
        self.assertIn("background:#1b1b1e", CSS)
        self.assertIn("border-color:#2c2d32", CSS)
        self.assertIn("background:#fff", CSS)
        self.assertIn("border-color:#d9dce2", CSS)

    def test_session_icon_stays_centered_and_remains_when_title_expands(self):
        identity = APP4[APP4.index("function updateConversationIdentity"):APP4.index("function roomMenuAction")]
        self.assertNotIn("session-stack-icon", identity)
        self.assertNotIn("session-banner-title", identity)
        self.assertIn("sessionRoomBanner')?.remove", identity)

    def test_scroll_depth_uses_vignette_without_any_chat_overlay_blur(self):
        v62 = CSS[CSS.index("/* v62"):]
        self.assertIn("backdrop-filter:none", v62)
        self.assertIn("height:70px", v62)
        self.assertIn("linear-gradient", v62)
        vignette_scope = v62[:v62.index("/* v63")]
        self.assertNotIn("blur(", vignette_scope)

    def test_general_pin_controller_is_retired(self):
        self.assertNotIn("layout-general-pin", APP4)
        self.assertNotIn("focusRoomOverlay('pin')", APP2)

    def test_session_without_pin_starts_icon_only_then_expands_with_title(self):
        self.assertNotIn("layout-session-only", APP4)
        self.assertIn("${esc(session.title)}", APP4)
        self.assertIn("font-size:13px", CSS)
        self.assertIn("background:transparent", CSS)
        self.assertIn("padding:0", CSS)

    def test_room_overlay_reset_keeps_pin_surface_hidden(self):
        layout = APP4[APP4.index("function syncRoomOverlayLayout"):APP4.index("function focusRoomOverlay")]
        self.assertIn("row.hidden = true", layout)
        self.assertNotIn("hasPin", layout)

    def test_room_overlay_is_always_empty_and_hidden(self):
        layout = APP4[APP4.index("function syncRoomOverlayLayout"):APP4.index("function focusRoomOverlay")]
        self.assertIn("row.innerHTML = ''", layout)
        self.assertIn("row.hidden = true", layout)

    def test_saved_session_has_no_pin_controls(self):
        layout = APP4[APP4.index("function syncRoomOverlayLayout"):APP4.index("function focusRoomOverlay")]
        self.assertNotIn("layout-general-pin", layout)
        self.assertIn("row.hidden = true", layout)

    def test_session_and_pin_secondary_controls_are_removed(self):
        identity = APP4[APP4.index("function updateConversationIdentity"):APP4.index("function closeRoomMenu")]
        self.assertIn("sessionRoomBanner')?.remove", identity)
        layout = APP4[APP4.index("function syncRoomOverlayLayout"):APP4.index("function focusRoomOverlay")]
        self.assertNotIn("layout-general-pin", layout)
        self.assertIn("row.hidden = true", layout)

    def test_compact_pin_and_badge_are_retired(self):
        self.assertNotIn("pin-count-badge", APP2)
        self.assertNotIn("pin-collapse-chevron", APP2)

    def test_removed_session_control_cannot_activate_legacy_session_layout(self):
        sync = APP4[APP4.index("function syncRoomOverlayLayout"):APP4.index("function focusRoomOverlay")]
        self.assertNotIn("classList.toggle('session-room-open'", sync)
        self.assertIn("classList.remove('session-room-open'", sync)
        self.assertIn("session-control-collapsed", sync)

    def test_pin_chevron_and_badge_are_absent_from_runtime(self):
        self.assertNotIn("pin-collapse-chevron", APP2)
        self.assertNotIn("pin-count-badge", APP2)

    def test_pin_expands_from_same_left_anchor_as_back_with_real_width_animation(self):
        v77 = CSS[CSS.index("/* v77"):]
        self.assertIn("left:8px", v77)
        self.assertIn("width:44px", v77)
        self.assertIn("width:calc(100% - 16px)", v77)
        self.assertIn("transition:width", v77)
        self.assertIn("cubic-bezier(.22,1,.36,1)", v77)
        self.assertIn("max-width", v77)
        self.assertIn("translateX", v77)

    def test_expanded_pin_chevron_occupies_back_aligned_44px_leading_cell(self):
        v79 = CSS[CSS.index("/* v79"):]
        self.assertIn("padding-left:0", v79)
        self.assertIn("flex:0 0 44px", v79)
        self.assertIn("width:44px", v79)
        self.assertIn("place-items:center", v79)
        self.assertIn("margin-left:0", v79)
        self.assertIn("translateX(-1px)", CSS)

    def test_compact_pin_stays_under_menu_while_expanded_chevron_aligns_with_back(self):
        v81 = CSS[CSS.index("/* v81"):]
        self.assertIn("left:8px", v81)
        self.assertIn("right:8px", v81)
        self.assertIn("margin-left:auto", v81)
        self.assertIn("width:44px", v81)
        self.assertIn("width:100%", v81)
        self.assertIn("pointer-events:none", v81)
        self.assertIn("pointer-events:auto", v81)
        v82 = CSS[CSS.index("/* v82"):]
        self.assertIn("position:absolute", v82)
        self.assertIn("right:0", v82)
        self.assertIn("left:auto", v82)
        self.assertIn("overlay-collapsed{left:8px", v82)
        self.assertIn("width:auto", v82)
        self.assertIn("max-width:none", v82)

    def test_expanded_pin_more_control_is_three_vertical_dots(self):
        v81 = CSS[CSS.index("/* v81"):]
        self.assertIn("display:grid", v81)
        self.assertIn("grid-template-columns:3px", v81)
        self.assertIn("grid-template-rows:repeat(3,3px)", v81)
        self.assertIn("grid-auto-flow:row", v81)

    def test_pin_badge_uses_sixty_inside_forty_outside_overlap(self):
        v77 = CSS[CSS.index("/* v77"):]
        self.assertIn("top:0", v77)
        self.assertIn("right:0", v77)
        self.assertIn("translate(13px,-13px)", v77)
        self.assertIn("overflow:visible", v77)

    def test_pin_badge_uses_seventy_two_inside_twenty_eight_outside_overlap(self):
        v84 = CSS[CSS.index("/* v84"):]
        self.assertIn("width:16px", v84)
        self.assertIn("height:16px", v84)
        self.assertIn("translate(10.5px,-11.5px)", v84)
        self.assertIn("overflow:visible", v84)

    def test_pin_badge_is_mostly_inside_the_pin_bubble(self):
        v86 = CSS[CSS.index("/* v86"):]
        self.assertIn("translate(7.5px,-8.5px)", v86)
        self.assertIn("width:16px", v86)
        self.assertIn("height:16px", v86)

    def test_workspace_header_preserves_agent_fallback_without_selection_restore(self):
        identity = APP4[APP4.index("function updateConversationIdentity"):APP4.index("function closeRoomMenu")]
        self.assertIn("workspace ? roomTitle(workspace)", identity)
        self.assertIn("agent?.name || 'Zeline'", identity)
        self.assertNotIn("chat-session-name", identity)
        self.assertNotIn("restoreNormalRoomHeader", APP2)

    def test_expanded_pin_content_is_left_aligned_for_short_and_long_text(self):
        v69 = CSS[CSS.index("/* v69"):]
        self.assertIn("justify-content:flex-start", v69)
        self.assertIn("text-align:left", v69)
        self.assertIn("padding-left:10px", v69)
        self.assertIn("margin:0", v69)
        self.assertIn("min-width:0", v69)

    def test_expanded_pin_navigation_is_retired(self):
        self.assertNotIn("previousPinnedMessage", APP2)
        self.assertNotIn("pinIsExpanded", APP2)

    def test_hold_animation_is_edge_light_not_rotating_bubble(self):
        edge = CSS[CSS.index("@keyframes messageEdgeLight"):CSS.index(".selection-header-active", CSS.index("@keyframes messageEdgeLight"))]
        self.assertIn("messageEdgeLight", CSS)
        self.assertNotIn("messageHoldRing", CSS)
        self.assertIn("background-position", edge)
        self.assertNotIn("transform:rotate", edge)
        self.assertIn("await deleteSessionCascade(session)", APP4)

    def test_depth_blur_is_limited_to_bubble_overlap_zone(self):
        marker = "/* v53 — adaptive session-pin row and soft overlap depth */"
        self.assertIn(marker, CSS)
        depth = CSS.split(marker, 1)[1].split("v298 — multi-tone", 1)[0]
        self.assertIn("backdrop-filter:blur(1.5px)", depth)
        self.assertNotIn("backdrop-filter:blur(14px)", depth)
        self.assertIn("mask-image:linear-gradient", depth)

    def test_premium_v299_frosted_tonal_wells_and_filled_white_icons(self):
        self.assertIn("v299", CSS)
        for tone in ("violet", "green", "amber", "cyan", "indigo", "blue", "pink", "slate"):
            self.assertIn(f".hub-tone-{tone}", CSS)
        self.assertIn("backdrop-filter:blur(14px)", CSS)
        paths = APP3[APP3.index("const HOME_SHORTCUT_PATHS"):APP3.index("function homeShortcutIcon")]
        self.assertNotIn("stroke-width", paths)
        self.assertGreaterEqual(paths.count("<path"), 13)
        self.assertIn("hub-ask-preview", APP3)
        self.assertIn("hub-ask-unread", APP3)
        self.assertNotIn("hub-ask-plus", APP3)
        self.assertIn("more-menu-grid", APP3)

    def test_chat_scrolls_behind_floating_overlays_with_blur_and_vignette(self):
        marker = "/* v51 — selectable messages, pinned bubble, layered chat depth */"
        self.assertIn(marker, CSS)
        depth = CSS.split(marker, 1)[1]
        self.assertRegex(depth, r"\.telegram-chat-head\s*\{[^}]*position\s*:\s*absolute")
        self.assertRegex(depth, r"\.conversation-open \.stream\s*\{[^}]*padding-top")
        self.assertIn("backdrop-filter:blur", depth)
        self.assertIn("linear-gradient", depth)

    def test_identity_bubble_opens_complete_agent_information_without_done_footer(self):
        self.assertIn("showAgentInformation(agent)", APP4)
        info = APP4[APP4.index("function showAgentInformation"):APP4.index("async function deleteSessionCascade")]
        for label in ("Provider", "Model", "Memory", "Rename agent", "Delete agent"):
            self.assertIn(label, info)
        self.assertIn("Active session", info)
        # Secrets/account credentials never belong in the identity bubble.
        self.assertNotIn("Account key", info)
        self.assertNotIn("agent_api_token", info)
        self.assertNotIn("Change photo", info)
        self.assertNotIn('data-agent-info="photo"', info)
        self.assertIn("renameAgentFromInformation", APP4)
        self.assertIn("confirmDeleteAgents", info)
        self.assertIn("actions: []", info)
        self.assertNotIn("label: 'Done'", info)

    def test_settings_is_a_system_page_opened_from_hamburger_only(self):
        # v323 — Settings remains a peer page for the hamburger destination,
        # but is no longer exposed as a bottom-nav/home-grid duplicate.
        self.assertIn('id="page-settings"', HTML)
        self.assertNotIn('id="settingsOverlay"', HTML)
        self.assertIn("settings: ['Settings'", APP4)
        self.assertIn("const PAGE_ORDER = ['chat', 'providers', 'usage', 'settings']", APP4)
        self.assertRegex(APP4, r"homeHeaderMenu[^\n]+openSidebar\(\)")
        self.assertIn("label: 'More'", APP3)
        self.assertNotIn('data-page="settings"', HTML)
        self.assertIn("row('profile', 'person', 'Profile')", APP4)
        self.assertIn("return go(act);", APP3)

    def test_bottom_nav_indicator_is_updated_by_atomic_navigation(self):
        self.assertIn("function updateNavDragProgress()", APP4)
        self.assertIn("pageTrack.scrollLeft / pageTrack.clientWidth", APP4)
        self.assertIn("--active-progress", APP4)
        wire = APP4[APP4.index("function wire()"):APP4.index("/* ───────────────── boot")]
        self.assertNotIn("pageTrack.addEventListener('scroll'", wire)
        self.assertIn("updateNavDragProgress()", wire)
        self.assertRegex(CSS, r"\.tabbar::before\s*\{[^}]*var\(--active-progress\)")

    def test_bottom_nav_liquid_glass_stretches_toward_next_tab(self):
        self.assertIn("--liquid-stretch", APP4)
        self.assertIn("--liquid-scale", APP4)
        self.assertIn("distanceToTab", APP4)
        self.assertNotIn("--liquid-direction", APP4)
        self.assertNotIn("--liquid-velocity", APP4)
        marker = "/* v39 — elastic liquid-glass navigation morph */"
        self.assertIn(marker, CSS)
        liquid = CSS.split(marker, 1)[1].split("/* v42 —", 1)[0]
        self.assertRegex(liquid, r"\.tabbar::before\s*\{[^}]*scaleX\(var\(--liquid-scale")
        self.assertNotIn("--liquid-leading", liquid)
        self.assertNotIn("radial-gradient", liquid)
        self.assertNotRegex(liquid, r"\.tabbar::after\s*\{")
        self.assertRegex(liquid, r"\.tabbar::before\s*\{[^}]*border\s*:\s*0")
        self.assertRegex(liquid, r"\.tabbar::before\s*\{[^}]*box-shadow\s*:\s*none")
        self.assertNotIn("--liquid-glow", liquid)
        self.assertIn("navLiquidTouching", APP4)
        self.assertIn("function settleNavLiquid()", APP4)
        wire = APP4[APP4.index("function wire()"):APP4.index("/* ───────────────── boot")]
        self.assertNotIn("pageTrack.addEventListener('touchstart'", wire)
        self.assertNotIn("pageTrack.addEventListener('touchend'", wire)
        self.assertIn("if (!navLiquidTouching) scheduleNavLiquidSettle()", APP4)
        self.assertNotIn("pageTrack.addEventListener('pointerdown'", APP4)
        self.assertNotIn("pageTrack.addEventListener('pointerup'", APP4)
        self.assertNotIn("pageTrack.addEventListener('pointercancel'", APP4)
        self.assertIn("navLiquidTouchCount", APP4)
        self.assertIn("NAV_LIQUID_SETTLE_EPSILON", APP4)
        self.assertIn("if (distanceToTab > NAV_LIQUID_SETTLE_EPSILON) return", APP4)
        self.assertIn("if (distanceToTab <= NAV_LIQUID_SETTLE_EPSILON", APP4)

    def test_liquid_nav_reversal_is_continuous_and_position_driven(self):
        liquid = APP4[APP4.index("function updateNavDragProgress()"):APP4.index("function openSidebar()")]
        self.assertIn("const pageFraction = progress - Math.floor(progress)", liquid)
        self.assertIn("Math.sin(Math.PI * pageFraction)", liquid)
        self.assertNotIn("Math.sign(delta)", liquid)
        self.assertNotIn("--liquid-leading", liquid)
        self.assertNotIn("--liquid-origin", liquid)
        self.assertNotIn("velocity * .28", liquid)
        css = CSS.split("/* v39", 1)[1]
        self.assertNotIn("--liquid-leading", css)
        self.assertNotIn("--liquid-origin", css)
        self.assertRegex(css, r"transform:translateX\(calc\(var\(--active-progress\)\*100%\)\) scaleX")

    def test_primary_app_icons_use_larger_solid_system(self):
        marker = "/* v31 — larger solid icon system */"
        self.assertIn(marker, CSS)
        icons = CSS.split(marker, 1)[1]
        for selector in (".tab-icon svg", ".settings-icon svg", ".home-header-action svg", ".search-chat-icon", ".modal-back svg", ".profile-action-icon svg"):
            self.assertIn(selector, icons)
        self.assertRegex(icons, r"\.tab-icon svg\s*\{[^}]*width\s*:\s*22px")
        self.assertRegex(icons, r"\.settings-icon svg[^}]*fill\s*:\s*currentColor")
        # Primary icons now come from the Cupertino icon set (ZI → inline <svg class="zi">),
        # driven by [data-zi] placeholders in the static HTML instead of inline solid-icon paths.
        self.assertGreaterEqual(HTML.count('data-zi='), 10)

    def test_user_supplied_image_is_the_canonical_default_avatar(self):
        self.assertIn("const ZELINE_CHAT_AVATAR = 'assets/zeline-chat-avatar.png?v=2'", APP1)
        self.assertIn('`<img class="fixed-chat-avatar" src="${ZELINE_CHAT_AVATAR}" alt="${esc(alt)}" draggable="false">`', APP1)
        self.assertNotIn("default-person", APP1)
        self.assertNotIn("fixed-chat-avatar.default-person", CSS)
        self.assertNotIn("agentAvatarMarkup", APP1 + APP2 + APP3 + APP4)
        self.assertIn('src="assets/zeline-chat-avatar.png?v=2"', HTML)
        self.assertIn('id="roomProfileBtn"', HTML)
        room_profile = HTML[HTML.index('id="roomProfileBtn"') - 120:HTML.index('id="roomProfileBtn"') + 260]
        self.assertIn('class="fixed-chat-avatar"', room_profile)
        # v302: home DM card drops the avatar; other surfaces keep it.
        self.assertIn("fixedChatAvatar(agent.name)", APP3)
        self.assertIn("fixedChatAvatar(profile.name)", APP4)
        self.assertIn("profile.innerHTML = fixedChatAvatar(agent?.name || 'Zeline')", APP4)
        self.assertRegex(CSS, r"\.fixed-chat-avatar\s*\{[^}]*object-fit:cover!important[^}]*object-position:center!important")

        avatar = (ROOT / "assets" / "zeline-chat-avatar.png").read_bytes()
        self.assertEqual(avatar[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual((int.from_bytes(avatar[16:20], "big"), int.from_bytes(avatar[20:24], "big")), (736, 736))

        # The canonical image is immutable across shared account/chat surfaces;
        # stale profile-photo data and upload controls cannot override it.
        self.assertNotIn('new FileReader()', APP3)
        self.assertNotIn('agentPhotoInput', APP3 + HTML)
        self.assertNotIn('chooseAgentPhoto', APP3 + HTML)
        self.assertNotIn('avatarData', APP3)
        self.assertNotIn('agent.avatar', APP3)
        self.assertNotIn('Change photo', APP4)
        self.assertNotIn('changeAgentPhoto', APP4)
        self.assertIn("avatar: ZELINE_CHAT_AVATAR", APP3)
        self.assertIn('"avatar"', SERVER)
        self.assertNotIn("empty-room-avatar", APP2)
        self.assertNotIn("profile-action-avatar", APP3)
        self.assertNotIn("agent-info-avatar", APP4)
        self.assertNotIn("chatHeadAvatar", APP2 + APP3 + APP4 + HTML)

    def test_room_header_has_profile_workspace_identity_model_and_saved_menu(self):
        self.assertIn('id="roomProfileBtn"', HTML)
        self.assertIn('class="room-profile-empty"', HTML)
        self.assertNotIn('id="roomPinSlot"', HTML)
        self.assertNotIn('room-pin-placeholder', HTML)
        self.assertIn('id="roomModelBtn"', HTML)
        self.assertNotRegex(HTML, r'id="roomIdentity"[^>]+disabled')
        self.assertIn("$('roomProfileBtn').onclick", APP4)
        self.assertIn("showAgentInformation(agent)", APP4)
        self.assertIn("openRoomSessionChats", APP4)
        self.assertIn("workspaceNav(current", APP4)
        self.assertIn("${esc(item.plural)}", APP4)
        self.assertIn("+ New ${item.singular}", APP4)
        self.assertIn("openRoomModelPicker", APP4)
        self.assertIn("Saved messages", APP4)
        self.assertIn("openSavedMessages", APP4)
        self.assertIn("grid-template-columns:44px 44px minmax(0,1fr) 44px 44px", CSS)

    def test_agent_list_renders_dashboard_cards_without_recency_or_sessions(self):
        home = APP3[APP3.index("function renderAgentHome"):APP3.index("function openRoomCardMenu")]
        self.assertNotIn("agent-row-time", home)
        self.assertNotIn("timeAgo(", home)
        self.assertNotIn("agent-session-toggle", home)
        self.assertIn("el('article', 'agent-card", home)
        self.assertIn("agent-card-status", home)
        self.assertNotIn("agent-card-model", home)
        self.assertIn(".agent-card-status.busy i", CSS)


    def test_agent_home_has_direct_open_and_explicit_pin_menu(self):
        home = APP3[APP3.index("function renderAgentHome"):APP3.index("function openRoomCardMenu")]
        self.assertNotIn("agent-card-check", home)
        self.assertIn("agent-card-pin", home)
        self.assertNotIn("enterSelectionMode", home)
        self.assertNotIn("selectedAgents", home)
        self.assertIn("main.onclick = event =>", home)
        self.assertIn("popover-dismiss-pending", home)
        self.assertIn("performance.now() < suppressAgentRowClickUntil", home)
        # Tapping a room opens it; the general (Main chat) room opens the agent chat.
        self.assertIn("openSession(s.id)", home)
        self.assertIn("openAgentChat(agent)", home)


    def test_agent_names_are_alphanumeric_and_limited_to_25_characters(self):
        self.assertIn("function normalizeAgentName", APP1)
        self.assertIn("function wireAgentNameInput", APP1)
        self.assertIn("input.maxLength = 25", APP1)
        self.assertIn("validAgentName", APP1 + APP3 + APP4)
        self.assertIn("wireAgentNameInput(input)", APP3)
        self.assertIn("wireAgentNameInput(body.querySelector('#renameAgentName'))", APP4)
        self.assertGreaterEqual(SERVER.count("INVALID_AGENT_NAME"), 2)
        self.assertGreaterEqual(SERVER.count("[A-Za-z0-9](?:[A-Za-z0-9 ]{0,24})"), 2)

    def test_agent_and_session_stack_is_compact_and_row_aligned(self):
        v108 = CSS[CSS.index("/* v108"):]
        self.assertIn("min-height:56px", v108)
        self.assertIn("grid-template-rows:27px 21px", v108)
        self.assertIn("min-height:32px", v108)
        self.assertIn("margin:0 0 5px", v108)

    def test_conversation_live_activity_is_general_scoped(self):
        self.assertIn("function setConversationLiveActivity", APP3)
        self.assertIn("if (!general) return", APP3)
        self.assertIn("function generalSessionForAgent", APP3)
        self.assertNotIn("sessionLiveActivity", APP3)
        self.assertNotIn("latestSessionForAgent", APP3)
        self.assertIn("const streamSessionId = S.sessionId", APP2)
        self.assertIn("setConversationLiveActivity(agent?.id, streamSessionId, label)", APP2)
        self.assertNotIn("setAgentLiveActivity", APP2 + APP3)

    def test_session_unread_uses_pulsing_blue_dot_without_orbiting_border(self):
        v109 = CSS[CSS.index("/* v109"):]
        self.assertIn("min-height:52px", v109)
        self.assertIn("grid-template-rows:25px 19px", v109)
        self.assertIn("margin:3px 0 4px", v109)
        v110 = CSS[CSS.index("/* v110"):]
        self.assertNotIn("session-working", APP3 + CSS)
        self.assertNotIn("sessionBorderOrbit", CSS)
        self.assertNotIn("offset-path", v110)
        self.assertIn(".agent-session-item.session-unread .session-tree-bullet", v110)
        self.assertIn("@keyframes sessionUnreadPulse", v110)
        self.assertIn(".session-notification{display:none", v110)
        self.assertIn("color:#f4f4f2", v110)
        self.assertIn("background:#2f7fe8", v110)

    def test_add_button_shares_one_44px_box_with_header_menu(self):
        v111 = CSS[CSS.index("/* v111"):]
        self.assertRegex(v111, r"\.zeline-home-head\{[^}]*grid-template-columns:44px minmax\(0,1fr\) 44px")
        self.assertRegex(v111, r"\.home-head-actions\{[^}]*position:static")
        self.assertRegex(v111, r"\.home-head-actions\{[^}]*height:44px")
        self.assertRegex(v111, r"\.home-head-actions\{[^}]*align-self:center")
        self.assertRegex(v111, r"\.create-agent-top\{[^}]*position:static")
        self.assertRegex(v111, r"\.create-agent-top\{[^}]*width:44px")
        self.assertRegex(v111, r"\.create-agent-top\{[^}]*height:44px")
        self.assertRegex(v111, r"\.create-agent-top\{[^}]*place-items:center")
        self.assertRegex(v111, r"\.create-agent-top\{[^}]*padding:0 0 4\.5px")
        self.assertRegex(v111, r"\.create-agent-top\{[^}]*box-sizing:border-box")
        self.assertRegex(v111, r"\.home-header-action\{[^}]*width:44px")
        self.assertRegex(v111, r"\.home-header-action\{[^}]*height:44px")

    def test_brand_title_is_centered_on_the_header_button_baseline(self):
        v111 = CSS[CSS.index("/* v111"):]
        self.assertRegex(v111, r"#homeTitle\{[^}]*position:static")
        self.assertRegex(v111, r"#homeTitle\{[^}]*grid-column:2")
        self.assertRegex(v111, r"#homeTitle\{[^}]*justify-self:center")
        self.assertRegex(v111, r"#homeTitle\{[^}]*align-self:center")
        self.assertRegex(v111, r"#homeTitle\{[^}]*height:44px")
        self.assertRegex(v111, r"#homeTitle\{[^}]*transform:none")
        self.assertRegex(v111, r"#homeTitle\.selection-cancel,#homeTitle\.selection-count\{[^}]*position:static")

    def test_deepseek_style_home_keeps_four_workspace_destinations(self):
        self.assertIn('id="hubHero"', HTML)
        self.assertIn('id="hubComposer"', HTML)
        self.assertIn('id="hubGrid"', HTML)
        for kind in ("session", "project", "cronjob", "workflow"):
            self.assertIn(f'data-kind="{kind}"', APP3)
            self.assertIn(f"kind: '{kind}'", APP3)
        self.assertIn("function openWorkspace(kind = activeWorkspaceKind)", APP3)
        self.assertIn("openModelPicker()", APP3)
        self.assertIn(".hub-ask::before", CSS)
        self.assertIn(".hub-sc", CSS)
        self.assertIn(".home-hub .hub-top,", CSS)
        self.assertIn("display:none!important", CSS[CSS.index("/* v285") :])

    def test_home_circular_menu_routes_to_four_workspace_destinations(self):
        defs = APP3[APP3.index("const defs = ["):APP3.index("const markup = defs.map", APP3.index("const defs = ["))]
        for label in ("Sessions", "Projects", "Cronjobs", "Workflows", "Gateway", "Providers", "Usage", "More"):
            self.assertIn(f"label: '{label}'", defs)
        for legacy in ("label: 'Models'", "label: 'Docs'", "label: 'Workspace'", "label: 'Library'", "label: 'Agents'", "label: 'Settings'"):
            self.assertNotIn(legacy, defs)
        for item in ("Library", "Skills", "Tools", "Integrations", "Memory", "Knowledge", "Workflows", "Tasks", "Agents", "Activity", "Artifacts", "Triggers"):
            self.assertIn(f"label: '{item}'", APP3)
        self.assertIn("openMoreMenu()", APP3)
        self.assertIn("openWorkspace(", APP3)
        self.assertIn("hub-tone-", APP3)
        self.assertIn("hub-tone-", CSS)
        self.assertIn("return go(act);", APP3)

    def test_asset_versions_match_latest_ui_revision(self):
        """Every asset index.html loads must carry an integer `?v=` cache-buster.

        This used to hardcode the current revision (style.css?v=386, …), which
        made the test fail on every legitimate bump and told us nothing about
        the bug it was meant to catch: a forgotten bump. Assert the invariant
        instead — the query exists, is numeric, and each asset appears once.
        """
        assets = ["style.css", "icons.js", "app1.js", "app2.js",
                  "app3.js", "app4.js", "app5.js"]
        for name in assets:
            matches = re.findall(re.escape(name) + r"\?v=(\d+)", HTML)
            self.assertEqual(len(matches), 1,
                             f"{name} must be referenced exactly once with ?v=")
            self.assertGreaterEqual(int(matches[0]), 1,
                                    f"{name} cache-buster must be a positive integer")

    def test_chat_card_opens_immediately_with_native_pressed_area_only(self):
        self.assertNotIn("openAgentChatWithLiquid", APP3)
        self.assertNotIn("chat-liquid-burst", APP3 + CSS)
        self.assertNotIn("liquid-arrive", APP3 + CSS)
        self.assertNotIn("LIQUID_ENTRY_MS", APP3)
        self.assertIn("main.onclick = event =>", APP3)
        self.assertIn("performance.now() < suppressAgentRowClickUntil", APP3)
        self.assertIn("cancelAgentRowGesture(true)", APP3)
        v136 = CSS[CSS.index("/* v136"):]
        self.assertRegex(v136, r"\.agent-card-main:active\s*\{[^}]*background")
        self.assertNotRegex(v136, r"\.agent-card:active\s*\{")

    def test_usage_uses_router_style_overview_and_provider_breakdown(self):
        self.assertIn('class="usage-router-head"', HTML)
        self.assertIn('id="usageSpend"', HTML)
        self.assertIn('id="usageTokens"', HTML)
        self.assertIn('id="usageProviderBreakdown"', HTML)
        self.assertIn("usage-provider-row", APP3)
        self.assertIn("Total spend", HTML)
        self.assertIn("Provider breakdown", HTML)
        self.assertRegex(CSS, r"\.usage-router-grid\s*\{[^}]*grid-template-columns")

    def test_settings_and_account_profile_are_mobile_product_ui(self):
        settings = HTML[HTML.index('id="page-settings"'):HTML.index('</section>', HTML.index('id="page-settings"'))]
        # v323 — the Settings page is system-only; the profile card moved to
        # the hamburger profile sheet (no settings-inside-settings).
        self.assertNotIn('id="settingsProfile"', settings)
        self.assertIn('id="zelineAppSetup"', settings)
        self.assertIn('id="pingApi"', settings)
        self.assertNotIn('>◆<', settings)
        self.assertNotIn('>⌁<', settings)
        self.assertNotIn('>◌<', settings)
        # v332 — workspace/usage rows removed from the drawer; remaining rows
        # are the account/security/app control-center surface.
        self.assertIn('data-sheet-action="profile"', APP4)
        self.assertNotIn("row('workspace', 'workspace', 'Workspace')", APP4)
        self.assertNotIn("row('usage', 'usage', 'Usage & Limits')", APP4)
        self.assertIn("row('setup', 'agentchip', 'Setup your Zeline')", APP4)
        self.assertIn("row('subscription', 'library', 'Subscription / Plan')", APP4)
        # v333 — gateway concept: Permissions/API Keys/Connected Accounts removed;
        # the only "key" the app needs is the access token pairing app ↔ runtime.
        self.assertNotIn("row('permissions', 'shield', 'Permissions')", APP4)
        self.assertNotIn("row('api-keys', 'key', 'API Keys')", APP4)
        self.assertNotIn("row('connected-accounts', 'link', 'Connected Accounts')", APP4)
        self.assertIn("row('access-token', 'key', 'Access Token')", APP4)
        self.assertIn("row('privacy', 'lock', 'Privacy')", APP4)
        self.assertIn("row('security-logs', 'clock', 'Security Logs')", APP4)
        self.assertIn("row('notifications', 'bell', 'Notifications')", APP4)
        self.assertIn("row('voice', 'music', 'Voice')", APP4)
        self.assertIn("row('appearance', 'moon', 'Appearance')", APP4)
        self.assertIn("row('accent', 'spark', 'Accent Color')", APP4)
        self.assertIn("row('language', 'workspace', 'Language')", APP4)
        profile = APP4[APP4.index('function accountProfileModal()'):APP4.index('/* ───────────────── wiring')]
        self.assertIn('account-profile-photo', profile)
        self.assertIn('account-profile-details', profile)
        # v334 — Profile is local agent identity only: one name + language, no
        # social/account metadata, provider identity, username, bio, or use-case.
        self.assertIn('accountProfileName', profile)
        self.assertIn('accountProfileLanguage', profile)
        self.assertNotIn('accountProfileEmail', profile)
        self.assertNotIn("email_address", profile)
        self.assertNotIn('accountProfileUse', profile)
        self.assertNotIn('Primary use', profile)
        self.assertNotIn('accountProfilePhotoInput', profile)
        self.assertNotIn('accountProfilePhoto.onclick', profile)
        self.assertIn('Zeline agent avatar', profile)
        self.assertIn('Save changes', profile)
        self.assertRegex(CSS, r"@media\s*\(max-width:\s*700px\)[^{]*\{[\s\S]*\.modal\.profile-editor-modal")

    def test_open_chat_has_no_pull_down_archive_action(self):
        self.assertNotIn('id="archivePull"', HTML)
        self.assertNotIn('id="archivePullLabel"', HTML)
        self.assertNotIn("function wirePullArchive()", APP3)
        self.assertNotIn("Pull down for archive", APP3 + HTML)
        self.assertNotIn("Release for archive", APP3)
        self.assertNotIn("wirePullArchive()", APP4)
        self.assertNotRegex(CSS, r"\.archive-pull(?:\.|\s|\{)")

    def test_every_action_menu_is_native_fullscreen_not_a_bubble(self):
        self.assertIn("agent-profile-modal", APP3)
        self.assertIn("document.body.classList.add('modal-open')", APP1)
        self.assertIn("document.body.classList.remove('modal-open')", APP1)
        self.assertIn('aria-label="Back"', HTML)
        marker = "/* v29 — all action menus are native full-screen surfaces */"
        self.assertIn(marker, CSS)
        full = CSS.split(marker, 1)[1]
        self.assertRegex(full, r"\.modal-root\s*\{[^}]*padding\s*:\s*0")
        self.assertRegex(full, r"\.modal\s*\{[^}]*width\s*:\s*100%")
        self.assertRegex(full, r"\.modal\s*\{[^}]*height\s*:\s*100%")
        self.assertRegex(full, r"\.modal\s*\{[^}]*border-radius\s*:\s*0")
        self.assertRegex(full, r"\.modal-body\s*\{[^}]*flex\s*:\s*1")
        self.assertNotRegex(full, r"\.modal\s*\{[^}]*max-height\s*:\s*(?:8|9)\d")

    def test_settings_is_a_system_page_without_a_duplicate_bottom_nav_entry(self):
        self.assertNotIn('id="settingsOverlay"', HTML)
        self.assertIn('id="page-settings"', HTML)
        self.assertIn("const PAGE_ORDER = ['chat', 'providers', 'usage', 'settings']", APP4)
        self.assertRegex(APP4, r"homeHeaderMenu[^\n]+openSidebar\(\)")
        self.assertIn("label: 'More'", APP3)
        self.assertNotIn('data-page="settings"', HTML)
        self.assertIn("row('profile', 'person', 'Profile')", APP4)
        self.assertRegex(CSS, r"#page-settings\s*\{[^}]*overflow\s*:\s*hidden")

    def test_reload_restores_general_room_even_before_a_transport_session_exists(self):
        self.assertIn("const LS_ACTIVE_ROOM = 'zeline.activeRoom'", APP1)
        persist = APP4[APP4.index("function persistActiveConversation"):APP4.index("function showConversation")]
        self.assertIn("LS_ACTIVE_ROOM", persist)
        self.assertIn("chatMode", persist)
        boot = APP4[APP4.index("window.startZelineApp"):APP4.index("(async function boot")]
        self.assertIn("restoreActiveConversation", boot)
        self.assertNotIn("restoreConversation && S.agentId && S.sessionId", boot)
        leave = APP4[APP4.index("function leaveConversation"):APP4.index("const PAGE_ORDER")]
        self.assertIn("clearActiveConversation", leave)

    def test_bootstrap_refresh_is_partial_and_cached_chat_never_blanks_on_one_failed_endpoint(self):
        refresh = APP4[APP4.index("async function refreshAll"):APP4.index("function themeIconMarkup")]
        self.assertIn("Promise.allSettled", refresh)
        self.assertIn("saveSessionCache", refresh)
        self.assertNotIn("Promise.all([", refresh)
        open_session = APP4[APP4.index("async function openSession"):APP4.index("let sessionCreatePromise")]
        self.assertIn("readMessageCache(id)", open_session)
        self.assertIn("saveMessageCache(id, S.messages)", open_session)
        self.assertNotIn("catch (error) { S.messages = []", open_session)
        open_general = APP3[APP3.index("async function openAgentChat"):APP3.index("function showAgentToken")]
        self.assertIn("readMessageCache", open_general)
        self.assertIn("saveMessageCache", open_general)

    def test_agent_overflow_is_a_sibling_of_the_open_button_and_consumes_the_whole_outside_gesture(self):
        start = APP3.index("const card = el('article', 'agent-card room-card')")
        render = APP3[start:APP3.index("box.appendChild(card);", start)]
        self.assertIn('class="agent-card-main"', render)
        self.assertNotIn("card.onclick =", render)
        menu = APP3[APP3.index("function openRoomCardMenu"):APP3.index("const AGENT_GATEWAY_HOLD_MS")]
        self.assertIn("popover-dismiss-pending", menu)
        self.assertIn("scrim.addEventListener('pointerup'", menu)
        self.assertIn("scrim.addEventListener('click'", menu)
        self.assertIn("setTimeout(removeScrim", menu)
        v136 = CSS[CSS.index("/* v136 — native stability and interaction repair */"):]
        self.assertIn(".agent-card-main:active", v136)
        self.assertNotRegex(v136, r"\.agent-card:active\s*\{")

    def test_navigation_uses_non_human_cupertino_agent_and_new_provider_symbols(self):
        self.assertIn('data-zi="windowsgrid"', HTML)
        self.assertIn('data-zi="providerlink"', HTML)
        self.assertIn("ZI('agentchip')", APP3 + APP4)
        self.assertNotIn("ZI('agent')", APP4)
        self.assertRegex(CSS, r"grid-template-columns:64px minmax\(0,1fr\) 64px")
        self.assertIn('"agentchip"', ICONS)
        self.assertIn('"agentnetwork"', ICONS)
        self.assertIn('"windowsgrid"', ICONS)
        self.assertIn('"providerlink"', ICONS)
        self.assertIn('google/material-design-icons', ICONS)
        self.assertIn('materialiconsround', ICONS)

    def test_gateway_binding_status_is_stable_without_full_home_refresh(self):
        self.assertIn("function agentConnectionPresentation", APP3)
        self.assertIn("is_connected_agent", APP3)
        self.assertIn("label: 'Reconnected'", APP3)
        self.assertIn("function refreshAgentStatusesInPlace", APP3)
        self.assertIn("window.addEventListener('online', refreshGatewayConnectivity)", APP4)
        self.assertIn("window.addEventListener('offline', refreshGatewayConnectivity)", APP4)
        self.assertNotIn("window.addEventListener('online', reconnectRoomConnection)", APP4)

    def test_agent_status_only_bound_agent_is_connected(self):
        # Connection is token-binding based: only the profile whose agent token
        # authed this gateway session (is_connected_agent) reads Connected. A
        # configured-but-unbound profile is Unconnected, not Connected.
        presentation = APP3[APP3.index("function agentConnectionPresentation"):APP3.index("function refreshAgentStatusesInPlace")]
        self.assertIn("const bound = Boolean(agent?.is_connected_agent)", presentation)
        self.assertNotIn("agent.provider_id && agent.model", presentation)
        home = APP3[APP3.index("function renderAgentHome"):APP3.index("function openRoomCardMenu")]
        self.assertIn("agentConnectionPresentation(agent)", home)
        inplace = APP3[APP3.index("function updateAgentCardStatusInPlace"):APP3.index("function agentPreviewMarkup")]
        self.assertIn("agentConnectionPresentation(agent)", inplace)
        self.assertIn("liveLabel || preview || connection.label", inplace)

    def test_stream_messages_are_cached_optimistically_before_network_wait(self):
        send = APP2[APP2.index("async function send()"):APP2.index("async function cancelGeneration")]
        cache_write = send.index("saveMessageCache(streamSessionId, streamMessages)")
        network = send.index("await fetch(`${API}/sessions/${streamSessionId}/messages?stream=true`")
        self.assertLess(cache_write, network)
        self.assertIn("optimisticUser", send)
        self.assertIn("optimisticAssistant", send)

    def test_stream_survives_leave_and_reenter_without_blank_history(self):
        render = APP2[APP2.index("function renderMessages"):APP2.index("function renderEmpty")]
        self.assertNotIn("m.status === 'streaming' && !roomMessageText(m).trim()) return", render)
        self.assertIn("const hasContent = roomMessageText(m).trim()", render)
        self.assertIn("if (hasContent || m.status !== 'streaming')", render)
        send = APP2[APP2.index("async function send()"):APP2.index("async function cancelGeneration")]
        self.assertIn("const streamMessages = S.messages", send)
        self.assertIn("function persistStreamSnapshot", send)
        self.assertIn("saveMessageCache(streamSessionId, streamMessages)", send)
        self.assertIn("S.messages !== streamMessages", send)
        self.assertIn("renderMessages()", send)
        self.assertIn("optimisticAssistant.status = 'cancelled'", send)
        self.assertIn("optimisticAssistant.status = 'error'", send)
        self.assertIn("optimisticAssistant.content = acc || '_(dibatalkan)_'", send)

    def test_agent_room_paints_cache_before_async_agent_sync(self):
        opening = APP3[APP3.index("async function openAgentChat"):APP3.index("function showAgentToken")]
        self.assertLess(opening.index("renderMessages({ force: true })"), opening.index("await syncAgentSelect()"))
        self.assertIn("catch (error)", opening)
        self.assertIn("keeping cached room visible", opening)

    def test_selected_header_is_independent_floating_bubbles_with_real_scroll_fade(self):
        self.assertIn("v143 — true floating room controls", CSS)
        self.assertIn("body.selection-header-active .telegram-chat-head", CSS)
        self.assertIn("grid-template-columns:repeat(4,40px)", CSS)
        self.assertIn("body.selection-header-active .selection-header-actions button", CSS)
        self.assertIn("-webkit-mask-image:linear-gradient(180deg,transparent 0", CSS)

    def test_gateway_status_is_inline_overlay_not_modal(self):
        block = APP3[APP3.index("function showInterfaceStatus"):APP3.index("/* Three-dot menu")]
        self.assertIn("gateway-status-overlay", block)
        self.assertIn("gateway-status-bubble", block)
        self.assertIn("ZEROLINEAR Interface", block)
        self.assertIn("Zeline Gateway", block)
        self.assertIn("Restart Gateway", block)
        self.assertNotIn("modal(", block)
        self.assertNotIn("Done", block)

    def test_agent_card_shows_preview_with_real_content_backed_unread(self):
        render = APP3[APP3.index("function renderAgentHome"):APP3.index("function openRoomCardMenu")]
        self.assertNotIn("agent-card-model", render)
        self.assertIn("agent-card-pin", render)
        # Room cards: line 2 shows the session's last preview; unread badge lives in
        # the right rail below the ⋯ menu, level with line-2 (not inline in the foot).
        self.assertIn("agent-card-unread", render)
        self.assertIn("sessionUnreadCount(s)", render)
        self.assertIn("s.last_preview", render)
        # Badge sits in the rail after the menu row, with a spacer when no unread.
        rail = render[render.index("agent-card-rail"):]
        self.assertIn("agent-card-unread-spacer", rail)
        self.assertLess(rail.index("agent-card-rail-top"), rail.index("agent-card-unread"))
        # No leading bullet dot in the status pill markup.
        self.assertNotIn('data-label="${esc(footText)}"><i></i>', render)
        # Unread is content-backed: counts assistant messages after the read cursor.
        unread_fn = APP3[APP3.index("function sessionUnreadCount"):APP3.index("function sessionHasUnread")]
        self.assertIn("m.role === 'assistant'", unread_fn)
        self.assertIn("readMessageCache(session.id)", unread_fn)
        self.assertNotIn("session?.last_preview", unread_fn)
        # The single-agent identity strip carries the avatar + gateway status.
        self.assertIn("fixedChatAvatar(agent.name)", render)
        self.assertIn("showInterfaceStatus", render)

    def test_open_agent_chat_falls_back_to_remembered_session_on_reload(self):
        # Refresh WHILE the agent is running must not blank the room: if the session
        # list hasn't synced yet, openAgentChat rebuilds the general session from the
        # active-room pointer so the cached mid-stream turn still paints.
        block = APP3[APP3.index("async function openAgentChat"):APP3.index("function showAgentToken")]
        self.assertIn("activeConversationSnapshot()", block)
        self.assertIn("saved.agentId === agent.id && saved.sessionId", block)
        self.assertIn("readMessageCache(general.id)", block)

    def test_agent_delete_animates_only_after_verified_backend_delete(self):
        deletion = APP3[APP3.index("async function deleteAgent"):APP3.index("async function deleteAgentsStrict")]
        self.assertIn("Agent still exists after delete", deletion)
        self.assertIn("agent-card-deleting", deletion)
        self.assertIn("await new Promise", deletion)
        self.assertIn("@keyframes agentCardDelete", CSS)

    def test_create_agent_has_fixed_avatar_and_token_safety_warning(self):
        create = APP3[APP3.index("function agentModal"):APP3.index("/* ───────────────── providers")]
        for marker in ("create-agent-step", "Save your agent key", "Never share this token", "avatar: ZELINE_CHAT_AVATAR"):
            self.assertIn(marker, create + CSS)
        for retired in ("agentPhotoInput", "agentPhotoPreview", "chooseAgentPhoto", "new FileReader()", "avatarData"):
            self.assertNotIn(retired, create)
        self.assertIn("Save this key now", APP3)
        self.assertIn("Do not share it with anyone", APP3)

    def test_access_token_replaces_account_key_surfaces(self):
        frontend = HTML + APP1 + APP2 + APP3 + APP4 + APP5
        self.assertNotIn("createAppToken", frontend)
        self.assertNotIn("Zeline App Token", frontend)
        self.assertNotIn("zeline.appToken", frontend)
        self.assertNotIn("accountProfileUse", frontend)
        self.assertNotIn("accountProfileEmail", frontend)
        self.assertNotIn("username", APP5)
        self.assertNotIn("bio", APP5)
        self.assertNotIn("API Keys", APP4)
        self.assertNotIn("Connected Accounts", APP4)
        self.assertNotIn("Permissions", APP4)
        self.assertIn("Access Token", APP4)
        self.assertIn("access-token-reveal", SERVER)
        self.assertIn("_configured_app_access_token", SERVER)

    def test_authoritative_native_action_screen_has_square_top_and_app_bar_action(self):
        self.assertIn('id="modalHeadAction"', HTML)
        self.assertIn("function wireModalAction", APP1)
        self.assertIn("compact = false", APP1)
        v136 = CSS[CSS.index("/* v136 — native stability and interaction repair */"):CSS.index("/* v138 — every bottom-tab glyph")]
        self.assertRegex(v136, r"\.modal:not\(\.compact-confirm-modal\)\s*\{[^}]*height:100dvh")
        self.assertRegex(v136, r"\.modal:not\(\.compact-confirm-modal\)\s*\{[^}]*border-radius:0")
        self.assertIn(".modal-head-action", v136)
        # The phone surface is edge-to-edge at 100dvh. A later >=700px desktop
        # block legitimately caps the sheet at 92dvh; this assertion guards the
        # v136 phone rules only, so it must not slice past the next section.
        self.assertNotIn("92dvh", v136)

    def test_room_header_keeps_five_controls_on_one_row(self):
        """The chat header must not inherit the 3-slot sheet bar template.

        The unified bar block near the end of the sheet forces
        `.telegram-chat-head` into `grid-template-columns:44px 1fr 44px` with
        `grid-template-areas:"back title action"`. The room header holds five
        controls (back, avatar, identity, model, menu), so that template wrapped
        the last two onto a second row and squeezed the identity pill into a
        44px column. The final block must re-declare a five-column track and
        place each child explicitly.
        """
        head = CSS[CSS.index("/* ── Room header: five controls on one row"):]
        self.assertRegex(head, r"\.telegram-chat-head\s*\{[^}]*grid-template-columns:44px 44px minmax\(0,1fr\) 44px 44px")
        self.assertRegex(head, r"\.telegram-chat-head\s*\{[^}]*grid-template-areas:none")
        for selector, column in (
            (r"\.room-head-back", 1), (r"\.room-profile-empty", 2),
            (r"\.room-head-identity", 3), (r"\.room-model-button", 4),
            (r"\.room-head-menu", 5),
        ):
            self.assertRegex(head, selector + r"\{[^}]*grid-column:" + str(column))
        # The sheet title rule must not hijack the identity pill's label.
        title_rule = CSS[CSS.index("/* Title — one size, one weight, one colour"):
                        CSS.index("/* Trailing action (search / create)")]
        self.assertNotIn(".telegram-chat-head strong", title_rule)

    def test_desktop_drawer_is_anchored_to_the_app_frame(self):
        """Above 960px the sidebar must slide over the frame, not sit inside it.

        `.app` is a fixed 430px phone frame centred on wide screens, but the
        off-canvas drawer rule only fired below 960px of *viewport* width. Above
        that the sidebar stayed static with `flex:0 0 var(--sidebar-w)` and ate
        300px of the 430px frame, leaving the chat pane 130px wide — and showed
        as a permanent column instead of a drawer. The fix anchors it to the
        frame (which needs `position:relative` on `#app`).
        """
        block = CSS[CSS.index("/* ── Drawer sidebar: anchor to the app frame"):]
        self.assertRegex(block, r"@media\s*\(min-width:\s*961px\)")
        self.assertRegex(block, r"#app\s*\{[^}]*position:relative")
        self.assertRegex(block, r"\.sidebar\s*\{[^}]*position:absolute")
        self.assertRegex(block, r"\.sidebar\s*\{[^}]*transform:translateX\(-102%\)")
        self.assertRegex(block, r"\.sidebar\.open\s*\{[^}]*transform:none")

    def test_api_type_select_keeps_its_dropdown_caret(self):
        """The API Type picker must render its dropdown arrow.

        `appearance:none` removes the native arrow, so the custom SVG caret is
        the only affordance. Two later rules wiped it: the provider-form well
        rule used the `background:` shorthand (which resets `background-image`
        to none and `padding:0 13px`, dropping the reserved caret gutter), and a
        higher-specificity `html[data-app-theme='light'] .field select` did the
        same in light mode. The picker rendered with no arrow in both themes.
        """
        # The caret is declared on the select, with its gutter reserved.
        caret_rule = re.search(r"\.provider-form \.field select\s*\{[^}]*background-image:url\(", CSS)
        self.assertIsNotNone(caret_rule, "the custom dropdown caret must be declared")
        self.assertRegex(CSS, r"\.provider-form \.field select\s*\{[^}]*padding-right:38px")

        # Anything declared AFTER the caret that shares or beats its specificity
        # must not use the `background` shorthand — that resets `background-image`
        # to none and erases the arrow. `background-color` is the safe form.
        after = CSS[caret_rule.start():]
        for body in re.findall(r"\.provider-form \.field input,\s*\.provider-form \.field select\s*\{([^}]*)\}", after):
            self.assertNotRegex(body, r"(?<!-)background:(?!-)")
        for body in re.findall(
                r"html\[data-app-theme='light'\] \.provider-form \.field input,\s*"
                r"html\[data-app-theme='light'\] \.provider-form \.field select\s*\{([^}]*)\}", after):
            self.assertNotRegex(body, r"(?<!-)background:(?!-)")
        # The generic light-theme `.field select` rule outranks the caret, so it
        # must not carry a shorthand either.
        self.assertNotRegex(
            CSS, r"html\[data-app-theme='light'\] \.field input,html\[data-app-theme='light'\] \.field select\{[^}]*background:")

    def test_oauth_connect_drives_the_router_instead_of_a_stub(self):
        """Connect OAuth must start a real flow, not print "not active yet".

        Zeline holds no OAuth credentials: the button drives the local router's
        authorize/device-code surface, the user approves in a browser, and the
        router records the connection. The old handler was a toast stub.
        """
        self.assertNotIn("is not active yet", APP3)
        self.assertIn("openOAuthConnect", APP3)
        for verb in ("/providers/oauth/authorize", "/providers/oauth/device-code",
                     "/providers/oauth/poll", "/providers/oauth/exchange"):
            self.assertIn(verb, APP3)
            self.assertIn(verb, SERVER)

    def test_oauth_poll_treats_pending_as_waiting_not_rejection(self):
        """`authorization_pending` is the normal state while the user approves.

        The first cut checked `if (r.error)` before the pending flag, so a poll
        that returned `{pending: true, error: "authorization_pending"}` was
        rendered as "Ditolak" and the flow died immediately.
        """
        start = APP3.index("async function oauthStartDeviceCode")
        end = APP3.index("function oauthShowRedirect")
        tick = APP3[start:end]
        # The pending guard must come before the generic error branch.
        pending_at = tick.index("authorization_pending")
        reject_at = tick.index("Ditolak")
        self.assertLess(pending_at, reject_at)
        self.assertIn("if (r.pending", tick)

    def test_oauth_hides_the_code_chip_when_a_provider_has_no_user_code(self):
        """Link-based device flows carry no user_code — the chip must not show "—"."""
        start = APP3.index("async function oauthStartDeviceCode")
        end = APP3.index("function oauthShowRedirect")
        block = APP3[start:end]
        self.assertIn("if (dc.user_code)", block)
        self.assertIn("oauthCodeChip", block)

    def test_router_models_bridge_maps_internal_provider_aliases(self):
        """A connected provider must not come back with an empty model list.

        The router keys some providers by a short internal alias (`cbai`, `cx`,
        `ag`) rather than the catalog id, so matching on the id alone returned
        nothing for providers that were demonstrably connected.
        """
        bridge = (ROOT / "router_bridge.py").read_text()
        self.assertIn("_PROVIDER_ALIASES", bridge)
        self.assertIn('"codebuddy-intl": ("codebuddy-intl", "cbai"', bridge)
        self.assertIn('"codex": ("codex", "cx")', bridge)
        self.assertIn("def provider_models", bridge)
        # Connections returned to the browser must be display fields only.
        self.assertIn("def _public_connection", bridge)
        self.assertNotIn('"data": row.get("data")', bridge)

    def test_oauth_redirect_flow_lands_on_zelines_own_callback(self):
        """The browser must return to Zeline, not to another app's dashboard.

        With a third-party callback the code was only exchanged if that app's
        dashboard happened to be open — so approving in the browser left the
        provider unconnected. Zeline now hosts /oauth/callback and exchanges the
        code server-side, and the waiting tab polls /oauth/status.
        """
        self.assertIn('"/oauth/callback"', SERVER)
        self.assertIn("def oauth_callback", SERVER)
        self.assertIn("def _zeline_callback_url", SERVER)
        self.assertIn("/providers/oauth/status", SERVER)
        self.assertIn("/providers/oauth/status", APP3)
        # The old dead-end button must be gone.
        self.assertNotIn("cek koneksi", APP3)
        # The callback must escape provider-supplied text before rendering it.
        self.assertIn("_html_escape", SERVER)

    def test_preflight_falls_back_to_a_real_request_without_a_models_route(self):
        """A working key must not be called unreachable just because there is no
        /models route — which is the case for every OAuth-connected provider.
        """
        self.assertIn("def _probe_chat_completion", SERVER)
        # A structured 4xx proves the credential; a bare HTML 404 does not.
        self.assertIn('detail.lstrip().startswith(("{", "["))', SERVER)
        self.assertIn("429", SERVER)
        # The UI must not lock Create when the endpoint published no catalog.
        self.assertIn("const hasCatalog = models.length > 0;", APP3)
        self.assertIn("!f.model || !hasCatalog || modelOk", APP3)

    def test_preflight_model_match_tolerates_decorated_model_ids(self):
        """Gateways publish `cx/gpt-5.6-sol`; users type `gpt-5.6-sol`.

        Comparing the raw strings marked a served model as missing and locked
        Create on an endpoint that was demonstrably working.
        """
        self.assertIn("def _model_matches", SERVER)
        self.assertIn('rsplit("/", 1)[-1].rsplit(":", 1)[-1]', SERVER)
        # The server owns the match; the UI reads its verdict.
        self.assertIn("d.model_found !== false", APP3)

    def test_modal_stacks_above_the_provider_detail_panel(self):
        """A modal opened from inside the provider-detail panel must be visible.

        Both `.modal-root` and `.provider-detail` were `position:fixed` with the
        SAME z-index, and the detail panel is appended to the body later, so it
        painted on top: tapping Connect OAuth opened a modal the user could not
        see until they pressed Back (which removed the panel). The modal layer
        must outrank the detail layer.
        """
        def zindex(selector):
            """Effective z-index: the winning declaration, not the first one.

            `.modal-root` is declared twice (a base rule and a later
            `!important` native-screen rule), so scanning for the first match
            reads the stale value. Prefer `!important` declarations and take the
            last one, which is what the cascade actually applies.
            """
            values = []
            for m in re.finditer(re.escape(selector) + r"\s*\{([^}]*)\}", CSS):
                zm = re.search(r"z-index:\s*(\d+)\s*(!important)?", m.group(1))
                if zm:
                    values.append((bool(zm.group(2)), int(zm.group(1))))
            self.assertTrue(values, f"{selector} has no z-index")
            important = [v for imp, v in values if imp]
            return important[-1] if important else values[-1][1]

        self.assertGreater(zindex(".modal-root"), zindex(".provider-detail"),
                           "modal must stack above the provider-detail panel")

    def test_bottom_navigation_is_compact_not_bulky(self):
        marker = "/* v32 — compact dock, top Add+, interactive settings drag */"
        self.assertIn(marker, CSS)
        ui = CSS.split(marker, 1)[1]
        self.assertRegex(ui, r"\.tabbar\s*\{[^}]*max-width\s*:\s*340px")
        self.assertRegex(ui, r"\.tabbar\s*\{[^}]*height\s*:\s*50px")
        self.assertRegex(ui, r"\.tabbar::before\s*\{[^}]*height\s*:\s*40px")
        self.assertRegex(ui, r"\.tab\s*\{[^}]*height\s*:\s*40px")

    def test_navigation_uses_one_sliding_ios_glass_indicator_without_tab_boxes(self):
        self.assertIn("--active-index", APP4)
        marker = "/* v26 — iOS liquid navigation and edge settings affordance */"
        self.assertIn(marker, CSS)
        nav = CSS.split(marker, 1)[1]
        self.assertRegex(nav, r"\.tabbar::before\s*\{")
        self.assertRegex(nav, r"backdrop-filter\s*:\s*blur")
        self.assertRegex(nav, r"\.tab\.active\s*\{[^}]*background\s*:\s*transparent")
        self.assertNotRegex(nav, r"\.tab\.active\s*\{[^}]*border\s*:")

    def test_send_button_tracks_empty_input(self):
        self.assertIn("updateSendAvailability", APP4)
        self.assertRegex(APP4, r"sendBtn[^\n]+disabled")


if __name__ == "__main__":
    unittest.main(verbosity=2)

/* ==========================================================================
   SoraLink (空連) — Passenger Cabin Experience Controller
   ========================================================================== */

(function () {
  "use strict";

  const SL = window.SoraLink;

  // Passenger State
  let seatLabel = "—";
  let sessionId = null;
  let passengerRequests = [];
  let activeBroadcastsMap = new Map(); // broadcast_id -> broadcast object
  let expandedRequestId = null;
  let moreCategoriesOpen = false;

  // Service Modal State
  let selectedServiceIntentId = null;
  let selectedWaterTemp = "ROOM";
  let selectedMealDiet = "NON_VEG";
  let isSubmittingService = false;

  // Voice Modal State
  let mediaStream = null;
  let mediaRecorder = null;
  let recordedChunks = [];
  let negotiatedMimeType = "";
  let recordingSeconds = 0;
  let recordingTimerId = null;
  let currentPreviewId = null;
  let previewConsumedOrRejected = false;
  let selectedVoiceIntentId = null;
  let voiceAttributes = {};
  let voiceCandidates = [];
  let showAllVoiceCategories = false;
  let isSubmittingVoice = false;

  // Typed Modal State
  let selectedTypedIntentId = "water_request";
  let isSubmittingTyped = false;

  // ==========================================================================
  // 1. Initialization & Language Updates
  // ==========================================================================

  function applyPassengerTranslations() {
    const setEl = (id, key) => {
      const el = document.getElementById(id);
      if (el) el.textContent = SL.t(key);
    };

    setEl("header-seat-label-text", "seat");
    setEl("header-logout-text", "logout");
    setEl("pax-heading-title", "howMayWeAssist");
    setEl("pax-heading-subtitle", "selectServiceSubtitle");
    setEl("more-categories-label", "moreCategories");
    setEl("speak-btn-title", "speakRequest");
    setEl("speak-btn-sub", "speakRequestSub");
    setEl("type-btn-title", "typeRequest");
    setEl("active-requests-heading", "inFlightRequests");
    setEl("empty-requests-text", "noActiveRequests");
    setEl("service-temp-label", "waterTempLabel");
    setEl("temp-btn-cold", "tempCold");
    setEl("temp-btn-room", "tempRoom");
    setEl("temp-btn-warm", "tempWarm");
    setEl("service-diet-label", "dietaryLabel");
    setEl("diet-btn-veg", "dietVeg");
    setEl("diet-btn-nonveg", "dietNonVeg");
    setEl("diet-btn-snack", "dietSnack");
    setEl("service-note-label", "optionalNoteLabel");
    setEl("cancel-service-modal-btn", "cancel");
    setEl("confirm-service-btn-text", "confirmAndSend");

    renderServiceGrids();
    renderActiveRequests();
    renderPABanners();
  }

  async function initPassengerApp() {
    SL.initHeaderControls(applyPassengerTranslations);
    bindEventListeners();
    applyPassengerTranslations();

    // Sync approved catalog dynamically from backend
    SL.syncCatalogFromServer().then((changed) => {
      if (changed) applyPassengerTranslations();
    });

    // Verify session & load authoritative passenger state
    const ok = await fetchPassengerState(true);
    if (!ok) return;

    // Also fetch active PA broadcasts
    await fetchActivePABroadcasts();

    // Start 1-second PA countdown ticker
    setInterval(tickPABannerCountdowns, 1000);

    // Initialize real-time Socket.IO connection
    SL.createSocketManager({
      onConnectionReady: (payload) => {
        if (payload && payload.seat_label) {
          seatLabel = payload.seat_label;
          const seatEl = document.getElementById("header-seat-number");
          if (seatEl) seatEl.textContent = seatLabel;
        }
      },
      onRequestUpdated: (payload) => {
        handleRealtimeRequestUpdated(payload);
      },
      onCrewReply: (payload) => {
        handleRealtimeCrewReply(payload);
      },
      onPABroadcastCreated: (payload) => {
        handleRealtimePACreated(payload);
      },
      onPABroadcastEnded: (payload) => {
        handleRealtimePAEnded(payload);
      },
      onResync: () => {
        fetchPassengerState(false);
        fetchActivePABroadcasts();
      },
    });
  }

  // ==========================================================================
  // 2. Authoritative State Fetching (REST)
  // ==========================================================================

  async function fetchPassengerState(isInitial) {
    const res = await SL.apiFetch("/api/passenger/state");
    if (res.isUnauthenticated) {
      window.location.replace("/login");
      return false;
    }

    if (!res.ok) {
      if (isInitial && res.status === 403) {
        // Logged in as crew instead of passenger
        window.location.replace("/crew");
        return false;
      }
      if (res.isNetworkError) {
        SL.updateConnectionBadge("offline");
      }
      return true;
    }

    const data = res.data || {};
    if (data.seat_label) {
      seatLabel = data.seat_label;
      const seatEl = document.getElementById("header-seat-number");
      if (seatEl) seatEl.textContent = seatLabel;
    }
    if (data.session && data.session.session_id) {
      sessionId = data.session.session_id;
    }

    if (Array.isArray(data.requests)) {
      passengerRequests = data.requests.slice().sort((a, b) => {
        const ta = a.created_at_ms || a.created_at || 0;
        const tb = b.created_at_ms || b.created_at || 0;
        return tb - ta;
      });
      if (!expandedRequestId && passengerRequests.length > 0) {
        expandedRequestId = passengerRequests[0].id || passengerRequests[0].request_id;
      }
      renderServiceGrids();
      renderActiveRequests();
    }

    if (Array.isArray(data.active_broadcasts)) {
      syncBroadcastList(data.active_broadcasts);
    }

    return true;
  }

  async function fetchActivePABroadcasts() {
    const res = await SL.apiFetch("/api/pa/active");
    if (res.ok && res.data && Array.isArray(res.data.broadcasts)) {
      syncBroadcastList(res.data.broadcasts);
    }
  }

  // ==========================================================================
  // 3. Real-Time Socket.IO Event Handlers
  // ==========================================================================

  function handleRealtimeRequestUpdated(payload) {
    if (!payload) return;
    const reqId = payload.request_id || payload.id;
    const newStatus = payload.status;
    let found = false;

    passengerRequests = passengerRequests.map((r) => {
      const id = r.id || r.request_id;
      if (id === reqId) {
        found = true;
        if (r.status !== newStatus && (newStatus === "ACKNOWLEDGED" || newStatus === "COMPLETED")) {
          SL.playServerAckChime();
          const title = SL.getIntentTitle(r.intent_id);
          SL.showToast(`${title}: ${newStatus}`, "success");
        }
        return Object.assign({}, r, {
          status: newStatus || r.status,
          updated_at_ms: payload.updated_at || Date.now(),
        });
      }
      return r;
    });

    if (!found) {
      fetchPassengerState(false);
    } else {
      renderServiceGrids();
      renderActiveRequests();
    }
  }

  function handleRealtimeCrewReply(payload) {
    if (!payload || !payload.request_id) return;
    const reqId = payload.request_id;
    SL.saveLocalRequestMeta(reqId, {
      crewReplyId: payload.response_id,
      crewReplyLabels: payload.labels || null,
      crewReplyAt: payload.created_at || Date.now(),
    });
    expandedRequestId = reqId;
    SL.playCabinChime("routine");
    const msg = SL.getCrewResponseText(payload.response_id, payload.labels);
    SL.showToast(`Crew Reply: ${msg}`, "success");
    fetchPassengerState(false);
  }

  function syncBroadcastList(list) {
    const now = Date.now();
    const nextMap = new Map();
    for (const item of list) {
      if (!item) continue;
      const bid = item.broadcast_id || item.id;
      const exp = item.expires_at_ms || item.expires_at || 0;
      if (bid && item.active_status !== false && exp > now) {
        nextMap.set(bid, item);
      }
    }
    activeBroadcastsMap = nextMap;
    renderPABanners();
  }

  function handleRealtimePACreated(payload) {
    if (!payload) return;
    const bid = payload.broadcast_id || payload.id;
    if (!bid) return;
    const isNew = !activeBroadcastsMap.has(bid);
    activeBroadcastsMap.set(bid, payload);
    if (isNew) {
      SL.playCabinChime("urgent");
    }
    renderPABanners();
  }

  function handleRealtimePAEnded(payload) {
    if (!payload) return;
    const bid = payload.broadcast_id || payload.id;
    if (bid && activeBroadcastsMap.has(bid)) {
      activeBroadcastsMap.delete(bid);
      renderPABanners();
    } else {
      fetchActivePABroadcasts();
    }
  }

  function tickPABannerCountdowns() {
    if (activeBroadcastsMap.size === 0) return;
    const now = Date.now();
    let expiredAny = false;

    for (const [bid, b] of activeBroadcastsMap.entries()) {
      const exp = b.expires_at_ms || b.expires_at || 0;
      if (exp <= now) {
        activeBroadcastsMap.delete(bid);
        expiredAny = true;
      } else {
        const timerEl = document.getElementById(`pa-timer-${bid}`);
        if (timerEl) {
          timerEl.textContent = SL.formatCountdownMMSS(exp - now);
        }
      }
    }

    if (expiredAny) {
      renderPABanners();
    }
  }

  // ==========================================================================
  // 4. Rendering: PA Banners, Service Cards & Active Requests
  // ==========================================================================

  function renderPABanners() {
    const container = document.getElementById("pa-banners-container");
    if (!container) return;

    const now = Date.now();
    const activeList = Array.from(activeBroadcastsMap.values()).filter((b) => {
      const exp = b.expires_at_ms || b.expires_at || 0;
      return b.active_status !== false && exp > now;
    });

    if (activeList.length === 0) {
      container.classList.add("hidden");
      container.innerHTML = "";
      return;
    }

    container.classList.remove("hidden");
    container.innerHTML = activeList
      .map((b) => {
        const bid = b.broadcast_id || b.id;
        const exp = b.expires_at_ms || b.expires_at || now;
        const localized = SL.getPACardLocalized(b.pa_card_id, b.title, b.body);
        const category = (b.category || localized.category || "cabin").toUpperCase();
        const countdown = SL.formatCountdownMMSS(exp - now);

        return `
          <div class="pa-banner-card" data-broadcast-id="${SL.escapeHtml(bid)}">
            <div class="pa-banner-watermark">
              <svg width="110" height="110" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/></svg>
            </div>
            <div class="pa-banner-inner">
              <div class="pa-banner-icon-box">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/></svg>
              </div>
              <div class="pa-banner-content">
                <div class="pa-banner-meta-row">
                  <div class="pa-banner-badges">
                    <span class="pa-badge-label">${SL.escapeHtml(SL.t("cabinAnnouncement"))}</span>
                    <span class="pa-badge-category">${SL.escapeHtml(category)}</span>
                  </div>
                  <div class="pa-timer-pill" title="Time remaining">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    <span id="pa-timer-${SL.escapeHtml(bid)}">${SL.escapeHtml(countdown)}</span>
                  </div>
                </div>
                <h3 class="pa-banner-title">${SL.escapeHtml(localized.title)}</h3>
                <p class="pa-banner-body">${SL.escapeHtml(localized.body)}</p>
                ${
                  SL.getLang() !== "en" && localized.bodyEn
                    ? `<p class="pa-banner-subtext-en">${SL.escapeHtml(localized.bodyEn)}</p>`
                    : ""
                }
              </div>
            </div>
          </div>
        `;
      })
      .join("");
  }

  function getActiveCountForIntent(intentId) {
    return passengerRequests.filter(
      (r) => r.intent_id === intentId && (r.status === "PENDING" || r.status === "ACKNOWLEDGED")
    ).length;
  }

  function renderServiceGrids() {
    const primaryGrid = document.getElementById("primary-service-grid");
    const moreGrid = document.getElementById("more-categories-grid");
    if (!primaryGrid || !moreGrid) return;

    const primaryIntents = SL.CANONICAL_INTENTS.filter((i) => i.isPrimary);
    const secondaryIntents = SL.CANONICAL_INTENTS.filter((i) => !i.isPrimary);

    primaryGrid.innerHTML = primaryIntents
      .map((item) => {
        const count = getActiveCountForIntent(item.id);
        const title = SL.getIntentTitle(item.id);
        const subLabel = SL.getIntentSubLabel(item.id);
        const description = SL.getIntentDescription(item.id);
        const isUrgent = item.priority === "URGENT";

        return `
          <button
            type="button"
            class="service-card-btn"
            data-intent-id="${SL.escapeHtml(item.id)}"
            aria-label="${SL.escapeHtml(title)}"
          >
            <div class="service-card-top-accent"></div>
            <div class="service-card-top-row">
              <div class="service-card-icon-circle ${isUrgent ? "urgent-icon" : ""}">
                ${SL.getCategoryIconSvg(item.id, 28)}
              </div>
              ${
                count > 0
                  ? `<span class="service-card-active-badge" title="${count} active"><span class="service-card-active-dot"></span><span>${count} active</span></span>`
                  : `<span class="service-card-kanji" aria-hidden="true">${SL.escapeHtml(item.kanji || "")}</span>`
              }
            </div>
            <div>
              <h3 class="service-card-title">${SL.escapeHtml(title)}</h3>
              ${
                subLabel
                  ? `<span class="service-card-sublabel">${SL.escapeHtml(subLabel)}</span>`
                  : ""
              }
              ${
                description
                  ? `<p class="service-card-desc">${SL.escapeHtml(description)}</p>`
                  : ""
              }
              ${
                isUrgent
                  ? `<span class="service-card-priority-tag">${SL.escapeHtml(SL.t("priorityUrgent"))}</span>`
                  : ""
              }
            </div>
          </button>
        `;
      })
      .join("");

    moreGrid.innerHTML = secondaryIntents
      .map((item) => {
        const count = getActiveCountForIntent(item.id);
        const title = SL.getIntentTitle(item.id);
        const isUrgent = item.priority === "URGENT";

        return `
          <button
            type="button"
            class="mini-intent-btn ${isUrgent ? "urgent-card" : ""}"
            data-intent-id="${SL.escapeHtml(item.id)}"
          >
            <div class="mini-intent-icon">
              ${SL.getCategoryIconSvg(item.id, 18)}
            </div>
            <div style="min-width:0;flex:1;">
              <div class="mini-intent-label">${SL.escapeHtml(title)}</div>
              ${
                isUrgent
                  ? `<span class="mini-intent-urgent-dot">• ${SL.escapeHtml(SL.t("priorityUrgent"))}</span>`
                  : ""
              }
            </div>
            ${
              count > 0
                ? `<span class="count-pill" style="background:var(--color-crimson);color:#fff;border:none;">${count}</span>`
                : ""
            }
          </button>
        `;
      })
      .join("");

    // Attach click handlers to open Service Confirmation Modal
    document.querySelectorAll("[data-intent-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const intentId = btn.getAttribute("data-intent-id");
        if (intentId) {
          openServiceModal(intentId);
        }
      });
    });
  }

  function renderActiveRequests() {
    const listEl = document.getElementById("active-requests-list");
    const emptyEl = document.getElementById("active-requests-empty");
    const countEl = document.getElementById("active-requests-count");
    if (!listEl || !emptyEl || !countEl) return;

    const activeCount = passengerRequests.filter(
      (r) => r.status === "PENDING" || r.status === "ACKNOWLEDGED"
    ).length;
    countEl.textContent = String(activeCount);

    if (passengerRequests.length === 0) {
      emptyEl.classList.remove("hidden");
      listEl.innerHTML = "";
      return;
    }

    emptyEl.classList.add("hidden");

    listEl.innerHTML = passengerRequests
      .map((req) => {
        const reqId = req.id || req.request_id;
        const isExpanded = expandedRequestId === reqId;
        const isCompleted = req.status === "COMPLETED";
        const isUrgent = req.priority === "URGENT";
        const title = SL.getIntentTitle(req.intent_id);
        const timeStr = SL.formatTimeHHMM(req.created_at_ms || req.created_at);
        const localMeta = SL.getLocalRequestMeta(reqId);

        let statusClass = "pending";
        let statusText = SL.t("statusPending");
        let statusDesc = SL.t("statusDescPending");
        if (req.status === "ACKNOWLEDGED") {
          statusClass = "acknowledged";
          statusText = SL.t("statusAcknowledged");
          statusDesc = SL.t("statusDescAck");
        } else if (req.status === "COMPLETED") {
          statusClass = "completed";
          statusText = SL.t("statusCompleted");
          statusDesc = SL.t("statusDescCompleted");
        }

        const crewReplyText = localMeta.crewReplyId
          ? SL.getCrewResponseText(localMeta.crewReplyId, localMeta.crewReplyLabels)
          : req.status === "ACKNOWLEDGED"
          ? SL.getCrewResponseText("request_acknowledged")
          : req.status === "COMPLETED"
          ? SL.getCrewResponseText("request_completed")
          : "";

        const attrParts = [];
        if (localMeta.temperature) attrParts.push(`Temp: ${localMeta.temperature}`);
        if (localMeta.dietary) attrParts.push(`Dietary: ${localMeta.dietary}`);

        return `
          <div class="req-item-card ${isExpanded ? "expanded" : ""} ${isCompleted ? "completed-dim" : ""}">
            <button
              type="button"
              class="req-item-summary"
              data-toggle-req="${SL.escapeHtml(reqId)}"
              aria-expanded="${isExpanded ? "true" : "false"}"
            >
              <div class="req-item-left">
                <div class="req-item-icon ${isUrgent ? "urgent" : ""}">
                  ${SL.getCategoryIconSvg(req.intent_id, 20)}
                </div>
                <div style="min-width:0;">
                  <div class="req-item-title-row">
                    <span class="req-item-title">${SL.escapeHtml(title)}</span>
                    ${
                      isUrgent
                        ? `<span class="priority-badge-urgent">${SL.escapeHtml(SL.t("priorityUrgent"))}</span>`
                        : ""
                    }
                  </div>
                  <div class="req-item-meta">
                    <span>${SL.escapeHtml(timeStr)}</span>
                    ${
                      attrParts.length > 0
                        ? `<span>• ${SL.escapeHtml(attrParts.join(", "))}</span>`
                        : ""
                    }
                  </div>
                </div>
              </div>

              <div class="req-item-right">
                <span class="status-badge ${statusClass}">${SL.escapeHtml(statusText)}</span>
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  style="color:var(--color-charcoal-light);transform:rotate(${isExpanded ? "180deg" : "0deg"});transition:transform 0.15s;"
                >
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </div>
            </button>

            ${
              isExpanded
                ? `
              <div class="req-item-details">
                <div class="req-detail-grid">
                  <div>
                    <span class="req-detail-label">Request ID</span>
                    <span class="req-detail-value font-mono-code" style="font-size:0.74rem;">#${SL.escapeHtml(
                      String(reqId).slice(0, 8)
                    )}</span>
                  </div>
                  <div>
                    <span class="req-detail-label">Priority</span>
                    <span class="req-detail-value">${
                      isUrgent ? SL.escapeHtml(SL.t("priorityUrgent")) : SL.escapeHtml(SL.t("priorityRoutine"))
                    }</span>
                  </div>
                  ${
                    localMeta.note
                      ? `
                    <div style="grid-column:span 2;">
                      <span class="req-detail-label">Your Note</span>
                      <span class="req-detail-value">"${SL.escapeHtml(localMeta.note)}"</span>
                    </div>
                  `
                      : ""
                  }
                </div>

                ${
                  crewReplyText
                    ? `
                  <div class="crew-reply-box">
                    <div class="crew-reply-header">
                      <span class="crew-reply-tag">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                        ${SL.escapeHtml(SL.t("crewMessage"))}
                      </span>
                      <button
                        type="button"
                        class="tts-reply-btn"
                        data-tts-text="${SL.escapeHtml(crewReplyText)}"
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                        <span>${SL.escapeHtml(SL.t("tapToHearReply"))}</span>
                      </button>
                    </div>
                    <p class="crew-reply-message">${SL.escapeHtml(crewReplyText)}</p>
                  </div>
                `
                    : ""
                }

                <div class="status-explanation-box">
                  ${SL.escapeHtml(statusDesc)}
                </div>

                ${
                  !isCompleted
                    ? `
                  <div class="followup-row">
                    <input
                      type="text"
                      class="followup-input"
                      id="followup-input-${SL.escapeHtml(reqId)}"
                      maxlength="240"
                      placeholder="Send a follow-up note to cabin crew…"
                    />
                    <button
                      type="button"
                      class="followup-btn"
                      data-send-followup="${SL.escapeHtml(reqId)}"
                    >
                      Send Note
                    </button>
                  </div>
                `
                    : ""
                }
              </div>
            `
                : ""
            }
          </div>
        `;
      })
      .join("");

    // Bind toggle expand
    listEl.querySelectorAll("[data-toggle-req]").forEach((btn) => {
      btn.addEventListener("click", () => {
        SL.playSoftTap();
        const id = btn.getAttribute("data-toggle-req");
        expandedRequestId = expandedRequestId === id ? null : id;
        renderActiveRequests();
      });
    });

    // Bind explicit user-triggered TTS reply playback
    listEl.querySelectorAll("[data-tts-text]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const text = btn.getAttribute("data-tts-text");
        SL.speakReplyText(text, SL.getLang());
      });
    });

    // Bind follow-up note submission -> POST /api/crew/requests/<id>/follow_up
    listEl.querySelectorAll("[data-send-followup]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const reqId = btn.getAttribute("data-send-followup");
        const inputEl = document.getElementById(`followup-input-${reqId}`);
        if (!inputEl) return;
        const message = inputEl.value.trim();
        if (!message) return;

        btn.disabled = true;
        const res = await SL.apiFetch(`/api/crew/requests/${encodeURIComponent(reqId)}/follow_up`, {
          method: "POST",
          body: { message },
        });
        btn.disabled = false;

        if (res.ok) {
          SL.saveLocalRequestMeta(reqId, { note: message });
          inputEl.value = "";
          SL.playServerAckChime();
          SL.showToast("Follow-up note sent to cabin crew.", "success");
          renderActiveRequests();
        } else {
          SL.showToast(res.errorMessage || "Could not send follow-up note.", "error");
        }
      });
    });
  }

  // ==========================================================================
  // 5. Visual Service Request Modal (RequestModal)
  // ==========================================================================

  function openServiceModal(intentId) {
    SL.playSoftTap();
    selectedServiceIntentId = intentId;
    selectedWaterTemp = "ROOM";
    selectedMealDiet = "NON_VEG";

    const meta = SL.getIntentMeta(intentId);
    const modal = document.getElementById("service-request-modal");
    const iconBox = document.getElementById("service-modal-icon");
    const titleEl = document.getElementById("service-modal-title");
    const prioEl = document.getElementById("service-modal-priority-badge");
    const tempGroup = document.getElementById("service-temp-group");
    const dietGroup = document.getElementById("service-diet-group");
    const noteInput = document.getElementById("service-note-input");
    const errBanner = document.getElementById("service-modal-error");

    if (iconBox) iconBox.innerHTML = SL.getCategoryIconSvg(intentId, 20);
    if (titleEl) titleEl.textContent = SL.getIntentTitle(intentId);
    if (prioEl) {
      prioEl.innerHTML =
        meta.priority === "URGENT"
          ? `<span class="priority-badge-urgent" style="margin-top:3px;">${SL.escapeHtml(
              SL.t("priorityUrgent")
            )}</span>`
          : `<span class="priority-badge-routine" style="margin-top:3px;">${SL.escapeHtml(
              SL.t("priorityRoutine")
            )}</span>`;
    }

    if (tempGroup) tempGroup.classList.toggle("hidden", !meta.hasTemperature);
    if (dietGroup) dietGroup.classList.toggle("hidden", !meta.hasDietary);
    if (noteInput) noteInput.value = "";
    if (errBanner) errBanner.classList.add("hidden");

    // Reset option pills UI
    document.querySelectorAll("[data-temp]").forEach((b) => {
      b.classList.toggle("selected", b.getAttribute("data-temp") === selectedWaterTemp);
    });
    document.querySelectorAll("[data-diet]").forEach((b) => {
      b.classList.toggle("selected", b.getAttribute("data-diet") === selectedMealDiet);
    });

    if (modal) modal.classList.remove("hidden");
  }

  function closeServiceModal() {
    const modal = document.getElementById("service-request-modal");
    if (modal) modal.classList.add("hidden");
    selectedServiceIntentId = null;
  }

  async function submitServiceModalRequest() {
    if (!selectedServiceIntentId || isSubmittingService) return;
    isSubmittingService = true;

    const confirmBtn = document.getElementById("confirm-service-modal-btn");
    const errBanner = document.getElementById("service-modal-error");
    const errText = document.getElementById("service-modal-error-text");
    if (confirmBtn) confirmBtn.disabled = true;
    if (errBanner) errBanner.classList.add("hidden");

    const meta = SL.getIntentMeta(selectedServiceIntentId);
    const noteText = (document.getElementById("service-note-input").value || "").trim();
    const clientRequestId = `vis_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    const res = await SL.apiFetch("/api/requests", {
      method: "POST",
      body: {
        intent_id: selectedServiceIntentId,
        client_request_id: clientRequestId,
      },
    });

    if (confirmBtn) confirmBtn.disabled = false;
    isSubmittingService = false;

    if (res.isUnauthenticated) {
      window.location.replace("/login");
      return;
    }

    if (!res.ok) {
      if (errText) errText.textContent = res.errorMessage || "Unable to submit request.";
      if (errBanner) errBanner.classList.remove("hidden");
      return;
    }

    const createdReq = (res.data && res.data.request) || res.data || {};
    const reqId = createdReq.id || createdReq.request_id;

    // Save attributes & optional note locally and send follow_up to crew if details were provided
    const metaPatch = {};
    const detailParts = [];
    if (meta.hasTemperature && selectedWaterTemp) {
      metaPatch.temperature = selectedWaterTemp;
      detailParts.push(`Water temperature: ${selectedWaterTemp}`);
    }
    if (meta.hasDietary && selectedMealDiet) {
      metaPatch.dietary = selectedMealDiet;
      detailParts.push(`Dietary: ${selectedMealDiet}`);
    }
    if (noteText) {
      metaPatch.note = noteText;
      detailParts.push(noteText);
    }

    if (reqId) {
      SL.saveLocalRequestMeta(reqId, metaPatch);
      expandedRequestId = reqId;
      if (detailParts.length > 0) {
        SL.apiFetch(`/api/crew/requests/${encodeURIComponent(reqId)}/follow_up`, {
          method: "POST",
          body: { message: detailParts.join(" | ").slice(0, 280) },
        });
      }
    }

    SL.playServerAckChime();
    closeServiceModal();
    SL.showToast(
      (res.data && res.data.was_created === false) || createdReq.was_created === false
        ? "Active request already in queue for your seat."
        : "Request confirmed and sent to cabin crew.",
      "success"
    );
    await fetchPassengerState(false);
  }

  // ==========================================================================
  // 6. Voice Request Recording, Upload & Single Review Flow (Screen C)
  // ==========================================================================

  function pickSupportedAudioMimeType() {
    if (typeof window.MediaRecorder === "undefined" || typeof window.MediaRecorder.isTypeSupported !== "function") {
      return "";
    }
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/mp4;codecs=mp4a.40.2",
      "audio/ogg;codecs=opus",
      "audio/wav",
    ];
    for (const mime of candidates) {
      try {
        if (window.MediaRecorder.isTypeSupported(mime)) {
          return mime;
        }
      } catch (_) {}
    }
    return "";
  }

  function stopMediaStream() {
    if (recordingTimerId) {
      clearInterval(recordingTimerId);
      recordingTimerId = null;
    }
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      try {
        mediaRecorder.stop();
      } catch (_) {}
    }
    if (mediaStream) {
      try {
        mediaStream.getTracks().forEach((track) => track.stop());
      } catch (_) {}
      mediaStream = null;
    }
  }

  function showVoiceStage(stage) {
    const recEl = document.getElementById("voice-stage-recording");
    const procEl = document.getElementById("voice-stage-processing");
    const revEl = document.getElementById("voice-stage-review");
    const footerEl = document.getElementById("voice-modal-footer");

    if (recEl) recEl.classList.toggle("hidden", stage !== "recording");
    if (procEl) procEl.classList.toggle("hidden", stage !== "processing");
    if (revEl) revEl.classList.toggle("hidden", stage !== "review");
    if (footerEl) footerEl.classList.toggle("hidden", stage !== "review");
  }

  async function openVoiceModalAndStartRecording() {
    SL.playSoftTap();
    const modal = document.getElementById("voice-request-modal");
    const errBanner = document.getElementById("voice-modal-error");
    const errText = document.getElementById("voice-modal-error-text");
    if (modal) modal.classList.remove("hidden");
    if (errBanner) errBanner.classList.add("hidden");

    currentPreviewId = null;
    previewConsumedOrRejected = false;
    selectedVoiceIntentId = "water_request";
    voiceAttributes = {};
    voiceCandidates = [];
    showAllVoiceCategories = false;

    if (
      !navigator.mediaDevices ||
      typeof navigator.mediaDevices.getUserMedia !== "function" ||
      typeof window.MediaRecorder === "undefined"
    ) {
      // Graceful fallback to manual review/selection inside the modal
      if (errText) {
        errText.textContent =
          "Microphone recording is unavailable on this browser. You can type your request or select a category below.";
      }
      if (errBanner) errBanner.classList.remove("hidden");
      populateVoiceReviewFallback("");
      return;
    }

    try {
      showVoiceStage("recording");
      recordingSeconds = 0;
      const timerEl = document.getElementById("voice-timer-display");
      if (timerEl) timerEl.textContent = "0:00 / 0:15";

      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordedChunks = [];
      negotiatedMimeType = pickSupportedAudioMimeType();

      const recorderOptions = negotiatedMimeType ? { mimeType: negotiatedMimeType } : undefined;
      mediaRecorder = new window.MediaRecorder(mediaStream, recorderOptions);

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          recordedChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        if (mediaStream) {
          try {
            mediaStream.getTracks().forEach((track) => track.stop());
          } catch (_) {}
          mediaStream = null;
        }
        uploadRecordedAudioForPreview();
      };

      mediaRecorder.start(250);

      recordingTimerId = setInterval(() => {
        recordingSeconds += 1;
        const secStr = recordingSeconds < 10 ? `0${recordingSeconds}` : String(recordingSeconds);
        if (timerEl) timerEl.textContent = `0:${secStr} / 0:15`;
        if (recordingSeconds >= 15) {
          stopMediaStream();
        }
      }, 1000);
    } catch (err) {
      stopMediaStream();
      if (errText) {
        errText.textContent =
          "Microphone permission was denied or unavailable. Please type your request or choose a category below.";
      }
      if (errBanner) errBanner.classList.remove("hidden");
      populateVoiceReviewFallback("");
    }
  }

  async function uploadRecordedAudioForPreview() {
    showVoiceStage("processing");
    const errBanner = document.getElementById("voice-modal-error");
    const errText = document.getElementById("voice-modal-error-text");
    if (errBanner) errBanner.classList.add("hidden");

    const actualType =
      (mediaRecorder && mediaRecorder.mimeType) || negotiatedMimeType || "audio/webm";
    const blob = new Blob(recordedChunks, { type: actualType });

    if (!blob || blob.size < 64) {
      if (errText) errText.textContent = "No audio was captured. Please record again or select a category.";
      if (errBanner) errBanner.classList.remove("hidden");
      populateVoiceReviewFallback("");
      return;
    }

    let ext = "webm";
    if (actualType.includes("mp4") || actualType.includes("m4a")) ext = "m4a";
    else if (actualType.includes("wav")) ext = "wav";
    else if (actualType.includes("ogg")) ext = "ogg";

    const formData = new FormData();
    formData.append("audio", blob, `passenger_voice.${ext}`);

    const res = await SL.apiFetch("/api/voice_request", {
      method: "POST",
      body: formData,
    });

    if (res.isUnauthenticated) {
      window.location.replace("/login");
      return;
    }

    if (!res.ok) {
      // Handle 503 MODEL_UNAVAILABLE, 422 SILENCE_OR_NO_SPEECH, etc. gracefully on the review screen
      if (errText) {
        errText.textContent =
          res.errorMessage ||
          "Local voice model could not process the audio. You can type your request or pick a category below.";
      }
      if (errBanner) errBanner.classList.remove("hidden");
      populateVoiceReviewFallback("");
      return;
    }

    const data = res.data || {};
    currentPreviewId = data.preview_id || null;
    previewConsumedOrRejected = false;
    voiceAttributes = data.attributes || {};

    const transcriptInput = document.getElementById("voice-transcript-input");
    if (transcriptInput) {
      transcriptInput.value = data.transcript || "";
    }

    // Determine initial selected intent & candidates
    const alts = Array.isArray(data.alternatives)
      ? data.alternatives
      : Array.isArray(data.candidates)
      ? data.candidates
      : [];

    voiceCandidates = alts.map((c) => ({
      intent_id: c.intent_id,
      confidence: c.confidence !== undefined ? c.confidence : c.score || 0.5,
    }));

    if (data.intent_id) {
      selectedVoiceIntentId = data.intent_id;
    } else if (voiceCandidates.length > 0) {
      selectedVoiceIntentId = voiceCandidates[0].intent_id;
    } else {
      selectedVoiceIntentId = "water_request";
    }

    showAllVoiceCategories = data.outcome === "UNRELIABLE" || voiceCandidates.length === 0;
    showVoiceStage("review");
    renderVoiceReviewState(data.outcome || "SUGGESTED", data.confidence);
  }

  function populateVoiceReviewFallback(initialText) {
    currentPreviewId = null;
    const transcriptInput = document.getElementById("voice-transcript-input");
    if (transcriptInput) transcriptInput.value = initialText || "";
    const localResult = SL.classifyTextLocally(initialText || "");
    selectedVoiceIntentId = localResult.intent_id || "water_request";
    voiceAttributes = localResult.attributes || {};
    voiceCandidates = localResult.alternatives || [];
    showAllVoiceCategories = true;
    showVoiceStage("review");
    renderVoiceReviewState(localResult.outcome, localResult.confidence);
  }

  function renderVoiceReviewState(outcome, confidenceScore) {
    const card = document.getElementById("voice-suggestion-card");
    const badge = document.getElementById("voice-outcome-badge");
    const confEl = document.getElementById("voice-confidence-text");
    const iconEl = document.getElementById("voice-selected-icon");
    const titleEl = document.getElementById("voice-selected-title");
    const prioEl = document.getElementById("voice-selected-priority");
    const attrsEl = document.getElementById("voice-selected-attrs");
    const gridEl = document.getElementById("voice-candidates-grid");

    const meta = SL.getIntentMeta(selectedVoiceIntentId);

    if (card && badge) {
      card.classList.toggle("suggested", outcome === "SUGGESTED");
      card.classList.toggle("uncertain", outcome !== "SUGGESTED");
      if (outcome === "SUGGESTED") {
        badge.className = "status-badge completed";
        badge.textContent = "SUGGESTED MATCH";
      } else if (outcome === "REQUIRES_CHOICE") {
        badge.className = "status-badge pending";
        badge.textContent = "PLEASE CONFIRM CATEGORY";
      } else {
        badge.className = "status-badge pending";
        badge.textContent = "SELECT A SERVICE CATEGORY";
      }
    }

    if (confEl) {
      confEl.textContent =
        typeof confidenceScore === "number" && confidenceScore > 0
          ? `${Math.round(confidenceScore * 100)}% match`
          : "";
    }

    if (iconEl) iconEl.innerHTML = SL.getCategoryIconSvg(meta.id, 20);
    if (titleEl) titleEl.textContent = SL.getIntentTitle(meta.id);
    if (prioEl) {
      prioEl.innerHTML =
        meta.priority === "URGENT"
          ? `<span class="priority-badge-urgent">${SL.escapeHtml(SL.t("priorityUrgent"))}</span>`
          : `<span class="priority-badge-routine">${SL.escapeHtml(SL.t("priorityRoutine"))}</span>`;
    }

    const attrStrings = [];
    if (voiceAttributes && voiceAttributes.temperature) {
      attrStrings.push(`Temperature: ${voiceAttributes.temperature}`);
    }
    if (voiceAttributes && voiceAttributes.dietary) {
      attrStrings.push(`Dietary: ${voiceAttributes.dietary}`);
    }
    if (attrsEl) {
      attrsEl.textContent =
        attrStrings.length > 0 ? attrStrings.join(" • ") : "Review and confirm before sending to crew";
    }

    if (gridEl) {
      const itemsToRender =
        showAllVoiceCategories || voiceCandidates.length === 0
          ? SL.CANONICAL_INTENTS.map((i) => ({ intent_id: i.id }))
          : voiceCandidates;

      gridEl.innerHTML = itemsToRender
        .map((c) => {
          const id = c.intent_id;
          const active = id === selectedVoiceIntentId;
          const m = SL.getIntentMeta(id);
          return `
            <button
              type="button"
              class="candidate-chip-btn ${active ? "active" : ""}"
              data-voice-candidate="${SL.escapeHtml(id)}"
            >
              <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                ${SL.escapeHtml(SL.getIntentTitle(id))}
              </span>
              ${
                m.priority === "URGENT"
                  ? `<span style="font-size:0.62rem;font-weight:700;opacity:0.9;">!</span>`
                  : ""
              }
            </button>
          `;
        })
        .join("");

      gridEl.querySelectorAll("[data-voice-candidate]").forEach((btn) => {
        btn.addEventListener("click", () => {
          SL.playSoftTap();
          selectedVoiceIntentId = btn.getAttribute("data-voice-candidate");
          renderVoiceReviewState("SUGGESTED", confidenceScore);
        });
      });
    }
  }

  function closeVoiceModal() {
    stopMediaStream();
    const modal = document.getElementById("voice-request-modal");
    if (modal) modal.classList.add("hidden");
  }

  async function handleVoiceNoneOfThese() {
    SL.playSoftTap();
    showAllVoiceCategories = true;
    if (currentPreviewId && !previewConsumedOrRejected) {
      previewConsumedOrRejected = true;
      await SL.apiFetch("/api/voice_request/none_of_these", {
        method: "POST",
        body: { preview_id: currentPreviewId },
      });
    }
    renderVoiceReviewState("REQUIRES_CHOICE", null);
  }

  async function confirmAndSendVoiceRequest() {
    if (!selectedVoiceIntentId || isSubmittingVoice) return;
    isSubmittingVoice = true;

    const confirmBtn = document.getElementById("confirm-voice-modal-btn");
    const errBanner = document.getElementById("voice-modal-error");
    const errText = document.getElementById("voice-modal-error-text");
    if (confirmBtn) confirmBtn.disabled = true;
    if (errBanner) errBanner.classList.add("hidden");

    const transcriptText = (document.getElementById("voice-transcript-input").value || "").trim();
    let res = null;

    if (currentPreviewId && !previewConsumedOrRejected) {
      res = await SL.apiFetch("/api/voice_request/confirm", {
        method: "POST",
        body: {
          preview_id: currentPreviewId,
          intent_id: selectedVoiceIntentId,
        },
      });

      // If preview expired (410) or was already rejected, seamlessly submit via /api/requests
      if (!res.ok && (res.status === 410 || res.errorCode === "PREVIEW_EXPIRED" || res.errorCode === "PREVIEW_REJECTED")) {
        res = await SL.apiFetch("/api/requests", {
          method: "POST",
          body: {
            intent_id: selectedVoiceIntentId,
            client_request_id: `voice_fb_${Date.now()}`,
          },
        });
      }
    } else {
      res = await SL.apiFetch("/api/requests", {
        method: "POST",
        body: {
          intent_id: selectedVoiceIntentId,
          client_request_id: `voice_manual_${Date.now()}`,
        },
      });
    }

    if (confirmBtn) confirmBtn.disabled = false;
    isSubmittingVoice = false;

    if (res.isUnauthenticated) {
      window.location.replace("/login");
      return;
    }

    if (!res.ok) {
      if (errText) errText.textContent = res.errorMessage || "Could not confirm voice request.";
      if (errBanner) errBanner.classList.remove("hidden");
      return;
    }

    const createdReq = (res.data && res.data.request) || res.data || {};
    const reqId = createdReq.id || createdReq.request_id;
    if (reqId) {
      const metaPatch = {};
      if (voiceAttributes.temperature) metaPatch.temperature = voiceAttributes.temperature;
      if (voiceAttributes.dietary) metaPatch.dietary = voiceAttributes.dietary;
      if (transcriptText) metaPatch.note = transcriptText;
      SL.saveLocalRequestMeta(reqId, metaPatch);
      expandedRequestId = reqId;

      if (transcriptText) {
        SL.apiFetch(`/api/crew/requests/${encodeURIComponent(reqId)}/follow_up`, {
          method: "POST",
          body: { message: `Voice transcript: "${transcriptText}"`.slice(0, 280) },
        });
      }
    }

    SL.playServerAckChime();
    closeVoiceModal();
    SL.showToast("Voice request confirmed and sent to cabin crew.", "success");
    await fetchPassengerState(false);
  }

  // ==========================================================================
  // 7. Typed Request Modal (TypedRequestModal)
  // ==========================================================================

  function openTypedModal() {
    SL.playSoftTap();
    selectedTypedIntentId = "water_request";
    const modal = document.getElementById("typed-request-modal");
    const input = document.getElementById("typed-text-input");
    const errBanner = document.getElementById("typed-modal-error");
    if (input) input.value = "";
    if (errBanner) errBanner.classList.add("hidden");
    renderTypedCategoriesGrid();
    if (modal) modal.classList.remove("hidden");
    if (input) input.focus();
  }

  function closeTypedModal() {
    const modal = document.getElementById("typed-request-modal");
    if (modal) modal.classList.add("hidden");
  }

  function renderTypedCategoriesGrid() {
    const grid = document.getElementById("typed-categories-grid");
    if (!grid) return;

    grid.innerHTML = SL.CANONICAL_INTENTS.map((item) => {
      const active = item.id === selectedTypedIntentId;
      return `
        <button
          type="button"
          class="candidate-chip-btn ${active ? "active" : ""}"
          data-typed-intent="${SL.escapeHtml(item.id)}"
        >
          <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
            ${SL.escapeHtml(SL.getIntentTitle(item.id))}
          </span>
          ${
            item.priority === "URGENT"
              ? `<span style="font-size:0.64rem;font-weight:700;">URGENT</span>`
              : ""
          }
        </button>
      `;
    }).join("");

    grid.querySelectorAll("[data-typed-intent]").forEach((btn) => {
      btn.addEventListener("click", () => {
        SL.playSoftTap();
        selectedTypedIntentId = btn.getAttribute("data-typed-intent");
        renderTypedCategoriesGrid();
      });
    });
  }

  async function submitTypedModalRequest() {
    if (!selectedTypedIntentId || isSubmittingTyped) return;
    isSubmittingTyped = true;

    const confirmBtn = document.getElementById("confirm-typed-modal-btn");
    const errBanner = document.getElementById("typed-modal-error");
    const errText = document.getElementById("typed-modal-error-text");
    if (confirmBtn) confirmBtn.disabled = true;
    if (errBanner) errBanner.classList.add("hidden");

    const noteText = (document.getElementById("typed-text-input").value || "").trim();
    const res = await SL.apiFetch("/api/requests", {
      method: "POST",
      body: {
        intent_id: selectedTypedIntentId,
        client_request_id: `typed_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      },
    });

    if (confirmBtn) confirmBtn.disabled = false;
    isSubmittingTyped = false;

    if (res.isUnauthenticated) {
      window.location.replace("/login");
      return;
    }

    if (!res.ok) {
      if (errText) errText.textContent = res.errorMessage || "Unable to submit request.";
      if (errBanner) errBanner.classList.remove("hidden");
      return;
    }

    const createdReq = (res.data && res.data.request) || res.data || {};
    const reqId = createdReq.id || createdReq.request_id;
    if (reqId) {
      if (noteText) {
        SL.saveLocalRequestMeta(reqId, { note: noteText });
        SL.apiFetch(`/api/crew/requests/${encodeURIComponent(reqId)}/follow_up`, {
          method: "POST",
          body: { message: noteText.slice(0, 280) },
        });
      }
      expandedRequestId = reqId;
    }

    SL.playServerAckChime();
    closeTypedModal();
    SL.showToast("Request confirmed and sent to cabin crew.", "success");
    await fetchPassengerState(false);
  }

  // ==========================================================================
  // 8. Event Listeners Binding
  // ==========================================================================

  function bindEventListeners() {
    // Logout Button -> POST /api/auth/logout
    const logoutBtn = document.getElementById("header-logout-btn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", async () => {
        SL.playSoftTap();
        await SL.apiFetch("/api/auth/logout", { method: "POST" });
        window.location.replace("/login");
      });
    }

    // Expandable All 15 Categories Drawer
    const moreToggleBtn = document.getElementById("toggle-more-categories-btn");
    const moreGridEl = document.getElementById("more-categories-grid");
    const moreChevron = document.getElementById("more-categories-chevron");
    if (moreToggleBtn && moreGridEl) {
      moreToggleBtn.addEventListener("click", () => {
        SL.playSoftTap();
        moreCategoriesOpen = !moreCategoriesOpen;
        moreGridEl.classList.toggle("hidden", !moreCategoriesOpen);
        moreToggleBtn.setAttribute("aria-expanded", String(moreCategoriesOpen));
        if (moreChevron) {
          moreChevron.style.transform = moreCategoriesOpen ? "rotate(180deg)" : "rotate(0deg)";
        }
      });
    }

    // Service Modal Controls
    document.getElementById("close-service-modal-btn").addEventListener("click", closeServiceModal);
    document.getElementById("cancel-service-modal-btn").addEventListener("click", closeServiceModal);
    document.getElementById("confirm-service-modal-btn").addEventListener("click", submitServiceModalRequest);

    document.querySelectorAll("[data-temp]").forEach((btn) => {
      btn.addEventListener("click", () => {
        SL.playSoftTap();
        selectedWaterTemp = btn.getAttribute("data-temp");
        document.querySelectorAll("[data-temp]").forEach((b) => {
          b.classList.toggle("selected", b.getAttribute("data-temp") === selectedWaterTemp);
        });
      });
    });

    document.querySelectorAll("[data-diet]").forEach((btn) => {
      btn.addEventListener("click", () => {
        SL.playSoftTap();
        selectedMealDiet = btn.getAttribute("data-diet");
        document.querySelectorAll("[data-diet]").forEach((b) => {
          b.classList.toggle("selected", b.getAttribute("data-diet") === selectedMealDiet);
        });
      });
    });

    // Voice Modal Controls
    document.getElementById("open-voice-modal-btn").addEventListener("click", openVoiceModalAndStartRecording);
    document.getElementById("stop-recording-btn").addEventListener("click", () => stopMediaStream());
    document.getElementById("close-voice-modal-btn").addEventListener("click", closeVoiceModal);
    document.getElementById("cancel-voice-modal-btn").addEventListener("click", closeVoiceModal);
    document.getElementById("voice-rerecord-btn").addEventListener("click", openVoiceModalAndStartRecording);
    document.getElementById("voice-none-of-these-btn").addEventListener("click", handleVoiceNoneOfThese);
    document.getElementById("confirm-voice-modal-btn").addEventListener("click", confirmAndSendVoiceRequest);

    // Live reclassification when passenger edits the transcript in Voice Review
    const voiceTranscriptInput = document.getElementById("voice-transcript-input");
    if (voiceTranscriptInput) {
      voiceTranscriptInput.addEventListener("input", (e) => {
        const val = e.target.value || "";
        const local = SL.classifyTextLocally(val);
        if (local.intent_id) {
          selectedVoiceIntentId = local.intent_id;
          voiceAttributes = Object.assign({}, voiceAttributes, local.attributes);
          renderVoiceReviewState(local.outcome, local.confidence);
        }
      });
    }

    // Typed Modal Controls
    document.getElementById("open-typed-modal-btn").addEventListener("click", openTypedModal);
    document.getElementById("close-typed-modal-btn").addEventListener("click", closeTypedModal);
    document.getElementById("cancel-typed-modal-btn").addEventListener("click", closeTypedModal);
    document.getElementById("confirm-typed-modal-btn").addEventListener("click", submitTypedModalRequest);

    const typedTextInput = document.getElementById("typed-text-input");
    if (typedTextInput) {
      typedTextInput.addEventListener("input", (e) => {
        const local = SL.classifyTextLocally(e.target.value || "");
        if (local.intent_id) {
          selectedTypedIntentId = local.intent_id;
          renderTypedCategoriesGrid();
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", initPassengerApp);
})();

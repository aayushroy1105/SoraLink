/* ==========================================================================
   SoraLink (空連) — Cabin Crew Operations Console Controller
   ========================================================================== */

(function () {
  "use strict";

  const SL = window.SoraLink;

  // Crew State
  let isCrewAuthenticated = false;
  let crewId = null;
  let socketManager = null;
  let crewRequests = [];
  let currentFilter = "ALL"; // ALL | PENDING | ACKNOWLEDGED | COMPLETED
  let paCardsList = [];
  let activeBroadcastsMap = new Map();
  let followUpAlertsMap = new Map(); // request_id -> timestamp

  // Reply Modal State
  let replyTargetRequestId = null;
  let replyTargetSeat = "";
  let selectedResponseId = "request_acknowledged";
  let isSendingReply = false;

  // ==========================================================================
  // 1. Initialization & Auth Verification
  // ==========================================================================

  async function initCrewApp() {
    SL.initHeaderControls(() => {
      renderPARadioSelect();
      renderActiveBroadcasts();
      renderCrewQueue();
      renderCrewReplyOptions();
    });

    bindCrewEvents();
    setInterval(tickCrewBroadcastTimers, 1000);

    await SL.syncCatalogFromServer();

    const meRes = await SL.apiFetch("/api/auth/me");
    if (meRes.ok && meRes.data && meRes.data.role === "crew") {
      crewId = meRes.data.crew_id || "crew_demo";
      await enterAuthenticatedCrewDashboard();
    } else {
      showCrewLoginView();
    }
  }

  function showCrewLoginView() {
    isCrewAuthenticated = false;
    document.getElementById("crew-login-view").classList.remove("hidden");
    document.getElementById("crew-dashboard-view").classList.add("hidden");
    document.getElementById("header-logout-btn").classList.add("hidden");
    if (socketManager) {
      socketManager.disconnect();
      socketManager = null;
    }
  }

  async function enterAuthenticatedCrewDashboard() {
    isCrewAuthenticated = true;
    document.getElementById("crew-login-view").classList.add("hidden");
    document.getElementById("crew-dashboard-view").classList.remove("hidden");
    document.getElementById("header-logout-btn").classList.remove("hidden");

    await Promise.all([fetchPACardsCatalog(), fetchCrewBroadcasts(), fetchCrewRequests()]);

    if (!socketManager) {
      socketManager = SL.createSocketManager({
        onRequestCreated: (payload) => {
          const req = (payload && payload.request) || payload || {};
          const isUrgent = req.priority === "URGENT";
          SL.playCabinChime(isUrgent ? "urgent" : "routine");
          const title = SL.getIntentTitle(req.intent_id);
          SL.showToast(
            `New ${isUrgent ? "URGENT " : ""}Request — Seat ${req.seat_label || "?"}: ${title}`,
            isUrgent ? "error" : "success"
          );
          fetchCrewRequests();
        },
        onRequestUpdated: () => {
          fetchCrewRequests();
        },
        onFollowUpRequested: (payload) => {
          if (payload && payload.request_id) {
            followUpAlertsMap.set(payload.request_id, Date.now());
            SL.playCabinChime("routine");
            SL.showToast("Passenger sent a follow-up note.", "success");
            fetchCrewRequests();
          }
        },
        onPABroadcastCreated: (payload) => {
          if (payload && (payload.broadcast_id || payload.id)) {
            activeBroadcastsMap.set(payload.broadcast_id || payload.id, payload);
            renderActiveBroadcasts();
          }
        },
        onPABroadcastEnded: (payload) => {
          const bid = payload && (payload.broadcast_id || payload.id);
          if (bid && activeBroadcastsMap.has(bid)) {
            activeBroadcastsMap.delete(bid);
            renderActiveBroadcasts();
          } else {
            fetchCrewBroadcasts();
          }
        },
        onResync: () => {
          if (isCrewAuthenticated) {
            fetchCrewRequests();
            fetchCrewBroadcasts();
          }
        },
      });
    }
  }

  // ==========================================================================
  // 2. Fetch Crew Queue, PA Catalog & Active Broadcasts
  // ==========================================================================

  async function fetchPACardsCatalog() {
    const res = await SL.apiFetch("/api/crew/pa/cards");
    if (res.ok && res.data && Array.isArray(res.data.cards) && res.data.cards.length > 0) {
      paCardsList = res.data.cards;
    } else {
      paCardsList = Object.values(SL.PA_CARDS_CATALOG).map((c) => ({
        id: c.id,
        title: c.titles.en,
        body: c.bodies.en,
        category: c.category,
        default_ttl: c.default_ttl,
      }));
    }
    renderPARadioSelect();
  }

  function renderPARadioSelect() {
    const selectEl = document.getElementById("crew-pa-card-select");
    const durSelect = document.getElementById("crew-pa-duration-select");
    if (!selectEl) return;

    const currentVal = selectEl.value;
    selectEl.innerHTML = paCardsList
      .map((card) => {
        const loc = SL.getPACardLocalized(card.id, card.title, card.body);
        const cat = (card.category || loc.category || "cabin").toUpperCase();
        return `<option value="${SL.escapeHtml(card.id)}" data-ttl="${
          card.default_ttl || 180
        }">[${SL.escapeHtml(cat)}] ${SL.escapeHtml(loc.title)} — ${SL.escapeHtml(
          loc.body.slice(0, 65)
        )}…</option>`;
      })
      .join("");

    if (currentVal && paCardsList.some((c) => c.id === currentVal)) {
      selectEl.value = currentVal;
    }

    selectEl.onchange = () => {
      const selectedOpt = selectEl.options[selectEl.selectedIndex];
      const defaultTtl = selectedOpt && selectedOpt.getAttribute("data-ttl");
      if (defaultTtl && durSelect) {
        durSelect.value = defaultTtl;
      }
    };
  }

  async function fetchCrewBroadcasts() {
    const res = await SL.apiFetch("/api/crew/broadcasts");
    if (res.isUnauthenticated) {
      showCrewLoginView();
      return;
    }
    if (res.ok && res.data && Array.isArray(res.data.broadcasts)) {
      const now = Date.now();
      const nextMap = new Map();
      for (const b of res.data.broadcasts) {
        const bid = b.broadcast_id || b.id;
        const exp = b.expires_at_ms || b.expires_at || 0;
        if (bid && b.active_status !== false && exp > now) {
          nextMap.set(bid, b);
        }
      }
      activeBroadcastsMap = nextMap;
      renderActiveBroadcasts();
    }
  }

  async function fetchCrewRequests() {
    const res = await SL.apiFetch("/api/crew/requests?include_completed=true");
    if (res.isUnauthenticated) {
      showCrewLoginView();
      return;
    }
    if (!res.ok) {
      if (res.isNetworkError) {
        SL.updateConnectionBadge("offline");
      }
      return;
    }

    const list = (res.data && res.data.requests) || [];
    // Deterministic priority sort: URGENT before ROUTINE, then created_at_ms ASC, then id ASC
    crewRequests = list.slice().sort((a, b) => {
      const prioA = a.priority === "URGENT" ? 0 : 1;
      const prioB = b.priority === "URGENT" ? 0 : 1;
      if (prioA !== prioB) return prioA - prioB;
      const tA = a.created_at_ms || a.created_at || 0;
      const tB = b.created_at_ms || b.created_at || 0;
      if (tA !== tB) return tA - tB;
      return String(a.id || "").localeCompare(String(b.id || ""));
    });

    renderCrewQueue();
  }

  // ==========================================================================
  // 3. Render PA Broadcasts & Crew Request Queue
  // ==========================================================================

  function renderActiveBroadcasts() {
    const container = document.getElementById("crew-active-broadcasts");
    if (!container) return;

    const now = Date.now();
    const activeList = Array.from(activeBroadcastsMap.values()).filter((b) => {
      const exp = b.expires_at_ms || b.expires_at || 0;
      return b.active_status !== false && exp > now;
    });

    if (activeList.length === 0) {
      container.innerHTML = "";
      return;
    }

    container.innerHTML = activeList
      .map((b) => {
        const bid = b.broadcast_id || b.id;
        const exp = b.expires_at_ms || b.expires_at || now;
        const loc = SL.getPACardLocalized(b.pa_card_id, b.title, b.body);
        const remaining = SL.formatCountdownMMSS(exp - now);

        return `
          <div class="crew-pa-active-box">
            <div style="flex:1;min-width:220px;">
              <div style="display:flex;align-items:center;gap:0.45rem;margin-bottom:0.25rem;">
                <span class="priority-badge-urgent">LIVE BROADCAST</span>
                <span class="priority-badge-routine">${SL.escapeHtml(
                  (b.category || loc.category || "cabin").toUpperCase()
                )}</span>
                <span class="font-mono-code" id="crew-pa-timer-${SL.escapeHtml(
                  bid
                )}" style="font-size:0.76rem;font-weight:700;color:var(--color-crimson);">
                  ${SL.escapeHtml(remaining)}
                </span>
              </div>
              <strong style="display:block;font-size:0.95rem;color:var(--color-charcoal);">${SL.escapeHtml(
                loc.title
              )}</strong>
              <p style="margin:2px 0 0;font-size:0.82rem;color:var(--color-charcoal-muted);">${SL.escapeHtml(
                loc.body
              )}</p>
            </div>
            <button
              type="button"
              class="btn-secondary"
              data-end-broadcast="${SL.escapeHtml(bid)}"
              style="border-color:rgba(200,16,46,0.35);color:var(--color-crimson);font-weight:700;"
            >
              End Announcement
            </button>
          </div>
        `;
      })
      .join("");

    container.querySelectorAll("[data-end-broadcast]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const bid = btn.getAttribute("data-end-broadcast");
        if (!bid) return;
        btn.disabled = true;
        const res = await SL.apiFetch("/api/crew/pa/end", {
          method: "POST",
          body: { broadcast_id: bid },
        });
        btn.disabled = false;
        if (res.ok) {
          activeBroadcastsMap.delete(bid);
          renderActiveBroadcasts();
          SL.showToast("Cabin announcement ended.", "success");
        } else {
          SL.showToast(res.errorMessage || "Could not end broadcast.", "error");
        }
      });
    });
  }

  function tickCrewBroadcastTimers() {
    if (activeBroadcastsMap.size === 0) return;
    const now = Date.now();
    let expiredAny = false;

    for (const [bid, b] of activeBroadcastsMap.entries()) {
      const exp = b.expires_at_ms || b.expires_at || 0;
      if (exp <= now) {
        activeBroadcastsMap.delete(bid);
        expiredAny = true;
      } else {
        const el = document.getElementById(`crew-pa-timer-${bid}`);
        if (el) el.textContent = SL.formatCountdownMMSS(exp - now);
      }
    }

    if (expiredAny) {
      renderActiveBroadcasts();
    }
  }

  function renderCrewQueue() {
    const container = document.getElementById("crew-requests-container");
    const emptyEl = document.getElementById("crew-queue-empty");
    if (!container || !emptyEl) return;

    // Update filter counters
    const pendingCount = crewRequests.filter((r) => r.status === "PENDING").length;
    const ackCount = crewRequests.filter((r) => r.status === "ACKNOWLEDGED").length;
    const compCount = crewRequests.filter((r) => r.status === "COMPLETED").length;
    const urgentActiveCount = crewRequests.filter(
      (r) => r.priority === "URGENT" && r.status !== "COMPLETED"
    ).length;

    const setCount = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = String(val);
    };
    setCount("count-all", crewRequests.length);
    setCount("count-pending", pendingCount);
    setCount("count-acknowledged", ackCount);
    setCount("count-completed", compCount);

    const urgentPill = document.getElementById("crew-urgent-pill");
    const urgentText = document.getElementById("crew-urgent-count-text");
    if (urgentPill && urgentText) {
      urgentPill.classList.toggle("hidden", urgentActiveCount === 0);
      urgentText.textContent = `${urgentActiveCount} Urgent Active`;
    }

    const filtered = crewRequests.filter((r) => {
      if (currentFilter === "ALL") return true;
      return r.status === currentFilter;
    });

    if (filtered.length === 0) {
      emptyEl.classList.remove("hidden");
      container.innerHTML = "";
      return;
    }

    emptyEl.classList.add("hidden");

    container.innerHTML = filtered
      .map((req) => {
        const reqId = req.id || req.request_id;
        const isUrgent = req.priority === "URGENT";
        const isPending = req.status === "PENDING";
        const isAck = req.status === "ACKNOWLEDGED";
        const isCompleted = req.status === "COMPLETED";
        const title = SL.getIntentTitle(req.intent_id);
        const timeStr = SL.formatTimeHHMM(req.created_at_ms || req.created_at);
        const localMeta = SL.getLocalRequestMeta(reqId);
        const hasFollowUp = followUpAlertsMap.has(reqId) || Boolean(localMeta.note);

        let statusBadgeClass = "pending";
        if (isAck) statusBadgeClass = "acknowledged";
        else if (isCompleted) statusBadgeClass = "completed";

        const replySentText = localMeta.crewReplyId
          ? SL.getCrewResponseText(localMeta.crewReplyId)
          : "";

        return `
          <div class="crew-req-card ${isUrgent && !isCompleted ? "urgent-priority" : ""} ${
          isCompleted ? "completed-state" : ""
        }">
            <div style="display:flex;align-items:flex-start;gap:1rem;flex:1;min-width:0;">
              <!-- Seat Box -->
              <div class="crew-seat-box">
                <span class="crew-seat-label-sm">SEAT</span>
                <span class="crew-seat-number">${SL.escapeHtml(req.seat_label || "—")}</span>
              </div>

              <!-- Request Details -->
              <div style="flex:1;min-width:0;">
                <div style="display:flex;flex-wrap:wrap;align-items:center;gap:0.45rem;margin-bottom:0.3rem;">
                  <span style="display:inline-flex;align-items:center;color:var(--color-charcoal-muted);">
                    ${SL.getCategoryIconSvg(req.intent_id, 18)}
                  </span>
                  <strong style="font-size:1.05rem;color:var(--color-charcoal);">
                    ${SL.escapeHtml(title)}
                  </strong>
                  ${
                    isUrgent
                      ? `<span class="priority-badge-urgent">URGENT</span>`
                      : `<span class="priority-badge-routine">ROUTINE</span>`
                  }
                  <span class="status-badge ${statusBadgeClass}">${SL.escapeHtml(req.status)}</span>
                  ${
                    hasFollowUp
                      ? `<span class="priority-badge-Routine" style="background:#FEF3C7;color:#92400E;border:1px solid #FDE68A;padding:0.12rem 0.45rem;border-radius:4px;font-size:0.65rem;font-weight:700;">FOLLOW-UP NOTE</span>`
                      : ""
                  }
                </div>

                <div style="font-size:0.76rem;color:var(--color-charcoal-muted);display:flex;flex-wrap:wrap;gap:0.65rem;">
                  <span>Requested at ${SL.escapeHtml(timeStr)}</span>
                  <span class="font-mono-code">ID: #${SL.escapeHtml(String(reqId).slice(0, 8))}</span>
                  ${
                    localMeta.temperature
                      ? `<span>• Temp: <strong>${SL.escapeHtml(localMeta.temperature)}</strong></span>`
                      : ""
                  }
                  ${
                    localMeta.dietary
                      ? `<span>• Dietary: <strong>${SL.escapeHtml(localMeta.dietary)}</strong></span>`
                      : ""
                  }
                </div>

                ${
                  localMeta.note
                    ? `<div style="margin-top:0.4rem;padding:0.4rem 0.65rem;background:var(--color-ivory);border-left:3px solid var(--color-crimson);border-radius:4px;font-size:0.8rem;color:var(--color-charcoal);">
                        <strong>Passenger Note:</strong> "${SL.escapeHtml(localMeta.note)}"
                      </div>`
                    : ""
                }

                ${
                  replySentText
                    ? `<div style="margin-top:0.35rem;font-size:0.76rem;color:var(--color-crimson);font-weight:600;">
                        ✓ Reply sent: "${SL.escapeHtml(replySentText)}"
                      </div>`
                    : ""
                }
              </div>
            </div>

            <!-- Action Buttons -->
            ${
              !isCompleted
                ? `
              <div class="crew-actions-group">
                <button
                  type="button"
                  class="crew-action-btn reply-btn"
                  data-open-reply="${SL.escapeHtml(reqId)}"
                  data-seat="${SL.escapeHtml(req.seat_label || "")}"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  <span>Predefined Reply</span>
                </button>

                ${
                  isPending
                    ? `
                  <button
                    type="button"
                    class="crew-action-btn ack-btn"
                    data-ack-req="${SL.escapeHtml(reqId)}"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="20 6 9 17 4 12"/></svg>
                    <span>Acknowledge</span>
                  </button>
                `
                    : ""
                }

                <button
                  type="button"
                  class="crew-action-btn complete-btn"
                  data-complete-req="${SL.escapeHtml(reqId)}"
                  ${!isAck ? 'disabled title="Acknowledge request before completing"' : ""}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                  <span>Complete</span>
                </button>
              </div>
            `
                : `
              <div class="crew-actions-group">
                <span style="font-size:0.78rem;color:var(--color-emerald);font-weight:700;">
                  ✓ Service Completed
                </span>
              </div>
            `
            }
          </div>
        `;
      })
      .join("");

    // Bind Acknowledge button -> POST /api/crew/requests/<id>/acknowledge
    container.querySelectorAll("[data-ack-req]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const reqId = btn.getAttribute("data-ack-req");
        if (!reqId) return;
        btn.disabled = true;
        const res = await SL.apiFetch(`/api/crew/requests/${encodeURIComponent(reqId)}/acknowledge`, {
          method: "POST",
          body: { response_id: "request_acknowledged" },
        });
        btn.disabled = false;

        if (res.ok) {
          SL.saveLocalRequestMeta(reqId, { crewReplyId: "request_acknowledged" });
          SL.playServerAckChime();
          SL.showToast("Request acknowledged.", "success");
          fetchCrewRequests();
        } else {
          SL.showToast(res.errorMessage || "Failed to acknowledge request.", "error");
        }
      });
    });

    // Bind Complete button -> POST /api/crew/requests/<id>/complete
    container.querySelectorAll("[data-complete-req]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const reqId = btn.getAttribute("data-complete-req");
        if (!reqId) return;
        btn.disabled = true;
        const res = await SL.apiFetch(`/api/crew/requests/${encodeURIComponent(reqId)}/complete`, {
          method: "POST",
          body: {},
        });
        btn.disabled = false;

        if (res.ok) {
          SL.playServerAckChime();
          SL.showToast("Request marked as completed.", "success");
          fetchCrewRequests();
        } else {
          SL.showToast(res.errorMessage || "Failed to complete request.", "error");
        }
      });
    });

    // Bind Open Predefined Reply Modal
    container.querySelectorAll("[data-open-reply]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const reqId = btn.getAttribute("data-open-reply");
        const seat = btn.getAttribute("data-seat") || "";
        openCrewReplyModal(reqId, seat);
      });
    });
  }

  // ==========================================================================
  // 4. Crew Predefined Reply Modal (CrewReplyModal)
  // ==========================================================================

  function openCrewReplyModal(requestId, seat) {
    SL.playSoftTap();
    replyTargetRequestId = requestId;
    replyTargetSeat = seat;
    selectedResponseId = "crew_on_the_way";

    const subtitleEl = document.getElementById("crew-reply-modal-subtitle");
    if (subtitleEl) {
      subtitleEl.textContent = `Seat ${seat} • Request #${String(requestId).slice(0, 8)}`;
    }

    renderCrewReplyOptions();
    document.getElementById("crew-reply-modal").classList.remove("hidden");
  }

  function closeCrewReplyModal() {
    document.getElementById("crew-reply-modal").classList.add("hidden");
    replyTargetRequestId = null;
  }

  function renderCrewReplyOptions() {
    const listEl = document.getElementById("crew-reply-options-list");
    if (!listEl) return;

    const lang = SL.getLang();
    const entries = Object.values(SL.CREW_RESPONSES_CATALOG);
    listEl.innerHTML = entries
      .map((item) => {
        const isSelected = item.id === selectedResponseId;
        const primaryText = (item.labels && (item.labels[lang] || item.labels.en)) || item.id;
        const subText = lang !== "en" && item.labels && item.labels.en ? item.labels.en : item.labels.ja || "";
        return `
          <button
            type="button"
            class="radio-option-card ${isSelected ? "selected" : ""}"
            data-reply-option="${SL.escapeHtml(item.id)}"
          >
            <div style="flex:1;min-width:0;padding-right:0.5rem;">
              <div style="font-size:0.9rem;font-weight:700;color:${isSelected ? "var(--color-crimson)" : "var(--color-charcoal)"};">
                "${SL.escapeHtml(primaryText)}"
              </div>
              ${
                subText
                  ? `<div style="font-size:0.75rem;color:var(--color-charcoal-muted);margin-top:2px;">${SL.escapeHtml(
                      subText
                    )}</div>`
                  : ""
              }
            </div>
            <span class="radio-circle">
              ${
                isSelected
                  ? `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>`
                  : ""
              }
            </span>
          </button>
        `;
      })
      .join("");

    listEl.querySelectorAll("[data-reply-option]").forEach((btn) => {
      btn.addEventListener("click", () => {
        SL.playSoftTap();
        selectedResponseId = btn.getAttribute("data-reply-option");
        renderCrewReplyOptions();
      });
    });
  }

  async function submitCrewPredefinedReply() {
    if (!replyTargetRequestId || !selectedResponseId || isSendingReply) return;
    isSendingReply = true;

    const confirmBtn = document.getElementById("confirm-crew-reply-modal-btn");
    if (confirmBtn) confirmBtn.disabled = true;

    const res = await SL.apiFetch(
      `/api/crew/requests/${encodeURIComponent(replyTargetRequestId)}/acknowledge`,
      {
        method: "POST",
        body: { response_id: selectedResponseId },
      }
    );

    if (confirmBtn) confirmBtn.disabled = false;
    isSendingReply = false;

    if (res.ok) {
      SL.saveLocalRequestMeta(replyTargetRequestId, {
        crewReplyId: selectedResponseId,
        crewReplyAt: Date.now(),
      });
      SL.playServerAckChime();
      closeCrewReplyModal();
      SL.showToast(`Reply sent to Seat ${replyTargetSeat}.`, "success");
      fetchCrewRequests();
    } else {
      SL.showToast(res.errorMessage || "Could not send reply.", "error");
    }
  }

  // ==========================================================================
  // 5. Event Listeners
  // ==========================================================================

  function bindCrewEvents() {
    // Embedded Crew Login Form -> POST /api/auth/crew
    const authForm = document.getElementById("crew-auth-form");
    const authErr = document.getElementById("crew-auth-error");
    const authErrText = document.getElementById("crew-auth-error-text");
    const authSubmit = document.getElementById("crew-auth-submit-btn");

    if (authForm) {
      authForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (authErr) authErr.classList.add("hidden");

        const username = document.getElementById("crew-user-field").value.trim() || "crew_demo";
        const password = document.getElementById("crew-pass-field").value.trim();

        if (!password) {
          if (authErrText) authErrText.textContent = "Please enter the crew password / PIN.";
          if (authErr) authErr.classList.remove("hidden");
          return;
        }

        if (authSubmit) authSubmit.disabled = true;
        const res = await SL.apiFetch("/api/auth/crew", {
          method: "POST",
          body: {
            username,
            password,
            crew_pin: password,
          },
        });
        if (authSubmit) authSubmit.disabled = false;

        if (!res.ok) {
          if (authErrText) authErrText.textContent = res.errorMessage || "Invalid crew credentials.";
          if (authErr) authErr.classList.remove("hidden");
          return;
        }

        SL.playServerAckChime();
        crewId = (res.data && res.data.crew_id) || username;
        await enterAuthenticatedCrewDashboard();
      });
    }

    // Crew Logout -> POST /api/auth/logout
    const logoutBtn = document.getElementById("header-logout-btn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", async () => {
        SL.playSoftTap();
        await SL.apiFetch("/api/auth/logout", { method: "POST" });
        showCrewLoginView();
      });
    }

    // PA Broadcast Form -> POST /api/crew/pa/broadcast
    const paForm = document.getElementById("crew-pa-form");
    const paSubmitBtn = document.getElementById("crew-pa-submit-btn");
    if (paForm) {
      paForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const paCardId = document.getElementById("crew-pa-card-select").value;
        const durationSeconds = parseInt(
          document.getElementById("crew-pa-duration-select").value || "180",
          10
        );
        if (!paCardId) return;

        if (paSubmitBtn) paSubmitBtn.disabled = true;
        // Strict contract: only send pa_card_id and duration_seconds
        const res = await SL.apiFetch("/api/crew/pa/broadcast", {
          method: "POST",
          body: {
            pa_card_id: paCardId,
            duration_seconds: durationSeconds,
          },
        });
        if (paSubmitBtn) paSubmitBtn.disabled = false;

        if (res.ok && res.data) {
          const b = res.data;
          const bid = b.broadcast_id || b.id;
          if (bid) {
            activeBroadcastsMap.set(bid, b);
          }
          SL.playCabinChime("urgent");
          renderActiveBroadcasts();
          SL.showToast("PA announcement broadcast to all passenger screens.", "success");
        } else {
          SL.showToast(res.errorMessage || "Failed to broadcast announcement.", "error");
        }
      });
    }

    // Queue Filter Tabs
    document.querySelectorAll("[data-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        SL.playSoftTap();
        currentFilter = btn.getAttribute("data-filter") || "ALL";
        document.querySelectorAll("[data-filter]").forEach((b) => {
          b.classList.toggle("active", b.getAttribute("data-filter") === currentFilter);
        });
        renderCrewQueue();
      });
    });

    // Manual Refresh Button
    const refreshBtn = document.getElementById("crew-refresh-btn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        SL.playSoftTap();
        fetchCrewRequests();
        fetchCrewBroadcasts();
      });
    }

    // Crew Reply Modal Buttons
    document.getElementById("close-crew-reply-modal-btn").addEventListener("click", closeCrewReplyModal);
    document.getElementById("cancel-crew-reply-modal-btn").addEventListener("click", closeCrewReplyModal);
    document.getElementById("confirm-crew-reply-modal-btn").addEventListener("click", submitCrewPredefinedReply);
  }

  document.addEventListener("DOMContentLoaded", initCrewApp);
})();

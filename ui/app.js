const API_BASE = "";

const skills = [
  {name: "scope_check", label: "scope_check", locked: true},
  {name: "first_principles", label: "first_principles"},
  {name: "visualization", label: "visualization"},
  {name: "thought_experiment", label: "thought_experiment"},
  {name: "patience_check", label: "patience_check"},
  {name: "idea_origin", label: "idea_origin"},
  {name: "unit_economics", label: "unit_economics"},
  {name: "experiments_and_poc", label: "experiments_and_poc"},
  {name: "projections", label: "projections"},
];

const modeDescriptions = {
  economy: "Lowest cost, best for quick extraction.",
  balanced: "Low cost by default, upgrades harder skills.",
  deep: "Higher cost, use when the decision matters.",
};

const nudgeSignals = [
  "investment",
  "acquisition",
  "hiring",
  "fire",
  "quit",
  "runway",
  "revenue",
  "pricing",
  "unit economics",
  "compliance",
  "legal",
  "regulator",
  "market",
  "strategy",
  "partnership",
  "enterprise",
  "sales",
  "gtm",
  "founder",
  "career",
  "offer",
  "equity",
  "debt",
  "contract",
  "customer",
  "churn",
  "incident",
  "safety",
];

const stakeholderSignals = [
  "customer",
  "customers",
  "operator",
  "operators",
  "truckers",
  "employee",
  "employees",
  "founder",
  "founders",
  "investor",
  "investors",
  "partner",
  "partners",
  "regulator",
  "regulators",
  "enterprise",
  "sales",
  "fleet",
  "fleets",
  "vendor",
  "vendors",
  "buyer",
  "buyers",
];

const els = {
  provider: document.querySelector("#provider-status"),
  model: document.querySelector("#model-status"),
  latency: document.querySelector("#latency-status"),
  dailyCapture: document.querySelector("#daily-capture"),
  saveCapture: document.querySelector("#save-capture"),
  captureStatus: document.querySelector("#capture-status"),
  analysisInput: document.querySelector("#analysis-input"),
  runAnalysis: document.querySelector("#run-analysis"),
  analysisStatus: document.querySelector("#analysis-status"),
  agenticMode: document.querySelector("#agentic-mode"),
  includeThreadContext: document.querySelector("#include-thread-context"),
  modeDescription: document.querySelector("#mode-description"),
  skillControls: document.querySelector("#skill-controls"),
  errorBox: document.querySelector("#error-box"),
  results: document.querySelector("#results"),
  resultCount: document.querySelector("#result-count"),
  skippedCount: document.querySelector("#skipped-count"),
  skippedPanel: document.querySelector("#skipped-panel"),
  skippedList: document.querySelector("#skipped-list"),
  nudge: document.querySelector("#mode-nudge"),
  nudgeTitle: document.querySelector("#nudge-title"),
  nudgeBody: document.querySelector("#nudge-body"),
  nudgeUpgrade: document.querySelector("#nudge-upgrade"),
  nudgeRunAnyway: document.querySelector("#nudge-run-anyway"),
  threadSelect: document.querySelector("#thread-select"),
  refreshThreads: document.querySelector("#refresh-threads"),
  newThreadName: document.querySelector("#new-thread-name"),
  createThread: document.querySelector("#create-thread"),
  threadStatus: document.querySelector("#thread-status"),
  threadList: document.querySelector("#thread-list"),
  sessionList: document.querySelector("#session-list"),
  sessionColTitle: document.querySelector("#session-col-title"),
  presentStatus: document.querySelector("#present-status"),
  timeline: document.querySelector("#timeline"),
  timelineCards: document.querySelector("#timeline-cards"),
  presentCard: document.querySelector("#present-card"),
  nextCard: document.querySelector("#next-card"),
  presentDetail: document.querySelector("#present-detail"),
  figurePresent: document.querySelector("#figure-present"),
  figureNext: document.querySelector("#figure-next"),
  historySearch: document.querySelector("#history-search"),
  historyDetail: document.querySelector("#history-detail"),
};

let historyThreadId = null;
let knownThreads = [];
let currentSessions = [];

function setBusy(isBusy) {
  els.saveCapture.disabled = isBusy;
  els.runAnalysis.disabled = isBusy;
  els.agenticMode.disabled = isBusy;
  els.includeThreadContext.disabled = isBusy;
  for (const input of els.skillControls.querySelectorAll("input:not([data-locked='true'])")) {
    input.disabled = isBusy;
  }
}

function setStatus(el, message, state = "") {
  el.textContent = message;
  el.classList.remove("ok", "error");
  if (state) {
    el.classList.add(state);
  }
}

function showError(message) {
  els.errorBox.textContent = message;
  els.errorBox.classList.remove("hidden");
}

function clearError() {
  els.errorBox.textContent = "";
  els.errorBox.classList.add("hidden");
}

function renderSkillControls() {
  els.skillControls.innerHTML = "";

  for (const skill of skills) {
    const label = document.createElement("label");
    label.className = `skill-toggle${skill.locked ? " locked" : ""}`;

    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = true;
    input.value = skill.name;
    input.dataset.skill = skill.name;

    if (skill.locked) {
      input.disabled = true;
      input.dataset.locked = "true";
      input.setAttribute("aria-label", "scope_check is always on");
    }

    const text = document.createElement("span");
    text.textContent = skill.locked ? `${skill.label} / locked` : skill.label;

    label.append(input, text);
    els.skillControls.appendChild(label);
  }
}

function selectedSkips() {
  return skills
    .filter(skill => !skill.locked)
    .filter(skill => {
      const input = els.skillControls.querySelector(`[data-skill="${skill.name}"]`);
      return input && !input.checked;
    })
    .map(skill => skill.name);
}

function selectedMode() {
  return document.querySelector("input[name='thinking-mode']:checked").value;
}

function selectedAgentic() {
  return els.agenticMode.checked;
}

function setSelectedMode(mode) {
  const input = document.querySelector(`input[name='thinking-mode'][value='${mode}']`);
  if (input) {
    input.checked = true;
    updateModeDescription();
  }
}

function updateModeDescription() {
  els.modeDescription.textContent = modeDescriptions[selectedMode()];
}

function countStakeholderGroups(text) {
  const normalized = text.toLowerCase();
  const found = new Set();

  for (const signal of stakeholderSignals) {
    const pattern = new RegExp(`\\b${signal}\\b`, "i");
    if (pattern.test(normalized)) {
      found.add(signal.replace(/s$/, ""));
    }
  }

  return found.size;
}

function nudgeProfile(input) {
  const normalized = input.toLowerCase();
  const matchedSignals = nudgeSignals.filter(signal => {
    const pattern = new RegExp(`\\b${signal.replace(" ", "\\s+")}\\b`, "i");
    return pattern.test(normalized);
  });
  const hasCurrency = /[$€£¥]\s?\d|\d+\s?(usd|dollars|eur|gbp)\b/i.test(input);
  const hasPercent = /\d+(\.\d+)?\s?%/.test(input);
  const stakeholderGroups = countStakeholderGroups(input);
  const isLong = input.length > 900;
  const score = matchedSignals.length
    + (hasCurrency ? 1 : 0)
    + (hasPercent ? 1 : 0)
    + (stakeholderGroups > 1 ? 1 : 0)
    + (isLong ? 1 : 0);

  return {
    complex: score > 0,
    veryHighStakes: score >= 3 || matchedSignals.length >= 4,
  };
}

function hasAgenticDeepSignal(input) {
  return /\b(runway|acquisition|legal|safety|compliance|revenue)\b/i.test(input);
}

function nudgeFor(input, mode, agentic) {
  const profile = nudgeProfile(input);

  if (agentic && mode === "economy" && profile.complex) {
    return {
      targetMode: "balanced",
      title: "This may need deeper thinking",
      body: "Agentic multi-pass will plan, check gaps, and synthesize. Balanced mode keeps most work low-cost while giving harder reasoning passes more room.",
      upgradeLabel: "Switch to Balanced",
      runAnywayLabel: "Run Economy Anyway",
    };
  }

  if (agentic && mode === "balanced" && profile.veryHighStakes && hasAgenticDeepSignal(input)) {
    return {
      targetMode: "deep",
      title: "Deep mode may be worth it",
      body: "This looks like a decision where failure modes, assumptions, or unit economics matter. Deep mode costs more but may be worth using for this pass.",
      upgradeLabel: "Switch to Deep",
      runAnywayLabel: "Run Balanced Anyway",
    };
  }

  if (mode === "economy" && profile.complex) {
    return {
      targetMode: "balanced",
      title: "This may need deeper thinking",
      body: "This input looks strategic, ambiguous, or financially consequential. Balanced mode will keep most skills low-cost but upgrade the harder reasoning passes.",
      upgradeLabel: "Switch to Balanced",
      runAnywayLabel: "Run Economy Anyway",
    };
  }

  if (mode === "balanced" && profile.veryHighStakes) {
    return {
      targetMode: "deep",
      title: "Deep mode may be worth it",
      body: "This looks like a decision where failure modes, assumptions, or unit economics matter. Deep mode costs more but may be worth using for this pass.",
      upgradeLabel: "Switch to Deep",
      runAnywayLabel: "Run Balanced Anyway",
    };
  }

  return null;
}

function showModeNudge(nudge) {
  return new Promise(resolve => {
    els.nudgeTitle.textContent = nudge.title;
    els.nudgeBody.textContent = nudge.body;
    els.nudgeUpgrade.textContent = nudge.upgradeLabel;
    els.nudgeRunAnyway.textContent = nudge.runAnywayLabel;

    const cleanup = () => {
      els.nudgeUpgrade.removeEventListener("click", upgrade);
      els.nudgeRunAnyway.removeEventListener("click", runAnyway);
      els.nudge.removeEventListener("cancel", cancel);
    };

    const closeDialog = () => {
      if (els.nudge.open) {
        els.nudge.close();
      }
    };

    const upgrade = () => {
      cleanup();
      closeDialog();
      resolve("upgrade");
    };

    const runAnyway = () => {
      cleanup();
      closeDialog();
      resolve("run-anyway");
    };

    const cancel = event => {
      event.preventDefault();
      cleanup();
      closeDialog();
      resolve("run-anyway");
    };

    els.nudgeUpgrade.addEventListener("click", upgrade);
    els.nudgeRunAnyway.addEventListener("click", runAnyway);
    els.nudge.addEventListener("cancel", cancel);
    els.nudge.showModal();
  });
}

async function parseResponse(response) {
  const text = await response.text();
  let data = null;

  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = {detail: text};
    }
  }

  if (!response.ok) {
    const detail = data && (data.detail || data.error || JSON.stringify(data));
    throw new Error(detail || `Request failed with HTTP ${response.status}`);
  }

  return data || {};
}

async function loadZoneStatus() {
  try {
    const response = await fetch(`${API_BASE}/zone-status`);
    const data = await parseResponse(response);
    els.provider.textContent = data.provider || "unknown";
    els.model.textContent = data.model || "unknown";
  } catch (error) {
    els.provider.textContent = "unknown";
    els.model.textContent = "unavailable";
    showError(`Could not load Zone status: ${error.message}`);
  }
}

async function saveCapture() {
  const text = els.dailyCapture.value.trim();
  clearError();

  if (!text) {
    setStatus(els.captureStatus, "Daily capture is empty.", "error");
    return;
  }

  setBusy(true);
  setStatus(els.captureStatus, "Saving capture...");

  try {
    const response = await fetch(`${API_BASE}/daily-capture`, {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({text}),
    });
    const data = await parseResponse(response);
    setStatus(els.captureStatus, `Saved ${data.date || "today"}.`, "ok");
  } catch (error) {
    setStatus(els.captureStatus, error.message, "error");
  } finally {
    setBusy(false);
  }
}

function buildSections(data) {
  const results = Array.isArray(data.results) ? data.results : [];
  const skipped = Array.isArray(data.skipped) ? data.skipped : [];
  const sections = data.agentic
    ? [data.synthesis, data.plan, ...results, data.gap_detection, data.followup].filter(Boolean)
    : results;
  return {sections, skipped};
}

// Renders analysis briefs into any container — reused by the Workspace results
// band, the Present/Next detail, and the History detail (one component, not three).
function renderBriefsInto(container, sections) {
  container.innerHTML = "";
  if (!sections.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No briefs to show.";
    container.appendChild(empty);
    return;
  }

  sections.forEach((result, index) => {
    const brief = document.createElement("details");
    const isFinal = result.skill === "synthesis_pass";
    const isOrchestration = ["planning_pass", "gap_detection_pass", "followup_pass"].includes(result.skill);
    brief.className = `brief${isFinal ? " final-packet" : ""}${isOrchestration ? " orchestration" : ""}`;
    brief.open = index === 0;

    const summary = document.createElement("summary");
    const title = document.createElement("span");
    title.className = "brief-title";
    title.textContent = isFinal ? "Final packet" : result.skill || `brief_${index + 1}`;

    const meta = document.createElement("span");
    meta.className = "brief-meta";
    meta.textContent = [result.mode, result.model].filter(Boolean).join(" / ");
    summary.append(title, meta);

    const body = document.createElement("pre");
    body.className = "brief-body";
    body.textContent = result.output || "";

    brief.append(summary, body);

    if (result.skill === "planning_pass" && Array.isArray(result.discarded_planner_skills) && result.discarded_planner_skills.length) {
      const discarded = document.createElement("div");
      discarded.className = "planner-discarded";
      discarded.textContent = `Planner requested unavailable passes: ${result.discarded_planner_skills.join(", ")}`;
      brief.appendChild(discarded);
    }

    if (result.skill === "planning_pass" && Array.isArray(result.suggested_missing_skills) && result.suggested_missing_skills.length) {
      const suggested = document.createElement("div");
      suggested.className = "planner-suggested";

      const heading = document.createElement("div");
      heading.className = "planner-suggested-heading";
      heading.textContent = "Planner identified possible missing skills (NOT executed):";
      suggested.appendChild(heading);

      const list = document.createElement("ul");
      list.className = "planner-suggested-list";
      for (const item of result.suggested_missing_skills) {
        const li = document.createElement("li");
        const name = typeof item.name === "string" ? item.name : "(unnamed)";
        const description = typeof item.description === "string" && item.description ? ` — ${item.description}` : "";
        li.textContent = `${name}${description}`;
        list.appendChild(li);
      }
      suggested.appendChild(list);
      brief.appendChild(suggested);
    }

    container.appendChild(brief);
  });
}

function renderResults(data) {
  const {sections, skipped} = buildSections(data);
  els.resultCount.textContent = `${sections.length} ${sections.length === 1 ? "brief" : "briefs"}`;
  els.skippedCount.textContent = `${skipped.length} skipped`;
  els.latency.textContent = typeof data.latency_ms === "number" ? `${data.latency_ms} ms` : "n/a";

  renderBriefsInto(els.results, sections);

  els.skippedList.innerHTML = "";
  if (skipped.length) {
    els.skippedPanel.classList.remove("hidden");
    for (const item of skipped) {
      const li = document.createElement("li");
      li.textContent = `${item.skill}: ${item.reason}`;
      els.skippedList.appendChild(li);
    }
  } else {
    els.skippedPanel.classList.add("hidden");
  }
}

function renderSessionDetailInto(container, rawOutput) {
  const {sections} = buildSections(rawOutput || {});
  renderBriefsInto(container, sections);
}

function formatTimestamp(value) {
  if (!value) {
    return "unknown";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function selectedThreadId() {
  return els.threadSelect.value;
}

async function loadThreads(preferredId = null) {
  try {
    const response = await fetch(`${API_BASE}/threads`);
    const data = await parseResponse(response);
    const threads = Array.isArray(data.threads) ? data.threads : [];
    knownThreads = threads;
    populateThreadSelect(threads, preferredId);
    renderThreadList(filteredThreads());
    if (historyThreadId && threads.some(thread => thread.id === historyThreadId)) {
      renderSessionList(currentSessions);
    }
  } catch (error) {
    setStatus(els.threadStatus, `Could not load threads: ${error.message}`, "error");
  }
}

function populateThreadSelect(threads, preferredId) {
  const previous = preferredId || els.threadSelect.value;
  els.threadSelect.innerHTML = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Uncategorized (default)";
  els.threadSelect.appendChild(placeholder);

  for (const thread of threads) {
    const option = document.createElement("option");
    option.value = thread.id;
    option.textContent = `${thread.name} (${thread.session_count})`;
    els.threadSelect.appendChild(option);
  }

  if (previous && threads.some(thread => thread.id === previous)) {
    els.threadSelect.value = previous;
  }
}

function renderThreadList(threads) {
  els.threadList.innerHTML = "";
  if (!threads.length) {
    const li = document.createElement("li");
    li.className = "empty-state";
    li.textContent = "No threads yet.";
    els.threadList.appendChild(li);
    return;
  }

  for (const thread of threads) {
    const li = document.createElement("li");
    li.className = "history-item";
    if (thread.id === historyThreadId) {
      li.classList.add("active");
    }

    const title = document.createElement("span");
    title.className = "history-item-title";
    title.textContent = thread.name;

    const meta = document.createElement("span");
    meta.className = "history-item-meta";
    const count = thread.session_count === 1 ? "1 session" : `${thread.session_count} sessions`;
    meta.textContent = `${count} · updated ${formatTimestamp(thread.updated_at)}`;

    li.append(title, meta);
    li.addEventListener("click", () => loadThreadSessions(thread.id, thread.name));
    els.threadList.appendChild(li);
  }
}

async function createNewThread() {
  const name = els.newThreadName.value.trim();
  clearError();
  if (!name) {
    setStatus(els.threadStatus, "Enter a thread name first.", "error");
    return;
  }

  setStatus(els.threadStatus, "Creating thread…");
  try {
    const response = await fetch(`${API_BASE}/threads`, {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({name}),
    });
    const data = await parseResponse(response);
    els.newThreadName.value = "";
    await loadThreads(data.id);
    setStatus(els.threadStatus, `Thread "${data.name}" ready.`, "ok");
  } catch (error) {
    setStatus(els.threadStatus, error.message, "error");
  }
}

async function loadThreadSessions(threadId, threadName = null) {
  historyThreadId = threadId;
  try {
    const response = await fetch(`${API_BASE}/threads/${encodeURIComponent(threadId)}/sessions`);
    const data = await parseResponse(response);
    const name = threadName || (data.thread && data.thread.name) || "thread";
    els.sessionColTitle.textContent = `Sessions — ${name}`;
    currentSessions = Array.isArray(data.sessions) ? data.sessions : [];
    renderSessionList(currentSessions);
    // Reflect the active-thread highlight without a full network refresh.
    for (const item of els.threadList.querySelectorAll(".history-item")) {
      item.classList.remove("active");
    }
  } catch (error) {
    showError(error.message);
  }
}

function renderSessionList(sessions) {
  currentSessions = sessions;
  els.sessionList.innerHTML = "";
  if (!sessions.length) {
    const li = document.createElement("li");
    li.className = "empty-state";
    li.textContent = "No sessions in this thread yet.";
    els.sessionList.appendChild(li);
    return;
  }

  for (const session of sessions) {
    const li = document.createElement("li");
    li.className = "history-item";

    const title = document.createElement("span");
    title.className = "history-item-title";
    title.textContent = session.input_text || "(no input)";

    const meta = document.createElement("span");
    meta.className = "history-item-meta";
    const latency = typeof session.latency_ms === "number" ? `${session.latency_ms} ms` : "n/a";
    meta.textContent = `${session.mode} · ${formatTimestamp(session.created_at)} · ${latency}`;

    title.addEventListener("click", () => openSession(session.id));
    meta.addEventListener("click", () => openSession(session.id));

    li.append(title, meta, buildMoveControl(session));
    els.sessionList.appendChild(li);
  }
}

function buildMoveControl(session) {
  // "Capture now, organize later": re-thread a session via PATCH /sessions/{id}.
  const row = document.createElement("div");
  row.className = "session-move";

  const label = document.createElement("span");
  label.textContent = "Move to:";

  const select = document.createElement("select");
  select.setAttribute("aria-label", "Move session to thread");
  for (const thread of knownThreads) {
    const option = document.createElement("option");
    option.value = thread.id;
    option.textContent = thread.name;
    if (thread.id === historyThreadId) {
      option.selected = true;
    }
    select.appendChild(option);
  }

  select.addEventListener("click", event => event.stopPropagation());
  select.addEventListener("change", () => moveSession(session.id, select.value));

  row.append(label, select);
  return row;
}

async function moveSession(sessionId, targetThreadId) {
  if (!targetThreadId || targetThreadId === historyThreadId) {
    return;
  }
  clearError();
  try {
    const response = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({thread_id: targetThreadId}),
    });
    await parseResponse(response);
    // Refresh counts, then reload the current thread's sessions (the moved one leaves it).
    await loadThreads(selectedThreadId() || null);
    if (historyThreadId) {
      await loadThreadSessions(historyThreadId);
    }
  } catch (error) {
    showError(`Could not move session: ${error.message}`);
  }
}

async function openSessionInto(sessionId, container) {
  clearError();
  try {
    const response = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`);
    const data = await parseResponse(response);
    renderSessionDetailInto(container, data.raw_output || {});
    container.scrollIntoView({behavior: "smooth", block: "start"});
  } catch (error) {
    showError(error.message);
  }
}

function openSession(sessionId) {
  // From the History session list -> render the full stored output below it.
  return openSessionInto(sessionId, els.historyDetail);
}

async function runAnalysis(options = {}) {
  const input = els.analysisInput.value.trim();
  clearError();

  // thread_id is optional: an empty selection means "capture into Uncategorized".
  const threadId = selectedThreadId();

  if (!input) {
    setStatus(els.analysisStatus, "Object of analysis is empty.", "error");
    return;
  }

  const mode = selectedMode();
  const agentic = selectedAgentic();
  const nudge = options.bypassNudge ? null : nudgeFor(input, mode, agentic);
  if (nudge) {
    const decision = await showModeNudge(nudge);
    if (decision === "upgrade") {
      setSelectedMode(nudge.targetMode);
      await runAnalysis({bypassNudge: true});
      return;
    }
    await runAnalysis({bypassNudge: true});
    return;
  }

  setBusy(true);
  setStatus(els.analysisStatus, "Running analysis packet...");
  els.latency.textContent = "running";

  try {
    const body = {input, skip_skills: selectedSkips(), mode, agentic};
    if (threadId) {
      body.thread_id = threadId;
    }
    if (els.includeThreadContext.checked) {
      body.include_thread_context = true;
    }
    const response = await fetch(`${API_BASE}/second-brain`, {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify(body),
    });
    const data = await parseResponse(response);
    renderResults(data);
    const landedThreadId = data.thread_id || threadId;

    let message = "Analysis packet complete.";
    if (data.shorthand_thread) {
      message = `Analysis packet complete — routed to "${data.shorthand_thread}" via +shorthand.`;
    } else if (!threadId) {
      message = "Analysis packet complete (captured to Uncategorized).";
    }
    if (data.thread_context_injected) {
      message += " Prior thread context injected.";
    }
    setStatus(els.analysisStatus, message, "ok");

    // Persisted — refresh the thread list (the server may have created Uncategorized
    // or routed via shorthand), select the thread it actually landed in, and reload
    // that thread's sessions if it's the one on screen.
    await loadThreads(landedThreadId || selectedThreadId() || null);
    if (historyThreadId && historyThreadId === landedThreadId) {
      await loadThreadSessions(landedThreadId);
    }
  } catch (error) {
    els.latency.textContent = "error";
    showError(error.message);
    setStatus(els.analysisStatus, "Analysis failed.", "error");
  } finally {
    setBusy(false);
  }
}

// ---------------- Navigation between the three views ----------------
const VIEWS = ["workspace", "present", "history"];

function showView(name) {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.classList.toggle("is-active", tab.dataset.view === name);
  }
  for (const view of VIEWS) {
    const section = document.querySelector(`#view-${view}`);
    const active = view === name;
    section.classList.toggle("is-active", active);
    section.hidden = !active;
  }
  if (name === "present") {
    loadPresentFuture();
  }
}

// ---------------- Present / Next timeline ----------------
function cardFragment(kicker, title, body, meta) {
  const frag = document.createDocumentFragment();
  if (kicker) {
    const k = document.createElement("p");
    k.className = "card-kicker";
    k.textContent = kicker;
    frag.appendChild(k);
  }
  if (title) {
    const t = document.createElement("h3");
    t.className = "card-title";
    t.textContent = title;
    frag.appendChild(t);
  }
  const b = document.createElement("p");
  b.className = "card-body";
  b.textContent = body;
  frag.appendChild(b);
  if (meta) {
    const m = document.createElement("p");
    m.className = "card-meta";
    m.textContent = meta;
    frag.appendChild(m);
  }
  return frag;
}

function renderPresent(data) {
  const present = data && data.present;
  els.presentDetail.innerHTML = "";

  if (!present) {
    els.presentStatus.textContent = "No sessions yet — run an analysis in Workspace to populate your timeline.";
    els.timeline.hidden = true;
    els.timelineCards.hidden = true;
    return;
  }

  els.presentStatus.textContent = "";
  els.timeline.hidden = false;
  els.timelineCards.hidden = false;

  const summaryText = present.summary && present.summary.trim()
    ? present.summary
    : (present.input_excerpt || "(no summary stored)");
  els.presentCard.innerHTML = "";
  els.presentCard.appendChild(
    cardFragment("Now — latest thought", present.thread_name || "thread", summaryText, formatTimestamp(present.created_at))
  );

  const next = data.next;
  els.nextCard.innerHTML = "";
  if (next && next.synthesis) {
    els.nextCard.classList.remove("muted");
    els.nextCard.appendChild(
      cardFragment("Next — open questions & next steps", next.thread_name || "", next.synthesis, "From your latest synthesis")
    );
    els.figureNext.disabled = false;
    els.figureNext.onclick = () => openSessionInto(present.session_id, els.presentDetail);
  } else {
    els.nextCard.classList.add("muted");
    els.nextCard.appendChild(
      cardFragment(
        "Next — open questions & next steps",
        "",
        "No synthesized next-steps yet. Run an agentic analysis (Agentic multi-pass) and its synthesis will appear here.",
        ""
      )
    );
    els.figureNext.disabled = true;
    els.figureNext.onclick = null;
  }

  els.figurePresent.onclick = () => openSessionInto(present.session_id, els.presentDetail);
}

async function loadPresentFuture() {
  els.presentStatus.textContent = "Loading…";
  els.timeline.hidden = true;
  els.timelineCards.hidden = true;
  els.presentDetail.innerHTML = "";
  try {
    const response = await fetch(`${API_BASE}/present-future`);
    const data = await parseResponse(response);
    renderPresent(data);
  } catch (error) {
    els.presentStatus.textContent = `Could not load timeline: ${error.message}`;
  }
}

// ---------------- History search / filter ----------------
let historyQuery = "";

function filteredThreads() {
  const query = historyQuery.trim().toLowerCase();
  if (!query) {
    return knownThreads;
  }
  return knownThreads.filter(thread =>
    (thread.name || "").toLowerCase().includes(query) ||
    formatTimestamp(thread.updated_at).toLowerCase().includes(query)
  );
}

renderSkillControls();
updateModeDescription();
loadZoneStatus();
loadThreads();

for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => showView(tab.dataset.view));
}
els.historySearch.addEventListener("input", () => {
  historyQuery = els.historySearch.value;
  renderThreadList(filteredThreads());
});

els.saveCapture.addEventListener("click", saveCapture);
els.runAnalysis.addEventListener("click", runAnalysis);
els.createThread.addEventListener("click", createNewThread);
els.refreshThreads.addEventListener("click", () => loadThreads());
els.newThreadName.addEventListener("keydown", event => {
  if (event.key === "Enter") {
    event.preventDefault();
    createNewThread();
  }
});
for (const input of document.querySelectorAll("input[name='thinking-mode']")) {
  input.addEventListener("change", updateModeDescription);
}

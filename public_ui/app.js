const pages = new Set(["/", "/thinking-window", "/contact"]);
const ASK_RAHUL_ENDPOINT = "/ask-rahul";
const CONTACT_ENDPOINT = "/contact-request";
const THINKING_COUNT_KEY = "rahul-thinking-window-count";
const CONTACT_PROFILE_KEY = "rahul-public-contact";
const THEME_KEY = "rahul-theme";

const els = {
  answerZone: document.querySelector("#answer-zone"),
  status: document.querySelector("#ask-status"),
  answer: document.querySelector("#answer-text"),
  evidence: document.querySelector("#evidence-list"),
  contactStatus: document.querySelector("#contact-status"),
  softContact: document.querySelector("[data-soft-contact]"),
  themeToggle: document.querySelector("[data-theme-toggle]"),
  portrait: document.querySelector("[data-portrait]"),
};

function apiPath(path) {
  return path;
}

function preferredTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
}

function currentPath() {
  return pages.has(window.location.pathname) ? window.location.pathname : "/";
}

function pageForPath(path) {
  if (path === "/thinking-window") return "thinking";
  if (path === "/contact") return "contact";
  return "portfolio";
}

function renderRoute() {
  const path = currentPath();
  const page = pageForPath(path);

  for (const section of document.querySelectorAll("[data-page]")) {
    section.hidden = section.dataset.page !== page;
  }

  for (const link of document.querySelectorAll("[data-route]")) {
    const href = link.getAttribute("href");
    link.classList.toggle("active", href === path || (href === "/" && path === "/"));
  }
}

function go(path) {
  window.history.pushState({}, "", path);
  renderRoute();
}

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Request failed with HTTP ${response.status}`);
  }
  return data;
}

function setStatus(message, kind = "") {
  els.status.textContent = message;
  els.status.className = `status ${kind}`.trim();
}

function splitSource(source) {
  const [file, section] = String(source || "public_corpus").split("#");
  return {file, section: section || "Summary"};
}

function renderEvidence(items) {
  els.evidence.innerHTML = "";
  if (!items || !items.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No public evidence supports that claim yet.";
    els.evidence.appendChild(empty);
    return;
  }

  for (const item of items) {
    const row = document.createElement("article");
    const source = splitSource(item.source);
    const meta = document.createElement("p");
    const excerpt = document.createElement("p");

    meta.className = "evidence-source";
    meta.textContent = `${source.file} · ${source.section}`;
    excerpt.textContent = item.excerpt || "";

    row.append(meta, excerpt);
    els.evidence.appendChild(row);
  }
}

function contactProfile() {
  return JSON.parse(localStorage.getItem(CONTACT_PROFILE_KEY) || "{}");
}

function saveContactProfile(form) {
  const profile = {
    email: form.elements.email?.value.trim() || "",
    phone: form.elements.phone?.value.trim() || "",
  };
  localStorage.setItem(CONTACT_PROFILE_KEY, JSON.stringify(profile));
}

function thinkingCount() {
  return Number(localStorage.getItem(THINKING_COUNT_KEY) || "0");
}

function incrementThinkingCount() {
  const next = thinkingCount() + 1;
  localStorage.setItem(THINKING_COUNT_KEY, String(next));
  if (next >= 2 && els.softContact) {
    els.softContact.hidden = false;
  }
}

async function ask(question, sourcePage = "portfolio") {
  const cleaned = question.trim();
  if (!cleaned) {
    setStatus("Ask a sharper question.", "error");
    return;
  }

  if (sourcePage === "thinking_window") {
    go("/thinking-window");
    incrementThinkingCount();
  }

  const profile = contactProfile();
  els.answerZone.hidden = false;
  els.answer.textContent = "";
  renderEvidence([]);
  setStatus("Reading the public evidence trail...");

  try {
    const response = await fetch(apiPath(ASK_RAHUL_ENDPOINT), {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({
        question: cleaned,
        source_page: sourcePage,
        contact_email: profile.email || null,
        contact_phone: profile.phone || null,
      }),
    });
    const data = await parseResponse(response);
    els.answer.textContent = data.answer || "";
    renderEvidence(data.evidence || []);
    setStatus((data.evidence || []).length ? "Answered with public evidence." : "Bounded by available public evidence.", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function submitContact(form, statusElement, source = "contact") {
  const payload = {
    name: form.elements.name?.value.trim() || null,
    email: form.elements.email.value.trim(),
    phone: form.elements.phone?.value.trim() || null,
    context_type: form.elements.context_type?.value || "other",
    message: form.elements.message.value.trim(),
    source,
  };

  statusElement.textContent = "Sending...";
  statusElement.className = "status";

  try {
    const response = await fetch(apiPath(CONTACT_ENDPOINT), {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify(payload),
    });
    await parseResponse(response);
    saveContactProfile(form);
    statusElement.textContent = "Received. Rahul has the signal.";
    statusElement.className = "status ok";
    form.reset();
  } catch (error) {
    statusElement.textContent = error.message;
    statusElement.className = "status error";
  }
}

for (const link of document.querySelectorAll("[data-route]")) {
  link.addEventListener("click", event => {
    event.preventDefault();
    go(link.getAttribute("href"));
  });
}

for (const form of document.querySelectorAll("[data-ask-form]")) {
  form.addEventListener("submit", event => {
    event.preventDefault();
    ask(form.elements.question.value, form.dataset.sourcePage || "portfolio");
  });
}

for (const chip of document.querySelectorAll("[data-question]")) {
  chip.addEventListener("click", () => ask(chip.dataset.question, chip.dataset.sourcePage || "portfolio"));
}

for (const form of document.querySelectorAll("[data-contact-form]")) {
  form.addEventListener("submit", event => {
    event.preventDefault();
    submitContact(form, els.contactStatus, "contact");
  });
}

for (const form of document.querySelectorAll("[data-inline-contact-form]")) {
  const status = document.createElement("p");
  status.className = "status";
  form.after(status);
  form.addEventListener("submit", event => {
    event.preventDefault();
    submitContact(form, status, "thinking_window");
  });
}

if (els.themeToggle) {
  els.themeToggle.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
}

if (els.portrait) {
  els.portrait.addEventListener("error", () => {
    els.portrait.hidden = true;
  });
}

window.addEventListener("popstate", renderRoute);
applyTheme(preferredTheme());
if (thinkingCount() >= 2 && els.softContact) els.softContact.hidden = false;
renderRoute();

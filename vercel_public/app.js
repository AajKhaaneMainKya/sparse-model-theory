const pages = new Set(["/", "/thinking-window", "/contact"]);
const ASK_RAHUL_ENDPOINT = "/api/ask-rahul";
const CONTACT_ENDPOINT = "/api/contact-request";
const THINKING_COUNT_KEY = "rahul-thinking-window-count";
const CONTACT_PROFILE_KEY = "rahul-public-contact";
const THEME_KEY = "rahul-theme";

const themeToggle = document.querySelector("[data-theme-toggle]");
const themeIcon = document.querySelector("[data-theme-icon]");
const softContact = document.querySelector("[data-soft-contact]");

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
  if (themeIcon) themeIcon.textContent = theme === "dark" ? "☾" : "☼";
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

  if (window.location.pathname !== path) {
    window.history.replaceState({}, "", path);
  }
}

function go(path) {
  window.history.pushState({}, "", path);
  renderRoute();
  window.scrollTo({top: 0, behavior: "smooth"});
}

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error("That did not go through. Try a shorter note or a valid email.");
  }
  return data;
}

function contactProfile() {
  try {
    return JSON.parse(localStorage.getItem(CONTACT_PROFILE_KEY) || "{}");
  } catch {
    return {};
  }
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
  if (next >= 2 && softContact) softContact.hidden = false;
}

function splitSource(source) {
  const [file, section] = String(source || "public_corpus").split("#");
  return {file, section: section || "Summary"};
}

function statusText(evidenceCount) {
  return evidenceCount ? "Evidence-backed" : "Bounded by public evidence";
}

function setSurfaceLoading(surface, question) {
  const output = surface.querySelector("[data-ask-output]");
  const label = surface.querySelector("[data-question-label]");
  const status = surface.querySelector("[data-ask-status]");
  const answer = surface.querySelector("[data-answer-text]");
  const evidence = surface.querySelector("[data-evidence-list]");

  output.hidden = false;
  output.dataset.state = "loading";
  label.textContent = question;
  status.textContent = "Reading public evidence";
  answer.textContent = "";
  evidence.innerHTML = "";
}

function renderEvidence(surface, items) {
  const evidence = surface.querySelector("[data-evidence-list]");
  evidence.innerHTML = "";

  if (!items || !items.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No public evidence supports that claim yet.";
    evidence.appendChild(empty);
    return;
  }

  for (const item of items) {
    const source = splitSource(item.source);
    const row = document.createElement("article");
    const meta = document.createElement("p");
    const excerpt = document.createElement("p");

    meta.className = "evidence-source";
    meta.textContent = `${source.file} · ${source.section}`;
    excerpt.textContent = item.excerpt || "";

    row.append(meta, excerpt);
    evidence.appendChild(row);
  }
}

function renderAnswer(surface, question, data) {
  const output = surface.querySelector("[data-ask-output]");
  const label = surface.querySelector("[data-question-label]");
  const status = surface.querySelector("[data-ask-status]");
  const answer = surface.querySelector("[data-answer-text]");
  const evidenceItems = data.evidence || [];

  output.hidden = false;
  output.dataset.state = "ready";
  label.textContent = question;
  status.textContent = statusText(evidenceItems.length);
  answer.textContent = data.answer || "";
  renderEvidence(surface, evidenceItems);
}

function renderAskError(surface, question, message) {
  const output = surface.querySelector("[data-ask-output]");
  const label = surface.querySelector("[data-question-label]");
  const status = surface.querySelector("[data-ask-status]");
  const answer = surface.querySelector("[data-answer-text]");

  output.hidden = false;
  output.dataset.state = "error";
  label.textContent = question;
  status.textContent = "Not sent";
  answer.textContent = message || "That did not go through. Try again in a moment.";
  renderEvidence(surface, []);
}

async function askFromSurface(surface, question) {
  const cleaned = question.trim();
  const sourcePage = surface.dataset.sourcePage || "portfolio";

  if (!cleaned) {
    renderAskError(surface, "No question yet", "Ask a sharper question.");
    return;
  }

  if (sourcePage === "thinking_window") incrementThinkingCount();

  const profile = contactProfile();
  setSurfaceLoading(surface, cleaned);

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
    renderAnswer(surface, cleaned, data);
  } catch (error) {
    renderAskError(surface, cleaned, error.message);
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

  statusElement.textContent = "Sending";
  statusElement.className = "form-status";

  try {
    const response = await fetch(apiPath(CONTACT_ENDPOINT), {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify(payload),
    });
    await parseResponse(response);
    saveContactProfile(form);
    statusElement.textContent = "Received. Rahul has the signal.";
    statusElement.className = "form-status ok";
    form.reset();
  } catch (error) {
    statusElement.textContent = error.message;
    statusElement.className = "form-status error";
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
    const surface = form.closest("[data-ask-surface]");
    askFromSurface(surface, form.elements.question.value);
  });
}

for (const chip of document.querySelectorAll("[data-question]")) {
  chip.addEventListener("click", () => {
    const surface = chip.closest("[data-ask-surface]");
    const field = surface.querySelector("[name='question']");
    field.value = chip.dataset.question;
    askFromSurface(surface, chip.dataset.question);
  });
}

for (const form of document.querySelectorAll("[data-contact-form]")) {
  const status = form.querySelector("[data-contact-status]");
  form.addEventListener("submit", event => {
    event.preventDefault();
    submitContact(form, status, "contact");
  });
}

for (const form of document.querySelectorAll("[data-inline-contact-form]")) {
  const status = document.createElement("p");
  status.className = "form-status";
  form.after(status);
  form.addEventListener("submit", event => {
    event.preventDefault();
    submitContact(form, status, "thinking_window");
  });
}

for (const portrait of document.querySelectorAll("[data-portrait]")) {
  portrait.addEventListener("error", () => {
    portrait.hidden = true;
    portrait.closest(".portrait-wrap")?.classList.add("portrait-missing");
  });
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
}

window.addEventListener("popstate", renderRoute);
applyTheme(preferredTheme());
if (thinkingCount() >= 2 && softContact) softContact.hidden = false;
renderRoute();

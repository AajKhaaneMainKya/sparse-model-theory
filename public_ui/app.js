const pages = new Set(["/", "/thinking-window", "/contact"]);
const ASK_RAHUL_ENDPOINT = "/api/ask-rahul";
const THINKING_WINDOW_ENDPOINT = "/api/thinking-window";
const CONTACT_ENDPOINT = "/api/contact-request";
const THINKING_COUNT_KEY = "rahul-thinking-window-count";
const CONTACT_PROFILE_KEY = "rahul-public-contact";
const THEME_KEY = "rahul-theme";

const themeToggle = document.querySelector("[data-theme-toggle]");
const themeIcon = document.querySelector("[data-theme-icon]");
const softContact = document.querySelector("[data-soft-contact]");
const navMenu = document.querySelector("[data-nav-menu]");
const navLinks = document.querySelector("[data-nav-links]");

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
  if (themeIcon) themeIcon.textContent = theme === "dark" ? "Dark" : "Light";
}

function currentPath() {
  return pages.has(window.location.pathname) ? window.location.pathname : "/";
}

function pageForPath(path) {
  if (path === "/thinking-window") return "thinking";
  if (path === "/contact") return "contact";
  return "portfolio";
}

function closeMobileNav() {
  document.body.classList.remove("nav-open");
  navMenu?.setAttribute("aria-expanded", "false");
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

  closeMobileNav();
}

function go(path) {
  window.history.pushState({}, "", path);
  renderRoute();
  window.scrollTo({top: 0, behavior: "smooth"});
}

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "That did not go through. Try a shorter note or a valid email.");
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

function endpointForSurface(surface) {
  return surface.dataset.sourcePage === "thinking_window" ? THINKING_WINDOW_ENDPOINT : ASK_RAHUL_ENDPOINT;
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
  answer.textContent = "Building a grounded answer...";
  evidence.innerHTML = "";
  output.scrollIntoView({block: "nearest", behavior: "smooth"});
}

function renderEvidence(surface, items, label = "Evidence trail") {
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
    meta.textContent = `${label}: ${source.file} · ${source.section}`;
    excerpt.textContent = item.excerpt || "";

    row.append(meta, excerpt);
    evidence.appendChild(row);
  }
}

// ---------- Structured-answer flow diagrams ----------
// Long answers that describe a sequence, a set of parallel states, or a
// decision framework read as a wall of text even with good typography.
// This detects that shape from the plain-text answer and renders it as a
// small connected diagram (nodes + connectors) instead, reusing the site's
// existing card/shadow tokens so it looks native. A short, unstructured
// answer is left as plain prose — the diagram only appears when the
// content actually has a shape worth drawing.

const SEQUENCE_LEAD_WORDS = /^(first|then|next|after that|finally|second|third|lastly)\b/i;
// A short, title-cased phrase (1-4 words), repeated 3+ times separated by
// "/" — e.g. "Verified / Declared / Missing / Conflict detected".
const SLASH_SEGMENT = "[A-Z][\\w-]*(?:\\s+[A-Za-z][\\w-]*){0,3}";
const SLASH_STATE_PATTERN = new RegExp(`${SLASH_SEGMENT}(?:\\s*/\\s*${SLASH_SEGMENT}){2,}`);
const TONE_RULES = [
  {pattern: /\b(verified|done|complete|confirmed|shipped|passed?|ready)\b/i, tone: "tone-positive"},
  {pattern: /\b(missing|conflict|failed?|blocked|risk|declined|error)\b/i, tone: "tone-negative"},
  {pattern: /\b(declared|pending|unknown|tbd|in progress)\b/i, tone: "tone-neutral"},
];

function truncateLabel(text, max) {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

// "Label: rest of the sentence" / "Label — rest" -> a short node label plus
// a longer supporting-detail sentence rendered below the diagram. Falls
// back to a trimmed short label with no separate detail when the whole
// item is already short, or a truncated label with the full item kept as
// detail when it is not.
function splitLabelDetail(raw) {
  const item = raw.trim();
  const sep = item.match(/^(.{2,40}?)\s*(?::|—|-)\s+(.+)$/);
  if (sep) return {label: sep[1].trim(), detail: sep[2].trim()};
  const words = item.split(/\s+/);
  if (words.length <= 8) return {label: item, detail: ""};
  return {label: truncateLabel(words.slice(0, 7).join(" "), 60), detail: item};
}

function parseAnswerStructure(rawText) {
  const text = String(rawText || "").trim();
  if (!text) return {type: "prose", paragraphs: []};

  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const paragraphs = text.split(/\n{2,}/).map(p => p.trim()).filter(Boolean);
  const prose = {type: "prose", paragraphs: paragraphs.length ? paragraphs : [text]};

  // Numbered/bulleted-list detection needs at least two list lines to mean
  // anything; a one-line answer skips straight to the single-line checks
  // below (slash-separated states, a colon-introduced list) rather than
  // bailing out to prose before those ever run.
  if (lines.length >= 2) {
    const numbered = lines.map(line => line.match(/^(\d+)[.)]\s+(.+)$/)).filter(Boolean);
    if (numbered.length >= 2 && numbered.length >= lines.length * 0.6) {
      return {type: "sequence", nodes: numbered.map(m => splitLabelDetail(m[2]))};
    }

    // A question line followed by a run of short follow-up lines reads as
    // a root question branching into sub-considerations. Checked before
    // the generic bulleted-list detector below: the sub-considerations
    // are very often themselves bulleted, which would otherwise make this
    // shape get swallowed into a flat category list with the question
    // discarded.
    const qIndex = lines.findIndex(line => line.endsWith("?"));
    if (qIndex !== -1) {
      const rest = lines.slice(qIndex + 1);
      const children = rest.filter(line => /^[-*•]/.test(line) || line.length < 90).slice(0, 6);
      if (children.length >= 2) {
        return {
          type: "tree",
          root: splitLabelDetail(lines[qIndex]),
          nodes: children.map(c => splitLabelDetail(c.replace(/^[-*•]\s+/, ""))),
        };
      }
    }

    const bulleted = lines.map(line => line.match(/^[-*•]\s+(.+)$/)).filter(Boolean);
    if (bulleted.length >= 2 && bulleted.length >= lines.length * 0.6) {
      const items = bulleted.map(m => m[1]);
      const seqCount = items.filter(item => SEQUENCE_LEAD_WORDS.test(item)).length;
      const type = seqCount >= Math.ceil(items.length / 2) ? "sequence" : "categories";
      return {type, nodes: items.map(splitLabelDetail)};
    }
  }

  // A run of short slash-separated states, e.g. "...claims: Verified /
  // Declared / Missing / Conflict detected." — matched as a substring
  // anywhere in the text (not the whole line), since it's usually the
  // tail end of a lead-in sentence rather than a line of its own.
  const slashMatch = text.match(SLASH_STATE_PATTERN);
  if (slashMatch) {
    const parts = slashMatch[0].split("/").map(part => part.trim()).filter(Boolean);
    if (parts.length >= 3) return {type: "categories", nodes: parts.map(p => ({label: p, detail: ""}))};
  }

  // "...three things: identity, intent, compatibility." — a short
  // comma-separated list introduced by a colon.
  const colonMatch = text.match(/:\s*([^.:\n]+)\.?\s*$/);
  if (colonMatch) {
    const candidates = colonMatch[1].split(",").map(s => s.trim()).filter(Boolean);
    if (candidates.length >= 3 && candidates.every(c => c.split(/\s+/).length <= 5)) {
      return {type: "categories", nodes: candidates.map(p => ({label: p, detail: ""}))};
    }
  }

  return prose;
}

function toneFor(label, index) {
  for (const rule of TONE_RULES) if (rule.pattern.test(label)) return rule.tone;
  return index % 2 === 0 ? "tone-a" : "tone-b";
}

function buildFlowNode(node, {index, tone, root} = {}) {
  const el = document.createElement("div");
  el.className = "flow-node";
  if (tone) el.classList.add("flow-node-tone", tone);
  if (root) el.classList.add("flow-node-root");

  if (typeof index === "number") {
    const badge = document.createElement("span");
    badge.className = "flow-node-index";
    badge.textContent = String(index);
    el.appendChild(badge);
  }

  const label = document.createElement("p");
  label.className = "flow-node-label";
  label.textContent = node.label;
  el.appendChild(label);
  return el;
}

function appendFlowDetails(container, nodes) {
  const withDetail = nodes.filter(node => node.detail);
  if (!withDetail.length) return;

  const list = document.createElement("div");
  list.className = "flow-details";
  for (const node of withDetail) {
    const row = document.createElement("p");
    row.className = "flow-detail-row";
    const strong = document.createElement("strong");
    strong.textContent = node.label;
    row.append(strong, document.createTextNode(` — ${node.detail}`));
    list.appendChild(row);
  }
  container.appendChild(list);
}

function renderSequenceDiagram(container, nodes) {
  const flow = document.createElement("div");
  flow.className = "flow-diagram flow-sequence";
  nodes.forEach((node, i) => {
    if (i > 0) {
      const connector = document.createElement("span");
      connector.className = "flow-connector";
      connector.setAttribute("aria-hidden", "true");
      flow.appendChild(connector);
    }
    flow.appendChild(buildFlowNode(node, {index: i + 1}));
  });
  container.appendChild(flow);
  appendFlowDetails(container, nodes);
}

function renderCategoriesDiagram(container, nodes) {
  const flow = document.createElement("div");
  flow.className = "flow-diagram flow-categories";
  nodes.forEach((node, i) => flow.appendChild(buildFlowNode(node, {tone: toneFor(node.label, i)})));
  container.appendChild(flow);
  appendFlowDetails(container, nodes);
}

function renderTreeDiagram(container, root, nodes) {
  const wrap = document.createElement("div");
  wrap.className = "flow-diagram flow-tree";

  wrap.appendChild(buildFlowNode(root, {root: true}));

  const branches = document.createElement("div");
  branches.className = "flow-branches";
  for (const node of nodes) branches.appendChild(buildFlowNode(node));
  wrap.appendChild(branches);

  container.appendChild(wrap);
  appendFlowDetails(container, [root, ...nodes]);
}

// ---------- Markdown rendering ----------
// Model answers routinely come back as real markdown: "## " headers,
// numbered/bulleted lists, "**bold**", and "| a | b |" tables. None of
// that was ever parsed — it rendered as literal text with the stray #, *,
// and | characters visible. This is a small, purpose-built block parser
// for exactly that whitelist (headers, lists, tables, bold/italic/code,
// paragraphs) — not a general Markdown/HTML renderer. Every text segment
// is escaped first via escapeHtml, and only the specific tags this code
// inserts itself are ever added afterward, so a model response can never
// inject arbitrary HTML (a literal "<img onerror=...>" in the answer text
// becomes the inert string "&lt;img onerror=...&gt;" before any markdown
// substitution runs).

const HEADING_TAGS = {1: "h3", 2: "h3", 3: "h4", 4: "h5"};

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Inline formatting within an already-block-parsed line: bold, italic,
// inline code. Operates on escaped text, so the only tags that can appear
// in the result are the <strong>/<em>/<code> this function writes itself.
function renderInlineMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  return html;
}

function splitTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map(cell => cell.trim());
}

const TABLE_SEPARATOR_LINE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

// Splits answer text into typed blocks (heading/table/ol/ul/paragraph).
// Deliberately only recognizes explicit markdown syntax (a line starting
// with "#", a real "|...|" table with a "---" separator row, "1. "/"- "
// list markers) — it does not try to guess structure from plain prose,
// which is what the separate shape-detector below is for.
function parseMarkdownBlocks(rawText) {
  const lines = String(rawText || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }

    const headerMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headerMatch) {
      blocks.push({type: "heading", level: Math.min(headerMatch[1].length, 4), text: headerMatch[2].trim()});
      i++;
      continue;
    }

    if (line.includes("|") && lines[i + 1] && TABLE_SEPARATOR_LINE.test(lines[i + 1])) {
      const header = splitTableRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        rows.push(splitTableRow(lines[i]));
        i++;
      }
      blocks.push({type: "table", header, rows});
      continue;
    }

    if (/^\d+[.)]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+[.)]\s+/, "").trim());
        i++;
      }
      blocks.push({type: "ol", items});
      continue;
    }

    if (/^[-*•]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*•]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*•]\s+/, "").trim());
        i++;
      }
      blocks.push({type: "ul", items});
      continue;
    }

    const paraLines = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^#{1,6}\s+/.test(lines[i]) &&
      !/^\d+[.)]\s+/.test(lines[i]) &&
      !/^[-*•]\s+/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    blocks.push({type: "p", text: paraLines.join(" ").trim()});
  }

  return blocks;
}

function renderMarkdownAnswer(container, rawText) {
  const blocks = parseMarkdownBlocks(rawText);
  if (!blocks.length) {
    const p = document.createElement("p");
    p.textContent = "No answer returned.";
    container.appendChild(p);
    return;
  }

  for (const block of blocks) {
    if (block.type === "heading") {
      const el = document.createElement(HEADING_TAGS[block.level] || "h4");
      el.className = "answer-heading";
      el.innerHTML = renderInlineMarkdown(block.text);
      container.appendChild(el);
    } else if (block.type === "p") {
      const el = document.createElement("p");
      el.innerHTML = renderInlineMarkdown(block.text);
      container.appendChild(el);
    } else if (block.type === "ol" || block.type === "ul") {
      const el = document.createElement(block.type);
      el.className = "answer-list";
      for (const item of block.items) {
        const li = document.createElement("li");
        li.innerHTML = renderInlineMarkdown(item);
        el.appendChild(li);
      }
      container.appendChild(el);
    } else if (block.type === "table") {
      const wrap = document.createElement("div");
      wrap.className = "answer-table-wrap";
      const table = document.createElement("table");
      table.className = "answer-table";

      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      for (const cell of block.header) {
        const th = document.createElement("th");
        th.innerHTML = renderInlineMarkdown(cell);
        headRow.appendChild(th);
      }
      thead.appendChild(headRow);
      table.appendChild(thead);

      const tbody = document.createElement("tbody");
      for (const row of block.rows) {
        const tr = document.createElement("tr");
        for (const cell of row) {
          const td = document.createElement("td");
          td.innerHTML = renderInlineMarkdown(cell);
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);

      wrap.appendChild(table);
      container.appendChild(wrap);
    }
  }
}

// A real markdown header, table, or bold span is a much more reliable
// structural signal than the plain-text shape guesses below, and a long
// markdown document (the common case for model output) shouldn't get
// force-fit into a 3-4 node diagram meant for short, bare, unformatted
// answers. So: markdown syntax present -> render it properly as rich
// text; otherwise -> try the compact shape diagrams; otherwise -> plain
// paragraphs (still routed through the markdown renderer so a stray
// inline "**word**" in an otherwise plain answer still renders).
const MARKDOWN_SIGNAL = /(^|\n)#{1,6}\s+\S|\*\*[^*\n]+\*\*|(^|\n)[ \t]*\|.+\|[ \t]*(\n|$)/;

function renderAnswerContent(container, text) {
  container.innerHTML = "";
  const raw = String(text || "");

  if (MARKDOWN_SIGNAL.test(raw)) {
    renderMarkdownAnswer(container, raw);
    return;
  }

  const structure = parseAnswerStructure(raw);
  const nodeCount = structure.nodes ? structure.nodes.length : 0;
  const minNodes = structure.type === "tree" ? 2 : 3;

  if (structure.type !== "prose" && nodeCount >= minNodes) {
    if (structure.type === "sequence") renderSequenceDiagram(container, structure.nodes);
    else if (structure.type === "categories") renderCategoriesDiagram(container, structure.nodes);
    else if (structure.type === "tree") renderTreeDiagram(container, structure.root, structure.nodes);
    return;
  }

  renderMarkdownAnswer(container, raw || "No answer returned.");
}

function renderAnswer(surface, question, data) {
  const output = surface.querySelector("[data-ask-output]");
  const label = surface.querySelector("[data-question-label]");
  const status = surface.querySelector("[data-ask-status]");
  const answer = surface.querySelector("[data-answer-text]");
  const evidenceItems = data.evidence || data.grounding || [];

  output.hidden = false;
  output.dataset.state = "ready";
  label.textContent = question;
  status.textContent = data.status === "blocked" ? "Blocked" : statusText(evidenceItems.length);
  renderAnswerContent(answer, data.answer || "No answer returned.");
  renderEvidence(surface, evidenceItems, data.mode === "thinking_window" ? "Grounding" : "Evidence trail");
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
    const response = await fetch(apiPath(endpointForSurface(surface)), {
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

// Persistent-header links that point at a section inside the home page
// (Proof, Ask Rahul CTA). A bare `#id` href only works while already on
// "/" — from any other route it just appends the hash to the current
// path, and the target (nested inside the home-only [data-page]
// wrapper) is hidden, so the click silently does nothing. This routes
// home first (a no-op if already there, since go()/renderRoute() are
// synchronous) and then scrolls to the now-visible target.
for (const link of document.querySelectorAll("[data-anchor]")) {
  link.addEventListener("click", event => {
    event.preventDefault();
    if (currentPath() !== "/") go("/");
    document.getElementById(link.dataset.anchor)?.scrollIntoView({behavior: "smooth", block: "start"});
    closeMobileNav();
  });
}

for (const link of document.querySelectorAll('a[href^="#"]')) {
  link.addEventListener("click", () => closeMobileNav());
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
    portrait.closest(".portrait-chip")?.classList.add("portrait-missing");
  });
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
}

if (navMenu && navLinks) {
  navMenu.addEventListener("click", () => {
    const open = !document.body.classList.contains("nav-open");
    document.body.classList.toggle("nav-open", open);
    navMenu.setAttribute("aria-expanded", String(open));
  });
}

const observer = "IntersectionObserver" in window
  ? new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.isIntersecting) entry.target.classList.add("is-visible");
      }
    }, {threshold: 0.12})
  : null;

for (const item of document.querySelectorAll(".reveal")) {
  if (observer) observer.observe(item);
  else item.classList.add("is-visible");
}

window.addEventListener("popstate", renderRoute);
applyTheme(preferredTheme());
if (thinkingCount() >= 2 && softContact) softContact.hidden = false;
renderRoute();

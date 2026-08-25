const pages = new Set(["/", "/projects", "/ask", "/contact"]);
const ASK_RAHUL_ENDPOINT = "/api/ask-rahul";

const els = {
  status: document.querySelector("#ask-status"),
  results: document.querySelector("#ask-results"),
  answer: document.querySelector("#answer-text"),
  evidence: document.querySelector("#evidence-list"),
  caveats: document.querySelector("#caveat-list"),
  interview: document.querySelector("#interview-list"),
};

function currentPath() {
  return pages.has(window.location.pathname) ? window.location.pathname : "/";
}

function renderRoute() {
  const path = currentPath();
  const page = path === "/" ? "home" : path.slice(1);

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

function listInto(container, items) {
  container.innerHTML = "";
  for (const item of items || []) {
    const li = document.createElement("li");
    li.textContent = item;
    container.appendChild(li);
  }
}

function renderEvidence(items) {
  els.evidence.innerHTML = "";
  if (!items || !items.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No supporting public evidence found.";
    els.evidence.appendChild(empty);
    return;
  }

  for (const item of items) {
    const article = document.createElement("article");
    const title = document.createElement("h4");
    const source = document.createElement("p");
    const excerpt = document.createElement("p");

    title.textContent = item.title || "Untitled evidence";
    source.className = "source";
    source.textContent = item.source || "public_corpus";
    excerpt.textContent = item.excerpt || "";

    article.append(title, source, excerpt);
    els.evidence.appendChild(article);
  }
}

async function ask(question) {
  const cleaned = question.trim();
  if (!cleaned) {
    setStatus("Enter a question first.", "error");
    return;
  }

  go("/ask");
  els.results.hidden = true;
  setStatus("Reading public corpus...");

  try {
    const response = await fetch(ASK_RAHUL_ENDPOINT, {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({question: cleaned}),
    });
    const data = await parseResponse(response);
    els.answer.textContent = data.answer || "";
    renderEvidence(data.evidence || []);
    listInto(els.caveats, data.caveats || []);
    listInto(els.interview, data.suggested_interview_questions || []);
    els.results.hidden = false;
    setStatus("Answered from public corpus.", "ok");
  } catch (error) {
    setStatus(error.message, "error");
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
    const input = form.elements.question;
    ask(input.value);
  });
}

for (const chip of document.querySelectorAll("[data-question]")) {
  chip.addEventListener("click", () => ask(chip.dataset.question));
}

window.addEventListener("popstate", renderRoute);
renderRoute();

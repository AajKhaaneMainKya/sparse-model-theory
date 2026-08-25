const loginForm = document.querySelector("#login-form");
const resumeForm = document.querySelector("#resume-form");
const dashboard = document.querySelector("#admin-dashboard");
const uploadStatus = document.querySelector("#upload-status");
const adminStatus = document.querySelector("#admin-status");
const contactRequests = document.querySelector("#contact-requests");
const questionLogs = document.querySelector("#question-logs");
const refreshButton = document.querySelector("#refresh-admin");
const logoutButton = document.querySelector("#logout-admin");

function setStatus(element, message, kind = "") {
  element.textContent = message;
  element.className = `status ${kind}`.trim();
}

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Request failed with HTTP ${response.status}`);
  }
  return data;
}

function renderRows(container, rows, emptyText, renderRow) {
  container.innerHTML = "";
  if (!rows || rows.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  for (const row of rows) {
    container.appendChild(renderRow(row));
  }
}

function textLine(label, value) {
  const line = document.createElement("p");
  line.innerHTML = `<strong>${label}</strong> ${value || "—"}`;
  return line;
}

async function loadDashboard() {
  const data = await parseResponse(await fetch("/admin/dashboard-data"));
  renderRows(contactRequests, data.contact_requests, "No contact requests yet.", row => {
    const item = document.createElement("article");
    item.append(
      textLine("Email", row.email),
      textLine("Phone", row.phone),
      textLine("Context", row.context_type),
      textLine("Notification", row.notification_status),
      textLine("Message", row.message),
    );
    return item;
  });
  renderRows(questionLogs, data.public_question_logs, "No public questions logged yet.", row => {
    const item = document.createElement("article");
    item.append(
      textLine("Source", row.source_page),
      textLine("Status", row.answer_status),
      textLine("Evidence", row.evidence_count),
      textLine("Question", row.question),
    );
    return item;
  });
}

async function unlock(password) {
  await parseResponse(await fetch("/admin/login", {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({password}),
  }));
  loginForm.hidden = true;
  dashboard.hidden = false;
  setStatus(adminStatus, "Admin unlocked.", "ok");
  await loadDashboard();
}

loginForm.addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await unlock(loginForm.elements.password.value);
  } catch (error) {
    setStatus(adminStatus, error.message, "error");
  }
});

resumeForm.addEventListener("submit", async event => {
  event.preventDefault();
  const fileInput = resumeForm.elements.resume;
  if (!fileInput.files || fileInput.files.length === 0) {
    setStatus(uploadStatus, "Choose a .txt, .md, .pdf, or .docx resume first.", "error");
    return;
  }

  const body = new FormData();
  body.append("resume", fileInput.files[0]);
  body.append("label", resumeForm.elements.label.value);
  setStatus(uploadStatus, "Uploading resume...");

  try {
    const response = await fetch("/admin/resume-upload", {method: "POST", body});
    const data = await parseResponse(response);
    const warning = data.warnings && data.warnings.length ? ` Warnings: ${data.warnings.join(" ")}` : "";
    setStatus(
      uploadStatus,
      `Uploaded ${data.source} and ${data.facts_source} (${data.fact_count} facts).${warning}`,
      "ok",
    );
    resumeForm.reset();
  } catch (error) {
    setStatus(uploadStatus, error.message, "error");
  }
});

refreshButton.addEventListener("click", async () => {
  try {
    await loadDashboard();
    setStatus(adminStatus, "Dashboard refreshed.", "ok");
  } catch (error) {
    setStatus(adminStatus, error.message, "error");
  }
});

logoutButton.addEventListener("click", async () => {
  await fetch("/admin/logout", {method: "POST"});
  dashboard.hidden = true;
  loginForm.hidden = false;
  setStatus(adminStatus, "Logged out.");
});

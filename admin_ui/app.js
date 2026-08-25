const form = document.querySelector("#resume-form");
const statusEl = document.querySelector("#upload-status");

function setStatus(message, kind = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${kind}`.trim();
}

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Upload failed with HTTP ${response.status}`);
  }
  return data;
}

form.addEventListener("submit", async event => {
  event.preventDefault();

  const fileInput = form.elements.resume;
  if (!fileInput.files || fileInput.files.length === 0) {
    setStatus("Choose a .txt, .md, .pdf, or .docx resume first.", "error");
    return;
  }

  const body = new FormData();
  body.append("resume", fileInput.files[0]);
  body.append("label", form.elements.label.value);

  const headers = {};
  const token = form.elements.adminToken.value.trim();
  if (token) {
    headers["X-Admin-Token"] = token;
  }

  setStatus("Uploading resume...");

  try {
    const response = await fetch("/admin/resume-upload", {
      method: "POST",
      headers,
      body,
    });
    const data = await parseResponse(response);
    setStatus(
      `Uploaded ${data.source} (${data.character_count} characters). Ask Rahul can now use this public resume evidence.`,
      "ok",
    );
    form.reset();
  } catch (error) {
    setStatus(error.message, "error");
  }
});

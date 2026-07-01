const API_ORIGINS = ["http://127.0.0.1:8000", "http://127.0.0.1:8001"];

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.action === "CAREERSITE_WATCH") {
    postLocalJson("/autofill/observe", message.payload || {})
      .then(sendResponse)
      .catch((error) => sendResponse({ error: error.message, page_type: "other" }));
    return true;
  }

  if (message?.action === "CAREERSITE_TAILOR_PREVIEW") {
    postLocalJson("/autofill/tailoring/preview", message.payload || {})
      .then(sendResponse)
      .catch((error) => sendResponse({ error: error.message }));
    return true;
  }

  if (message?.action === "CAREERSITE_TAILOR_FINALIZE") {
    postLocalJson("/autofill/tailoring/finalize", message.payload || {})
      .then(sendResponse)
      .catch((error) => sendResponse({ error: error.message }));
    return true;
  }

  if (message?.action === "CAREERSITE_TAILOR_RENDER_PREVIEW") {
    postLocalJson("/autofill/tailoring/render-preview", message.payload || {})
      .then(sendResponse)
      .catch((error) => sendResponse({ error: error.message }));
    return true;
  }

  if (message?.action === "CAREERSITE_TAILOR_DOWNLOAD") {
    downloadLocalFile(message.path || "")
      .then(sendResponse)
      .catch((error) => sendResponse({ error: error.message }));
    return true;
  }

  return false;
});

async function postLocalJson(path, payload) {
  const errors = [];
  for (const origin of API_ORIGINS) {
    try {
      return await postJson(`${origin}${path}`, payload);
    } catch (error) {
      errors.push(`${origin}: ${error.message}`);
    }
  }
  throw new Error(`Local CareerSite API is unavailable. Tried ${errors.join("; ")}`);
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Local CareerSite API returned HTTP ${response.status}`);
  }
  return response.json();
}

async function downloadLocalFile(path) {
  if (!path.startsWith("/autofill/tailoring/download/")) {
    throw new Error("Invalid local tailoring download path.");
  }
  const errors = [];
  for (const origin of API_ORIGINS) {
    const url = `${origin}${path}`;
    try {
      const response = await fetch(url, { headers: { Range: "bytes=0-0" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const downloadId = await chrome.downloads.download({ url, saveAs: true });
      return { started: true, download_id: downloadId };
    } catch (error) {
      errors.push(`${origin}: ${error.message}`);
    }
  }
  throw new Error(`Download is unavailable. Tried ${errors.join("; ")}`);
}

// =========================
// Gestion de la page "Logs"
// =========================

const state = {
  page: 1,
  per_page: 25,
  q: "",
  ip: "",
  campaign: "",
  file: "",
  days: "",
  timer: null,
};

function qs(sel) { return document.querySelector(sel); }

async function fetchLogs() {
  const params = new URLSearchParams({
    page: state.page,
    per_page: state.per_page,
  });
  ["q", "ip", "campaign", "file", "days"].forEach(k => {
    if (state[k]) params.set(k, state[k]);
  });

  const res = await fetch(`/api/logs?${params.toString()}`);
  const data = await res.json();
  renderLogs(data);
}

function renderLogs(data) {
  const tbody = qs("#logs-tbody");
  const meta = qs("#logs-meta");
  tbody.innerHTML = "";

  data.items.forEach(item => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${item.ts}</td>
      <td>${item.ip || ""}</td>
      <td>${item.country || ""} ${item.city ? "• " + item.city : ""}</td>
      <td>${escapeHtml(item.user_agent || "")}</td>
      <td>${escapeHtml(item.file_name || "")}</td>
      <td>${escapeHtml(item.campaign || "")}</td>
      <td>
        <a href="${item.click_url}" target="_blank">ouvrir</a> · 
        <a href="${item.qr_url}" target="_blank">QR</a> · 
        <button class="delete-link-btn" data-id="${item.link_id}">Supprimer</button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  // Bind deletion buttons
  tbody.querySelectorAll(".delete-link-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm("Voulez-vous vraiment supprimer ce lien et ses clics associés ?")) return;
      const linkId = btn.dataset.id;
      try {
        const resp = await fetch(`/delete_link/${linkId}`, { method: "DELETE" });
        if (resp.ok) {
          alert(`Lien ${linkId} supprimé avec succès`);
          fetchLogs();
        } else {
          alert("Erreur lors de la suppression");
        }
      } catch (err) {
        console.error(err);
        alert("Erreur réseau ou serveur");
      }
    });
  });

  meta.textContent = `Page ${data.page} • ${data.items.length} / ${data.total} entrées`;

  qs("#btn-prev").disabled = data.page <= 1;
  qs("#btn-next").disabled = data.page * state.per_page >= data.total;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}

function bindLogsUI() {
  const inputs = ["q", "ip", "campaign", "file", "days", "per_page"];
  inputs.forEach(id => {
    const el = qs(`#${id}`);
    if (!el) return;
    el.addEventListener("input", () => {
      const v = el.value.trim();
      if (id === "per_page") {
        state.per_page = Math.max(1, Math.min(parseInt(v || "25", 10), 200));
      } else {
        state[id] = v;
      }
      state.page = 1;
      fetchLogs();
    });
  });

  qs("#btn-prev").addEventListener("click", () => { state.page = Math.max(1, state.page - 1); fetchLogs(); });
  qs("#btn-next").addEventListener("click", () => { state.page = state.page + 1; fetchLogs(); });

  // auto refresh
  const intervalSel = qs("#refresh");
  const setTimer = () => {
    if (state.timer) clearInterval(state.timer);
    const ms = parseInt(intervalSel.value, 10);
    if (ms > 0) {
      state.timer = setInterval(fetchLogs, ms);
    }
  };
  intervalSel.addEventListener("change", setTimer);
  setTimer();

  fetchLogs();
}

// ================================
// Gestion suppression page d'accueil
// ================================
function bindIndexDeleteButtons() {
  document.querySelectorAll(".delete-btn").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      const id = btn.dataset.id;
      if (!confirm("Supprimer ce lien et tous ses clics ?")) return;
      try {
        const resp = await fetch(`/delete_link/${id}`, { method: "DELETE" });
        if (resp.ok) {
          // retirer la ligne
          btn.closest("tr").remove();
        } else {
          alert("Erreur lors de la suppression");
        }
      } catch (err) {
        console.error(err);
        alert("Erreur réseau ou serveur");
      }
    });
  });
}

// =========================
// Initialisation globale
// =========================
document.addEventListener("DOMContentLoaded", () => {
  if (qs("#logs-page-flag")) {
    bindLogsUI();
  }
  if (qs("#index-page-flag")) {
    bindIndexDeleteButtons();
  }
});

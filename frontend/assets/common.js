// Shared helpers for all pages
const ZONE_UZ = { red: "Qizil", yellow: "Sariq", green: "Yashil" };
const SOURCE_UZ = { self: "o'zi kiritgan", clinic: "klinika", lab: "laboratoriya", device: "qurilma" };
const KIND_UZ = { mother: "Homilador", newborn: "Chaqaloq" };

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function zoneChip(z) { return `<span class="zone ${z}"><span class="dot ${z}"></span>${ZONE_UZ[z] || z}</span>`; }

// Backend sends naive UTC timestamps; treat them as UTC unless a zone is already present.
function parseUTC(iso) { return iso ? new Date(/(Z|[+-]\d\d:\d\d)$/.test(iso) ? iso : iso + "Z") : null; }

function ago(iso) {
  const d = parseUTC(iso); if (!d) return "—";
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "hozirgina";
  if (s < 3600) return `${Math.floor(s / 60)} daq oldin`;
  if (s < 86400) return `${Math.floor(s / 3600)} soat oldin`;
  return `${Math.floor(s / 86400)} kun oldin`;
}

function fmtDate(iso, withTime = true) {
  const d = parseUTC(iso); if (!d) return "—";
  const p = n => String(n).padStart(2, "0");
  const s = `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
  return withTime ? `${s} ${p(d.getHours())}:${p(d.getMinutes())}` : s;
}

function toast(msg, ms = 3500) {
  let el = document.querySelector(".toast");
  if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
  el.textContent = msg; el.classList.add("show");
  clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove("show"), ms);
}

function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = 880; o.connect(g); g.connect(ctx.destination);
    g.gain.setValueAtTime(0.08, ctx.currentTime); g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.5);
    o.start(); o.stop(ctx.currentTime + 0.5);
  } catch {}
}

const ACTOR_KEY = "perizone.actor";
function currentActor() {
  try { return localStorage.getItem(ACTOR_KEY) || "OvaBMU mutaxassisi"; } catch { return "OvaBMU mutaxassisi"; }
}
function setActor(v) { try { localStorage.setItem(ACTOR_KEY, v); } catch {} }

function headerHTML(active) {
  const link = (href, key, label) => `<a href="${href}" class="${active === key ? "active" : ""}">${label}</a>`;
  return `<header class="top">
    <div class="brand"><span class="logo"><i style="background:var(--red)"></i><i style="background:var(--yellow-dot)"></i><i style="background:var(--green)"></i></span>
      PeriZone <span class="muted small" style="font-weight:400">· Perinatal xavf registri</span></div>
    <nav>
      ${link("/", "dash", "Monitoring")}
      ${link("/patients.html", "patients", "Registr")}
      ${link("/rules.html", "rules", "Qoidalar va ML")}
      ${link("/mother.html", "mother", "Ona ilovasi")}
    </nav></header>`;
}

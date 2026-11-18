// PeriZone — shared frontend helpers (auth, layout, icons, formatting)
const ZONE_UZ = { red: "Qizil", yellow: "Sariq", green: "Yashil" };
const SOURCE_UZ = { self: "o'zi kiritgan", clinic: "klinika", lab: "laboratoriya", device: "qurilma" };
const KIND_UZ = { mother: "Homilador ayol", newborn: "Chaqaloq" };
const ROLE_UZ = { doctor: "Shifokor", owner: "Administrator" };

// ---- icons (Lucide-style paths) ----
const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  doctor: '<path d="M4.8 2.3A.3.3 0 1 0 5 2H4a2 2 0 0 0-2 2v5a6 6 0 0 0 6 6 6 6 0 0 0 6-6V4a2 2 0 0 0-2-2h-1a.2.2 0 1 0 .3.3"/><path d="M8 15v1a6 6 0 0 0 6 6 6 6 0 0 0 6-6v-4"/><circle cx="20" cy="10" r="2"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  heart: '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  map: '<path d="M14.1 6 9.9 4 3 7v14l6.9-3 4.2 2 6.9-3V3z"/><path d="M9.9 4v14M14.1 6v14"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  baby: '<path d="M9 12h.01M15 12h.01"/><path d="M10 16c.5.3 1.2.5 2 .5s1.5-.2 2-.5"/><path d="M19 6.3a9 9 0 0 1 1.8 3.9 2 2 0 0 1 0 3.6 9 9 0 0 1-17.6 0 2 2 0 0 1 0-3.6A9 9 0 0 1 12 3c2 0 3.5 1.1 3.5 2.5s-.9 2.5-2 2.5c-.8 0-1.5-.4-1.5-1"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  chart: '<path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  telegram: '<path d="m22 3-20 8 7 2 2 7 4-5 5 4z"/><path d="m9 13 6-5"/>',
  star: '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>',
  bot: '<rect x="3" y="8" width="18" height="12" rx="3"/><path d="M12 8V4M8 4h8"/><circle cx="9" cy="14" r="1.2"/><circle cx="15" cy="14" r="1.2"/>',
  key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
  money: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
  sparkle: '<path d="M12 3l1.9 5.8L20 10l-6.1 1.2L12 17l-1.9-5.8L4 10l6.1-1.2z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  bellOn: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/><path d="M4 2 2 4M20 2l2 2"/>',
};
function icon(name, cls = "") { return `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`; }

// ---- API ----
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" }, credentials: "same-origin", ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401 && !path.startsWith("/api/auth") && !opts.noRedirect) {
    location.href = "/login.html?next=" + encodeURIComponent(location.pathname + location.search);
    throw new Error("Tizimga kiring");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : (j.detail?.[0]?.msg || JSON.stringify(j.detail)); } catch {}
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}

// ---- formatting ----
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function zoneChip(z) { return `<span class="zone ${z}">${ZONE_UZ[z] || z}</span>`; }
function parseUTC(iso) { return iso ? new Date(/(Z|[+-]\d\d:\d\d)$/.test(iso) ? iso : iso + "Z") : null; }
function ago(iso) {
  const d = parseUTC(iso); if (!d) return "—";
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "hozirgina";
  if (s < 3600) return `${Math.floor(s / 60)} daqiqa oldin`;
  if (s < 86400) return `${Math.floor(s / 3600)} soat oldin`;
  return `${Math.floor(s / 86400)} kun oldin`;
}
function fmtDate(iso, withTime = true) {
  const d = parseUTC(iso); if (!d) return "—";
  const p = n => String(n).padStart(2, "0");
  const s = `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
  return withTime ? `${s}, ${p(d.getHours())}:${p(d.getMinutes())}` : s;
}
function fmtDuration(sec) {
  if (sec == null) return "—";
  if (sec < 3600) return `${Math.max(1, Math.round(sec / 60))} daq`;
  if (sec < 86400) return `${(sec / 3600).toFixed(1)} soat`;
  return `${(sec / 86400).toFixed(1)} kun`;
}
function initials(name) { return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase(); }
function avatar(name, zone, cls = "") { return `<span class="avatar ${zone || "blue"} ${cls}">${esc(initials(name))}</span>`; }
function patientMeta(p) {
  if (p.kind === "mother") {
    const st = p.postpartum_days != null ? `Tug'ruqdan keyin ${p.postpartum_days} kun` : p.gestational_weeks != null ? p.gestational_weeks + " hafta" : "Homilador";
    return `${st}${p.age ? " · " + p.age + " yosh" : ""}`;
  }
  return `Chaqaloq · ${p.age_days ?? "?"} kunlik`;
}
function toast(msg, ms = 3200) {
  let el = document.querySelector(".toast");
  if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
  el.textContent = msg; el.classList.add("show");
  clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove("show"), ms);
}
function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
async function copyText(t) { try { await navigator.clipboard.writeText(t); toast("Nusxa olindi"); } catch { prompt("Nusxa oling:", t); } }
function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)(), o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = 880; o.connect(g); g.connect(ctx.destination);
    g.gain.setValueAtTime(0.07, ctx.currentTime); g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.45);
    o.start(); o.stop(ctx.currentTime + 0.45);
  } catch {}
}
function emptyState(text, ic = "check") { return `<div class="empty">${icon(ic)}<div>${text}</div></div>`; }

// ---- layout ----
const NAV = [
  { href: "/", key: "home", icon: "home", label: "Bosh sahifa" },
  { href: "/patients.html", key: "patients", icon: "users", label: { doctor: "Bemorlarim", owner: "Bemorlar" } },
  { href: "/doctors.html", key: "doctors", icon: "doctor", label: "Shifokorlar", owner: true },
  { href: "/subscriptions.html", key: "subs", icon: "star", label: "Obunalar", owner: true },
  { href: "/guide.html", key: "guide", icon: "book", label: "Qanday ishlaydi" },
];

function renderShell(active, me) {
  const app = document.getElementById("app");
  const nav = NAV.filter(n => !n.owner || me.role === "owner").map(n => {
    const label = typeof n.label === "string" ? n.label : n.label[me.role];
    return `<a href="${n.href}" class="${active === n.key ? "active" : ""}">${icon(n.icon)}<span>${label}</span>${n.key === "home" ? '<span class="count hidden" id="navAlerts"></span>' : ""}</a>`;
  }).join("");
  const sidebar = document.createElement("aside");
  sidebar.className = "sidebar"; sidebar.id = "sidebar";
  sidebar.innerHTML = `
    <div class="brand"><span class="dots"><i style="background:var(--red)"></i><i style="background:var(--yellow)"></i><i style="background:var(--green)"></i></span>
      <div>PeriZone<small>Perinatal xavf registri</small></div></div>
    <nav class="nav">${nav}
      <div class="sep"></div><div class="label">Bemorlar uchun</div>
      <a href="/mother.html" target="_blank" rel="noopener">${icon("heart")}<span>Ona sahifasi</span>${icon("external", "sm")}</a>
    </nav>
    <div class="user-card">${avatar(me.full_name, "blue")}
      <div class="who"><b title="${esc(me.full_name)}">${esc(me.full_name)}</b><span>${ROLE_UZ[me.role]}${me.district ? " · " + esc(me.district) : ""}</span></div>
      <button class="icon-btn" id="logoutBtn" title="Chiqish">${icon("logout")}</button></div>`;
  const mobile = document.createElement("div");
  mobile.className = "mobile-bar";
  mobile.innerHTML = `<button class="icon-btn" id="menuBtn" aria-label="Menyu">${icon("menu")}</button>
    <div class="brand" style="padding:0"><span class="dots"><i style="background:var(--red)"></i><i style="background:var(--yellow)"></i><i style="background:var(--green)"></i></span>PeriZone</div>`;
  app.prepend(sidebar);
  document.querySelector(".main").prepend(mobile);
  document.getElementById("logoutBtn").onclick = async () => { await api("/api/auth/logout", { method: "POST" }).catch(() => {}); location.href = "/login.html"; };
  document.getElementById("menuBtn").onclick = () => {
    sidebar.classList.add("open");
    const scrim = document.createElement("div"); scrim.className = "scrim";
    scrim.onclick = () => { sidebar.classList.remove("open"); scrim.remove(); };
    document.body.appendChild(scrim);
  };
}

async function boot(active, { ownerOnly = false } = {}) {
  const [me, meta] = await Promise.all([api("/api/me"), api("/api/meta")]);
  if (ownerOnly && me.role !== "owner") { location.href = "/"; throw new Error("owner only"); }
  renderShell(active, me);
  document.body.classList.add("role-" + me.role);
  startAlertWatcher();
  return { me, meta };
}

// ---- site-wide alert watcher: badge + sound + desktop notification for new red alerts ----
let _seenAlerts = null;  // alert id -> last seen version (updated_at or created_at)
async function checkAlerts() {
  try {
    const alerts = await api("/api/alerts?status=open&limit=50", { noRedirect: true });
    setNavAlerts(alerts.length);
    const ver = a => a.updated_at || a.created_at;
    const fresh = _seenAlerts ? alerts.filter(a => _seenAlerts.get(a.id) !== ver(a)) : [];
    _seenAlerts = new Map([...(_seenAlerts || []), ...alerts.map(a => [a.id, ver(a)])]);
    if (fresh.length) {
      const top = fresh.find(a => a.zone === "red") || fresh[0];
      const isNew = !top.updated_at;
      beep();
      toast(`${top.zone === "red" ? "🔴" : "🟡"} ${isNew ? top.title : "Bemordan yangi ma'lumot"}: ${top.patient_name}`, 6000);
      if ("Notification" in window && Notification.permission === "granted") {
        const n = new Notification(`PeriZone — ${isNew ? "yangi xabarnoma" : "yangi ma'lumot"}`, { body: `${top.patient_name}: ${top.message.split(String.fromCharCode(10))[0]}`, tag: "pz-" + top.id + ver(top) });
        n.onclick = () => { window.focus(); location.href = `/patient.html?id=${top.patient_id}`; };
      }
      document.dispatchEvent(new CustomEvent("pz:new-alerts", { detail: fresh }));
    }
  } catch {}
}
let _lastReport = null;
async function checkReports() {
  try {
    const reps = await api("/api/reports?limit=10", { noRedirect: true });
    if (!reps.length) return;
    if (_lastReport !== null) {
      const fresh = reps.filter(r => r.at > _lastReport);
      if (fresh.length) {
        const r = fresh[0];
        if (r.level === "green") beep();  // abnormal ones also raise an alert (handled by checkAlerts)
        toast(`📥 ${r.patient_name}: ${r.summary}${r.symptoms.length ? " · " + r.symptoms.join(", ") : ""}`, 6000);
        if ("Notification" in window && Notification.permission === "granted" && r.level === "green") {
          const n = new Notification("PeriZone — bemordan ma'lumot", { body: `${r.patient_name}: ${r.summary}`, tag: "pz-rep-" + r.id });
          n.onclick = () => { window.focus(); location.href = `/patient.html?id=${r.patient_id}`; };
        }
        document.dispatchEvent(new CustomEvent("pz:new-alerts", { detail: [] }));
      }
    }
    _lastReport = reps[0].at;
  } catch {}
}
function startAlertWatcher() {
  checkAlerts(); checkReports();
  setInterval(() => { checkAlerts(); checkReports(); }, 8000);
  if ("Notification" in window && Notification.permission === "default") {
    const card = document.querySelector(".user-card");
    const b = document.createElement("button");
    b.className = "btn sm block"; b.style.marginBottom = "8px";
    b.innerHTML = icon("bellOn", "sm") + "Bildirishnomalarni yoqish";
    b.onclick = async () => { await Notification.requestPermission(); b.remove(); toast("Bildirishnomalar yoqildi"); };
    card.parentNode.insertBefore(b, card);
  }
}
function fmtMoneyShort(n) {
  if (n == null) return "—";
  if (n >= 1e6) return `${(n / 1e6).toFixed(2).replace(".", ",")}<small>mln so'm</small>`;
  if (n >= 1e3) return `${Math.round(n / 1e3)}<small>ming so'm</small>`;
  return `${n}<small>so'm</small>`;
}
function fmtMoney(n) { return n == null ? "—" : `${Math.round(n).toLocaleString("ru-RU").replace(/,/g, " ")} so'm`; }

function setNavAlerts(n) {
  const el = document.getElementById("navAlerts");
  if (!el) return;
  el.textContent = n; el.classList.toggle("hidden", !n);
}

// What a doctor should do in each zone (shown on patient card + guide). Demo protocol — to be approved.
const ZONE_ACTIONS = {
  red: { title: "Shoshilinch: 1 soat ichida chora ko'ring", items: ["Bemorga darhol qo'ng'iroq qiling yoki uyiga boring", "O'zi kiritgan ma'lumot bo'lsa — klinik o'lchov bilan tasdiqlang", "Zarur bo'lsa perinatal markazga yo'naltiring yoki 103 chaqiring", "Xabarnomada qilingan amalni belgilang"] },
  yellow: { title: "Diqqat: 24 soat ichida bog'laning", items: ["Bemor bilan bog'lanib, ahvolini aniqlang", "Keyingi ko'rikni yaqinlashtiring", "Kuzatuvni kuchaytiring — har 2–3 kunda ma'lumot", "Kerak bo'lsa qo'shimcha tahlil buyuring"] },
  green: { title: "Rejali kuzatuv", items: ["Rejadagi ko'riklarni davom ettiring", "Bemor har 1–2 haftada holatini yuborsin", "Xavf belgilari haqida eslatib turing"] },
};

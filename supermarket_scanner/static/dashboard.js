/* Shared helpers + page logic for dashboard, POS and inventory. */
const $ = (s, r = document) => r.querySelector(s);
const CUR = document.body.dataset.currency || "₦";
const money = n => CUR + Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(url, method = "GET", body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function toast(msg, isErr = false) {
  const t = document.createElement("div");
  t.className = "toast" + (isErr ? " err" : "");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

/* Poll scanner events. First poll only learns the latest id so old scans are not replayed. */
function watchScans(onScan) {
  let since = null;
  async function tick() {
    try {
      const d = await api("/api/scan/poll" + (since === null ? "" : "?since=" + since));
      const first = since === null;
      since = d.last_id;
      if (!first) d.events.forEach(onScan);
    } catch (e) { /* server restarting; try again */ }
    setTimeout(tick, 600);
  }
  tick();
}

function bindScannerControls() {
  const status = $("#scanner-status");
  async function refresh() {
    try {
      const s = await api("/api/scanner/status");
      if (status) status.textContent = s.error ? s.error : (s.running ? "Camera on" : "Camera off");
    } catch (e) {}
  }
  $("#scan-start")?.addEventListener("click", async () => {
    await api("/api/scanner/start", "POST");
    $("#cam").src = "/video_feed?" + Date.now();
    setTimeout(refresh, 800);
  });
  $("#scan-stop")?.addEventListener("click", async () => {
    await api("/api/scanner/stop", "POST");
    setTimeout(refresh, 300);
  });
  $("#manual-form")?.addEventListener("submit", async e => {
    e.preventDefault();
    const inp = $("#manual-code");
    if (!inp.value.trim()) return;
    await api("/api/scan/manual", "POST", { barcode: inp.value.trim() });
    inp.value = "";
  });
  $("#photo")?.addEventListener("change", async e => {
    const f = e.target.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("image", f);
    const r = await fetch("/api/scan/image", { method: "POST", body: fd }).then(r => r.json());
    toast(r.codes.length ? "Read " + r.codes.join(", ") : "No barcode found in photo", !r.codes.length);
    e.target.value = "";
  });
  refresh();
}

/* ---------------- Dashboard ---------------- */
async function initDashboard() {
  bindScannerControls();
  const feed = $("#feed");
  watchScans(ev => {
    const li = document.createElement("li");
    li.innerHTML = ev.product
      ? `<strong>${esc(ev.product.name)}</strong> <span class="price">${money(ev.product.price)}</span>`
      : `${esc(ev.barcode)} <span class="badge low">not in inventory</span>`;
    feed.querySelector(".empty")?.remove();
    feed.prepend(li);
  });
  async function load() {
    const s = await api("/api/stats");
    $("#s-rev").textContent = money(s.today.revenue);
    $("#s-sales").textContent = s.today.sales;
    $("#s-items").textContent = s.today.items;
    $("#s-prod").textContent = s.inventory.products;
    $("#s-val").textContent = money(s.inventory.value);
    $("#low").innerHTML = s.low_stock.length
      ? s.low_stock.map(p => `<tr><td>${esc(p.name)}</td><td class="r"><span class="badge ${p.stock === 0 ? "low" : ""}">${p.stock} left</span></td></tr>`).join("")
      : `<tr><td class="empty">Every product is above its minimum stock.</td></tr>`;
    $("#recent").innerHTML = s.recent_sales.length
      ? s.recent_sales.map(r => `<tr><td>Sale #${r.id}</td><td class="muted">${esc(r.created_at)}</td><td class="r price">${money(r.total)}</td></tr>`).join("")
      : `<tr><td class="empty">No sales yet. Open Point of sale to ring up the first one.</td></tr>`;
    $("#top").innerHTML = s.top.length
      ? s.top.map(t => `<tr><td>${esc(t.name)}</td><td class="r">${t.sold} sold</td></tr>`).join("")
      : `<tr><td class="empty">Best sellers appear after the first sale.</td></tr>`;
  }
  load();
  setInterval(load, 10000);
}

/* ---------------- POS ---------------- */
function initPOS() {
  bindScannerControls();
  const cart = new Map(); // barcode -> {product, qty}

  function render() {
    const body = $("#cart");
    if (!cart.size) {
      body.innerHTML = `<tr><td colspan="4" class="empty">Scan a barcode or type one in to start the sale.</td></tr>`;
    } else {
      body.innerHTML = [...cart.values()].map(({ product: p, qty }) => `
        <tr>
          <td>${esc(p.name)}<div class="muted">${esc(p.barcode)}</div></td>
          <td><span class="qty"><button data-a="dec" data-b="${esc(p.barcode)}" aria-label="Decrease quantity">−</button>${qty}<button data-a="inc" data-b="${esc(p.barcode)}" aria-label="Increase quantity">+</button></span></td>
          <td class="r price">${money(p.price * qty)}</td>
          <td class="r"><button class="danger" data-a="del" data-b="${esc(p.barcode)}" aria-label="Remove ${esc(p.name)}">✕</button></td>
        </tr>`).join("");
    }
    const total = [...cart.values()].reduce((s, l) => s + l.product.price * l.qty, 0);
    $("#total").textContent = money(total);
    $("#pay").disabled = !cart.size;
  }

  function add(p) {
    const line = cart.get(p.barcode);
    if (line && line.qty >= p.stock) return toast(`Only ${p.stock} of ${p.name} in stock`, true);
    if (!line && p.stock < 1) return toast(`${p.name} is out of stock`, true);
    line ? line.qty++ : cart.set(p.barcode, { product: p, qty: 1 });
    render();
  }

  watchScans(ev => {
    if (!ev.product) return toast(`${ev.barcode} is not in inventory. Add it under Inventory.`, true);
    add(ev.product);
    toast("Added " + ev.product.name);
  });

  $("#cart").addEventListener("click", e => {
    const b = e.target.closest("button");
    if (!b) return;
    const line = cart.get(b.dataset.b);
    if (b.dataset.a === "del") cart.delete(b.dataset.b);
    if (b.dataset.a === "inc") add(line.product);
    if (b.dataset.a === "dec") { line.qty--; if (line.qty < 1) cart.delete(b.dataset.b); }
    render();
  });

  $("#clear").addEventListener("click", () => { cart.clear(); render(); });
  $("#pay").addEventListener("click", async () => {
    try {
      const items = [...cart.values()].map(l => ({ barcode: l.product.barcode, qty: l.qty }));
      const r = await api("/api/checkout", "POST", { items });
      toast(`Sale #${r.sale_id} complete: ${money(r.total)}`);
      cart.clear();
      render();
    } catch (e) { toast(e.message, true); }
  });
  render();
}

/* ---------------- Inventory ---------------- */
function initInventory() {
  bindScannerControls();
  const dlg = $("#dlg"), form = $("#pform");
  let editing = null, items = [];

  async function load() {
    items = await api("/api/products?q=" + encodeURIComponent($("#search").value));
    $("#rows").innerHTML = items.length ? items.map(p => `
      <tr>
        <td>${esc(p.name)}<div class="muted">${esc(p.barcode)}</div></td>
        <td>${esc(p.category)}</td>
        <td class="r price">${money(p.price)}</td>
        <td class="r"><span class="badge ${p.stock <= p.min_stock ? "low" : "ok"}">${p.stock}</span></td>
        <td class="r"><button data-a="edit" data-id="${p.id}">Edit</button> <button class="danger" data-a="del" data-id="${p.id}">Delete</button></td>
      </tr>`).join("")
      : `<tr><td colspan="5" class="empty">No products match. Add one with the button above, or scan a new barcode.</td></tr>`;
  }

  function openDialog(p = {}) {
    editing = p.id || null;
    $("#dtitle").textContent = editing ? "Edit product" : "Add product";
    for (const k of ["barcode", "name", "category", "price", "stock", "min_stock"]) form.elements[k].value = p[k] ?? (k === "category" ? "General" : k === "min_stock" ? 5 : k === "stock" || k === "price" ? 0 : "");
    dlg.showModal();
  }

  $("#add").addEventListener("click", () => openDialog());
  $("#cancel").addEventListener("click", () => dlg.close());
  $("#search").addEventListener("input", load);
  $("#rows").addEventListener("click", async e => {
    const b = e.target.closest("button");
    if (!b) return;
    const p = items.find(i => i.id == b.dataset.id);
    if (b.dataset.a === "edit") openDialog(p);
    if (b.dataset.a === "del" && confirm(`Delete ${p.name}? Past sales keep their records.`)) {
      await api("/api/products/" + p.id, "DELETE");
      toast("Deleted " + p.name);
      load();
    }
  });
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(form));
    try {
      editing ? await api("/api/products/" + editing, "PUT", d) : await api("/api/products", "POST", d);
      dlg.close();
      toast("Saved " + d.name);
      load();
    } catch (err) { toast(err.message, true); }
  });

  // Scanning fills the barcode while the dialog is open; otherwise it finds or starts a product.
  watchScans(ev => {
    if (dlg.open) { form.elements.barcode.value = ev.barcode; return; }
    if (ev.product) { $("#search").value = ev.barcode; load(); toast("Found " + ev.product.name); }
    else { openDialog({ barcode: ev.barcode }); toast("New barcode: fill in the details"); }
  });
  load();
}

const page = document.body.dataset.page;
if (page === "dashboard") initDashboard();
if (page === "pos") initPOS();
if (page === "inventory") initInventory();

const TIER_THRESHOLD = 100;
const LOW_STOCK = 5;

const $ = (sel) => document.querySelector(sel);
const money = (v) => `$${Number(v).toFixed(2)}`;

let products = [];
let cart = null;

// ---------- API ----------

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message = data.detail?.message || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
}

async function run(action) {
  try {
    await action();
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------- product feed ----------

function renderProducts() {
  const grid = $('[data-testid="product-grid"]');
  grid.innerHTML = "";
  for (const p of products) {
    const card = document.createElement("article");
    card.className = "card";
    card.dataset.testid = `product-${p.id}`;
    card.innerHTML = `
      <div class="thumb">
        <span>${p.emoji}</span>
      </div>
      <div class="info">
        <div class="name">${p.name}</div>
        <div class="price">${money(p.price)}</div>
        ${p.stock <= LOW_STOCK ? `
          <div class="stock" data-testid="stock-${p.id}">
            ${p.stock > 0 ? `Only ${p.stock} left` : "Sold out"}
          </div>` : ""}
        <button class="add" data-testid="add-${p.id}" ${p.stock === 0 ? "disabled" : ""}>
          ${p.stock === 0 ? "Sold out" : "Add to cart"}
        </button>
      </div>`;
    card.querySelector(".add").addEventListener("click", () =>
      run(async () => {
        cart = await api("POST", `/api/carts/${cart.id}/items`, {
          product_id: p.id,
          qty: 1,
        });
        renderCart();
        toast(`Added ${p.name}`);
      }),
    );
    grid.appendChild(card);
  }
}

async function loadProducts() {
  products = await api("GET", "/api/products");
  renderProducts();
}

// ---------- cart ----------

function renderCart() {
  const count = cart.items.reduce((n, i) => n + i.qty, 0);
  const badge = $('[data-testid="cart-count"]');
  badge.textContent = count;
  badge.hidden = count === 0;

  const lines = $('[data-testid="cart-lines"]');
  lines.innerHTML = "";
  for (const item of cart.items) {
    const li = document.createElement("li");
    li.className = "line";
    li.dataset.testid = `line-${item.product_id}`;
    li.innerHTML = `
      <span class="emoji">${item.emoji}</span>
      <span class="meta">${item.name}<small>${money(item.price)} each</small></span>
      <span class="stepper">
        <button data-act="dec" aria-label="Decrease">−</button>
        <span data-testid="qty-${item.product_id}">${item.qty}</span>
        <button data-act="inc" aria-label="Increase">+</button>
      </span>`;
    li.querySelector('[data-act="dec"]').addEventListener("click", () => changeQty(item, -1));
    li.querySelector('[data-act="inc"]').addEventListener("click", () => changeQty(item, 1));
    lines.appendChild(li);
  }
  $('[data-testid="cart-empty"]').hidden = cart.items.length > 0;

  // Progress towards the spend-$100 discount
  const sub = Number(cart.subtotal);
  const tier = $('[data-testid="tier-progress"]');
  const unlocked = Number(cart.tier_discount) > 0;
  tier.classList.toggle("unlocked", unlocked);
  tier.querySelector(".tier-text").textContent = unlocked
    ? "🎉 10% off unlocked!"
    : `Add ${money(TIER_THRESHOLD - sub)} more to get 10% off`;
  tier.querySelector(".fill").style.width = `${Math.min(100, (sub / TIER_THRESHOLD) * 100)}%`;
  tier.hidden = cart.items.length === 0;

  const chips = $('[data-testid="coupon-chips"]');
  chips.innerHTML = "";
  for (const code of cart.coupons) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `${code} <button aria-label="Remove coupon">✕</button>`;
    chip.querySelector("button").addEventListener("click", () =>
      run(async () => {
        cart = await api("DELETE", `/api/carts/${cart.id}/coupons/${code}`);
        renderCart();
      }),
    );
    chips.appendChild(chip);
  }

  $('[data-testid="subtotal"]').textContent = money(cart.subtotal);
  $('[data-testid="tier-discount"]').textContent = `-${money(cart.tier_discount)}`;
  $('[data-testid="coupon-discount"]').textContent = `-${money(cart.coupon_discount)}`;
  $('[data-testid="total"]').textContent = money(cart.total);

  $('[data-testid="checkout"]').disabled = cart.items.length === 0;
}

function changeQty(item, delta) {
  run(async () => {
    const qty = item.qty + delta;
    cart = qty < 1
      ? await api("DELETE", `/api/carts/${cart.id}/items/${item.product_id}`)
      : await api("PATCH", `/api/carts/${cart.id}/items/${item.product_id}`, { qty });
    renderCart();
  });
}

async function newCart() {
  cart = await api("POST", "/api/carts");
  renderCart();
}

// ---------- UI wiring ----------

function toast(message, isError = false) {
  const el = $('[data-testid="toast"]');
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), 2500);
}

function setOverlay(testid, open) {
  $(`[data-testid="${testid}"]`).hidden = !open;
}

$('[data-testid="open-cart"]').addEventListener("click", () => setOverlay("cart-overlay", true));
$('[data-testid="close-cart"]').addEventListener("click", () => setOverlay("cart-overlay", false));
$('[data-testid="cart-overlay"]').addEventListener("click", (e) => {
  if (e.target === e.currentTarget) setOverlay("cart-overlay", false);
});

$('[data-testid="coupon-form"]').addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $('[data-testid="coupon-input"]');
  const code = input.value.trim();
  if (!code) return;
  run(async () => {
    cart = await api("POST", `/api/carts/${cart.id}/coupons`, { code });
    input.value = "";
    renderCart();
  });
});

$('[data-testid="checkout"]').addEventListener("click", () =>
  run(async () => {
    const order = await api("POST", `/api/carts/${cart.id}/checkout`);
    $('[data-testid="order-summary"]').textContent =
      `Order #${order.order_id} · Paid ${money(order.total)}`;
    setOverlay("cart-overlay", false);
    setOverlay("order-overlay", true);
    await Promise.all([newCart(), loadProducts()]);
  }),
);

$('[data-testid="continue-shopping"]').addEventListener("click", () =>
  setOverlay("order-overlay", false),
);

run(async () => {
  await Promise.all([loadProducts(), newCart()]);
});

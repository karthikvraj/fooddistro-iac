from flask import Flask, jsonify, request

app = Flask(__name__)

# ... keep all your existing imports, DynamoDB/RDS setup, APIs, etc ...

@app.route("/")
def index():
    # Simple single-page UI
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>FoodDistro Backend UI</title>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 0;
      background: #0b1120;
      color: #e5e7eb;
    }
    header {
      background: #111827;
      padding: 16px 24px;
      border-bottom: 1px solid #1f2937;
    }
    header h1 {
      margin: 0;
      font-size: 24px;
      color: #f97316;
    }
    main {
      padding: 24px;
      max-width: 960px;
      margin: 0 auto;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }
    .card {
      background: #020617;
      border-radius: 12px;
      border: 1px solid #1f2937;
      padding: 16px 18px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.4);
    }
    .card h2 {
      margin-top: 0;
      font-size: 18px;
      color: #f3f4f6;
    }
    label {
      display: block;
      font-size: 13px;
      margin-top: 8px;
      color: #9ca3af;
    }
    input, textarea {
      width: 100%;
      margin-top: 4px;
      padding: 8px 10px;
      border-radius: 8px;
      border: 1px solid #374151;
      background: #020617;
      color: #e5e7eb;
      font-size: 14px;
    }
    input:focus, textarea:focus {
      outline: 2px solid #f97316;
      outline-offset: 1px;
      border-color: #f97316;
    }
    button {
      margin-top: 10px;
      padding: 8px 14px;
      border-radius: 999px;
      border: none;
      background: #f97316;
      color: #020617;
      font-weight: 600;
      cursor: pointer;
      font-size: 14px;
    }
    button:hover {
      background: #fb923c;
    }
    .tag {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      background: #111827;
      border: 1px solid #1f2937;
      font-size: 11px;
      color: #9ca3af;
      margin-left: 8px;
    }
    #status {
      margin-top: 20px;
      padding: 12px 14px;
      border-radius: 12px;
      background: #020617;
      border: 1px solid #1f2937;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      font-size: 12px;
      max-height: 260px;
      overflow: auto;
      white-space: pre-wrap;
    }
    .pill-row {
      font-size: 12px;
      margin-bottom: 8px;
      color: #9ca3af;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid #374151;
      margin-right: 6px;
    }
    .pill span {
      margin-left: 4px;
      color: #e5e7eb;
    }
  </style>
</head>
<body>
<header>
  <h1>FoodDistro Backend <span class="tag">ECS · ALB · DynamoDB · RDS</span></h1>
</header>
<main>
  <div class="pill-row">
    <div class="pill">User ID: <span id="pill-user">not set</span></div>
    <div class="pill">Session ID: <span id="pill-session">not set</span></div>
    <div class="pill">Last Order ID: <span id="pill-order">none</span></div>
  </div>

  <div class="grid">
    <!-- Session -->
    <section class="card">
      <h2>1. Session</h2>
      <label>User ID</label>
      <input id="userId" placeholder="e.g. user-123" />
      <button onclick="createSession()">Create Session</button>
    </section>

    <!-- Cart -->
    <section class="card">
      <h2>2. Cart</h2>
      <label>Session ID (auto-filled)</label>
      <input id="sessionIdCart" placeholder="session id" />

      <label>Items JSON</label>
      <textarea id="cartItems" rows="4">[
  {"sku":"pizza-margherita","qty":1},
  {"sku":"salad-greek","qty":2}
]</textarea>

      <button onclick="saveCart()">Save Cart</button>
      <button onclick="loadCart()">Load Cart</button>
    </section>

    <!-- Order -->
    <section class="card">
      <h2>3. Order</h2>
      <label>User ID (auto-filled)</label>
      <input id="userIdOrder" />

      <label>Session ID (auto-filled)</label>
      <input id="sessionIdOrder" />

      <label>Order Total</label>
      <input id="orderTotal" type="number" step="0.01" placeholder="42.50" />

      <button onclick="createOrder()">Place Order</button>
      <button onclick="loadOrder()">Get Order Details</button>
    </section>
  </div>

  <h2 style="margin-top:28px;font-size:16px;">Event Log</h2>
  <div id="status"></div>
</main>

<script>
  // Using same-origin; no hardcoded API base needed.
  const statusEl = document.getElementById('status');
  const pillUser = document.getElementById('pill-user');
  const pillSession = document.getElementById('pill-session');
  const pillOrder = document.getElementById('pill-order');

  function log(msg, obj) {
    const time = new Date().toISOString();
    let line = `[${time}] ${msg}`;
    if (obj) {
      line += " \\n" + JSON.stringify(obj, null, 2);
    }
    statusEl.textContent = line + "\\n\\n" + statusEl.textContent;
  }

  function setStateFromStorage() {
    const userId = localStorage.getItem('fd_userId') || '';
    const sessionId = localStorage.getItem('fd_sessionId') || '';
    const orderId = localStorage.getItem('fd_orderId') || '';

    document.getElementById('userId').value = userId;
    document.getElementById('userIdOrder').value = userId;

    document.getElementById('sessionIdCart').value = sessionId;
    document.getElementById('sessionIdOrder').value = sessionId;

    pillUser.textContent = userId || 'not set';
    pillSession.textContent = sessionId || 'not set';
    pillOrder.textContent = orderId || 'none';
  }

  async function createSession() {
    const userId = document.getElementById('userId').value.trim();
    if (!userId) {
      alert('Enter a userId first');
      return;
    }

    try {
      const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ userId })
      });
      const data = await res.json();
      if (!res.ok) throw data;

      const sessionId = data.session.sessionId;
      localStorage.setItem('fd_userId', userId);
      localStorage.setItem('fd_sessionId', sessionId);

      setStateFromStorage();
      log('Session created', data);
    } catch (err) {
      log('Error creating session', err);
    }
  }

  async function saveCart() {
    const sessionId = document.getElementById('sessionIdCart').value.trim();
    if (!sessionId) {
      alert('Session ID required. Create session first.');
      return;
    }

    let items;
    try {
      items = JSON.parse(document.getElementById('cartItems').value);
    } catch (e) {
      alert('Items JSON is invalid');
      return;
    }

    try {
      const res = await fetch('/api/cart', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ sessionId, items })
      });
      const data = await res.json();
      if (!res.ok) throw data;

      log('Cart saved', data);
    } catch (err) {
      log('Error saving cart', err);
    }
  }

  async function loadCart() {
    const sessionId = document.getElementById('sessionIdCart').value.trim();
    if (!sessionId) {
      alert('Session ID required.');
      return;
    }

    try {
      const res = await fetch('/api/cart/' + encodeURIComponent(sessionId));
      const data = await res.json();
      if (!res.ok) throw data;

      document.getElementById('cartItems').value = JSON.stringify(data.cart.items || [], null, 2);
      log('Cart loaded', data);
    } catch (err) {
      log('Error loading cart', err);
    }
  }

  async function createOrder() {
    const userId = document.getElementById('userIdOrder').value.trim();
    const sessionId = document.getElementById('sessionIdOrder').value.trim();
    const totalStr = document.getElementById('orderTotal').value.trim();

    if (!userId || !sessionId || !totalStr) {
      alert('User ID, Session ID and total are required');
      return;
    }

    const total = parseFloat(totalStr);

    try {
      const res = await fetch('/api/orders', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ userId, sessionId, total })
      });
      const data = await res.json();
      if (!res.ok) throw data;

      const orderId = data.orderId || (data.order && data.order.orderId);
      if (orderId) {
        localStorage.setItem('fd_orderId', orderId);
      }

      setStateFromStorage();
      log('Order created', data);
    } catch (err) {
      log('Error creating order', err);
    }
  }

  async function loadOrder() {
    const orderId = localStorage.getItem('fd_orderId') ||
                    prompt('Enter orderId to load');
    if (!orderId) {
      alert('No orderId found');
      return;
    }

    try {
      const res = await fetch('/api/orders/' + encodeURIComponent(orderId));
      const data = await res.json();
      if (!res.ok) throw data;

      log('Order loaded', data);
    } catch (err) {
      log('Error loading order', err);
    }
  }

  // Boot
  setStateFromStorage();
  log('UI loaded. Use the panels above to create a session, save a cart, and place an order.');
</script>
</body>
</html>
    """
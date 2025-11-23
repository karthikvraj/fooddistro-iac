import os
import json
import uuid
from datetime import datetime

from flask import Flask, jsonify, request, Response
import boto3
import pymysql

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

SESSIONS_TABLE_NAME = os.getenv("SESSIONS_TABLE_NAME", "fooddistro-sessions-dev")
CART_TABLE_NAME = os.getenv("CART_TABLE_NAME", "fooddistro-cart-dev")
ORDERS_TABLE_NAME = os.getenv("ORDERS_TABLE_NAME", "fooddistro-orders-dev")

DB_HOST = os.getenv("DB_HOST")          # e.g. fooddistro-db-dev.xxxxx.us-east-1.rds.amazonaws.com
DB_USER = os.getenv("DB_USER")          # e.g. fooddistro_app
DB_PASSWORD = os.getenv("DB_PASSWORD")  # or loaded from Secrets Manager below
DB_NAME = os.getenv("DB_NAME", "fooddistro")

DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")  # optional; if set, overrides DB_* above

app = Flask(__name__)

# ---------------------------------------------------------------------------
# AWS Clients
# ---------------------------------------------------------------------------

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)

sessions_table = dynamodb.Table(SESSIONS_TABLE_NAME)
cart_table = dynamodb.Table(CART_TABLE_NAME)
orders_ddb_table = dynamodb.Table(ORDERS_TABLE_NAME)


def load_db_credentials_from_secret():
    """
    If DB_SECRET_ARN is set, read DB credentials from Secrets Manager.
    Secret is expected to be JSON with keys: host, username, password, dbname.
    """
    if not DB_SECRET_ARN:
        return

    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    try:
        resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
        secret_str = resp.get("SecretString")
        if not secret_str:
            app.logger.warning("DB secret has no SecretString")
            return

        secret = json.loads(secret_str)
        global DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

        DB_HOST = secret.get("host", DB_HOST)
        DB_USER = secret.get("username", DB_USER)
        DB_PASSWORD = secret.get("password", DB_PASSWORD)
        DB_NAME = secret.get("dbname", DB_NAME)

        app.logger.info("Loaded DB credentials from Secrets Manager")
    except Exception as e:
        app.logger.exception(f"Failed to load DB credentials from secret: {e}")


load_db_credentials_from_secret()


def get_db_connection():
    """
    Returns a new pymysql connection to the RDS MySQL instance.
    """
    if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        raise RuntimeError(
            "Database configuration incomplete. "
            "Ensure DB_HOST, DB_USER, DB_PASSWORD, DB_NAME (or DB_SECRET_ARN) are set."
        )

    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


# ---------------------------------------------------------------------------
# HTML Frontend (Single-Page App)
# ---------------------------------------------------------------------------

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>FoodDistro Backend</title>
  <style>
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #050816;
      color: #f5f5f5;
    }
    header {
      padding: 16px 32px;
      background: #0f172a;
      border-bottom: 1px solid #1f2937;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    header h1 {
      margin: 0;
      font-size: 26px;
      color: #f97316;
    }
    header .tags span {
      margin-left: 8px;
      font-size: 12px;
      padding: 4px 8px;
      border-radius: 999px;
      background: #111827;
      color: #9ca3af;
      border: 1px solid #374151;
    }
    main {
      padding: 24px 32px 80px 32px;
    }
    .status-bar {
      margin-bottom: 16px;
      font-size: 13px;
      color: #9ca3af;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      background: #111827;
      border-radius: 999px;
      padding: 4px 10px;
      margin-right: 8px;
      border: 1px solid #1f2937;
    }
    .status-pill span.label {
      text-transform: uppercase;
      font-size: 10px;
      color: #6b7280;
      margin-right: 4px;
    }
    .status-pill span.value {
      color: #e5e7eb;
      font-weight: 600;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 20px;
      margin-bottom: 24px;
    }
    .panel {
      background: radial-gradient(circle at top left, #111827, #020617 70%);
      border-radius: 16px;
      border: 1px solid #1f2937;
      padding: 18px 18px 20px 18px;
      box-shadow: 0 18px 40px rgba(0,0,0,0.6);
    }
    .panel h2 {
      margin: 0 0 6px 0;
      font-size: 20px;
    }
    .panel small {
      color: #6b7280;
      font-size: 12px;
    }
    label {
      display: block;
      font-size: 12px;
      color: #9ca3af;
      margin-top: 14px;
      margin-bottom: 4px;
    }
    input, textarea {
      width: 100%;
      background: #020617;
      border-radius: 10px;
      border: 1px solid #1f2937;
      color: #e5e7eb;
      padding: 8px 10px;
      font-size: 13px;
      font-family: inherit;
      box-sizing: border-box;
    }
    input:focus, textarea:focus {
      outline: none;
      border-color: #f97316;
      box-shadow: 0 0 0 1px rgba(249, 115, 22, 0.6);
    }
    textarea {
      min-height: 120px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      font-size: 12px;
    }
    .btn-row {
      margin-top: 14px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    button {
      border-radius: 999px;
      border: none;
      padding: 8px 18px;
      font-size: 13px;
      cursor: pointer;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.08s ease, box-shadow 0.08s ease, background 0.08s ease;
    }
    button.primary {
      background: linear-gradient(90deg, #f97316, #ea580c);
      color: #111827;
      box-shadow: 0 8px 24px rgba(248, 113, 22, 0.4);
    }
    button.secondary {
      background: #020617;
      color: #e5e7eb;
      border: 1px solid #4b5563;
    }
    button:hover {
      transform: translateY(-1px);
      box-shadow: 0 10px 30px rgba(0,0,0,0.55);
    }
    button:active {
      transform: translateY(0);
      box-shadow: none;
    }
    .log-panel {
      background: #020617;
      border-radius: 16px;
      border: 1px solid #1f2937;
      padding: 16px 18px;
      font-size: 12px;
    }
    .log-panel h3 {
      margin: 0 0 6px 0;
      font-size: 14px;
    }
    .log-output {
      margin-top: 6px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      background: #020617;
      border-radius: 12px;
      padding: 10px 12px;
      max-height: 220px;
      overflow-y: auto;
      white-space: pre-wrap;
      line-height: 1.4;
      border: 1px solid #111827;
    }
    .log-entry-ts {
      color: #6b7280;
    }
    .log-entry-msg.ok {
      color: #22c55e;
    }
    .log-entry-msg.err {
      color: #f97316;
    }
    .pill-ok {
      color: #22c55e;
    }
    .pill-warn {
      color: #facc15;
    }
  </style>
</head>
<body>
  <header>
    <h1>FoodDistro Backend</h1>
    <div class="tags">
      <span>ECS</span><span>ALB</span><span>DynamoDB</span><span>RDS</span>
    </div>
  </header>
  <main>
    <div class="status-bar">
      <span class="status-pill">
        <span class="label">User ID:</span>
        <span class="value" id="status-user-id">not set</span>
      </span>
      <span class="status-pill">
        <span class="label">Session ID:</span>
        <span class="value" id="status-session-id">not set</span>
      </span>
      <span class="status-pill">
        <span class="label">Last Order ID:</span>
        <span class="value" id="status-order-id">none</span>
      </span>
    </div>

    <div class="grid">
      <!-- Session Panel -->
      <section class="panel">
        <h2>1. Session</h2>
        <small>Create a backend session for a FoodDistro user.</small>

        <label for="user-id">User ID</label>
        <input id="user-id" placeholder="e.g. 1234" value="1234" />

        <div class="btn-row">
          <button class="primary" id="btn-create-session">Create Session</button>
        </div>
      </section>

      <!-- Cart Panel -->
      <section class="panel">
        <h2>2. Cart</h2>
        <small>Persist the shopping cart in DynamoDB.</small>

        <label for="cart-session-id">Session ID (auto-filled)</label>
        <input id="cart-session-id" placeholder="session id" />

        <label for="cart-items-json">Items JSON</label>
        <textarea id="cart-items-json">[
  {"sku": "pizza-margherita", "qty": 1},
  {"sku": "salad-greek", "qty": 2}
]</textarea>

        <div class="btn-row">
          <button class="primary" id="btn-save-cart">Save Cart</button>
          <button class="secondary" id="btn-load-cart">Load Cart</button>
        </div>
      </section>

      <!-- Order Panel -->
      <section class="panel">
        <h2>3. Order</h2>
        <small>Write an order to RDS and DynamoDB.</small>

        <label for="order-user-id">User ID (auto-filled)</label>
        <input id="order-user-id" />

        <label for="order-session-id">Session ID (auto-filled)</label>
        <input id="order-session-id" />

        <label for="order-total">Order Total</label>
        <input id="order-total" value="42.50" />

        <label for="order-id">Order ID (for lookup)</label>
        <input id="order-id" placeholder="order id" />

        <div class="btn-row">
          <button class="primary" id="btn-place-order">Place Order</button>
          <button class="secondary" id="btn-get-order">Get Order Details</button>
        </div>
      </section>
    </div>

    <section class="log-panel">
      <h3>Event Log</h3>
      <div id="log-output" class="log-output"></div>
    </section>
  </main>

  <script>
    const statusUserId = document.getElementById("status-user-id");
    const statusSessionId = document.getElementById("status-session-id");
    const statusOrderId = document.getElementById("status-order-id");

    const userIdInput = document.getElementById("user-id");
    const cartSessionInput = document.getElementById("cart-session-id");
    const cartItemsInput = document.getElementById("cart-items-json");
    const orderUserIdInput = document.getElementById("order-user-id");
    const orderSessionIdInput = document.getElementById("order-session-id");
    const orderTotalInput = document.getElementById("order-total");
    const orderIdInput = document.getElementById("order-id");

    const logOutput = document.getElementById("log-output");

    function ts() {
      return new Date().toISOString();
    }

    function log(message, isError = false) {
      const line = document.createElement("div");
      const tsSpan = document.createElement("span");
      const msgSpan = document.createElement("span");

      tsSpan.className = "log-entry-ts";
      tsSpan.textContent = `[${ts()}] `;

      msgSpan.className = "log-entry-msg " + (isError ? "err" : "ok");
      msgSpan.textContent = message;

      line.appendChild(tsSpan);
      line.appendChild(msgSpan);
      logOutput.appendChild(line);
      logOutput.scrollTop = logOutput.scrollHeight;
    }

    async function api(path, options = {}) {
      const resp = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      let data = {};
      try {
        data = await resp.json();
      } catch (_) {
        // ignore parse errors
      }
      if (!resp.ok) {
        const msg = data.error || resp.statusText || "Unknown error";
        throw new Error(msg);
      }
      return data;
    }

    // Create Session
    document.getElementById("btn-create-session").onclick = async () => {
      const userId = userIdInput.value.trim();
      if (!userId) {
        log("User ID is required to create a session", true);
        return;
      }
      try {
        const data = await api("/api/sessions", {
          method: "POST",
          body: JSON.stringify({ userId }),
        });

        const session = data.session || {};
        statusUserId.textContent = userId;
        statusSessionId.textContent = session.sessionId || "unknown";

        cartSessionInput.value = session.sessionId || "";
        orderUserIdInput.value = userId;
        orderSessionIdInput.value = session.sessionId || "";

        log(`Session created: ${JSON.stringify(session)}`);
      } catch (err) {
        log("Error creating session: " + err.message, true);
      }
    };

    // Save Cart
    document.getElementById("btn-save-cart").onclick = async () => {
      const sessionId = cartSessionInput.value.trim();
      if (!sessionId) {
        log("Session ID is required to save cart", true);
        return;
      }
      let items;
      try {
        items = JSON.parse(cartItemsInput.value);
      } catch (e) {
        log("Items JSON is invalid: " + e.message, true);
        return;
      }
      try {
        const data = await api("/api/cart", {
          method: "POST",
          body: JSON.stringify({ sessionId, items }),
        });
        log(`Cart saved: ${JSON.stringify(data.cart || {})}`);
      } catch (err) {
        log("Error saving cart: " + err.message, true);
      }
    };

    // Load Cart
    document.getElementById("btn-load-cart").onclick = async () => {
      const sessionId = cartSessionInput.value.trim();
      if (!sessionId) {
        log("Session ID is required to load cart", true);
        return;
      }
      try {
        const data = await api(`/api/cart/${encodeURIComponent(sessionId)}`);
        cartItemsInput.value = JSON.stringify(data.cart.items || [], null, 2);
        log(`Cart loaded: ${JSON.stringify(data.cart || {})}`);
      } catch (err) {
        log("Error loading cart: " + err.message, true);
      }
    };

    // Place Order
    document.getElementById("btn-place-order").onclick = async () => {
      const userId = orderUserIdInput.value.trim();
      const sessionId = orderSessionIdInput.value.trim();
      const total = parseFloat(orderTotalInput.value || "0");
      if (!userId || !sessionId) {
        log("User ID and Session ID are required to place order", true);
        return;
      }
      try {
        const data = await api("/api/orders", {
          method: "POST",
          body: JSON.stringify({ userId, sessionId, total }),
        });
        const order = data.order || {};
        statusOrderId.textContent = order.orderId || "unknown";
        orderIdInput.value = order.orderId || "";
        log(`Order created: ${JSON.stringify(order)}`);
      } catch (err) {
        log("Error placing order: " + err.message, true);
      }
    };

    // Get Order Details
    document.getElementById("btn-get-order").onclick = async () => {
      const orderId = orderIdInput.value.trim();
      if (!orderId) {
        log("Order ID is required to load order", true);
        return;
      }
      try {
        const data = await api(`/api/orders/${encodeURIComponent(orderId)}`);
        log(`Order loaded: ${JSON.stringify(data.order || {})}`);
      } catch (err) {
        log("Error loading order: " + err.message, true);
      }
    };

    // Initial log
    log("UI loaded. Use the panels above to create a session, save a cart, and place an order.");
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return Response(INDEX_HTML, mimetype="text/html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok", time=datetime.utcnow().isoformat() + "Z")


# --------------------------- Sessions --------------------------------------


@app.route("/api/sessions", methods=["POST"])
def create_session():
    """
    Body: { "userId": "1234" }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_id = data.get("userId")

        if not user_id:
            return jsonify(error="userId is required"), 400

        session_id = str(uuid.uuid4())
        item = {
            "sessionId": session_id,
            "userId": user_id,
            "createdAt": datetime.utcnow().isoformat() + "Z",
        }

        app.logger.info(f"Creating session: {item}")
        sessions_table.put_item(Item=item)

        return jsonify(message="Session created", session=item), 201

    except Exception as e:
        app.logger.exception("Error in /api/sessions")
        return jsonify(error=str(e)), 500


# --------------------------- Cart ------------------------------------------


@app.route("/api/cart", methods=["POST"])
def upsert_cart():
    """
    Body: { "sessionId": "...", "items": [ ... ] }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        session_id = data.get("sessionId")
        items = data.get("items", [])

        if not session_id:
            return jsonify(error="sessionId is required"), 400

        cart_item = {
            "sessionId": session_id,
            "items": items,
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }

        app.logger.info(f"Upserting cart: {cart_item}")
        cart_table.put_item(Item=cart_item)

        return jsonify(message="Cart saved", cart=cart_item), 200

    except Exception as e:
        app.logger.exception("Error in /api/cart (POST)")
        return jsonify(error=str(e)), 500


@app.route("/api/cart/<session_id>", methods=["GET"])
def get_cart(session_id):
    try:
        app.logger.info(f"Loading cart for session {session_id}")
        resp = cart_table.get_item(Key={"sessionId": session_id})
        item = resp.get("Item")

        if not item:
            return jsonify(error="Cart not found"), 404

        return jsonify(cart=item), 200

    except Exception as e:
        app.logger.exception("Error in /api/cart (GET)")
        return jsonify(error=str(e)), 500


# --------------------------- Orders ----------------------------------------


@app.route("/api/orders", methods=["POST"])
def create_order():
    """
    Body: { "userId": "...", "sessionId": "...", "total": 25.99 }
    - Loads cart items from DynamoDB.
    - Inserts order into RDS MySQL.
    - Writes summary to DynamoDB orders table.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_id = data.get("userId")
        session_id = data.get("sessionId")
        total = float(data.get("total", 0.0))

        if not user_id or not session_id:
            return jsonify(error="userId and sessionId are required"), 400

        # Load cart
        cart_resp = cart_table.get_item(Key={"sessionId": session_id})
        cart = cart_resp.get("Item", {})
        items = cart.get("items", [])

        order_id = str(uuid.uuid4())
        created_at = datetime.utcnow()

        # Insert into RDS
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO orders (order_id, user_id, session_id, total, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (order_id, user_id, session_id, total, created_at),
                )
            conn.commit()
        finally:
            conn.close()

        # Also store summary in DynamoDB orders table
        orders_ddb_table.put_item(Item={
            "orderId": order_id,
            "userId": user_id,
            "sessionId": session_id,
            "total": total,
            "items": items,
            "createdAt": created_at.isoformat() + "Z",
        })

        order_obj = {
            "orderId": order_id,
            "userId": user_id,
            "sessionId": session_id,
            "total": total,
            "items": items,
            "createdAt": created_at.isoformat() + "Z",
        }

        app.logger.info(f"Order created: {order_obj}")
        return jsonify(message="Order created", order=order_obj), 201

    except Exception as e:
        app.logger.exception("Error in /api/orders (POST)")
        return jsonify(error=str(e)), 500


@app.route("/api/orders/<order_id>", methods=["GET"])
def get_order(order_id):
    """
    Fetch order from RDS; if not there, try DynamoDB.
    """
    try:
        # First try RDS
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT order_id, user_id, session_id, total, created_at
                    FROM orders
                    WHERE order_id = %s
                    """,
                    (order_id,),
                )
                row = cursor.fetchone()
        finally:
            conn.close()

        if row:
            order = {
                "orderId": row["order_id"],
                "userId": row["user_id"],
                "sessionId": row["session_id"],
                "total": float(row["total"]),
                "createdAt": row["created_at"].isoformat() + "Z",
            }
            return jsonify(order=order), 200

        # Fallback to DynamoDB if not found in RDS
        resp = orders_ddb_table.get_item(Key={"orderId": order_id})
        item = resp.get("Item")
        if item:
            # DynamoDB item already in API-friendly shape
            return jsonify(order=item), 200

        return jsonify(error="Order not found"), 404

    except Exception as e:
        app.logger.exception("Error in /api/orders (GET)")
        return jsonify(error=str(e)), 500


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Local dev only; in ECS you will use gunicorn
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=True)

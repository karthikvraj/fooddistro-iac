import os
import uuid
from datetime import datetime

from flask import Flask, jsonify, request
import boto3
import pymysql

app = Flask(__name__)

# ---------- DynamoDB SETUP ----------

REGION = os.getenv("AWS_REGION", "us-east-1")
dynamodb = boto3.resource("dynamodb", region_name=REGION)

CART_TABLE_NAME = os.getenv("CART_TABLE_NAME", "fooddistro-cart-dev")
ORDERS_TABLE_NAME = os.getenv("ORDERS_TABLE_NAME", "fooddistro-orders-dev")
SESSIONS_TABLE_NAME = os.getenv("SESSIONS_TABLE_NAME", "fooddistro-sessions-dev")

cart_table = dynamodb.Table(CART_TABLE_NAME)
orders_ddb_table = dynamodb.Table(ORDERS_TABLE_NAME)
sessions_table = dynamodb.Table(SESSIONS_TABLE_NAME)

# ---------- RDS SETUP ----------

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")


def get_db_connection():
    if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        raise RuntimeError("DB connection env vars are not set")
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
    )


# ---------- BASIC ROUTES ----------

@app.route("/")
def index():
    return """
    <html>
      <head><title>FoodDistro Backend</title></head>
      <body>
        <h1>FoodDistro Backend – Live</h1>
        <p>Python Flask app running on ECS Fargate behind an ALB.</p>
        <p>Sessions & cart data are stored in DynamoDB; orders are persisted in RDS MySQL (and cached in DynamoDB).</p>
      </body>
    </html>
    """, 200


@app.route("/health")
def health():
    return jsonify(status="ok"), 200


# ---------- SESSIONS ----------

@app.route("/api/sessions", methods=["POST"])
def create_session():
    """
    Body: { "userId": "user-123" }
    Creates a session row in fooddistro-sessions-dev.
    """
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("userId")
    if not user_id:
        return jsonify(error="userId is required"), 400

    session_id = str(uuid.uuid4())
    item = {
        "userId": user_id,
        "sessionId": session_id,
        "createdAt": datetime.utcnow().isoformat() + "Z",
    }
    sessions_table.put_item(Item=item)
    return jsonify(message="Session created", session=item), 201


# ---------- CART ----------

@app.route("/api/cart", methods=["POST"])
def upsert_cart():
    """
    Body: { "sessionId": "...", "items": [ {"sku":"...", "qty":2}, ... ] }
    Upserts the cart in fooddistro-cart-dev.
    """
    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get("sessionId")
    items = data.get("items", [])

    if not session_id:
        return jsonify(error="sessionId is required"), 400

    item = {
        "sessionId": session_id,
        "items": items,
        "updatedAt": datetime.utcnow().isoformat() + "Z",
    }
    cart_table.put_item(Item=item)
    return jsonify(message="Cart saved", cart=item), 201


@app.route("/api/cart/<session_id>", methods=["GET"])
def get_cart(session_id):
    resp = cart_table.get_item(Key={"sessionId": session_id})
    item = resp.get("Item")
    if not item:
        return jsonify(error="Cart not found", sessionId=session_id), 404
    return jsonify(cart=item), 200


# ---------- ORDERS ----------

@app.route("/api/orders", methods=["POST"])
def create_order():
    """
    Body: { "userId": "...", "sessionId": "...", "total": 25.99 }
    - Reads cart from DynamoDB
    - Writes the order record to RDS (primary)
    - Also writes a copy into DynamoDB orders table (cache/log)
    """
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("userId")
    session_id = data.get("sessionId")
    total = data.get("total", 0.0)

    if not user_id or not session_id:
        return jsonify(error="userId and sessionId are required"), 400

    # Get cart items for this session (from DynamoDB)
    cart_resp = cart_table.get_item(Key={"sessionId": session_id})
    cart_item = cart_resp.get("Item", {})
    items = cart_item.get("items", [])

    order_id = str(uuid.uuid4())
    created_at = datetime.utcnow()

    # ---- Write to RDS ----
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO orders (order_id, user_id, session_id, total, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (order_id, user_id, session_id, float(total), created_at))
        conn.commit()
    finally:
        conn.close()

    # ---- Also write to DynamoDB (optional cache/log) ----
    orders_ddb_table.put_item(Item={
        "orderId": order_id,
        "createdAt": created_at.isoformat() + "Z",
        "userId": user_id,
        "sessionId": session_id,
        "total": float(total),
        "items": items,
    })

    return jsonify(
        message="Order created",
        orderId=order_id,
        userId=user_id,
        sessionId=session_id,
        total=float(total),
        items=items,
    ), 201


@app.route("/api/orders/<order_id>", methods=["GET"])
def get_order(order_id):
    """
    Try DynamoDB cache first; if not found, fall back to RDS.
    """
    # Try DynamoDB
    ddb_resp = orders_ddb_table.scan(
        FilterExpression="orderId = :oid",
        ExpressionAttributeValues={":oid": order_id},
        Limit=1,
    )
    items = ddb_resp.get("Items", [])
    if items:
        return jsonify(source="dynamodb", order=items[0]), 200

    # Fallback to RDS
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
            row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify(error="Order not found", orderId=order_id), 404

    row["created_at"] = row["created_at"].isoformat()
    return jsonify(source="rds", order=row), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
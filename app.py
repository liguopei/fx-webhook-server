from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# ==========================================
# OANDA CONFIGURATION
# ==========================================
OANDA_API_KEY    = os.environ.get("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.environ.get("OANDA_ACCOUNT_ID")
OANDA_BASE_URL   = os.environ.get("OANDA_BASE_URL", "https://api-fxpractice.oanda.com")
WEBHOOK_SECRET   = os.environ.get("WEBHOOK_SECRET", "")

def get_headers():
    return {
        "Authorization": f"Bearer {OANDA_API_KEY}",
        "Content-Type": "application/json"
    }

# ==========================================
# CHECK FOR ACTIVE TRADE
# ==========================================
def has_open_trade(symbol):
    """Check if there is already an open trade for this symbol"""
    try:
        url = f"{OANDA_BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/trades"
        response = requests.get(url, headers=get_headers())
        trades = response.json().get("trades", [])
        for trade in trades:
            if trade["instrument"] == symbol and trade["state"] == "OPEN":
                print(f"[SKIP] Active trade already exists for {symbol}")
                return True
        return False
    except Exception as e:
        print(f"[ERROR] Failed to check open trades: {e}")
        return False

# ==========================================
# PLACE ORDER
# ==========================================
def place_order(symbol, units, stop_price=None, tp_price=None):
    url = f"{OANDA_BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/orders"

    order = {
        "type": "MARKET",
        "instrument": symbol,
        "units": str(units),
    }

    if stop_price:
        order["stopLossOnFill"] = {"price": str(round(float(stop_price), 3))}

    if tp_price:
        order["takeProfitOnFill"] = {"price": str(round(float(tp_price), 3))}

    payload = {"order": order}
    response = requests.post(url, json=payload, headers=get_headers())
    return response.json(), response.status_code

# ==========================================
# CLOSE ALL POSITIONS
# ==========================================
def close_all_positions(symbol):
    url = f"{OANDA_BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/positions/{symbol}"
    response = requests.get(url, headers=get_headers())
    position = response.json()

    results = []

    long_units = position.get("position", {}).get("long", {}).get("units", "0")
    if float(long_units) > 0:
        close_url = f"{OANDA_BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/positions/{symbol}/close"
        r = requests.put(close_url, json={"longUnits": "ALL"}, headers=get_headers())
        results.append(r.json())

    short_units = position.get("position", {}).get("short", {}).get("units", "0")
    if float(short_units) < 0:
        close_url = f"{OANDA_BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/positions/{symbol}/close"
        r = requests.put(close_url, json={"shortUnits": "ALL"}, headers=get_headers())
        results.append(r.json())

    return results

# ==========================================
# WEBHOOK ENDPOINT
# ==========================================
@app.route("/webhook", methods=["POST"])
def webhook():
    secret = request.args.get("secret", "")
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    action = data.get("action")
    symbol = data.get("symbol")
    qty    = data.get("qty", "1000")
    stop   = data.get("stop")
    tp     = data.get("tp")

    if not action or not symbol:
        return jsonify({"error": "Missing action or symbol"}), 400

    # BUY
    if action == "buy":
        if has_open_trade(symbol):
            return jsonify({"status": "skipped", "reason": "active trade exists", "symbol": symbol}), 200
        units = int(float(qty))
        result, status = place_order(symbol, units, stop, tp)
        return jsonify({"action": "buy", "symbol": symbol, "result": result}), status

    # SELL
    elif action == "sell":
        if has_open_trade(symbol):
            return jsonify({"status": "skipped", "reason": "active trade exists", "symbol": symbol}), 200
        units = -int(float(qty))
        result, status = place_order(symbol, units, stop, tp)
        return jsonify({"action": "sell", "symbol": symbol, "result": result}), status

    # CLOSE ALL
    elif action == "close_all":
        results = close_all_positions(symbol)
        return jsonify({"action": "close_all", "symbol": symbol, "results": results}), 200

    else:
        return jsonify({"error": f"Unknown action: {action}"}), 400

# ==========================================
# HEALTH CHECK
# ==========================================
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

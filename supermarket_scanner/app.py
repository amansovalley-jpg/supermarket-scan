"""Supermarket scanner - Flask backend. Run: python app.py"""
import sqlite3

from flask import Flask, Response, jsonify, render_template, request

import database as db
from scanner import decode_image_bytes, scanner

app = Flask(__name__)
CURRENCY = "₦"


@app.context_processor
def inject():
    return {"currency": CURRENCY}


# ---------- pages ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/pos")
def pos():
    return render_template("pos.html")


@app.route("/inventory")
def inventory():
    return render_template("inventory.html")


# ---------- scanner ----------
@app.route("/video_feed")
def video_feed():
    scanner.start()
    return Response(scanner.mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/scanner/<action>", methods=["POST"])
def scanner_toggle(action):
    scanner.start() if action == "start" else scanner.stop()
    return jsonify(running=scanner.running, error=scanner.error)


@app.route("/api/scanner/status")
def scanner_status():
    return jsonify(running=scanner.running, error=scanner.error)


@app.route("/api/scan/poll")
def scan_poll():
    since = request.args.get("since", type=int)
    last, events = scanner.events_since(since)
    for e in events:
        e["product"] = db.get_product_by_barcode(e["barcode"])
    return jsonify(last_id=last, events=events)


@app.route("/api/scan/manual", methods=["POST"])
def scan_manual():
    code = (request.json or {}).get("barcode", "").strip()
    if code:
        scanner.push(code, "MANUAL")
    return jsonify(ok=bool(code))


@app.route("/api/scan/image", methods=["POST"])
def scan_image():
    """Fallback: decode a barcode from an uploaded photo."""
    f = request.files.get("image")
    codes = decode_image_bytes(f.read()) if f else []
    for c in codes:
        scanner.push(c, "IMAGE")
    return jsonify(codes=codes)


# ---------- products ----------
@app.route("/api/products", methods=["GET", "POST"])
def products():
    if request.method == "GET":
        return jsonify(db.list_products(request.args.get("q", "")))
    try:
        pid = db.add_product(request.json)
        return jsonify(id=pid), 201
    except sqlite3.IntegrityError:
        return jsonify(error="A product with this barcode already exists"), 409
    except (KeyError, ValueError):
        return jsonify(error="Name, barcode and a valid price are required"), 400


@app.route("/api/products/<int:pid>", methods=["PUT", "DELETE"])
def product(pid):
    try:
        if request.method == "DELETE":
            db.delete_product(pid)
        else:
            db.update_product(pid, request.json)
        return jsonify(ok=True)
    except sqlite3.IntegrityError:
        return jsonify(error="Barcode already used by another product"), 409
    except (KeyError, ValueError):
        return jsonify(error="Invalid product data"), 400


@app.route("/api/products/barcode/<barcode>")
def product_by_barcode(barcode):
    p = db.get_product_by_barcode(barcode)
    return (jsonify(p), 200) if p else (jsonify(error="Not found"), 404)


# ---------- sales ----------
@app.route("/api/checkout", methods=["POST"])
def checkout():
    try:
        return jsonify(db.create_sale((request.json or {}).get("items", [])))
    except ValueError as e:
        return jsonify(error=str(e)), 400


@app.route("/api/stats")
def stats():
    return jsonify(db.get_stats())


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

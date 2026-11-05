"""SQLite setup and helper functions."""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "products.db")

SAMPLE = [
    ("5449000000996", "Coca-Cola 500ml", "Drinks", 300, 48, 10),
    ("6001068012343", "Peak Milk Tin 400g", "Dairy", 2200, 20, 5),
    ("5000112637922", "Indomie Chicken Noodles", "Pantry", 250, 120, 30),
    ("8901030865275", "Dettol Soap 100g", "Household", 650, 35, 10),
    ("4006381333931", "Stabilo Boss Highlighter", "Stationery", 1200, 4, 5),
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            price REAL NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0,
            min_stock INTEGER NOT NULL DEFAULT 5,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total REAL NOT NULL,
            items_count INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
            product_id INTEGER,
            barcode TEXT, name TEXT,
            qty INTEGER NOT NULL, price REAL NOT NULL
        );
        """)
        if c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO products (barcode,name,category,price,stock,min_stock) VALUES (?,?,?,?,?,?)",
                SAMPLE)


def rows(sql, args=()):
    with get_conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql, args=()):
    r = rows(sql, args)
    return r[0] if r else None


def get_product_by_barcode(barcode):
    return one("SELECT * FROM products WHERE barcode = ?", (barcode,))


def list_products(search=""):
    like = f"%{search}%"
    return rows("SELECT * FROM products WHERE name LIKE ? OR barcode LIKE ? OR category LIKE ? ORDER BY name",
                (like, like, like))


def add_product(d):
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO products (barcode,name,category,price,stock,min_stock) VALUES (?,?,?,?,?,?)",
            (d["barcode"].strip(), d["name"].strip(), d.get("category", "General"),
             float(d["price"]), int(d.get("stock", 0)), int(d.get("min_stock", 5))))
        return cur.lastrowid


def update_product(pid, d):
    with get_conn() as c:
        c.execute(
            "UPDATE products SET barcode=?, name=?, category=?, price=?, stock=?, min_stock=? WHERE id=?",
            (d["barcode"].strip(), d["name"].strip(), d.get("category", "General"),
             float(d["price"]), int(d.get("stock", 0)), int(d.get("min_stock", 5)), pid))


def delete_product(pid):
    with get_conn() as c:
        c.execute("DELETE FROM products WHERE id = ?", (pid,))


def create_sale(items):
    """items: [{barcode, qty}]. All-or-nothing; raises ValueError on problems."""
    if not items:
        raise ValueError("Cart is empty")
    with get_conn() as c:
        lines, total = [], 0.0
        for it in items:
            qty = int(it["qty"])
            p = c.execute("SELECT * FROM products WHERE barcode = ?", (it["barcode"],)).fetchone()
            if not p:
                raise ValueError(f"Unknown barcode {it['barcode']}")
            if qty < 1 or p["stock"] < qty:
                raise ValueError(f"Not enough stock for {p['name']} (have {p['stock']})")
            lines.append((p, qty))
            total += p["price"] * qty
        cur = c.execute("INSERT INTO sales (total, items_count) VALUES (?,?)",
                        (total, sum(q for _, q in lines)))
        sale_id = cur.lastrowid
        for p, qty in lines:
            c.execute("INSERT INTO sale_items (sale_id,product_id,barcode,name,qty,price) VALUES (?,?,?,?,?,?)",
                      (sale_id, p["id"], p["barcode"], p["name"], qty, p["price"]))
            c.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (qty, p["id"]))
        return {"sale_id": sale_id, "total": total}


def get_stats():
    today = one("""SELECT COALESCE(SUM(total),0) AS revenue, COUNT(*) AS sales,
                   COALESCE(SUM(items_count),0) AS items
                   FROM sales WHERE date(created_at) = date('now','localtime')""")
    inv = one("SELECT COUNT(*) AS products, COALESCE(SUM(price*stock),0) AS value FROM products")
    low = rows("SELECT * FROM products WHERE stock <= min_stock ORDER BY stock LIMIT 10")
    recent = rows("SELECT * FROM sales ORDER BY id DESC LIMIT 8")
    top = rows("""SELECT name, SUM(qty) AS sold FROM sale_items
                  GROUP BY barcode ORDER BY sold DESC LIMIT 5""")
    return {"today": today, "inventory": inv, "low_stock": low, "recent_sales": recent, "top": top}

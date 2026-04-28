from flask import Flask, render_template, request, redirect, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import pandas as pd
import io
import urllib.parse
from flask import render_template

app = Flask(__name__)
app.secret_key = "clave_secreta"


# 🔌 CONEXIÓN SQLITE
def conectar():
    try:
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print("ERROR:", e)
        return None


# 🧱 CREAR TABLAS
def crear_tablas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT,
        contraseña TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        stock_inicial INTEGER DEFAULT 0,
        stock_actual INTEGER,
        precio REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER,
        cantidad INTEGER,
        total REAL,
        fecha TEXT,
        metodo_pago_id INTEGER,
        promocion_id INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descripcion TEXT,
        monto REAL,
        fecha TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historial (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT,
        descripcion TEXT,
        producto_id INTEGER,
        cantidad INTEGER,
        monto REAL,
        fecha TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


# 👤 USUARIO INICIAL
def crear_usuario():
    conn = conectar()
    cursor = conn.cursor()

    usuarios = ["Micaela", "Magali", "Francisco"]
    password = generate_password_hash("Familia26@")

    for u in usuarios:
        cursor.execute("SELECT * FROM usuarios WHERE usuario = ?", (u,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO usuarios (usuario, contraseña) VALUES (?, ?)",
                (u, password)
            )

    conn.commit()
    conn.close()


# 🔐 LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
        user = cursor.fetchone()

        if user and check_password_hash(user["contraseña"], password):
            session["usuario"] = user["usuario"]
            return redirect("/")
        else:
            return "❌ Datos incorrectos"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
def home():
    carrito = session.get("carrito", [])

    cantidad_carrito = sum(item["cantidad"] for item in carrito)

    return render_template("home.html", cantidad_carrito=cantidad_carrito)

# ➕ AGREGAR AL CARRITO
@app.route("/agregar", methods=["POST"])
def agregar():
    nombre = request.form.get("producto")
    precio = int(request.form.get("precio"))

    if "carrito" not in session:
        session["carrito"] = []

    carrito = session["carrito"]

    # 🔥 LIMPIA formato viejo automáticamente
    if carrito and isinstance(carrito[0], str):
        session["carrito"] = []
        carrito = []

    for item in carrito:
        if item["nombre"] == nombre:
            item["cantidad"] += 1
            session.modified = True
            return redirect("/")

    carrito.append({
        "nombre": nombre,
        "precio": precio,
        "cantidad": 1
    })

    session.modified = True
    return redirect("/")


# 🛒 VER CARRITO
@app.route("/carrito")
def carrito():
    carrito = session.get("carrito", [])

    total = sum(item["precio"] * item["cantidad"] for item in carrito)

    return render_template("carrito.html", carrito=carrito, total=total)


@app.route("/sumar/<nombre>")
def sumar(nombre):
    for item in session["carrito"]:
        if item["nombre"] == nombre:
            item["cantidad"] += 1
            break

    session.modified = True
    return redirect("/carrito")


@app.route("/restar/<nombre>")
def restar(nombre):
    for item in session["carrito"]:
        if item["nombre"] == nombre:
            item["cantidad"] -= 1

            if item["cantidad"] <= 0:
                session["carrito"].remove(item)

            break

    session.modified = True
    return redirect("/carrito")

# ❌ VACIAR CARRITO
@app.route("/vaciar")
def vaciar():
    session.pop("carrito", None)
    return redirect("/carrito")


# 📲 ENVIAR A WHATSAPP
@app.route("/enviar")
def enviar():
    carrito = session.get("carrito", [])

    mensaje = "Hola, quiero pedir:\n\n"
    total = 0

    for item in carrito:
        subtotal = item["precio"] * item["cantidad"]
        total += subtotal

        mensaje += f"{item['nombre']} x{item['cantidad']} = ${subtotal}\n"

    mensaje += f"\nTOTAL: ${total}"

    mensaje_codificado = urllib.parse.quote(mensaje)

    return redirect(f"https://wa.me/5493564593629?text={mensaje_codificado}")

# 🏠 INICIO
@app.route("/dashboard")
def dashboard():
    if "usuario" not in session:
        return redirect("/login")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT IFNULL(SUM(total),0) FROM ventas")
    ventas_total = cursor.fetchone()[0]

    cursor.execute("SELECT IFNULL(SUM(monto),0) FROM gastos")
    gastos_total = cursor.fetchone()[0]

    ganancia = ventas_total - gastos_total

    cursor.execute("SELECT * FROM productos")
    productos = cursor.fetchall()

    cursor.execute("SELECT * FROM ventas ORDER BY fecha DESC LIMIT 5")
    ventas_ultimas = cursor.fetchall()

    cursor.execute("SELECT * FROM ventas ORDER BY fecha DESC")
    ventas_todas = cursor.fetchall()

    cursor.execute("SELECT * FROM gastos ORDER BY fecha DESC LIMIT 5")
    gastos_ultimos = cursor.fetchall()

    cursor.execute("SELECT * FROM gastos ORDER BY fecha DESC")
    gastos_todos = cursor.fetchall()

    conn.close()

    return render_template(
        "ventas.html",
        productos=productos,
        ventas_ultimas=ventas_ultimas,
        ventas_todas=ventas_todas,
        gastos_ultimos=gastos_ultimos,
        gastos_todos=gastos_todos,
        ventas_total=ventas_total,
        gastos_total=gastos_total,
        ganancia=ganancia
    )


# ➕ PRODUCTO
@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    nombre = request.form["nombre"]
    precio = float(request.form["precio"])
    stock = int(request.form["stock"])

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO productos (nombre, precio, stock_actual)
        VALUES (?, ?, ?)
    """, (nombre, precio, stock))

    conn.commit()
    conn.close()

    return redirect("/")


# 💰 VENTA
@app.route("/agregar_venta", methods=["POST"])
def agregar_venta():
    producto_id = int(request.form["producto_id"])
    cantidad = int(request.form["cantidad"])

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT precio, stock_actual FROM productos WHERE id = ?", (producto_id,))
    producto = cursor.fetchone()

    if not producto:
        return "Producto no encontrado"

    precio, stock = producto

    if cantidad > stock:
        return "Sin stock"

    total = precio * cantidad

    cursor.execute("""
        INSERT INTO ventas (fecha, producto_id, cantidad, total)
        VALUES (datetime('now'), ?, ?, ?)
    """, (producto_id, cantidad, total))

    cursor.execute("""
        UPDATE productos
        SET stock_actual = stock_actual - ?
        WHERE id = ?
    """, (cantidad, producto_id))

    conn.commit()
    conn.close()

    return redirect("/")


# ❌ ELIMINAR VENTA
@app.route("/eliminar_venta/<int:id>", methods=["POST"])
def eliminar_venta(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT producto_id, cantidad, total FROM ventas WHERE id = ?", (id,))
    venta = cursor.fetchone()

    if venta:
        producto_id, cantidad, total = venta

        cursor.execute("""
            INSERT INTO historial (tipo, producto_id, cantidad, monto)
            VALUES ('VENTA ELIMINADA', ?, ?, ?)
        """, (producto_id, cantidad, total))

        cursor.execute("DELETE FROM ventas WHERE id = ?", (id,))

    conn.commit()
    conn.close()

    return redirect("/")


# 💸 GASTO
@app.route("/agregar_gasto", methods=["POST"])
def agregar_gasto():
    descripcion = request.form["descripcion"]
    monto = float(request.form["monto"])

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO gastos (descripcion, monto, fecha)
        VALUES (?, ?, datetime('now'))
    """, (descripcion, monto))

    conn.commit()
    conn.close()

    return redirect("/")


# 📊 HISTORIAL
@app.route("/historial")
def historial():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM historial ORDER BY fecha DESC")
    data = cursor.fetchall()

    conn.close()

    return render_template("historial.html", historial=data)


# 📁 EXCEL SIMPLE (estable)
@app.route("/excel")
def excel():
    conn = conectar()

    ventas = pd.read_sql("SELECT * FROM ventas", conn)
    gastos = pd.read_sql("SELECT * FROM gastos", conn)

    conn.close()

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        ventas.to_excel(writer, sheet_name="Ventas", index=False)
        gastos.to_excel(writer, sheet_name="Gastos", index=False)

    output.seek(0)

    return send_file(output, download_name="reporte.xlsx", as_attachment=True)


# 🚀 INIT
crear_tablas()
crear_usuario()



if __name__ == "__main__":
    app.run(debug=True)
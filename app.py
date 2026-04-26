from flask import Flask, render_template, request, redirect, session
import pyodbc
from werkzeug.security import generate_password_hash, check_password_hash

import pandas as pd
import io
from flask import send_file

app = Flask(__name__)
app.secret_key = "clave_secreta"


# 🔌 CONEXIÓN SQL SERVER
def conectar():
    try:
        conn = pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=NOTEBOOKFLOR\\SQLEXPRESS;"
            "DATABASE=hueveria_losprimos;"
            "Trusted_Connection=yes;"
        )
        return conn
    except Exception as e:
        print("ERROR:", e)
        return None


# 🔐 LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]

        conn = conectar()
        if not conn:
            return "⚠️ Error de conexión"

        cursor = conn.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
        user = cursor.fetchone()

        if user and check_password_hash(user[2], password):
            session["usuario"] = user[1]
            session["usuario_id"] = user[0]
            return redirect("/")
        else:
            return "❌ Datos incorrectos"

    return render_template("login.html")


# 🚪 LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# 🏠 INICIO
@app.route("/")
def inicio():
    if "usuario" not in session:
        return redirect("/login")

    conn = conectar()
    cursor = conn.cursor()

    # 💰 TOTAL VENTAS
    cursor.execute("SELECT ISNULL(SUM(total), 0) FROM ventas")
    ventas_total = cursor.fetchone()[0]

    # 💸 TOTAL GASTOS
    cursor.execute("SELECT ISNULL(SUM(monto), 0) FROM gastos")
    gastos_total = cursor.fetchone()[0]

    # 📈 GANANCIA
    ganancia = ventas_total - gastos_total

    # PRODUCTOS
    cursor.execute("SELECT id, nombre, stock_inicial, stock_actual, precio FROM productos")
    productos = cursor.fetchall()

    # VENTAS
    cursor.execute("""
        SELECT TOP 5 id, fecha, total
        FROM ventas
        ORDER BY fecha DESC
    """)
    ventas = cursor.fetchall()

    # VENTAS ÚLTIMAS
    cursor.execute("""
    SELECT TOP 5 v.id, v.fecha, p.nombre, v.cantidad, v.total, mp.nombre
    FROM ventas v
    JOIN productos p ON v.producto_id = p.id
    LEFT JOIN metodos_pago mp ON v.metodo_pago_id = mp.id
    ORDER BY v.fecha DESC
""")
    ventas_ultimas = cursor.fetchall()

# TODAS LAS VENTAS
    cursor.execute("""
    SELECT v.id, v.fecha, p.nombre, v.cantidad, v.total, mp.nombre
    FROM ventas v
    JOIN productos p ON v.producto_id = p.id
    LEFT JOIN metodos_pago mp ON v.metodo_pago_id = mp.id
    ORDER BY v.fecha DESC
""")
    ventas_todas = cursor.fetchall()

    # METODOS DE PAGO
    cursor.execute("SELECT id, nombre FROM metodos_pago")
    metodos_pago = cursor.fetchall()

    # 🔥 PROMOCIONES (ESTO ES LO NUEVO)
    cursor.execute("SELECT id, descripcion, precio FROM promociones")
    promociones = cursor.fetchall()


    # 💸 GASTOS ÚLTIMOS
    cursor.execute("""
    SELECT TOP 5 id, descripcion, monto, fecha
    FROM gastos
    ORDER BY fecha DESC
""")
    gastos_ultimos = cursor.fetchall()

    # 💸 TODOS LOS GASTOS
    cursor.execute("""
    SELECT id, descripcion, monto, fecha
    FROM gastos
    ORDER BY fecha DESC
""")
    gastos_todos = cursor.fetchall()

        

    return render_template(
    "ventas.html",
    productos=productos,
    metodos_pago=metodos_pago,
    promociones=promociones,
    ventas_ultimas=ventas_ultimas,
    ventas_todas=ventas_todas,
    gastos_ultimos=gastos_ultimos,   # 👈 ESTO FALTABA
    gastos_todos=gastos_todos,       # 👈 Y ESTO
    ventas_total=ventas_total,
    gastos_total=gastos_total,
    ganancia=ganancia
)

# ➕ AGREGAR PRODUCTO
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


# 💰 AGREGAR VENTA
@app.route("/agregar_venta", methods=["POST"])
def agregar_venta():
    try:
        producto_id = int(request.form["producto_id"])
        cantidad = int(request.form["cantidad"])

        promocion_id = request.form.get("promocion_id")
        metodo_pago_id = request.form.get("metodo_pago_id")

        # ✅ LIMPIAR DATOS
        promocion_id = int(promocion_id) if promocion_id else None
        metodo_pago_id = int(metodo_pago_id) if metodo_pago_id else None

        conn = conectar()
        cursor = conn.cursor()

        # 🔍 PRODUCTO
        cursor.execute("SELECT precio, stock_actual FROM productos WHERE id = ?", (producto_id,))
        producto = cursor.fetchone()

        if not producto:
            return "Producto no encontrado"

        precio, stock = producto

        # 🔥 PROMOCIÓN
        if promocion_id:
            cursor.execute("SELECT precio FROM promociones WHERE id = ?", (promocion_id,))
            promo = cursor.fetchone()

            if promo:
                precio = promo[0]
            else:
                return "❌ Promoción inválida"

        # 🚫 STOCK
        if cantidad > stock:
            return "❌ Sin stock"

        total = precio * cantidad

        # 💾 INSERT
        cursor.execute("""
            INSERT INTO ventas (fecha, producto_id, cantidad, total, metodo_pago_id, promocion_id)
            VALUES (GETDATE(), ?, ?, ?, ?, ?)
        """, (producto_id, cantidad, total, metodo_pago_id, promocion_id))

        # 📦 ACTUALIZAR STOCK
        cursor.execute("""
            UPDATE productos
            SET stock_actual = stock_actual - ?
            WHERE id = ?
        """, (cantidad, producto_id))

        conn.commit()
        conn.close()

        return redirect("/")

    except Exception as e:
     print("🔥 ERROR REAL:", e)
    return f"<h1>ERROR: {e}</h1>"

@app.route("/eliminar_venta/<int:id>", methods=["POST"])
def eliminar_venta(id):
    conn = conectar()
    cursor = conn.cursor()

    # 🔍 BUSCAR DATOS
    cursor.execute("""
        SELECT producto_id, cantidad, total
        FROM ventas
        WHERE id = ?
    """, (id,))
    venta = cursor.fetchone()

    if not venta:
        return "Venta no encontrada"

    producto_id, cantidad, total = venta

    # 🔍 NOMBRE PRODUCTO
    cursor.execute("SELECT nombre FROM productos WHERE id = ?", (producto_id,))
    producto = cursor.fetchone()
    nombre_producto = producto[0]

    # 🔄 DEVOLVER STOCK
    cursor.execute("""
        UPDATE productos
        SET stock_actual = stock_actual + ?
        WHERE id = ?
    """, (cantidad, producto_id))

    # 📝 HISTORIAL (CORRECTO)
    cursor.execute("""
        INSERT INTO historial (tipo, descripcion, producto_id, cantidad, monto)
        VALUES ('VENTA ELIMINADA', ?, ?, ?, ?)
    """, (nombre_producto, producto_id, cantidad, total))

    # ❌ ELIMINAR
    cursor.execute("DELETE FROM ventas WHERE id = ?", (id,))

    conn.commit()
    conn.close()

    return redirect("/")


    
@app.route("/editar_precio/<int:id>", methods=["POST"])
def editar_precio(id):
    try:
        nuevo_precio = float(request.form["precio"])

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE productos
            SET precio = ?
            WHERE id = ?
        """, (nuevo_precio, id))

        conn.commit()
        conn.close()

        return redirect("/")

    except Exception as e:
        print("ERROR EDITAR PRECIO:", e)
        return "❌ Error al actualizar precio"
    

@app.route("/eliminar_producto/<int:id>")
def eliminar_producto(id):
    conn = conectar()
    cursor = conn.cursor()

    # 🔍 BUSCAR PRODUCTO
    cursor.execute("SELECT nombre FROM productos WHERE id = ?", (id,))
    producto = cursor.fetchone()

    if producto:
        nombre = producto[0]

        # 📝 HISTORIAL
        cursor.execute("""
            INSERT INTO historial (tipo, descripcion)
            VALUES ('PRODUCTO ELIMINADO', ?)
        """, (nombre,))

    # ❌ BORRAR
    cursor.execute("DELETE FROM productos WHERE id = ?", (id,))

    conn.commit()
    conn.close()

    return redirect("/")
    
@app.route("/editar_producto", methods=["POST"])
def editar_producto():
    try:
        producto_id = int(request.form["producto_id"])
        precio = float(request.form["precio"])
        stock_inicial = int(request.form["stock_inicial"])

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE productos
            SET precio = ?, stock_inicial = ?
            WHERE id = ?
        """, (precio, stock_inicial, producto_id))

        conn.commit()
        conn.close()

        return redirect("/")

    except Exception as e:
        print("ERROR EDITAR PRODUCTO:", e)
        return f"❌ Error: {e}"    

@app.route("/agregar_gasto", methods=["POST"])
def agregar_gasto():
    try:
        descripcion = request.form["descripcion"]
        monto = float(request.form["monto"])

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO gastos (descripcion, monto, fecha)
            VALUES (?, ?, GETDATE())
        """, (descripcion, monto))

        conn.commit()
        conn.close()

        return redirect("/")

    except Exception as e:
        print("ERROR AGREGAR GASTO:", e)
        return f"❌ Error: {e}"
    

@app.route("/eliminar_gasto/<int:id>", methods=["POST"])
def eliminar_gasto(id):
    conn = conectar()
    cursor = conn.cursor()

    # 🔍 BUSCAR GASTO
    cursor.execute("SELECT descripcion, monto FROM gastos WHERE id = ?", (id,))
    gasto = cursor.fetchone()

    if gasto:
        descripcion, monto = gasto

        # 📝 HISTORIAL
        cursor.execute("""
    INSERT INTO historial (tipo, descripcion, monto)
    VALUES ('GASTO ELIMINADO', ?, ?)
""", (descripcion, monto))

    # ❌ BORRAR
    cursor.execute("DELETE FROM gastos WHERE id = ?", (id,))

    conn.commit()
    conn.close()

    return redirect("/")
    
@app.route("/historial")
def ver_historial():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, tipo, descripcion, fecha
    FROM historial
    ORDER BY fecha DESC
""")

    historial = cursor.fetchall()
    conn.close()

    return render_template("historial.html", historial=historial) 

@app.route("/eliminar_historial/<int:id>", methods=["POST"])
def eliminar_historial(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM historial WHERE id = ?", (id,))

    conn.commit()
    conn.close()

    return redirect("/historial")

@app.route("/restaurar_historial/<int:id>", methods=["POST"])
def restaurar_historial(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT tipo, producto_id, cantidad, monto
        FROM historial
        WHERE id = ?
    """, (id,))
    h = cursor.fetchone()

    if not h:
        return "Registro no encontrado"

    tipo, producto_id, cantidad, monto = h

    # 🔁 RESTAURAR VENTA COMPLETA
    if tipo == "VENTA ELIMINADA":
        cursor.execute("""
            INSERT INTO ventas (fecha, producto_id, cantidad, total)
            VALUES (GETDATE(), ?, ?, ?)
        """, (producto_id, cantidad, monto))

        cursor.execute("""
            UPDATE productos
            SET stock_actual = stock_actual - ?
            WHERE id = ?
        """, (cantidad, producto_id))

    # 🔁 RESTAURAR GASTO
    elif tipo == "GASTO ELIMINADO":
        cursor.execute("""
            INSERT INTO gastos (descripcion, monto, fecha)
            VALUES ('Restaurado', ?, GETDATE())
        """, (monto,))

    conn.commit()
    conn.close()

    return redirect("/historial")

@app.route("/ingresar_stock", methods=["POST"])
def ingresar_stock():
    try:
        producto_id = int(request.form["producto_id"])
        cantidad = int(request.form["cantidad"])

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE productos
            SET stock_actual = stock_actual + ?
            WHERE id = ?
        """, (cantidad, producto_id))

        conn.commit()
        conn.close()

        return redirect("/")

    except Exception as e:
        print("ERROR STOCK:", e)
        return "Error al ingresar stock"
    
@app.route("/excel")
def exportar_excel():
    import pandas as pd
    import io
    from flask import send_file
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import BarChart, Reference

    conn = conectar()

    ventas = pd.read_sql("""
        SELECT v.fecha,
               p.nombre AS Producto,
               v.cantidad AS Cantidad,
               v.total AS Total
        FROM ventas v
        JOIN productos p ON v.producto_id = p.id
    """, conn)

    gastos = pd.read_sql("""
        SELECT fecha,
               descripcion AS Descripción,
               monto AS Monto
        FROM gastos
    """, conn)

    ranking = pd.read_sql("""
        SELECT p.nombre AS Producto,
               SUM(v.cantidad) AS Cantidad
        FROM ventas v
        JOIN productos p ON v.producto_id = p.id
        GROUP BY p.nombre
        ORDER BY Cantidad DESC
    """, conn)

    conn.close()

    # 🔥 FORMATO FECHA
    ventas["Fecha"] = pd.to_datetime(ventas["fecha"]).dt.strftime("%d/%m/%Y %H:%M")
    ventas = ventas.drop(columns=["fecha"])
    ventas = ventas[["Fecha", "Producto", "Cantidad", "Total"]]

    gastos["Fecha"] = pd.to_datetime(gastos["fecha"]).dt.strftime("%d/%m/%Y %H:%M")
    gastos = gastos.drop(columns=["fecha"])
    gastos = gastos[["Fecha", "Descripción", "Monto"]]

    # 📊 RESUMEN
    total_ventas = ventas["Total"].astype(float).sum()
    total_gastos = gastos["Monto"].astype(float).sum()
    ganancia = total_ventas - total_gastos

    resumen = pd.DataFrame({
        "Concepto": ["Ventas", "Gastos", "Ganancia"],
        "Monto": [total_ventas, total_gastos, ganancia]
    })

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:

        ventas.to_excel(writer, sheet_name="Ventas", index=False)
        gastos.to_excel(writer, sheet_name="Gastos", index=False)
        ranking.to_excel(writer, sheet_name="Ranking", index=False)
        resumen.to_excel(writer, sheet_name="Resumen", index=False)

        # 🎨 ESTILOS
        header_fill = PatternFill(start_color="34495E", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        center = Alignment(horizontal="center")
        thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                      top=Side(style='thin'), bottom=Side(style='thin'))

        for name, sheet in writer.sheets.items():

            sheet.column_dimensions["A"].width = 20
            sheet.column_dimensions["B"].width = 30
            sheet.column_dimensions["C"].width = 15
            sheet.column_dimensions["D"].width = 15

            for cell in sheet[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = center
                cell.border = thin

            for i, row in enumerate(sheet.iter_rows(min_row=2), start=2):
                for cell in row:
                    cell.border = thin
                    cell.alignment = center

                    if name == "Ventas" and cell.column_letter == "D":
                        cell.number_format = '"$"#,##0'

                    if name == "Gastos" and cell.column_letter == "C":
                        cell.number_format = '"$"#,##0'

                    if name == "Resumen" and cell.column_letter == "B":
                        cell.number_format = '"$"#,##0'

                if i % 2 == 0:
                    for cell in row:
                        cell.fill = PatternFill(start_color="F2F2F2", fill_type="solid")

        # 📊 GRÁFICO RANKING
        sheet_ranking = writer.sheets["Ranking"]

        chart = BarChart()
        chart.title = "Productos más vendidos"

        max_filas = min(len(ranking), 5) + 1

        data = Reference(sheet_ranking, min_col=2, min_row=1, max_row=max_filas)
        categories = Reference(sheet_ranking, min_col=1, min_row=2, max_row=max_filas)

        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)

        chart.width = 12
        chart.height = 7

        sheet_ranking.add_chart(chart, "E2")

    output.seek(0)

    return send_file(
        output,
        download_name="reporte_pro.xlsx",
        as_attachment=True
    )
# ▶️ EJECUTAR
if __name__ == "__main__":
    app.run(debug=True)

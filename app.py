from decimal import Decimal, InvalidOperation
from io import BytesIO
import os
import uuid

from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from config import Config
from extensions import db, migrate
from models import Customer, Product, ProductVariant, Order, OrderItem, Payment, User


ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def allowed_image_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def parse_decimal(value, default="0"):
    try:
        if value is None or str(value).strip() == "":
            return Decimal(default)
        return Decimal(str(value).strip())
    except InvalidOperation:
        return Decimal(default)


def parse_int(value, default=0):
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(value)
    except ValueError:
        return default


def save_product_image(app, uploaded_file):
    if not uploaded_file or uploaded_file.filename == "":
        return None

    if not allowed_image_file(uploaded_file.filename):
        return None

    original_name = secure_filename(uploaded_file.filename)
    ext = original_name.rsplit(".", 1)[1].lower()
    new_filename = f"{uuid.uuid4().hex}.{ext}"

    upload_folder = os.path.join(app.root_path, "static", "uploads", "products")
    os.makedirs(upload_folder, exist_ok=True)

    uploaded_file.save(os.path.join(upload_folder, new_filename))
    return new_filename


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(os.path.join(app.root_path, "static", "uploads", "products"), exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.login_message = "Iniciá sesión para continuar."
    login_manager.login_message_category = "warning"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.template_filter("money")
    def money_filter(value):
        try:
            return f"₡{float(value):,.2f}"
        except Exception:
            return "₡0.00"

    def root_required():
        if not current_user.is_authenticated or current_user.role != "ROOT":
            flash("No tenés permiso para acceder a esta sección.", "danger")
            return False
        return True

    # -------------------------
    # DEBUG TESTS
    # -------------------------
    @app.route("/test")
    def test():
        return "OK"

    @app.route("/test2")
    def test2():
        return "VERSION NUEVA"

    # -------------------------
    # AUTH
    # -------------------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            user = User.query.filter_by(username=username).first()

            if not user or not user.check_password(password):
                flash("Usuario o contraseña incorrectos.", "danger")
                return redirect(url_for("login"))

            if not user.is_active_user:
                flash("Este usuario está inactivo.", "danger")
                return redirect(url_for("login"))

            login_user(user)
            flash("Sesión iniciada correctamente.", "success")
            return redirect(url_for("dashboard"))

        return render_template("auth/login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("Sesión cerrada.", "success")
        return redirect(url_for("login"))

    @app.route("/admin/create", methods=["GET", "POST"])
    @login_required
    def create_admin():
        if not root_required():
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            role = request.form.get("role", "ADMIN").strip()

            if not username or not password:
                flash("Usuario y contraseña son obligatorios.", "danger")
                return redirect(url_for("create_admin"))

            if role not in ["ADMIN", "ROOT"]:
                role = "ADMIN"

            if User.query.filter_by(username=username).first():
                flash("Ese usuario ya existe.", "danger")
                return redirect(url_for("create_admin"))

            user = User(username=username, role=role)
            user.set_password(password)

            db.session.add(user)
            db.session.commit()

            flash("Usuario creado correctamente.", "success")
            return redirect(url_for("create_admin"))

        users = User.query.order_by(User.created_at.desc()).all()
        return render_template("auth/create_admin.html", users=users)

    # -------------------------
    # DASHBOARD
    # -------------------------
    @app.route("/")
    @login_required
    def dashboard():
        total_products = Product.query.count()
        total_customers = Customer.query.count()

        pending_orders = Order.query.filter(Order.order_status == "PENDING").count()
        completed_orders = Order.query.filter(Order.order_status == "COMPLETED").count()
        cancelled_orders = Order.query.filter(Order.order_status == "CANCELLED").count()

        orders = Order.query.all()

        total_revenue = sum(
            float(order.subtotal or 0)
            for order in orders
            if order.order_status != "CANCELLED"
        )

        total_collected = sum(
            float(order.total_paid or 0)
            for order in orders
            if order.order_status != "CANCELLED"
        )

        total_pending_balance = sum(
            float(order.balance_due or 0)
            for order in orders
            if order.order_status != "CANCELLED"
        )

        low_stock_variants = (
            ProductVariant.query
            .filter(ProductVariant.stock_quantity <= 3)
            .order_by(ProductVariant.stock_quantity.asc())
            .all()
        )

        return render_template(
            "dashboard.html",
            total_products=total_products,
            total_customers=total_customers,
            pending_orders=pending_orders,
            completed_orders=completed_orders,
            cancelled_orders=cancelled_orders,
            total_revenue=total_revenue,
            total_collected=total_collected,
            total_pending_balance=total_pending_balance,
            low_stock_variants=low_stock_variants,
        )

    # -------------------------
    # CUSTOMERS
    # -------------------------
    @app.route("/customers")
    @login_required
    def customer_list():
        customers = Customer.query.order_by(Customer.created_at.desc()).all()
        return render_template("customers/list.html", customers=customers)

    @app.route("/customers/new", methods=["GET", "POST"])
    @login_required
    def customer_create():
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            phone = request.form.get("phone", "").strip()
            email = request.form.get("email", "").strip()
            notes = request.form.get("notes", "").strip()

            if not full_name or not phone:
                flash("Nombre y teléfono son obligatorios.", "danger")
                return redirect(url_for("customer_create"))

            customer = Customer(
                full_name=full_name,
                phone=phone,
                email=email or None,
                notes=notes or None,
            )

            db.session.add(customer)
            db.session.commit()

            flash("Cliente creado correctamente.", "success")
            return redirect(url_for("customer_list"))

        return render_template("customers/form.html", customer=None)

    @app.route("/customers/quick-create", methods=["POST"])
    @login_required
    def customer_quick_create():
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        notes = request.form.get("notes", "").strip()

        if not full_name or not phone:
            flash("Nombre y teléfono son obligatorios.", "danger")
            return redirect(url_for("order_create"))

        customer = Customer(
            full_name=full_name,
            phone=phone,
            email=email or None,
            notes=notes or None,
        )

        db.session.add(customer)
        db.session.commit()

        flash("Cliente creado correctamente.", "success")
        return redirect(url_for("order_create"))

    # -------------------------
    # PRODUCTS
    # -------------------------
    @app.route("/products")
    @login_required
    def product_list():
        products = Product.query.order_by(Product.created_at.desc()).all()
        return render_template("products/list.html", products=products)

    @app.route("/products/new", methods=["GET", "POST"])
    @login_required
    def product_create():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            base_price = parse_decimal(request.form.get("base_price"))
            image_file = request.files.get("image")

            if not name:
                flash("El nombre del producto es obligatorio.", "danger")
                return redirect(url_for("product_create"))

            image_filename = None

            if image_file and image_file.filename:
                image_filename = save_product_image(app, image_file)

                if image_filename is None:
                    flash("Imagen inválida. Usá PNG, JPG, JPEG o WEBP.", "danger")
                    return redirect(url_for("product_create"))

            product = Product(
                name=name,
                base_price=base_price,
                image_filename=image_filename,
            )

            db.session.add(product)
            db.session.flush()

            sizes = ["S", "M", "L", "XL", "XXL"]

            for size in sizes:
                qty = parse_int(request.form.get(f"stock_{size}"), 0)

                if qty > 0:
                    variant = ProductVariant(
                        product_id=product.id,
                        size=size,
                        stock_quantity=qty,
                    )
                    db.session.add(variant)

            db.session.commit()

            flash("Producto creado correctamente.", "success")
            return redirect(url_for("product_list"))

        return render_template("products/form.html", product=None)

    @app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
    @login_required
    def product_edit(product_id):
        product = Product.query.get_or_404(product_id)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            base_price = parse_decimal(request.form.get("base_price"))
            image_file = request.files.get("image")

            if not name:
                flash("El nombre del producto es obligatorio.", "danger")
                return redirect(url_for("product_edit", product_id=product.id))

            product.name = name
            product.base_price = base_price

            if image_file and image_file.filename:
                image_filename = save_product_image(app, image_file)

                if image_filename is None:
                    flash("Imagen inválida. Usá PNG, JPG, JPEG o WEBP.", "danger")
                    return redirect(url_for("product_edit", product_id=product.id))

                product.image_filename = image_filename

            sizes = ["S", "M", "L", "XL", "XXL"]
            existing_variants = {variant.size: variant for variant in product.variants}

            for size in sizes:
                qty = parse_int(request.form.get(f"stock_{size}"), 0)

                if size in existing_variants:
                    existing_variants[size].stock_quantity = qty
                elif qty > 0:
                    variant = ProductVariant(
                        product_id=product.id,
                        size=size,
                        stock_quantity=qty,
                    )
                    db.session.add(variant)

            db.session.commit()

            flash("Producto actualizado correctamente.", "success")
            return redirect(url_for("product_list"))

        return render_template("products/form.html", product=product)

    @app.route("/products/<int:product_id>/delete", methods=["POST"])
    @login_required
    def product_delete(product_id):
        product = Product.query.get_or_404(product_id)

        if product.has_orders():
            flash("No podés eliminar un producto que ya tiene órdenes registradas.", "danger")
            return redirect(url_for("product_list"))

        db.session.delete(product)
        db.session.commit()

        flash("Producto eliminado correctamente.", "success")
        return redirect(url_for("product_list"))

    # -------------------------
    # ORDERS
    # -------------------------
    @app.route("/orders")
    @login_required
    def order_list():
        order_status = request.args.get("order_status", "").strip()
        payment_status = request.args.get("payment_status", "").strip()
        search = request.args.get("search", "").strip()

        query = Order.query.join(Customer).order_by(Order.created_at.desc())

        if order_status:
            query = query.filter(Order.order_status == order_status)

        if payment_status:
            query = query.filter(Order.payment_status == payment_status)

        if search:
            like_term = f"%{search}%"
            query = query.filter(
                or_(
                    Customer.full_name.ilike(like_term),
                    Customer.phone.ilike(like_term),
                )
            )

        orders = query.all()

        return render_template(
            "orders/list.html",
            orders=orders,
            current_order_status=order_status,
            current_payment_status=payment_status,
            current_search=search,
        )

    @app.route("/orders/new", methods=["GET", "POST"])
    @login_required
    def order_create():
        customers = Customer.query.order_by(Customer.full_name.asc()).all()
        variants = ProductVariant.query.order_by(ProductVariant.created_at.desc()).all()
        available_variants = [variant for variant in variants if variant.available_quantity() > 0]

        if request.method == "POST":
            customer_id = request.form.get("customer_id")
            payment_type = request.form.get("payment_type", "PARTIAL")
            payment_method = request.form.get("payment_method", "CASH")
            fulfillment_method = request.form.get("fulfillment_method", "PICKUP")
            shipping_address = request.form.get("shipping_address", "").strip()
            pickup_location = request.form.get("pickup_location", "").strip()
            notes = request.form.get("notes", "").strip()

            variant_ids = request.form.getlist("variant_id[]")
            quantities = request.form.getlist("quantity[]")
            discount_amounts = request.form.getlist("discount_amount[]")

            if not customer_id:
                flash("Seleccioná un cliente.", "danger")
                return redirect(url_for("order_create"))

            clean_lines = []

            for index, variant_id in enumerate(variant_ids):
                if not variant_id:
                    continue

                qty = parse_int(quantities[index] if index < len(quantities) else "1", 1)
                discount_amount = parse_decimal(
                    discount_amounts[index] if index < len(discount_amounts) else "0"
                )

                if qty <= 0:
                    qty = 1

                variant = ProductVariant.query.get(variant_id)

                if not variant:
                    continue

                clean_lines.append((variant, qty, discount_amount))

            if not clean_lines:
                flash("Agregá al menos un producto.", "danger")
                return redirect(url_for("order_create"))

            customer = Customer.query.get_or_404(customer_id)

            order = Order(
                customer_id=customer.id,
                order_status="PENDING",
                fulfillment_method=fulfillment_method,
                fulfillment_status="SHIPPING_PENDING" if fulfillment_method == "SHIPPING" else "PICKUP_PENDING",
                shipping_address=shipping_address or None,
                pickup_location=pickup_location or None,
                notes=notes or None,
            )

            db.session.add(order)
            db.session.flush()

            for variant, qty, discount_amount in clean_lines:
                if variant.stock_quantity < qty:
                    db.session.rollback()
                    flash(
                        f"Stock insuficiente para {variant.product.name} / {variant.size}.",
                        "danger",
                    )
                    return redirect(url_for("order_create"))

                base_price = Decimal(str(variant.product.base_price))
                final_price = base_price - discount_amount

                if final_price < 0:
                    final_price = Decimal("0")

                item = OrderItem(
                    order_id=order.id,
                    product_variant_id=variant.id,
                    quantity=qty,
                    unit_price=final_price,
                    discount_amount=discount_amount,
                    item_status="RESERVED",
                )

                db.session.add(item)
                variant.stock_quantity -= qty

            db.session.flush()
            order.recalculate_totals()

            if payment_type == "FULL":
                initial_payment_amount = Decimal(str(order.subtotal))
            elif payment_type == "NONE":
                initial_payment_amount = Decimal("0")
            else:
                initial_payment_amount = Decimal(str(order.subtotal)) * Decimal("0.50")

            order.deposit_amount = initial_payment_amount

            if initial_payment_amount > 0:
                payment = Payment(
                    order=order,
                    amount=initial_payment_amount,
                    payment_method=payment_method or "CASH",
                    notes="Pago inicial",
                )
                db.session.add(payment)

            db.session.flush()
            order.recalculate_totals()

            if order.payment_status == "PAID":
                for item in order.items:
                    item.item_status = "PAID"

            db.session.commit()

            flash("Orden creada correctamente.", "success")
            return redirect(url_for("order_detail", order_id=order.id))

        return render_template(
            "orders/form.html",
            customers=customers,
            variants=available_variants,
        )

    @app.route("/orders/<int:order_id>")
    @login_required
    def order_detail(order_id):
        order = Order.query.get_or_404(order_id)
        return render_template("orders/detail.html", order=order)

    @app.route("/orders/<int:order_id>/edit", methods=["GET", "POST"])
    @login_required
    def order_edit(order_id):
        order = Order.query.get_or_404(order_id)

        if order.order_status == "CANCELLED":
            flash("No podés editar una orden cancelada.", "danger")
            return redirect(url_for("order_detail", order_id=order.id))

        customers = Customer.query.order_by(Customer.full_name.asc()).all()

        if request.method == "POST":
            customer_id = request.form.get("customer_id")
            fulfillment_method = request.form.get("fulfillment_method", "PICKUP")
            shipping_address = request.form.get("shipping_address", "").strip()
            pickup_location = request.form.get("pickup_location", "").strip()
            notes = request.form.get("notes", "").strip()

            customer = Customer.query.get_or_404(customer_id)

            order.customer_id = customer.id
            order.fulfillment_method = fulfillment_method
            order.fulfillment_status = "SHIPPING_PENDING" if fulfillment_method == "SHIPPING" else "PICKUP_PENDING"
            order.shipping_address = shipping_address or None
            order.pickup_location = pickup_location or None
            order.notes = notes or None

            db.session.commit()

            flash("Orden actualizada correctamente.", "success")
            return redirect(url_for("order_detail", order_id=order.id))

        return render_template(
            "orders/edit.html",
            order=order,
            customers=customers,
        )

    @app.route("/orders/<int:order_id>/add-payment", methods=["POST"])
    @login_required
    def order_add_payment(order_id):
        order = Order.query.get_or_404(order_id)

        if order.order_status == "CANCELLED":
            flash("No podés agregar pagos a una orden cancelada.", "danger")
            return redirect(url_for("order_detail", order_id=order.id))

        amount = parse_decimal(request.form.get("amount"))
        payment_method = request.form.get("payment_method", "CASH").strip()
        notes = request.form.get("notes", "").strip()

        if amount <= 0:
            flash("El monto debe ser mayor a cero.", "danger")
            return redirect(url_for("order_detail", order_id=order.id))

        if amount > order.balance_due:
            flash("El monto no puede ser mayor al saldo pendiente.", "danger")
            return redirect(url_for("order_detail", order_id=order.id))

        payment = Payment(
            order=order,
            amount=amount,
            payment_method=payment_method or "CASH",
            notes=notes or None,
        )

        db.session.add(payment)
        db.session.flush()

        order.recalculate_totals()

        if order.payment_status == "PAID":
            for item in order.items:
                if item.item_status != "CANCELLED":
                    item.item_status = "PAID"

        db.session.commit()

        flash("Pago registrado correctamente.", "success")
        return redirect(url_for("order_detail", order_id=order.id))

    @app.route("/orders/<int:order_id>/mark-completed", methods=["POST"])
    @login_required
    def order_mark_completed(order_id):
        order = Order.query.get_or_404(order_id)

        if order.order_status == "CANCELLED":
            flash("No podés completar una orden cancelada.", "danger")
            return redirect(url_for("order_detail", order_id=order.id))

        if order.payment_status != "PAID":
            flash("La orden debe estar pagada antes de marcarla como completada.", "danger")
            return redirect(url_for("order_detail", order_id=order.id))

        order.order_status = "COMPLETED"
        order.fulfillment_status = "DELIVERED"

        for item in order.items:
            if item.item_status != "CANCELLED":
                item.item_status = "DELIVERED"

        db.session.commit()

        flash("Orden completada correctamente.", "success")
        return redirect(url_for("order_detail", order_id=order.id))

    @app.route("/orders/<int:order_id>/cancel", methods=["POST"])
    @login_required
    def order_cancel(order_id):
        order = Order.query.get_or_404(order_id)

        if order.order_status == "CANCELLED":
            flash("La orden ya estaba cancelada.", "warning")
            return redirect(url_for("order_detail", order_id=order.id))

        order.order_status = "CANCELLED"
        order.fulfillment_status = "CANCELLED"

        for item in order.items:
            if item.item_status != "CANCELLED":
                item.variant.stock_quantity += item.quantity
                item.item_status = "CANCELLED"

        db.session.commit()

        flash("Orden cancelada correctamente. El stock fue restaurado.", "warning")
        return redirect(url_for("order_detail", order_id=order.id))

    @app.route("/orders/<int:order_id>/pdf")
    @login_required
    def order_pdf(order_id):
        order = Order.query.get_or_404(order_id)

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        logo_path = os.path.join(app.root_path, "static", "img", "logo.png")
        regular_font_path = os.path.join(app.root_path, "static", "fonts", "Inter_18pt-Regular.ttf")
        bold_font_path = os.path.join(app.root_path, "static", "fonts", "Inter_18pt-Bold.ttf")

        regular_font_name = "Helvetica"
        bold_font_name = "Helvetica-Bold"

        try:
            if os.path.exists(regular_font_path):
                pdfmetrics.registerFont(TTFont("Inter-Regular", regular_font_path))
                regular_font_name = "Inter-Regular"

            if os.path.exists(bold_font_path):
                pdfmetrics.registerFont(TTFont("Inter-Bold", bold_font_path))
                bold_font_name = "Inter-Bold"
        except Exception:
            regular_font_name = "Helvetica"
            bold_font_name = "Helvetica-Bold"

        def money(value):
            try:
                return f"CRC {float(value):,.0f}"
            except Exception:
                return "CRC 0"

        def draw_label_value(x, y, label, value, label_width=38 * mm):
            pdf.setFont(bold_font_name, 9)
            pdf.setFillColor(colors.HexColor("#111827"))
            pdf.drawString(x, y, label)

            pdf.setFont(regular_font_name, 9)
            pdf.setFillColor(colors.HexColor("#374151"))
            pdf.drawString(x + label_width, y, str(value))

        pdf.setFillColor(colors.white)
        pdf.rect(0, 0, width, height, fill=1, stroke=0)

        y = height - 28 * mm

        if os.path.exists(logo_path):
            try:
                logo = ImageReader(logo_path)
                pdf.drawImage(
                    logo,
                    20 * mm,
                    y - 10 * mm,
                    width=28 * mm,
                    height=28 * mm,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass

        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.setFont(bold_font_name, 22)
        pdf.drawString(55 * mm, y, "Carrier")

        pdf.setFont(regular_font_name, 10)
        pdf.setFillColor(colors.HexColor("#6B7280"))
        pdf.drawString(55 * mm, y - 6 * mm, "Order Document")

        title = "Invoice" if order.payment_status == "PAID" else "Reservation Receipt"

        pdf.setFont(bold_font_name, 14)
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.drawRightString(width - 20 * mm, y, title)

        pdf.setFont(regular_font_name, 10)
        pdf.setFillColor(colors.HexColor("#6B7280"))
        pdf.drawRightString(width - 20 * mm, y - 6 * mm, f"Order #{order.id}")

        y -= 24 * mm
        pdf.setStrokeColor(colors.HexColor("#E5E7EB"))
        pdf.line(20 * mm, y, width - 20 * mm, y)

        y -= 12 * mm

        pdf.setFont(bold_font_name, 12)
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.drawString(20 * mm, y, "Customer")
        pdf.drawString(110 * mm, y, "Summary")

        y -= 8 * mm

        draw_label_value(20 * mm, y, "Name:", order.customer.full_name)
        y -= 6 * mm
        draw_label_value(20 * mm, y, "Phone:", order.customer.phone)

        if order.customer.email:
            y -= 6 * mm
            draw_label_value(20 * mm, y, "Email:", order.customer.email)

        y_summary = height - 72 * mm
        draw_label_value(110 * mm, y_summary, "Total:", money(order.subtotal))
        y_summary -= 6 * mm
        draw_label_value(110 * mm, y_summary, "Paid:", money(order.total_paid))
        y_summary -= 6 * mm
        draw_label_value(110 * mm, y_summary, "Balance:", money(order.balance_due))
        y_summary -= 6 * mm
        draw_label_value(110 * mm, y_summary, "Payment:", order.payment_status)
        y_summary -= 6 * mm
        draw_label_value(110 * mm, y_summary, "Order:", order.order_status)

        y = min(y, y_summary) - 12 * mm

        pdf.setStrokeColor(colors.HexColor("#E5E7EB"))
        pdf.line(20 * mm, y, width - 20 * mm, y)

        y -= 10 * mm
        pdf.setFont(bold_font_name, 12)
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.drawString(20 * mm, y, "Items")

        y -= 10 * mm

        for item in order.items:
            if y < 55 * mm:
                pdf.showPage()
                y = height - 30 * mm

            card_height = 34 * mm

            pdf.setFillColor(colors.HexColor("#F8FAFC"))
            pdf.roundRect(
                20 * mm,
                y - card_height,
                width - 40 * mm,
                card_height,
                6,
                fill=1,
                stroke=0,
            )

            image_x = 24 * mm
            image_y = y - 29 * mm
            image_w = 22 * mm
            image_h = 22 * mm

            product_image_path = None

            if item.variant.product.image_filename:
                product_image_path = os.path.join(
                    app.root_path,
                    "static",
                    "uploads",
                    "products",
                    item.variant.product.image_filename,
                )

            if product_image_path and os.path.exists(product_image_path):
                try:
                    product_img = ImageReader(product_image_path)
                    pdf.drawImage(
                        product_img,
                        image_x,
                        image_y,
                        width=image_w,
                        height=image_h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                except Exception:
                    pdf.setFillColor(colors.HexColor("#E5E7EB"))
                    pdf.roundRect(image_x, image_y, image_w, image_h, 4, fill=1, stroke=0)
            else:
                pdf.setFillColor(colors.HexColor("#E5E7EB"))
                pdf.roundRect(image_x, image_y, image_w, image_h, 4, fill=1, stroke=0)

            text_x = 52 * mm
            text_y = y - 9 * mm

            pdf.setFillColor(colors.HexColor("#111827"))
            pdf.setFont(bold_font_name, 10)
            pdf.drawString(text_x, text_y, str(item.variant.product.name)[:48])

            pdf.setFont(regular_font_name, 9)
            pdf.setFillColor(colors.HexColor("#374151"))
            pdf.drawString(text_x, text_y - 6 * mm, f"Size: {item.variant.size}")
            pdf.drawString(text_x + 28 * mm, text_y - 6 * mm, f"Qty: {item.quantity}")
            pdf.drawString(text_x + 55 * mm, text_y - 6 * mm, f"Unit: {money(item.unit_price)}")

            if item.discount_amount and item.discount_amount > 0:
                pdf.drawString(text_x, text_y - 12 * mm, f"Discount/unit: {money(item.discount_amount)}")

            pdf.drawString(text_x, text_y - 18 * mm, f"Line total: {money(item.line_total)}")

            y -= 40 * mm

        y -= 3 * mm
        pdf.setStrokeColor(colors.HexColor("#E5E7EB"))
        pdf.line(20 * mm, y, width - 20 * mm, y)

        y -= 10 * mm
        pdf.setFont(bold_font_name, 12)
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.drawString(20 * mm, y, "Payments")

        y -= 8 * mm

        pdf.setFont(regular_font_name, 9)

        if order.payments:
            for payment in order.payments:
                if y < 25 * mm:
                    pdf.showPage()
                    y = height - 30 * mm

                pdf.setFillColor(colors.HexColor("#111827"))
                pdf.drawString(20 * mm, y, payment.created_at.strftime("%Y-%m-%d %H:%M"))
                pdf.drawString(65 * mm, y, money(payment.amount))
                pdf.drawString(100 * mm, y, payment.payment_method)
                pdf.drawString(132 * mm, y, str(payment.notes or "-")[:35])
                y -= 7 * mm
        else:
            pdf.setFillColor(colors.HexColor("#6B7280"))
            pdf.drawString(20 * mm, y, "No payments registered.")

        pdf.setFillColor(colors.HexColor("#9CA3AF"))
        pdf.setFont(regular_font_name, 8)
        pdf.drawString(20 * mm, 12 * mm, "Carrier • Generated automatically")

        pdf.save()
        buffer.seek(0)

        filename = f"order_{order.id}.pdf"

        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf",
        )

    # -------------------------
    # CLI COMMANDS
    # -------------------------
    @app.cli.command("create-root")
    def create_root():
        username = "root"
        password = "123456"

        if User.query.filter_by(username=username).first():
            print("Root ya existe")
            return

        user = User(username=username, role="ROOT")
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        print("Root creado")
        print("Usuario: root")
        print("Password: 123456")

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
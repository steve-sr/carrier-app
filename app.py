from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user
from config import Config
from extensions import db, migrate
from models import Customer, Product, Order, User


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    # LOGIN
    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # -------------------------
    # LOGIN
    # -------------------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")

            user = User.query.filter_by(username=username).first()

            if not user or not user.check_password(password):
                flash("Credenciales incorrectas", "danger")
                return redirect(url_for("login"))

            login_user(user)
            return redirect(url_for("dashboard"))

        return render_template("auth/login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # -------------------------
    # TEST
    # -------------------------
    @app.route("/test")
    def test():
        return "OK"

    # -------------------------
    # DASHBOARD
    # -------------------------
    @app.route("/")
    @login_required
    def dashboard():
        return render_template("dashboard.html")

    # -------------------------
    # PRODUCTS
    # -------------------------
    @app.route("/products")
    @login_required
    def product_list():
        products = Product.query.all()
        return render_template("products/list.html", products=products)

    # -------------------------
    # ORDERS
    # -------------------------
    @app.route("/orders")
    @login_required
    def order_list():
        orders = Order.query.all()
        return render_template("orders/list.html", orders=orders)

    # -------------------------
    # CUSTOMERS
    # -------------------------
    @app.route("/customers")
    @login_required
    def customer_list():
        customers = Customer.query.all()
        return render_template("customers/list.html", customers=customers)

    # -------------------------
    # CLI ROOT
    # -------------------------
    @app.cli.command("create-root")
    def create_root():
        if User.query.filter_by(username="root").first():
            print("Root ya existe")
            return

        user = User(username="root", role="ROOT")
        user.set_password("123456")

        db.session.add(user)
        db.session.commit()

        print("Root creado")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
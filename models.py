from datetime import datetime
from decimal import Decimal
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin



class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Customer(db.Model, TimestampMixin):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    orders = db.relationship("Order", backref="customer", lazy=True)


class Product(db.Model, TimestampMixin):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    base_price = db.Column(db.Numeric(10, 2), nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    variants = db.relationship(
        "ProductVariant",
        backref="product",
        lazy=True,
        cascade="all, delete-orphan"
    )

    @property
    def total_stock(self):
        return sum(v.stock_quantity for v in self.variants)

    @property
    def available_stock(self):
        return sum(v.available_quantity() for v in self.variants)


class ProductVariant(db.Model, TimestampMixin):
    __tablename__ = "product_variants"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    size = db.Column(db.String(10), nullable=False)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)

    order_items = db.relationship("OrderItem", backref="variant", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("product_id", "size", name="uq_product_size"),
    )

    def available_quantity(self):
        return self.stock_quantity


class Order(db.Model, TimestampMixin):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)

    order_status = db.Column(db.String(20), nullable=False, default="PENDING")
    payment_status = db.Column(db.String(20), nullable=False, default="UNPAID")
    fulfillment_method = db.Column(db.String(20), nullable=False, default="PICKUP")
    fulfillment_status = db.Column(db.String(30), nullable=False, default="PICKUP_PENDING")

    shipping_address = db.Column(db.Text, nullable=True)
    pickup_location = db.Column(db.String(120), nullable=True)

    subtotal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_paid = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    balance_due = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    notes = db.Column(db.Text, nullable=True)

    items = db.relationship(
        "OrderItem",
        backref="order",
        lazy=True,
        cascade="all, delete-orphan"
    )

    payments = db.relationship(
        "Payment",
        backref="order",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="desc(Payment.created_at)"
    )

    def recalculate_totals(self):
        subtotal = sum(item.unit_price * item.quantity for item in self.items)

        self.subtotal = subtotal

        if self.subtotal < 0:
            self.subtotal = 0

        # saldo
        self.balance_due = self.subtotal - self.total_paid

        if self.balance_due < 0:
            self.balance_due = 0

        # estado de pago
        if self.total_paid >= self.subtotal:
            self.payment_status = "PAID"
        elif self.total_paid > 0:
            self.payment_status = "PARTIAL"
        else:
            self.payment_status = "UNPAID"

class OrderItem(db.Model, TimestampMixin):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)

    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)

    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    item_status = db.Column(db.String(20), nullable=False, default="RESERVED")


class Payment(db.Model, TimestampMixin):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(30), nullable=False, default="CASH")
    notes = db.Column(db.Text, nullable=True)

class User(UserMixin, db.Model, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="ADMIN")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)
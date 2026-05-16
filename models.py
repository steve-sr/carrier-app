from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class User(UserMixin, db.Model, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="ADMIN")  # ROOT / ADMIN
    is_active_user = db.Column(db.Boolean, nullable=False, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Customer(db.Model, TimestampMixin):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    orders = db.relationship("Order", backref="customer", lazy=True)

    def __repr__(self):
        return f"<Customer {self.full_name}>"


class Product(db.Model, TimestampMixin):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    base_price = db.Column(db.Numeric(10, 2), nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    variants = db.relationship(
        "ProductVariant",
        backref="product",
        lazy=True,
        cascade="all, delete-orphan",
    )

    @property
    def total_stock(self):
        return sum(v.stock_quantity for v in self.variants)

    @property
    def available_stock(self):
        return sum(v.available_quantity() for v in self.variants)

    def has_orders(self):
        return any(len(variant.order_items) > 0 for variant in self.variants)

    def __repr__(self):
        return f"<Product {self.name}>"


class ProductVariant(db.Model, TimestampMixin):
    __tablename__ = "product_variants"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    size = db.Column(db.String(20), nullable=False)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)

    order_items = db.relationship("OrderItem", backref="variant", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("product_id", "size", name="uq_product_size"),
    )

    def available_quantity(self):
        return max(self.stock_quantity, 0)

    def __repr__(self):
        return f"<Variant product={self.product_id} size={self.size}>"


class Order(db.Model, TimestampMixin):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)

    order_status = db.Column(db.String(20), nullable=False, default="PENDING")
    payment_status = db.Column(db.String(20), nullable=False, default="UNPAID")

    fulfillment_method = db.Column(db.String(20), nullable=False, default="PICKUP")
    fulfillment_status = db.Column(db.String(30), nullable=False, default="PICKUP_PENDING")

    shipping_address = db.Column(db.Text, nullable=True)
    pickup_location = db.Column(db.String(160), nullable=True)

    subtotal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_paid = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    balance_due = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    notes = db.Column(db.Text, nullable=True)

    items = db.relationship(
        "OrderItem",
        backref="order",
        lazy=True,
        cascade="all, delete-orphan",
    )

    payments = db.relationship(
        "Payment",
        backref="order",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="desc(Payment.created_at)",
    )

    def recalculate_totals(self):
        subtotal = Decimal("0")

        for item in self.items:
            subtotal += Decimal(str(item.unit_price)) * Decimal(str(item.quantity))

        total_paid = Decimal("0")

        for payment in self.payments:
            total_paid += Decimal(str(payment.amount))

        self.subtotal = subtotal
        self.total_paid = total_paid
        self.balance_due = self.subtotal - self.total_paid

        if self.balance_due < 0:
            self.balance_due = Decimal("0")

        if self.total_paid >= self.subtotal and self.subtotal > 0:
            self.payment_status = "PAID"
        elif self.total_paid > 0:
            self.payment_status = "PARTIAL"
        else:
            self.payment_status = "UNPAID"

    def __repr__(self):
        return f"<Order #{self.id}>"


class OrderItem(db.Model, TimestampMixin):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_variant_id = db.Column(
        db.Integer,
        db.ForeignKey("product_variants.id"),
        nullable=False,
    )

    quantity = db.Column(db.Integer, nullable=False, default=1)

    # unit_price = precio final por unidad, ya con descuento aplicado
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)

    # discount_amount = descuento por unidad
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    item_status = db.Column(db.String(20), nullable=False, default="RESERVED")

    @property
    def original_unit_price(self):
        return Decimal(str(self.unit_price)) + Decimal(str(self.discount_amount or 0))

    @property
    def line_total(self):
        return Decimal(str(self.unit_price)) * Decimal(str(self.quantity))

    @property
    def line_original_total(self):
        return self.original_unit_price * Decimal(str(self.quantity))

    @property
    def line_discount_total(self):
        return Decimal(str(self.discount_amount or 0)) * Decimal(str(self.quantity))

    def __repr__(self):
        return f"<OrderItem order={self.order_id} variant={self.product_variant_id}>"


class Payment(db.Model, TimestampMixin):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(30), nullable=False, default="CASH")
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<Payment order={self.order_id} amount={self.amount}>"
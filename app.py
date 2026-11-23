import os
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

basedir = os.path.abspath(os.path.dirname(__file__))
default_db = f"sqlite:///{os.path.join(basedir, 'ecommerce_v2.db')}"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", default_db)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Integer, nullable=False)  # Price in QAR
    image_url = db.Column(db.String(255), nullable=True)


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    product = db.relationship("Product", backref="cart_items")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def seed_sample_products():
    if Product.query.count() == 0:
        sample_products = [
            Product(name="Classic Hoodie", price=145, image_url=None),
            Product(name="Canvas Tote", price=65, image_url=None),
            Product(name="Desk Lamp", price=190, image_url=None),
            Product(name="Ceramic Mug", price=45, image_url=None),
            Product(name="Wireless Mouse", price=120, image_url=None),
            Product(name="Notebook Set", price=55, image_url=None),
        ]
        db.session.add_all(sample_products)
        db.session.commit()


with app.app_context():
    db.create_all()
    seed_sample_products()


@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    if q:
        products = Product.query.filter(Product.name.ilike(f"%{q}%")).all()
    else:
        products = Product.query.all()
    return render_template("index.html", products=products)


@app.route("/add-to-cart/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    item = CartItem.query.filter_by(user_id=current_user.id, product_id=product.id).first()

    if item:
        item.quantity = min(item.quantity + 1, 100)
    else:
        item = CartItem(user_id=current_user.id, product_id=product.id, quantity=1)
        db.session.add(item)

    db.session.commit()
    return redirect(url_for("cart"))


@app.route("/cart")
@login_required
def cart():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    return render_template("cart.html", cart_items=cart_items)


@app.route("/cart/update/<int:item_id>", methods=["POST"])
@login_required
def update_cart(item_id):
    item = CartItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    try:
        qty = int(request.form.get("quantity", 1))
    except ValueError:
        qty = 1

    if qty <= 0:
        db.session.delete(item)
    else:
        item.quantity = min(qty, 100)

    db.session.commit()
    return redirect(url_for("cart"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("index"))

        flash("Invalid username or password.")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("Please fill in all fields.")
            return render_template("register.html")

        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing_user:
            flash("Username or email already exists.")
            return render_template("register.html")

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Username or email already exists.")
            return render_template("register.html")

        login_user(user)
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        flash("Password reset instructions have been sent if that account exists.")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
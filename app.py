import base64
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
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB max upload

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
    profile_pic = db.Column(db.Text, nullable=True)  # Stores Base64 image
    shop_rewards = db.Column(db.Integer, default=100, nullable=False)  # Starting rewards

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def reward_value_qar(self):
        # 1 Shop Reward = 0.1 QAR
        return round(self.shop_rewards * 0.1, 2)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Integer, nullable=False)  # QAR
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
            Product(name="Gradient Graphic T-shirt", price=145),
            Product(name="Polo with Tipping Details", price=180),
            Product(name="Black Striped T-shirt", price=120),
            Product(name="Skinny Fit Jeans", price=240),
            Product(name="Checkered Shirt", price=180),
            Product(name="Sleeve Striped T-shirt", price=130),
            Product(name="Vertical Striped Shirt", price=212),
            Product(name="Courage Graphic T-shirt", price=145),
        ]
        db.session.add_all(sample_products)
        db.session.commit()


with app.app_context():
    db.create_all()
    seed_sample_products()


@app.context_processor
def inject_cart_count():
    if current_user.is_authenticated:
        count = sum(item.quantity for item in CartItem.query.filter_by(user_id=current_user.id).all())
        return dict(cart_count=count)
    return dict(cart_count=0)


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


@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash("Your cart is empty.")
        return redirect(url_for("cart"))

    subtotal = sum(item.product.price * item.quantity for item in cart_items)
    
    # 1 QAR Spent = 1 Shop Reward Earned
    earned_rewards = subtotal
    current_user.shop_rewards += earned_rewards

    # Clear cart after checkout
    for item in cart_items:
        db.session.delete(item)

    db.session.commit()
    flash(f"Order successful! You earned {earned_rewards} Shop Rewards!")
    return redirect(url_for("profile"))


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

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or email already exists.")
            return render_template("register.html")

        # Create user with 50 bonus rewards upon sign up
        user = User(username=username, email=email, shop_rewards=50)
        user.set_password(password)
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Username or email already exists.")
            return render_template("register.html")

        login_user(user)
        flash("Account created! You received 50 bonus Shop Rewards!")
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html")


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        file = request.files.get("profile_pic")

        if username and username != current_user.username:
            if User.query.filter_by(username=username).first():
                flash("Username is already taken.")
                return render_template("edit_profile.html")
            current_user.username = username

        if email and email != current_user.email:
            if User.query.filter_by(email=email).first():
                flash("Email is already taken.")
                return render_template("edit_profile.html")
            current_user.email = email

        if file and file.filename != "":
            file_bytes = file.read()
            mime_type = file.mimetype
            base64_img = base64.b64encode(file_bytes).decode("utf-8")
            current_user.profile_pic = f"data:{mime_type};base64,{base64_img}"

        db.session.commit()
        flash("Profile updated successfully!")
        return redirect(url_for("profile"))

    return render_template("edit_profile.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
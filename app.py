#36b48c5d1ba5e23cc3046499d6481c32743abc11a54185996e775b7f5a3c6d3c
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = '36b48c5d1ba5e23cc3046499d6481c32743abc11a54185996e775b7f5a3c6d3c'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ecommerce_v2.db'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- GMAIL CONFIGURATION ---
SENDER_EMAIL = "codetest662@gmail.com"
APP_PASSWORD = "xlum znzw wccn yefw"


# --- DATABASE MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    reset_code = db.Column(db.String(6), nullable=True)
    cart_items = db.relationship(
        'CartItem', backref='user', lazy=True, cascade='all, delete-orphan'
    )


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(
        db.Text, nullable=False, default="Quality store product."
    )


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    product = db.relationship('Product')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def get_cart_count():
    if not current_user.is_authenticated:
        return 0
    return sum(item.quantity for item in current_user.cart_items)


@app.context_processor
def inject_cart_count():
    return {'cart_count': get_cart_count()}


# --- HELPER FUNCTION: SEND GMAIL ---
def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


# --- ROUTES ---
@app.route('/')
def home():
    products = Product.query.all()
    return render_template('index.html', products=products)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product)


@app.route('/add-to-cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    try:
        qty = int(request.form.get('quantity', 1))
    except ValueError:
        qty = 1

    if qty < 1 or qty > 100:
        flash("Quantity must be between 1 and 100.", "danger")
        return redirect(url_for('product_detail', product_id=product.id))

    existing_item = CartItem.query.filter_by(
        user_id=current_user.id, product_id=product.id
    ).first()
    if existing_item:
        existing_item.quantity = min(100, existing_item.quantity + qty)
    else:
        db.session.add(
            CartItem(user_id=current_user.id, product_id=product.id, quantity=qty)
        )

    db.session.commit()
    flash(f"Added {qty} x {product.name} to your cart!", "success")
    return redirect(url_for('cart'))


@app.route('/cart')
@login_required
def cart():
    items = current_user.cart_items
    total_bill = sum(item.product.price * item.quantity for item in items)
    return render_template('cart.html', items=items, total_bill=total_bill)


@app.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('cart'))

    db.session.delete(item)
    db.session.commit()
    flash("Item removed from cart.", "info")
    return redirect(url_for('cart'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if User.query.filter_by(email=email).first():
            flash("Email already exists!", "danger")
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password, method='scrypt')
        new_user = User(email=email, password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()

        subject = "Welcome to Our Store!"
        body = "Hello,\n\nThank you for creating an account at our E-Commerce store!"
        send_email(email, subject, body)

        flash("Account created! Check your email for confirmation.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Logged in successfully!", "success")
            return redirect(url_for('home'))

        flash("Invalid email or password.", "danger")
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for('home'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()

        if user:
            code = str(random.randint(100000, 999999))
            user.reset_code = code
            db.session.commit()

            subject = "Password Reset Code"
            body = f"Your verification code to reset your password is: {code}"
            send_email(email, subject, body)

            flash("Verification code sent to your email.", "info")
            return redirect(url_for('reset_password', email=email))

        flash("Email not found.", "danger")
    return render_template('forgot_password.html')


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = request.args.get('email') or request.form.get('email')
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        new_password = request.form.get('new_password', '')
        user = User.query.filter_by(email=email).first()

        if user and user.reset_code == code:
            user.password_hash = generate_password_hash(new_password, method='scrypt')
            user.reset_code = None
            db.session.commit()
            flash("Password updated! You can now log in.", "success")
            return redirect(url_for('login'))

        flash("Invalid verification code.", "danger")

    return render_template('reset_password.html', email=email)


with app.app_context():
    db.create_all()
    if not Product.query.first():
        db.session.add(Product(
            name="Wireless Mouse",
            price=25.00,
            description="Ergonomic 2.4GHz wireless mouse with adjustable DPI and quiet clicks.",
        ))
        db.session.add(Product(
            name="Mechanical Keyboard",
            price=75.00,
            description="Tactile mechanical keyboard with durable keycaps and USB-C connection.",
        ))
        db.session.add(Product(
            name="HD Monitor",
            price=150.00,
            description="Crisp full-HD display with slim bezels, HDMI/DisplayPort inputs, and eye-care mode.",
        ))
        db.session.commit()


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
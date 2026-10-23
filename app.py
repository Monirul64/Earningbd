import os, secrets
from datetime import datetime, date, timedelta
from decimal import Decimal
from functools import wraps

from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Length, Email, EqualTo, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

app = Flask(__name__)
production = os.environ.get("RENDER") == "true" or os.environ.get("FLASK_ENV") == "production"
secret_key = os.environ.get("SECRET_KEY")
if production and not secret_key:
    raise RuntimeError("Set SECRET_KEY in the deployment environment.")
app.config["SECRET_KEY"] = secret_key or "local-dev-key-change-before-deploy"
csrf = CSRFProtect(app)
db_url = os.environ.get("DATABASE_URL", "sqlite:///project_tasks.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = production
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "এই পেজ দেখতে লগইন করুন।"

PROJECT_DAYS = 60
TASKS_PER_DAY = 5
PROJECT_PACKAGES = {
    "500": Decimal("10.00"),
    "1000": Decimal("20.00"),
    "1500": Decimal("30.00"),
    "2000": Decimal("40.00"),
    "2500": Decimal("60.00"),
    "3000": Decimal("60.00"),
    "4000": Decimal("80.00"),
    "5000": Decimal("140.00"),
    "7500": Decimal("150.00"),
    "10000": Decimal("200.00"),
    "15000": Decimal("300.00"),
    "20000": Decimal("400.00"),
}
PROJECT_PRICE = Decimal("500.00")
DAILY_REWARD = PROJECT_PACKAGES["500"] * TASKS_PER_DAY
WEEKLY_PAYOUT_DAY = os.environ.get("WEEKLY_PAYOUT_DAY", "Sunday")

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reset_token_hash = db.Column(db.String(64), nullable=True, index=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    price = db.Column(db.Numeric(12, 2), nullable=False, default=PROJECT_PRICE)
    status = db.Column(db.String(20), default="pending", nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)
    payment_reference = db.Column(db.String(120), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship("User", backref="purchases")

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_number = db.Column(db.Integer, nullable=False)
    task_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    __table_args__ = (db.UniqueConstraint("day_number", "task_number", name="unique_day_task"),)

class TaskSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchase.id"), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    proof = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    admin_note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship("User")
    purchase = db.relationship("Purchase")
    task = db.relationship("Task")
    __table_args__ = (db.UniqueConstraint("user_id", "purchase_id", "task_id", name="one_task_per_purchase"),)

class Ledger(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    kind = db.Column(db.String(30), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship("User")

class Payout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(20), nullable=False)
    account_number = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    admin_note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    user = db.relationship("User")

class SignupForm(FlaskForm):
    username = StringField("ইউজারনেম", validators=[DataRequired(), Length(min=3, max=40)])
    email = StringField("ইমেইল", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("পাসওয়ার্ড (কমপক্ষে ৮ অক্ষর)", validators=[DataRequired(), Length(min=8, max=128)])
    confirm = PasswordField("পাসওয়ার্ড নিশ্চিত করুন", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("অ্যাকাউন্ট খুলুন")

class LoginForm(FlaskForm):
    identity = StringField("ইউজারনেম বা ইমেইল", validators=[DataRequired()])
    password = PasswordField("পাসওয়ার্ড", validators=[DataRequired()])
    submit = SubmitField("লগইন")

class ForgotForm(FlaskForm):
    email = StringField("অ্যাকাউন্টের ইমেইল", validators=[DataRequired(), Email()])
    submit = SubmitField("রিসেট লিংক তৈরি করুন")

class ResetForm(FlaskForm):
    password = PasswordField("নতুন পাসওয়ার্ড (কমপক্ষে ৮ অক্ষর)", validators=[DataRequired(), Length(min=8, max=128)])
    confirm = PasswordField("নতুন পাসওয়ার্ড নিশ্চিত করুন", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("পাসওয়ার্ড পরিবর্তন করুন")

class PurchaseForm(FlaskForm):
    package_price = SelectField(
        "প্রজেক্ট প্যাকেজ",
        choices=[(price, f"৳{int(price):,} প্যাকেজ") for price in PROJECT_PACKAGES],
        validators=[DataRequired()]
    )
    method = SelectField("পেমেন্ট মাধ্যম", choices=[("bKash","bKash"),("Rocket","Rocket")], validators=[DataRequired()])
    reference = StringField("Transaction ID / রেফারেন্স", validators=[DataRequired(), Length(min=4, max=120)])
    submit = SubmitField("কেনার অনুরোধ দিন")

class ProofForm(FlaskForm):
    proof = TextAreaField("উত্তর দিন", validators=[DataRequired(), Length(min=4, max=2500)])
    submit = SubmitField("কাজ জমা দিন")

class ReviewForm(FlaskForm):
    action = SelectField("সিদ্ধান্ত", choices=[("approve","অনুমোদন"),("reject","বাতিল")], validators=[DataRequired()])
    note = StringField("Admin নোট", validators=[Optional(), Length(max=500)])
    submit = SubmitField("সিদ্ধান্ত সংরক্ষণ")

class PayoutForm(FlaskForm):
    amount = StringField("টাকার পরিমাণ", validators=[DataRequired(), Length(max=20)])
    method = SelectField("মাধ্যম", choices=[("bKash","bKash"),("Rocket","Rocket")], validators=[DataRequired()])
    account_number = StringField("পেমেন্ট নম্বর", validators=[DataRequired(), Length(min=8, max=20)])
    submit = SubmitField("উত্তোলনের অনুরোধ")

class PayoutReviewForm(FlaskForm):
    action = SelectField("সিদ্ধান্ত", choices=[("paid","পেমেন্ট সম্পন্ন"),("reject","বাতিল")], validators=[DataRequired()])
    note = StringField("Admin নোট", validators=[Optional(), Length(max=500)])
    submit = SubmitField("আপডেট")

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def user_balance(user_id):
    total = db.session.query(func.coalesce(func.sum(Ledger.amount), 0)).filter_by(user_id=user_id).scalar()
    return Decimal(str(total or 0))

def active_purchase(user_id):
    now = datetime.utcnow()
    return Purchase.query.filter_by(user_id=user_id, status="active").filter(Purchase.ends_at > now).order_by(Purchase.ends_at.desc()).first()

def active_purchases(user_id):
    now = datetime.utcnow()
    return (Purchase.query.filter_by(user_id=user_id, status="active")
            .filter(Purchase.ends_at > now).order_by(Purchase.starts_at.asc(), Purchase.id.asc()).all())

def pick_purchase(user_id, task=None, requested_id=None):
    purchases = active_purchases(user_id)
    if not purchases:
        return None
    if requested_id:
        for p in purchases:
            if p.id == requested_id:
                return p
        return None
    for p in purchases:
        day = current_day(p)
        if day > PROJECT_DAYS:
            continue
        if task is not None:
            if task.day_number != day:
                continue
            done = TaskSubmission.query.filter_by(user_id=user_id, purchase_id=p.id, task_id=task.id).first()
            if not done:
                return p
        else:
            day_tasks = Task.query.filter_by(day_number=day, is_active=True).all()
            done_ids = {x.task_id for x in TaskSubmission.query.filter_by(user_id=user_id, purchase_id=p.id).all()}
            if any(t.id not in done_ids for t in day_tasks):
                return p
    return purchases[0]

def current_day(purchase):
    if not purchase or not purchase.starts_at:
        return 0
    return max(1, (date.today() - purchase.starts_at.date()).days + 1)

def money(value):
    return f"৳{Decimal(str(value or 0)):,.2f}"
app.jinja_env.filters["money"] = money

def bn(value):
    try:
        text = f"{int(value):,}"
    except (TypeError, ValueError):
        text = str(value)
    return text.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))
app.jinja_env.filters["bn"] = bn
app.jinja_env.globals["current_day"] = current_day

@app.context_processor
def globals_for_templates():
    return {"project_price": PROJECT_PRICE, "project_days": PROJECT_DAYS, "tasks_per_day": TASKS_PER_DAY,
            "daily_reward": DAILY_REWARD, "weekly_payout_day": WEEKLY_PAYOUT_DAY, "today": date.today()}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    form = SignupForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip().lower()
        if User.query.filter(func.lower(User.username) == username.lower()).first() or User.query.filter_by(email=email).first():
            flash("ইউজারনেম বা ইমেইল আগে ব্যবহার হয়েছে।", "error")
        else:
            user = User(username=username, email=email)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash("অ্যাকাউন্ট তৈরি হয়েছে। লগইন করুন।", "success")
            return redirect(url_for("login"))
    return render_template("signup.html", form=form)

@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        identity = form.identity.data.strip()
        user = User.query.filter(func.lower(User.username) == identity.lower()).first()
        if not user:
            user = User.query.filter_by(email=identity.lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for("admin_home" if user.is_admin else "dashboard"))
        flash("লগইন তথ্য সঠিক নয়।", "error")
    return render_template("login.html", form=form)

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("লগআউট হয়েছে।", "success")
    return redirect(url_for("index"))

@app.route("/forgot-password", methods=["GET","POST"])
def forgot_password():
    form = ForgotForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user:
            raw = secrets.token_urlsafe(32)
            user.reset_token_hash = __import__("hashlib").sha256(raw.encode()).hexdigest()
            user.reset_token_expires = datetime.utcnow() + timedelta(minutes=30)
            db.session.commit()
            reset_url = url_for("reset_password", token=raw, _external=True)
            flash("ডেমো রিসেট লিংক: " + reset_url, "success")
        else:
            flash("ইমেইলটি নিবন্ধিত থাকলে রিসেট নির্দেশনা পাওয়া যাবে।", "success")
        return redirect(url_for("forgot_password"))
    return render_template("forgot.html", form=form)

@app.route("/reset-password/<token>", methods=["GET","POST"])
def reset_password(token):
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user = User.query.filter_by(reset_token_hash=token_hash).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        flash("রিসেট লিংকটি ভুল বা মেয়াদ শেষ। নতুন লিংক নিন।", "error")
        return redirect(url_for("forgot_password"))
    form = ResetForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.reset_token_hash = None
        user.reset_token_expires = None
        db.session.commit()
        flash("পাসওয়ার্ড পরিবর্তন হয়েছে। লগইন করুন।", "success")
        return redirect(url_for("login"))
    return render_template("reset.html", form=form)

@app.route("/dashboard")
@login_required
def dashboard():
    purchases = active_purchases(current_user.id)
    purchase = purchases[0] if purchases else None
    
    # Calculate Today's Income
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_income = db.session.query(func.coalesce(func.sum(Ledger.amount), 0))        .filter(Ledger.user_id == current_user.id, Ledger.kind == "task_reward", Ledger.created_at >= today_start).scalar()
    
    # Calculate Total Withdrawals (paid/completed)
    total_withdraw = db.session.query(func.coalesce(func.sum(Payout.amount), 0))        .filter(Payout.user_id == current_user.id, Payout.status == "paid").scalar()
    
    recent = TaskSubmission.query.filter_by(user_id=current_user.id).order_by(TaskSubmission.created_at.desc()).limit(10).all()
    payouts = Payout.query.filter_by(user_id=current_user.id).order_by(Payout.created_at.desc()).all()
    
    return render_template(
        "dashboard.html",
        purchase=purchase,
        purchases=purchases,
        day=current_day(purchase),
        balance=user_balance(current_user.id),
        today_income=Decimal(str(today_income or 0)),
        total_withdraw=Decimal(str(total_withdraw or 0)),
        recent=recent,
        payouts=payouts
    )

@app.route("/buy", methods=["GET","POST"])
@login_required
def buy():
    form = PurchaseForm()
    if form.validate_on_submit():
        selected_price = form.package_price.data
        if selected_price not in PROJECT_PACKAGES:
            flash("সঠিক প্যাকেজ নির্বাচন করুন।", "error")
            return redirect(url_for("buy"))
        purchase = Purchase(user_id=current_user.id, price=Decimal(selected_price), payment_method=form.method.data,
                            payment_reference=form.reference.data.strip(), status="pending")
        db.session.add(purchase)
        db.session.commit()
        flash("কেনার অনুরোধ জমা হয়েছে। Admin পেমেন্ট যাচাই করে অনুমোদন করবেন।", "success")
        return redirect(url_for("dashboard"))
    if request.method == "GET":
        chosen = request.args.get("package", "")
        if chosen in PROJECT_PACKAGES:
            form.package_price.data = chosen
    packages = [
        {
            "price": price,
            "daily": reward * TASKS_PER_DAY,
            "total": reward * TASKS_PER_DAY * PROJECT_DAYS,
        }
        for price, reward in PROJECT_PACKAGES.items()
    ]
    payouts = Payout.query.filter_by(user_id=current_user.id).order_by(Payout.created_at.desc()).limit(5).all()
    return render_template("buy.html", form=form, packages=packages,
                           selected=form.package_price.data or "",
                           balance=user_balance(current_user.id), payouts=payouts)

@app.route("/buy/<price>", methods=["GET", "POST"])
@login_required
def buy_package(price):
    if price not in PROJECT_PACKAGES:
        abort(404)
    form = PurchaseForm()
    form.package_price.data = price
    if form.validate_on_submit():
        purchase = Purchase(user_id=current_user.id, price=Decimal(price), payment_method=form.method.data,
                            payment_reference=form.reference.data.strip(), status="pending")
        db.session.add(purchase)
        db.session.commit()
        flash("কেনার অনুরোধ জমা হয়েছে। Admin পেমেন্ট যাচাই করে অনুমোদন করবেন।", "success")
        return redirect(url_for("dashboard"))
    return render_template("checkout.html", form=form, price=price)

@app.route("/tasks")
@login_required
def tasks():
    purchases = active_purchases(current_user.id)
    purchase = pick_purchase(current_user.id, requested_id=request.args.get("purchase", type=int))
    if not purchase:
        flash("টাস্ক দেখতে আগে প্রজেক্ট কিনে Admin অনুমোদন নিতে হবে।", "error")
        return redirect(url_for("buy"))
    day = current_day(purchase)
    if day > PROJECT_DAYS:
        flash("প্রজেক্টের ১২০ দিনের মেয়াদ শেষ।", "error")
        return redirect(url_for("dashboard"))
    task_list = Task.query.filter_by(day_number=day, is_active=True).order_by(Task.task_number).all()
    submitted = {s.task_id for s in TaskSubmission.query.filter_by(user_id=current_user.id, purchase_id=purchase.id).all()}
    return render_template("tasks.html", purchase=purchase, purchases=purchases, day=day, tasks=task_list, submitted=submitted)

@app.route("/tasks/<int:task_id>/submit", methods=["GET", "POST"])
@login_required
def submit_task(task_id):
    task = Task.query.filter_by(
        id=task_id,
        is_active=True
    ).first_or_404()

    purchase = pick_purchase(current_user.id, task=task, requested_id=request.args.get("purchase", type=int))

    if not purchase:
        abort(403)

    if task.day_number != current_day(purchase):
        abort(403)

    existing = TaskSubmission.query.filter_by(
        user_id=current_user.id,
        purchase_id=purchase.id,
        task_id=task.id
    ).first()

    if existing:
        flash("এই কাজটি ইতিমধ্যে জমা দিয়েছেন।", "error")
        return redirect(url_for("tasks", purchase=purchase.id))

    form = ProofForm()

    if form.validate_on_submit():
        task_reward = PROJECT_PACKAGES.get(
            str(int(purchase.price)),
            Decimal("1.00")
        )

        try:
            submission = TaskSubmission(
                user_id=current_user.id,
                purchase_id=purchase.id,
                task_id=task.id,
                proof=form.proof.data.strip(),
                status="approved",
                reviewed_at=datetime.utcnow(),
                admin_note="Auto approved"
            )

            db.session.add(submission)

            db.session.add(
                Ledger(
                    user_id=current_user.id,
                    amount=task_reward,
                    kind="task_reward",
                    description=f"Auto approved task: {task.title}"
                )
            )

            db.session.commit()

            flash(
                f"কাজ স্বয়ংক্রিয়ভাবে অনুমোদিত হয়েছে। "
                f"পুরস্কার: ৳{task_reward}",
                "success"
            )

            return redirect(url_for("tasks", purchase=purchase.id))

        except Exception:
            db.session.rollback()
            app.logger.exception("Task auto approval failed")
            flash("কাজ জমা দিতে সমস্যা হয়েছে। আবার চেষ্টা করুন।", "error")

    return render_template(
        "submit.html",
        form=form,
        task=task
    )

@app.route("/wallet")
@login_required
def wallet():
    entries = Ledger.query.filter_by(user_id=current_user.id).order_by(Ledger.created_at.desc()).all()
    payouts = Payout.query.filter_by(user_id=current_user.id).order_by(Payout.created_at.desc()).all()
    return render_template("wallet.html", balance=user_balance(current_user.id), entries=entries, payouts=payouts)

@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    form = PayoutForm()
    balance = Decimal(str(user_balance(current_user.id)))

    if date.today().strftime("%A") != WEEKLY_PAYOUT_DAY:
        flash(
            f"উত্তোলনের অনুরোধ নেওয়ার নির্ধারিত দিন "
            f"{WEEKLY_PAYOUT_DAY}।",
            "error"
        )
        return render_template(
            "withdraw.html",
            form=form,
            balance=balance,
            can_request=False
        )

    if form.validate_on_submit():
        try:
            amount = Decimal(str(form.amount.data)).quantize(
                Decimal("0.01")
            )
        except Exception:
            amount = Decimal("0")

        pending = db.session.query(
            func.coalesce(func.sum(Payout.amount), 0)
        ).filter_by(
            user_id=current_user.id,
            status="pending"
        ).scalar()

        available_balance = balance - Decimal(str(pending or 0))

        if amount < Decimal("500.00"):
            flash(
                "সর্বনিম্ন ৫০০ টাকা উত্তোলন করতে পারবেন।",
                "error"
            )

        elif amount > available_balance:
            flash(
                "আপনার পর্যাপ্ত ব্যালেন্স নেই।",
                "error"
            )

        elif amount <= 0:
            flash("টাকার পরিমাণ সঠিক নয়।", "error")

        else:
            payout = Payout(
                user_id=current_user.id,
                amount=amount,
                method=form.method.data,
                account_number=form.account_number.data.strip(),
                status="pending"
            )

            db.session.add(payout)
            db.session.commit()

            flash(
                "উত্তোলনের অনুরোধ জমা হয়েছে। Admin যাচাই করবেন।",
                "success"
            )
            return redirect(url_for("wallet"))

    return render_template(
        "withdraw.html",
        form=form,
        balance=balance,
        can_request=True
    )

@app.route("/admin")
@admin_required
def admin_home():
    return render_template("admin/home.html", pending_purchases=Purchase.query.filter_by(status="pending").count(),
        pending_submissions=TaskSubmission.query.filter_by(status="pending").count(),
        pending_payouts=Payout.query.filter_by(status="pending").count(), users=User.query.filter_by(is_admin=False).count())

@app.route("/admin/users")
@admin_required
def admin_users():
    return render_template("admin/users.html", users=User.query.order_by(User.created_at.desc()).all())

@app.route("/admin/purchases")
@admin_required
def admin_purchases():
    return render_template("admin/purchases.html", purchases=Purchase.query.order_by(Purchase.created_at.desc()).all())

@app.route("/admin/purchases/<int:purchase_id>/<action>", methods=["POST"])
@admin_required
def review_purchase(purchase_id, action):
    purchase = db.session.get(Purchase, purchase_id) or abort(404)
    if purchase.status != "pending" or action not in ("approve","reject"):
        flash("এই অনুরোধ আর পরিবর্তন করা যাবে না।", "error")
    elif action == "approve":
        purchase.status = "active"
        purchase.starts_at = datetime.utcnow()
        purchase.ends_at = purchase.starts_at + timedelta(days=PROJECT_DAYS)
        flash("পেমেন্ট যাচাইয়ের পর প্রজেক্ট সক্রিয় হয়েছে।", "success")
    else:
        purchase.status = "rejected"
        flash("কেনার অনুরোধ বাতিল হয়েছে।", "success")
    db.session.commit()
    return redirect(url_for("admin_purchases"))

@app.route("/admin/tasks", methods=["GET","POST"])
@admin_required
def admin_tasks():
    if request.method == "POST":
        day = request.form.get("day", type=int)
        num = request.form.get("num", type=int)
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not day or day < 1 or day > PROJECT_DAYS or not num or num < 1 or num > TASKS_PER_DAY or not title or not description:
            flash("দিন ১–১২০, টাস্ক ১–৫ এবং সব তথ্য পূরণ করুন।", "error")
        elif Task.query.filter_by(day_number=day, task_number=num).first():
            flash("এই দিনের এই নম্বরের টাস্ক আগে আছে।", "error")
        else:
            db.session.add(Task(day_number=day, task_number=num, title=title, description=description))
            db.session.commit()
            flash("টাস্ক তৈরি হয়েছে।", "success")
        return redirect(url_for("admin_tasks"))
    tasks = Task.query.order_by(Task.day_number, Task.task_number).limit(300).all()
    return render_template("admin/tasks.html", tasks=tasks)

@app.route("/admin/submissions")
@admin_required
def admin_submissions():
    return render_template("admin/submissions.html", submissions=TaskSubmission.query.order_by(TaskSubmission.created_at.desc()).all(), form=ReviewForm())

@app.route("/admin/submissions/<int:sid>/review", methods=["POST"])
@admin_required
def review_submission(sid):
    form = ReviewForm()
    sub = db.session.get(TaskSubmission, sid) or abort(404)
    if not form.validate_on_submit() or sub.status != "pending":
        flash("ফর্ম ভুল অথবা কাজটি আগে যাচাই হয়েছে।", "error")
        return redirect(url_for("admin_submissions"))
    sub.reviewed_at = datetime.utcnow()
    sub.admin_note = (form.note.data or "").strip()
    if form.action.data == "approve":
        sub.status = "approved"
        task_reward = PROJECT_PACKAGES.get(str(int(sub.purchase.price)), Decimal("1.00"))
        db.session.add(Ledger(user_id=sub.user_id, amount=task_reward, kind="task_reward", description=f"Approved task: {sub.task.title}"))
        flash(f"কাজ অনুমোদিত; ৳{task_reward} ব্যালেন্স যোগ হয়েছে।", "success")
    else:
        sub.status = "rejected"
        flash("কাজ বাতিল হয়েছে।", "success")
    db.session.commit()
    return redirect(url_for("admin_submissions"))

@app.route("/admin/payouts")
@admin_required
def admin_payouts():
    return render_template("admin/payouts.html", payouts=Payout.query.order_by(Payout.created_at.desc()).all(), form=PayoutReviewForm())

@app.route("/admin/payouts/<int:pid>/review", methods=["POST"])
@admin_required
def review_payout(pid):
    form = PayoutReviewForm()
    payout = db.session.get(Payout, pid) or abort(404)
    if not form.validate_on_submit() or payout.status != "pending":
        flash("ফর্ম ভুল অথবা অনুরোধটি আগে যাচাই হয়েছে।", "error")
        return redirect(url_for("admin_payouts"))
    payout.admin_note = (form.note.data or "").strip()
    payout.reviewed_at = datetime.utcnow()
    if form.action.data == "paid":
        pending_other = db.session.query(func.coalesce(func.sum(Payout.amount), 0)).filter(
            Payout.user_id == payout.user_id, Payout.status == "pending", Payout.id != payout.id).scalar()
        if payout.amount > user_balance(payout.user_id) - Decimal(str(pending_other or 0)):
            flash("এই উত্তোলনের জন্য ব্যালেন্স যথেষ্ট নয়।", "error")
            return redirect(url_for("admin_payouts"))
        payout.status = "paid"
        db.session.add(Ledger(user_id=payout.user_id, amount=-payout.amount, kind="payout", description=f"Withdrawal paid via {payout.method}"))
        flash("বাইরে থেকে টাকা পাঠানো নিশ্চিত করে পেমেন্ট সম্পন্ন চিহ্নিত করুন।", "success")
    else:
        payout.status = "rejected"
        flash("উত্তোলন বাতিল হয়েছে।", "success")
    db.session.commit()
    return redirect(url_for("admin_payouts"))

@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="এই পেজ দেখার অনুমতি নেই।"), 403
@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="পেজটি পাওয়া যায়নি।"), 404

def init_db():
    db.create_all()
    admin_name = os.environ.get("ADMIN_USER", "admin").strip()
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if production and not admin_password:
        raise RuntimeError("Set ADMIN_PASSWORD in production.")

    if not admin_password:
        admin_password = "ChangeThisAdmin123!"
        print("LOCAL DEVELOPMENT ADMIN: admin / ChangeThisAdmin123!")

    admin = User.query.filter(
        func.lower(User.username) == admin_name.lower()
    ).first()

    if not admin:
        admin = User(
            username=admin_name,
            email="admin@localhost.invalid",
            is_admin=True
        )
        db.session.add(admin)

    admin.is_admin = True
    admin.set_password(admin_password)

    db.session.commit()

with app.app_context():
    init_db()

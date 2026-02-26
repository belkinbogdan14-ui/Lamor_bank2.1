from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "lamor_key_2026"
app.config['SESSION_PERMANENT'] = True 

basedir = os.path.abspath(os.path.dirname(__file__))
# Изменили на bank_v3.db для сброса структуры на Render
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'bank_v3.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- МОДЕЛИ ДАННЫХ ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login_id = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    accounts = db.relationship('Account', backref='owner', lazy=True)

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Float, default=1000.0) 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    price = db.Column(db.Float)
    seller = db.Column(db.String(100))
    contact = db.Column(db.String(100))
    seller_id = db.Column(db.Integer)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(500))
    user_id = db.Column(db.Integer, nullable=True) # None = для всех, ID = личное
    date = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

def get_current_data():
    if 'user_id' not in session: return None, None
    u = db.session.get(User, session['user_id'])
    if not u: return None, None
    acc = Account.query.filter_by(user_id=u.id).first()
    return u, acc

# --- РОУТЫ ---

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/home')
def home():
    u, acc = get_current_data()
    if not u: return redirect(url_for('login'))
    
    # Фильтр уведомлений: личные + глобальные
    notes = Notification.query.filter(
        (Notification.user_id == None) | (Notification.user_id == u.id)
    ).order_by(Notification.date.desc()).all()
    
    return render_template('home.html', user=u, balance=acc.balance, notifications=notes, is_admin=u.is_admin)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(login_id=request.form.get('login_id'), password=request.form.get('password')).first()
        if u:
            session.clear()
            session['user_id'] = u.id
            return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        l_id = request.form.get('login_id')
        name = request.form.get('name')
        pwd = request.form.get('password')
        if not User.query.filter_by(login_id=l_id).first():
            is_first = (User.query.count() == 0)
            u = User(login_id=l_id, name=name, password=pwd, is_admin=is_first)
            db.session.add(u)
            db.session.commit()
            db.session.add(Account(user_id=u.id))
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/payments', methods=['GET', 'POST'])
def payments():
    u, acc = get_current_data()
    if not u: return redirect(url_for('login'))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'sell':
            db.session.add(Product(title=request.form.get('title'), price=float(request.form.get('price')), 
                                   seller=u.name, contact=request.form.get('contact'), seller_id=u.id))
        elif action == 'buy':
            p = db.session.get(Product, request.form.get('product_id'))
            if p and acc.balance >= p.price:
                s_acc = Account.query.filter_by(user_id=p.seller_id).first()
                acc.balance -= p.price
                if s_acc: 
                    s_acc.balance += p.price
                    db.session.add(Notification(
                        message=f"Товар '{p.title}' продан! +{p.price} ГМР от {u.name}",
                        user_id=p.seller_id
                    ))
                db.session.delete(p)
        db.session.commit()
        return redirect(url_for('payments'))
    return render_template('payments.html', products=Product.query.all(), is_admin=u.is_admin, balance=acc.balance)

@app.route('/transfers', methods=['GET', 'POST'])
def transfers():
    u, acc = get_current_data()
    if not u: return redirect(url_for('login'))
    if request.method == 'POST':
        target_id = int(request.form.get('target_id'))
        amount = float(request.form.get('amount', 0))
        target_acc = Account.query.filter_by(user_id=target_id).first()
        if target_acc and acc.balance >= amount and amount > 0:
            acc.balance -= amount
            target_acc.balance += amount
            db.session.add(Notification(
                message=f"Перевод: {u.name} прислал вам {amount} ГМР",
                user_id=target_id
            ))
            db.session.commit()
            return redirect(url_for('transfers'))
    users = User.query.filter(User.id != u.id).all()
    return render_template('transfers.html', users=users, balance=acc.balance, is_admin=u.is_admin)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    u, acc = get_current_data()
    if not u or not u.is_admin: return "403 Access Denied", 403
    if request.method == 'POST':
        act = request.form.get('action')
        if act == 'post_news':
            db.session.add(Notification(message=request.form.get('news_text'), user_id=None))
        elif act == 'add_money':
            t_acc = Account.query.filter_by(user_id=request.form.get('user_id')).first()
            if t_acc: t_acc.balance += float(request.form.get('amount', 0))
        elif act == 'make_admin':
            t_user = db.session.get(User, request.form.get('user_id'))
            if t_user: t_user.is_admin = True
        db.session.commit()
        return redirect(url_for('admin'))
    return render_template('admin.html', users=User.query.all(), is_admin=True)

@app.route('/accounts')
def accounts():
    u, acc = get_current_data()
    if not u: return redirect(url_for('login'))
    return render_template('accounts.html', balance=acc.balance, is_admin=u.is_admin, user=u)

@app.route('/bonuses')
def bonuses():
    u, _ = get_current_data()
    if not u: return redirect(url_for('login'))
    return render_template('bonuses.html', is_admin=u.is_admin)

@app.route('/analytics')
def analytics():
    u, _ = get_current_data()
    if not u: return redirect(url_for('login'))
    return render_template('analytics.html', is_admin=u.is_admin)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
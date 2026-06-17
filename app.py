from flask import Flask, render_template, redirect, url_for, request
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import os

app = Flask(__name__)
import os
print("Current directory:", os.getcwd())
print("Templates exists:", os.path.exists('templates'))
if os.path.exists('templates'):
    print("Files in templates:", os.listdir('templates'))
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    name = db.Column(db.String(100))
    password_hash = db.Column(db.String(200))
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    picture = db.Column(db.String(200), default='')
    login_type = db.Column(db.String(20))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_name = db.Column(db.String(100))
    text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def index():
    messages = Message.query.order_by(Message.timestamp.desc()).limit(50).all()
    messages.reverse()
    return render_template('index.html', messages=messages, user=current_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        return 'Invalid email or password'
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        
        if User.query.filter_by(email=email).first():
            return 'Email already exists'
        
        user = User(
            email=email,
            name=name,
            password_hash=generate_password_hash(password),
            login_type='email'
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/google')
def google_login():
    redirect_uri = url_for('google_callback', _external=True, _scheme='https')
    return google.authorize_redirect(redirect_uri)

@app.route('/callback')
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    
    if not user_info:
        return 'Failed to get user info from Google'
    
    user = User.query.filter_by(google_id=user_info.get('sub')).first()
    if not user:
        user = User.query.filter_by(email=user_info.get('email')).first()
    
    if not user:
        user = User(
            google_id=user_info.get('sub'),
            email=user_info.get('email'),
            name=user_info.get('name'),
            picture=user_info.get('picture', ''),
            login_type='google'
        )
        db.session.add(user)
        db.session.commit()
    
    login_user(user)
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin():
    if current_user.email != 'your-email@example.com':
        return 'Not authorized'
    
    users = User.query.all()
    output = '<h2>Users</h2><table border="1"><tr><th>Name</th><th>Email</th><th>Login Type</th></tr>'
    for u in users:
        output += f'<tr><td>{u.name}</td><td>{u.email}</td><td>{u.login_type}</td></tr>'
    output += '</table>'
    return output

@socketio.on('message')
def handle_message(data):
    if current_user.is_authenticated:
        msg = Message(user_id=current_user.id, user_name=current_user.name, text=data)
        db.session.add(msg)
        db.session.commit()
        emit('message', {'name': current_user.name, 'text': data, 'time': msg.timestamp.strftime('%H:%M')}, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)

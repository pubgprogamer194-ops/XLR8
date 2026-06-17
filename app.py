from flask import Flask, render_template_string, redirect, url_for, request
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import os

app = Flask(__name__)
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
    return render_template_string(HTML, messages=messages, user=current_user)

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
    
    return LOGIN_HTML

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
    
    return REGISTER_HTML

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

LOGIN_HTML = '''<!DOCTYPE html>
<html>
<head>
    <title>XLR8 - Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #000000;
            color: #ffffff;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            width: 100%;
            max-width: 400px;
            padding: 40px;
        }
        .logo {
            font-size: 28px;
            font-weight: 700;
            letter-spacing: 3px;
            text-align: center;
            margin-bottom: 8px;
        }
        .subtitle {
            color: #666666;
            text-align: center;
            font-size: 14px;
            margin-bottom: 40px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        input {
            width: 100%;
            padding: 14px 16px;
            background: #111111;
            border: 1px solid #222222;
            border-radius: 12px;
            color: #ffffff;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }
        input:focus {
            border-color: #444444;
        }
        input::placeholder {
            color: #555555;
        }
        button[type="submit"] {
            width: 100%;
            padding: 14px;
            background: #ffffff;
            color: #000000;
            border: none;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            margin-top: 10px;
        }
        button[type="submit"]:hover {
            background: #dddddd;
        }
        .divider {
            display: flex;
            align-items: center;
            margin: 30px 0;
            color: #555555;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .divider::before, .divider::after {
            content: '';
            flex: 1;
            height: 1px;
            background: #222222;
        }
        .divider::before { margin-right: 16px; }
        .divider::after { margin-left: 16px; }
        .google-btn {
            width: 100%;
            padding: 14px;
            background: #111111;
            color: #ffffff;
            border: 1px solid #222222;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        .google-btn:hover {
            background: #1a1a1a;
            border-color: #333333;
        }
        .google-icon {
            width: 18px;
            height: 18px;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #666666;
            font-size: 14px;
        }
        .footer a {
            color: #ffffff;
            text-decoration: none;
            font-weight: 500;
        }
        .footer a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">XLR8</div>
        <div class="subtitle">Welcome back</div>
        
        <form method="POST">
            <div class="form-group">
                <input type="email" name="email" placeholder="Email" required>
            </div>
            <div class="form-group">
                <input type="password" name="password" placeholder="Password" required>
            </div>
            <button type="submit">Sign In</button>
        </form>
        
        <div class="divider">or</div>
        
        <a href="/google" class="google-btn">
            <svg class="google-icon" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
        </a>
        
        <div class="footer">
            No account? <a href="/register">Create one</a>
        </div>
    </div>
</body>
</html>'''

REGISTER_HTML = '''<!DOCTYPE html>
<html>
<head>
    <title>XLR8 - Register</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #000000;
            color: #ffffff;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            width: 100%;
            max-width: 400px;
            padding: 40px;
        }
        .logo {
            font-size: 28px;
            font-weight: 700;
            letter-spacing: 3px;
            text-align: center;
            margin-bottom: 8px;
        }
        .subtitle {
            color: #666666;
            text-align: center;
            font-size: 14px;
            margin-bottom: 40px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        input {
            width: 100%;
            padding: 14px 16px;
            background: #111111;
            border: 1px solid #222222;
            border-radius: 12px;
            color: #ffffff;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }
        input:focus {
            border-color: #444444;
        }
        input::placeholder {
            color: #555555;
        }
        button[type="submit"] {
            width: 100%;
            padding: 14px;
            background: #ffffff;
            color: #000000;
            border: none;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            margin-top: 10px;
        }
        button[type="submit"]:hover {
            background: #dddddd;
        }
        .divider {
            display: flex;
            align-items: center;
            margin: 30px 0;
            color: #555555;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .divider::before, .divider::after {
            content: '';
            flex: 1;
            height: 1px;
            background: #222222;
        }
        .divider::before { margin-right: 16px; }
        .divider::after { margin-left: 16px; }
        .google-btn {
            width: 100%;
            padding: 14px;
            background: #111111;
            color: #ffffff;
            border: 1px solid #222222;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        .google-btn:hover {
            background: #1a1a1a;
            border-color: #333333;
        }
        .google-icon {
            width: 18px;
            height: 18px;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #666666;
            font-size: 14px;
        }
        .footer a {
            color: #ffffff;
            text-decoration: none;
            font-weight: 500;
        }
        .footer a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">XLR8</div>
        <div class="subtitle">Create your account</div>
        
        <form method="POST">
            <div class="form-group">
                <input type="text" name="name" placeholder="Your Name" required>
            </div>
            <div class="form-group">
                <input type="email" name="email" placeholder="Email" required>
            </div>
            <div class="form-group">
                <input type="password" name="password" placeholder="Password" required>
            </div>
            <button type="submit">Create Account</button>
        </form>
        
        <div class="divider">or</div>
        
        <a href="/google" class="google-btn">
            <svg class="google-icon" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Sign up with Google
        </a>
        
        <div class="footer">
            Already have an account? <a href="/login">Sign in</a>
        </div>
    </div>
</body>
</html>'''

HTML = '''<!DOCTYPE html>
<html>
<head>
    <title>XLR8</title>
    <style>
        :root {
            --bg: #000000; --text: #ffffff; --card: #111111; --border: #1a1a1a;
            --input-bg: #111111; --input-border: #222222; --placeholder: #555555;
            --button-bg: #ffffff; --button-text: #000000; --button-hover: #dddddd;
            --nick-color: #888888; --status: #666666;
        }
        [data-theme="light"] {
            --bg: #ffffff; --text: #000000; --card: #f5f5f5; --border: #e0e0e0;
            --input-bg: #f5f5f5; --input-border: #e0e0e0; --placeholder: #999999;
            --button-bg: #000000; --button-text: #ffffff; --button-hover: #333333;
            --nick-color: #666666; --status: #999999;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg); color: var(--text); height: 100vh;
            display: flex; flex-direction: column; transition: background 0.3s, color 0.3s;
        }
        .header {
            padding: 20px 30px; border-bottom: 1px solid var(--border);
            display: flex; align-items: center; justify-content: space-between;
        }
        .logo { font-size: 20px; font-weight: 600; letter-spacing: 2px; color: var(--text); }
        .user-info { display: flex; align-items: center; gap: 10px; }
        .user-info img { width: 32px; height: 32px; border-radius: 50%; }
        #messages {
            flex: 1; overflow-y: auto; padding: 30px;
            display: flex; flex-direction: column; gap: 12px;
        }
        .message {
            max-width: 70%; padding: 14px 18px; background: var(--card);
            border: 1px solid var(--border); border-radius: 12px;
            line-height: 1.5; font-size: 14px;
        }
        .message .nick {
            font-size: 12px; font-weight: 600; color: var(--nick-color);
            margin-bottom: 4px; text-transform: uppercase; letter-spacing: 1px;
        }
        .message .text { color: var(--text); }
        .input-area {
            padding: 20px 30px; border-top: 1px solid var(--border);
            display: flex; gap: 12px; align-items: center;
        }
        #msgInput {
            flex: 1; padding: 12px 16px; background: var(--input-bg);
            border: 1px solid var(--input-border); border-radius: 10px;
            color: var(--text); font-size: 14px; outline: none;
        }
        button {
            padding: 12px 24px; background: var(--button-bg); color: var(--button-text);
            border: none; border-radius: 10px; font-size: 14px; font-weight: 600;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">XLR8</div>
        <div class="user-info">
            {% if user.picture %}<<img src="{{ user.picture }}">{% endif %}
            <span>{{ user.name }}</span>
            <a href="/logout" style="color: var(--text);">Logout</a>
        </div>
    </div>
    <div id="messages">
        {% for msg in messages %}
        <div class="message">
            <div class="nick">{{ msg.user_name }} · {{ msg.timestamp.strftime('%H:%M') }}</div>
            <div class="text">{{ msg.text }}</div>
        </div>
        {% endfor %}
    </div>
    <div class="input-area">
        <input type="text" id="msgInput" placeholder="Type a message..." autocomplete="off">
        <button onclick="sendMessage()">Send</button>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        var socket = io();
        socket.on('message', function(data) {
            var div = document.createElement('div');
            div.className = 'message';
            div.innerHTML = '<div class="nick">' + data.name + ' · ' + data.time + '</div><div class="text">' + data.text + '</div>';
            document.getElementById('messages').appendChild(div);
            document.getElementById('messages').scrollTop = 999999;
        });
        function sendMessage() {
            var msg = document.getElementById('msgInput').value.trim();
            if (msg) { socket.emit('message', msg); document.getElementById('msgInput').value = ''; }
        }
        document.getElementById('msgInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') sendMessage();
        });
    </script>
</body>
</html>'''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)

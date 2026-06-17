from flask import Flask, render_template_string, redirect, url_for, session
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id='YOUR_GOOGLE_CLIENT_ID',
    client_secret='YOUR_GOOGLE_CLIENT_SECRET',
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
    client_kwargs={'scope': 'openid email profile'},
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(100))
    name = db.Column(db.String(100))
    picture = db.Column(db.String(200))

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
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    # Load last 50 messages
    messages = Message.query.order_by(Message.timestamp.desc()).limit(50).all()
    messages.reverse()
    
    return render_template_string(HTML, messages=messages, user=current_user)

@app.route('/login')
def login():
    return '<a href="/google">Login with Google</a>'

@app.route('/google')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/callback')
def google_callback():
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()
    
    user = User.query.filter_by(google_id=user_info['id']).first()
    if not user:
        user = User(
            google_id=user_info['id'],
            email=user_info['email'],
            name=user_info['name'],
            picture=user_info.get('picture', '')
        )
        db.session.add(user)
        db.session.commit()
    
    login_user(user)
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@socketio.on('message')
def handle_message(data):
    if current_user.is_authenticated:
        msg = Message(user_id=current_user.id, user_name=current_user.name, text=data)
        db.session.add(msg)
        db.session.commit()
        emit('message', {'name': current_user.name, 'text': data, 'time': msg.timestamp.strftime('%H:%M')}, broadcast=True)

HTML = '''<!DOCTYPE html>
<html>
<head>
    <title>XLR8</title>
    <style>
        /* ... your existing styles ... */
        .login-btn { padding: 10px 20px; background: #fff; color: #000; border-radius: 5px; text-decoration: none; }
        .user-info { display: flex; align-items: center; gap: 10px; }
        .user-info img { width: 32px; height: 32px; border-radius: 50%; }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">XLR8</div>
        <div class="user-info">
            <img src="{{ user.picture }}">
            <span>{{ user.name }}</span>
            <a href="/logout" style="color: #fff;">Logout</a>
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

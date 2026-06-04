import os
import uuid
import sqlite3
import psycopg2
import psycopg2.extras
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
SQLITE_PATH = os.environ.get('SQLITE_PATH', os.path.join(BASE_DIR, 'data', 'messages.db'))
TIMEZONE = ZoneInfo(os.environ.get('APP_TIMEZONE', 'Europe/Istanbul'))

IS_PRODUCTION = bool(
    os.environ.get('RAILWAY_ENVIRONMENT')
    or os.environ.get('RAILWAY_PROJECT_ID')
    or os.environ.get('PRODUCTION') == '1'
)

SECRET_KEY = os.environ.get('SECRET_KEY')
if IS_PRODUCTION and not SECRET_KEY:
    raise RuntimeError('SECRET_KEY production ortamında zorunludur.')

USER1_CODE = os.environ.get('USER1_CODE')
USER2_CODE = os.environ.get('USER2_CODE')
USER1_NAME = os.environ.get('USER1_NAME', 'Özgür')
USER2_NAME = os.environ.get('USER2_NAME', 'Kişi 2')

if IS_PRODUCTION and (not USER1_CODE or not USER2_CODE):
    raise RuntimeError('USER1_CODE ve USER2_CODE production ortamında zorunludur.')

# Sadece yerel geliştirme kolaylığı için varsayılan kodlar kullanılır.
USER1_CODE = USER1_CODE or 'KARA-001'
USER2_CODE = USER2_CODE or 'KARA-002'

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY or 'local-dev-secret-change-me'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

limiter = Limiter(get_remote_address, app=app, default_limits=[])

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'pdf'}
ALLOWED_MIME_TYPES = {
    'image/png',
    'image/jpeg',
    'image/gif',
    'image/webp',
    'video/mp4',
    'application/pdf',
}

ROOM = 'private_room'
socketio = SocketIO(app, cors_allowed_origins=[], async_mode='eventlet')
online_users = {}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)

# ── DATABASE ─────────────────────────────────────────────────────────────────

def using_postgres():
    return bool(os.environ.get('DATABASE_URL'))


def get_db():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        return psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    try:
        with conn:
            if using_postgres():
                with conn.cursor() as cur:
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS messages (
                            id          TEXT PRIMARY KEY,
                            user_id     TEXT NOT NULL,
                            user_name   TEXT NOT NULL,
                            type        TEXT NOT NULL DEFAULT 'text',
                            text        TEXT,
                            file_url    TEXT,
                            file_name   TEXT,
                            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
                        )
                    ''')
            else:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS messages (
                        id          TEXT PRIMARY KEY,
                        user_id     TEXT NOT NULL,
                        user_name   TEXT NOT NULL,
                        type        TEXT NOT NULL DEFAULT 'text',
                        text        TEXT,
                        file_url    TEXT,
                        file_name   TEXT,
                        created_at  TEXT NOT NULL
                    )
                ''')
    finally:
        conn.close()


def save_message(msg):
    conn = get_db()
    created_at = datetime.now(TIMEZONE)
    try:
        if using_postgres():
            with conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        INSERT INTO messages (id, user_id, user_name, type, text, file_url, file_name, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        msg['id'],
                        msg['user']['id'],
                        msg['user']['name'],
                        msg['type'],
                        msg.get('text', ''),
                        msg.get('file_url', ''),
                        msg.get('file_name', ''),
                        created_at.replace(tzinfo=None),
                    ))
        else:
            with conn:
                conn.execute('''
                    INSERT INTO messages (id, user_id, user_name, type, text, file_url, file_name, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    msg['id'],
                    msg['user']['id'],
                    msg['user']['name'],
                    msg['type'],
                    msg.get('text', ''),
                    msg.get('file_url', ''),
                    msg.get('file_name', ''),
                    created_at.isoformat(),
                ))
    finally:
        conn.close()


def parse_created_at(value):
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return datetime.now(TIMEZONE)


def load_messages(limit=200):
    conn = get_db()
    try:
        if using_postgres():
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT * FROM (
                        SELECT * FROM messages ORDER BY created_at DESC LIMIT %s
                    ) sub ORDER BY created_at ASC
                ''', (limit,))
                rows = cur.fetchall()
        else:
            rows = conn.execute('''
                SELECT * FROM (
                    SELECT * FROM messages ORDER BY created_at DESC LIMIT ?
                ) sub ORDER BY created_at ASC
            ''', (limit,)).fetchall()

        result = []
        for r in rows:
            created_at = parse_created_at(r['created_at'])
            result.append({
                'id': r['id'],
                'user': {'id': r['user_id'], 'name': r['user_name']},
                'type': r['type'],
                'text': r['text'] or '',
                'file_url': r['file_url'] or '',
                'file_name': r['file_name'] or '',
                'timestamp': created_at.strftime('%H:%M'),
                'date_label': created_at.strftime('%d.%m.%Y'),
            })
        return result
    finally:
        conn.close()


try:
    init_db()
except Exception as e:
    print(f'DB init warning: {e}')

# ── HELPERS ──────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_mime(file):
    return file.mimetype in ALLOWED_MIME_TYPES


def validate_code(code):
    code = (code or '').strip().upper()
    if code == USER1_CODE.upper():
        return {'id': 'user1', 'name': USER1_NAME}
    if code == USER2_CODE.upper():
        return {'id': 'user2', 'name': USER2_NAME}
    return None

# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('chat'))
    return render_template('login.html')


@app.route('/login', methods=['POST'])
@limiter.limit('5 per minute')
def login():
    user = validate_code(request.form.get('code', ''))
    if user:
        session.clear()
        session['user'] = user
        return redirect(url_for('chat'))
    return render_template('login.html', error='Geçersiz kod'), 401


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))


@app.route('/chat')
def chat():
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('chat.html', user=session['user'])


@app.route('/api/messages')
def api_messages():
    if 'user' not in session:
        return jsonify({'error': 'Yetkisiz'}), 401
    msgs = load_messages(200)
    return jsonify(msgs)


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'user' not in session:
        return jsonify({'error': 'Yetkisiz'}), 401
    if 'file' not in request.files:
        return jsonify({'error': 'Dosya yok'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Dosya seçilmedi'}), 400

    if not allowed_file(file.filename) or not allowed_mime(file):
        return jsonify({'error': 'İzin verilmeyen dosya türü'}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f'{uuid.uuid4().hex}.{ext}'
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return jsonify({'url': f'/static/uploads/{filename}', 'name': file.filename})

# ── SOCKETIO ─────────────────────────────────────────────────────────────────

@socketio.on('join')
def on_join(data):
    if 'user' not in session:
        return
    user = session['user']
    join_room(ROOM)
    online_users[request.sid] = user
    emit('user_status', {
        'user': user,
        'online': list(online_users.values()),
        'event': 'joined'
    }, room=ROOM)


@socketio.on('disconnect')
def on_disconnect():
    if request.sid in online_users:
        user = online_users.pop(request.sid)
        leave_room(ROOM)
        emit('user_status', {
            'user': user,
            'online': list(online_users.values()),
            'event': 'left'
        }, room=ROOM)


@socketio.on('message')
def on_message(data):
    if 'user' not in session:
        return

    msg_type = data.get('type', 'text')
    if msg_type not in {'text', 'image', 'file'}:
        return

    user = session['user']
    now = datetime.now(TIMEZONE)
    msg = {
        'id': uuid.uuid4().hex,
        'user': user,
        'text': (data.get('text', '') or '')[:4000],
        'type': msg_type,
        'file_url': data.get('file_url', ''),
        'file_name': data.get('file_name', ''),
        'timestamp': now.strftime('%H:%M'),
        'date_label': now.strftime('%d.%m.%Y'),
    }

    try:
        save_message(msg)
    except Exception as e:
        print(f'Save message error: {e}')

    emit('message', msg, room=ROOM)


@socketio.on('typing')
def on_typing(data):
    if 'user' not in session:
        return
    emit('typing', {'user': session['user'], 'typing': bool(data.get('typing', False))}, room=ROOM, include_self=False)


@socketio.on('webrtc_offer')
def on_offer(data):
    if 'user' not in session:
        return
    emit('webrtc_offer', {**data, 'from': session.get('user', {})}, room=ROOM, include_self=False)


@socketio.on('webrtc_answer')
def on_answer(data):
    if 'user' not in session:
        return
    emit('webrtc_answer', {**data, 'from': session.get('user', {})}, room=ROOM, include_self=False)


@socketio.on('webrtc_ice')
def on_ice(data):
    if 'user' not in session:
        return
    emit('webrtc_ice', data, room=ROOM, include_self=False)


@socketio.on('call_request')
def on_call_request(data):
    if 'user' not in session:
        return
    emit('call_request', {**data, 'from': session.get('user', {})}, room=ROOM, include_self=False)


@socketio.on('call_response')
def on_call_response(data):
    if 'user' not in session:
        return
    emit('call_response', data, room=ROOM, include_self=False)


@socketio.on('call_end')
def on_call_end(data):
    if 'user' not in session:
        return
    emit('call_end', data or {}, room=ROOM, include_self=False)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=not IS_PRODUCTION)

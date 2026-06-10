import os
import uuid
import sqlite3
import imghdr
import psycopg2
import psycopg2.extras
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_from_directory, abort
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
SQLITE_PATH = os.environ.get('SQLITE_PATH', os.path.join(BASE_DIR, 'data', 'messages.db'))
TIMEZONE = ZoneInfo(os.environ.get('APP_TIMEZONE', 'Europe/Istanbul'))

IS_PRODUCTION = bool(os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RAILWAY_PROJECT_ID') or os.environ.get('PRODUCTION') == '1')
SECRET_KEY = os.environ.get('SECRET_KEY')
if IS_PRODUCTION and not SECRET_KEY:
    raise RuntimeError('SECRET_KEY production ortamında zorunludur.')

USER1_CODE = os.environ.get('USER1_CODE')
USER2_CODE = os.environ.get('USER2_CODE')
USER1_NAME = os.environ.get('USER1_NAME', 'Özgür')
USER2_NAME = os.environ.get('USER2_NAME', 'Kişi 2')
if IS_PRODUCTION and (not USER1_CODE or not USER2_CODE):
    raise RuntimeError('USER1_CODE ve USER2_CODE production ortamında zorunludur.')
USER1_CODE = USER1_CODE or 'KARA-001'
USER2_CODE = USER2_CODE or 'KARA-002'

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY or 'local-dev-secret-change-me'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
    SESSION_COOKIE_SAMESITE='Lax',
)
limiter = Limiter(get_remote_address, app=app, default_limits=[])

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
VIDEO_EXTENSIONS = {'mp4', 'webm', 'mov'}
DOC_EXTENSIONS = {'pdf'}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | DOC_EXTENSIONS
IMAGE_MIME_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
VIDEO_MIME_TYPES = {'video/mp4', 'video/webm', 'video/quicktime'}
DOC_MIME_TYPES = {'application/pdf'}
ALLOWED_MIME_TYPES = IMAGE_MIME_TYPES | VIDEO_MIME_TYPES | DOC_MIME_TYPES

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


def add_column_if_missing(conn, column_name, column_def):
    try:
        if using_postgres():
            with conn.cursor() as cur:
                cur.execute(f'ALTER TABLE messages ADD COLUMN IF NOT EXISTS {column_name} {column_def}')
        else:
            cols = conn.execute('PRAGMA table_info(messages)').fetchall()
            if column_name not in [c['name'] for c in cols]:
                conn.execute(f'ALTER TABLE messages ADD COLUMN {column_name} {column_def}')
    except Exception as e:
        print(f'Migration warning for {column_name}: {e}')


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
                            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
                            read_at     TIMESTAMP
                        )
                    ''')
                add_column_if_missing(conn, 'read_at', 'TIMESTAMP')
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
                        created_at  TEXT NOT NULL,
                        read_at     TEXT
                    )
                ''')
                add_column_if_missing(conn, 'read_at', 'TEXT')
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
                        INSERT INTO messages (id, user_id, user_name, type, text, file_url, file_name, created_at, read_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL)
                    ''', (msg['id'], msg['user']['id'], msg['user']['name'], msg['type'], msg.get('text', ''), msg.get('file_url', ''), msg.get('file_name', ''), created_at.replace(tzinfo=None)))
        else:
            with conn:
                conn.execute('''
                    INSERT INTO messages (id, user_id, user_name, type, text, file_url, file_name, created_at, read_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ''', (msg['id'], msg['user']['id'], msg['user']['name'], msg['type'], msg.get('text', ''), msg.get('file_url', ''), msg.get('file_name', ''), created_at.isoformat()))
    finally:
        conn.close()


def parse_created_at(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def row_get(row, key, default=None):
    try:
        return row[key]
    except Exception:
        return default


def load_messages(limit=200):
    conn = get_db()
    try:
        if using_postgres():
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT * FROM (SELECT * FROM messages ORDER BY created_at DESC LIMIT %s) sub ORDER BY created_at ASC
                ''', (limit,))
                rows = cur.fetchall()
        else:
            rows = conn.execute('''
                SELECT * FROM (SELECT * FROM messages ORDER BY created_at DESC LIMIT ?) sub ORDER BY created_at ASC
            ''', (limit,)).fetchall()
        result = []
        for r in rows:
            created_at = parse_created_at(r['created_at']) or datetime.now(TIMEZONE)
            read_at = parse_created_at(row_get(r, 'read_at'))
            result.append({
                'id': r['id'],
                'user': {'id': r['user_id'], 'name': r['user_name']},
                'type': r['type'],
                'text': r['text'] or '',
                'file_url': r['file_url'] or '',
                'file_name': r['file_name'] or '',
                'timestamp': created_at.strftime('%H:%M'),
                'date_label': created_at.strftime('%d.%m.%Y'),
                'read': bool(read_at),
                'read_at': read_at.strftime('%H:%M') if read_at else '',
            })
        return result
    finally:
        conn.close()


def mark_messages_read(message_ids, reader_id):
    if not message_ids:
        return []
    clean_ids = [str(x) for x in message_ids if x]
    if not clean_ids:
        return []
    now = datetime.now(TIMEZONE)
    conn = get_db()
    try:
        if using_postgres():
            with conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        UPDATE messages
                           SET read_at = COALESCE(read_at, %s)
                         WHERE id = ANY(%s) AND user_id <> %s
                     RETURNING id
                    ''', (now.replace(tzinfo=None), clean_ids, reader_id))
                    rows = cur.fetchall()
                    return [r['id'] for r in rows]
        with conn:
            placeholders = ','.join(['?'] * len(clean_ids))
            conn.execute(f'''
                UPDATE messages
                   SET read_at = COALESCE(read_at, ?)
                 WHERE id IN ({placeholders}) AND user_id <> ?
            ''', [now.isoformat(), *clean_ids, reader_id])
            rows = conn.execute(f'''
                SELECT id FROM messages
                 WHERE id IN ({placeholders}) AND user_id <> ? AND read_at IS NOT NULL
            ''', [*clean_ids, reader_id]).fetchall()
            return [r['id'] for r in rows]
    finally:
        conn.close()

try:
    init_db()
except Exception as e:
    print(f'DB init warning: {e}')

# ── HELPERS ──────────────────────────────────────────────────────────────────

def file_extension(filename):
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def allowed_file(filename):
    return file_extension(filename) in ALLOWED_EXTENSIONS


def allowed_mime(file):
    return file.mimetype in ALLOWED_MIME_TYPES


def allowed_photo(file):
    return file_extension(file.filename) in IMAGE_EXTENSIONS and file.mimetype in IMAGE_MIME_TYPES


def is_valid_upload_signature(file, ext):
    head = file.stream.read(512)
    file.stream.seek(0)
    ext = ext.lower()
    if ext in {'jpg', 'jpeg', 'png', 'gif', 'webp'}:
        detected = imghdr.what(None, head)
        if ext in {'jpg', 'jpeg'}:
            return detected == 'jpeg'
        return detected == ext
    if ext == 'pdf':
        return head.startswith(b'%PDF')
    if ext == 'mp4':
        return b'ftyp' in head[:64]
    if ext == 'webm':
        return head.startswith(b'\x1a\x45\xdf\xa3')
    if ext == 'mov':
        return b'ftyp' in head[:64]
    return False


def save_uploaded_file(file):
    ext = file_extension(file.filename) or 'jpg'
    filename = f'{uuid.uuid4().hex}.{ext}'
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return {'url': f'/media/{filename}', 'name': file.filename or filename}


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
    return jsonify(load_messages(200))

@app.route('/media/<path:filename>')
def media(filename):
    if 'user' not in session:
        abort(401)
    if '/' in filename or '\\' in filename or '..' in filename:
        abort(404)
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)

@app.route('/upload/photo', methods=['POST'])
@limiter.limit('20 per minute')
def upload_photo():
    if 'user' not in session:
        return jsonify({'error': 'Yetkisiz'}), 401
    if 'photo' not in request.files:
        return jsonify({'error': 'Fotoğraf yok'}), 400
    photo = request.files['photo']
    if photo.filename == '':
        photo.filename = 'camera.jpg'
    ext = file_extension(photo.filename)
    if not allowed_photo(photo) or not is_valid_upload_signature(photo, ext):
        return jsonify({'error': 'Sadece geçerli PNG, JPG, JPEG, GIF veya WEBP fotoğraf yüklenebilir'}), 400
    return jsonify({**save_uploaded_file(photo), 'type': 'image'})

@app.route('/upload', methods=['POST'])
@limiter.limit('12 per minute')
def upload_file():
    if 'user' not in session:
        return jsonify({'error': 'Yetkisiz'}), 401
    if 'file' not in request.files:
        return jsonify({'error': 'Dosya yok'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Dosya seçilmedi'}), 400
    ext = file_extension(file.filename)
    if not allowed_file(file.filename) or not allowed_mime(file) or not is_valid_upload_signature(file, ext):
        return jsonify({'error': 'İzin verilmeyen veya geçersiz dosya türü'}), 400
    upload_type = 'image' if file.mimetype in IMAGE_MIME_TYPES else ('video' if file.mimetype in VIDEO_MIME_TYPES else 'file')
    return jsonify({**save_uploaded_file(file), 'type': upload_type})

# ── SOCKETIO ─────────────────────────────────────────────────────────────────

@socketio.on('join')
def on_join(data):
    if 'user' not in session:
        return
    user = session['user']
    join_room(ROOM)
    online_users[request.sid] = user
    emit('user_status', {'user': user, 'online': list(online_users.values()), 'event': 'joined'}, room=ROOM)

@socketio.on('disconnect')
def on_disconnect():
    if request.sid in online_users:
        user = online_users.pop(request.sid)
        leave_room(ROOM)
        emit('user_status', {'user': user, 'online': list(online_users.values()), 'event': 'left'}, room=ROOM)

@socketio.on('message')
def on_message(data):
    if 'user' not in session or not isinstance(data, dict):
        return
    msg_type = data.get('type', 'text')
    if msg_type not in {'text', 'image', 'file', 'video', 'location'}:
        return
    user = session['user']
    now = datetime.now(TIMEZONE)
    text = (data.get('text', '') or '')[:4000]
    file_url = (data.get('file_url', '') or '')[:500]
    if file_url and not file_url.startswith('/media/'):
        return
    msg = {
        'id': uuid.uuid4().hex,
        'user': user,
        'text': text,
        'type': msg_type,
        'file_url': file_url,
        'file_name': (data.get('file_name', '') or '')[:255],
        'timestamp': now.strftime('%H:%M'),
        'date_label': now.strftime('%d.%m.%Y'),
        'read': False,
        'read_at': '',
    }
    try:
        save_message(msg)
    except Exception as e:
        print(f'Save message error: {e}')
    emit('message', msg, room=ROOM)

@socketio.on('messages_read')
def on_messages_read(data):
    if 'user' not in session:
        return
    ids = data.get('ids', []) if isinstance(data, dict) else []
    read_ids = mark_messages_read(ids, session['user']['id'])
    if read_ids:
        emit('messages_read', {'ids': read_ids, 'reader': session['user']}, room=ROOM)

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

import os
import uuid
import json
import psycopg2
import psycopg2.extras
from datetime import datetime
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'gizli-anahtar-degistir-2024')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'pdf'}

USER1_CODE = os.environ.get('USER1_CODE', 'KARA-001')
USER2_CODE = os.environ.get('USER2_CODE', 'KARA-002')
USER1_NAME = os.environ.get('USER1_NAME', 'Özgür')
USER2_NAME = os.environ.get('USER2_NAME', 'Kişi 2')

ROOM = 'private_room'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
online_users = {}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ── DATABASE ─────────────────────────────────────────────────────────────────

def get_db():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return None
    # Railway bazen postgresql:// yerine postgres:// verir
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    return psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    conn = get_db()
    if not conn:
        return
    try:
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
        conn.commit()
    finally:
        conn.close()

def save_message(msg):
    conn = get_db()
    if not conn:
        return
    try:
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
                datetime.utcnow()
            ))
        conn.commit()
    finally:
        conn.close()

def load_messages(limit=200):
    conn = get_db()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT * FROM (
                    SELECT * FROM messages ORDER BY created_at DESC LIMIT %s
                ) sub ORDER BY created_at ASC
            ''', (limit,))
            rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                'id': r['id'],
                'user': {'id': r['user_id'], 'name': r['user_name']},
                'type': r['type'],
                'text': r['text'] or '',
                'file_url': r['file_url'] or '',
                'file_name': r['file_name'] or '',
                'timestamp': r['created_at'].strftime('%H:%M') if r['created_at'] else '',
                'date_label': r['created_at'].strftime('%d.%m.%Y') if r['created_at'] else '',
            })
        return result
    finally:
        conn.close()

# DB tablosunu uygulama başlarken oluştur
try:
    init_db()
except Exception as e:
    print(f"DB init warning: {e}")

# ── HELPERS ──────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_code(code):
    code = code.strip().upper()
    if code == USER1_CODE.upper():
        return {'id': 'user1', 'name': USER1_NAME}
    elif code == USER2_CODE.upper():
        return {'id': 'user2', 'name': USER2_NAME}
    return None

# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    user = validate_code(request.form.get('code', ''))
    if user:
        session['user'] = user
        return redirect(url_for('chat'))
    return render_template('login.html', error='Geçersiz kod')

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
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({'url': f'/static/uploads/{filename}', 'name': file.filename})
    return jsonify({'error': 'İzin verilmeyen dosya türü'}), 400

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
    user = session['user']
    msg = {
        'id': uuid.uuid4().hex,
        'user': user,
        'text': data.get('text', ''),
        'type': data.get('type', 'text'),
        'file_url': data.get('file_url', ''),
        'file_name': data.get('file_name', ''),
        'timestamp': datetime.now().strftime('%H:%M'),
    }
    try:
        save_message(msg)
    except Exception as e:
        print(f"Save message error: {e}")
    emit('message', msg, room=ROOM)

@socketio.on('typing')
def on_typing(data):
    if 'user' not in session:
        return
    emit('typing', {'user': session['user'], 'typing': data.get('typing', False)},
         room=ROOM, include_self=False)

@socketio.on('webrtc_offer')
def on_offer(data):
    emit('webrtc_offer', {**data, 'from': session.get('user', {})}, room=ROOM, include_self=False)

@socketio.on('webrtc_answer')
def on_answer(data):
    emit('webrtc_answer', {**data, 'from': session.get('user', {})}, room=ROOM, include_self=False)

@socketio.on('webrtc_ice')
def on_ice(data):
    emit('webrtc_ice', data, room=ROOM, include_self=False)

@socketio.on('call_request')
def on_call_request(data):
    emit('call_request', {**data, 'from': session.get('user', {})}, room=ROOM, include_self=False)

@socketio.on('call_response')
def on_call_response(data):
    emit('call_response', data, room=ROOM, include_self=False)

@socketio.on('call_end')
def on_call_end(data):
    emit('call_end', data, room=ROOM)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)

import sitecustomize
import app as chat_app
from flask import session
from flask_socketio import emit

chat_app.IMAGE_EXTENSIONS.update({'heic', 'heif'})
chat_app.VIDEO_EXTENSIONS.update({'m4v'})
chat_app.ALLOWED_EXTENSIONS.update({'heic', 'heif', 'm4v'})
chat_app.IMAGE_MIME_TYPES.update({'image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence', 'application/octet-stream'})
chat_app.VIDEO_MIME_TYPES.update({'video/x-m4v', 'application/octet-stream'})
chat_app.ALLOWED_MIME_TYPES.update(chat_app.IMAGE_MIME_TYPES | chat_app.VIDEO_MIME_TYPES)

_original_allowed_photo = chat_app.allowed_photo
_original_allowed_mime = chat_app.allowed_mime
_original_signature = chat_app.is_valid_upload_signature


def _ext(file):
    return chat_app.file_extension(getattr(file, 'filename', '') or '')


def allowed_photo(file):
    ext = _ext(file)
    if ext in {'heic', 'heif'}:
        return True
    return _original_allowed_photo(file)


def allowed_mime(file):
    ext = _ext(file)
    if ext in {'heic', 'heif', 'mov', 'm4v'}:
        return True
    return _original_allowed_mime(file)


def is_valid_upload_signature(file, ext):
    ext = (ext or '').lower()
    if ext in {'heic', 'heif'}:
        head = file.stream.read(64)
        file.stream.seek(0)
        return b'ftyp' in head or getattr(file, 'mimetype', '').startswith('image/')
    if ext in {'mov', 'm4v'}:
        head = file.stream.read(64)
        file.stream.seek(0)
        return b'ftyp' in head or getattr(file, 'mimetype', '').startswith('video/')
    return _original_signature(file, ext)


chat_app.allowed_photo = allowed_photo
chat_app.allowed_mime = allowed_mime
chat_app.is_valid_upload_signature = is_valid_upload_signature


def ensure_location_columns():
    conn = chat_app.get_db()
    try:
        with conn:
            if chat_app.using_postgres():
                with conn.cursor() as cur:
                    cur.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_lat DOUBLE PRECISION')
                    cur.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_lng DOUBLE PRECISION')
                    cur.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_location_accuracy DOUBLE PRECISION')
                    cur.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_location_at TIMESTAMP')
            else:
                cols = [c['name'] for c in conn.execute('PRAGMA table_info(users)').fetchall()]
                if 'last_lat' not in cols:
                    conn.execute('ALTER TABLE users ADD COLUMN last_lat REAL')
                if 'last_lng' not in cols:
                    conn.execute('ALTER TABLE users ADD COLUMN last_lng REAL')
                if 'last_location_accuracy' not in cols:
                    conn.execute('ALTER TABLE users ADD COLUMN last_location_accuracy REAL')
                if 'last_location_at' not in cols:
                    conn.execute('ALTER TABLE users ADD COLUMN last_location_at TEXT')
    finally:
        conn.close()


def save_last_location(user_id, loc):
    if not user_id or not isinstance(loc, dict):
        return
    lat = loc.get('lat')
    lng = loc.get('lng')
    if lat is None or lng is None:
        return
    accuracy = loc.get('accuracy')
    now = chat_app.datetime.now(chat_app.TIMEZONE)
    conn = chat_app.get_db()
    try:
        with conn:
            if chat_app.using_postgres():
                with conn.cursor() as cur:
                    cur.execute(
                        'UPDATE users SET last_lat=%s,last_lng=%s,last_location_accuracy=%s,last_location_at=%s WHERE id=%s',
                        (float(lat), float(lng), accuracy, now.replace(tzinfo=None), user_id)
                    )
            else:
                conn.execute(
                    'UPDATE users SET last_lat=?,last_lng=?,last_location_accuracy=?,last_location_at=? WHERE id=?',
                    (float(lat), float(lng), accuracy, now.isoformat(), user_id)
                )
    finally:
        conn.close()


def load_saved_locations():
    conn = chat_app.get_db()
    try:
        if chat_app.using_postgres():
            with conn.cursor() as cur:
                cur.execute('SELECT id,last_lat,last_lng,last_location_accuracy,last_location_at FROM users')
                rows = cur.fetchall()
        else:
            rows = conn.execute('SELECT id,last_lat,last_lng,last_location_accuracy,last_location_at FROM users').fetchall()
        out = {}
        for row in rows:
            lat = chat_app.row_get(row, 'last_lat')
            lng = chat_app.row_get(row, 'last_lng')
            if lat is None or lng is None:
                continue
            ts = chat_app.parse_created_at(chat_app.row_get(row, 'last_location_at'))
            out[row['id']] = {
                'lat': float(lat),
                'lng': float(lng),
                'accuracy': chat_app.row_get(row, 'last_location_accuracy'),
                'updated_at': ts.strftime('%H:%M') if ts else ''
            }
        return out
    finally:
        conn.close()


class PersistentLocationDict(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        try:
            save_last_location(key, value)
        except Exception as exc:
            print(f'Location save warning: {exc}')


def get_public_locations():
    merged = {}
    try:
        merged.update(load_saved_locations())
    except Exception as exc:
        print(f'Location load warning: {exc}')
    merged.update(dict(chat_app.user_locations))
    return {uid: {**loc, 'url': f"https://maps.google.com/?q={loc['lat']},{loc['lng']}"} for uid, loc in merged.items()}


chat_app.tap_state = {}


@chat_app.socketio.on('tap')
def on_tap(data):
    if 'user' not in session or not isinstance(data, dict):
        return
    mid = str(data.get('id') or '')[:100]
    if not mid:
        return
    uid = session['user']['id']
    box = chat_app.tap_state.setdefault(mid, {})
    if uid in box:
        box.pop(uid, None)
    else:
        box[uid] = session['user']['name']
    emit('tap', {'id': mid, 'count': len(box), 'users': box}, room=chat_app.ROOM)


try:
    ensure_location_columns()
    saved = load_saved_locations()
except Exception as exc:
    print(f'Location migration warning: {exc}')
    saved = {}

chat_app.user_locations = PersistentLocationDict(chat_app.user_locations)
for _uid, _loc in saved.items():
    dict.__setitem__(chat_app.user_locations, _uid, _loc)
chat_app.get_public_locations = get_public_locations

app = chat_app.app

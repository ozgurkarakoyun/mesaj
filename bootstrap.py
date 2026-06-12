import sitecustomize
import app as chat_app

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
app = chat_app.app

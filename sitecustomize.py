import flask
import flask.templating

_original_render_template = flask.templating.render_template
_original_make_response = flask.Flask.make_response


def _fix_location_button_html(html):
    if not isinstance(html, str):
        return html
    html = html.replace(
        'id="topMapIcon" type="button" title="Konumu aç" style="display:none"',
        'id="topMapIcon" type="button" title="Konumu aç"'
    )
    html = html.replace(
        '<button class="ib" onclick="toggleSearch()">🔎</button>',
        '<button class="ib mapicon" id="topMapIcon" type="button" title="Konumu aç">📍</button><button class="ib" onclick="toggleSearch()">🔎</button>'
    )
    html = html.replace(
        "const display = show && otherLocationUrl ? '' : 'none';",
        "const display = '';"
    )
    html = html.replace(
        'if(icon) { icon.style.display = display; icon.onclick = openOtherLocation; }',
        "if(icon) { icon.style.display = ''; icon.onclick = openOtherLocation; }"
    )
    return html


def render_template(*args, **kwargs):
    html = _original_render_template(*args, **kwargs)
    template_name = args[0] if args else ''
    if template_name == 'chat.html':
        html = _fix_location_button_html(html)
    return html


def make_response(self, rv):
    response = _original_make_response(self, rv)
    try:
        if flask.request.path == '/chat' and response.content_type and 'text/html' in response.content_type:
            body = response.get_data(as_text=True)
            response.set_data(_fix_location_button_html(body))
    except Exception:
        pass
    return response


flask.templating.render_template = render_template
flask.render_template = render_template
flask.Flask.make_response = make_response

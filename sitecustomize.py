import flask
import flask.templating

_original_render_template = flask.templating.render_template


def render_template(*args, **kwargs):
    html = _original_render_template(*args, **kwargs)
    template_name = args[0] if args else ''
    if template_name == 'chat.html' and isinstance(html, str):
        html = html.replace(
            'id="topMapIcon" type="button" title="Konumu aç" style="display:none"',
            'id="topMapIcon" type="button" title="Konumu aç"'
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

flask.templating.render_template = render_template
flask.render_template = render_template

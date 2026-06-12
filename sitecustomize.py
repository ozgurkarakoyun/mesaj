import flask

_original_make_response = flask.Flask.make_response


def _dedupe_map_button(html):
    if not isinstance(html, str):
        return html

    marker = 'id="topMapIcon"'
    if marker not in html:
        return html

    parts = html.split('<button')
    output = [parts[0]]
    seen = False

    for part in parts[1:]:
        chunk = '<button' + part
        if marker in chunk:
            if seen:
                end = chunk.find('</button>')
                if end != -1:
                    chunk = chunk[end + len('</button>'):]
            else:
                seen = True
                chunk = chunk.replace(' style="display:none"', '')
        output.append(chunk)

    html = ''.join(output)
    html = html.replace("const display = show && otherLocationUrl ? '' : 'none';", "const display = '';")
    html = html.replace('if(icon) { icon.style.display = display; icon.onclick = openOtherLocation; }', "if(icon) { icon.style.display = ''; icon.onclick = openOtherLocation; }")
    return html


def make_response(self, rv):
    response = _original_make_response(self, rv)
    try:
        if flask.request.path == '/chat' and response.content_type and 'text/html' in response.content_type:
            response.set_data(_dedupe_map_button(response.get_data(as_text=True)))
    except Exception:
        pass
    return response


flask.Flask.make_response = make_response

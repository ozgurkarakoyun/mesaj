import flask

_original_make_response = flask.Flask.make_response

STATUS_STYLE = '<style id="statusLinesPatch">#statusText{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;line-height:1.18!important}#statusText .sd{display:block!important;font-weight:700!important}#statusText .st{display:block!important;font-size:11px!important;opacity:.95!important}.hb{border:0;border-radius:999px;background:#fff8;padding:1px 5px;margin-right:4px;font-size:12px}.hb.on{background:#ffdce5}</style>'
HEART_SCRIPT = '<script id="heartPatch">function hu(b,i){var w=b.closest(".mw");return w&&(w.dataset.id||w.id)||String(i)}function hs(id,on){document.querySelectorAll(".bub").forEach(function(b,i){if(hu(b,i)==id){var x=b.querySelector(".hb");if(x){x.className="hb"+(on?" on":"");x.textContent=on?"❤️":"♡"}}})}setInterval(function(){document.querySelectorAll(".bub").forEach(function(b,i){if(b.querySelector(".hb"))return;var id=hu(b,i),m=b.querySelector(".meta")||b,x=document.createElement("button");x.className="hb";x.type="button";x.textContent="♡";x.onclick=function(e){e.stopPropagation();try{window["socket"].emit("tap",{id:id})}catch(_){x.classList.toggle("on");x.textContent=x.classList.contains("on")?"❤️":"♡"}};m.insertBefore(x,m.firstChild)})},1200);setInterval(function(){try{var s=window["socket"];if(s&&!s.__hb){s.__hb=1;s.on("tap",function(d){hs(d.id,d.count>0)})}}catch(_){}},1000)</script>'


def _dedupe_map_button(html):
    if not isinstance(html, str):
        return html

    marker = 'id="topMapIcon"'
    if marker in html:
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
        html = html.replace("setStatus(last.date, 'Son konum: ' + (loc.updated_at || last.time || ''), true, loc.url);", "setStatus('Son görülme: ' + last.date + (last.time ? ' ' + last.time : ''), 'Son konum: ' + (loc.updated_at || last.time || ''), true, loc.url);")

    if 'statusLinesPatch' not in html:
        html = html.replace('</head>', STATUS_STYLE + '</head>')
    if 'heartPatch' not in html:
        html = html.replace('</body>', HEART_SCRIPT + '</body>')
    html = html.replace('accept="image/png,image/jpeg,image/gif,image/webp"', 'accept="image/*"')
    html = html.replace('accept="application/pdf,video/mp4,video/webm,video/quicktime"', 'accept="application/pdf,video/*"')
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

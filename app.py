import os, io, threading, dropbox, html, json
from flask import Flask, render_template_string, request, session, redirect, url_for, jsonify
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this")

APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

BUILD_STATUS = {"running": False, "progress": 0, "text": "Idle"}


def get_dbx():
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    if not refresh_token or not APP_KEY or not APP_SECRET:
        return None
    return dropbox.Dropbox(oauth2_refresh_token=refresh_token, app_key=APP_KEY, app_secret=APP_SECRET)


HTML_LOGIN = '''
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {
    margin:0;
    font-family:sans-serif;
    background:radial-gradient(circle at top, #1a1f2e, #000);
    color:white;
    display:flex;
    justify-content:center;
    align-items:center;
    height:100vh;
}
.card {
    background:rgba(255,255,255,0.05);
    border:1px solid rgba(255,215,0,0.2);
    padding:30px;
    border-radius:20px;
    width:320px;
    backdrop-filter: blur(10px);
}
img { width:100px; display:block; margin:auto; }
h2 { text-align:center; margin-bottom:20px; }
input {
    width:100%;
    padding:12px;
    margin-top:10px;
    border-radius:8px;
    border:1px solid #333;
    background:#111;
    color:white;
}
button {
    width:100%;
    padding:12px;
    margin-top:15px;
    border:none;
    border-radius:8px;
    background:linear-gradient(90deg,#d4af37,#f5d76e);
    font-weight:bold;
}
</style>
</head>
<body>
<div class="card">
<img src="/static/logo.png">
<h2>PoW Band PDF Portal</h2>
<form method="POST">
<input type="password" name="password" placeholder="Password">
<button>Sign In</button>
</form>
</div>
</body>
</html>
'''


@app.before_request
def protect():
    if not APP_PASSWORD:
        return
    if request.endpoint in ['login', 'static', 'status']:
        return
    if not session.get("auth"):
        return redirect(url_for("login"))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == APP_PASSWORD:
            session['auth'] = True
            return redirect('/')
    return render_template_string(HTML_LOGIN)


def render_setlist_html(setlist):
    out = ""
    for i, s in enumerate(setlist):
        name = html.escape(s.get("name", ""))
        payload = json.dumps(s)

        up = json.dumps({"index": i, "dir": "up"})
        down = json.dumps({"index": i, "dir": "down"})

        out += f'''
<div style="display:flex;justify-content:space-between;align-items:center;padding:10px;border-bottom:1px solid #333;color:white;">
<span>{i+1}. {name}</span>
<div>
<button hx-post="/move" hx-vals='{up}' hx-target="#setlist-inner">↑</button>
<button hx-post="/move" hx-vals='{down}' hx-target="#setlist-inner">↓</button>
<button hx-post="/remove" hx-vals='{payload}' hx-target="#setlist-inner">×</button>
</div>
</div>
'''
    return out or "<p style='color:#888'>No songs selected</p>"


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
body {
    font-family:sans-serif;
    max-width:500px;
    margin:auto;
    padding:20px;
    background:radial-gradient(circle at top, #1a1f2e, #000);
    color:white;
}
.card {
    background:rgba(255,255,255,0.05);
    border:1px solid rgba(255,215,0,0.2);
    padding:15px;
    border-radius:15px;
    margin-bottom:20px;
}
.item { display:flex; justify-content:space-between; padding:10px; border-bottom:1px solid #333; }
.btn-add { background:#d4af37; border:none; padding:6px 10px; border-radius:5px; }
.build-btn { width:100%; padding:15px; background:linear-gradient(90deg,#d4af37,#f5d76e); border:none; border-radius:10px; }
#status-box { background:#111; color:#0f0; padding:10px; border-radius:5px; }
input, select { width:100%; padding:10px; margin-bottom:10px; border-radius:5px; border:1px solid #333; background:#111; color:white; }
</style>
</head>
<body>

<h1 style="text-align:center;">🎺 PoW Band PDF Portal</h1>

<div class="card">
<select name="folder_path" hx-post="/update-library" hx-trigger="change" hx-target="#library-container">
<option value="">-- Choose Set --</option>
{% for folder in folders %}
<option value="{{ folder.path_lower }}">{{ folder.name }}</option>
{% endfor %}
</select>
</div>

<div class="card">
<input id="libSearch" placeholder="Search songs..." onkeyup="filterLib()">
<div id="library-container"></div>
</div>

<div class="card">
<div id="setlist-inner">{{ setlist_html|safe }}</div>
</div>

<form action="/build" method="POST">
<input name="set_name" placeholder="Set Name">
<button class="build-btn">BUILD</button>
</form>

<div id="status-box"><span id="status-text"></span></div>

<script>
function filterLib(){
 let q=document.getElementById('libSearch').value.toLowerCase();
 document.querySelectorAll('.lib-item').forEach(e=>{
  e.style.display=e.innerText.toLowerCase().includes(q)?'flex':'none';
 });
}

setInterval(()=>{
 fetch('/status').then(r=>r.json()).then(d=>{
  document.getElementById('status-text').innerText=d.text+' '+d.progress+'%';
 });
},1000);
</script>

</body>
</html>
'''


@app.route('/')
def index():
    session.setdefault('setlist', [])
    dbx = get_dbx()
    folders = []
    if dbx:
        res = dbx.files_list_folder("")
        folders = [e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata)]
    return render_template_string(HTML_TEMPLATE, folders=folders, setlist_html=render_setlist_html(session['setlist']))


@app.route('/move', methods=['POST'])
def move():
    idx = int(request.form.get('index'))
    direction = request.form.get('dir')
    lst = session.get('setlist', [])

    if direction == 'up' and idx > 0:
        lst[idx], lst[idx-1] = lst[idx-1], lst[idx]
    elif direction == 'down' and idx < len(lst)-1:
        lst[idx], lst[idx+1] = lst[idx+1], lst[idx]

    session['setlist'] = lst
    return render_setlist_html(lst)


@app.route('/update-library', methods=['POST'])
def update_library():
    dbx = get_dbx()
    path = request.form.get('folder_path')
    if not dbx or not path:
        return ""

    res = dbx.files_list_folder(path)
    out = ""
    seen = set()

    for e in res.entries:
        if isinstance(e, dropbox.files.FolderMetadata):
            sub = dbx.files_list_folder(e.path_lower)
            for f in sub.entries:
                if f.name.lower().endswith('.pdf'):
                    key = f.name.lower()
                    if key in seen:
                        continue
                    seen.add(key)

                    payload = json.dumps({"name": f.name, "path": f.path_lower})

                    out += f'''<div class="lib-item item">
<span>{html.escape(f.name)}</span>
<button class="btn-add" hx-post="/add" hx-vals='{payload}' hx-target="#setlist-inner">+</button>
</div>'''

    return out


@app.route('/add', methods=['POST'])
def add():
    name = request.form.get('name')
    path = request.form.get('path')
    lst = session.get('setlist', [])
    if name and path:
        lst.append({"name": name, "path": path})
    session['setlist'] = lst
    return render_setlist_html(lst)


@app.route('/remove', methods=['POST'])
def remove():
    name = request.form.get('name')
    path = request.form.get('path')
    lst = session.get('setlist', [])
    lst = [s for s in lst if not (s.get('name') == name and s.get('path') == path)]
    session['setlist'] = lst
    return render_setlist_html(lst)


@app.route('/status')
def status():
    return jsonify(BUILD_STATUS)


if __name__ == '__main__':
    app.run()

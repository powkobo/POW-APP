import os, io, threading, dropbox, html
from flask import Flask, render_template_string, request, session, redirect, url_for, jsonify
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this")

APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

LIB_CACHE = {}
REG_CACHE = {}
BUILD_STATUS = {"running": False, "progress": 0, "text": "Idle"}


def get_dbx():
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    if not refresh_token or not APP_KEY or not APP_SECRET:
        return None
    return dropbox.Dropbox(oauth2_refresh_token=refresh_token, app_key=APP_KEY, app_secret=APP_SECRET)


@app.before_request
def require_login():
    if not APP_PASSWORD:
        return
    if request.endpoint in ("login", "static", "status"):
        return
    if session.get("auth") is not True:
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["auth"] = True
            return redirect(url_for("index"))
    return '<form method="POST"><input name="password" type="password"><button>Login</button></form>'


def render_setlist_html(setlist):
    out = ""
    for i, song in enumerate(setlist):
        safe = html.escape(song, quote=True)
        out += f'<div><span>{i+1}. {safe}</span><button hx-post="/remove" name="song" value="{safe}" hx-target="#setlist-inner">×</button></div>'
    return out if setlist else '<p>No songs selected.</p>'


HTML = '''
<!DOCTYPE html>
<html>
<head>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head>
<body>
<h2>Builder</h2>
<select name="folder_path" hx-post="/update-library" hx-trigger="change" hx-target="#lib"></select>
<div id="lib"></div>
<div id="setlist-inner">{{setlist|safe}}</div>
<form method="POST" action="/build">
<input name="set_name">
<button>Build</button>
</form>
<div id="status"></div>
<script>
setInterval(()=>{
fetch('/status').then(r=>r.json()).then(d=>{
 document.getElementById('status').innerText = d.text + ' ' + d.progress + '%';
});
},1000);
</script>
</body>
</html>
'''


@app.route('/')
def index():
    session.setdefault('setlist', [])
    return render_template_string(HTML, setlist=render_setlist_html(session['setlist']))


@app.route('/update-library', methods=['POST'])
def update_library():
    dbx = get_dbx()
    path = request.form.get('folder_path')
    if not dbx or not path:
        return ""
    res = dbx.files_list_folder(path)
    out = ""
    for e in res.entries:
        if isinstance(e, dropbox.files.FolderMetadata):
            sub = dbx.files_list_folder(e.path_lower)
            for f in sub.entries:
                if f.name.lower().endswith('.pdf'):
                    safe = html.escape(f.name, quote=True)
                    out += f'<div>{safe}<button name="song" value="{safe}" hx-post="/add" hx-target="#setlist-inner">+</button></div>'
    return out


@app.route('/add', methods=['POST'])
def add():
    song = request.form.get('song')
    lst = session.get('setlist', [])
    if song and song not in lst:
        lst.append(song)
    session['setlist'] = lst
    return render_setlist_html(lst)


@app.route('/remove', methods=['POST'])
def remove():
    song = request.form.get('song')
    lst = session.get('setlist', [])
    if song in lst:
        lst.remove(song)
    session['setlist'] = lst
    return render_setlist_html(lst)


def build_worker(setlist, set_name, active_folder):
    dbx = get_dbx()
    BUILD_STATUS["running"] = True
    BUILD_STATUS["progress"] = 0

    res = dbx.files_list_folder(active_folder)
    folders = [f for f in res.entries if isinstance(f, dropbox.files.FolderMetadata)]

    pdf_cache = {}
    for song in setlist:
        for f in folders:
            items = dbx.files_list_folder(f.path_lower).entries
            for e in items:
                if e.name.lower() == song.lower():
                    _, r = dbx.files_download(e.path_lower)
                    pdf_cache[song.lower()] = r.content
                    break

    total = len(folders)

    for i, f in enumerate(folders):
        writer = PdfWriter()
        for song in setlist:
            if song.lower() in pdf_cache:
                writer.append(io.BytesIO(pdf_cache[song.lower()]))

        out = io.BytesIO()
        writer.write(out)
        out.seek(0)

        dbx.files_upload(out.read(), f"/Generated/{set_name}/{f.name}-{set_name}.pdf", mode=dropbox.files.WriteMode.overwrite)

        BUILD_STATUS["progress"] = int((i+1)/total*100)
        BUILD_STATUS["text"] = f"Processing {f.name}"

    BUILD_STATUS["text"] = "Done"
    BUILD_STATUS["running"] = False


@app.route('/build', methods=['POST'])
def build():
    if BUILD_STATUS["running"]:
        return "Already running"

    setlist = session.get('setlist', [])
    set_name = request.form.get('set_name')
    active_folder = request.form.get('active_folder')

    threading.Thread(target=build_worker, args=(setlist, set_name, active_folder)).start()

    return redirect('/')


@app.route('/status')
def status():
    return jsonify(BUILD_STATUS)


if __name__ == '__main__':
    app.run()

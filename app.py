import os, io, dropbox, html
from flask import Flask, render_template_string, request, session, redirect, url_for, send_file
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this")

APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

LIB_CACHE = {}


def get_dbx():
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    if not refresh_token or not APP_KEY or not APP_SECRET:
        return None
    try:
        return dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=APP_KEY,
            app_secret=APP_SECRET
        )
    except Exception:
        return None


@app.before_request
def require_login():
    if not APP_PASSWORD:
        return
    if request.endpoint in ("login", "static"):
        return
    if session.get("auth") is not True:
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["auth"] = True
            return redirect(url_for("index"))
    return """
    <form method="POST" style="max-width:300px;margin:100px auto;font-family:sans-serif;">
        <h3>Password</h3>
        <input type="password" name="password" style="width:100%;padding:10px;"/>
        <button style="width:100%;margin-top:10px;">Login</button>
    </form>
    """


def render_setlist_html(setlist):
    html_out = ""
    for i, song in enumerate(setlist):
        safe = html.escape(song, quote=True)
        html_out += f'''
        <div class="item" style="display:flex;justify-content:space-between;padding:10px;border-bottom:1px solid #eee;align-items:center;">
            <span>{i+1}. {safe}</span>
            <div>
                <button hx-post="/move" hx-vals='{{"index": {i}, "dir": "up"}}' hx-target="#setlist-inner">↑</button>
                <button hx-post="/move" hx-vals='{{"index": {i}, "dir": "down"}}' hx-target="#setlist-inner">↓</button>
                <button hx-post="/remove" hx-vals='{{"song": "{safe}"}}' hx-target="#setlist-inner">×</button>
            </div>
        </div>'''
    return html_out if setlist else '<p style="color:#999;padding:10px;">No songs selected.</p>'


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
body{font-family:sans-serif;max-width:500px;margin:auto;padding:20px;background:#f4f4f4}
.card{background:white;border:1px solid #ddd;padding:15px;border-radius:8px;margin-bottom:20px}
.build-btn{width:100%;padding:15px;background:#007bff;color:white;border:none;border-radius:8px;font-weight:bold;font-size:18px}
.item button{margin-left:5px}
</style>
</head>
<body>
<h1>🎺 POW Set Downloader</h1>

<div class="card">
<h3>1. Select Set Folder</h3>
<select name="folder_path" hx-post="/update-library" hx-trigger="change" hx-target="#library-container">
<option value="">-- Choose --</option>
{% for folder in folders %}
<option value="{{ folder.path_lower }}">{{ folder.name }}</option>
{% endfor %}
</select>
</div>

<div class="card">
<h3>2. Library</h3>
<div id="library-container"></div>
</div>

<div class="card">
<h3>3. Setlist</h3>
<div id="setlist-inner">{{ setlist_html|safe }}</div>
<button hx-post="/clear" hx-target="#setlist-inner">Clear</button>
</div>

<form method="POST" action="/build">
<input type="hidden" id="active_folder" name="active_folder">
<input name="set_name" placeholder="Set name" required>
<button class="build-btn">BUILD</button>
</form>

<script>
document.body.addEventListener('htmx:afterRequest', function(evt){
    if(evt.detail.target.id==='library-container'){
        document.getElementById('active_folder').value=document.querySelector('select').value;
    }
});
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
        try:
            res = dbx.files_list_folder("")
            folders = [e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata)]
        except:
            pass

    return render_template_string(HTML_TEMPLATE, folders=folders, setlist_html=render_setlist_html(session['setlist']))


@app.route('/update-library', methods=['POST'])
def update_library():
    dbx = get_dbx()
    path = request.form.get('folder_path')

    if not dbx or not path:
        return ""

    if path in LIB_CACHE:
        return LIB_CACHE[path]

    try:
        res = dbx.files_list_folder(path)
        html_out = ""
        seen = set()

        for entry in res.entries:
            if isinstance(entry, dropbox.files.FolderMetadata):
                sub = dbx.files_list_folder(entry.path_lower)
                for file in sub.entries:
                    if isinstance(file, dropbox.files.FileMetadata) and file.name.lower().endswith('.pdf'):
                        key = file.name.lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        safe = html.escape(file.name, quote=True)
                        html_out += f'''<div class="item">
<span>{safe}</span>
<button hx-post="/add" hx-vals='{{"song":"{safe}"}}' hx-target="#setlist-inner">+</button>
</div>'''

        LIB_CACHE[path] = html_out
        return html_out
    except Exception as e:
        return str(e)


@app.route('/add', methods=['POST'])
def add_song():
    song = request.form.get('song')
    lst = session.get('setlist', [])
    if song and song not in lst and len(lst) < 50:
        lst.append(song)
    session['setlist'] = lst
    return render_setlist_html(lst)


@app.route('/remove', methods=['POST'])
def remove_song():
    song = request.form.get('song')
    lst = session.get('setlist', [])
    if song in lst:
        lst.remove(song)
    session['setlist'] = lst
    return render_setlist_html(lst)


@app.route('/move', methods=['POST'])
def move():
    i = int(request.form.get('index'))
    d = request.form.get('dir')
    lst = session.get('setlist', [])

    if d == 'up' and i > 0:
        lst[i], lst[i-1] = lst[i-1], lst[i]
    if d == 'down' and i < len(lst)-1:
        lst[i], lst[i+1] = lst[i+1], lst[i]

    session['setlist'] = lst
    return render_setlist_html(lst)


@app.route('/clear', methods=['POST'])
def clear():
    session['setlist'] = []
    return render_setlist_html([])


@app.route('/build', methods=['POST'])
def build():
    dbx = get_dbx()
    setlist = session.get('setlist', [])
    set_name = request.form.get('set_name')
    active_folder = request.form.get('active_folder')

    if not dbx or not setlist or not active_folder:
        return "Error"

    try:
        try:
            dbx.files_create_folder_v2(f"/Generated/{set_name}")
        except:
            pass

        res = dbx.files_list_folder(active_folder)

        for f in res.entries:
            if not isinstance(f, dropbox.files.FolderMetadata):
                continue

            writer = PdfWriter()
            items = dbx.files_list_folder(f.path_lower).entries
            pdf_map = {e.name.lower(): e.path_lower for e in items if e.name.lower().endswith('.pdf')}

            for song in setlist:
                if song.lower() in pdf_map:
                    try:
                        _, r = dbx.files_download(pdf_map[song.lower()])
                        writer.append(io.BytesIO(r.content))
                    except:
                        continue

            out = io.BytesIO()
            writer.write(out)
            out.seek(0)

            dbx.files_upload(out.read(), f"/Generated/{set_name}/{f.name}-{set_name}.pdf", mode=dropbox.files.WriteMode.overwrite)

        session['setlist'] = []
        return "<h1>Done</h1><a href='/'>Back</a>"

    except Exception as e:
        return str(e)


if __name__ == '__main__':
    app.run()

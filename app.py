import os, io, dropbox, html
from flask import Flask, render_template_string, request, session, redirect, url_for, send_file
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this")

APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
APP_PASSWORD = os.environ.get("APP_PASSWORD")


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
        safe_song = html.escape(song, quote=True)
        html_out += f'''
        <div class="item" draggable="true" data-index="{i}">
            <span>{i+1}. {safe_song}</span>
            <div>
                <button hx-post="/move" hx-vals='{{"index": {i}, "dir": "up"}}' hx-target="#setlist-inner">↑</button>
                <button hx-post="/move" hx-vals='{{"index": {i}, "dir": "down"}}' hx-target="#setlist-inner">↓</button>
                <button hx-post="/remove" hx-vals='{{"song": "{safe_song}"}}' hx-target="#setlist-inner">×</button>
            </div>
        </div>'''
    return html_out if setlist else '<p style="color:#999; padding:10px;">No songs selected.</p>'


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    <style>
        body { font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px; background: #f4f4f4; }
        .card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: white; margin-bottom: 20px; }
        .item { display: flex; justify-content: space-between; padding: 10px; border-bottom: 1px solid #eee; align-items: center; cursor: grab; }
        .btn-add { background: #28a745; color: white; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; }
        .build-btn { width: 100%; padding: 15px; background: #007bff; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 18px; cursor: pointer; }
        select, input { width: 100%; padding: 12px; margin-bottom: 10px; border-radius: 4px; border: 1px solid #ccc; box-sizing: border-box; }
    </style>
</head>
<body>
    <h1>🎺 POW Set Downloader</h1>
    
    <div class="card">
        <h3>1. Select Set Folder</h3>
        <select name="folder_path" hx-post="/update-library" hx-trigger="change" hx-target="#library-container">
            <option value="">-- Choose a Set --</option>
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
        <h3>3. Your Setlist</h3>
        <div id="setlist-inner">{{ setlist_html|safe }}</div>
        <button hx-post="/clear" hx-target="#setlist-inner">Clear All</button>
    </div>

    <form action="/build" method="POST">
        <input type="hidden" id="active_folder" name="active_folder">
        <input type="text" name="set_name" required>
        <button class="build-btn">BUILD</button>
    </form>

<script>
let dragIndex = null;

document.addEventListener('dragstart', e => {
    dragIndex = e.target.dataset.index;
});

document.addEventListener('dragover', e => {
    e.preventDefault();
});

document.addEventListener('drop', e => {
    e.preventDefault();
    const target = e.target.closest('.item');
    if (!target) return;
    const toIndex = target.dataset.index;

    fetch('/reorder', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: `from=${dragIndex}&to=${toIndex}`
    }).then(r => r.text()).then(html => {
        document.getElementById('setlist-inner').innerHTML = html;
    });
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
            folders = sorted([e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata)], key=lambda x: x.name)
        except Exception:
            pass

    return render_template_string(
        HTML_TEMPLATE,
        folders=folders,
        setlist_html=render_setlist_html(session['setlist'])
    )


@app.route('/update-library', methods=['POST'])
def update_library():
    dbx = get_dbx()
    path = request.form.get('folder_path')

    if not dbx or not path:
        return ""

    try:
        res = dbx.files_list_folder(path)
        html_out = ""

        for entry in res.entries:
            if isinstance(entry, dropbox.files.FolderMetadata):
                sub = dbx.files_list_folder(entry.path_lower)
                for file in sub.entries:
                    if isinstance(file, dropbox.files.FileMetadata) and file.name.lower().endswith('.pdf'):
                        safe = html.escape(file.name, quote=True)
                        html_out += f'''<div class="item"><span>{safe}</span><button class="btn-add" hx-post="/add" hx-vals='{{"song": "{safe}"}}' hx-target="#setlist-inner">+</button></div>'''

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
    idx = int(request.form.get('index'))
    direction = request.form.get('dir')
    lst = session.get('setlist', [])

    if direction == 'up' and idx > 0:
        lst[idx], lst[idx-1] = lst[idx-1], lst[idx]
    elif direction == 'down' and idx < len(lst)-1:
        lst[idx], lst[idx+1] = lst[idx+1], lst[idx]

    session['setlist'] = lst
    return render_setlist_html(lst)


@app.route('/reorder', methods=['POST'])
def reorder():
    frm = int(request.form.get('from'))
    to = int(request.form.get('to'))
    lst = session.get('setlist', [])

    item = lst.pop(frm)
    lst.insert(to, item)

    session['setlist'] = lst
    return render_setlist_html(lst)


@app.route('/clear', methods=['POST'])
def clear():
    session['setlist'] = []
    return render_setlist_html([])


@app.route('/download/<path:filepath>')
def download(filepath):
    dbx = get_dbx()
    _, res = dbx.files_download(filepath)
    return send_file(io.BytesIO(res.content), download_name=os.path.basename(filepath), as_attachment=True)


@app.route('/build', methods=['POST'])
def build():
    dbx = get_dbx()
    setlist = session.get('setlist', [])
    set_name = request.form.get('set_name')
    active_folder = request.form.get('active_folder')

    if not setlist or not dbx or not active_folder:
        return "Error"

    links = []

    try:
        try:
            dbx.files_create_folder_v2(f"/Generated/{set_name}")
        except Exception:
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
                    except Exception:
                        continue

            out = io.BytesIO()
            writer.write(out)
            out.seek(0)

            filename = f"{f.name}-{set_name}.pdf"
            path = f"/Generated/{set_name}/{filename}"

            dbx.files_upload(out.read(), path, mode=dropbox.files.WriteMode.overwrite)
            links.append(path)

        session['setlist'] = []

        buttons = ''.join([f'<a href="/download{p}">Download {os.path.basename(p)}</a><br>' for p in links])

        return f"<h1>Success</h1>{buttons}<a href='/'>Back</a>"

    except Exception as e:
        return str(e)


if __name__ == '__main__':
    app.run()

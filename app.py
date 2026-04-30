import os, io, threading, dropbox, html, json
from flask import Flask, render_template_string, request, session, redirect, url_for, jsonify
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this")

APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")

BUILD_STATUS = {"running": False, "progress": 0, "text": "Idle"}


def get_dbx():
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    if not refresh_token or not APP_KEY or not APP_SECRET:
        return None
    return dropbox.Dropbox(oauth2_refresh_token=refresh_token, app_key=APP_KEY, app_secret=APP_SECRET)


def render_setlist_html(setlist):
    out = ""
    for i, s in enumerate(setlist):
        name = html.escape(s.get("name", ""))
        payload = json.dumps(s)
        out += f'''<div style="display:flex;justify-content:space-between;padding:8px;border-bottom:1px solid #eee;">
        <span>{i+1}. {name}</span>
        <button hx-post="/remove" hx-vals='{payload}' hx-target="#setlist-inner">×</button>
        </div>'''
    return out or "<p style='color:#999'>No songs selected</p>"


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
body { font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px; background: #f4f4f4; }
.card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: white; margin-bottom: 20px; }
.item { display: flex; justify-content: space-between; padding: 10px; border-bottom: 1px solid #eee; align-items: center; }
.btn-add { background: #28a745; color: white; border: none; padding: 6px 10px; border-radius: 4px; }
.build-btn { width: 100%; padding: 15px; background: #007bff; color: white; border: none; border-radius: 8px; font-weight: bold; }
#status-box { font-size: 12px; background: #222; color: #0f0; padding: 10px; border-radius: 5px; }
</style>
</head>
<body>

<h1>🎺 POW Set Downloader</h1>

<div class="card">
<h3>Select Set Folder</h3>
<select name="folder_path" hx-post="/update-library" hx-trigger="change" hx-target="#library-container">
<option value="">-- Choose a Set --</option>
{% for folder in folders %}
<option value="{{ folder.path_lower }}">{{ folder.name }}</option>
{% endfor %}
</select>
</div>

<div class="card">
<h3>Library</h3>
<input id="libSearch" placeholder="Search songs..." onkeyup="filterLib()">
<div id="library-container"></div>
</div>

<div class="card">
<h3>Setlist</h3>
<div id="setlist-inner">{{ setlist_html|safe }}</div>
</div>

<form action="/build" method="POST">
<input type="text" name="set_name" placeholder="Set Name" required>
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

    try:
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

                        safe = html.escape(f.name)
                        payload = json.dumps({"name": f.name, "path": f.path_lower})

                        out += f"<div class='lib-item item'><span>{safe}</span>\\
                        <button class='btn-add' hx-post='/add' hx-vals='{payload}' hx-target='#setlist-inner'>+</button></div>"

        return out

    except Exception as e:
        return str(e)


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


def build_worker(setlist, set_name):
    dbx = get_dbx()

    if not dbx:
        BUILD_STATUS.update({"running": False, "text": "Dropbox error"})
        return

    if not setlist:
        BUILD_STATUS.update({"running": False, "text": "Empty setlist"})
        return

    BUILD_STATUS.update({"running": True, "progress": 0, "text": "Starting..."})

    # determine root from first song path
    try:
        first_path = setlist[0].get("path")
        root = "/" + first_path.split("/")[1]
    except Exception:
        BUILD_STATUS.update({"running": False, "text": "Path error"})
        return

    try:
        res = dbx.files_list_folder(root)
        folders = [f for f in res.entries if isinstance(f, dropbox.files.FolderMetadata)]
    except Exception:
        BUILD_STATUS.update({"running": False, "text": "Folder error"})
        return

    if not folders:
        BUILD_STATUS.update({"running": False, "text": "No instrument folders"})
        return

    total = len(folders)

    for i, folder in enumerate(folders):
        writer = PdfWriter()

        try:
            items = dbx.files_list_folder(folder.path_lower).entries
            pdf_map = {e.name.lower(): e.path_lower for e in items if e.name.lower().endswith('.pdf')}
        except Exception:
            continue

        for song in setlist:
            name = (song.get("name") or "").lower()

            if name in pdf_map:
                try:
                    _, r = dbx.files_download(pdf_map[name])
                    writer.append(io.BytesIO(r.content))
                except Exception:
                    continue

        if not writer.pages:
            continue

        out = io.BytesIO()
        writer.write(out)
        out.seek(0)

        try:
            dbx.files_upload(
                out.read(),
                f"/Generated/{set_name}/{folder.name}-{set_name}.pdf",
                mode=dropbox.files.WriteMode.overwrite
            )
        except Exception:
            continue

        BUILD_STATUS.update({
            "progress": int((i + 1) / total * 100),
            "text": folder.name
        })

    BUILD_STATUS.update({"running": False, "text": "Done"})


@app.route('/build', methods=['POST'])
def build():
    if BUILD_STATUS["running"]:
        return "Busy"

    threading.Thread(
        target=build_worker,
        args=(session.get('setlist', []), request.form.get('set_name'))
    ).start()

    return redirect('/')


@app.route('/status')
def status():
    return jsonify(BUILD_STATUS)


if __name__ == '__main__':
    app.run()

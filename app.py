import os, io, dropbox, re
from flask import Flask, render_template_string, request, session
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "pow-band-2026-secure")

# App Credentials
APP_KEY = "88f9pjkp9e5b7qg"
APP_SECRET = "54ely7xrn7l4ixj"

def get_dbx():
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    try:
        return dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=APP_KEY,
            app_secret=APP_SECRET
        )
    except: return None

def render_setlist_html(setlist):
    html = ""
    for i, song in enumerate(setlist):
        html += f'''
        <div class="item">
            <span>{i+1}. {song}</span>
            <button class="btn-rem" hx-post="/remove" hx-vals='{{"song": "{song}"}}' hx-target="#setlist-inner">×</button>
        </div>'''
    return html if setlist else '<p style="color:#999;">No songs selected.</p>'

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <!-- REVISED HTMX LINK -->
    <script src="https://jsdelivr.net"></script>
    <style>
        body { font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px; background: #f4f4f4; }
        .card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: white; margin-bottom: 20px; }
        .item { display: flex; justify-content: space-between; padding: 10px; border-bottom: 1px solid #eee; align-items: center; }
        .btn-add { background: #28a745; color: white; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; }
        .btn-rem { background: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; }
        .build-btn { width: 100%; padding: 15px; background: #007bff; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 18px; cursor: pointer; }
        select, input { width: 100%; padding: 12px; margin-bottom: 10px; border-radius: 4px; border: 1px solid #ccc; box-sizing: border-box; }
        #debug-log { background: #222; color: #0f0; padding: 10px; font-family: monospace; font-size: 11px; border-radius: 5px; height: 100px; overflow-y: auto; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>🎺 POW Set Builder</h1>
    
    <div class="card">
        <h3>1. Select Set Folder</h3>
        <select name="folder_path" hx-post="/update-library" hx-target="#library-container">
            <option value="">-- Choose a Set --</option>
            {% for folder in folders %}
            <option value="{{ folder.path_lower }}">{{ folder.name }}</option>
            {% endfor %}
        </select>
    </div>

    <div class="card">
        <h3>2. Library (Click +)</h3>
        <div id="library-container" style="max-height: 250px; overflow-y: auto;">
            <p style="color:#999;">Select a Set above.</p>
        </div>
    </div>

    <div class="card">
        <h3>3. Your Setlist</h3>
        <div id="setlist-inner">{{ setlist_html|safe }}</div>
    </div>

    <form action="/build" method="POST">
        <input type="hidden" id="active_folder" name="active_folder" value="">
        <input type="text" name="set_name" placeholder="Output Folder Name" required>
        <button class="build-btn" type="submit">BUILD ALL PARTS</button>
    </form>

    <div id="debug-log">
        <strong>Debug Console:</strong><br>
        <div id="log-content">App Initialised... Waiting for user.</div>
    </div>

    <script>
        // Log every HTMX request and error to the green screen
        document.body.addEventListener('htmx:beforeRequest', function(evt) {
            document.getElementById('log-content').innerHTML += '<br>> Sending request to ' + evt.detail.path;
        });
        document.body.addEventListener('htmx:afterRequest', function(evt) {
            if (evt.detail.target.id === 'library-container') {
                document.getElementById('active_folder').value = document.querySelector('select[name="folder_path"]').value;
                document.getElementById('log-content').innerHTML += '<br>> Library updated successfully.';
            }
        });
        document.body.addEventListener('htmx:responseError', function(evt) {
            document.getElementById('log-content').innerHTML += '<br><span style="color:red;">> ERROR: ' + evt.detail.xhr.status + '</span>';
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    dbx = get_dbx()
    session.setdefault('setlist', [])
    folders = []
    if dbx:
        try:
            res = dbx.files_list_folder("")
            folders = sorted([e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata) and e.name.lower() != "generated"], key=lambda x: x.name)
        except: pass
    return render_template_string(HTML_TEMPLATE, folders=folders, setlist_html=render_setlist_html(session['setlist']))

@app.route('/update-library', methods=['POST'])
def update_library():
    dbx = get_dbx()
    path = request.form.get('folder_path')
    html = ""
    if dbx and path:
        try:
            res = dbx.files_list_folder(path)
            # Find any subfolder that isn't a file
            subs = [e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata)]
            if subs:
                songs = dbx.files_list_folder(subs[0].path_lower).entries
                pdf_names = sorted([s.name for s in songs if s.name.lower().endswith('.pdf')])
                for name in pdf_names:
                    html += f'''<div class="item"><span>{name}</span><button class="btn-add" hx-post="/add" hx-vals='{{"song": "{name}"}}' hx-target="#setlist-inner">+</button></div>'''
            else: html = "<p>No instrument folders found.</p>"
        except Exception as e: html = f"<p style='color:red;'>Dropbox Error: {e}</p>"
    return html

@app.route('/add', methods=['POST'])
def add_song():
    song = request.form.get('song')
    lst = session.get('setlist', [])
    if song and song not in lst:
        lst.append(song)
        session['setlist'] = lst
    return render_setlist_html(session['setlist'])

@app.route('/remove', methods=['POST'])
def remove_song():
    song = request.form.get('song')
    lst = session.get('setlist', [])
    if song in lst:
        lst.remove(song)
        session['setlist'] = lst
    return render_setlist_html(session['setlist'])

@app.route('/build', methods=['POST'])
def build():
    dbx = get_dbx()
    setlist = session.get('setlist', [])
    set_name = request.form.get('set_name')
    active_folder = request.form.get('active_folder')
    if not setlist or not dbx or not active_folder: return "Error: Select set/add songs."
    try:
        res = dbx.files_list_folder(active_folder)
        folders = [e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata)]
        for f in folders:
            writer = PdfWriter()
            items = dbx.files_list_folder(f.path_lower).entries
            pdf_map = {e.name.lower(): e.path_lower for e in items if e.name.lower().endswith('.pdf')}
            for song in setlist:
                if song.lower() in pdf_map:
                    _, r = dbx.files_download(pdf_map[song.lower()])
                    writer.append(io.BytesIO(r.content))
            out = io.BytesIO()
            writer.write(out)
            out.seek(0)
            dbx.files_upload(out.read(), f"/Generated/{set_name}/{f.name}.pdf", mode=dropbox.files.WriteMode.overwrite)
        session['setlist'] = []
        return f"<h1>Success!</h1><p>Created in /Generated/{set_name}</p><a href='/'>Back</a>"
    except Exception as e: return f"<h1>Error</h1><p>{str(e)}</p>"

if __name__ == '__main__':
    app.run()

import os, io, dropbox, re
from flask import Flask, render_template_string, request, session
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "pow-band-2026-secure")

# Your App Credentials
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

# --- UI TEMPLATES ---
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <!-- FIXED HTMX LINK BELOW -->
    <script src="https://unpkg.com"></script>
    <style>
        body { font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px; background: #f4f4f4; }
        .card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: white; margin-bottom: 20px; }
        .item { display: flex; justify-content: space-between; padding: 10px; border-bottom: 1px solid #eee; align-items: center; }
        .btn-add { background: #28a745; color: white; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; }
        .btn-rem { background: #dc3545; color: white; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; }
        .btn-clear { background: #6c757d; color: white; border: none; padding: 10px; border-radius: 4px; cursor: pointer; width: 100%; margin-top: 10px; }
        .build-btn { width: 100%; padding: 15px; background: #007bff; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 18px; cursor: pointer; }
        select, input { width: 100%; padding: 12px; margin-bottom: 10px; border-radius: 4px; border: 1px solid #ccc; box-sizing: border-box; }
        .status-box { font-size: 11px; background: #333; color: #0f0; padding: 10px; border-radius: 5px; margin-top: 20px; font-family: monospace; }
    </style>
</head>
<body>
    <h1>🎺 POW Set Builder</h1>
    
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
        <h3>2. Library (Click +)</h3>
        <div id="library-container" style="max-height: 300px; overflow-y: auto;">
            <p style="color:#999;">Select a Set above to load music.</p>
        </div>
    </div>

    <div class="card">
        <h3>3. Your Setlist</h3>
        <div id="setlist-inner">
            {% for song in setlist %}
            <div class="item">
                <span>{{ loop.index }}. {{ song }}</span>
                <button class="btn-rem" hx-post="/remove" hx-vals='{"song": "{{ song }}"}' hx-target="#setlist-inner">−</button>
            </div>
            {% endfor %}
            {% if not setlist %}<p style="color:#999;">No songs selected.</p>{% endif %}
        </div>
        <button class="btn-clear" hx-post="/clear" hx-target="#setlist-inner">Clear Setlist</button>
    </div>

    <form action="/build" method="POST">
        <input type="hidden" id="active_folder" name="active_folder" value="">
        <input type="text" name="set_name" placeholder="Output Folder Name" required>
        <button class="build-btn" type="submit">BUILD 19 INSTRUMENT PARTS</button>
    </form>

    <div class="status-box"><strong>Status:</strong> {{ status }}</div>

    <script>
        document.body.addEventListener('htmx:afterRequest', function(evt) {
            if (evt.detail.target.id === 'library-container') {
                document.getElementById('active_folder').value = document.querySelector('select[name="folder_path"]').value;
            }
        });
    </script>
</body>
</html>
'''

LIBRARY_PARTIAL = '''
{% for song in library %}
<div class="item">
    <span>{{ song }}</span>
    <button class="btn-add" hx-post="/add" hx-vals='{"song": "{{ song }}"}' hx-target="#setlist-inner">+</button>
</div>
{% endfor %}
{% if not library %}<p style="color:#999;">No PDFs found in this Set.</p>{% endif %}
'''

INNER_TEMPLATE = '''
{% for song in setlist %}
<div class="item">
    <span>{{ loop.index }}. {{ song }}</span>
    <button class="btn-rem" hx-post="/remove" hx-vals='{"song": "{{ song }}"}' hx-target="#setlist-inner">−</button>
</div>
{% endfor %}
{% if not setlist %}<p style="color:#999;">No songs selected.</p>{% endif %}
'''

@app.route('/')
def index():
    dbx = get_dbx()
    session.setdefault('setlist', [])
    folders, status = [], "Connecting..."
    if dbx:
        try:
            res = dbx.files_list_folder("")
            folders = sorted([e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata) and e.name.lower() != "generated"], key=lambda x: x.name)
            status = f"Connected! Found {len(folders)} sets." if folders else "Connected, but root is empty."
        except Exception as e: status = f"Error: {e}"
    else: status = "Error: DROPBOX_REFRESH_TOKEN missing."
    return render_template_string(HTML_TEMPLATE, folders=folders, setlist=session['setlist'], status=status)

@app.route('/update-library', methods=['POST'])
def update_library():
    dbx = get_dbx()
    folder_path = request.form.get('folder_path')
    library = []
    if dbx and folder_path:
        try:
            res = dbx.files_list_folder(folder_path)
            subs = [e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata)]
            if subs:
                # Scans the first instrument folder (e.g., Soprano) to build the song list
                songs_res = dbx.files_list_folder(subs[0].path_lower)
                library = sorted([s.name for s in songs_res.entries if s.name.lower().endswith('.pdf')])
        except Exception as e:
            return f"<p style='color:red;'>Error reading folder: {e}</p>"
    return render_template_string(LIBRARY_PARTIAL, library=library)

@app.route('/add', methods=['POST'])
def add_song():
    song, lst = request.form.get('song'), session.get('setlist', [])
    if song and song not in lst:
        lst.append(song); session['setlist'] = lst; session.modified = True
    return render_template_string(INNER_TEMPLATE, setlist=lst)

@app.route('/remove', methods=['POST'])
def remove_song():
    song, lst = request.form.get('song'), session.get('setlist', [])
    if song in lst:
        lst.remove(song); session['setlist'] = lst; session.modified = True
    return render_template_string(INNER_TEMPLATE, setlist=lst)

@app.route('/clear', methods=['POST'])
def clear_list():
    session['setlist'] = []
    session.modified = True
    return render_template_string(INNER_TEMPLATE, setlist=[])

@app.route('/build', methods=['POST'])
def build():
    dbx = get_dbx()
    setlist, set_name = session.get('setlist', []), request.form.get('set_name')
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
        return f"<h1>Success!</h1><p>Check Dropbox: /Generated/{set_name}</p><a href='/'>Back</a>"
    except Exception as e: return f"<h1>Error</h1><p>{str(e)}</p>"

if __name__ == '__main__':
    app.run()

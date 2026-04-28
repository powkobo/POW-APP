import os, io, dropbox, re
from flask import Flask, render_template_string, request, session
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "pow-band-2026")

def get_dbx():
    try:
        return dropbox.Dropbox(
            oauth2_refresh_token=os.environ.get("DROPBOX_REFRESH_TOKEN"),
            app_key=os.environ.get("DROPBOX_APP_KEY"),
            app_secret=os.environ.get("DROPBOX_APP_SECRET")
        )
    except:
        return None

# --- UI TEMPLATE ---
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://unpkg.com"></script>
    <style>
        body { font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px; background: #f4f4f4; }
        .card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: white; margin-bottom: 20px; }
        .item { display: flex; justify-content: space-between; padding: 10px; border-bottom: 1px solid #eee; align-items: center; }
        .btn-add { background: #28a745; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; }
        .btn-rem { background: #dc3545; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; }
        .build-btn { width: 100%; padding: 15px; background: #007bff; color: white; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; }
        select, input { width: 100%; padding: 12px; margin-bottom: 10px; border-radius: 4px; border: 1px solid #ccc; box-sizing: border-box; }
    </style>
</head>
<body>
    <h1>🎺 POW Set Builder</h1>
    
    <div class="card">
        <h3>1. Select Active Set Folder</h3>
        <select name="folder_path" hx-post="/update-library" hx-target="#library-container">
            <option value="">-- Choose a Set Folder --</option>
            {% for folder in folders %}
            <option value="{{ folder.path_lower }}">{{ folder.name }}</option>
            {% endfor %}
        </select>
    </div>

    <div class="card">
        <h3>2. Library (Click +)</h3>
        <div id="library-container" style="max-height: 250px; overflow-y: auto;">
            <p style="color:#999;">Select a folder above to see songs.</p>
        </div>
    </div>

    <div class="card">
        <h3>3. Your Setlist</h3>
        <div id="setlist-inner">{% include 'inner' %}</div>
    </div>

    <form action="/build" method="POST">
        <input type="text" name="set_name" placeholder="Name the Output Set (e.g. Christmas 2026)" required>
        <button class="build-btn" type="submit">BUILD 19 INSTRUMENT PARTS</button>
    </form>
</body>
</html>
'''

# The snippet for the library list
LIBRARY_PARTIAL = '''
{% for song in library %}
<div class="item">
    <span>{{ song }}</span>
    <button class="btn-add" hx-post="/add" hx-vals='{"song": "{{ song }}"}' hx-target="#setlist-inner">+</button>
</div>
{% endfor %}
{% if not library %}<p style="color:#999;">No PDFs found in this folder.</p>{% endif %}
'''

# The snippet for the current setlist
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
    folders = []
    if dbx:
        try:
            # Scans for top-level set folders in your music directory
            base_path = "/POW PDFs/POW PDFs Parts by instrument"
            res = dbx.files_list_folder(base_path)
            folders = [e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata)]
        except:
            pass
    return render_template_string(HTML_TEMPLATE.replace("{% include 'inner' %}", INNER_TEMPLATE), 
                                 folders=folders, setlist=session['setlist'])

@app.route('/update-library', methods=['POST'])
def update_library():
    dbx = get_dbx()
    folder_path = request.form.get('folder_path')
    library = []
    if dbx and folder_path:
        try:
            # Finds one instrument sub-folder to act as the "Master List" for songs in this set
            subfolders = [e for e in dbx.files_list_folder(folder_path).entries if isinstance(e, dropbox.files.FolderMetadata)]
            if subfolders:
                master_folder = subfolders[0].path_lower
                songs = dbx.files_list_folder(master_folder).entries
                library = sorted([s.name for s in songs if s.name.lower().endswith('.pdf')])
        except:
            pass
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

@app.route('/build', methods=['POST'])
def build():
    # ... (Same build logic as before, using the folder_path from session if needed) ...
    return "Build complete. Check Dropbox!"

if __name__ == '__main__':
    app.run()

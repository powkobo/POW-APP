import os, io, dropbox, re
from flask import Flask, render_template_string, request, session
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "pow-band-2026")

# Global Dropbox client setup
def get_dropbox():
    try:
        return dropbox.Dropbox(
            oauth2_refresh_token=os.environ.get("DROPBOX_REFRESH_TOKEN"),
            app_key=os.environ.get("DROPBOX_APP_KEY"),
            app_secret=os.environ.get("DROPBOX_APP_SECRET")
        )
    except:
        return None

# --- UI TEMPLATES ---
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://unpkg.com"></script>
    <style>
        body { font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px; background: #f4f4f4; }
        .card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: white; margin-bottom: 20px; }
        .item { display: flex; justify-content: space-between; padding: 12px; border-bottom: 1px solid #eee; align-items: center; }
        .btn-add { background: #28a745; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; }
        .btn-rem { background: #dc3545; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; }
        .build-btn { width: 100%; padding: 15px; background: #007bff; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 18px; cursor: pointer; }
    </style>
</head>
<body>
    <h1>🎺 POW Set Builder</h1>
    <div class="card">
        <h3>1. Library (Click + to add)</h3>
        <div style="max-height: 300px; overflow-y: auto;">
            {% for song in library %}
            <div class="item">
                <span>{{ song }}</span>
                <button class="btn-add" hx-post="/add" hx-vals='{"song": "{{ song }}"}' hx-target="#setlist-container">+</button>
            </div>
            {% endfor %}
            {% if not library %}<p style="color:red;">Error: No library found. Check Dropbox path.</p>{% endif %}
        </div>
    </div>
    <div class="card">
        <h3>2. Your Setlist</h3>
        <div id="setlist-container">{% include 'inner' %}</div>
    </div>
    <form action="/build" method="POST">
        <input type="text" name="set_name" placeholder="Set Name (e.g. Summer Tour)" required style="width:100%; padding:12px; margin-bottom:15px; box-sizing:border-box;">
        <button class="build-btn" type="submit">BUILD 19 INSTRUMENT PARTS</button>
    </form>
</body>
</html>
'''

SETLIST_INNER = '''
{% for song in setlist %}
<div class="item">
    <span><strong>{{ loop.index }}.</strong> {{ song }}</span>
    <button class="btn-rem" hx-post="/remove" hx-vals='{"song": "{{ song }}"}' hx-target="#setlist-container">−</button>
</div>
{% endfor %}
{% if not setlist %}<p style="color:#999;">No songs selected.</p>{% endif %}
'''

# --- ROUTES ---
@app.route('/')
def index():
    dbx = get_dropbox()
    if 'setlist' not in session: session['setlist'] = []
    
    # AGNOSTIC PATH SEARCH: Find the first folder inside your Parts directory
    library = []
    if dbx:
        try:
            base_dir = "/POW PDFs/POW PDFs Parts by instrument"
            # Get the first subfolder to use as the master song list
            entries = dbx.files_list_folder(base_dir).entries
            first_folder = next(e for e in entries if isinstance(e, dropbox.files.FolderMetadata))
            
            # List songs in that first folder
            songs = dbx.files_list_folder(first_folder.path_lower).entries
            library = sorted([s.name for s in songs if s.name.lower().endswith('.pdf')])
        except Exception as e:
            print(f"Library Error: {e}")

    return render_template_string(HTML_TEMPLATE, library=library, setlist=session['setlist'])

@app.route('/add', methods=['POST'])
def add_song():
    song, lst = request.form.get('song'), session.get('setlist', [])
    if song and song not in lst:
        lst.append(song)
        session['setlist'] = lst
    return render_template_string(SETLIST_INNER, setlist=lst)

@app.route('/remove', methods=['POST'])
def remove_song():
    song, lst = request.form.get('song'), session.get('setlist', [])
    if song in lst:
        lst.remove(song)
        session['setlist'] = lst
    return render_template_string(SETLIST_INNER, setlist=lst)

@app.route('/build', methods=['POST'])
def build():
    dbx = get_dropbox()
    setlist, set_name = session.get('setlist', []), request.form.get('set_name')
    if not setlist or not dbx: return "Error: Data missing."
    
    try:
        base = "/POW PDFs/POW PDFs Parts by instrument"
        folders = [f for f in dbx.files_list_folder(base).entries if isinstance(f, dropbox.files.FolderMetadata)]
        for f in folders:
            writer = PdfWriter()
            inst_files = {e.name: e.path_lower for e in dbx.files_list_folder(f.path_lower).entries}
            for song in setlist:
                if song in inst_files:
                    _, res = dbx.files_download(inst_files[song])
                    writer.append(io.BytesIO(res.content))
            out = io.BytesIO()
            writer.write(out)
            out.seek(0)
            dbx.files_upload(out.read(), f"/Generated Sets/{set_name}/{f.name}.pdf", mode=dropbox.files.WriteMode.overwrite)
        
        session['setlist'] = []
        return f"<h1>Success!</h1><p>Created in Dropbox: /Generated Sets/{set_name}</p><a href='/'>Back</a>"
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p><a href='/'>Try Again</a>"

if __name__ == '__main__':
    app.run()

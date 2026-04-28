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
        .item { display: flex; justify-content: space-between; padding: 10px; border-bottom: 1px solid #eee; align-items: center; }
        .btn-add { background: #28a745; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; }
        .btn-rem { background: #dc3545; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; }
        .build-btn { width: 100%; padding: 15px; background: #007bff; color: white; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; }
        .error { background: #fee; color: #b00; padding: 10px; border: 1px solid #b00; border-radius: 4px; margin-bottom: 10px; font-size: 14px; }
        .debug { font-size: 10px; color: #999; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>🎺 POW Set Builder</h1>
    
    {% if error %}
    <div class="error"><strong>Notice:</strong> {{ error }}</div>
    {% endif %}

    <div class="card">
        <h3>1. Library (Click +)</h3>
        <div style="max-height: 250px; overflow-y: auto;">
            {% for song in library %}
            <div class="item">
                <span>{{ song }}</span>
                <button class="btn-add" hx-post="/add" hx-vals='{"song": "{{ song }}"}' hx-target="#setlist-inner">+</button>
            </div>
            {% endfor %}
            {% if not library and not error %}<p>Searching for instrument folders...</p>{% endif %}
        </div>
    </div>

    <div class="card">
        <h3>2. Your Setlist</h3>
        <div id="setlist-inner">{% include 'inner' %}</div>
    </div>

    <form action="/build" method="POST">
        <input type="text" name="set_name" placeholder="Set Name (e.g. Christmas)" required style="width:100%; padding:12px; margin-bottom:15px; box-sizing:border-box;">
        <button class="build-btn" type="submit">BUILD 19 INSTRUMENT PARTS</button>
    </form>
</body>
</html>
'''

INNER_TEMPLATE = '''
{% for song in setlist %}
<div class="item">
    <span><strong>{{ loop.index }}.</strong> {{ song }}</span>
    <button class="btn-rem" hx-post="/remove" hx-vals='{"song": "{{ song }}"}' hx-target="#setlist-inner">−</button>
</div>
{% endfor %}
{% if not setlist %}<p style="color:#999;">No songs selected.</p>{% endif %}
'''

def scan_for_library(dbx, path):
    """Recursively looks for a folder that contains PDFs to build the library."""
    try:
        res = dbx.files_list_folder(path)
        entries = res.entries
        
        # 1. Check if this folder itself has PDFs
        pdfs = sorted([e.name for e in entries if e.name.lower().endswith('.pdf')])
        if pdfs:
            return pdfs, path
        
        # 2. If not, look inside subfolders (like 01-Soprano Cornet)
        for e in entries:
            if isinstance(e, dropbox.files.FolderMetadata):
                sub_pdfs, sub_path = scan_for_library(dbx, e.path_lower)
                if sub_pdfs:
                    return sub_pdfs, path # Return the 'parent' path where all instrument folders are
        return [], None
    except:
        return [], None

@app.route('/')
def index():
    dbx = get_dbx()
    session.setdefault('setlist', [])
    library, error = [], None

    if not dbx:
        error = "Credentials missing in Render."
    else:
        # Start scanning from the root to find your music
        library, parent_path = scan_for_library(dbx, "")
        if parent_path:
            session['music_root'] = parent_path
        else:
            error = "Could not find any folders containing PDFs. Please check your Dropbox."

    return render_template_string(HTML_TEMPLATE.replace("{% include 'inner' %}", INNER_TEMPLATE), 
                                 library=library, setlist=session['setlist'], error=error)

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
    dbx = get_dbx()
    setlist, set_name = session.get('setlist', []), request.form.get('set_name')
    root = session.get('music_root', "")
    
    if not setlist or not dbx: return "Error: Data missing."
    
    try:
        # Get all 19 instrument folders in the root we found
        res = dbx.files_list_folder(root)
        folders = [e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata)]
        
        for f in folders:
            writer = PdfWriter()
            # Map PDFs in this specific instrument folder
            items = dbx.files_list_folder(f.path_lower).entries
            inst_files = {e.name: e.path_lower for e in items if e.name.lower().endswith('.pdf')}
            
            for song in setlist:
                if song in inst_files:
                    _, res_file = dbx.files_download(inst_files[song])
                    writer.append(io.BytesIO(res_file.content))
            
            out = io.BytesIO()
            writer.write(out)
            out.seek(0)
            dbx.files_upload(out.read(), f"/Generated Sets/{set_name}/{f.name}.pdf", mode=dropbox.files.WriteMode.overwrite)
        
        session['setlist'] = []
        return f"<h1>Success!</h1><p>Created: /Generated Sets/{set_name}</p><a href='/'>Back</a>"
    except Exception as e:
        return f"<h1>Build Error</h1><p>{str(e)}</p><a href='/'>Back</a>"

if __name__ == '__main__':
    app.run()

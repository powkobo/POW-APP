import os, io, dropbox, re
from flask import Flask, render_template_string, request, session
from pypdf import PdfWriter
from rapidfuzz import fuzz, process

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "pow-set-builder-2026")

# Connect to Dropbox
try:
    dbx = dropbox.Dropbox(
        oauth2_refresh_token=os.environ.get("DROPBOX_REFRESH_TOKEN"),
        app_key=os.environ.get("DROPBOX_APP_KEY"),
        app_secret=os.environ.get("DROPBOX_APP_SECRET")
    )
except Exception as e:
    dbx = None

def normalize(text):
    return re.sub(r"\s+", " ", re.sub(r"[_\-\(\)\[\]\{\},]+", " ", text.lower())).strip()

# Complete, single-file HTML template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://unpkg.com"></script>
    <style>
        body { font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px; background: #f9f9f9; }
        .card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: white; margin-bottom: 20px; }
        .song-item { display: flex; justify-content: space-between; padding: 10px; border-bottom: 1px solid #eee; }
        .btn-add { color: #28a745; font-weight: bold; cursor: pointer; padding: 0 10px; }
        .btn-rem { color: #dc3545; font-weight: bold; cursor: pointer; padding: 0 10px; }
        .main-btn { width: 100%; padding: 15px; background: #b30000; color: white; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; }
    </style>
</head>
<body>
    <h1>🎺 POW Set Builder</h1>
    <div class="card">
        <h3>Search Library</h3>
        <input type="text" name="q" placeholder="Type song name..." 
               hx-post="/search" hx-trigger="keyup changed delay:500ms" hx-target="#search-results" style="width:100%; padding:12px; box-sizing:border-box;">
        <div id="search-results" style="margin-top:10px;"></div>
    </div>

    <div class="card">
        <h3>Current Setlist</h3>
        <div id="current-setlist">
            {% for song in setlist %}
            <div class="song-item">
                <span>{{ song }}</span>
                <span class="btn-rem" hx-post="/remove" hx-vals='{"song": "{{ song }}"}' hx-target="#current-setlist">−</span>
            </div>
            {% endfor %}
            {% if not setlist %}<p style="color:#999;">List is empty</p>{% endif %}
        </div>
    </div>

    <form action="/build" method="POST">
        <input type="text" name="set_name" placeholder="Set Name (e.g. Tour 2026)" required style="width:100%; padding:12px; margin-bottom:10px; box-sizing:border-box;">
        <button class="main-btn" type="submit">BUILD 19 INSTRUMENT PARTS</button>
    </form>
</body>
</html>
'''

@app.route('/')
def index():
    if 'setlist' not in session: session['setlist'] = []
    return render_template_string(HTML_TEMPLATE, setlist=session['setlist'])

@app.route('/search', methods=['POST'])
def search():
    query = normalize(request.form.get('q', ''))
    if not query or not dbx: return ""
    
    # Update this path to a folder that DEFINITELY exists in your Dropbox
    base = "/POW PDFs/POW PDFs Parts by instrument/01-Soprano Cornet"
    try:
        files = [f.name for f in dbx.files_list_folder(base).entries if f.name.lower().endswith('.pdf')]
        matches = process.extract(query, files, limit=5, scorer=fuzz.token_set_ratio)
        res = ""
        for name, score, idx in matches:
            if score > 50:
                res += f'<div class="song-item"><span>{name}</span><span class="btn-add" hx-post="/add" hx-vals=\'{{"song": "{name}"}}\' hx-target="#current-setlist">+</span></div>'
        return res
    except Exception as e:
        return f"<div>Error: {str(e)}</div>"

@app.route('/add', methods=['POST'])
def add_song():
    song, lst = request.form.get('song'), session.get('setlist', [])
    if song and song not in lst: 
        lst.append(song)
        session['setlist'] = lst
    # Manually re-rendering the list part since we removed the partial file
    res = ""
    for s in lst:
        res += f'<div class="song-item"><span>{s}</span><span class="btn-rem" hx-post="/remove" hx-vals=\'{{"song": "{s}"}}\' hx-target="#current-setlist">−</span></div>'
    return res

@app.route('/remove', methods=['POST'])
def remove_song():
    song, lst = request.form.get('song'), session.get('setlist', [])
    if song in lst: 
        lst.remove(song)
        session['setlist'] = lst
    res = ""
    for s in lst:
        res += f'<div class="song-item"><span>{s}</span><span class="btn-rem" hx-post="/remove" hx-vals=\'{{"song": "{s}"}}\' hx-target="#current-setlist">−</span></div>'
    return res or '<p style="color:#999;">List is empty</p>'

@app.route('/build', methods=['POST'])
def build():
    setlist, set_name = session.get('setlist', []), request.form.get('set_name')
    if not setlist or not dbx: return "Error: Missing setlist or Dropbox connection."
    
    try:
        base_lib = "/POW PDFs/POW PDFs Parts by instrument"
        folders = [f for f in dbx.files_list_folder(base_lib).entries if isinstance(f, dropbox.files.FolderMetadata)]
        
        for folder in folders:
            writer = PdfWriter()
            inst_files = {f.name: f.path_lower for f in dbx.files_list_folder(folder.path_lower).entries}
            for song in setlist:
                if song in inst_files:
                    _, res = dbx.files_download(inst_files[song])
                    writer.append(io.BytesIO(res.content))
            out = io.BytesIO()
            writer.write(out)
            out.seek(0)
            dbx.files_upload(out.read(), f"/Generated Sets/{set_name}/{folder.name}.pdf", mode=dropbox.files.WriteMode.overwrite)
        
        session['setlist'] = []
        return f"<h1>Success!</h1><p>Parts built in Dropbox: /Generated Sets/{set_name}</p><a href='/'>Back</a>"
    except Exception as e:
        return f"<h1>Build Error</h1><p>{str(e)}</p><a href='/'>Back</a>"

if __name__ == '__main__':
    app.run()

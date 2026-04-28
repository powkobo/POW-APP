import os, io, dropbox, re
from flask import Flask, render_template_string, request, session
from pypdf import PdfWriter
from rapidfuzz import fuzz, process

app = Flask(__name__)
app.secret_key = "pow_band_secret" # Needed for the +/- session memory

# Dropbox Connection (Uses your Refresh Token logic)
dbx = dropbox.Dropbox(
    oauth2_refresh_token=os.environ.get("DROPBOX_REFRESH_TOKEN"),
    app_key=os.environ.get("DROPBOX_APP_KEY"),
    app_secret=os.environ.get("DROPBOX_APP_SECRET")
)

def normalize(text):
    return re.sub(r"\s+", " ", re.sub(r"[_\-\(\)\[\]\{\},]+", " ", text.lower())).strip()

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://unpkg.com"></script>
    <style>
        body { font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; background: #fdfdfd; }
        .card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: white; margin-bottom: 20px; }
        .song-item { display: flex; justify-content: space-between; padding: 8px; border-bottom: 1px solid #eee; }
        .btn-add { color: green; font-weight: bold; cursor: pointer; }
        .btn-rem { color: red; font-weight: bold; cursor: pointer; }
        button.main { width: 100%; padding: 15px; background: #b30000; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 16px; cursor: pointer; }
    </style>
</head>
<body>
    <h1>🎺 POW Set Builder</h1>

    <div class="card">
        <h3>1. Search Library</h3>
        <input type="text" name="q" placeholder="Search song name..." 
               hx-post="/search" hx-trigger="keyup changed delay:500ms" hx-target="#search-results" style="width:100%; padding:10px;">
        <div id="search-results" style="margin-top:10px;"></div>
    </div>

    <div class="card">
        <h3>2. Current Setlist</h3>
        <div id="current-setlist">
            <!-- This part updates dynamically -->
            {% include 'setlist_partial.html' %}
        </div>
    </div>

    <form action="/build" method="POST">
        <input type="text" name="set_name" placeholder="Set Name (e.g. Christmas 2024)" required style="width:100%; padding:10px; margin-bottom:10px;">
        <button class="main" type="submit">BUILD 19 INSTRUMENT PARTS</button>
    </form>
</body>
</html>
'''

# Helper to render the setlist part
SETLIST_PARTIAL = '''
{% for song in setlist %}
<div class="song-item">
    <span>{{ song }}</span>
    <span class="btn-rem" hx-post="/remove" hx-vals='{"song": "{{ song }}"}' hx-target="#current-setlist">−</span>
</div>
{% endfor %}
{% if not setlist %}<p style="color:#999;">Setlist is empty</p>{% endif %}
'''

@app.route('/')
def index():
    if 'setlist' not in session: session['setlist'] = []
    return render_template_string(HTML_TEMPLATE, setlist=session['setlist'])

@app.route('/search', methods=['POST'])
def search():
    query = normalize(request.form.get('q', ''))
    if not query: return ""
    
    # Scans one instrument folder just to get song titles (Agnostic approach)
    base_path = "/POW PDFs/POW PDFs Parts by instrument/01-Soprano Cornet"
    files = [f.name for f in dbx.files_list_folder(base_path).entries if f.name.lower().endswith('.pdf')]
    
    matches = process.extract(query, files, limit=5, scorer=fuzz.token_set_ratio)
    
    results_html = ""
    for name, score, idx in matches:
        if score > 50:
            results_html += f'''
            <div class="song-item">
                <span>{name}</span>
                <span class="btn-add" hx-post="/add" hx-vals='{{"song": "{name}"}}' hx-target="#current-setlist">+</span>
            </div>'''
    return results_html

@app.route('/add', methods=['POST'])
def add_song():
    song = request.form.get('song')
    lst = session.get('setlist', [])
    if song not in lst: lst.append(song)
    session['setlist'] = lst
    return render_template_string(SETLIST_PARTIAL, setlist=lst)

@app.route('/remove', methods=['POST'])
def remove_song():
    song = request.form.get('song')
    lst = session.get('setlist', [])
    if song in lst: lst.remove(song)
    session['setlist'] = lst
    return render_template_string(SETLIST_PARTIAL, setlist=lst)

@app.route('/build', methods=['POST'])
def build():
    setlist = session.get('setlist', [])
    set_name = request.form.get('set_name')
    base_lib = "/POW PDFs/POW PDFs Parts by instrument"
    
    # 1. Get all 19 instrument folders
    folders = [f for f in dbx.files_list_folder(base_lib).entries if isinstance(f, dropbox.files.FolderMetadata)]
    
    for folder in folders:
        writer = PdfWriter()
        # Find the songs in THIS instrument folder
        inst_files = {f.name: f.path_lower for f in dbx.files_list_folder(folder.path_lower).entries}
        
        for song_name in setlist:
            if song_name in inst_files:
                _, res = dbx.files_download(inst_files[song_name])
                writer.append(io.BytesIO(res.content))
        
        # Save to Generated Sets
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        dbx.files_upload(output.read(), f"/Generated Sets/{set_name}/{folder.name}.pdf", mode=dropbox.files.WriteMode.overwrite)

    session['setlist'] = [] # Clear for next time
    return f"<h1>Success!</h1><p>Created 19 parts in /Generated Sets/{set_name}</p><a href='/'>Back to Builder</a>"

if __name__ == '__main__':
    app.run()

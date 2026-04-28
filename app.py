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

# Combined Template
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
        .error { color: #b00; background: #fee; padding: 10px; border-radius: 4px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <h1>🎺 POW Set Builder</h1>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}

    <div class="card">
        <h3>1. Library (Click +)</h3>
        <div style="max-height: 250px; overflow-y: auto;">
            {% for song in library %}
            <div class="item">
                <span>{{ song }}</span>
                <button class="btn-add" hx-post="/add" hx-vals='{"song": "{{ song }}"}' hx-target="#setlist-inner">+</button>
            </div>
            {% endfor %}
        </div>
    </div>

    <div class="card">
        <h3>2. Your Setlist</h3>
        <div id="setlist-inner">{% include 'inner' %}</div>
    </div>

    <form action="/build" method="POST">
        <input type="text" name="set_name" placeholder="Set Name (e.g. Tour 2026)" required style="width:100%; padding:12px; margin-bottom:15px; box-sizing:border-box;">
        <button class="build-btn" type="submit">BUILD 19 INSTRUMENT PARTS</button>
    </form>
</body>
</html>
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
    library, error = [], None

    if not dbx:
        error = "Dropbox keys missing in Render Settings."
    else:
        try:
            # We try a simpler path approach
            path = "/pow pdfs/pow pdfs parts by instrument"
            
            # 1. List folders in that path
            folders = dbx.files_list_folder(path).entries
            # 2. Pick the first folder found (e.g. 01-Soprano Cornet)
            first_folder = next(f for f in folders if isinstance(f, dropbox.files.FolderMetadata))
            # 3. List PDFs in that folder to populate the master library
            songs = dbx.files_list_folder(first_folder.path_lower).entries
            library = sorted([s.name for s in songs if s.name.lower().endswith('.pdf')])
        except Exception as e:
            error = f"Path error: {str(e)}. Make sure your Dropbox folder is named correctly."

    return render_template_string(HTML_TEMPLATE.replace("{% include 'inner' %}", INNER_TEMPLATE), 
                                 library=library, setlist=session['setlist'], error=error)

@app.route('/add', methods=['POST'])
def add_song():
    song = request.form.get('song')
    lst = session.get('setlist', [])
    if song and song not in lst:
        lst.append(song)
        session['setlist'] = lst
        session.modified = True
    return render_template_string(INNER_TEMPLATE, setlist=lst)

@app.route('/remove', methods=['POST'])
def remove_song():
    song = request.form.get('song')
    lst = session.get('setlist', [])
    if song in lst:
        lst.remove(song)
        session['setlist'] = lst
        session.modified = True
    return render_template_string(INNER_TEMPLATE, setlist=lst)

@app.route('/build', methods=['POST'])
def build():
    dbx = get_dbx()
    setlist = session.get('setlist', [])
    set_name = request.form.get('set_name')
    if not setlist or not dbx: return "Error: Missing data."
    
    try:
        base_path = "/pow pdfs/pow pdfs parts by instrument"
        folders = [f for f in dbx.files_list_folder(base_path).entries if isinstance(f, dropbox.files.FolderMetadata)]
        
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
        return f"<h1>Success!</h1><p>Created in Dropbox: /Generated Sets/{set_name}</p><a href='/'>Back</a>"
    except Exception as e:
        return f"<h1>Build Error</h1><p>{str(e)}</p><a href='/'>Try Again</a>"

if __name__ == '__main__':
    app.run()

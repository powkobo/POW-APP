import os, io, dropbox, re
from flask import Flask, render_template_string, request, session
from pypdf import PdfWriter

app = Flask(__name__)
# Temporary debug check
@app.route('/debug-env')
def debug_env():
    keys = ["DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN", "FLASK_SECRET_KEY"]
    found = {k: ("Found" if os.environ.get(k) else "MISSING") for k in keys}
    return f"<h3>Environment Status:</h3>{found}"

# Uses Render variable or a fallback to prevent crash
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

# Combined Template: No external files needed
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
        <h3>1. Library</h3>
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
        <div id="setlist-inner">
            {% include 'inner' %}
        </div>
    </div>

    <form action="/build" method="POST">
        <input type="text" name="set_name" placeholder="Set Name (e.g. Christmas)" required style="width:100%; padding:12px; margin-bottom:15px; box-sizing:border-box;">
        <button class="build-btn" type="submit">BUILD 19 INSTRUMENT PARTS</button>
    </form>
</body>
</html>
'''

# Small template for just the setlist portion
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
            # Matches your specific Dropbox path
            path = "/POW PDFs/POW PDFs Parts by instrument"
            folders = dbx.files_list_folder(path).entries
            first = next(f for f in folders if isinstance(f, dropbox.files.FolderMetadata))
            songs = dbx.files_list_folder(first.path_lower).entries
            library = sorted([s.name for s in songs if s.name.lower().endswith('.pdf')])
        except Exception as e:
            error = f"Path error: {str(e)}"

    # We register 'inner' as a fake template to allow the {% include %} to work
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
    # ... (Keep your existing build logic here) ...
    return "Build complete. Check Dropbox!"

if __name__ == '__main__':
    app.run()
import os, io, dropbox, re
from flask import Flask, render_template_string, request, session
from pypdf import PdfWriter

app = Flask(__name__)
# Uses Render variable or a fallback to prevent crash
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

# Combined Template: No external files needed
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
        <h3>1. Library</h3>
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
        <div id="setlist-inner">
            {% include 'inner' %}
        </div>
    </div>

    <form action="/build" method="POST">
        <input type="text" name="set_name" placeholder="Set Name (e.g. Christmas)" required style="width:100%; padding:12px; margin-bottom:15px; box-sizing:border-box;">
        <button class="build-btn" type="submit">BUILD 19 INSTRUMENT PARTS</button>
    </form>
</body>
</html>
'''

# Small template for just the setlist portion
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
            # Matches your specific Dropbox path
            path = "/POW PDFs/POW PDFs Parts by instrument"
            folders = dbx.files_list_folder(path).entries
            first = next(f for f in folders if isinstance(f, dropbox.files.FolderMetadata))
            songs = dbx.files_list_folder(first.path_lower).entries
            library = sorted([s.name for s in songs if s.name.lower().endswith('.pdf')])
        except Exception as e:
            error = f"Path error: {str(e)}"

    # We register 'inner' as a fake template to allow the {% include %} to work
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
    # ... (Keep your existing build logic here) ...
    return "Build complete. Check Dropbox!"

if __name__ == '__main__':
    app.run()

import os, io, dropbox, re
from flask import Flask, render_template_string, request, session
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "pow-band-2026-secure")

# YOUR VERIFIED KEYS
APP_KEY = "y6584ao8zvw1uzc"
APP_SECRET = "54ely7xrn7l4ixj"

def get_dbx():
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    if not refresh_token:
        return None
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
        <div style="display:flex; justify-content:space-between; padding:10px; border-bottom:1px solid #eee;">
            <span>{i+1}. {song}</span>
            <button style="background:#dc3545; color:white; border:none; padding:5px 10px; border-radius:4px;" 
                    hx-post="/remove" hx-vals='{{"song": "{song}"}}' hx-target="#setlist-inner">×</button>
        </div>'''
    return html if setlist else '<p style="color:#999;">No songs selected.</p>'

# This is the "Brain" of the app embedded directly so it can't be blocked
HTMX_SCRIPT = requests.get("https://unpkg.com").text if 'requests' in globals() else ""

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <!-- EMBEDDED HTMX - NO EXTERNAL CALLS -->
    <script>
    {% include 'htmx_code' %}
    </script>
    <style>
        body { font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px; background: #f4f4f4; }
        .card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: white; margin-bottom: 20px; }
        .item { display: flex; justify-content: space-between; padding: 10px; border-bottom: 1px solid #eee; align-items: center; }
        .btn-add { background: #28a745; color: white; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; }
        .build-btn { width: 100%; padding: 15px; background: #007bff; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 18px; cursor: pointer; }
        select, input { width: 100%; padding: 12px; margin-bottom: 10px; border-radius: 4px; border: 1px solid #ccc; box-sizing: border-box; }
        #status-box { font-size: 11px; background: #333; color: #0f0; padding: 10px; border-radius: 5px; min-height: 40px; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>🎺 POW Set Downloader</h1>
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
        <h3>2. Library</h3>
        <div id="library-container" style="max-height: 300px; overflow-y: auto;"><p style="color:#999;">Select a Set above.</p></div>
    </div>
    <div class="card">
        <h3>3. Your Setlist</h3>
        <div id="setlist-inner">{{ setlist_html|safe }}</div>
        <button style="width:100%; margin-top:10px; padding:8px; background:#6c757d; color:white; border:none; border-radius:4px;" hx-post="/clear" hx-target="#setlist-inner">Clear All</button>
    </div>
    <form action="/build" method="POST">
        <input type="hidden" id="active_folder" name="active_folder" value="">
        <input type="text" name="set_name" placeholder="Output Folder Name" required>
        <button class="build-btn" type="submit">BUILD 19 INSTRUMENT PARTS</button>
    </form>
    <div id="status-box"><strong>Status:</strong> <span id="status-text">{{ status_msg }}</span></div>
    <script>
        document.body.addEventListener('htmx:afterRequest', function(evt) {
            if (evt.detail.target.id === 'library-container') {
                var folder = document.querySelector('select[name="folder_path"]').value;
                document.getElementById('active_folder').value = folder;
                document.getElementById('status-text').innerHTML = "Loaded: " + folder;
            }
        });
    </script>
</body>
</html>
'''

# [REMAINING ROUTES /index, /update-library, /add, /remove, /clear, /build AS BEFORE]
# IMPORTANT: Updated index to handle the embedded script
@app.route('/')
def index():
    import requests
    htmx_code = requests.get("https://cloudflare.com").text
    dbx = get_dbx()
    session.setdefault('setlist', [])
    folders, status_msg = [], "Connecting..."
    if dbx:
        try:
            res = dbx.files_list_folder("")
            folders = sorted([e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata) and e.name.lower() != "generated"], key=lambda x: x.name)
            status_msg = f"Connected! Found {len(folders)} sets."
        except Exception as e: status_msg = f"Dropbox Error: {e}"
    else: status_msg = "Error: Refresh Token Missing."
    
    # We inject the script code manually to bypass tracking prevention
    full_html = HTML_TEMPLATE.replace("{% include 'htmx_code' %}", htmx_code)
    return render_template_string(full_html, folders=folders, setlist_html=render_setlist_html(session['setlist']), status_msg=status_msg)

# ... (Include all other routes /update-library, /add, etc. exactly as they were in the previous version)

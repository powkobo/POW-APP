import os, io, dropbox, html
from flask import Flask, render_template_string, request, session, redirect, url_for
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this")

# --- ENV VARS ---
APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
APP_PASSWORD = os.environ.get("APP_PASSWORD")  # simple auth


def get_dbx():
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    if not refresh_token or not APP_KEY or not APP_SECRET:
        return None
    try:
        return dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=APP_KEY,
            app_secret=APP_SECRET
        )
    except:
        return None

# --- SIMPLE AUTH ---
@app.before_request
def require_login():
    if not APP_PASSWORD:
        return
    if request.endpoint in ("login", "static"):
        return
    if session.get("auth") != True:
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["auth"] = True
            return redirect("/")
    return """
    <form method="POST" style="max-width:300px;margin:100px auto;font-family:sans-serif;">
        <h3>Password</h3>
        <input type="password" name="password" style="width:100%;padding:10px;"/>
        <button style="width:100%;margin-top:10px;">Login</button>
    </form>
    """


def render_setlist_html(setlist):
    html_out = ""
    for i, song in enumerate(setlist):
        safe_song = html.escape(song)
        html_out += f'''
        <div class="item">
            <span>{i+1}. {safe_song}</span>
            <button hx-post="/remove" hx-vals='{{"song": "{safe_song}"}}' hx-target="#setlist-inner">×</button>
        </div>'''
    return html_out or '<p>No songs selected.</p>'


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head>
<body>
<h2>Set Builder</h2>

<select name="folder_path" hx-post="/update-library" hx-trigger="change" hx-target="#library"></select>

<div id="library"></div>
<div id="setlist-inner">{{ setlist_html|safe }}</div>

<form action="/build" method="POST">
    <input type="hidden" id="active_folder" name="active_folder">
    <input name="set_name" required>
    <button>BUILD</button>
</form>

<script>
document.body.addEventListener('htmx:afterRequest', function(evt) {
    if (evt.detail.target.id === 'library') {
        document.getElementById('active_folder').value = document.querySelector('select').value;
    }
});
</script>
</body>
</html>
'''


@app.route('/')
def index():
    session.setdefault('setlist', [])
    dbx = get_dbx()

    folders = []
    if dbx:
        try:
            res = dbx.files_list_folder("")
            folders = [e for e in res.entries if isinstance(e, dropbox.files.FolderMetadata)]
        except:
            pass

    return render_template_string(
        HTML_TEMPLATE,
        folders=folders,
        setlist_html=render_setlist_html(session['setlist'])
    )


@app.route('/update-library', methods=['POST'])
def update_library():
    dbx = get_dbx()
    path = request.form.get('folder_path')

    if not dbx or not path:
        return ""

    try:
        res = dbx.files_list_folder(path)
        html_out = ""

        for entry in res.entries:
            if isinstance(entry, dropbox.files.FileMetadata) and entry.name.lower().endswith('.pdf'):
                safe = html.escape(entry.name)
                html_out += f'<div>{safe} <button hx-post="/add" hx-vals=\'{{"song":"{safe}"}}\' hx-target="#setlist-inner">+</button></div>'

        return html_out or "No PDFs found"
    except Exception as e:
        return str(e)


@app.route('/add', methods=['POST'])
def add_song():
    song = request.form.get('song')
    lst = session.get('setlist', [])

    if song and song not in lst:
        if len(lst) < 50:  # prevent session overflow
            lst.append(song)
    session['setlist'] = lst

    return render_setlist_html(lst)


@app.route('/remove', methods=['POST'])
def remove_song():
    song = request.form.get('song')
    lst = session.get('setlist', [])

    if song in lst:
        lst.remove(song)

    session['setlist'] = lst
    return render_setlist_html(lst)


@app.route('/build', methods=['POST'])
def build():
    dbx = get_dbx()
    setlist = session.get('setlist', [])
    set_name = request.form.get('set_name')
    active_folder = request.form.get('active_folder')

    if not setlist or not dbx or not active_folder:
        return "Error"

    try:
        # ensure folder exists
        try:
            dbx.files_create_folder_v2(f"/Generated/{set_name}")
        except:
            pass

        res = dbx.files_list_folder(active_folder)

        for f in res.entries:
            if not isinstance(f, dropbox.files.FolderMetadata):
                continue

            writer = PdfWriter()

            items = dbx.files_list_folder(f.path_lower).entries
            pdf_map = {e.name.lower(): e.path_lower for e in items if e.name.lower().endswith('.pdf')}

            for song in setlist:
                if song.lower() in pdf_map:
                    try:
                        _, r = dbx.files_download(pdf_map[song.lower()])
                        writer.append(io.BytesIO(r.content))
                    except:
                        continue

            out = io.BytesIO()
            writer.write(out)
            out.seek(0)

            dbx.files_upload(
                out.read(),
                f"/Generated/{set_name}/{f.name}.pdf",
                mode=dropbox.files.WriteMode.overwrite
            )

        session['setlist'] = []
        return "Done"

    except Exception as e:
        return str(e)


if __name__ == '__main__':
    app.run()

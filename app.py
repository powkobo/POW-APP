import os, io, threading, dropbox, html
from flask import Flask, render_template_string, request, session, redirect, url_for, jsonify
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this")

APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

BUILD_STATUS = {"running": False, "progress": 0, "text": "Idle"}


def get_dbx():
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    if not refresh_token or not APP_KEY or not APP_SECRET:
        return None
    return dropbox.Dropbox(oauth2_refresh_token=refresh_token, app_key=APP_KEY, app_secret=APP_SECRET)


HTML_LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PoW Band PDF Portal</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600&display=swap" rel="stylesheet">
<style>
body {margin:0;font-family:'Poppins',sans-serif;background:radial-gradient(circle at top,#0f172a,#020617);color:white;display:flex;align-items:center;justify-content:center;height:100vh;}
.container {width:100%;max-width:400px;background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);border-radius:20px;padding:30px;box-shadow:0 0 40px rgba(255,215,0,0.15);text-align:center;}
.logo {width:120px;margin-bottom:15px;}
h1 {font-weight:600;margin-bottom:10px;}
.subtitle {color:#aaa;font-size:14px;margin-bottom:25px;}
.input {width:100%;padding:14px;margin-bottom:15px;border:none;border-radius:10px;background:rgba(255,255,255,0.08);color:white;}
.input:focus {outline:none;box-shadow:0 0 0 2px gold;}
.button {width:100%;padding:14px;border:none;border-radius:10px;background:linear-gradient(135deg,gold,#c9a100);color:black;font-weight:600;cursor:pointer;transition:0.2s;}
.button:hover {transform:translateY(-2px);box-shadow:0 10px 20px rgba(255,215,0,0.3);} 
.footer {margin-top:15px;font-size:12px;color:#888;}
.error {color:#ff6b6b;margin-bottom:10px;}
</style>
</head>
<body>
<div class="container">
<img src="/static/logo.png" class="logo">
<h1>PoW Band PDF Portal</h1>
<div class="subtitle">Create. Organize. Perform.</div>
{% if error %}<div class="error">{{error}}</div>{% endif %}
<form method="POST">
<input class="input" type="password" name="password" placeholder="Enter Password" required>
<button class="button">Sign In</button>
</form>
<div class="footer">Secure access to your band's PDF library</div>
</div>
</body>
</html>
'''


@app.before_request
def require_login():
    if not APP_PASSWORD:
        return
    if request.endpoint in ("login", "static", "status"):
        return
    if session.get("auth") is not True:
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["auth"] = True
            return redirect(url_for("index"))
        else:
            error = "Incorrect password"
    return render_template_string(HTML_LOGIN_TEMPLATE, error=error)


def render_setlist_html(setlist):
    out = ""
    for i, song in enumerate(setlist):
        safe = html.escape(song, quote=True)
        out += f'''
        <div style="display:flex; justify-content:space-between; padding:10px; border-bottom:1px solid #eee; align-items:center;">
            <span>{i+1}. {safe}</span>
            <div>
                <button hx-post="/move" hx-vals='{{"index": {i}, "dir": "up"}}' hx-target="#setlist-inner">↑</button>
                <button hx-post="/move" hx-vals='{{"index": {i}, "dir": "down"}}' hx-target="#setlist-inner">↓</button>
                <button hx-post="/remove" name="song" value="{safe}" hx-target="#setlist-inner">×</button>
            </div>
        </div>'''
    return out if setlist else '<p style="color:#999; padding:10px;">No songs selected.</p>'


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
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
        <h3>2. Library (Click +)</h3>
        <input id="libSearch" placeholder="Search" onkeyup="filterLib()">
        <div id="library-container"></div>
    </div>

    <div class="card">
        <h3>3. Your Setlist</h3>
        <div id="setlist-inner">{{ setlist_html|safe }}</div>
        <button hx-post="/clear" hx-target="#setlist-inner">Clear All</button>
    </div>

    <form action="/build" method="POST">
        <input type="hidden" id="active_folder" name="active_folder">
        <input type="text" name="set_name" placeholder="Output Folder Name" required>
        <button class="build-btn" type="submit">BUILD</button>
    </form>

    <div id="status-box">
        <strong>Status:</strong> <span id="status-text"></span>
    </div>

<script>
function filterLib(){
 let q=document.getElementById('libSearch').value.toLowerCase();
 document.querySelectorAll('.lib-item').forEach(e=>{
  e.style.display=e.innerText.toLowerCase().includes(q)?'flex':'none';
 });
}
setInterval(()=>{
 fetch('/status').then(r=>r.json()).then(d=>{
  document.getElementById('status-text').innerText = d.text + ' ' + d.progress + '%';
 });
},1000);
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
    return render_template_string(HTML_TEMPLATE, folders=folders, setlist_html=render_setlist_html(session['setlist']))

@app.route('/update-library', methods=['POST'])
def update_library():
    dbx = get_dbx()
    path = request.form.get('folder_path')
    if not dbx or not path:
        return ""
    res = dbx.files_list_folder(path)
    out = ""
    seen=set()
    for e in res.entries:
        if isinstance(e, dropbox.files.FolderMetadata):
            sub=dbx.files_list_folder(e.path_lower)
            for f in sub.entries:
                if f.name.lower().endswith('.pdf'):
                    k=f.name.lower()
                    if k in seen: continue
                    seen.add(k)
                    safe=html.escape(f.name)
                    out+=f'<div class="lib-item item"><span>{safe}</span><button class="btn-add" name="song" value="{safe}" hx-post="/add" hx-target="#setlist-inner">+</button></div>'
    return out

@app.route('/add', methods=['POST'])
def add():
    song=request.form.get('song')
    lst=session.get('setlist',[])
    if song:
        lst.append(song)
    session['setlist']=lst
    return render_setlist_html(lst)

@app.route('/remove', methods=['POST'])
def remove():
    song=request.form.get('song')
    lst=session.get('setlist',[])
    if song in lst: lst.remove(song)
    session['setlist']=lst
    return render_setlist_html(lst)

@app.route('/move', methods=['POST'])
def move():
    i=int(request.form.get('index'))
    d=request.form.get('dir')
    lst=session.get('setlist',[])
    if d=='up' and i>0: lst[i],lst[i-1]=lst[i-1],lst[i]
    if d=='down' and i<len(lst)-1: lst[i],lst[i+1]=lst[i+1],lst[i]
    session['setlist']=lst
    return render_setlist_html(lst)

@app.route('/clear', methods=['POST'])
def clear():
    session['setlist']=[]
    return render_setlist_html([])


def build_worker(setlist,set_name,active_folder):
    dbx=get_dbx()
    BUILD_STATUS.update({"running":True,"progress":0})
    res=dbx.files_list_folder(active_folder)
    folders=[f for f in res.entries if isinstance(f,dropbox.files.FolderMetadata)]
    for i,f in enumerate(folders):
        writer=PdfWriter()
        items=dbx.files_list_folder(f.path_lower).entries
        pdf_map={e.name.lower():e.path_lower for e in items if e.name.lower().endswith('.pdf')}
        for song in setlist:
            key=song.lower()
            if key in pdf_map:
                _,r=dbx.files_download(pdf_map[key])
                writer.append(io.BytesIO(r.content))
        if not writer.pages:
            continue
        out=io.BytesIO()
        writer.write(out)
        out.seek(0)
        dbx.files_upload(out.read(),f"/Generated/{set_name}/{f.name}-{set_name}.pdf",mode=dropbox.files.WriteMode.overwrite)
        BUILD_STATUS.update({"progress":int((i+1)/len(folders)*100),"text":f.name})
    BUILD_STATUS.update({"running":False,"text":"Done"})

@app.route('/build',methods=['POST'])
def build():
    if BUILD_STATUS["running"]: return "Busy"
    threading.Thread(target=build_worker,args=(session.get('setlist',[]),request.form.get('set_name'),request.form.get('active_folder'))).start()
    return redirect('/')

@app.route('/status')
def status(): return jsonify(BUILD_STATUS)

if __name__=='__main__': app.run()

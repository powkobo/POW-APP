import os
import io
import threading
import dropbox
import html
import json

from flask import Flask, render_template_string, request, session, redirect, url_for, jsonify
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "pow-secret")

APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "admin123")

BUILD_STATUS = {"running": False, "progress": 0, "text": "Idle"}

def get_dbx():
    token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    if not token:
        return None
    return dropbox.Dropbox(oauth2_refresh_token=token, app_key=APP_KEY, app_secret=APP_SECRET)

# ---------------- LOGIN ----------------

HTML_LOGIN = '''
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {
    margin:0;
    font-family:sans-serif;
    background:radial-gradient(circle at top, #1a1f2e, #000);
    color:white;
    display:flex;
    justify-content:center;
    align-items:center;
    height:100vh;
}
.card {
    background:rgba(255,255,255,0.05);
    border:1px solid rgba(255,215,0,0.2);
    padding:30px;
    border-radius:20px;
    width:320px;
    text-align:center;
}
.logo {
    width:120px;
    margin-bottom:15px;
    filter:drop-shadow(0 0 10px gold);
}
input {
    width:100%;
    padding:12px;
    margin-top:10px;
    border-radius:8px;
    border:1px solid #333;
    background:#111;
    color:white;
}
button {
    width:100%;
    padding:12px;
    margin-top:15px;
    border:none;
    border-radius:8px;
    background:linear-gradient(90deg,#d4af37,#f5d76e);
}
</style>
</head>
<body>
<div class="card">
<img src="/static/logo.png" class="logo">
<h2>PoW Band PDF Portal</h2>
<form method="POST">
<input type="password" name="password" placeholder="Password">
<button>Login</button>
</form>
</div>
</body>
</html>
'''

@app.before_request
def protect():
    if request.path.startswith('/static'):
        return
    if request.path in ['/login', '/status', '/build']:
        return
    if not session.get("auth"):
        return redirect('/login')

@app.route('/login', methods=['GET','POST'])
def login():
    if session.get("auth"):
        return redirect('/')
    if request.method == 'POST':
        if request.form.get('password') == APP_PASSWORD:
            session['auth'] = True
            return redirect('/')
    return render_template_string(HTML_LOGIN)

# ---------------- UI ----------------

def render_setlist_html(lst):
    out=""
    for i,s in enumerate(lst):
        name=html.escape(s["name"])
        up=json.dumps({"index":i,"dir":"up"})
        down=json.dumps({"index":i,"dir":"down"})
        payload=json.dumps(s)

        out+=f'''
<div style="display:flex;justify-content:space-between;padding:10px;border-bottom:1px solid #333;">
<span>{i+1}. {name}</span>
<div>
<button hx-post="/move" hx-vals='{up}' hx-target="#setlist-inner">↑</button>
<button hx-post="/move" hx-vals='{down}' hx-target="#setlist-inner">↓</button>
<button hx-post="/remove" hx-vals='{payload}' hx-target="#setlist-inner">×</button>
</div>
</div>
'''
    return out or "<p>No songs</p>"

HTML = '''
<!DOCTYPE html>
<html>
<head>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
body { background:#000; color:white; font-family:sans-serif; max-width:500px; margin:auto; padding:20px; }
.card { background:#111; padding:15px; border-radius:10px; margin-bottom:15px; }
.item { display:flex; justify-content:space-between; padding:8px; border-bottom:1px solid #333; }
.btn-add { background:gold; border:none; }
</style>
</head>
<body>

<h2>🎺 PoW Set Builder</h2>

<div class="card">
<select name="folder_path" hx-post="/update-library" hx-trigger="change" hx-target="#lib">
<option>Select Set</option>
{% for f in folders %}
<option value="{{f.path_lower}}">{{f.name}}</option>
{% endfor %}
</select>
</div>

<div class="card">
<input id="search" placeholder="Search..." onkeyup="filterLib()">
<div id="lib"></div>
</div>

<div class="card">
<div id="setlist-inner">{{setlist|safe}}</div>
</div>

<form method="POST" action="/build">
<input name="set_name" placeholder="Set Name">
<button>BUILD</button>
</form>

<div id="status"></div>

<script>
function filterLib(){
 let q=document.getElementById("search").value.toLowerCase();
 document.querySelectorAll(".lib-item").forEach(e=>{
  e.style.display=e.innerText.toLowerCase().includes(q)?"flex":"none";
 });
}

setInterval(()=>{
 fetch('/status').then(r=>r.json()).then(d=>{
  document.getElementById("status").innerText=d.text+" "+d.progress+"%";
 });
},1000);
</script>

</body>
</html>
'''

@app.route('/')
def index():
    session.setdefault("setlist",[])
    dbx=get_dbx()
    folders=[]
    if dbx:
        res=dbx.files_list_folder("")
        folders=[e for e in res.entries if isinstance(e,dropbox.files.FolderMetadata)]
    return render_template_string(HTML,folders=folders,setlist=render_setlist_html(session["setlist"]))

# ---------------- LIBRARY ----------------

@app.route('/update-library', methods=['POST'])
def update_library():
    dbx=get_dbx()
    path=request.form.get("folder_path")
    out=""
    seen=set()

    res=dbx.files_list_folder(path)
    for e in res.entries:
        if isinstance(e,dropbox.files.FolderMetadata):
            sub=dbx.files_list_folder(e.path_lower)
            for f in sub.entries:
                if f.name.lower().endswith(".pdf"):
                    key=f.name.lower()
                    if key in seen: continue
                    seen.add(key)

                    payload=json.dumps({"name":f.name,"path":f.path_lower})
                    out+=f'''
<div class="lib-item item">
<span>{html.escape(f.name)}</span>
<button hx-post="/add" hx-vals='{payload}' hx-target="#setlist-inner">+</button>
</div>
'''
    return out

@app.route('/add', methods=['POST'])
def add():
    lst=session.get("setlist",[])
    lst.append({"name":request.form["name"],"path":request.form["path"]})
    session["setlist"]=lst
    return render_setlist_html(lst)

@app.route('/remove', methods=['POST'])
def remove():
    lst=session.get("setlist",[])
    name=request.form.get("name")
    path=request.form.get("path")
    lst=[s for s in lst if not (s["name"]==name and s["path"]==path)]
    session["setlist"]=lst
    return render_setlist_html(lst)

@app.route('/move', methods=['POST'])
def move():
    lst=session.get("setlist",[])
    i=int(request.form["index"])
    d=request.form["dir"]
    if d=="up" and i>0:
        lst[i],lst[i-1]=lst[i-1],lst[i]
    if d=="down" and i<len(lst)-1:
        lst[i],lst[i+1]=lst[i+1],lst[i]
    session["setlist"]=lst
    return render_setlist_html(lst)

# ---------------- BUILD ----------------

def build_worker(setlist,set_name):
    dbx=get_dbx()
    BUILD_STATUS.update({"running":True,"progress":0})

    root="/"+setlist[0]["path"].split("/")[1]
    res=dbx.files_list_folder(root)
    folders=[f for f in res.entries if isinstance(f,dropbox.files.FolderMetadata)]

    for i,f in enumerate(folders):
        writer=PdfWriter()
        items=dbx.files_list_folder(f.path_lower).entries
        pdf_map={x.name.lower():x.path_lower for x in items if x.name.lower().endswith(".pdf")}

        for s in setlist:
            name=s["name"].lower()
            if name in pdf_map:
                _,r=dbx.files_download(pdf_map[name])
                writer.append(io.BytesIO(r.content))

        if writer.pages:
            out=io.BytesIO()
            writer.write(out)
            out.seek(0)
            dbx.files_upload(out.read(),f"/Generated/{set_name}/{f.name}-{set_name}.pdf",mode=dropbox.files.WriteMode.overwrite)

        BUILD_STATUS.update({"progress":int((i+1)/len(folders)*100),"text":f.name})

    BUILD_STATUS.update({"running":False,"text":"Done"})

@app.route('/build', methods=['POST'])
def build():
    threading.Thread(target=build_worker,args=(session["setlist"],request.form["set_name"])).start()
    return redirect('/')

@app.route('/status')
def status():
    return jsonify(BUILD_STATUS)

if __name__ == "__main__":
    app.run()
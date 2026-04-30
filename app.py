import os
import io
import threading
import dropbox
import html
import json

from flask import Flask, render_template_string, request, session, redirect, jsonify
from pypdf import PdfWriter

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "pow-secret")

APP_PASSWORD = os.environ.get("APP_PASSWORD", "admin123")

BUILD_STATUS = {"running": False, "progress": 0, "text": "Idle"}


def get_dbx():
    return dropbox.Dropbox(
        oauth2_refresh_token=os.environ.get("DROPBOX_REFRESH_TOKEN"),
        app_key=os.environ.get("DROPBOX_APP_KEY"),
        app_secret=os.environ.get("DROPBOX_APP_SECRET"),
    )


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
    background:#000;
    color:white;
    display:flex;
    justify-content:center;
    align-items:center;
    height:100vh;
}
.card {
    background:#111;
    padding:25px;
    border-radius:15px;
    text-align:center;
}
.logo { width:120px; margin-bottom:10px; }
input {
    width:100%;
    padding:12px;
    margin-top:10px;
    background:#222;
    border:none;
    color:white;
}
button {
    width:100%;
    padding:12px;
    margin-top:10px;
    background:gold;
    border:none;
}
</style>
</head>
<body>
<div class="card">
<img src="/static/logo.png" class="logo">
<h2>PoW Band Portal</h2>
<form method="POST">
<input name="password" type="password">
<button>Login</button>
</form>
</div>
</body>
</html>
'''


@app.before_request
def protect():
    if request.path.startswith("/static"):
        return
    if request.path in ["/login", "/status", "/build"]:
        return
    if not session.get("auth"):
        return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["auth"] = True
            return redirect("/")
    return render_template_string(HTML_LOGIN)


# ---------------- UI ----------------

def render_setlist(lst):
    out = ""
    for i, s in enumerate(lst):
        name = html.escape(s["name"])
        payload = json.dumps(s)
        up = json.dumps({"i": i, "d": "up"})
        down = json.dumps({"i": i, "d": "down"})

        out += f'''
<div class="item" draggable="true">
<span>{i+1}. {name}</span>
<div>
<button hx-post="/move" hx-vals='{up}' hx-target="#setlist">⬆</button>
<button hx-post="/move" hx-vals='{down}' hx-target="#setlist">⬇</button>
<button hx-post="/remove" hx-vals='{payload}' hx-target="#setlist">❌</button>
</div>
</div>
'''
    return out or "<p>No songs</p>"


HTML = '''
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
body { background:#000; color:white; font-family:sans-serif; padding:10px; }
.card { background:#111; padding:12px; border-radius:10px; margin-bottom:10px; }
.item { display:flex; justify-content:space-between; padding:10px; border-bottom:1px solid #333; }
button { background:gold; border:none; padding:8px; border-radius:6px; }
#lib { max-height:300px; overflow:auto; }
.build { position:sticky; bottom:0; background:#000; padding:10px; }
</style>
</head>
<body>

<h2>🎺 PoW Builder</h2>

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
<div id="setlist">{{setlist|safe}}</div>
</div>

<div class="build">
<form method="POST" action="/build">
<input name="set_name" placeholder="Set name">
<button>BUILD</button>
</form>
</div>

<div id="status"></div>

<script>
function filterLib(){
 let q=document.getElementById("search").value.toLowerCase();
 document.querySelectorAll(".lib-item").forEach(e=>{
  e.style.display=e.innerText.toLowerCase().includes(q)?"flex":"none";
 });
}

// drag reorder
let dragged
document.addEventListener("dragstart",e=>dragged=e.target)
document.addEventListener("dragover",e=>e.preventDefault())
document.addEventListener("drop",e=>{
 let el=e.target.closest(".item")
 if(el){
  let list=[...document.querySelectorAll(".item")]
  let from=list.indexOf(dragged)
  let to=list.indexOf(el)
  fetch('/reorder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from,to})})
  .then(()=>location.reload())
 }
})

// swipe delete
let startX=0
document.addEventListener("touchstart",e=>startX=e.touches[0].clientX)
document.addEventListener("touchend",e=>{
 let diff=e.changedTouches[0].clientX-startX
 if(diff<-80){
  let el=e.target.closest(".item")
  if(el){
    el.querySelector("button[hx-post='/remove']").click()
  }
 }
})

// status
setInterval(()=>{
 fetch('/status').then(r=>r.json()).then(d=>{
  document.getElementById("status").innerText=d.text+" "+d.progress+"%"
 })
},1000)
</script>

</body>
</html>
'''


@app.route("/")
def index():
    session.setdefault("setlist", [])
    dbx = get_dbx()
    folders = []

    if dbx:
        res = dbx.files_list_folder("")
        folders = [f for f in res.entries if isinstance(f, dropbox.files.FolderMetadata)]

    return render_template_string(HTML, folders=folders, setlist=render_setlist(session["setlist"]))


# ---------------- LIBRARY ----------------

@app.route("/update-library", methods=["POST"])
def lib():
    dbx = get_dbx()
    path = request.form.get("folder_path")
    seen = set()
    out = ""

    for f in dbx.files_list_folder(path).entries:
        if isinstance(f, dropbox.files.FolderMetadata):
            for p in dbx.files_list_folder(f.path_lower).entries:
                if p.name.lower().endswith(".pdf"):
                    if p.name in seen:
                        continue
                    seen.add(p.name)
                    payload = json.dumps({"name": p.name, "path": p.path_lower})
                    out += f'<div class="lib-item item"><span>{html.escape(p.name)}</span><button hx-post="/add" hx-vals=\'{payload}\' hx-target="#setlist">+</button></div>'
    return out


@app.route("/add", methods=["POST"])
def add():
    lst = session.get("setlist", [])
    lst.append({"name": request.form["name"], "path": request.form["path"]})
    session["setlist"] = lst
    return render_setlist(lst)


@app.route("/remove", methods=["POST"])
def remove():
    lst = session.get("setlist", [])
    name = request.form.get("name")
    path = request.form.get("path")
    lst = [s for s in lst if not (s["name"] == name and s["path"] == path)]
    session["setlist"] = lst
    return render_setlist(lst)


@app.route("/move", methods=["POST"])
def move():
    lst = session.get("setlist", [])
    i = int(request.form["i"])
    d = request.form["d"]

    if d == "up" and i > 0:
        lst[i], lst[i-1] = lst[i-1], lst[i]
    elif d == "down" and i < len(lst)-1:
        lst[i], lst[i+1] = lst[i+1], lst[i]

    session["setlist"] = lst
    return render_setlist(lst)


@app.route("/reorder", methods=["POST"])
def reorder():
    data = request.json
    lst = session.get("setlist", [])
    item = lst.pop(data["from"])
    lst.insert(data["to"], item)
    session["setlist"] = lst
    return "ok"


# ---------------- BUILD ----------------

def build_worker(lst, name):
    dbx = get_dbx()
    BUILD_STATUS.update({"running": True, "progress": 0, "text": "Starting"})

    if not lst:
        BUILD_STATUS.update({"running": False, "text": "No songs"})
        return

    root = "/" + lst[0]["path"].split("/")[1]
    folders = [f for f in dbx.files_list_folder(root).entries if isinstance(f, dropbox.files.FolderMetadata)]

    for i, f in enumerate(folders):
        writer = PdfWriter()
        items = dbx.files_list_folder(f.path_lower).entries
        mp = {x.name.lower(): x.path_lower for x in items if x.name.lower().endswith(".pdf")}

        for s in lst:
            if s["name"].lower() in mp:
                _, r = dbx.files_download(mp[s["name"].lower()])
                writer.append(io.BytesIO(r.content))

        if writer.pages:
            out = io.BytesIO()
            writer.write(out)
            out.seek(0)
            dbx.files_upload(
                out.read(),
                f"/Generated/{name}/{f.name}-{name}.pdf",
                mode=dropbox.files.WriteMode.overwrite,
            )

        BUILD_STATUS.update({
            "progress": int((i + 1) / len(folders) * 100),
            "text": f.name
        })

    BUILD_STATUS.update({"running": False, "text": "Done"})


@app.route("/build", methods=["POST"])
def build():
    threading.Thread(
        target=build_worker,
        args=(session.get("setlist", []), request.form.get("set_name"))
    ).start()
    return redirect("/")


@app.route("/status")
def status():
    return jsonify(BUILD_STATUS)


if __name__ == "__main__":
    app.run()
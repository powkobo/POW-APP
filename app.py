import os, io, dropbox
from flask import Flask, render_template_string, request, send_file
from pypdf import PdfWriter

app = Flask(__name__)

# Connect to Dropbox via Environment Variable
TOKEN = os.environ.get("DROPBOX_TOKEN")
dbx = dropbox.Dropbox(TOKEN)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; padding: 20px; max-width: 400px; margin: auto; text-align: center; }
        select, button { width: 100%; padding: 15px; margin: 10px 0; font-size: 18px; border-radius: 8px; border: 1px solid #ccc; }
        button { background: #008000; color: white; font-weight: bold; border: none; }
        .loader { font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <h1>🎺 POW Parts</h1>
    <form method="POST">
        <label>1. Select Set</label>
        <select name="set_num">
            <option>Set 1</option>
            <option>Set 2</option>
            <option>Set 3</option>
        </select>

        <label>2. Select Instrument</label>
        <select name="instrument">
            {% for inst in instruments %}
            <option value="{{ inst }}">{{ inst }}</option>
            {% endfor %}
        </select>

        <button type="submit" onclick="this.innerHTML='Generating...';">Download My PDF</button>
    </form>
    <p class="loader">Files are merged live from Dropbox</p>
</body>
</html>
'''

def get_instruments(set_name="Set 1"):
    """Lists folders in Dropbox to build the dropdown menu."""
    try:
        path = f"/POW PDFs/POW PDFs Parts by instrument/{set_name}"
        res = dbx.files_list_folder(path)
        # Only return folder names, sorted alphabetically
        return sorted([entry.name for entry in res.entries if isinstance(entry, dropbox.files.FolderMetadata)])
    except:
        return ["Error: Check Dropbox Path"]

@app.route('/', methods=['GET', 'POST'])
def index():
    # Get instruments for the dropdown (defaults to Set 1 for the list)
    instruments = get_instruments()

    if request.method == 'POST':
        set_num = request.form.get('set_num')
        inst = request.form.get('instrument')
        
        writer = PdfWriter()
        folder_path = f"/POW PDFs/POW PDFs Parts by instrument/{set_num}/{inst}"
        
        # Download and merge each PDF in the folder
        files = dbx.files_list_folder(folder_path).entries
        for file in sorted(files, key=lambda x: x.name):
            if file.name.lower().endswith('.pdf'):
                _, res = dbx.files_download(file.path_lower)
                writer.append(io.BytesIO(res.content))
        
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        
        return send_file(
            output, 
            download_name=f"{inst}_{set_num}.pdf", 
            as_attachment=True,
            mimetype='application/pdf'
        )

    return render_template_string(HTML_TEMPLATE, instruments=instruments)

if __name__ == '__main__':
    app.run()

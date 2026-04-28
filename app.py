import os
import io
import dropbox
from flask import Flask, render_template_string, request, send_file
from pypdf import PdfWriter

app = Flask(__name__)

# Connect to Dropbox
dbx = dropbox.Dropbox(os.environ.get("DROPBOX_TOKEN"))

# Minimalist HTML for E-Readers
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>Brass Band PDF</title></head>
<body>
    <h2>Build Set List</h2>
    <form method="POST">
        Set: <select name="set_num"><option>Set 1</option><option>Set 2</option></select><br><br>
        Instrument: <input type="text" name="instrument" placeholder="01-Soprano Cornet"><br><br>
        <button type="submit">Download PDF</button>
    </form>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        set_num = request.form['set_num']
        inst = request.form['instrument']
        
        # Path based on your Dropbox structure
        folder_path = f"/POW PDFs/POW PDFs Parts by instrument/{set_num}/{inst}"
        
        writer = PdfWriter()
        
        # List files in Dropbox folder
        files = dbx.files_list_folder(folder_path).entries
        for file in sorted(files, key=lambda x: x.name):
            if file.name.endswith('.pdf'):
                _, res = dbx.files_download(file.path_lower)
                writer.append(io.BytesIO(res.content))
        
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        
        return send_file(output, download_name=f"{inst}_{set_num}.pdf", as_attachment=True)

    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    app.run()

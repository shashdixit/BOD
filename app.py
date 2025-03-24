import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from werkzeug.utils import secure_filename
import pandas as pd
from models.search import process_board_members, save_to_csv
from models.enhanced import BoardMemberVerifier

app = Flask(__name__)

# Configure upload and download folders
UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

ALLOWED_EXTENSIONS_EXCEL = {'xlsx', 'xls'}
ALLOWED_EXTENSIONS_CSV = {'csv'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_model1', methods=['POST'])
def process_model1():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    
    if file and allowed_file(file.filename, ALLOWED_EXTENSIONS_EXCEL):
        # Create unique session ID for this run
        session_id = str(uuid.uuid4())
        session_folder = os.path.join(app.config['DOWNLOAD_FOLDER'], session_id)
        os.makedirs(session_folder, exist_ok=True)
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Process the file with Model 1
        output_csv_path = os.path.join(session_folder, "combined_board_members.csv")
        
        # Read Excel file
        df = pd.read_excel(file_path)
        
        # Process each website URL
        if 'Portfolio company Website' not in df.columns:
            flash("Error: 'Portfolio company Website' column not found in the Excel file.")
            return redirect(url_for('index'))
        
        # Create a fresh output file
        if os.path.exists(output_csv_path):
            os.remove(output_csv_path)
        
        # Process each website (simplified version of the original code)
        for website_url in df['Portfolio company Website']:
            if pd.isna(website_url):
                continue
                
            board_data = process_board_members(website_url)
            
            if board_data:
                if len(board_data) == 1 and "Status" in board_data[0] and board_data[0]["Status"] == "No board members found":
                    not_found_entry = [{"Website URL": website_url, "Status": "Not Found", "Comments": "No board members found"}]
                    save_to_csv(not_found_entry, website_url, output_csv_path, write_header=(not os.path.exists(output_csv_path)))
                else:
                    save_to_csv(board_data, website_url, output_csv_path, write_header=(not os.path.exists(output_csv_path)))
            else:
                not_found_entry = [{"Website URL": website_url, "Status": "Not Found", "Comments": "API call failed or no data returned"}]
                save_to_csv(not_found_entry, website_url, output_csv_path, write_header=(not os.path.exists(output_csv_path)))
        
        # Clean up
        os.remove(file_path)
        
        return send_file(output_csv_path, as_attachment=True, download_name="combined_board_members.csv")
    
    flash('Invalid file type. Please upload an Excel file (.xlsx or .xls)')
    return redirect(url_for('index'))

@app.route('/process_model2', methods=['POST'])
def process_model2():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    
    if file and allowed_file(file.filename, ALLOWED_EXTENSIONS_CSV):
        # Create unique session ID for this run
        session_id = str(uuid.uuid4())
        session_folder = os.path.join(app.config['DOWNLOAD_FOLDER'], session_id)
        os.makedirs(session_folder, exist_ok=True)
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Process the file with Model 2
        # Modify the BoardMemberVerifier to use our paths
        verifier = BoardMemberVerifier(file_path)
        verifier.output_csv_path = os.path.join(session_folder, "enhanced_board_members.csv")
        verifier.feedback_csv_path = os.path.join(session_folder, "model_feedback.csv")
        
        # Run the verification process
        result = verifier.run()
        
        # Create a zip file with all outputs
        import zipfile
        zip_path = os.path.join(session_folder, "feedback_results.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            zipf.write(verifier.output_csv_path, os.path.basename(verifier.output_csv_path))
            zipf.write(verifier.feedback_csv_path, os.path.basename(verifier.feedback_csv_path))
        
        # Clean up
        os.remove(file_path)
        
        return send_file(zip_path, as_attachment=True, download_name="feedback_results.zip")
    
    flash('Invalid file type. Please upload a CSV file')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
import os
from flask import Flask, request, send_from_directory, render_template_string, jsonify
from werkzeug.utils import secure_filename
import humanize
import sys
import tkinter as tk
from threading import Thread
import webbrowser
from datetime import datetime, timedelta
import platform
from collections import defaultdict
import time
import qrcode
from PIL import Image, ImageTk
from io import BytesIO
import base64
import socket

# Dictionary to store connected users information
connected_users = defaultdict(lambda: {
    'first_seen': None,      # First connection time
    'last_seen': None,       # Last activity time
    'last_active': None,     # Last active timestamp
    'user_agent': None,
    'platform': None,
    'activities': [],
    'is_connected': False    # Connection status
})

def check_active_users():
    """Update active users status"""
    while True:
        current_time = datetime.now()
        for ip in connected_users:
            if connected_users[ip]['last_seen']:
                last_seen = datetime.strptime(connected_users[ip]['last_seen'], "%Y-%m-%d %H:%M:%S")
                # Changed duration to 15 minutes
                if current_time - last_seen > timedelta(minutes=15):
                    if connected_users[ip]['is_connected']:
                        connected_users[ip]['is_connected'] = False
                        connected_users[ip]['activities'].append({
                            'time': current_time.strftime("%H:%M:%S"),
                            'action': "Disconnected"
                        })
        time.sleep(30)  # Check every 30 seconds

def log_activity(ip, activity):
    current_time = datetime.now()
    if not connected_users[ip]['first_seen']:
        connected_users[ip]['first_seen'] = current_time.strftime("%Y-%m-%d %H:%M:%S")
        connected_users[ip]['activities'].append({
            'time': current_time.strftime("%H:%M:%S"),
            'action': "First connection"
        })
    
    connected_users[ip]['last_seen'] = current_time.strftime("%Y-%m-%d %H:%M:%S")
    connected_users[ip]['user_agent'] = request.headers.get('User-Agent')
    connected_users[ip]['platform'] = request.headers.get('Sec-Ch-Ua-Platform', 'Unknown')
    
    if not connected_users[ip]['is_connected']:
        connected_users[ip]['is_connected'] = True
        connected_users[ip]['activities'].append({
            'time': current_time.strftime("%H:%M:%S"),
            'action': "Connected to network"
        })
    
    connected_users[ip]['activities'].append({
        'time': current_time.strftime("%H:%M:%S"),
        'action': activity
    })

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')  # Dynamic path
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max file size

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html dir="ltr">
<head>
    <meta charset="UTF-8">
    <title>File Sharing</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --primary-color: #4a90e2;
            --secondary-color: #2c3e50;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f8f9fa;
            margin: 0;
            padding: 20px;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .title {
            color: var(--secondary-color);
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5rem;
            font-weight: bold;
        }
        
        .upload-zone {
            border: 3px dashed var(--primary-color);
            border-radius: 15px;
            padding: 40px;
            text-align: center;
            background: #f8f9fa;
            transition: all 0.3s ease;
            cursor: pointer;
            margin-bottom: 30px;
        }
        
        .upload-zone:hover, .upload-zone.dragover {
            background: #e3f2fd;
            border-color: #2196f3;
        }
        
        .upload-zone i {
            font-size: 48px;
            color: var(--primary-color);
            margin-bottom: 15px;
        }
        
        .file-list {
            margin-top: 30px;
        }
        
        .file-item {
            display: flex;
            align-items: center;
            padding: 15px;
            border-bottom: 1px solid #eee;
            transition: background-color 0.2s;
        }
        
        .file-item:hover {
            background-color: #f8f9fa;
        }
        
        .file-icon {
            font-size: 24px;
            margin-left: 15px;
            color: var(--primary-color);
        }
        
        .file-info {
            flex-grow: 1;
        }
        
        .file-name {
            font-weight: 500;
            color: var(--secondary-color);
        }
        
        .file-size {
            font-size: 0.85rem;
            color: #666;
        }
        
        .file-actions {
            display: flex;
            gap: 10px;
        }
        
        .btn-action {
            padding: 5px 15px;
            border-radius: 20px;
            border: none;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .btn-download {
            background-color: var(--primary-color);
            color: white;
        }
        
        .btn-delete {
            background-color: #dc3545;
            color: white;
        }
        
        .btn-action:hover {
            opacity: 0.9;
            transform: translateY(-1px);
        }
        
        #progress-bar {
            display: none;
            margin-top: 20px;
        }
        
        .alert {
            display: none;
            margin-top: 20px;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 15px;
            }
            
            .title {
                font-size: 2rem;
            }
            
            .upload-zone {
                padding: 20px;
            }
            
            .file-item {
                flex-direction: column;
                text-align: center;
            }
            
            .file-actions {
                margin-top: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="title">File Sharing</h1>
        
        <!-- Close button -->
        <div class="text-center mb-4">
            <button onclick="shutdownServer()" class="btn btn-danger btn-lg">
                <i class="fas fa-power-off"></i> Close Program
            </button>
        </div>

        <div id="alert" class="alert" role="alert"></div>
        
        <div id="upload-zone" class="upload-zone">
            <i class="fas fa-cloud-upload-alt"></i>
            <h3>Drop files here</h3>
            <p>or</p>
            <form id="upload-form" enctype="multipart/form-data">
                <input type="file" id="file-input" name="file" style="display: none;">
                <button type="button" class="btn btn-primary" onclick="document.getElementById('file-input').click()">
                    Choose File
                </button>
            </form>
            <div id="progress-bar" class="progress mt-3">
                <div class="progress-bar" role="progressbar" style="width: 0%"></div>
            </div>
        </div>

        <div class="file-list">
            <h2>Available Files</h2>
            <div id="files-container">
                {% for file, size in files %}
                <div class="file-item">
                    <i class="fas fa-file file-icon"></i>
                    <div class="file-info">
                        <div class="file-name">{{ file }}</div>
                        <div class="file-size">{{ size }}</div>
                    </div>
                    <div class="file-actions">
                        <a href="{{ url_for('download_file', filename=file) }}" class="btn btn-action btn-download">
                            <i class="fas fa-download"></i> Download
                        </a>
                        <button onclick="deleteFile('{{ file }}')" class="btn btn-action btn-delete">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        const uploadZone = document.getElementById('upload-zone');
        const fileInput = document.getElementById('file-input');
        const uploadForm = document.getElementById('upload-form');
        const progressBar = document.getElementById('progress-bar');
        const alert = document.getElementById('alert');

        function showAlert(message, type) {
            alert.className = `alert alert-${type}`;
            alert.textContent = message;
            alert.style.display = 'block';
            setTimeout(() => alert.style.display = 'none', 3000);
        }

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadZone.addEventListener(eventName, preventDefaults, false);
            document.body.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            uploadZone.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            uploadZone.addEventListener(eventName, unhighlight, false);
        });

        function highlight(e) {
            uploadZone.classList.add('dragover');
        }

        function unhighlight(e) {
            uploadZone.classList.remove('dragover');
        }

        uploadZone.addEventListener('drop', handleDrop, false);

        function handleDrop(e) {
            const dt = e.dataTransfer;
            const file = dt.files[0];
            handleFile(file);
        }

        fileInput.addEventListener('change', function(e) {
            handleFile(this.files[0]);
        });

        function handleFile(file) {
            const formData = new FormData();
            formData.append('file', file);

            progressBar.style.display = 'block';
            const xhr = new XMLHttpRequest();

            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    progressBar.querySelector('.progress-bar').style.width = percentComplete + '%';
                }
            });

            xhr.onload = function() {
                if (xhr.status === 200) {
                    showAlert('File uploaded successfully!', 'success');
                    location.reload();
                } else {
                    showAlert('Error uploading file', 'danger');
                }
                progressBar.style.display = 'none';
            };

            xhr.onerror = function() {
                showAlert('Error uploading file', 'danger');
                progressBar.style.display = 'none';
            };

            xhr.open('POST', '/', true);
            xhr.send(formData);
        }

        function deleteFile(filename) {
            if (confirm('Are you sure you want to delete this file?')) {
                fetch(`/delete/${filename}`, { method: 'DELETE' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            showAlert('File deleted successfully', 'success');
                            location.reload();
                        } else {
                            showAlert('Error deleting file', 'danger');
                        }
                    })
                    .catch(() => showAlert('Error deleting file', 'danger'));
            }
        }

        // Add shutdown server function
        function shutdownServer() {
            if (confirm('Are you sure you want to close the program?')) {
                fetch('/shutdown', { method: 'POST' })
                    .then(() => {
                        showAlert('Program closed successfully', 'success');
                        setTimeout(() => {
                            window.close();
                        }, 1000);
                    })
                    .catch(() => showAlert('Error closing program', 'danger'));
            }
        }
    </script>
</body>
</html>
'''

MONITOR_TEMPLATE = '''
<!DOCTYPE html>
<html dir="ltr">
<head>
    <meta charset="UTF-8">
    <title>Connected Users Monitor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding: 20px; }
        .user-card {
            margin-bottom: 20px;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
        }
        .activity-list {
            max-height: 200px;
            overflow-y: auto;
        }
        .activity-item {
            padding: 5px;
            border-bottom: 1px solid #eee;
        }
        .mobile-user { border-right: 4px solid #4CAF50; }
        .desktop-user { border-right: 4px solid #2196F3; }
        .connected { background-color: #e8f5e9; }
        .disconnected { background-color: #ffebee; }
        .status-badge {
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 0.9em;
            display: inline-block;
            margin-right: 10px;
        }
        .status-connected {
            background-color: #4CAF50;
            color: white;
        }
        .status-disconnected {
            background-color: #f44336;
            color: white;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mb-4">Connected Users</h1>
        <div class="row">
            {% for ip, data in users.items() %}
            <div class="col-md-6">
                <div class="user-card {% if 'Mobile' in data.user_agent %}mobile-user{% else %}desktop-user{% endif %} {% if data.is_connected %}connected{% else %}disconnected{% endif %}">
                    <h3>
                        User: {{ ip }}
                        <span class="status-badge {% if data.is_connected %}status-connected{% else %}status-disconnected{% endif %}">
                            {{ 'Connected' if data.is_connected else 'Disconnected' }}
                        </span>
                    </h3>
                    <p>First seen: {{ data.first_seen }}</p>
                    <p>Last activity: {{ data.last_seen }}</p>
                    <p>Device type: {{ 'Mobile' if 'Mobile' in data.user_agent else 'Computer' }}</p>
                    <p>Browser: {{ data.user_agent }}</p>
                    <p>OS: {{ data.platform }}</p>
                    <h4>Activities:</h4>
                    <div class="activity-list">
                        {% for activity in data.activities|reverse %}
                        <div class="activity-item">
                            <small>{{ activity.time }}</small>
                            {{ activity.action }}
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    <script>
        // Refresh page every 5 seconds
        setTimeout(() => location.reload(), 5000);
    </script>
</body>
</html>
'''

def get_file_size(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    size_bytes = os.path.getsize(path)
    return humanize.naturalsize(size_bytes)

@app.before_request
def log_request():
    if not request.path.startswith('/static'):
        ip = request.remote_addr
        path = request.path
        if path == '/':
            log_activity(ip, "Opened main page")
        elif path.startswith('/uploads'):
            log_activity(ip, f"Downloaded file: {path.split('/')[-1]}")
        elif request.method == 'POST' and path == '/':
            log_activity(ip, "Attempted file upload")

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': 'No file selected'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            return jsonify({'success': True})
    
    files = [(f, get_file_size(f)) for f in os.listdir(app.config['UPLOAD_FOLDER'])]
    return render_template_string(HTML_TEMPLATE, files=files)

@app.route('/uploads/<filename>')
def download_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/shutdown', methods=['POST'])
def shutdown():
    try:
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            sys.exit(0)  # If shutdown function is not found, exit the program directly
        func()
        return jsonify({'success': True})
    except:
        sys.exit(0)  # In case of any error, exit the program

@app.route('/monitor')
def monitor():
    return render_template_string(MONITOR_TEMPLATE, users=connected_users)

# Create control window
def create_control_window():
    window = tk.Tk()
    window.title("File Sharing Control")
    window.geometry("300x300")  # Increase window size to accommodate new button
    
    # Center the window
    window.eval('tk::PlaceWindow . center')
    
    # Always keep the window on top
    window.attributes('-topmost', True)
    
    # Add title
    title = tk.Label(window, text="File Sharing Program", font=("Arial", 16))
    title.pack(pady=20)
    
    # Add button to open browser
    def open_browser():
        webbrowser.open('http://localhost:5000')
    
    open_btn = tk.Button(window, text="Open in Browser", command=open_browser, 
                        bg='#4a90e2', fg='white', font=("Arial", 12))
    open_btn.pack(pady=10)

    # Add button to monitor users
    def open_monitor():
        webbrowser.open('http://localhost:5000/monitor')
    
    monitor_btn = tk.Button(window, text="Monitor Users", command=open_monitor,
                          bg='#28a745', fg='white', font=("Arial", 12))
    monitor_btn.pack(pady=10)
    
    # Add button to show QR Code
    def show_qr_code():
        # Get device IP address
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        
        # Create URL using IP address
        qr_url = f"http://{ip_address}:{app.config['PORT']}"  # Server address
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Display image in new window
        qr_window = tk.Toplevel(window)
        qr_window.title("QR Code for Connection")
        qr_window.geometry("300x350")
        qr_window.attributes('-topmost', True)
        
        # Convert image to Tkinter compatible format
        img_tk = ImageTk.PhotoImage(img)
        
        # Display image
        label = tk.Label(qr_window, image=img_tk)
        label.image = img_tk  # Prevent image from being garbage collected
        label.pack(pady=10)
        
        # Add explanatory text
        text_label = tk.Label(qr_window, text=f"Open camera and point to QR Code to connect.\nAddress: {qr_url}", font=("Arial", 12))
        text_label.pack(pady=10)
    
    qr_btn = tk.Button(window, text="Show QR Code", command=show_qr_code,
                      bg='#ff9800', fg='white', font=("Arial", 12))
    qr_btn.pack(pady=10)
    
    # Add close button
    def shutdown_server():
        os._exit(0)  # Close the program completely
    
    quit_btn = tk.Button(window, text="Close Program", command=shutdown_server,
                        bg='#dc3545', fg='white', font=("Arial", 12))
    quit_btn.pack(pady=10)
    
    return window

def ensure_upload_folder():
    upload_folder = app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        print(f"Created folder: {upload_folder}")
    else:
        print(f"Folder already exists: {upload_folder}")

if __name__ == '__main__':
    ensure_upload_folder()
    app.config['HOST'] = '0.0.0.0'  # Server address
    app.config['PORT'] = 5000       # Port
    
    # Start thread to monitor active users
    Thread(target=check_active_users, daemon=True).start()
    
    # Run control window in separate thread
    control_window = create_control_window()
    Thread(target=lambda: app.run(host=app.config['HOST'], port=app.config['PORT'], debug=False)).start()
    control_window.mainloop()
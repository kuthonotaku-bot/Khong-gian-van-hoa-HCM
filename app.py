import os
import re
import sqlite3
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, session

app = Flask(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

app.secret_key = 'khong-gian-van-hoa-hcm-secret-key'
ADMIN_PASSWORD = 'admin123'


# ─── Database ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                type TEXT,
                drive_link TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                option_a TEXT,
                option_b TEXT,
                option_c TEXT,
                option_d TEXT,
                correct_answer INTEGER
            );
        ''')


# ─── Helpers ──────────────────────────────────────────────────────────────────
def extract_drive_file_id(link):
    """Extract FILE_ID from various Google Drive share link formats."""
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
        r'/d/([a-zA-Z0-9_-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return match.group(1)
    return None


def make_drive_direct_link(file_id):
    """Convert FILE_ID to a direct Google Drive view/embed link."""
    # Changed to return the 'view' format instead of 'uc?export=view'
    return f'https://drive.google.com/file/d/{file_id}/view'


def normalize_youtube_url(url):
    """Normalize any YouTube URL to an embed URL."""
    # Match standard watch URL: youtube.com/watch?v=VIDEO_ID
    match = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
    if match:
        video_id = match.group(1)
        return f'https://www.youtube.com/embed/{video_id}'
    # If already an embed URL, return as-is
    if 'youtube.com/embed/' in url:
        return url
    # Return original if unable to parse
    return url


def login_required(f):
    """Decorator to protect admin routes."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ─── Public Routes ────────────────────────────────────────────────────────────
@app.route('/')
def index():
    with get_db() as conn:
        images = conn.execute(
            "SELECT title, drive_link FROM resources WHERE type='image' ORDER BY created_at DESC"
        ).fetchall()
        docs = conn.execute(
            "SELECT title, drive_link FROM resources WHERE type='document' ORDER BY created_at DESC"
        ).fetchall()
    return render_template('index.html', images=images, docs=docs)


# ─── Auth Routes ──────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        else:
            error = 'Mật khẩu không đúng. Vui lòng thử lại.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── Admin Routes ─────────────────────────────────────────────────────────────
@app.route('/admin')
@login_required
def admin():
    return render_template('admin.html')


@app.route('/add-image-link', methods=['POST'])
@login_required
def add_image_link():
    data = request.json
    link = (data.get('link') or '').strip()
    title = (data.get('title') or 'Hình ảnh').strip()

    if not link:
        return jsonify({'error': 'Vui lòng nhập link Google Drive'}), 400

    file_id = extract_drive_file_id(link)
    if not file_id:
        return jsonify({'error': 'Không thể trích xuất File ID từ link. Vui lòng dùng link "Share" của Google Drive.'}), 400

    drive_link = make_drive_direct_link(file_id)

    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO resources (title, type, drive_link) VALUES (?, 'image', ?)",
            (title, drive_link)
        )
        resource_id = cursor.lastrowid

    return jsonify({'success': True, 'id': resource_id, 'drive_link': drive_link}), 200


@app.route('/add-document-link', methods=['POST'])
@login_required
def add_document_link():
    data = request.json
    link = (data.get('link') or '').strip()
    title = (data.get('title') or 'Tài liệu').strip()

    if not link:
        return jsonify({'error': 'Vui lòng nhập link Google Drive'}), 400

    file_id = extract_drive_file_id(link)
    if not file_id:
        return jsonify({'error': 'Không thể trích xuất File ID từ link. Vui lòng dùng link "Share" của Google Drive.'}), 400

    # For documents, we use the direct view link now
    drive_link = make_drive_direct_link(file_id)

    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO resources (title, type, drive_link) VALUES (?, 'document', ?)",
            (title, drive_link)
        )
        resource_id = cursor.lastrowid

    return jsonify({'success': True, 'id': resource_id, 'drive_link': drive_link}), 200


@app.route('/get-resources', methods=['GET'])
@login_required
def get_resources():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, type, drive_link FROM resources ORDER BY created_at DESC"
        ).fetchall()
    
    result = [dict(row) for row in rows]
    return jsonify(result), 200


@app.route('/delete-resource/<int:resource_id>', methods=['DELETE'])
@login_required
def delete_resource(resource_id):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── Questions Routes ─────────────────────────────────────────────────────────
@app.route('/save-questions', methods=['POST'])
@login_required
def save_questions():
    data = request.json
    if not isinstance(data, list):
        return jsonify({'error': 'Dữ liệu không hợp lệ'}), 400

    try:
        with get_db() as conn:
            conn.execute("DELETE FROM questions")
            for q in data:
                options = q.get('options', ['', '', '', ''])
                conn.execute(
                    """INSERT INTO questions
                       (question, option_a, option_b, option_c, option_d, correct_answer)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        q.get('q', ''),
                        options[0] if len(options) > 0 else '',
                        options[1] if len(options) > 1 else '',
                        options[2] if len(options) > 2 else '',
                        options[3] if len(options) > 3 else '',
                        int(q.get('correct', 0))
                    )
                )
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get-questions', methods=['GET'])
def get_questions():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT question, option_a, option_b, option_c, option_d, correct_answer FROM questions"
        ).fetchall()

    result = [
        {
            'q': row['question'],
            'options': [row['option_a'], row['option_b'], row['option_c'], row['option_d']],
            'correct': row['correct_answer']
        }
        for row in rows
    ]
    return jsonify(result), 200


# ─── Videos Routes ────────────────────────────────────────────────────────────
@app.route('/save-videos', methods=['POST'])
@login_required
def save_videos():
    data = request.json
    if not isinstance(data, list):
        return jsonify({'error': 'Dữ liệu không hợp lệ'}), 400

    try:
        with get_db() as conn:
            conn.execute("DELETE FROM videos")
            for v in data:
                raw_url = (v.get('url') or '').strip()
                if raw_url:
                    embed_url = normalize_youtube_url(raw_url)
                    conn.execute("INSERT INTO videos (url) VALUES (?)", (embed_url,))
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get-videos', methods=['GET'])
def get_videos():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT url FROM videos ORDER BY created_at ASC"
        ).fetchall()

    result = [{'url': row['url']} for row in rows]
    return jsonify(result), 200


# ─── Startup ──────────────────────────────────────────────────────────────────
init_db()

if __name__ == '__main__':
    print("Khởi động server Flask tại: http://0.0.0.0:5001")
    print("Vui lòng đảm bảo đã cài: pip install flask gunicorn")
    app.run(debug=True, host='0.0.0.0', port=5001)

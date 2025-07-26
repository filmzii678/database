from flask import Flask, request, jsonify, render_template_string
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime

app = Flask(__name__)
auth = HTTPBasicAuth()

# Configure database
DATABASE = 'media.db'

# User credentials (in production, use environment variables)
users = {
    "Venera": generate_password_hash("Venera")
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK (type IN ('movie', 'tvseries')),
            title TEXT NOT NULL,
            thumbnail_url TEXT,
            details TEXT,
            release_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.execute('''
        CREATE TABLE IF NOT EXISTS tv_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id INTEGER NOT NULL,
            season_number INTEGER NOT NULL,
            episode_number INTEGER NOT NULL,
            title TEXT,
            video_link TEXT NOT NULL,
            FOREIGN KEY (series_id) REFERENCES media(id)
        )
        ''')
        
        conn.execute('''
        CREATE TABLE IF NOT EXISTS movie_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id INTEGER NOT NULL,
            resolution TEXT,
            video_link TEXT NOT NULL,
            FOREIGN KEY (movie_id) REFERENCES media(id)
        )
        ''')
        conn.commit()

# Initialize database
init_db()

# =====================
# PUBLIC ENDPOINTS
# =====================

@app.route('/')
def home():
    return "Movie & TV Series API running! For admin interface, go to /admin"

@app.route('/media')
def get_all_media():
    with get_db() as conn:
        media = conn.execute('SELECT * FROM media').fetchall()
        return jsonify([dict(row) for row in media])

@app.route('/media/<int:media_id>')
def get_media(media_id):
    with get_db() as conn:
        media = conn.execute('SELECT * FROM media WHERE id = ?', (media_id,)).fetchone()
        if not media:
            return jsonify({"error": "Media not found"}), 404
        
        media_data = dict(media)
        
        if media['type'] == 'movie':
            links = conn.execute('''
                SELECT resolution, video_link 
                FROM movie_links 
                WHERE movie_id = ?
            ''', (media_id,)).fetchall()
            media_data['video_links'] = [dict(link) for link in links]
        else:
            episodes = conn.execute('''
                SELECT season_number, episode_number, title, video_link 
                FROM tv_episodes 
                WHERE series_id = ?
                ORDER BY season_number, episode_number
            ''', (media_id,)).fetchall()
            media_data['episodes'] = [dict(ep) for ep in episodes]
        
        return jsonify(media_data)

# =====================
# ADMIN ENDPOINTS
# =====================

@app.route('/admin/media', methods=['POST'])
@auth.login_required
def add_media():
    data = request.get_json()
    
    required_fields = ['type', 'title']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
    
    if data['type'] not in ['movie', 'tvseries']:
        return jsonify({"error": "Invalid media type"}), 400
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO media (type, title, thumbnail_url, details, release_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                data['type'],
                data['title'],
                data.get('thumbnail_url'),
                data.get('details'),
                data.get('release_date')
            ))
            media_id = cursor.lastrowid
            
            if data['type'] == 'movie' and 'video_links' in data:
                for link in data['video_links']:
                    cursor.execute('''
                        INSERT INTO movie_links (movie_id, resolution, video_link)
                        VALUES (?, ?, ?)
                    ''', (media_id, link.get('resolution'), link['video_link']))
            
            elif data['type'] == 'tvseries' and 'episodes' in data:
                for episode in data['episodes']:
                    cursor.execute('''
                        INSERT INTO tv_episodes (series_id, season_number, episode_number, title, video_link)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        media_id,
                        episode['season_number'],
                        episode['episode_number'],
                        episode.get('title'),
                        episode['video_link']
                    ))
            
            conn.commit()
            return jsonify({"message": "Media added successfully", "id": media_id}), 201
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/media/<int:media_id>/episodes', methods=['POST'])
@auth.login_required
def add_episodes(media_id):
    data = request.get_json()
    
    if not isinstance(data, list):
        return jsonify({"error": "Expected array of episodes"}), 400
    
    try:
        with get_db() as conn:
            # Verify media exists and is a TV series
            media = conn.execute('SELECT type FROM media WHERE id = ?', (media_id,)).fetchone()
            if not media:
                return jsonify({"error": "Media not found"}), 404
            if media['type'] != 'tvseries':
                return jsonify({"error": "Can only add episodes to TV series"}), 400
            
            for episode in data:
                conn.execute('''
                    INSERT INTO tv_episodes (series_id, season_number, episode_number, title, video_link)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    media_id,
                    episode['season_number'],
                    episode['episode_number'],
                    episode.get('title'),
                    episode['video_link']
                ))
            
            conn.commit()
            return jsonify({"message": f"{len(data)} episodes added successfully"}), 201
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Admin HTML Interface (similar to your original but expanded for TV series)
ADMIN_PAGE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <!-- Your existing CSS styles -->
    <style>
        /* ... (keep all your existing styles) ... */
        
        /* Additional styles for TV series form */
        .episode-form {
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 15px;
        }
        
        .episode-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        
        .remove-episode {
            background: #ff6b6b;
            color: white;
            border: none;
            border-radius: 50%;
            width: 25px;
            height: 25px;
            cursor: pointer;
        }
        
        .media-type-selector {
            display: flex;
            margin-bottom: 20px;
        }
        
        .media-type-btn {
            flex: 1;
            padding: 15px;
            text-align: center;
            background: rgba(255,255,255,0.1);
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .media-type-btn.active {
            background: #667eea;
            color: white;
        }
        
        .media-type-btn:first-child {
            border-radius: 10px 0 0 10px;
        }
        
        .media-type-btn:last-child {
            border-radius: 0 10px 10px 0;
        }
        
        #episodes-container {
            margin-top: 20px;
        }
        
        #add-episode {
            background: #4ecdc4;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 5px;
            cursor: pointer;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="floating-shapes">
        <div class="shape"></div>
        <div class="shape"></div>
        <div class="shape"></div>
    </div>

    <div class="container">
        <div class="header">
            <div class="icon">🎬</div>
            <h1>Media Admin</h1>
            <p class="subtitle">Add new movies or TV series to your collection</p>
        </div>
        
        <form id="mediaForm">
            <div class="media-type-selector">
                <div class="media-type-btn active" data-type="movie">Movie</div>
                <div class="media-type-btn" data-type="tvseries">TV Series</div>
            </div>
            
            <div class="form-grid">
                <div class="form-group">
                    <label for="title">🎭 Title</label>
                    <input type="text" id="title" name="title" required placeholder="Enter title" />
                </div>
                
                <div class="form-group">
                    <label for="thumbnail_url">🖼️ Thumbnail URL</label>
                    <input type="url" id="thumbnail_url" name="thumbnail_url" placeholder="https://example.com/poster.jpg" />
                </div>
                
                <div class="form-group">
                    <label for="details">📝 Details</label>
                    <textarea id="details" name="details" placeholder="Enter description..."></textarea>
                </div>
                
                <div class="form-group">
                    <label for="release_date">📅 Release Date</label>
                    <input type="date" id="release_date" name="release_date" />
                </div>
                
                <!-- Movie specific fields -->
                <div id="movie-fields" class="form-group">
                    <label>🎥 Download Links</label>
                    <div class="resolution-grid">
                        <div class="resolution-item">
                            <label>1080p HD</label>
                            <input type="url" id="video_link_1080p" name="video_link_1080p" placeholder="HD download link" />
                        </div>
                        <div class="resolution-item">
                            <label>720p</label>
                            <input type="url" id="video_link_720p" name="video_link_720p" placeholder="Standard download link" />
                        </div>
                        <div class="resolution-item">
                            <label>480p</label>
                            <input type="url" id="video_link_480p" name="video_link_480p" placeholder="Mobile download link" />
                        </div>
                    </div>
                </div>
                
                <!-- TV Series specific fields -->
                <div id="tvseries-fields" class="form-group" style="display: none;">
                    <label>📺 Episodes</label>
                    <button type="button" id="add-episode">➕ Add Episode</button>
                    <div id="episodes-container"></div>
                </div>
            </div>
            
            <button type="submit" class="btn">
                <span>Add to Collection</span>
            </button>
            
            <div id="message"></div>
        </form>
    </div>

    <script>
        const form = document.getElementById('mediaForm');
        const message = document.getElementById('message');
        const submitBtn = form.querySelector('.btn');
        const typeButtons = document.querySelectorAll('.media-type-btn');
        const movieFields = document.getElementById('movie-fields');
        const tvseriesFields = document.getElementById('tvseries-fields');
        const addEpisodeBtn = document.getElementById('add-episode');
        const episodesContainer = document.getElementById('episodes-container');
        
        let currentType = 'movie';
        
        // Switch between movie and TV series forms
        typeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                typeButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentType = btn.dataset.type;
                
                if (currentType === 'movie') {
                    movieFields.style.display = 'block';
                    tvseriesFields.style.display = 'none';
                } else {
                    movieFields.style.display = 'none';
                    tvseriesFields.style.display = 'block';
                }
            });
        });
        
        // Add episode form
        addEpisodeBtn.addEventListener('click', () => {
            const episodeDiv = document.createElement('div');
            episodeDiv.className = 'episode-form';
            episodeDiv.innerHTML = `
                <div class="episode-header">
                    <h3>Episode ${episodesContainer.children.length + 1}</h3>
                    <button type="button" class="remove-episode">×</button>
                </div>
                <div class="form-group">
                    <label>Season Number</label>
                    <input type="number" class="season-number" min="1" value="1" required />
                </div>
                <div class="form-group">
                    <label>Episode Number</label>
                    <input type="number" class="episode-number" min="1" value="${episodesContainer.children.length + 1}" required />
                </div>
                <div class="form-group">
                    <label>Episode Title (Optional)</label>
                    <input type="text" class="episode-title" placeholder="Episode title" />
                </div>
                <div class="form-group">
                    <label>Video Link</label>
                    <input type="url" class="episode-link" placeholder="https://example.com/episode.mp4" required />
                </div>
            `;
            
            episodeDiv.querySelector('.remove-episode').addEventListener('click', () => {
                episodesContainer.removeChild(episodeDiv);
            });
            
            episodesContainer.appendChild(episodeDiv);
        });
        
        function showMessage(text, type) {
            message.textContent = text;
            message.className = `show ${type}`;
            
            if (type !== 'loading') {
                setTimeout(() => {
                    message.classList.remove('show');
                }, 4000);
            }
        }
        
        form.onsubmit = async (e) => {
            e.preventDefault();
            
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span>Adding Media...</span>';
            showMessage('Adding media to collection...', 'loading');
            
            const formData = {
                type: currentType,
                title: form.title.value,
                thumbnail_url: form.thumbnail_url.value,
                details: form.details.value,
                release_date: form.release_date.value
            };
            
            if (currentType === 'movie') {
                formData.video_links = [
                    { resolution: '1080p', video_link: form.video_link_1080p.value },
                    { resolution: '720p', video_link: form.video_link_720p.value },
                    { resolution: '480p', video_link: form.video_link_480p.value }
                ].filter(link => link.video_link);
            } else {
                const episodes = [];
                const episodeForms = episodesContainer.querySelectorAll('.episode-form');
                
                episodeForms.forEach(epForm => {
                    episodes.push({
                        season_number: parseInt(epForm.querySelector('.season-number').value),
                        episode_number: parseInt(epForm.querySelector('.episode-number').value),
                        title: epForm.querySelector('.episode-title').value,
                        video_link: epForm.querySelector('.episode-link').value
                    });
                });
                
                if (episodes.length === 0) {
                    showMessage('❌ Please add at least one episode', 'error');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<span>Add to Collection</span>';
                    return;
                }
                
                formData.episodes = episodes;
            }
            
            try {
                const res = await fetch('/admin/media', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Basic ' + btoa('Venera:Venera')
                    },
                    body: JSON.stringify(formData)
                });
                
                const json = await res.json();
                
                if (res.ok) {
                    showMessage(`🎉 Media added successfully! ID: ${json.id}`, 'success');
                    form.reset();
                    episodesContainer.innerHTML = '';
                } else {
                    showMessage(`❌ ${json.error || 'Failed to add media'}`, 'error');
                }
            } catch (err) {
                showMessage(`🔌 Network error: ${err.message}`, 'error');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<span>Add to Collection</span>';
            }
        };
    </script>
</body>
</html>
'''

@app.route('/admin')
@auth.login_required
def admin():
    return render_template_string(ADMIN_PAGE_HTML)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

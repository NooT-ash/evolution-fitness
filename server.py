import os
import json
import sqlite3
import datetime
import secrets
import csv
import io
from flask import Flask, request, jsonify, send_from_directory, Response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_DIR = os.path.join(BASE_DIR, 'assets', 'images')
DB_PATH = os.path.join(DATA_DIR, 'gym_cms.db')
SETTINGS_JSON_PATH = os.path.join(DATA_DIR, 'settings.json')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Verified Default Slots for Visual Photo Manager (VPM)
DEFAULT_VPM_SLOTS = {
    'img_slot_logo': 'assets/images/evolution_fitness_logo_circle.png',
    'img_slot_hero': 'assets/images/real_cardio_turf_hd.jpg',
    'img_slot_about': 'assets/images/real_gym_hall_hd.jpg',
    'img_slot_spotlight': 'assets/images/real_athlete_glory_hd.jpg',
    'img_slot_tour_1': 'assets/images/real_weight_lifting_hd.jpg',
    'img_slot_tour_2': 'assets/images/real_cardio_turf_hd.jpg',
    'img_slot_tour_3': 'assets/images/real_strength_machines_hd.jpg',
    'img_slot_tour_4': 'assets/images/real_boxing_crossfit_hd.jpg',
    'img_slot_tour_5': 'assets/images/real_gmap_weights_hd.jpg',
    'img_slot_tour_6': 'assets/images/real_bodybuilding_physique_hd.jpg',
    'img_slot_program_1': 'assets/images/real_strength_machines_hd.jpg',
    'img_slot_program_2': 'assets/images/personal_training.jpg',
    'img_slot_program_3': 'assets/images/zumba_class.jpg',
    'img_slot_program_4': 'assets/images/yoga_stretch.jpg',
    'img_slot_program_5': 'assets/images/real_boxing_crossfit_hd.jpg',
    'img_slot_program_6': 'assets/images/nutrition_diet.jpg',
}

app = Flask(__name__, static_folder=BASE_DIR)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.route('/api/<path:subpath>', methods=['OPTIONS'])
def handle_options(subpath):
    res = Response(status=200)
    res.headers['Access-Control-Allow-Origin'] = '*'
    res.headers['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, DELETE, OPTIONS'
    res.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return res

# Active admin tokens (in-memory, persists while server runs)
ACTIVE_TOKENS = set()
DEFAULT_ADMIN_PASS = "evolution2026"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def sync_settings_json():
    """Sync current settings to a static JSON file for Netlify / static offline fallback."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM settings')
        data = {row['key']: row['value'] for row in cursor.fetchall()}
        conn.close()
        data.pop('admin_password', None)
        with open(SETTINGS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump({'settings': data, 'updated_at': datetime.datetime.now().isoformat()}, f, indent=2)
    except Exception as e:
        print(f"Error syncing settings.json: {e}")

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            service TEXT,
            notes TEXT,
            status TEXT DEFAULT 'New',
            admin_notes TEXT DEFAULT ''
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    # Seed default settings from gym_profile.json if empty
    cursor.execute('SELECT COUNT(*) as count FROM settings')
    if cursor.fetchone()['count'] == 0:
        default_settings = {
            'announcement_active': 'true',
            'announcement_text': 'Open 7 Days a Week: 6:00 AM – 10:00 PM | Dhanori-Lohegaon Rd (Nr HP Petrol Pump)',
            'gym_name': 'Evolution Fitness',
            'reception_phone': '+91 93707 37887',
            'primary_phone': '+91 89287 44136',
            'whatsapp_phone': '918928744136',
            'starter_plan_price': '1,499',
            'starter_plan_period': 'month',
            'momentum_plan_price': '3,999',
            'momentum_plan_period': '3 months',
            'vip_plan_price': '9,999',
            'vip_plan_period': 'year',
            'hours_weekday': '6:00 AM – 10:00 PM',
            'hours_weekend': '6:00 AM – 10:00 PM',
            'admin_password': DEFAULT_ADMIN_PASS
        }
        for k, v in default_settings.items():
            cursor.execute('INSERT INTO settings (key, value) VALUES (?, ?)', (k, v))
        
        # Add sample leads so dashboard has instant demo data
        sample_leads = [
            (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'Amit Deshmukh', '98220 12345', '1-on-1 Personal Training', 'Interested in evening slot with Manoj Sir', 'Trial Scheduled', 'Trial confirmed for Tuesday 7 PM'),
            (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'Sneha Kulkarni', '98901 67890', 'Zumba & Yoga', 'Wants morning 8 AM Zumba batch details', 'Contacted', 'Shared batch schedule on WhatsApp'),
            (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'Vikram Salunkhe', '99705 43210', 'Strength & Muscle Gain', 'College student nearby, asking for student discount', 'New', '')
        ]
        cursor.executemany('''
            INSERT INTO leads (created_at, name, phone, service, notes, status, admin_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', sample_leads)

    # Ensure all VPM image slots are seeded
    for slot_key, default_img in DEFAULT_VPM_SLOTS.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (slot_key, default_img))

    conn.commit()
    conn.close()
    sync_settings_json()

init_db()

def require_auth(req):
    auth_header = req.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        if token in ACTIVE_TOKENS:
            return True
    return False

# ----------------- Static File Routes -----------------

@app.route('/')
def serve_index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/admin')
def serve_admin():
    return send_from_directory(BASE_DIR, 'admin.html')

@app.route('/assets/<path:filepath>')
def serve_assets(filepath):
    return send_from_directory(os.path.join(BASE_DIR, 'assets'), filepath)

# ----------------- Auth API -----------------

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    password = data.get('password', '')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('admin_password',))
    row = cursor.fetchone()
    conn.close()

    stored_pass = row['value'] if row else DEFAULT_ADMIN_PASS

    if password == stored_pass:
        token = secrets.token_hex(24)
        ACTIVE_TOKENS.add(token)
        return jsonify({'success': True, 'token': token, 'message': 'Welcome to Evolution Fitness Admin'})
    else:
        return jsonify({'success': False, 'message': 'Incorrect admin password'}), 401

@app.route('/api/auth/verify', methods=['GET'])
def api_verify():
    if require_auth(request):
        return jsonify({'authenticated': True})
    return jsonify({'authenticated': False}), 401

@app.route('/api/auth/change-password', methods=['POST'])
def api_change_password():
    if not require_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    new_pass = data.get('new_password', '').strip()
    if len(new_pass) < 4:
        return jsonify({'error': 'Password must be at least 4 characters long'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE settings SET value = ? WHERE key = ?', (new_pass, 'admin_password'))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Password changed successfully'})

# ----------------- Leads API -----------------

@app.route('/api/leads', methods=['GET'])
def get_leads():
    if not require_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM leads ORDER BY id DESC')
    leads = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'leads': leads})

@app.route('/api/leads', methods=['POST'])
def submit_lead():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    service = data.get('service', 'General Fitness').strip()
    notes = data.get('notes', '').strip()

    if not name or not phone:
        return jsonify({'error': 'Name and phone are required'}), 400

    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO leads (created_at, name, phone, service, notes, status, admin_notes)
        VALUES (?, ?, ?, ?, ?, 'New', '')
    ''', (now, name, phone, service, notes))
    conn.commit()
    lead_id = cursor.lastrowid
    conn.close()

    return jsonify({'success': True, 'lead_id': lead_id, 'message': 'Trial request registered!'})

@app.route('/api/leads/<int:lead_id>', methods=['PATCH'])
def update_lead(lead_id):
    if not require_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    status = data.get('status')
    admin_notes = data.get('admin_notes')

    conn = get_db()
    cursor = conn.cursor()
    
    updates = []
    params = []
    if status is not None:
        updates.append('status = ?')
        params.append(status)
    if admin_notes is not None:
        updates.append('admin_notes = ?')
        params.append(admin_notes)

    if updates:
        params.append(lead_id)
        cursor.execute(f"UPDATE leads SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

    conn.close()
    return jsonify({'success': True})

@app.route('/api/leads/<int:lead_id>', methods=['DELETE'])
def delete_lead(lead_id):
    if not require_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM leads WHERE id = ?', (lead_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/leads/export', methods=['GET'])
def export_leads():
    if not require_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, created_at, name, phone, service, status, notes, admin_notes FROM leads ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(['Lead ID', 'Date & Time', 'Name', 'Phone', 'Program / Goal', 'Status', 'User Notes', 'Staff Notes'])
    for r in rows:
        writer.writerow(list(r))

    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8-sig'))
    output.seek(0)

    filename = f"evolution_fitness_leads_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/data/<path:filepath>')
def serve_data(filepath):
    return send_from_directory(DATA_DIR, filepath)

# ----------------- Settings & Content API -----------------

@app.route('/api/settings', methods=['GET'])
def get_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings')
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    # Don't expose password hash in public settings
    settings.pop('admin_password', None)
    return jsonify({'settings': settings})

@app.route('/api/settings', methods=['POST'])
def update_settings():
    if not require_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    conn = get_db()
    cursor = conn.cursor()

    for k, v in data.items():
        if k != 'admin_password':
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (str(k), str(v)))

    conn.commit()
    conn.close()
    sync_settings_json()
    return jsonify({'success': True, 'message': 'Settings updated successfully'})

# ----------------- Visual Photo Manager (VPM) API -----------------

VPM_METADATA = [
    {
        'id': 'logo',
        'key': 'img_slot_logo',
        'category': 'brand',
        'title': 'Official Gym Logo Emblem',
        'section': 'Header Navbar, Mobile Drawer & Footer',
        'desc': 'Primary circular emblem used in branding across top header and bottom footer.',
        'aspect': '1:1 Square (1024×1024px)',
        'default': 'assets/images/evolution_fitness_logo_circle.png'
    },
    {
        'id': 'hero',
        'key': 'img_slot_hero',
        'category': 'hero',
        'title': 'Hero Main Showcase Banner',
        'section': 'Top Hero Section (Above the fold)',
        'desc': 'High-impact background showing the spacious green sprint turf, treadmills and gym floor.',
        'aspect': '16:9 Landscape (Min 1600×900px)',
        'default': 'assets/images/real_cardio_turf_hd.jpg'
    },
    {
        'id': 'about',
        'key': 'img_slot_about',
        'category': 'hero',
        'title': 'About Facility Ambience',
        'section': "'Why Lohegaon Trains Here' Section",
        'desc': 'Wide view of the main workout hall highlighting modern industrial LED ceiling strip lighting.',
        'aspect': '4:3 or 16:9 Landscape (Min 1200×800px)',
        'default': 'assets/images/real_gym_hall_hd.jpg'
    },
    {
        'id': 'spotlight',
        'key': 'img_slot_spotlight',
        'category': 'hero',
        'title': 'Athlete Glory & Awards Wall',
        'section': 'Coaching Excellence Feature Spotlight',
        'desc': 'Certified trainer and athlete trophy wall representing championship discipline and results.',
        'aspect': '3:4 Portrait (Min 800×1066px)',
        'default': 'assets/images/real_athlete_glory_hd.jpg'
    },
    {
        'id': 'tour_1',
        'key': 'img_slot_tour_1',
        'category': 'tour',
        'title': 'Facility Tour #1: Olympic Weightlifting Bay',
        'section': 'Virtual Tour Grid - Item 1',
        'desc': 'Squat racks, Olympic barbells, power cages, and heavy bumper plates.',
        'aspect': '4:3 Landscape (Min 1200×900px)',
        'default': 'assets/images/real_weight_lifting_hd.jpg'
    },
    {
        'id': 'tour_2',
        'key': 'img_slot_tour_2',
        'category': 'tour',
        'title': 'Facility Tour #2: Cardio & Sprint Turf',
        'section': 'Virtual Tour Grid - Item 2',
        'desc': 'Commercial high-incline treadmills, ellipticals, and dedicated sprint track turf.',
        'aspect': '4:3 Landscape (Min 1200×900px)',
        'default': 'assets/images/real_cardio_turf_hd.jpg'
    },
    {
        'id': 'tour_3',
        'key': 'img_slot_tour_3',
        'category': 'tour',
        'title': 'Facility Tour #3: Pin-Loaded Strength Line',
        'section': 'Virtual Tour Grid - Item 3',
        'desc': 'Chest press, lat pulldowns, leg curl/extension, and dual adjustable cable pulleys.',
        'aspect': '4:3 Landscape (Min 1200×900px)',
        'default': 'assets/images/real_strength_machines_hd.jpg'
    },
    {
        'id': 'tour_4',
        'key': 'img_slot_tour_4',
        'category': 'tour',
        'title': 'Facility Tour #4: Boxing & Functional Rig',
        'section': 'Virtual Tour Grid - Item 4',
        'desc': 'Heavy punching bags, kettlebells, battle ropes, and HIIT conditioning gear.',
        'aspect': '4:3 Landscape (Min 1200×900px)',
        'default': 'assets/images/real_boxing_crossfit_hd.jpg'
    },
    {
        'id': 'tour_5',
        'key': 'img_slot_tour_5',
        'category': 'tour',
        'title': 'Facility Tour #5: Heavy Free-Weight Dumbbells',
        'section': 'Virtual Tour Grid - Item 5',
        'desc': 'Rubber-coated dumbbells ranging from 2.5kg up to 40kg+ with adjustable incline benches.',
        'aspect': '4:3 Landscape (Min 1200×900px)',
        'default': 'assets/images/real_gmap_weights_hd.jpg'
    },
    {
        'id': 'tour_6',
        'key': 'img_slot_tour_6',
        'category': 'tour',
        'title': 'Facility Tour #6: Physique & Elite Conditioning',
        'section': 'Virtual Tour Grid - Item 6',
        'desc': 'Real client muscle definition and physique transformation standards.',
        'aspect': '4:3 Landscape (Min 1200×900px)',
        'default': 'assets/images/real_bodybuilding_physique_hd.jpg'
    },
    {
        'id': 'program_1',
        'key': 'img_slot_program_1',
        'category': 'programs',
        'title': 'Program #1: Strength & Hypertrophy',
        'section': 'Programs Grid - Card 1',
        'desc': 'Progressive overload training, powerlifting, and muscle building routines.',
        'aspect': '16:9 Landscape (Min 800×450px)',
        'default': 'assets/images/real_strength_machines_hd.jpg'
    },
    {
        'id': 'program_2',
        'key': 'img_slot_program_2',
        'category': 'programs',
        'title': 'Program #2: 1-on-1 Personal Training',
        'section': 'Programs Grid - Card 2 (Most Popular)',
        'desc': 'Dedicated coaching with head trainer Manoj Sir & certified specialists.',
        'aspect': '16:9 Landscape (Min 800×450px)',
        'default': 'assets/images/personal_training.jpg'
    },
    {
        'id': 'program_3',
        'key': 'img_slot_program_3',
        'category': 'programs',
        'title': 'Program #3: Group Zumba & Dance Aerobics',
        'section': 'Programs Grid - Card 3',
        'desc': 'High-energy fat-loss dance fitness sessions with motivating music.',
        'aspect': '16:9 Landscape (Min 800×450px)',
        'default': 'assets/images/zumba_class.jpg'
    },
    {
        'id': 'program_4',
        'key': 'img_slot_program_4',
        'category': 'programs',
        'title': 'Program #4: Yoga & Core Mobility',
        'section': 'Programs Grid - Card 4',
        'desc': 'Postural correction, joint flexibility, and breathing exercises.',
        'aspect': '16:9 Landscape (Min 800×450px)',
        'default': 'assets/images/yoga_stretch.jpg'
    },
    {
        'id': 'program_5',
        'key': 'img_slot_program_5',
        'category': 'programs',
        'title': 'Program #5: Functional Boxing & HIIT',
        'section': 'Programs Grid - Card 5',
        'desc': 'Fast-paced calorie burning, agility drills, and kickboxing rounds.',
        'aspect': '16:9 Landscape (Min 800×450px)',
        'default': 'assets/images/real_boxing_crossfit_hd.jpg'
    },
    {
        'id': 'program_6',
        'key': 'img_slot_program_6',
        'category': 'programs',
        'title': 'Program #6: Customized Diet & Nutrition',
        'section': 'Programs Grid - Card 6',
        'desc': 'Calorie-counted Indian meal charts, macro breakdown, and supplementation advice.',
        'aspect': '16:9 Landscape (Min 800×450px)',
        'default': 'assets/images/nutrition_diet.jpg'
    }
]

@app.route('/api/vpm/slots', methods=['GET'])
def get_vpm_slots():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings WHERE key LIKE "img_slot_%"')
    current_slots = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()

    result = []
    for item in VPM_METADATA:
        slot_data = dict(item)
        slot_data['current_url'] = current_slots.get(item['key'], item['default'])
        slot_data['is_custom'] = (slot_data['current_url'] != item['default'])
        result.append(slot_data)

    return jsonify({'slots': result})

@app.route('/api/vpm/reset-slot', methods=['POST'])
def reset_vpm_slot():
    if not require_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    slot_id = data.get('slot', '').strip()
    key = f'img_slot_{slot_id}'

    if key not in DEFAULT_VPM_SLOTS:
        return jsonify({'error': 'Invalid slot'}), 400

    default_val = DEFAULT_VPM_SLOTS[key]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, default_val))
    conn.commit()
    conn.close()

    sync_settings_json()
    return jsonify({'success': True, 'slot': slot_id, 'url': default_val, 'message': 'Slot restored to verified default'})

@app.route('/api/vpm/reset-all', methods=['POST'])
def reset_all_vpm_slots():
    if not require_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    cursor = conn.cursor()
    for key, val in DEFAULT_VPM_SLOTS.items():
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, val))
    conn.commit()
    conn.close()

    sync_settings_json()
    return jsonify({'success': True, 'message': 'All website photo slots restored to verified originals!'})

# ----------------- Image Upload API -----------------

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'svg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if not require_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': f'Unsupported file format. Please upload JPG, PNG, WEBP, or SVG.'}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    clean_base = "".join([c if c.isalnum() or c in ('-', '_') else '_' for c in file.filename.rsplit('.', 1)[0]])
    filename = f"gym_{int(datetime.datetime.now().timestamp())}_{clean_base[:40]}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    file.save(filepath)

    relative_url = f"assets/images/{filename}"
    return jsonify({'success': True, 'url': relative_url, 'filename': filename})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    print(f'Starting Evolution Fitness Server on http://localhost:{port} ...')
    app.run(host='0.0.0.0', port=port, debug=False)

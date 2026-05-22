# kollar endas kakor, version som ska användas med separata html filer

import math
import os
from flask import Flask, render_template, request, session, redirect, url_for, send_file
from authlib.integrations.flask_client import OAuth
import qrcode
from io import BytesIO

app = Flask(__name__)
app.secret_key = "MIN_SUPERHEMLIGA_PROJEKTNYCKEL_123!"

# GOOGLE OAUTH KONFIGURATION
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id='317746992046-9si2oe199ii2i33cd62q05ff21brd2nq.apps.googleusercontent.com',
    client_secret='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',
    access_token_url='https://oauth2.googleapis.com/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
    client_kwargs={'scope': 'openid email profile'},
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
)

# --- GPS-KONFIGURATION ---
# Koordinater för skolan (exempel: ProCivitas Helsingborg)
SCHOOL_LAT = 56.0442
SCHOOL_LON = 12.6974
MAX_DISTANCE_METERS = 200  # Maxavstånd i meter för att bli godkänd

def calculate_distance(lat1, lon1, lat2, lon2):
    """Räknar ut avståndet i meter mellan två GPS-koordinater."""
    R = 6371000  # Jordens radie i meter
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Databas i minnet
rooms = {}

# 1. STARTSIDAN (LÄRARE)
@app.route('/')
def index():
    return render_template('index.html')

# 2. SKAPA NYTT KLASSRUM
@app.route('/skapa-rum', methods=['POST'])
def create_room():
    room_id = request.form.get('room_id', '').strip()
    if not room_id:
        room_id = "Standardrum"
        
    if room_id not in rooms:
        rooms[room_id] = {
            "log": [],
            "lesson_id": 1
        }
    return redirect(url_for('teacher_dashboard', room_id=room_id))

# 3. LÄRARENS SKÄRM (PROJEKTORN)
@app.route('/rum/<room_id>')
def teacher_dashboard(room_id):
    if room_id not in rooms:
        return "Rummet hittades inte", 404
    room_data = rooms[room_id]
    sorted_log = sorted(room_data["log"], key=lambda x: x['namn'])
    return render_template('teacher.html', room_id=room_id, room_data=room_data, sorted_log=sorted_log)

# 4. GENERERA QR-KOD (LÄNKAR DIREKT TILL GOOGLE-INLOGGNINGEN)
@app.route('/qr/<room_id>')
def serve_qr(room_id):
    if room_id not in rooms:
        return "Hittades inte", 404
        
    # QR-koden skickar nu eleven direkt till vår login-rutt med rätt rum laddat
    join_url = f"{request.host_url}login/{room_id}"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(join_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

# 5. SKICKA ELEVEN TILL GOOGLE FOR INLOGGNING
@app.route('/login/<room_id>')
def login(room_id):
    session['target_room'] = room_id  # Kom ihåg vilket rum eleven ska till
    redirect_uri = url_for('login_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

# 6. GOOGLE SKICKAR TILLBAKA ELEVEN HIT EFTER GODKÄND INLOGGNING
@app.route('/login/callback')
def login_callback():
    token = google.authorize_access_token()
    user_info = google.get('userinfo').json()
    
    # Spara elevens Google-info i sessionen
    session['user_email'] = user_info['email']
    session['user_name'] = user_info['name']
    
    room_id = session.get('target_room', 'Standardrum')
    return redirect(url_for('student_join', room_id=room_id))

# 7. ELEVENS REGRISTRERINGSSIDA (EFTER INLOGGNING)
@app.route('/anslut/<room_id>')
def student_join(room_id):
    if room_id not in rooms:
        return "<h1>Klassrummet stängdes.</h1>", 404
        
    # Säkerställ att de faktiskt har loggat in med Google först
    if 'user_email' not in session:
        return redirect(url_for('login', room_id=room_id))
        
    room_data = rooms[room_id]
    
    # FUSKSPÄRR: Kolla om denna Google-e-post redan finns i närvarolistan
    for student in room_data["log"]:
        if student.get("email") == session['user_email']:
            return f"<h1>Redan registrerad!</h1><p>Kontot {session['user_email']} har redan anmält närvaro på den här lektionen.</p>"
            
    return render_template('student.html', room_id=room_id)

# 8. SPARA NÄRVARON (MED GPS-SPÄRR)
@app.route('/spara/<room_id>', methods=['POST'])
def student_save(room_id):
    if room_id not in rooms:
        return "Fel", 404
        
    if 'user_email' not in session:
        return "Nekat! Du måste vara inloggad.", 401
        
    # --- GPS-KONTROLL ---
    try:
        student_lat = float(request.form.get('lat'))
        student_lon = float(request.form.get('lon'))
    except (TypeError, ValueError):
        return "<h1>GPS saknas!</h1><p>Du måste tillåta att webbläsaren ser din plats.</p>", 403

    distance = calculate_distance(SCHOOL_LAT, SCHOOL_LON, student_lat, student_lon)
    
    if distance > MAX_DISTANCE_METERS:
        return f"<h1>Nekat! Du är för långt bort.</h1><p>Du är {int(distance)} meter från skolan. Max tillåtet avstånd är {MAX_DISTANCE_METERS} meter.</p>", 403
    # --------------------

    room_data = rooms[room_id]
    user_email = session['user_email']
    
    for student in room_data["log"]:
        if student.get("email") == user_email:
            return "Redan registrerad!", 403
            
    klass = request.form.get('klass')
    
    student_info = {
        "namn": session['user_name'],
        "klass": klass,
        "email": user_email
    }
    room_data["log"].append(student_info)
    
    return f"<h1>Tack {session['user_name']}!</h1><p>Din närvaro är sparad (Avstånd till skolan: {int(distance)}m).</p>"

# 9. NOLLSTÄLL KLASSRUMMET
@app.route('/nollstall/<room_id>', methods=['POST'])
def reset_room(room_id):
    if room_id in rooms:
        rooms[room_id]["log"] = []
    return redirect(url_for('teacher_dashboard', room_id=room_id))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

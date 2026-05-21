# hnanterar endast kakor, ej ip-adress


from flask import Flask, request, render_template_string, session, redirect, url_for, send_file
import pyotp
import qrcode
import io
import random
import string
from datetime import timedelta

app = Flask(__name__)
app.secret_key = "GLOBAL_SUPER_HEMLIS_FOR_WEBBEN"
app.permanent_session_lifetime = timedelta(hours=12)

# Här sparas alla aktiva lektioner. Format:
# { "RUMS_ID": { "secret": X, "totp": X, "log": [], "ips": [], "lesson_id": 1 } }
rooms = {}



def generate_room_id():
    """Genererar en unik kod på 4 bokstäver, t.ex. 'XFQA'"""
    while True:
        room_id = ''.join(random.choices(string.ascii_uppercase, k=4))
        if room_id not in rooms:
            return room_id

# --- HTML TEMPLATES (Inbakade som strängar för att göra det enkelt att köra) ---

# --- NYA DESIGNADE HTML TEMPLATES ---

INDEX_HTML = """
<!DOCTYPE html>
<html lang="sv">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Digital Närvaro - Start</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light d-flex align-items-center justify-content-center" style="min-height: 100vh;">
    <div class="card shadow-sm p-4 text-center" style="max-width: 500px; width: 100%; border-radius: 12px;">
        <div class="fs-1 mb-3">🏫</div>
        <h1 class="h3 mb-3 fw-bold text-dark">Digital Närvaro</h1>
        <p class="text-muted mb-4">Starta en smidig, fusksäker närvaroregistrering för din klass direkt i webbläsaren.</p>
        <a href="/skapa-rum" class="btn btn-primary btn-lg w-100 fw-bold" style="border-radius: 8px;">Skapa digitalt klassrum</a>
    </div>
</body>
</html>
"""

TEACHER_HTML = """
<!DOCTYPE html>
<html lang="sv">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Lärare - Rum {{ room_id }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light" style="min-height: 100vh; padding: 20px;">
    <div class="container-fluid bg-white shadow-sm rounded-3 p-4 mb-4" style="max-width: 1400px;">
        <div class="d-flex justify-content-between align-items-center flex-wrap gap-3">
            <div>
                <span class="badge bg-primary mb-1">Aktiv Session</span>
                <h1 class="h2 fw-bold m-0 text-dark">Klassrum: <span class="text-primary">{{ room_id }}</span></h1>
            </div>
            <div class="text-md-end">
                <span class="fs-5 text-muted d-block mb-2">Lektionsnummer: <strong>{{ room_data.lesson_id }}</strong></span>
                <form action="/nollstall/{{ room_id }}" method="post" onsubmit="return confirm('Vill du tömma listan och starta nästa lektion?');">
                    <button type="submit" class="btn btn-outline-danger fw-bold btn-sm">🔄 Starta ny lektion (Nollställ)</button>
                </form>
            </div>
        </div>
    </div>

    <div class="container-fluid" style="max-width: 1400px;">
        <div class="row g-4">
            <div class="col-12 col-lg-5 text-center">
                <div class="card shadow-sm border-0 p-4 h-100 d-flex flex-column align-items-center justify-content-center" style="border-radius: 12px;">
                    <h3 class="fw-bold mb-3 text-secondary">SKANNA FÖR NÄRVARO</h3>
                    <div class="p-3 bg-light rounded-3 mb-3" style="border: 1px solid #e3e6f0;">
                        <img id="qr-box" src="/qr/{{ room_id }}" class="img-fluid" style="max-width: 320px; width: 100%;">
                    </div>
                    <div class="d-flex align-items-center gap-2 text-muted">
                        <div class="spinner-grow spinner-grow-sm text-success" role="status"></div>
                        <small>QR-koden uppdateras live var 30:e sekund för att förhindra fusk</small>
                    </div>
                </div>
            </div>

            <div class="col-12 col-lg-7">
                <div class="card shadow-sm border-0 p-4 h-100" style="border-radius: 12px;">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h3 class="fw-bold m-0 text-dark">Registrerade elever</h3>
                        <span class="badge bg-success fs-6">Totalt: {% if sorted_log %}{{ sorted_log|length }}{% else %}0{% endif %}</span>
                    </div>
                    <div class="table-responsive">
                        {% if not sorted_log %}
                            <div class="text-center text-muted py-5">
                                <div class="fs-2 mb-2">💤</div>
                                <p>Inga elever har registrerat sig ännu på den här lektionen.</p>
                            </div>
                        {% else %}
                            <table class="table table-hover align-middle">
                                <thead class="table-light">
                                    <tr>
                                        <th>Namn</th>
                                        <th>Klass</th>
                                        <th class="text-end">Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for student in sorted_log %}
                                    <tr>
                                        <td class="fw-semibold text-dark">{{ student.namn }}</td>
                                        <td><span class="badge bg-secondary">{{ student.klass }}</span></td>
                                        <td class="text-end text-success fw-bold">🟢 Registrerad</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Uppdaterar QR-bilden var 5:e sekund
        setInterval(function(){
            document.getElementById('qr-box').src = "/qr/{{ room_id }}?cache=" + new Date().getTime();
        }, 5000);
        
        // Laddar om sidan var 10:e sekund för att se nya elever
        setInterval(function(){
            location.reload();
        }, 10000);
    </script>
</body>
</html>
"""

STUDENT_HTML = """
<!DOCTYPE html>
<html lang="sv">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Elev - Registrering</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light d-flex align-items-center justify-content-center" style="min-height: 100vh; padding: 15px;">
    <div class="card shadow-sm p-4 text-center" style="max-width: 450px; width: 100%; border-radius: 12px; border-top: 5px solid #0d6efd;">
        <h1 class="h3 fw-bold text-dark mb-1">Registrera Närvaro</h1>
        <p class="text-muted mb-4 small">Klassrumskod: <strong class="text-primary">{{ room_id }}</strong></p>
        
        <form action="/spara/{{ room_id }}" method="post" class="text-start">
            <input type="hidden" name="token" value="{{ token }}">
            
            <div class="mb-3">
                <label class="form-label fw-semibold text-secondary">Ditt fullständiga namn</label>
                <input type="text" name="namn" class="form-control form-control-lg" placeholder="Förnamn Efternamn" required style="border-radius: 8px;">
            </div>
            
            <div class="mb-4">
                <label class="form-label fw-semibold text-secondary">Välj din klass</label>
                <select name="klass" class="form-select form-select-lg" required style="border-radius: 8px;">
                    <option value="" disabled selected>-- Välj i listan --</option>
                    <option value="TE21">TE21</option>
                    <option value="TE22">TE22</option>
                    <option value="TE23">TE23</option>
                    <option value="NA21">NA21</option>
                    <option value="NA22">NA22</option>
                </select>
            </div>
            
            <button type="submit" class="btn btn-primary btn-lg w-100 fw-bold" style="border-radius: 8px;">Sänd närvaro ✅</button>
        </form>
    </div>
</body>
</html>
"""

# --- ROUTING / LOGIK ---

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/skapa-rum')
def create_room():
    room_id = generate_room_id()
    secret = pyotp.random_base32()
    rooms[room_id] = {
        "secret": secret,
        "totp": pyotp.TOTP(secret, interval=30),
        "log": [],
        "lesson_id": 1
    }
    return redirect(url_for('teacher_dashboard', room_id=room_id))

@app.route('/rum/<room_id>')
def teacher_dashboard(room_id):
    if room_id not in rooms:
        return "<h1>Rummet hittades inte!</h1>", 404
    
    room_data = rooms[room_id]
    sorted_log = sorted(room_data["log"], key=lambda x: (x['klass'], x['namn']))
    return render_template_string(TEACHER_HTML, room_id=room_id, room_data=room_data, sorted_log=sorted_log)

@app.route('/qr/<room_id>')
def serve_qr(room_id):
    if room_id not in rooms:
        return "Fel", 404
    
    # Skapa den dynamiska länken som eleven hamnar på när hen skannar
    token = rooms[room_id]["totp"].now()
    student_url = f"{request.host_url}anslut/{room_id}?token={token}"
    
    # Generera QR-koden direkt till en minnesbuffer istället för en fil
    img = qrcode.make(student_url)
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/anslut/<room_id>')
def student_join(room_id):
    if room_id not in rooms:
        return "<h1>Detta rum existerar inte längre.</h1>", 404
        
    room_data = rooms[room_id]
    
    # Kollar ENDAST sessions-kakan nu 
    if session.get(f'last_lesson_{room_id}') == room_data["lesson_id"]:
        return "<h1>Redan registrerad!</h1><p>Du har redan registrerat närvaro på den här lektionen.</p>"
        
    token = request.args.get('token')
    return render_template_string(STUDENT_HTML, room_id=room_id, token=token)

@app.route('/spara/<room_id>', methods=['POST'])
def student_save(room_id):
    if room_id not in rooms:
        return "Fel", 404
        
    room_data = rooms[room_id]
    
    # 1. Vanlig fuskspärr (kakan)
    if session.get(f'last_lesson_{room_id}') == room_data["lesson_id"]:
        return "<h1>Nekat!</h1><p>Du har redan registrerat närvaro.</p>", 403
        
    namn = request.form.get('namn')
    klass = request.form.get('klass')
    token = request.form.get('token')
    
    # NYHET: Skapa en lista för använda koder i rummet om den inte redan finns
    if "used_tokens" not in room_data:
        room_data["used_tokens"] = []
        
    # NYHET: Kolla om exakt denna kod/länk REDAN har använts av någon annan
    if token in room_data["used_tokens"]:
        return "<h1>Länken har redan använts!</h1><p>Den här QR-koden har redan förbrukats av en annan elev. Skanna den nya koden på skärmen.</p>", 403
    
    # UPPDATERAD: valid_window=0 betyder att koden dör DIREKT när klockan slår om (max 30 sekunder)
    if room_data["totp"].verify(token, valid_window=0):
        student_info = {"namn": namn, "klass": klass}
        
        if student_info not in room_data["log"]:
            room_data["log"].append(student_info)
            # NYHET: Spara koden i listan över förbrukade koder
            room_data["used_tokens"].append(token)
            
        session.permanent = True
        session[f'last_lesson_{room_id}'] = room_data["lesson_id"]
        
        return f"<h1>Tack {namn}!</h1><p>Din närvaro i {klass} är sparad.</p>"
    else:
        return "<h1>Koden är för gammal!</h1><p>Denna länk har gått ut. Skanna den nya QR-koden som visas på tavlan just nu.</p>", 403

@app.route('/nollstall/<room_id>', methods=['POST'])
def reset_room(room_id):
    if room_id in rooms:
        rooms[room_id]["lesson_id"] += 1
        rooms[room_id]["log"] = []  # Tömmer bara listan med namn
    return redirect(url_for('teacher_dashboard', room_id=room_id))

import os  # Lägg till denna rad högst upp i din fil om den inte redan finns!

if __name__ == '__main__':
    # Render skickar med en port i systemet, om den inte finns använder vi 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

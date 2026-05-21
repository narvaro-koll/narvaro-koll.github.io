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

def get_client_ip():
    """Hämtar elevens riktiga IP-adress, även bakom Renders dörrvakt"""
    if request.headers.get('X-Forwarded-For'):
        # Tar den första IP-adressen i listan (elevens riktiga)
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

def generate_room_id():
    """Genererar en unik kod på 4 bokstäver, t.ex. 'XFQA'"""
    while True:
        room_id = ''.join(random.choices(string.ascii_uppercase, k=4))
        if room_id not in rooms:
            return room_id

# --- HTML TEMPLATES (Inbakade som strängar för att göra det enkelt att köra) ---

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head><title>Närvaro Start</title><meta charset="utf-8"></head>
<body style="font-family:sans-serif; text-align:center; padding-top:50px;">
    <h1>Digital Närvaroregistrering</h1>
    <p>För lärare: Starta en ny session för din klass utan några nedladdningar.</p>
    <a href="/skapa-rum" style="background:#5cb85c; color:white; padding:15px 25px; text-decoration:none; font-weight:bold; border-radius:5px;">🏫 Skapa nytt digitalt klassrum</a>
</body>
</html>
"""

TEACHER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Lärare - Rum {{ room_id }}</title>
    <meta charset="utf-8">
</head>
<body style="font-family:sans-serif; margin:30px;">
    <h1>Klassrumskod: <span style="color:#0275d8;">{{ room_id }}</span> (Lektion {{ room_data.lesson_id }})</h1>
    
    <div style="display:flex; gap:50px;">
        <div style="text-align:center; border:2px solid #ccc; padding:20px; border-radius:8px;">
            <h3>SKANNA FÖR NÄRVARO</h3>
            <img id="qr-box" src="/qr/{{ room_id }}" width="300" style="border:1px solid #eee;"><br>
            <p><i>Koden uppdateras live i bakgrunden</i></p>
            
            <form action="/nollstall/{{ room_id }}" method="post" onsubmit="return confirm('Vill du tömma listan och starta nästa lektion?');">
                <button type="submit" style="background:#d9534f; color:white; padding:10px; border:none; border-radius:4px; cursor:pointer; font-weight:bold;">🔄 Starta ny lektion (Nollställ)</button>
            </form>
        </div>

        <div style="flex-grow:1;">
            <h2>Registrerade elever ({% if sorted_log %}{{ sorted_log|length }}{% else %}0{% endif %})</h2>
            <hr>
            {% if not sorted_log %}
                <p>Inga elever har registrerat sig ännu.</p>
            {% else %}
                {% set current_klass = list %}
                {% for student in sorted_log %}
                    {% if student.klass != current_klass %}
                        <h3>Klass: {{ student.klass }}</h3>
                        <ul>
                    {% endif %}
                    <li>{{ student.namn }}</li>
                    {% if loop.last or sorted_log[loop.index].klass != student.klass %}
                        </ul>
                    {% endif %}
                {% endfor %}
            {% endif %}
        </div>
    </div>

    <script>
        // Uppdaterar QR-bilden var 5:e sekund så att TOTP-token hålls färsk
        setInterval(function(){
            document.getElementById('qr-box').src = "/qr/{{ room_id }}?cache=" + new Date().getTime();
        }, 5000);
        
        // Laddar om hela sidan var 10:e sekund för att läraren ska se nya elever som loggar in
        setInterval(function(){
            location.reload();
        }, 10000);
    </script>
</body>
</html>
"""

STUDENT_HTML = """
<!DOCTYPE html>
<html>
<head><title>Elev Registrering</title><meta charset="utf-8"></head>
<body style="font-family:sans-serif; margin:20px;">
    <h1>Närvaroregistrering - Rum {{ room_id }}</h1>
    <form action="/spara/{{ room_id }}" method="post">
        <input type="hidden" name="token" value="{{ token }}">
        
        <label>Ditt fullständiga namn:</label><br>
        <input type="text" name="namn" required style="padding:8px; width:200px;"><br><br>
        
        <label>Ange din klass:</label><br>
        <select name="klass" required style="padding:8px; width:212px;">
            <option value="NA1A">NA1A</option>
            <option value="NA1B">NA1B</option>
            <option value="NA1C">NA1C</option>
            <option value="SA1">SA1</option>
            <option value="EK1A">EK1A</option>
            <option value="EK1B">EK1B</option>
            <option value="EK1C">EK1C</option>
            <option value="NA2A">NA2A</option>
            <option value="NA2B">NA2B</option>
            <option value="NA2C">NA2C</option>
            <option value="SA2">SA2</option>
            <option value="EK2A">EK2A</option>
            <option value="EK2B">EK2B</option>
            <option value="EK2C">EK2C</option>
            <option value="NA3A">NA3A</option>
            <option value="NA3B">NA3B</option>
            <option value="NA3C">NA3C</option>
            <option value="SA3">SA3</option>
            <option value="EK3A">EK3A</option>
            <option value="EK3B">EK3B</option>
            <option value="EK3C">EK3C</option>
        </select><br><br>
        
        <button type="submit" style="background:#0275d8; color:white; padding:10px 20px; border:none; border-radius:4px; font-weight:bold;">Sänd närvaro</button>
    </form>
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
        "ips": [],
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
    user_ip = get_client_ip()  # 👈 UPPDATERAD HÄR
    
    if session.get(f'last_lesson_{room_id}') == room_data["lesson_id"] or user_ip in room_data["ips"]:
        return "<h1>Redan registrerad!</h1><p>Den här enheten har redan skickat närvaro för denna lektion.</p>"
        
    token = request.args.get('token')
    return render_template_string(STUDENT_HTML, room_id=room_id, token=token)

@app.route('/spara/<room_id>', methods=['POST'])
def student_save(room_id):
    if room_id not in rooms:
        return "Fel", 404
        
    room_data = rooms[room_id]
    user_ip = get_client_ip()  # 👈 UPPDATERAD HÄR
    
    if session.get(f'last_lesson_{room_id}') == room_data["lesson_id"] or user_ip in room_data["ips"]:
        return "<h1>Nekat!</h1><p>Redan registrerad.</p>", 403
        
    namn = request.form.get('namn')
    klass = request.form.get('klass')
    token = request.form.get('token')
    
    if room_data["totp"].verify(token, valid_window=2):
        student_info = {"namn": namn, "klass": klass}
        if student_info not in room_data["log"]:
            room_data["log"].append(student_info)
            room_data["ips"].append(user_ip)
            
        session.permanent = True
        session[f'last_lesson_{room_id}'] = room_data["lesson_id"]
        
        return f"<h1>Tack {namn}!</h1><p>Din närvaro i {klass} är sparad.</p>"
    else:
        return "<h1>Koden hann gå ut!</h1><p>Be läraren om en ny QR-kod.</p>", 403

@app.route('/nollstall/<room_id>', methods=['POST'])
def reset_room(room_id):
    if room_id in rooms:
        rooms[room_id]["lesson_id"] += 1
        rooms[room_id]["log"] = []
        rooms[room_id]["ips"] = []
    return redirect(url_for('teacher_dashboard', room_id=room_id))

import os  # Lägg till denna rad högst upp i din fil om den inte redan finns!

if __name__ == '__main__':
    # Render skickar med en port i systemet, om den inte finns använder vi 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

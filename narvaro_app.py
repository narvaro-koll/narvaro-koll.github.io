import os
from flask import Flask, render_template, request, session, redirect, url_for, send_file
import pyotp
import qrcode
from io import BytesIO

app = Flask(__name__)
# Den här nyckeln behövs för att spara sessions-kakorna på elevernas mobiler
app.secret_key = "MIN_SUPERHEMLIGA_PROJEKTNYCKEL_123!"

# Här sparas all data om klassrummen i minnet medan servern körs
rooms = {}

# 1. STARTSIDAN
@app.route('/')
def index():
    return render_template('index.html')

# 2. SKAPA NYTT KLASSRUM
@app.route('/skapa-rum')
def create_room():
    room_id = "TE22"  # Detta blir namnet på ditt rum
    if room_id not in rooms:
        secret = pyotp.random_base32()
        rooms[room_id] = {
            "secret": secret,
            "totp": pyotp.TOTP(secret, interval=30),
            "log": [],
            "lesson_id": 1,
            "used_tokens": []  # Här sparas använda engångskoder
        }
    return redirect(url_for('teacher_dashboard', room_id=room_id))

# 3. LÄRARENS INSTRUMENTPANEL (PROJEKTORN)
@app.route('/rum/<room_id>')
def teacher_dashboard(room_id):
    if room_id not in rooms:
        return "Rummet hittades inte", 404
    room_data = rooms[room_id]
    sorted_log = sorted(room_data["log"], key=lambda x: x['namn'])
    return render_template('teacher.html', room_id=room_id, room_data=room_data, sorted_log=sorted_log)

# 4. GENERERA QR-KODEN (BILDEN)
@app.route('/qr/<room_id>')
def serve_qr(room_id):
    if room_id not in rooms:
        return "Hittades inte", 404
        
    room_data = rooms[room_id]
    token = room_data["totp"].now()  # Hämtar den aktuella 6-siffriga koden just nu
    
    # Skapar länken dynamiskt baserat på om du kör lokalt eller på Render
    join_url = f"{request.host_url}anslut/{room_id}?token={token}"
    
    # Ritar QR-koden
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(join_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Sparar bilden i serverns tillfälliga minne och skickar den till webbläsaren
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

# 5. ELEVENS ANKOMSTSIDA (NÄR DE SKANNAT)
@app.route('/anslut/<room_id>')
def student_join(room_id):
    if room_id not in rooms:
        return "<h1>Detta rum existerar inte längre.</h1>", 404
        
    room_data = rooms[room_id]
    
    # Fuskspärr: Har eleven redan registrerat sig på den här lektionen?
    if session.get(f'last_lesson_{room_id}') == room_data["lesson_id"]:
        return "<h1>Redan registrerad!</h1><p>Du har redan skickat in närvaro för denna lektion.</p>"
        
    token = request.args.get('token')
    return render_template('student.html', room_id=room_id, token=token)

# 6. SPARA ELEVENS NÄRVARO (NÄR DE TRYCKER PÅ SÄND)
@app.route('/spara/<room_id>', methods=['POST'])
def student_save(room_id):
    if room_id not in rooms:
        return "Fel", 404
        
    room_data = rooms[room_id]
    
    if session.get(f'last_lesson_{room_id}') == room_data["lesson_id"]:
        return "<h1>Nekat!</h1><p>Redan registrerad.</p>", 403
        
    namn = request.form.get('namn')
    klass = request.form.get('klass')
    token = request.form.get('token')
    
    # Spärr: Har någon ANNAN elev precis använt exakt denna kod?
    if token in room_data.get("used_tokens", []):
        return "<h1>Länken har redan använts!</h1><p>Den här QR-koden har redan förbrukats. Skanna den nya koden på skärmen.</p>", 403
    
    # Kontrollera om tidskoden är giltig just nu (valid_window=0 betyder stenhård koll)
    if room_data["totp"].verify(token, valid_window=0):
        student_info = {"namn": namn, "klass": klass}
        
        if student_info not in room_data["log"]:
            room_data["log"].append(student_info)
            room_data["used_tokens"].append(token)  # Förbruka koden permanent
            
        # Spara lektions-ID i elevens webbläsare (kaka)
        session.permanent = True
        session[f'last_lesson_{room_id}'] = room_data["lesson_id"]
        
        return f"<h1>Tack {namn}!</h1><p>Din närvaro i {klass} är sparad.</p>"
    else:
        return "<h1>Koden är för gammal!</h1><p>Denna länk har gått ut. Skanna den nya QR-koden som visas på tavlan.</p>", 403

# 7. NOLLSTÄLL RUMMET (FÖR NÄSTA LEKTION)
@app.route('/nollstall/{{ room_id }}', methods=['POST'])
@app.route('/nollstall/<room_id>', methods=['POST'])
def reset_room(room_id):
    if room_id in rooms:
        rooms[room_id]["lesson_id"] += 1
        rooms[room_id]["log"] = []
        rooms[room_id]["used_tokens"] = []  # Tömmer de förbrukade koderna
    return redirect(url_for('teacher_dashboard', room_id=room_id))

# STARTA SERVERN
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

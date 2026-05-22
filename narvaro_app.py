import os
from flask import Flask, render_template, request, session, redirect, url_for
import pyotp
import qrcode
from io import BytesIO

app = Flask(__name__)
app.secret_key = "SUPERHEMLIG_NYCKEL_HÄR"
SHARED_SECRET = "MIN_HEMLIGA_BAS32_KOD_HÄR"

rooms = {}

@app.route('/')
def index():
    # Flask letar automatiskt i mappen 'templates' efter index.html
    return render_template('index.html')

@app.route('/skapa-rum')
def create_room():
    room_id = "TE22"  # Eller generera dynamiskt
    if room_id not in rooms:
        secret = pyotp.random_base32()
        rooms[room_id] = {
            "secret": secret,
            "totp": pyotp.TOTP(secret, interval=30),
            "log": [],
            "lesson_id": 1,
            "used_tokens": []
        }
    return redirect(url_for('teacher_dashboard', room_id=room_id))

@app.route('/rum/<room_id>')
def teacher_dashboard(room_id):
    if room_id not in rooms:
        return "Rummet hittades inte", 404
    room_data = rooms[room_id]
    sorted_log = sorted(room_data["log"], key=lambda x: x['namn'])
    
    # Vi skickar med data (variabler) från Python direkt in i HTML-filen!
    return render_template('teacher.html', room_id=room_id, room_data=room_data, sorted_log=sorted_log)

@app.route('/anslut/<room_id>')
def student_join(room_id):
    if room_id not in rooms:
        return "<h1>Detta rum existerar inte längre.</h1>", 404
        
    room_data = rooms[room_id]
    if session.get(f'last_lesson_{room_id}') == room_data["lesson_id"]:
        return "<h1>Redan registrerad!</h1>"
        
    token = request.args.get('token')
    return render_template('student.html', room_id=room_id, token=token)

# ... (resten av dina rutter som /spara och /qr förblir exakt desamma)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

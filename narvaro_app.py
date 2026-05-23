# note to self: kollar endas kakor, version som ska användas med separata html filer


import pyotp
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
        secret = pyotp.random_base32()
        rooms[room_id] = {
            "totp": pyotp.TOTP(secret, interval=10), # QR-koden är giltig i 15 sekunder
            "log": [],
            "lesson_id": 1
        }
    return redirect(url_for('teacher_dashboard', room_id=room_id))

# 3. LÄRARENS SKÄRM (projektorn)
@app.route('/rum/<room_id>')
def teacher_dashboard(room_id):
    if room_id not in rooms:
        return "Rummet hittades inte", 404
        
    room_data = rooms[room_id]
    
    # NY SORTERINGSFUNKTION:
    def sortera_elever(student):
        klass = student.get('klass', '')
        hela_namnet = student.get('namn', '')
        
        # Plockar ut sista ordet i namnet (efternamnet) och gör det till små bokstäver
        # så att "Andersson" och "andersson" sorteras likadant.
        efternamn = hela_namnet.split()[-1].lower() if hela_namnet else ''
        
        # Returnerar en "tuple" (klass, efternamn) vilket säger till Python:
        # Sortera ALLTID på klass först, och inom samma klass: sortera på efternamnet.
        return (klass, efternamn)
        
    # Sortera listan med vår nya logik
    sorted_log = sorted(room_data["log"], key=sortera_elever)
    
    return render_template('teacher.html', room_id=room_id, room_data=room_data, sorted_log=sorted_log)

# 4. GENERERA QR-KOD 
@app.route('/qr/<room_id>')
def serve_qr(room_id):
    if room_id not in rooms:
        return "Hittades inte", 404
        
    room_data = rooms[room_id]
    token = room_data["totp"].now() # Hämtar tidskoden just nu
    
    # Skickar med token in i inloggningslänken
    join_url = f"{request.host_url}login/{room_id}?token={token}"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(join_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

# 5. SKICKA ELEVEN TILL GOOGLE 
@app.route('/login/<room_id>')
def login(room_id):
    if room_id not in rooms:
        return "Rummet finns inte", 404

    token = request.args.get('token')
    room_data = rooms[room_id]
    
    # FUSKSPÄRR 1: Är länken för gammal?
    # valid_window=1 ger lite marginal så att de hinner skanna
    if not token or not room_data["totp"].verify(token, valid_window=0):
        return "<h1>Länken har gått ut! ⏰</h1><p>Du var för långsam, eller så har någon skickat en gammal länk till dig. Skanna den senaste QR-koden på tavlan.</p>", 403

    # Om tiden är okej, släpp vidare till Google!
    session['target_room'] = room_id
    redirect_uri = url_for('login_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

# 6. GOOGLE SKICKAR TILLBAKA ELEVEN EFTER GODKÄND INLOGGNING
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
        
    room_data = rooms[room_id]
        
    # FUSKSPÄRR 1: Har den här enheten (mobilen) redan registrerat sig?
    if session.get(f'device_registered_{room_id}') == room_data["lesson_id"]:
        return "<h1>Enhet spärrad! 📱</h1><p>Den här mobilen har redan använts för att registrera närvaro på denna lektion. Du kan inte logga in flera personer från samma enhet.</p>"

    # Säkerställ att de har loggat in med Google först
    if 'user_email' not in session:
        return redirect(url_for('login', room_id=room_id))
        
    # FUSKSPÄRR 2: Kolla om denna Google-e-post redan finns i närvarolistan
    for student in room_data["log"]:
        if student.get("email") == session['user_email']:
            return f"<h1>Redan registrerad!</h1><p>Kontot {session['user_email']} har redan anmält närvaro på den här lektionen.</p>"
            
    return render_template('student.html', room_id=room_id)


# 8. SPARA NÄRVARON 
@app.route('/spara/<room_id>', methods=['POST'])
def student_save(room_id):
    if room_id not in rooms:
        return "Fel", 404
        
    room_data = rooms[room_id]

    # Dubbelkoll av enhet vid inskick
    if session.get(f'device_registered_{room_id}') == room_data["lesson_id"]:
        return "Nekat! Enheten har redan använts.", 403

    if 'user_email' not in session:
        return "Nekat! Du måste vara inloggad.", 401

    user_email = session['user_email']
    
    # Dubbelkoll av e-post
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
    
    # SPARA I KAKAN ATT MOBILEN HAR REGISTRERAT SIG
    session.permanent = True
    session[f'device_registered_{room_id}'] = room_data["lesson_id"]
    
    return f"<h1>Tack {session['user_name']}!</h1><p>Din närvaro är sparad.</p>"


# 9. NOLLSTÄLL KLASSRUMMET
@app.route('/nollstall/<room_id>', methods=['POST'])
def reset_room(room_id):
    if room_id in rooms:
        rooms[room_id]["log"] = []
    return redirect(url_for('teacher_dashboard', room_id=room_id))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

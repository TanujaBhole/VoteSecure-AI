import os
import base64
import uuid
import threading
from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import random
from datetime import datetime
from config import Config
from config import basedir
from models import db, User, Election, Candidate, Vote, SecurityLog
from ai_modules.face_auth import verify_face
from ai_modules.fraud_detection import analyze_voting_pattern

UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads', 'candidates')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
mail = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
with app.app_context():
    db.create_all()
    # Create default admin if not exists or update existing
    admin_aadhaar = '385051555262'
    admin_pass = 'tanuja@22'
    
    admin = User.query.filter_by(is_admin=True).first()

    if not admin:
        existing_user = User.query.filter_by(aadhaar=admin_aadhaar).first()
        if existing_user:
            existing_user.is_admin = True
            existing_user.is_verified = True
        else:
            admin = User(
                full_name='System Admin',
                aadhaar=admin_aadhaar,
                email='admin@ly.com',
                phone='0000000000',
                address='Admin Office',
                city='System',
                password_hash=generate_password_hash(admin_pass),
                is_admin=True,
                is_verified=True
            )
            db.session.add(admin)

    db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def log_security(user_id, action, details=""):
    log = SecurityLog(user_id=user_id, action=action, details=details, ip_address=request.remote_addr)
    db.session.add(log)
    db.session.commit()

def send_result_emails_in_background(app_obj, user_details, title, is_tie, winner_name, winner_party):
    with app_obj.app_context():
        with mail.connect() as conn:
            for email, full_name in user_details:
                body = f"Hello {full_name},\n\n"
                body += f"The results for the election \"{title}\" have been officially declared.\n\n"
                if is_tie:
                    body += "The election has ended in a tie.\n\n"
                elif winner_name != "N/A":
                    body += f"🏆 Winner: {winner_name}\n"
                    body += f"🏛 Party: {winner_party}\n\n"
                else:
                    body += "No votes were cast in this election.\n\n"
                
                body += "Please log in to VoteSecure AI to view:\n"
                body += "• Complete Results\n"
                body += "• Winner Card\n"
                body += "• Candidate Rankings\n"
                body += "• Vote Statistics\n\n"
                body += "Thank you for participating in the election.\n\n"
                body += "Regards,\nVoteSecure AI Team"
                
                try:
                    msg = Message("VoteSecure AI - Election Results Declared", recipients=[email])
                    msg.body = body
                    conn.send(msg)
                except Exception as e:
                    print(f"Failed to send result email to {email}: {str(e)}")

def check_and_send_result_emails(election):
    log = SecurityLog.query.filter_by(action='Results Emailed', details=f"Election ID: {election.id}").first()
    if log:
        return
        
    admin_user = User.query.filter_by(is_admin=True).first()
    admin_id = admin_user.id if admin_user else None
    
    log_sync = SecurityLog(user_id=admin_id, action='Results Emailed', details=f"Election ID: {election.id}", ip_address="System")
    db.session.add(log_sync)
    db.session.commit()
    
    candidates = Candidate.query.filter_by(election_id=election.id).all()
    results = [{'candidate': c, 'votes': len(c.votes)} for c in candidates]
    results.sort(key=lambda x: x['votes'], reverse=True)
    
    winner_name = "N/A"
    winner_party = "N/A"
    is_tie = False
    
    if len(results) > 0 and results[0]['votes'] > 0:
        highest_votes = results[0]['votes']
        winners = [r for r in results if r['votes'] == highest_votes]
        if len(winners) > 1:
            is_tie = True
        else:
            winner_name = winners[0]['candidate'].name
            winner_party = winners[0]['candidate'].party
            
    users = User.query.filter_by(is_verified=True, is_admin=False).all()
    user_details = [(u.email, u.full_name) for u in users]
    
    thread = threading.Thread(
        target=send_result_emails_in_background, 
        args=(app._get_current_object(), user_details, election.title, is_tie, winner_name, winner_party)
    )
    thread.start()

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        aadhaar = request.form.get('aadhaar')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        city = request.form.get('city')
        password = request.form.get('password')

        # Validation
        if len(aadhaar) != 12 or not aadhaar.isdigit():
            flash('Invalid Aadhaar number', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(aadhaar=aadhaar).first() or \
           User.query.filter_by(email=email).first() or \
           User.query.filter_by(phone=phone).first():
            flash('Aadhaar, Email or Phone already registered.', 'danger')
            return redirect(url_for('register'))

        otp = str(random.randint(100000, 999999))
        session['reg_data'] = {
            'full_name': full_name, 'aadhaar': aadhaar, 'email': email,
            'phone': phone, 'address': address, 'city': city,
            'password_hash': generate_password_hash(password)
        }
        session['otp'] = otp
        
        print(f"\n{'='*40}\nOTP FOR TESTING: {otp}\n{'='*40}\n")
        
        email_user = app.config.get('MAIL_USERNAME')
        email_pass = app.config.get('MAIL_PASSWORD')
        if not email_user or not email_pass or email_user == 'your-email@gmail.com':
            print("ERROR: Email credentials missing in .env file. Please configure EMAIL_ADDRESS and EMAIL_APP_PASSWORD.")
            flash('Warning: Email sending is not configured. Proceeding in testing mode.', 'warning')

        try:
            msg = Message("LY Voting System - Verification OTP", recipients=[email])
            msg.body = f"Your OTP for registration is {otp}. Do not share this with anyone."
            mail.send(msg)
            flash('OTP sent to your email.', 'info')
        except Exception as e:
            print(f"\nSMTP ERROR: Failed to send OTP email to {email}")
            print(f"Details: {str(e)}\n")
            flash('Failed to send OTP email. If you are an admin, check terminal for details.', 'danger')
            
        # Continue to verify_otp regardless of email success so testing is possible
        return redirect(url_for('verify_otp'))

    return render_template('auth/register.html')

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if 'reg_data' not in session or 'otp' not in session:
        return redirect(url_for('register'))
        
    if request.method == 'POST':
        user_otp = request.form.get('otp')
        if user_otp == session['otp']:
            session['otp_verified'] = True
            flash('OTP Verified! Please complete Face Registration.', 'success')
            return redirect(url_for('register_face'))
        else:
            flash('Invalid OTP', 'danger')
    return render_template('auth/verify_otp.html')

@app.route('/resend_otp')
def resend_otp():
    if 'reg_data' not in session or 'otp' not in session:
        return redirect(url_for('register'))
        
    otp = str(random.randint(100000, 999999))
    session['otp'] = otp
    email = session['reg_data']['email']
    print(f"\n{'='*40}\nRESENT OTP FOR TESTING: {otp}\n{'='*40}\n")
    
    email_user = app.config.get('MAIL_USERNAME')
    email_pass = app.config.get('MAIL_PASSWORD')
    if not email_user or not email_pass or email_user == 'your-email@gmail.com':
        print("ERROR: Email credentials missing in .env file. Please configure EMAIL_ADDRESS and EMAIL_APP_PASSWORD.")
        flash('Warning: Email sending is not configured. Proceeding in testing mode.', 'warning')
        
    try:
        msg = Message("LY Voting System - Verification OTP", recipients=[email])
        msg.body = f"Your new OTP for registration is {otp}. Do not share this with anyone."
        mail.send(msg)
        flash('A new OTP has been sent to your email.', 'info')
    except Exception as e:
        print(f"\nSMTP ERROR: Failed to resend OTP email to {email}")
        print(f"Details: {str(e)}\n")
        flash('Failed to resend OTP email. Check terminal for details.', 'danger')
        
    return redirect(url_for('verify_otp'))

@app.route('/register_face', methods=['GET', 'POST'])
def register_face():
    if not session.get('otp_verified') or 'reg_data' not in session:
        return redirect(url_for('register'))

    if request.method == 'POST':
        face_data = request.form.get('face_data')
        if not face_data:
            flash('Face data is required.', 'danger')
            return redirect(url_for('register_face'))

        try:
            print("\n--- DEBUG: Image received from frontend ---")
            header, encoded = face_data.split(",", 1)
            image_data = base64.b64decode(encoded)
            
            filename = f"{uuid.uuid4().hex}.jpg"
            filepath = os.path.join(basedir, 'face_data', filename)
            
            with open(filepath, 'wb') as f:
                f.write(image_data)
                
            print("--- DEBUG: Image saved ---")
            print(f"--- DEBUG: File path: {filepath} ---")
            
            data = session['reg_data']
            user = User(**data)
            user.is_verified = True
            user.face_encoding = filename
            
            db.session.add(user)
            db.session.commit()
            print("--- DEBUG: Database updated successfully ---\n")
            log_security(user.id, 'User Registered with Face')
            
            session.pop('reg_data', None)
            session.pop('otp', None)
            session.pop('otp_verified', None)
            
            flash('Face Registration complete! You can now log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Failed to process face data: {str(e)}', 'danger')
            
    return render_template('auth/face_register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        elif 'current_election_id' in session:
            return redirect(url_for('dashboard'))
        else:
            logout_user() # Force re-login if no election in session
            
    if request.method == 'POST':
        aadhaar = request.form.get('aadhaar')
        password = request.form.get('password')
        election_code = request.form.get('election_code')
        
        user = User.query.filter_by(aadhaar=aadhaar).first()
        if user and check_password_hash(user.password_hash, password):
            if user.is_admin:
                login_user(user)
                log_security(user.id, 'Admin Login')
                return redirect(url_for('admin_dashboard'))
                
            if not election_code:
                flash('Election Code is mandatory for voters.', 'danger')
                return redirect(url_for('login'))
                
            election = Election.query.filter_by(code=election_code).first()
            if not election:
                flash('Invalid Election Code.', 'danger')
                return redirect(url_for('login'))
                
            login_user(user)
            session['current_election_id'] = election.id
            log_security(user.id, f'User Login to Election {election.code}')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid Aadhaar number or password.', 'danger')
            
    return render_template('auth/login.html')

@app.route('/logout')
@login_required
def logout():
    log_security(current_user.id, 'User Logout')
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
        
    election_id = session.get('current_election_id')
    if not election_id:
        logout_user()
        flash('Session expired or invalid election context.', 'danger')
        return redirect(url_for('login'))
        
    election = Election.query.get(election_id)
    if not election:
        logout_user()
        flash('Election not found.', 'danger')
        return redirect(url_for('login'))
        
    now = datetime.now()
    if now < election.start_time:
        election.status = 'Upcoming'
    elif now > election.end_time:
        election.status = 'Closed'
        check_and_send_result_emails(election)
    else:
        election.status = 'Live'
    db.session.commit()
        
    has_voted = Vote.query.filter_by(user_id=current_user.id, election_id=election_id).first() is not None
    
    results = []
    winner = None
    tie = False
    tie_candidates = []
    total_valid_votes = 0
    
    if election.status == 'Closed':
        total_valid_votes = Vote.query.filter_by(election_id=election.id).count()
        candidates = Candidate.query.filter_by(election_id=election.id).all()
        for c in candidates:
            cvotes = len(c.votes)
            perc = (cvotes / total_valid_votes * 100) if total_valid_votes > 0 else 0
            results.append({'candidate': c, 'votes': cvotes, 'percent': round(perc, 1)})
            
        results.sort(key=lambda x: x['votes'], reverse=True)
        if len(results) > 0:
            highest_votes = results[0]['votes']
            if highest_votes > 0:
                winners = [r for r in results if r['votes'] == highest_votes]
                if len(winners) > 1:
                    tie = True
                    tie_candidates = winners
                else:
                    winner = winners[0]

    return render_template('user/dashboard.html', election=election, has_voted=has_voted, results=results, winner=winner, tie=tie, tie_candidates=tie_candidates, total_valid_votes=total_valid_votes)

@app.route('/vote/<int:election_id>', methods=['GET', 'POST'])
@login_required
def vote(election_id):
    if current_user.is_admin:
        flash('Admins cannot vote.', 'warning')
        return redirect(url_for('admin_dashboard'))
        
    if session.get('current_election_id') != election_id:
        flash('You are not logged into this election context.', 'danger')
        return redirect(url_for('dashboard'))
        
    election = Election.query.get_or_404(election_id)
    
    now = datetime.now()
    if now < election.start_time:
        election.status = 'Upcoming'
    elif now > election.end_time:
        election.status = 'Closed'
        check_and_send_result_emails(election)
    else:
        election.status = 'Live'
    db.session.commit()
    
    if election.status != 'Live':
        if election.status == 'Upcoming':
            flash('This election has not started yet.', 'warning')
        else:
            flash('This election has ended.', 'danger')
        return redirect(url_for('dashboard'))
        
    if Vote.query.filter_by(user_id=current_user.id, election_id=election_id).first():
        flash('You have already voted in this election.', 'warning')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        candidate_id = request.form.get('candidate_id')
        face_data = request.form.get('face_data')
        
        if not candidate_id:
            flash('Please select a candidate.', 'danger')
            return redirect(url_for('vote', election_id=election_id))
            
        if not face_data:
            flash('Face data is required for verification.', 'danger')
            return redirect(url_for('vote', election_id=election_id))

        # Save temporary image for verification
        try:
            header, encoded = face_data.split(",", 1)
            image_data = base64.b64decode(encoded)
            temp_path = os.path.join(basedir, 'face_data', f"temp_verify_{current_user.id}.jpg")
            with open(temp_path, 'wb') as f:
                f.write(image_data)
        except Exception as e:
            flash('Error processing webcam image.', 'danger')
            return redirect(url_for('vote', election_id=election_id))

        # Verify Face
        is_verified = verify_face(current_user.id, temp_path)
        
        # Cleanup temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)

        if not is_verified:
            log_security(current_user.id, 'Failed Face Auth during voting')
            flash('Face verification failed. Please try again or contact admin.', 'danger')
            return redirect(url_for('vote', election_id=election_id))
            
        fraud_check = analyze_voting_pattern(current_user.id, election_id, request.remote_addr)
        if fraud_check.get('is_fraudulent'):
            log_security(current_user.id, 'Fraud detected', f"Risk score: {fraud_check.get('risk_score')}")
            flash('Security block: Anomalous voting pattern detected.', 'danger')
            return redirect(url_for('dashboard'))

        new_vote = Vote(user_id=current_user.id, election_id=election_id, candidate_id=candidate_id)
        db.session.add(new_vote)
        db.session.commit()
        log_security(current_user.id, f'Voted securely in election {election_id}')
        
        flash('Your vote has been cast successfully!', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('user/vote.html', election=election)

# --- Admin Routes ---

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
        
    now = datetime.now()
    elections = Election.query.all()
    for el in elections:
        if now < el.start_time:
            el.status = 'Upcoming'
        elif now > el.end_time:
            el.status = 'Closed'
            check_and_send_result_emails(el)
        else:
            el.status = 'Live'
    db.session.commit()
    
    total_users = User.query.filter_by(is_admin=False).count()
    total_elections = len(elections)
    total_votes = Vote.query.count()
    active_elections = Election.query.filter_by(status='Live').count()
    closed_elections = Election.query.filter_by(status='Closed').count()
    
    turnout = 0
    if total_users > 0 and total_elections > 0:
        turnout = round((total_votes / (total_users * total_elections)) * 100, 1)

    return render_template('admin/dashboard.html', total_users=total_users, 
                           total_elections=total_elections, total_votes=total_votes,
                           active_elections=active_elections, closed_elections=closed_elections, turnout=turnout)

@app.route('/admin/elections', methods=['GET', 'POST'])
@login_required
def manage_elections():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title = request.form.get('title')
        code = request.form.get('code')
        desc = request.form.get('description')
        s_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M')
        e_time = datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M')
        
        if Election.query.filter_by(code=code).first():
            flash('Election Code must be unique.', 'danger')
            return redirect(url_for('manage_elections'))
            
        el = Election(title=title, code=code, description=desc, start_time=s_time, end_time=e_time, status='Upcoming')
        db.session.add(el)
        db.session.commit()
        log_security(current_user.id, f'Created election {el.code}')
        flash(f'Election created successfully! The Election Code is: {el.code} (Share this with voters)', 'success')
        return redirect(url_for('manage_elections'))
        
    elections = Election.query.all()
    return render_template('admin/elections.html', elections=elections)

@app.route('/admin/election/edit/<int:election_id>', methods=['GET', 'POST'])
@login_required
def edit_election(election_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    election = Election.query.get_or_404(election_id)
    if request.method == 'POST':
        election.title = request.form.get('title')
        new_code = request.form.get('code')
        if new_code != election.code and Election.query.filter_by(code=new_code).first():
            flash('Election Code must be unique.', 'danger')
            return redirect(url_for('edit_election', election_id=election.id))
        election.code = new_code
        election.description = request.form.get('description')
        election.start_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M')
        election.end_time = datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M')
        
        now = datetime.now()
        if now < election.start_time:
            election.status = 'Upcoming'
        elif now > election.end_time:
            election.status = 'Closed'
            check_and_send_result_emails(election)
        else:
            election.status = 'Live'
            
        db.session.commit()
        flash('Election updated successfully.', 'success')
        return redirect(url_for('manage_elections'))
        
    return render_template('admin/edit_election.html', election=election)

@app.route('/admin/election/<action>/<int:election_id>')
@login_required
def admin_election_action(action, election_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    election = Election.query.get_or_404(election_id)
    if action == 'activate':
        election.status = 'Live'
        election.start_time = datetime.now()
        if election.end_time <= datetime.now():
            from datetime import timedelta
            election.end_time = datetime.now() + timedelta(days=1)
        flash(f'Election {election.code} is now Live.', 'success')
    elif action == 'close':
        election.status = 'Closed'
        election.end_time = datetime.now()
        check_and_send_result_emails(election)
        flash(f'Election {election.code} is now Closed.', 'success')
    elif action == 'delete':
        db.session.delete(election)
        flash('Election deleted.', 'success')
    db.session.commit()
    return redirect(url_for('manage_elections'))

@app.route('/admin/candidates/<int:election_id>', methods=['GET', 'POST'])
@login_required
def manage_candidates(election_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    election = Election.query.get_or_404(election_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        party = request.form.get('party')
        manifesto = request.form.get('manifesto')
        
        photo_filename = None
        symbol_filename = None
        
        photo = request.files.get('photo')
        if photo and photo.filename != '':
            photo_filename = secure_filename(f"{uuid.uuid4().hex}_{photo.filename}")
            photo.save(os.path.join(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), photo_filename))
            
        symbol = request.files.get('symbol')
        if symbol and symbol.filename != '':
            symbol_filename = secure_filename(f"{uuid.uuid4().hex}_{symbol.filename}")
            symbol.save(os.path.join(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), symbol_filename))
            
        c = Candidate(election_id=election_id, name=name, party=party, manifesto=manifesto, 
                      photo_filename=photo_filename, symbol_filename=symbol_filename)
        db.session.add(c)
        db.session.commit()
        flash('Candidate added successfully.', 'success')
        return redirect(url_for('manage_candidates', election_id=election_id))
        
    candidates = Candidate.query.filter_by(election_id=election_id).all()
    total_votes = Vote.query.filter_by(election_id=election_id).count()
    results = []
    for c in candidates:
        cvotes = len(c.votes)
        perc = (cvotes/total_votes*100) if total_votes > 0 else 0
        results.append({'candidate': c, 'votes': cvotes, 'percent': round(perc, 1)})
        
    return render_template('admin/candidates.html', election=election, results=results)

@app.route('/admin/candidate/<action>/<int:candidate_id>')
@login_required
def admin_candidate_action(action, candidate_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    candidate = Candidate.query.get_or_404(candidate_id)
    election_id = candidate.election_id
    if action == 'delete':
        db.session.delete(candidate)
        db.session.commit()
        flash('Candidate deleted successfully.', 'success')
    return redirect(url_for('manage_candidates', election_id=election_id))

@app.route('/admin/users')
@login_required
def manage_users():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    users = User.query.filter_by(is_admin=False).all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/logs')
@login_required
def security_logs():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    logs = SecurityLog.query.order_by(SecurityLog.timestamp.desc()).limit(100).all()
    return render_template('admin/logs.html', logs=logs)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

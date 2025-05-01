# app.py

from flask import Flask, render_template, url_for, flash, redirect, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy.sql import func
import os
import numpy as np
from joblib import load
from flask import send_file
from datetime import datetime
from flask import send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from io import BytesIO
from reportlab.pdfgen import canvas


# ========== Initialize Flask App ==========
app = Flask(__name__)
app.config['SECRET_KEY'] = '5791628bb0b13ce0c676dfde280ba245'

# ========== Database Setup ==========
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ========== Load ML Model ==========
try:
    model = load(r'Stressometer-master/Stressometer-master/models.pkl')
    print("Model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

# ========== Database Models ==========
class Users(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)
    stress_level = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    test_results = db.relationship('TestResult', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'

class TestResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.DateTime(timezone=True), server_default=func.now())
    stress_level = db.Column(db.String(100))
    score = db.Column(db.Integer)
    recommendation = db.Column(db.String(200))

    def __repr__(self):
        return f'<TestResult for user_id={self.user_id}>'
    
class MoodEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mood = db.Column(db.String(100), nullable=False)
    journal = db.Column(db.Text, nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)

# ========== User Loader ==========
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))

# ========== Routes ==========
@app.route('/')
@app.route('/home')
def home():
    return render_template('home.html', title="Home")

stress_level_map = {
    'No Stress': {'score': 0, 'recommendation': 'Keep up the good work! Maintain your healthy lifestyle.'},
    'Acute Stress': {'score': 2, 'recommendation': 'Take short breaks, practice breathing exercises, and monitor your stress.'},
    'Episodic Acute Stress': {'score': 4, 'recommendation': 'Consider stress management strategies like mindfulness and time management.'},
    'Chronic Stress': {'score': 6, 'recommendation': 'Seek professional help and work on long-term lifestyle changes.'}
    }

@app.route('/dashboard')
@login_required
def dashboard():
    results = TestResult.query.filter_by(user_id=current_user.id).all()
    dates = [result.date.strftime('%Y-%m-%d') for result in results]
    scores = [stress_level_map.get(result.stress_level, {'score': 0})['score'] for result in results]
    return render_template('dashboard.html', results=results, dates=dates, scores=scores)


@app.route('/mood_checkin', methods=['POST'])
@login_required
def mood_checkin():
    # Your logic to handle the form data (mood and journal entry)
    mood = request.form['mood']
    journal = request.form['journal']
    
    # Save mood and journal to the database
    new_mood_entry = MoodEntry(user_id=current_user.id, mood=mood, journal=journal)
    db.session.add(new_mood_entry)
    db.session.commit()
    
    flash('Mood and journal entry saved!', 'success')
    return redirect(url_for('dashboard'))  # Redirect to the dashboard after submitting

@app.route('/download_report')
@login_required
def download_report():
    try:
        # Create a file-like buffer to receive PDF data
        buffer = BytesIO()

        # Create a canvas to draw the PDF
        p = canvas.Canvas(buffer)

        # Add content to the PDF
        p.setFont("Helvetica", 12)
        p.drawString(100, 800, f"User Report for {current_user.username}")
        p.drawString(100, 780, f"Email: {current_user.email}")
        p.drawString(100, 760, f"Stress Level: {current_user.stress_level}")
        p.drawString(100, 740, "Thank you for using Stressometer!")

        # Finalize the PDF file
        p.showPage()
        p.save()

        # Rewind the buffer
        buffer.seek(0)

        # Send the buffer as a downloadable PDF file
        return send_file(
            buffer,
            as_attachment=True,
            download_name='stress_report.pdf',
            mimetype='application/pdf'
        )

    except Exception as e:
        flash('Error generating report.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    from forms import RegistrationForm
    form = RegistrationForm()
    if request.method == 'POST' and form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data
        user_type = "student"
        stressLevel = "Not measured"

        existing_user = Users.query.filter((Users.username == username) | (Users.email == email)).first()
        if existing_user:
            flash('Username or Email already exists.', 'danger')
        else:
            user = Users(username=username, email=email, password=password, user_type=user_type, stress_level=stressLevel)
            db.session.add(user)
            db.session.commit()
            flash('Account created successfully!', 'success')
            return redirect(url_for('login'))

    return render_template('register.html', title="Register", form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    from forms import LoginForm
    form = LoginForm()
    if request.method == 'POST' and form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        session['email'] = email
        session['password'] = password

        user = Users.query.filter_by(email=email).first()
        if user and user.password == password:
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Login failed. Check email and password.', 'danger')
    return render_template('login.html', title="Login", form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))

@app.route('/form')
@login_required
def form():
    return render_template('form.html')

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    if model:
        try:
            # Extract form inputs
            m_f = int(request.form.get("gender"))
            financial_issues = sum(1 for i in range(4) if request.form.get(f"financial_issues{i}"))
            family_issues = sum(1 for i in range(4) if request.form.get(f"family_issues{i}"))
            s_h = int(request.form.get("study_hours"))
            health_issues = sum(1 for i in range(10) if request.form.get(f"health_issues{i}"))
            friends_issues = sum(1 for i in range(6) if request.form.get(f"friends_issues{i}"))
            t_f = int(request.form.get("time_with_friends"))
            overload = int(request.form.get("overload"))
            unpleasant = int(request.form.get("unpleasant"))
            academic = int(request.form.get("academic"))
            career = int(request.form.get("career"))
            criticism = int(request.form.get("criticism"))
            Conflicts = int(request.form.get("Conflicts"))

            features = np.array([[m_f, financial_issues, family_issues, s_h, health_issues, friends_issues,
                                  t_f, overload, unpleasant, academic, career, criticism, Conflicts]])

            # Predict using model
            prediction = model.predict(features)[0]

            if prediction == 0:
                pred_label = "Acute Stress"
            elif prediction == 1:
                pred_label = "Episodic Acute Stress"
            elif prediction == 2:
                pred_label = "Chronic Stress"
            else:
                pred_label = "No Stress"
            
            stress_info = stress_level_map[pred_label]
            score = stress_info['score']
            recommendation = stress_info['recommendation']

            # Save prediction result in the database
            if current_user.is_authenticated:
                new_result = TestResult(
                user_id=current_user.id,
                stress_level=pred_label,
                score=score,
                recommendation=recommendation
                )
                db.session.add(new_result)
                db.session.commit()  # <== this line is essential
                

            return render_template('result.html', prediction_text=pred_label)


        except Exception as e:
            flash(f"Prediction error: {e}", 'danger')
            return redirect(url_for('form'))
    else:
        flash('Model is not available.', 'danger')
        return redirect(url_for('form'))

@app.route('/result')
@login_required
def result():
    return render_template('result.html')

# ========== Run App ==========
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # 🔥 Very important: create tables if they don't exist
    app.run(debug=True)

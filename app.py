import os
import re
import secrets
from datetime import datetime
from functools import wraps
from io import BytesIO

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from fpdf import FPDF
from PIL import Image

app = Flask(__name__, instance_path='/tmp/instance')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:////tmp/instance/app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Auto-create uploads directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('/tmp/instance', exist_ok=True)

ALLOWED_EXTENSIONS = {'ppt', 'pptx', 'pdf'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

# ==================== MODELS ====================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    roll_no = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    batch = db.Column(db.String(50), nullable=False)
    semester = db.Column(db.String(50), nullable=False)
    profile_picture = db.Column(db.String(200), default='')
    role = db.Column(db.String(20), default='student')  # student, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    presentations = db.relationship('Presentation', backref='student', lazy=True, cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy=True, cascade='all, delete-orphan')
    assigned_topics = db.relationship('Topic', backref='student', lazy=True, cascade='all, delete-orphan')

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Semester(db.Model):
    __tablename__ = 'semesters'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Presentation(db.Model):
    __tablename__ = 'presentations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    topic = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    semester = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, approved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    evaluation = db.relationship('Evaluation', backref='presentation', uselist=False, cascade='all, delete-orphan')

class Evaluation(db.Model):
    __tablename__ = 'evaluations'
    id = db.Column(db.Integer, primary_key=True)
    presentation_id = db.Column(db.Integer, db.ForeignKey('presentations.id'), nullable=False)
    content_quality = db.Column(db.Float, default=0)
    technical_knowledge = db.Column(db.Float, default=0)
    presentation_skills = db.Column(db.Float, default=0)
    communication = db.Column(db.Float, default=0)
    total_marks = db.Column(db.Float, default=0)
    max_marks = db.Column(db.Float, default=20)
    comments = db.Column(db.Text, default='')
    evaluated_by = db.Column(db.String(100), default='Admin')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Topic(db.Model):
    __tablename__ = 'topics'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    semester = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='assigned')  # assigned, submitted

class Setting(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    max_marks = db.Column(db.Float, default=20)
    criteria = db.Column(db.Text, default='Content Quality,Technical Knowledge,Presentation Skills,Communication')

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== DEPARTMENT CODES ====================

DEPT_CODES = {
    'Cyber Security': 'CYS',
    'Computer Science': 'CS',
    'Software Engineering': 'SE',
    'Information Technology': 'IT',
    'Artificial Intelligence': 'AI',
    'Electrical Engineering': 'EE',
    'Computer Engineering': 'CE',
    'Data Science': 'DS',
    'Business Administration': 'BA'
}

def generate_roll_number(department, batch):
    """Generate roll number: YY + DEPT_CODE + NN"""
    dept_code = DEPT_CODES.get(department, 'XX')
    try:
        year = batch.split('-')[0][-2:]
    except:
        year = '24'
    prefix = f"{year}{dept_code}"
    existing = User.query.filter(User.roll_no.like(f"{prefix}%")).order_by(User.roll_no.desc()).first()
    if existing:
        try:
            last_num = int(existing.roll_no[len(prefix):])
            next_num = last_num + 1
        except:
            next_num = 1
    else:
        next_num = 1
    return f"{prefix}{next_num:02d}"

def validate_roll_number(roll_no, department):
    """Strict validation: YY + DEPT_CODE + NN"""
    dept_code = DEPT_CODES.get(department, '')
    if not dept_code:
        return False, f"Unknown department: {department}"
    pattern = r'^\d{2}' + re.escape(dept_code) + r'\d{2}$'
    if not re.match(pattern, roll_no.upper()):
        expected = f"YY{dept_code}NN (e.g., 24{dept_code}01)"
        return False, f"Invalid roll number format. Expected: {expected}"
    return True, ""

# ==================== IMAGE PROCESSING ====================

def process_profile_picture(file_storage, filename):
    """Center-crop to square, resize to 400x400, save."""
    img = Image.open(file_storage.stream)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    width, height = img.size
    min_dim = min(width, height)
    left = (width - min_dim) // 2
    top = (height - min_dim) // 2
    right = left + min_dim
    bottom = top + min_dim
    img = img.crop((left, top, right, bottom))
    img = img.resize((400, 400), Image.LANCZOS)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    img.save(filepath, 'JPEG', quality=90)
    return filename

# ==================== HELPERS ====================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def get_student_stats(user_id):
    total = Presentation.query.filter_by(user_id=user_id).count()
    submitted = Presentation.query.filter_by(user_id=user_id).filter(Presentation.status.in_(['reviewed', 'approved'])).count()
    evals = db.session.query(Evaluation).join(Presentation).filter(Presentation.user_id == user_id).all()
    avg = sum(e.total_marks for e in evals) / len(evals) if evals else 0
    latest_feedback = Evaluation.query.join(Presentation).filter(Presentation.user_id == user_id).order_by(Evaluation.created_at.desc()).first()
    return {
        'total': total,
        'submitted': submitted,
        'average': round(avg, 1),
        'latest_feedback': latest_feedback.comments if latest_feedback else 'No feedback yet',
        'latest_feedback_date': latest_feedback.created_at.strftime("%b %d, %Y") if latest_feedback else ''
    }

def get_admin_stats():
    total_users = User.query.filter_by(role='student').count()
    total_presentations = Presentation.query.count()
    pending_reviews = Presentation.query.filter_by(status='pending').count()
    evals = Evaluation.query.all()
    avg = sum(e.total_marks for e in evals) / len(evals) if evals else 0
    return {
        'total_users': total_users,
        'total_presentations': total_presentations,
        'pending_reviews': pending_reviews,
        'average_marks': round(avg, 1)
    }

# ==================== CONTEXT PROCESSOR ====================

@app.context_processor
def inject_globals():
    departments = Department.query.all()
    semesters = Semester.query.all()
    settings = Setting.query.first()
    if not settings:
        settings = Setting(max_marks=20)
        db.session.add(settings)
        db.session.commit()
    return dict(departments=departments, semesters=semesters, global_settings=settings)

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        roll_no = request.form.get('roll_no', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        user = User.query.filter_by(roll_no=roll_no).first()
        if user and check_password_hash(user.password_hash, password):
            if user.role == 'admin':
                flash('Please use the admin portal to log in as administrator.', 'warning')
                return redirect(url_for('login'))
            login_user(user, remember=remember)
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid roll number or password.', 'error')
    return render_template('auth.html', mode='login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        department = request.form.get('department', '')
        batch = request.form.get('batch', '')
        semester = request.form.get('semester', '')
        roll_no = request.form.get('roll_no', '').strip().upper()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not all([name, email, department, batch, semester, password]):
            flash('All fields are required.', 'error')
            return redirect(url_for('register'))
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))

        if not roll_no:
            roll_no = generate_roll_number(department, batch)
        else:
            valid, msg = validate_roll_number(roll_no, department)
            if not valid:
                flash(msg, 'error')
                return redirect(url_for('register'))

        if User.query.filter_by(roll_no=roll_no).first():
            flash('Roll number already registered.', 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))

        profile_pic = ''
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename and allowed_image_file(file.filename):
                ext = 'jpg'
                filename = secure_filename(f"{roll_no}_{secrets.token_hex(4)}.{ext}")
                process_profile_picture(file, filename)
                profile_pic = filename

        user = User(
            name=name,
            email=email,
            roll_no=roll_no,
            password_hash=generate_password_hash(password),
            department=department,
            batch=batch,
            semester=semester,
            profile_picture=profile_pic,
            role='student'
        )
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('auth.html', mode='register')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# ==================== STUDENT ROUTES ====================

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    stats = get_student_stats(current_user.id)
    presentations = Presentation.query.filter_by(user_id=current_user.id).order_by(Presentation.created_at.desc()).limit(5).all()
    topics = Topic.query.filter_by(user_id=current_user.id, status='assigned').order_by(Topic.assigned_at.desc()).all()
    return render_template('student.html', section='dashboard', stats=stats, presentations=presentations, assigned_topics=topics)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        current_user.name = request.form.get('name', current_user.name)
        current_user.email = request.form.get('email', current_user.email)
        current_user.department = request.form.get('department', current_user.department)
        current_user.batch = request.form.get('batch', current_user.batch)
        current_user.semester = request.form.get('semester', current_user.semester)

        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename and allowed_image_file(file.filename):
                ext = 'jpg'
                filename = secure_filename(f"{current_user.roll_no}_{secrets.token_hex(4)}.{ext}")
                if current_user.profile_picture:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], current_user.profile_picture))
                    except:
                        pass
                process_profile_picture(file, filename)
                current_user.profile_picture = filename

        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('profile'))
    return render_template('student.html', section='profile')

@app.route('/presentations', methods=['GET', 'POST'])
@login_required
def presentations():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        topic = request.form.get('topic', '').strip()
        description = request.form.get('description', '').strip()
        semester = request.form.get('semester', '')

        if 'file' not in request.files:
            flash('No file selected.', 'error')
            return redirect(url_for('presentations'))
        file = request.files['file']
        if not file or file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('presentations'))
        if not allowed_file(file.filename):
            flash('Invalid file type. Only PPT, PPTX, and PDF allowed.', 'error')
            return redirect(url_for('presentations'))

        filename = secure_filename(f"{current_user.roll_no}_{secrets.token_hex(4)}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        pres = Presentation(
            user_id=current_user.id,
            title=title,
            topic=topic,
            description=description,
            filename=file.filename,
            file_path=filename,
            semester=semester,
            department=current_user.department,
            status='pending'
        )
        db.session.add(pres)
        db.session.commit()

        assigned = Topic.query.filter_by(user_id=current_user.id, title=title, status='assigned').first()
        if assigned:
            assigned.status = 'submitted'
            db.session.commit()

        notif = Notification(user_id=current_user.id, message=f'Presentation "{title}" uploaded successfully and is pending review.')
        db.session.add(notif)
        db.session.commit()

        flash('Presentation uploaded successfully.', 'success')
        return redirect(url_for('presentations'))

    presentations = Presentation.query.filter_by(user_id=current_user.id).order_by(Presentation.created_at.desc()).all()
    topics = Topic.query.filter_by(user_id=current_user.id).order_by(Topic.assigned_at.desc()).all()
    return render_template('student.html', section='presentations', presentations=presentations, assigned_topics=topics)

@app.route('/download/<int:pres_id>')
@login_required
def download_presentation(pres_id):
    pres = Presentation.query.get_or_404(pres_id)
    if pres.user_id != current_user.id and current_user.role != 'admin':
        abort(403)
    return send_from_directory(app.config['UPLOAD_FOLDER'], pres.file_path, as_attachment=True, download_name=pres.filename)

@app.route('/evaluations')
@login_required
def evaluations():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    presentations = Presentation.query.filter_by(user_id=current_user.id).order_by(Presentation.created_at.desc()).all()
    return render_template('student.html', section='evaluations', presentations=presentations)

@app.route('/feedback')
@login_required
def feedback():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    evals = Evaluation.query.join(Presentation).filter(Presentation.user_id == current_user.id).order_by(Evaluation.created_at.desc()).all()
    return render_template('student.html', section='feedback', evaluations=evals)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if new_password:
            if not check_password_hash(current_user.password_hash, current_password):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('settings'))
            if new_password != confirm_password:
                flash('New passwords do not match.', 'error')
                return redirect(url_for('settings'))
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('Password updated successfully.', 'success')
        return redirect(url_for('settings'))
    return render_template('student.html', section='settings')

@app.route('/about')
@login_required
def about():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    return render_template('student.html', section='about')

# ==================== ADMIN ROUTES ====================

@app.route('/secure-admin-access-portal', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated and current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        roll_no = request.form.get('roll_no', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(roll_no=roll_no, role='admin').first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Welcome to the Admin Portal.', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid admin credentials.', 'error')
    return render_template('auth.html', mode='admin')

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    stats = get_admin_stats()
    recent_presentations = Presentation.query.order_by(Presentation.created_at.desc()).limit(10).all()
    recent_users = User.query.filter_by(role='student').order_by(User.created_at.desc()).limit(8).all()
    return render_template('admin.html', section='dashboard', stats=stats, recent_presentations=recent_presentations, recent_users=recent_users)

@app.route('/admin/profile', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_profile():
    if request.method == 'POST':
        action = request.form.get('action', 'info')
        if action == 'info':
            current_user.name = request.form.get('name', current_user.name)
            current_user.email = request.form.get('email', current_user.email)
            db.session.commit()
            flash('Profile updated successfully.', 'success')
        elif action == 'password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            if not check_password_hash(current_user.password_hash, current_password):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('admin_profile'))
            if new_password != confirm_password:
                flash('New passwords do not match.', 'error')
                return redirect(url_for('admin_profile'))
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('Password updated successfully.', 'success')
        elif action == 'picture':
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename and allowed_image_file(file.filename):
                    ext = 'jpg'
                    filename = secure_filename(f"ADMIN_{current_user.roll_no}_{secrets.token_hex(4)}.{ext}")
                    if current_user.profile_picture:
                        try:
                            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], current_user.profile_picture))
                        except:
                            pass
                    process_profile_picture(file, filename)
                    current_user.profile_picture = filename
                    db.session.commit()
                    flash('Profile picture updated successfully.', 'success')
        return redirect(url_for('admin_profile'))
    return render_template('admin.html', section='profile')

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.filter_by(role='student').order_by(User.created_at.desc()).all()
    return render_template('admin.html', section='users', users=users)

@app.route('/admin/user/<int:user_id>/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)
    user.name = request.form.get('name', user.name)
    user.email = request.form.get('email', user.email)
    user.department = request.form.get('department', user.department)
    user.batch = request.form.get('batch', user.batch)
    user.semester = request.form.get('semester', user.semester)
    db.session.commit()
    flash('User updated successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.profile_picture:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], user.profile_picture))
        except:
            pass
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def admin_reset_password(user_id):
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password', '')
    if new_password:
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash('Password reset successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/create', methods=['POST'])
@login_required
@admin_required
def admin_create_user():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    department = request.form.get('department', '')
    batch = request.form.get('batch', '')
    semester = request.form.get('semester', '')
    password = request.form.get('password', '')
    roll_no = request.form.get('roll_no', '').strip().upper()

    if not all([name, email, department, batch, semester, password]):
        flash('All fields are required.', 'error')
        return redirect(url_for('admin_users'))

    if not roll_no:
        roll_no = generate_roll_number(department, batch)
    else:
        valid, msg = validate_roll_number(roll_no, department)
        if not valid:
            flash(msg, 'error')
            return redirect(url_for('admin_users'))

    if User.query.filter_by(roll_no=roll_no).first():
        flash('Roll number already exists.', 'error')
        return redirect(url_for('admin_users'))
    if User.query.filter_by(email=email).first():
        flash('Email already registered.', 'error')
        return redirect(url_for('admin_users'))

    user = User(
        name=name,
        email=email,
        roll_no=roll_no,
        password_hash=generate_password_hash(password),
        department=department,
        batch=batch,
        semester=semester,
        role='student'
    )
    db.session.add(user)
    db.session.commit()
    flash(f'User {name} created successfully with Roll No: {roll_no}', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/presentations')
@login_required
@admin_required
def admin_presentations():
    presentations = Presentation.query.order_by(Presentation.created_at.desc()).all()
    return render_template('admin.html', section='presentations', presentations=presentations)

@app.route('/admin/presentation/<int:pres_id>/review', methods=['POST'])
@login_required
@admin_required
def admin_review_presentation(pres_id):
    pres = Presentation.query.get_or_404(pres_id)
    pres.status = request.form.get('status', pres.status)
    db.session.commit()
    flash('Presentation status updated.', 'success')
    return redirect(url_for('admin_presentations'))

@app.route('/admin/presentation/<int:pres_id>/evaluate', methods=['POST'])
@login_required
@admin_required
def admin_evaluate_presentation(pres_id):
    pres = Presentation.query.get_or_404(pres_id)
    settings = Setting.query.first()
    max_marks = settings.max_marks if settings else 20

    content = float(request.form.get('content_quality', 0))
    technical = float(request.form.get('technical_knowledge', 0))
    skills = float(request.form.get('presentation_skills', 0))
    communication = float(request.form.get('communication', 0))
    comments = request.form.get('comments', '')

    total = content + technical + skills + communication

    if pres.evaluation:
        pres.evaluation.content_quality = content
        pres.evaluation.technical_knowledge = technical
        pres.evaluation.presentation_skills = skills
        pres.evaluation.communication = communication
        pres.evaluation.total_marks = total
        pres.evaluation.max_marks = max_marks
        pres.evaluation.comments = comments
        pres.evaluation.evaluated_by = current_user.name
    else:
        eval = Evaluation(
            presentation_id=pres_id,
            content_quality=content,
            technical_knowledge=technical,
            presentation_skills=skills,
            communication=communication,
            total_marks=total,
            max_marks=max_marks,
            comments=comments,
            evaluated_by=current_user.name
        )
        db.session.add(eval)

    pres.status = 'reviewed'
    db.session.commit()

    notif = Notification(user_id=pres.user_id, message=f'Your presentation "{pres.title}" has been evaluated. Total marks: {total}/{max_marks}')
    db.session.add(notif)
    db.session.commit()

    flash('Evaluation submitted successfully.', 'success')
    return redirect(url_for('admin_presentations'))

@app.route('/admin/evaluations')
@login_required
@admin_required
def admin_evaluations():
    evaluations = Evaluation.query.order_by(Evaluation.created_at.desc()).all()
    return render_template('admin.html', section='evaluations', evaluations=evaluations)

@app.route('/admin/marks')
@login_required
@admin_required
def admin_marks():
    evaluations = Evaluation.query.order_by(Evaluation.created_at.desc()).all()
    return render_template('admin.html', section='marks', evaluations=evaluations)

@app.route('/admin/marks/<int:eval_id>/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_marks(eval_id):
    eval = Evaluation.query.get_or_404(eval_id)
    settings = Setting.query.first()
    max_marks = settings.max_marks if settings else 20

    eval.content_quality = float(request.form.get('content_quality', 0))
    eval.technical_knowledge = float(request.form.get('technical_knowledge', 0))
    eval.presentation_skills = float(request.form.get('presentation_skills', 0))
    eval.communication = float(request.form.get('communication', 0))
    eval.total_marks = eval.content_quality + eval.technical_knowledge + eval.presentation_skills + eval.communication
    eval.max_marks = max_marks
    eval.comments = request.form.get('comments', '')
    db.session.commit()

    notif = Notification(user_id=eval.presentation.user_id, message=f'Your marks for "{eval.presentation.title}" have been updated. New total: {eval.total_marks}/{max_marks}')
    db.session.add(notif)
    db.session.commit()

    flash('Marks updated successfully.', 'success')
    return redirect(url_for('admin_marks'))

@app.route('/admin/topics')
@login_required
@admin_required
def admin_topics():
    topics = Topic.query.order_by(Topic.assigned_at.desc()).all()
    students = User.query.filter_by(role='student').all()
    return render_template('admin.html', section='topics', topics=topics, students=students)

@app.route('/admin/topic/create', methods=['POST'])
@login_required
@admin_required
def admin_create_topic():
    user_id = request.form.get('user_id', '')
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    semester = request.form.get('semester', '')
    department = request.form.get('department', '')

    if not all([user_id, title, semester, department]):
        flash('All fields are required.', 'error')
        return redirect(url_for('admin_topics'))

    topic = Topic(
        user_id=int(user_id),
        title=title,
        description=description,
        semester=semester,
        department=department
    )
    db.session.add(topic)
    db.session.commit()

    notif = Notification(user_id=int(user_id), message=f'New presentation topic assigned: "{title}"')
    db.session.add(notif)
    db.session.commit()

    flash('Topic assigned successfully.', 'success')
    return redirect(url_for('admin_topics'))

@app.route('/admin/topic/<int:topic_id>/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    topic.title = request.form.get('title', topic.title)
    topic.description = request.form.get('description', topic.description)
    topic.semester = request.form.get('semester', topic.semester)
    topic.department = request.form.get('department', topic.department)
    db.session.commit()
    flash('Topic updated successfully.', 'success')
    return redirect(url_for('admin_topics'))

@app.route('/admin/topic/<int:topic_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    db.session.delete(topic)
    db.session.commit()
    flash('Topic deleted successfully.', 'success')
    return redirect(url_for('admin_topics'))

@app.route('/admin/notifications', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_notifications():
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        target = request.form.get('target', 'all')
        target_value = request.form.get('target_value', '')

        if not message:
            flash('Message is required.', 'error')
            return redirect(url_for('admin_notifications'))

        if target == 'all':
            users = User.query.filter_by(role='student').all()
        elif target == 'department':
            users = User.query.filter_by(role='student', department=target_value).all()
        elif target == 'semester':
            users = User.query.filter_by(role='student', semester=target_value).all()
        elif target == 'user':
            user = User.query.filter_by(roll_no=target_value, role='student').first()
            users = [user] if user else []
        else:
            users = []

        count = 0
        for user in users:
            if user:
                notif = Notification(user_id=user.id, message=message)
                db.session.add(notif)
                count += 1
        db.session.commit()

        flash(f'Notification sent to {count} student(s).', 'success')
        return redirect(url_for('admin_notifications'))

    notifications = Notification.query.order_by(Notification.created_at.desc()).limit(50).all()
    return render_template('admin.html', section='notifications', notifications=notifications)

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_settings():
    settings = Setting.query.first()
    if request.method == 'POST':
        settings.max_marks = float(request.form.get('max_marks', 20))
        settings.criteria = request.form.get('criteria', settings.criteria)
        db.session.commit()
        flash('Settings updated successfully.', 'success')
        return redirect(url_for('admin_settings'))
    return render_template('admin.html', section='settings', settings=settings)

@app.route('/admin/departments', methods=['POST'])
@login_required
@admin_required
def admin_add_department():
    name = request.form.get('name', '').strip()
    if name and not Department.query.filter_by(name=name).first():
        db.session.add(Department(name=name))
        db.session.commit()
        flash('Department added.', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/departments/<int:dept_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    db.session.delete(dept)
    db.session.commit()
    flash('Department removed.', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/semesters', methods=['POST'])
@login_required
@admin_required
def admin_add_semester():
    name = request.form.get('name', '').strip()
    if name and not Semester.query.filter_by(name=name).first():
        db.session.add(Semester(name=name))
        db.session.commit()
        flash('Semester added.', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/semesters/<int:sem_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_semester(sem_id):
    sem = Semester.query.get_or_404(sem_id)
    db.session.delete(sem)
    db.session.commit()
    flash('Semester removed.', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/pdf_export')
@login_required
@admin_required
def admin_pdf_export():
    return render_template('admin.html', section='pdf_export')

@app.route('/admin/generate_pdf', methods=['POST'])
@login_required
@admin_required
def admin_generate_pdf():
    columns = request.form.getlist('columns')
    department_filter = request.form.get('department_filter', '')
    semester_filter = request.form.get('semester_filter', '')

    query = User.query.filter_by(role='student')
    if department_filter:
        query = query.filter_by(department=department_filter)
    if semester_filter:
        query = query.filter_by(semester=semester_filter)
    users = query.order_by(User.roll_no).all()

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'Student Records Report', 0, 1, 'C')
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f'Generated on {datetime.now().strftime("%B %d, %Y at %H:%M")}', 0, 1, 'C')
    pdf.ln(5)

    pdf.set_fill_color(37, 99, 235)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 10)

    col_widths = {'sno': 15, 'name': 45, 'roll_no': 30, 'department': 40, 'semester': 30, 'topic': 55, 'marks': 25, 'remarks': 40}
    available_width = 277
    total_requested = sum(col_widths.get(c, 30) for c in columns)
    scale = available_width / total_requested if total_requested > 0 else 1

    for col in columns:
        w = col_widths.get(col, 30) * scale
        header_text = {
            'sno': 'S.No.', 'name': 'Student Name', 'roll_no': 'Roll Number',
            'department': 'Department', 'semester': 'Semester', 'topic': 'Presentation Topic',
            'marks': 'Marks', 'remarks': 'Remarks'
        }.get(col, col.title())
        pdf.cell(w, 10, header_text, 1, 0, 'C', True)
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Helvetica', '', 9)

    for idx, user in enumerate(users, 1):
        pres = Presentation.query.filter_by(user_id=user.id).order_by(Presentation.created_at.desc()).first()
        eval = Evaluation.query.join(Presentation).filter(Presentation.user_id == user.id).order_by(Evaluation.created_at.desc()).first()

        topic_text = pres.topic if pres else 'N/A'
        marks_text = f"{eval.total_marks}/{eval.max_marks}" if eval else 'N/A'
        remarks_text = eval.comments[:30] + '...' if eval and eval.comments and len(eval.comments) > 30 else (eval.comments if eval else 'Pending')

        row_data = {
            'sno': str(idx),
            'name': user.name,
            'roll_no': user.roll_no,
            'department': user.department,
            'semester': user.semester,
            'topic': topic_text,
            'marks': marks_text,
            'remarks': remarks_text
        }

        for col in columns:
            w = col_widths.get(col, 30) * scale
            text = row_data.get(col, '')
            pdf.cell(w, 10, text, 1, 0, 'L')
        pdf.ln()

    pdf.set_y(-15)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.cell(0, 10, f'Page {pdf.page_no()}', 0, 0, 'C')

    buffer = BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=f'student_records_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf')

# ==================== API ROUTES ====================

@app.route('/api/stats')
@login_required
def api_stats():
    if current_user.role == 'admin':
        stats = get_admin_stats()
        data = db.session.query(
            db.func.strftime('%Y-%m', Presentation.created_at).label('month'),
            db.func.count(Presentation.id).label('count')
        ).group_by('month').order_by('month').limit(6).all()
        return jsonify({
            'stats': stats,
            'chart_data': {
                'labels': [d[0] for d in data],
                'data': [d[1] for d in data]
            }
        })
    else:
        stats = get_student_stats(current_user.id)
        pres_data = db.session.query(
            Presentation.status,
            db.func.count(Presentation.id)
        ).filter_by(user_id=current_user.id).group_by(Presentation.status).all()
        return jsonify({
            'stats': stats,
            'chart_data': {
                'labels': [d[0].title() for d in pres_data],
                'data': [d[1] for d in pres_data]
            }
        })

@app.route('/api/notifications')
@login_required
def api_notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    return jsonify([{
        'id': n.id,
        'message': n.message,
        'date': n.created_at.strftime('%b %d, %H:%M')
    } for n in notifs])

@app.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def api_read_notification(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != current_user.id:
        abort(403)
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})

# ==================== ERROR HANDLERS ====================

@app.errorhandler(403)
def forbidden(e):
    return render_template('student.html', section='forbidden'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('student.html', section='not_found'), 404

# ==================== INIT ====================

def init_db():
    with app.app_context():
        db.create_all()

        default_depts = ['Cyber Security', 'Computer Science', 'Software Engineering', 'Information Technology',
                        'Artificial Intelligence', 'Electrical Engineering', 'Computer Engineering', 'Data Science', 'Business Administration']
        for dept in default_depts:
            if not Department.query.filter_by(name=dept).first():
                db.session.add(Department(name=dept))

        for i in range(1, 9):
            name = f'Semester {i}'
            if not Semester.query.filter_by(name=name).first():
                db.session.add(Semester(name=name))

        if not Setting.query.first():
            db.session.add(Setting(max_marks=20, criteria='Content Quality,Technical Knowledge,Presentation Skills,Communication'))

        if not User.query.filter_by(roll_no='ADMIN001').first():
            admin = User(
                name='Mr. Amir Rasool',
                email='amir.rasool@university.edu',
                roll_no='ADMIN001',
                password_hash=generate_password_hash('admin123'),
                department='Cyber Security',
                batch='N/A',
                semester='N/A',
                role='admin'
            )
            db.session.add(admin)

        db.session.commit()
        print("Database initialized successfully.")

init_db()

if __name__ == '__main__':
    app.run(debug=True)
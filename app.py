from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from functools import wraps
import os
import random
from werkzeug.utils import secure_filename
import uuid
from utils.auth import register_user, login_user, get_user_by_id
from utils.database import Database
from utils.gemini_api import chat_with_gemini, process_response
from utils.gemini_api import grade_essay_with_ai ############
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
app.config['SESSION_COOKIE_SECURE'] = False  # Đổi thành True nếu dùng HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'


db = Database()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập để tiếp tục', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập', 'warning')
            return redirect(url_for('login'))
        
        user = get_user_by_id(session['user_id'])
        if not user or user['role'] != 'teacher':
            flash('Chỉ giáo viên mới có quyền truy cập trang này', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập', 'warning')
            return redirect(url_for('login'))
        
        user = get_user_by_id(session['user_id'])
        if not user or user['role'] != 'student':
            flash('Chỉ học sinh mới có quyền truy cập trang này', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    
    total_courses = len(db.get_all_courses())
    total_documents = len(db.get_all_documents())
    
    return render_template('index.html', 
                         total_courses=total_courses,
                         total_documents=total_documents)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip()
        
        if not username or not password or not email:
            flash('Vui lòng điền đầy đủ thông tin', 'danger')
            return render_template('register.html')
        
        result = register_user(username, password, email, role='student')
        
        if result['success']:
            flash('Đăng ký thành công! Vui lòng đăng nhập', 'success')
            return redirect(url_for('login'))
        else:
            flash(result['message'], 'danger')
            return render_template('register.html')
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Vui lòng nhập tên đăng nhập và mật khẩu', 'danger')
            return render_template('login.html')
        
        result = login_user(username, password)
        
        if result['success']:
            session['user_id'] = result['user_id']
            session['username'] = result['username']
            session['role'] = result['role']
            
            flash(f'Chào mừng {result["username"]}!', 'success')
            
            if result['role'] == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash(result['message'], 'danger')
            return render_template('login.html')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    username = session.get('username', 'Người dùng')
    session.clear()
    flash(f'Tạm biệt {username}!', 'info')
    return redirect(url_for('index'))


@app.route('/student/dashboard')
@login_required
@student_required
def student_dashboard():
    courses = db.get_all_courses()
    my_progress = db.get_student_progress(session['user_id'])
    
    enrolled_courses = []
    for progress in my_progress:
        course = db.get_course_by_id(progress['course_id'])
        if course:
            total_lessons = len(course.get('lessons', []))
            completed_lessons = len(progress.get('completed_lessons', []))
            percentage = (completed_lessons / total_lessons * 100) if total_lessons > 0 else 0
            
            enrolled_courses.append({
                'course': course,
                'progress': progress,
                'percentage': round(percentage, 1)
            })
    
    return render_template('student_dashboard.html', 
                         courses=courses,
                         enrolled_courses=enrolled_courses,
                         username=session.get('username'))


@app.route('/teacher/dashboard')
@login_required
@teacher_required
def teacher_dashboard():
    my_courses = db.get_courses_by_teacher(session['user_id'])
    
    course_stats = []
    for course in my_courses:
        all_progress = db._load_json(db.progress_file)
        students_enrolled = len([p for p in all_progress if p['course_id'] == course['id']])
        
        course_stats.append({
            'course': course,
            'students_enrolled': students_enrolled,
            'total_lessons': len(course.get('lessons', []))
        })
    
    return render_template('teacher_dashboard.html',
                         courses=course_stats,
                         username=session.get('username'))


@app.route('/courses')
@login_required
def courses():
    all_courses = db.get_all_courses()
    
    courses_with_teacher = []
    for course in all_courses:
        teacher = get_user_by_id(course['teacher_id'])
        course['teacher_name'] = teacher['username'] if teacher else 'Unknown'
        courses_with_teacher.append(course)
    
    return render_template('courses.html', courses=courses_with_teacher)


@app.route('/course/<course_id>')
@login_required
def course_detail(course_id):
    course = db.get_course_by_id(course_id)
    
    if not course:
        flash('Khóa học không tồn tại', 'danger')
        return redirect(url_for('courses'))
    
    teacher = get_user_by_id(course['teacher_id'])
    course['teacher_name'] = teacher['username'] if teacher else 'Unknown'
    
    progress = db.get_course_progress(session['user_id'], course_id)
    completed_lessons = progress['completed_lessons'] if progress else []
    
    is_teacher = session.get('role') == 'teacher' and course['teacher_id'] == session['user_id']
    
    return render_template('course_detail.html', 
                         course=course,
                         completed_lessons=completed_lessons,
                         is_teacher=is_teacher)


@app.route('/teacher/create_course', methods=['GET', 'POST'])
@teacher_required
def create_course():
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            if not data.get('title'):
                return jsonify({'success': False, 'message': 'Vui lòng nhập tên khóa học'})
            
            all_courses = db.get_all_courses()
            if any(c['title'].lower() == data['title'].lower() and c['teacher_id'] == session['user_id'] for c in all_courses):
                return jsonify({'success': False, 'message': 'Bạn đã có khóa học trùng tên này'})
            
            course_id = db.create_course(data, session['user_id'])
            
            return jsonify({'success': True, 'course_id': course_id, 'message': 'Tạo khóa học thành công'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
    
    return render_template('create_course.html')


@app.route('/teacher/edit_course/<course_id>', methods=['GET', 'POST'])
@teacher_required
def edit_course(course_id):
    course = db.get_course_by_id(course_id)
    
    if not course:
        flash('Khóa học không tồn tại', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    if course['teacher_id'] != session['user_id']:
        flash('Bạn không có quyền chỉnh sửa khóa học này', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            success = db.update_course(course_id, data)
            
            if success:
                return jsonify({'success': True, 'message': 'Cập nhật khóa học thành công'})
            else:
                return jsonify({'success': False, 'message': 'Cập nhật thất bại'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
    
    return render_template('create_course.html', course=course, edit_mode=True)


@app.route('/teacher/delete_course/<course_id>', methods=['POST'])
@teacher_required
def delete_course(course_id):
    course = db.get_course_by_id(course_id)
    
    if not course:
        return jsonify({'success': False, 'message': 'Khóa học không tồn tại'})
    
    if course['teacher_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Bạn không có quyền xóa khóa học này'})
    
    courses = db.get_all_courses()
    courses = [c for c in courses if c['id'] != course_id]
    db._save_json(db.courses_file, courses)
    
    return jsonify({'success': True, 'message': 'Xóa khóa học thành công'})


@app.route('/exercises')
@login_required
def exercises():
    all_courses = db.get_all_courses()
    
    exercises_list = []
    for course in all_courses:
        for lesson in course.get('lessons', []):
            questions = lesson.get('questions', [])
            if questions:
                exercises_list.append({
                    'course_id': course['id'],
                    'course_title': course['title'],
                    'lesson_id': lesson['id'],
                    'lesson_title': lesson['title'],
                    'questions': questions
                })
    
    try:
        all_submissions = db._load_json(db.submissions_file) if hasattr(db, 'submissions_file') else []
    except:
        all_submissions = []
    
    my_submissions = [s for s in all_submissions if s.get('user_id') == session['user_id']]
    
    return render_template('exercises.html', 
                         exercises=exercises_list,
                         submissions=my_submissions)


@app.route('/submit_exercise', methods=['POST'])
@login_required
def submit_exercise():
    try:
        data = request.get_json()
        
        if not data.get('course_id') or not data.get('lesson_id') or not data.get('answers'):
            return jsonify({'success': False, 'message': 'Dữ liệu không đầy đủ'})
        
        submission_data = {
            'course_id': data['course_id'],
            'exercise_id': data['lesson_id'],
            'answers': data['answers'],
            'submitted_at': datetime.now().isoformat()
        }
        
        submission_id = db.save_exercise_submission(session['user_id'], submission_data)
        
        course = db.get_course_by_id(data['course_id'])
        if course:
            lesson = next((l for l in course.get('lessons', []) if l['id'] == data['lesson_id']), None)
            if lesson:
                questions = lesson.get('questions', [])
                correct = 0
                total = len(questions)
                
                for i, q in enumerate(questions):
                    user_answer = data['answers'].get(str(i), '').strip()
                    correct_answer = q.get('correct_answer', '').strip()
                    
                    if user_answer and correct_answer:
                        user_first_char = user_answer.split('.')[0].strip().upper()
                        correct_first_char = correct_answer.split('.')[0].strip().upper()
                        
                        if user_first_char == correct_first_char:
                            correct += 1
                
                score = round((correct / total * 100) if total > 0 else 0, 1)
                
                return jsonify({
                    'success': True,
                    'submission_id': submission_id,
                    'score': score,
                    'correct': correct,
                    'total': total,
                    'message': 'Nộp bài thành công'
                })
        
        return jsonify({'success': True, 'submission_id': submission_id, 'message': 'Nộp bài thành công'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
###############

@app.route('/documents')
@login_required
def documents():
    # Lấy các tham số lọc từ query string
    grade_filter = request.args.get('grade', 'all')  # 6, 7, 8, 9, hoặc all
    type_filter = request.args.get('type', 'all')    # document, lecture, exam, hoặc all
    
    docs = db.get_all_documents()
    
    if grade_filter != 'all':
        docs = [d for d in docs if d.get('grade') == grade_filter]
    if type_filter != 'all':
        docs = [d for d in docs if d.get('doc_type') == type_filter]
    
    docs_by_grade = {
        '6': [d for d in docs if d.get('grade') == '6'],
        '7': [d for d in docs if d.get('grade') == '7'],
        '8': [d for d in docs if d.get('grade') == '8'],
        '9': [d for d in docs if d.get('grade') == '9']
    }
    
    return render_template('documents.html',
                         docs_by_grade=docs_by_grade,
                         current_grade=grade_filter,
                         current_type=type_filter)

############
@app.route('/teacher/delete_document/<doc_id>', methods=['POST'])
@teacher_required
def delete_document(doc_id):
    """
    Xóa tài liệu - chỉ giáo viên mới có quyền xóa
    """
    try:
        docs = db.get_all_documents()
        doc = next((d for d in docs if d['id'] == doc_id), None)
        
        if not doc:
            return jsonify({'success': False, 'message': 'Tài liệu không tồn tại'})
        
        # Kiểm tra quyền: chỉ giáo viên tạo tài liệu mới được xóa
        if doc.get('teacher_id') != session['user_id']:
            return jsonify({'success': False, 'message': 'Bạn không có quyền xóa tài liệu này'})
        
        # Xóa file đính kèm nếu có (nếu bạn lưu file local)
        if doc.get('attachments'):
            for attachment in doc.get('attachments', []):
                try:
                    if os.path.exists(attachment.get('path', '')):
                        os.remove(attachment['path'])
                except:
                    pass
        
        # Xóa tài liệu khỏi database
        docs = [d for d in docs if d['id'] != doc_id]
        db._save_json(db.documents_file, docs)
        
        return jsonify({'success': True, 'message': 'Xóa tài liệu thành công'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})

################
@app.route('/teacher/add_document', methods=['GET', 'POST'])
@teacher_required
def add_document():
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            if not data.get('title') or not data.get('url'):
                return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ thông tin'})
            
            if not data.get('grade'):
                return jsonify({'success': False, 'message': 'Vui lòng chọn lớp học'})
            
            if not data.get('doc_type'):
                return jsonify({'success': False, 'message': 'Vui lòng chọn loại tài liệu'})
            
            if 'youtube.com' in data['url'] or 'youtu.be' in data['url']:
                data['link_type'] = 'youtube'
            elif 'drive.google.com' in data['url']:
                data['link_type'] = 'drive'
            else:
                data['link_type'] = data.get('link_type', 'other')
            
            
            data['teacher_id'] = session['user_id']
            
            doc_id = db.add_document(data)
            
            return jsonify({'success': True, 'doc_id': doc_id, 'message': 'Thêm tài liệu thành công'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
    
    return render_template('add_document.html')
#################################




@app.route('/update_progress', methods=['POST'])
@login_required
def update_progress():
    try:
        data = request.get_json()
        
        if not data.get('course_id') or not data.get('lesson_id'):
            return jsonify({'success': False, 'message': 'Dữ liệu không đầy đủ'})
        
        db.update_progress(
            session['user_id'],
            data['course_id'],
            data['lesson_id'],
            data.get('completed', True),
            timestamp=datetime.now().isoformat()
        )
        
        return jsonify({'success': True, 'message': 'Cập nhật tiến độ thành công'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/teacher/students_progress')
@teacher_required
def students_progress():
    teacher_courses = db.get_courses_by_teacher(session['user_id'])
    teacher_course_ids = [c['id'] for c in teacher_courses]
    
    all_progress = db._load_json(db.progress_file)
    filtered_progress = [p for p in all_progress if p['course_id'] in teacher_course_ids]
    
    progress_with_details = []
    for prog in filtered_progress:
        student = get_user_by_id(prog['user_id'])
        course = db.get_course_by_id(prog['course_id'])
        
        if student and course:
            total_lessons = len(course.get('lessons', []))
            completed = len(prog.get('completed_lessons', []))
            percentage = round((completed / total_lessons * 100) if total_lessons > 0 else 0, 1)
            
            progress_with_details.append({
                'student_name': student['username'],
                'student_email': student.get('email', ''),
                'course_title': course['title'],
                'completed': completed,
                'total': total_lessons,
                'percentage': percentage,
                'last_updated': prog.get('last_updated', 'Chưa cập nhật')
            })
    
    return render_template('student_progress.html', progress=progress_with_details)


@app.route('/teacher/view_submissions')
@teacher_required
def view_submissions():
    teacher_courses = db.get_courses_by_teacher(session['user_id'])
    teacher_course_ids = [c['id'] for c in teacher_courses]
    
    try:
        all_submissions = db._load_json(db.submissions_file) if hasattr(db, 'submissions_file') else []
    except:
        all_submissions = []
    
    filtered_submissions = [s for s in all_submissions if s.get('course_id') in teacher_course_ids]
    
    submissions_with_details = []
    for sub in filtered_submissions:
        student = get_user_by_id(sub['user_id'])
        course = db.get_course_by_id(sub.get('course_id'))
        
        if student and course:
            submissions_with_details.append({
                'student_name': student['username'],
                'course_title': course['title'],
                'exercise_id': sub.get('exercise_id'),
                'answers': sub.get('answers', {}),
                'submitted_at': sub.get('submitted_at', 'Không rõ')
            })
    
    return render_template('view_submissions.html', submissions=submissions_with_details)


@app.route('/api/course/<course_id>')
@login_required
def api_get_course(course_id):
    course = db.get_course_by_id(course_id)
    if course:
        return jsonify({'success': True, 'course': course})
    return jsonify({'success': False, 'error': 'Course not found'}), 404


@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500



########################
#
# ============================================================================
# ROUTE 1: Trang chọn đề thi trắc nghiệm (đã sửa)
# ============================================================================
# ============================================================================
# THÊM VÀO ĐẦU FILE app.py (sau phần import)
# ============================================================================

# Danh sách môn học đầy đủ (10 môn)
SUBJECTS = {
    'toan': {'name': 'Toán', 'icon': '🔢', 'color': '#3498db'},
    'anh': {'name': 'Tiếng Anh', 'icon': '🇬🇧', 'color': '#e74c3c'},
    'li': {'name': 'Vật Lý', 'icon': '⚡', 'color': '#9b59b6'},
    'hoa': {'name': 'Hóa Học', 'icon': '🧪', 'color': '#1abc9c'},
    'sinh': {'name': 'Sinh Học', 'icon': '🧬', 'color': '#2ecc71'},
    'su': {'name': 'Lịch Sử', 'icon': '📜', 'color': '#f39c12'},
    'dia': {'name': 'Địa Lý', 'icon': '🌍', 'color': '#16a085'},
    'nguvan': {'name': 'Ngữ Văn', 'icon': '📖', 'color': '#c0392b'},
    'gdcd': {'name': 'GDCD', 'icon': '⚖️', 'color': '#8e44ad'},
    'congnghe': {'name': 'Công Nghệ', 'icon': '🔧', 'color': '#34495e'},
    'tinhoc': {'name': 'Tin Học', 'icon': '💻', 'color': '#2c3e50'}
}

def validate_subject(subject):
    """Kiểm tra môn học hợp lệ"""
    return subject in SUBJECTS


# ============================================================================
# ROUTE 1: Trang chọn đề thi - ĐÃ CẬP NHẬT CHO 10 MÔN
# ============================================================================
@app.route('/tracnghiem')
@login_required
@student_required
def tracnghiem():
    """
    Trang chọn đề thi trắc nghiệm - Hỗ trợ 10 môn học
    """
    print("========= DEBUG TRACNGHIEM =========")
    print(f"User ID: {session.get('user_id')}")
    print(f"Role: {session.get('role')}")
    print(f"Username: {session.get('username')}")
    print("====================================")
    
    try:
        all_exams = []
        
        # Đọc đề thi từ TẤT CẢ các môn học (10 môn)
        for subject_code, subject_info in SUBJECTS.items():
            json_file = f'data/{subject_code}.json'
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    exams_data = json.load(f)
                    exams = exams_data.get('exams', [])
                    
                    for exam in exams:
                        exam['subject'] = subject_code
                        exam['subject_name'] = subject_info['name']
                        exam['subject_icon'] = subject_info['icon']
                        exam['subject_color'] = subject_info['color']
                    
                    all_exams.extend(exams)
                    print(f"✓ Loaded {len(exams)} exams from {subject_info['name']}")
            
            except FileNotFoundError:
                print(f"⚠️ File {json_file} chưa tồn tại")
                continue
            except json.JSONDecodeError:
                print(f"✗ File {json_file} bị lỗi định dạng")
                continue
        
        # Nhóm theo môn học
        exams_by_subject = {}
        for subject_code in SUBJECTS.keys():
            exams_by_subject[subject_code] = [
                e for e in all_exams if e['subject'] == subject_code
            ]
        
        print(f"Total exams: {len(all_exams)}")
        for subject_code, subject_info in SUBJECTS.items():
            count = len(exams_by_subject[subject_code])
            print(f"{subject_info['name']}: {count} đề")
        
        return render_template('tracnghiem.html', 
                             exams_by_subject=exams_by_subject,
                             subjects=SUBJECTS,
                             username=session.get('username'))
    
    except Exception as e:
        print(f"ERROR in tracnghiem route: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Lỗi khi tải danh sách đề thi: {str(e)}', 'danger')
        return redirect(url_for('student_dashboard'))


# ============================================================================
# ROUTE 2: Trang làm bài thi - ĐÃ CẬP NHẬT
# ============================================================================
@app.route('/tracnghiem/lam-bai/<subject>/<exam_id>')
@login_required
@student_required
def lam_bai_tracnghiem(subject, exam_id):
    """
    Hiển thị đề trắc nghiệm để học sinh làm bài
    ĐÃ CẬP NHẬT: Hỗ trợ 10 môn học
    """
    # Validate môn học (10 môn)
    if not validate_subject(subject):
        flash(' Môn học không hợp lệ', 'danger')
        return redirect(url_for('tracnghiem'))
    
    subject_info = SUBJECTS[subject]
    json_file = f'data/{subject}.json'
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            exams_data = json.load(f)
            exams = exams_data.get('exams', [])
            
            exam = next((e for e in exams if e['id'] == exam_id), None)
            
            if not exam:
                flash('Đề thi không tồn tại', 'danger')
                return redirect(url_for('tracnghiem'))
            
            time_limit = exam.get('time_limit', 15)
            
            if not isinstance(time_limit, (int, float)) or time_limit <= 0:
                time_limit = 15
                print(f"Warning: Invalid time_limit in exam {exam_id}, using default 15 minutes")
            
            session_key = f'exam_start_{subject}_{exam_id}'
            reset_param = request.args.get('reset', 'no')
            
            if not session.permanent:
                session.permanent = True
                session.modified = True
            
            should_create_new_session = False
            remaining_time = time_limit * 60
            
            if reset_param == 'yes':
                should_create_new_session = True
                print(f"Reset session for exam {exam_id}")
            
            elif session_key not in session:
                should_create_new_session = True
                print(f"New session for exam {exam_id}")
            else:
                try:
                    start_time_str = session.get(session_key)
                    if not start_time_str or not isinstance(start_time_str, str):
                        raise ValueError("Invalid start_time format")
                    
                    start_time = datetime.fromisoformat(start_time_str)
                    current_time = datetime.now()
                    
                    elapsed_seconds = (current_time - start_time).total_seconds()
                    
                    if elapsed_seconds < 0:
                        print(f"ERROR: Negative elapsed time for exam {exam_id}")
                        should_create_new_session = True
                    elif elapsed_seconds > (time_limit * 60 * 2):
                        print(f"WARNING: Session too old for exam {exam_id}")
                        should_create_new_session = True
                    else:
                        remaining_time = (time_limit * 60) - elapsed_seconds
                        
                        if remaining_time <= 0:
                            flash(' Đã hết thời gian làm bài! Vui lòng làm lại từ đầu.', 'warning')
                            session.pop(session_key, None)
                            session.modified = True
                            return redirect(url_for('tracnghiem'))
                        
                        print(f"Exam {exam_id}: {int(remaining_time)}s remaining")
                
                except (ValueError, KeyError, TypeError, AttributeError) as e:
                    print(f"Session error for exam {exam_id}: {e}")
                    should_create_new_session = True
            
            if should_create_new_session:
                current_time = datetime.now()
                session[session_key] = current_time.isoformat()
                session.permanent = True
                session.modified = True
                remaining_time = time_limit * 60
                print(f"Created new session for exam {exam_id}, expires in {time_limit} minutes")
            
            remaining_time = max(1, min(remaining_time, time_limit * 60))
            remaining_time = int(remaining_time)
            
            print(f"""
            ===== EXAM SESSION INFO =====
            Exam: {exam_id} | Subject: {subject}
            Time Limit: {time_limit} minutes
            Remaining: {remaining_time} seconds ({remaining_time//60}m {remaining_time%60}s)
            Session Key: {session_key}
            Session Permanent: {session.permanent}
            ============================
            """)
            
            return render_template('baitap.html',
                                 exam=exam,
                                 subject=subject,
                                 subject_name=subject_info['name'],
                                 subject_icon=subject_info['icon'],
                                 subject_color=subject_info['color'],
                                 time_limit=time_limit,
                                 remaining_time=remaining_time,
                                 username=session.get('username'))
    
    except FileNotFoundError:
        flash('⚠️ Không tìm thấy dữ liệu đề thi', 'danger')
        return redirect(url_for('tracnghiem'))
    
    except json.JSONDecodeError as e:
        flash('⚠️ Dữ liệu đề thi bị lỗi định dạng', 'danger')
        print(f"JSON decode error: {e}")
        return redirect(url_for('tracnghiem'))
    
    except Exception as e:
        flash(f'⚠️ Lỗi không xác định: {str(e)}', 'danger')
        print(f"Unexpected error in lam_bai_tracnghiem: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('tracnghiem'))


# ============================================================================
# ROUTE 3: API kiểm tra thời gian - ĐÃ CẬP NHẬT
# ============================================================================
@app.route('/api/tracnghiem/check-time/<subject>/<exam_id>')
@login_required
@student_required
def api_check_exam_time(subject, exam_id):
    """
    API kiểm tra thời gian còn lại - Hỗ trợ 10 môn
    """
    if not validate_subject(subject):
        return jsonify({
            'success': False,
            'message': 'Môn học không hợp lệ',
            'is_expired': True,
            'remaining_time': 0
        })
    
    session_key = f'exam_start_{subject}_{exam_id}'
    
    if session_key not in session:
        return jsonify({
            'success': False,
            'message': 'Session không tồn tại',
            'is_expired': True,
            'remaining_time': 0
        })
    
    try:
        json_file = f'data/{subject}.json'
        with open(json_file, 'r', encoding='utf-8') as f:
            exams_data = json.load(f)
            exams = exams_data.get('exams', [])
            exam = next((e for e in exams if e['id'] == exam_id), None)
            
            if not exam:
                return jsonify({
                    'success': False,
                    'message': 'Đề thi không tồn tại',
                    'is_expired': True,
                    'remaining_time': 0
                })
            
            time_limit = exam.get('time_limit', 15)
        
        start_time = datetime.fromisoformat(session[session_key])
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        remaining_seconds = (time_limit * 60) - elapsed_seconds
        
        if remaining_seconds <= 0:
            session.pop(session_key, None)
            session.modified = True
            
            return jsonify({
                'success': True,
                'remaining_time': 0,
                'is_expired': True,
                'message': 'Hết thời gian'
            })
        
        return jsonify({
            'success': True,
            'remaining_time': int(remaining_seconds),
            'is_expired': False,
            'time_limit_minutes': time_limit
        })
    
    except (ValueError, KeyError, TypeError) as e:
        print(f"Error in api_check_exam_time: {e}")
        return jsonify({
            'success': False,
            'message': f'Lỗi session: {str(e)}',
            'is_expired': True,
            'remaining_time': 0
        })
    
    except Exception as e:
        print(f"Unexpected error in api_check_exam_time: {e}")
        return jsonify({
            'success': False,
            'message': f'Lỗi: {str(e)}',
            'is_expired': True,
            'remaining_time': 0
        })


# ============================================================================
# ROUTE 4: Nộp bài thi -  ĐÃ TÍCH HỢP AI GEMINI 
# ============================================================================
@app.route('/tracnghiem/nop-bai', methods=['POST'])
@login_required
@student_required
def nop_bai_tracnghiem():
    """
    Nộp bài - Hỗ trợ cả trắc nghiệm và tự luận
    Điểm tổng luôn quy về thang 10
    ⭐ ĐÃ TÍCH HỢP AI PHÂN TÍCH ⭐
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'Không nhận được dữ liệu'}), 400
        
        subject = data.get('subject')
        exam_id = data.get('exam_id')
        answers = data.get('answers', {})      # Câu trắc nghiệm
        essays = data.get('essays', {})        # Câu tự luận (nếu có)
        
        # Validate
        if not subject or not exam_id:
            return jsonify({'success': False, 'message': 'Thiếu thông tin đề thi'}), 400
        
        if not validate_subject(subject):
            return jsonify({'success': False, 'message': 'Môn học không hợp lệ'}), 400
        
        # Kiểm tra session
        session_key = f'exam_start_{subject}_{exam_id}'
        if session_key not in session:
            return jsonify({'success': False, 'message': '⚠️ Session đã hết hạn'}), 403
        
        # Load đề thi
        json_file = f'data/{subject}.json'
        with open(json_file, 'r', encoding='utf-8') as f:
            exams_data = json.load(f)
            exam = next((e for e in exams_data.get('exams', []) if e['id'] == exam_id), None)
        
        if not exam:
            return jsonify({'success': False, 'message': 'Không tìm thấy đề thi'}), 404
        
        # Kiểm tra thời gian
        time_limit = exam.get('time_limit', 15)
        try:
            start_time = datetime.fromisoformat(session[session_key])
            elapsed_seconds = (datetime.now() - start_time).total_seconds()
            
            if elapsed_seconds > (time_limit * 60):
                session.pop(session_key, None)
                return jsonify({'success': False, 'message': '⏰ Hết thời gian!'}), 403
        except:
            return jsonify({'success': False, 'message': 'Session không hợp lệ'}), 403
        
        # ========== LẤY CẤU HÌNH CHẤM ĐIỂM ==========
        scoring_config = exam.get('scoring_config', {})
        
        # Nếu không có scoring_config, mặc định 100% trắc nghiệm
        if not scoring_config:
            scoring_config = {
                'multiple_choice': {'weight_percent': 100, 'points': 10}
            }
        
        mc_weight = scoring_config.get('multiple_choice', {}).get('weight_percent', 100) / 100
        essay_weight = scoring_config.get('essay', {}).get('weight_percent', 0) / 100
        
        # ========== KẾT QUẢ ==========
        result = {
            'multiple_choice': None,
            'essay': None,
            'total_score': 0,
            'wrong_answers': []
        }
        
        # ========== CHẤM PHẦN TRẮC NGHIỆM ==========
        sections = exam.get('sections', [])
        
        # Nếu đề không có sections (đề cũ), dùng questions trực tiếp
        if not sections and exam.get('questions'):
            sections = [{
                'type': 'multiple_choice',
                'questions': exam.get('questions', [])
            }]
        
        mc_section = next((s for s in sections if s['type'] == 'multiple_choice'), None)
        
        if mc_section:
            mc_questions = mc_section.get('questions', [])
            correct_count = 0
            
            for q in mc_questions:
                q_id = str(q['id'])
                user_answer = answers.get(q_id, '').strip().upper()
                correct_answer = q['correct_answer'].strip().upper()
                
                if user_answer == correct_answer:
                    correct_count += 1
                else:
                    result['wrong_answers'].append({
                        'question_number': q['number'],
                        'question_text': q['question'],
                        'user_answer': user_answer if user_answer else 'Không trả lời',
                        'correct_answer': correct_answer,
                        'explanation': q.get('explanation', '')
                    })
            
            total_mc = len(mc_questions)
            mc_percentage = (correct_count / total_mc) if total_mc > 0 else 0
            mc_score = mc_percentage * 10 * mc_weight
            
            result['multiple_choice'] = {
                'correct_count': correct_count,
                'total_questions': total_mc,
                'percentage': round(mc_percentage * 100, 1),
                'raw_score': round(mc_score, 2),
                'weight': mc_weight * 100
            }
        
        # ========== CHẤM PHẦN TỰ LUẬN (NẾU CÓ) ==========
        essay_section = next((s for s in sections if s['type'] == 'essay'), None)
        
        if essay_section and essay_weight > 0:
            essay_questions = essay_section.get('questions', [])
            essay_results = []
            total_essay_score = 0
            
            for q in essay_questions:
                q_id = str(q['id'])
                user_essay = essays.get(q_id, '').strip()
                
                # Validate độ dài
                word_count = len(user_essay.split()) if user_essay else 0
                min_words = q.get('min_words', 0)
                max_words = q.get('max_words', 999999)
                
                if word_count < min_words:
                    essay_results.append({
                        'question_number': q['number'],
                        'question': q['question'],
                        'score': 0,
                        'max_score': q.get('points', 0),
                        'feedback': f'Bài viết quá ngắn ({word_count}/{min_words} từ)',
                        'word_count': word_count
                    })
                    continue
                
                if word_count > max_words:
                    essay_results.append({
                        'question_number': q['number'],
                        'question': q['question'],
                        'score': 0,
                        'max_score': q.get('points', 0),
                        'feedback': f'Bài viết quá dài ({word_count}/{max_words} từ)',
                        'word_count': word_count
                    })
                    continue
                
                # Chấm bằng AI (nếu bật)
                if scoring_config.get('essay', {}).get('ai_grading', False):
                    try:
                        from utils.gemini_api import grade_essay_with_ai
                        
                        ai_feedback = grade_essay_with_ai(user_essay, q, subject)
                        
                        # Tính điểm theo rubric
                        rubric = q.get('grading_rubric', {})
                        essay_score = 0
                        max_points = q.get('points', 0)
                        details = {}
                        
                        for criterion, config in rubric.items():
                            weight = config.get('weight_percent', 0) / 100
                            criterion_score = ai_feedback.get(criterion, {}).get('score', 5)
                            weighted = (criterion_score / 10) * max_points * weight
                            essay_score += weighted
                            
                            details[criterion] = {
                                'score': criterion_score,
                                'weighted_score': round(weighted, 2),
                                'feedback': ai_feedback.get(criterion, {}).get('feedback', '')
                            }
                        
                        total_essay_score += essay_score
                        
                        essay_results.append({
                            'question_number': q['number'],
                            'question': q['question'],
                            'user_answer': user_essay,
                            'score': round(essay_score, 2),
                            'max_score': max_points,
                            'word_count': word_count,
                            'feedback': ai_feedback.get('overall_feedback', ''),
                            'details': details
                        })
                    
                    except Exception as e:
                        print(f"❌ Lỗi chấm AI: {e}")
                        essay_results.append({
                            'question_number': q['number'],
                            'question': q['question'],
                            'score': 0,
                            'max_score': q.get('points', 0),
                            'feedback': 'Lỗi hệ thống chấm bài',
                            'word_count': word_count
                        })
                else:
                    # Không dùng AI, cho điểm trung bình
                    max_points = q.get('points', 0)
                    default_score = max_points * 0.7
                    total_essay_score += default_score
                    
                    essay_results.append({
                        'question_number': q['number'],
                        'question': q['question'],
                        'user_answer': user_essay,
                        'score': round(default_score, 2),
                        'max_score': max_points,
                        'word_count': word_count,
                        'feedback': 'Bài làm đã được nộp (chưa chấm chi tiết)'
                    })
            
            # Tính điểm tự luận
            max_essay_points = sum(q.get('points', 0) for q in essay_questions)
            essay_percentage = (total_essay_score / max_essay_points) if max_essay_points > 0 else 0
            essay_weighted = essay_percentage * 10 * essay_weight
            
            result['essay'] = {
                'total_score': round(total_essay_score, 2),
                'max_score': max_essay_points,
                'percentage': round(essay_percentage * 100, 1),
                'weighted_score': round(essay_weighted, 2),
                'weight': essay_weight * 100,
                'results': essay_results
            }
        
        # ========== TỔNG ĐIỂM ==========
        mc_final = result['multiple_choice']['raw_score'] if result['multiple_choice'] else 0
        essay_final = result['essay']['weighted_score'] if result['essay'] else 0
        result['total_score'] = round(mc_final + essay_final, 2)
        
        # ========== XÓA SESSION ==========
        session.pop(session_key, None)
        session.modified = True
        
        # ⭐⭐⭐ TẠO PHÂN TÍCH AI ⭐⭐⭐
        ai_analysis = None
        
        # Chỉ tạo AI analysis nếu có câu sai
        if result.get('wrong_answers') and len(result['wrong_answers']) > 0:
            try:
                print("🤖 Đang tạo phân tích AI...")
                
                from utils.gemini_api import analyze_exam_results
                
                subject_info = SUBJECTS.get(subject, {})
                
                # Chuẩn bị dữ liệu cho AI
                analysis_data = {
                    'subject': subject,
                    'subject_name': subject_info.get('name', subject),
                    'exam_title': exam.get('title', ''),
                    'total_score': result['total_score'],
                    'correct_count': result['multiple_choice']['correct_count'] if result.get('multiple_choice') else 0,
                    'total_questions': result['multiple_choice']['total_questions'] if result.get('multiple_choice') else 0,
                    'wrong_answers': result['wrong_answers']
                }
                
                # Gọi AI để phân tích
                ai_analysis = analyze_exam_results(analysis_data)
                
                if ai_analysis:
                    print("✅ Đã tạo phân tích AI thành công")
                else:
                    print("⚠️ Không thể tạo phân tích AI")
                    
            except Exception as e:
                print(f"❌ Lỗi AI: {e}")
                ai_analysis = None
        else:
            print("⚠️ Không có câu sai, bỏ qua phân tích AI")
        
        # ========== LƯU KẾT QUẢ ==========
        results_file = 'data/exam_results.json'
        os.makedirs('data', exist_ok=True)
        
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                all_results = json.load(f)
        except:
            all_results = []
        
        subject_info = SUBJECTS.get(subject, {})
        
        all_results.append({
            'user_id': session['user_id'],
            'username': session.get('username', 'Unknown'),
            'subject': subject,
            'subject_name': subject_info.get('name', subject),
            'subject_icon': subject_info.get('icon', '📚'),
            'subject_color': subject_info.get('color', '#95a5a6'),
            'exam_id': exam_id,
            'exam_title': exam.get('title', ''),
            'result': result,
            'ai_analysis': ai_analysis,  # ⭐ THÊM AI ANALYSIS
            'submitted_at': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        })
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True,
            'result': result,
            'message': 'Nộp bài thành công'
        })
    
    except FileNotFoundError:
        return jsonify({'success': False, 'message': 'Không tìm thấy file đề thi'}), 404
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'}), 500

# ============================================================================
# ROUTE 5: Lịch sử làm bài - ĐÃ CẬP NHẬT
# ============================================================================
@app.route('/tracnghiem/lich-su')
@login_required
@student_required
def lich_su_tracnghiem():
    """
    Hiển thị lịch sử làm bài - Hỗ trợ 10 môn học
    """
    try:
        user_id = session.get('user_id')
        results_file = 'data/exam_results.json'
        
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                all_results = json.load(f)
        except FileNotFoundError:
            all_results = []
        except json.JSONDecodeError:
            print("ERROR: exam_results.json bị lỗi định dạng")
            all_results = []
        
        user_results = [r for r in all_results if r.get('user_id') == user_id]
        user_results.sort(key=lambda x: x.get('submitted_at', ''), reverse=True)
        
        # Thêm tên môn học và icon
        for result in user_results:
            subject = result.get('subject', '')
            subject_info = SUBJECTS.get(subject, {'name': subject, 'icon': '📚'})
            result['subject_name'] = subject_info['name']
            result['subject_icon'] = subject_info['icon']
            result['subject_color'] = subject_info.get('color', '#95a5a6')
        
        print(f"User {user_id} có {len(user_results)} bài đã làm")
        
        return render_template('lichsu_tracnghiem.html', 
                             results=user_results,
                             username=session.get('username'))
    
    except Exception as e:
        print(f"ERROR in lich_su_tracnghiem: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Lỗi khi tải lịch sử: {str(e)}', 'danger')
        return redirect(url_for('tracnghiem'))


# ============================================================================
# ROUTE 6: Reset session - GIỮ NGUYÊN
# ============================================================================
@app.route('/tracnghiem/reset/<subject>/<exam_id>')
@login_required
@student_required
def reset_exam_session(subject, exam_id):
    """
    Reset session để làm lại bài thi
    """
    if not validate_subject(subject):
        flash('Môn học không hợp lệ', 'danger')
        return redirect(url_for('tracnghiem'))
    
    session_key = f'exam_start_{subject}_{exam_id}'
    
    if session_key in session:
        session.pop(session_key)
        session.modified = True
        flash('Đã reset bài thi. Bạn có thể làm lại từ đầu!', 'success')
    
    return redirect(url_for('lam_bai_tracnghiem', subject=subject, exam_id=exam_id, reset='yes'))


# ============================================================================
# ROUTE 7: Xem kết quả - ⭐ ĐÃ TÍCH HỢP HIỂN THỊ AI ANALYSIS ⭐
# ============================================================================
@app.route('/tracnghiem/ket-qua/<subject>/<exam_id>')
@login_required
@student_required
def ket_qua_tracnghiem(subject, exam_id):
    """
    Hiển thị kết quả bài làm - ⭐ BAO GỒM PHÂN TÍCH AI
    """
    try:
        if not validate_subject(subject):
            flash('Môn học không hợp lệ', 'danger')
            return redirect(url_for('tracnghiem'))
        
        user_id = session.get('user_id')
        results_file = 'data/exam_results.json'
        
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                all_results = json.load(f)
        except FileNotFoundError:
            flash('Không tìm thấy kết quả bài làm', 'warning')
            return redirect(url_for('tracnghiem'))
        
        matching_results = [
            r for r in all_results 
            if r.get('user_id') == user_id 
            and r.get('subject') == subject
            and r.get('exam_id') == exam_id
        ]
        
        if not matching_results:
            flash('Không tìm thấy kết quả bài làm', 'warning')
            return redirect(url_for('tracnghiem'))
        
        result_data = matching_results[-1]
        
        # Thêm thông tin môn học
        subject_info = SUBJECTS.get(subject, {'name': subject, 'icon': '📚', 'color': '#95a5a6'})
        
        # ⭐ CHUẨN BỊ DỮ LIỆU CHO TEMPLATE
        # Lấy kết quả thực tế từ nested structure
        actual_result = result_data.get('result', {})
        
        # Tính toán các giá trị cần thiết
        if actual_result.get('multiple_choice'):
            mc_data = actual_result['multiple_choice']
            correct_count = mc_data.get('correct_count', 0)
            total_questions = mc_data.get('total_questions', 0)
        else:
            correct_count = 0
            total_questions = 0
        
        # Tạo object result đơn giản cho template
        template_result = {
            'score': actual_result.get('total_score', 0),
            'correct_count': correct_count,
            'total_questions': total_questions,
            'wrong_answers': actual_result.get('wrong_answers', []),
            'subject': subject,
            'subject_name': subject_info['name'],
            'subject_icon': subject_info['icon'],
            'subject_color': subject_info['color'],
            'exam_id': exam_id,
            'exam_title': result_data.get('exam_title', ''),
            'submitted_at': result_data.get('submitted_at', '')
        }
        
        # ⭐ LẤY PHÂN TÍCH AI (nếu có)
        ai_analysis = result_data.get('ai_analysis', None)
        
        if ai_analysis:
            print(f"✅ Hiển thị phân tích AI cho user {user_id}")
        else:
            print(f"⚠️ Không có phân tích AI cho bài thi này")
        
        return render_template('ketqua.html', 
                             result=template_result,
                             ai_analysis=ai_analysis,
                             username=session.get('username'))
    
    except Exception as e:
        print(f"ERROR in ket_qua_tracnghiem: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Lỗi khi hiển thị kết quả: {str(e)}', 'danger')
        return redirect(url_for('tracnghiem'))
##############


UPLOAD_FOLDER = 'static/uploads/forum'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'zip', 'rar'}
MAX_FILE_SIZE = 10 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/forum')
@login_required
def forum():
    search_query = request.args.get('search', '').strip()
    filter_type = request.args.get('filter', 'all')
    
    if search_query:
        posts = db.search_forum_posts(search_query)
    elif filter_type == 'my_posts':
        posts = db.get_forum_posts_by_user(session['user_id'])
    else:
        posts = db.get_all_forum_posts()
    
    for post in posts:
        post['created_at_formatted'] = format_datetime(post['created_at'])
        if post.get('updated_at'):
            post['updated_at_formatted'] = format_datetime(post['updated_at'])
    
    return render_template('forum.html', 
                         posts=posts,
                         search_query=search_query,
                         filter_type=filter_type,
                         username=session.get('username'))


@app.route('/forum/post/<post_id>')
@login_required
def forum_post_detail(post_id):
    post = db.get_forum_post_by_id(post_id)
    
    if not post:
        flash('Bài viết không tồn tại', 'danger')
        return redirect(url_for('forum'))
    
    db.increment_post_views(post_id)
    
    comments = db.get_comments_by_post(post_id)
    
    post['created_at_formatted'] = format_datetime(post['created_at'])
    if post.get('updated_at'):
        post['updated_at_formatted'] = format_datetime(post['updated_at'])
    
    for comment in comments:
        comment['created_at_formatted'] = format_datetime(comment['created_at'])
    
    is_author = post['author_id'] == session['user_id']
    
    return render_template('forum_post_detail.html',
                         post=post,
                         comments=comments,
                         is_author=is_author,
                         username=session.get('username'))


@app.route('/forum/create', methods=['GET', 'POST'])
@login_required
def forum_create_post():
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            tags_str = request.form.get('tags', '').strip()
            
            if not title or not content:
                return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ tiêu đề và nội dung'})
            
            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()] if tags_str else []
            
            attachments = []
            if 'files' in request.files:
                files = request.files.getlist('files')
                for file in files:
                    if file and file.filename and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                        
                        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                        file.save(file_path)
                        
                        file_size = os.path.getsize(file_path)
                        
                        file_ext = filename.rsplit('.', 1)[1].lower()
                        file_type = 'image' if file_ext in {'png', 'jpg', 'jpeg', 'gif'} else 'file'
                        
                        attachments.append({
                            'type': file_type,
                            'filename': filename,
                            'path': file_path.replace('\\', '/'),
                            'size': file_size
                        })
            
            user = get_user_by_id(session['user_id'])
            
            post_data = {
                'title': title,
                'content': content,
                'author_id': session['user_id'],
                'author_name': session.get('username', 'Unknown'),
                'author_role': user.get('role', 'student') if user else 'student',
                'attachments': attachments,
                'tags': tags
            }
            
            post_id = db.create_forum_post(post_data)
            
            return jsonify({'success': True, 'post_id': post_id, 'message': 'Tạo bài viết thành công'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
    
    return render_template('forum_create_post.html', username=session.get('username'))


@app.route('/forum/edit/<post_id>', methods=['GET', 'POST'])
@login_required
def forum_edit_post(post_id):
    post = db.get_forum_post_by_id(post_id)
    
    if not post:
        flash('Bài viết không tồn tại', 'danger')
        return redirect(url_for('forum'))
    
    if post['author_id'] != session['user_id']:
        flash('Bạn không có quyền chỉnh sửa bài viết này', 'danger')
        return redirect(url_for('forum'))
    
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            tags_str = request.form.get('tags', '').strip()
            
            if not title or not content:
                return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ tiêu đề và nội dung'})
            
            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()] if tags_str else []
            
            attachments = post.get('attachments', [])
            
            if 'files' in request.files:
                files = request.files.getlist('files')
                for file in files:
                    if file and file.filename and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                        
                        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                        file.save(file_path)
                        
                        file_size = os.path.getsize(file_path)
                        file_ext = filename.rsplit('.', 1)[1].lower()
                        file_type = 'image' if file_ext in {'png', 'jpg', 'jpeg', 'gif'} else 'file'
                        
                        attachments.append({
                            'type': file_type,
                            'filename': filename,
                            'path': file_path.replace('\\', '/'),
                            'size': file_size
                        })
            
            post_data = {
                'title': title,
                'content': content,
                'attachments': attachments,
                'tags': tags
            }
            
            success = db.update_forum_post(post_id, post_data)
            
            if success:
                return jsonify({'success': True, 'message': 'Cập nhật bài viết thành công'})
            else:
                return jsonify({'success': False, 'message': 'Cập nhật thất bại'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
    
    return render_template('forum_create_post.html', 
                         post=post, 
                         edit_mode=True,
                         username=session.get('username'))


@app.route('/forum/delete/<post_id>', methods=['POST'])
@login_required
def forum_delete_post(post_id):
    post = db.get_forum_post_by_id(post_id)
    
    if not post:
        return jsonify({'success': False, 'message': 'Bài viết không tồn tại'})
    
    if post['author_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Bạn không có quyền xóa bài viết này'})
    
    for attachment in post.get('attachments', []):
        try:
            if os.path.exists(attachment['path']):
                os.remove(attachment['path'])
        except:
            pass
    
    db.delete_forum_post(post_id)
    
    return jsonify({'success': True, 'message': 'Xóa bài viết thành công'})


@app.route('/forum/comment/<post_id>', methods=['POST'])
@login_required
def forum_add_comment(post_id):
    try:
        post = db.get_forum_post_by_id(post_id)
        
        if not post:
            return jsonify({'success': False, 'message': 'Bài viết không tồn tại'})
        
        content = request.form.get('content', '').strip()
        
        if not content:
            return jsonify({'success': False, 'message': 'Vui lòng nhập nội dung bình luận'})
        
        attachments = []
        if 'files' in request.files:
            files = request.files.getlist('files')
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                    
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                    file.save(file_path)
                    
                    file_size = os.path.getsize(file_path)
                    file_ext = filename.rsplit('.', 1)[1].lower()
                    file_type = 'image' if file_ext in {'png', 'jpg', 'jpeg', 'gif'} else 'file'
                    
                    attachments.append({
                        'type': file_type,
                        'filename': filename,
                        'path': file_path.replace('\\', '/'),
                        'size': file_size
                    })
        
        user = get_user_by_id(session['user_id'])
        
        comment_data = {
            'post_id': post_id,
            'author_id': session['user_id'],
            'author_name': session.get('username', 'Unknown'),
            'author_role': user.get('role', 'student') if user else 'student',
            'content': content,
            'attachments': attachments
        }
        
        comment_id = db.add_comment(comment_data)
        
        return jsonify({'success': True, 'comment_id': comment_id, 'message': 'Thêm bình luận thành công'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/forum/delete-comment/<comment_id>', methods=['POST'])
@login_required
def forum_delete_comment(comment_id):
    comments = db._load_json(db.forum_comments_file)
    comment = next((c for c in comments if c['id'] == comment_id), None)
    
    if not comment:
        return jsonify({'success': False, 'message': 'Bình luận không tồn tại'})
    
    if comment['author_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Bạn không có quyền xóa bình luận này'})
    
    for attachment in comment.get('attachments', []):
        try:
            if os.path.exists(attachment['path']):
                os.remove(attachment['path'])
        except:
            pass
    
    db.delete_comment(comment_id)
    
    return jsonify({'success': True, 'message': 'Xóa bình luận thành công'})


def format_datetime(iso_string):
    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime('%d/%m/%Y %H:%M')
    except:
        return iso_string
#######
@app.route('/chat')
@login_required
def chat_room():
    messages = db.get_all_chat_messages()
    
    for msg in messages:
        msg['created_at_formatted'] = format_datetime(msg['created_at'])
    
    return render_template('chat_room.html',
                         messages=messages,
                         username=session.get('username'))


@app.route('/api/chat/send', methods=['POST'])
@login_required
def send_chat_message():
    try:
        data = request.get_json()
        content = data.get('content', '').strip()
        reply_to = data.get('reply_to')
        
        if not content:
            return jsonify({'success': False, 'message': 'Nội dung không được để trống'})
        
        user = get_user_by_id(session['user_id'])
        
        message_data = {
            'content': content,
            'author_id': session['user_id'],
            'author_name': session.get('username', 'Unknown'),
            'author_role': user.get('role', 'student') if user else 'student',
            'reply_to': reply_to
        }
        
        message_id = db.add_chat_message(message_data)
        message = db.get_chat_message_by_id(message_id)
        message['created_at_formatted'] = format_datetime(message['created_at'])
        
        return jsonify({
            'success': True,
            'message': message
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/api/chat/messages')
@login_required
def get_chat_messages():
    try:
        last_id = request.args.get('last_id', '')
        messages = db.get_chat_messages_after(last_id)
        
        for msg in messages:
            msg['created_at_formatted'] = format_datetime(msg['created_at'])
        
        return jsonify({
            'success': True,
            'messages': messages
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/api/chat/delete/<message_id>', methods=['POST'])
@login_required
def delete_chat_message(message_id):
    try:
        message = db.get_chat_message_by_id(message_id)
        
        if not message:
            return jsonify({'success': False, 'message': 'Tin nhắn không tồn tại'})
        
        if message['author_id'] != session['user_id']:
            return jsonify({'success': False, 'message': 'Bạn không có quyền xóa tin nhắn này'})
        
        db.delete_chat_message(message_id)
        
        return jsonify({'success': True, 'message': 'Đã xóa tin nhắn'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
################
#game

@app.route("/enter_nickname")
def enter_nickname():
    return render_template("nickname.html")

@app.route("/start_game", methods=["POST"])
def start_game():
    nickname = request.form["nickname"]
    bai = request.form["bai"]
    session["nickname"] = nickname
    session["bai"] = bai
    return redirect("/game")

@app.route("/game")
def game():
    if "nickname" not in session or "bai" not in session:
        return redirect("/enter_nickname")
    return render_template("game.html")

@app.route("/get_questions")
def get_questions():
    bai = session.get("bai", "bai_1")
    with open("questions.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = data.get(bai, [])
    random.shuffle(questions)
    for q in questions:
        random.shuffle(q["options"])
    return jsonify(questions[:20])

@app.route("/submit_score", methods=["POST"])
def submit_score():
    nickname = session.get("nickname")
    bai = session.get("bai")
    score = request.json["score"]

    if not nickname:
        return jsonify({"status": "error", "message": "No nickname found"})
    if not bai:
        return jsonify({"status": "error", "message": "No bai found"})

    if not os.path.exists("scores.json"):
        with open("scores.json", "w", encoding="utf-8") as f:
            json.dump([], f)

    with open("scores.json", "r+", encoding="utf-8") as f:
        scores = json.load(f)
        now = datetime.now().strftime("%d/%m/%Y %H:%M")

        existing = next((s for s in scores if s["nickname"] == nickname and s.get("bai") == bai), None)

        if existing:
            if score > existing["score"]:
                existing["score"] = score
                existing["time"] = now
        else:
            scores.append({
                "nickname": nickname,
                "score": score,
                "time": now,
                "bai": bai
            })

        filtered = [s for s in scores if s.get("bai") == bai]
        top50 = sorted(filtered, key=lambda x: x["score"], reverse=True)[:50]

        others = [s for s in scores if s.get("bai") != bai]
        final_scores = others + top50

        f.seek(0)
        json.dump(final_scores, f, ensure_ascii=False, indent=2)
        f.truncate()

    return jsonify({"status": "ok"})

@app.route("/leaderboard")
def leaderboard():
    bai = session.get("bai")

    if not bai:
        bai = "bai_1"

    if not os.path.exists("scores.json"):
        top5 = []
    else:
        with open("scores.json", "r", encoding="utf-8") as f:
            scores = json.load(f)

        filtered = [s for s in scores if s.get("bai") == bai]
        top5 = sorted(filtered, key=lambda x: x["score"], reverse=True)[:5]

    return render_template("leaderboard.html", players=top5, bai=bai)

# Nếu cần giữ cả hai, đổi tên route
@app.route('/chatbot')
@login_required
def chatbot():
    """
    Hien thi trang chatbot
    """
    return render_template('chatbot.html', 
                         username=session.get('username'),
                         user_role=session.get('role'))


@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    """
    API chat - xử lý cả text và ảnh
    """
    try:
        # Kiểm tra Content-Type
        is_json = request.content_type and 'application/json' in request.content_type
        
        # Kiểm tra có file ảnh không
        has_image = 'image' in request.files
        image_data = None
        
        if has_image:
            file = request.files['image']
            
            if file and file.filename:
                # Validate định dạng
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                
                if file_ext not in allowed_extensions:
                    return jsonify({
                        'success': False,
                        'error': 'Chỉ chấp nhận ảnh: PNG, JPG, JPEG, GIF, WEBP'
                    }), 400
                
                # Đọc ảnh
                image_data = file.read()
                
                # Kiểm tra kích thước (max 10MB)
                if len(image_data) > 10 * 1024 * 1024:
                    return jsonify({
                        'success': False,
                        'error': 'Ảnh quá lớn. Tối đa 10MB'
                    }), 400
        
        # Lấy message - ưu tiên form, fallback về JSON
        if is_json:
            user_message = request.get_json().get('message', '').strip()
        else:
            user_message = request.form.get('message', '').strip()
        
        if not user_message and not image_data:
            return jsonify({
                'success': False,
                'error': 'Vui lòng nhập tin nhắn hoặc gửi ảnh'
            }), 400
        
        # Import hàm mới
        from utils.gemini_api import chat_with_gemini_image
        
        # Gọi Gemini với ảnh (nếu có)
        if image_data:
            response = chat_with_gemini_image(user_message, image_data=image_data)
        else:
            response = chat_with_gemini(user_message)
        
        # Xử lý response
        processed = process_response(response)
        
        # Lưu vào database
        db.add_chat_message({
            'content': user_message if user_message else "[Đã gửi ảnh]",
            'author_id': session['user_id'],
            'author_name': session['username'],
            'author_role': session.get('role', 'student'),
            'response': response,
            'has_diagrams': processed['has_diagrams'],
            'has_image': bool(image_data)
        })
        
        return jsonify({
            'success': True,
            'response': response,
            'processed': processed
        })
        
    except Exception as e:
        print(f"Lỗi chat API: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': 'Có lỗi xảy ra khi xử lý tin nhắn',
            'details': str(e)
        }), 500


@app.route('/api/chat/history', methods=['GET'])
@login_required
def get_chat_history():
    """
    Lay lich su chat cua user
    """
    try:
        user_id = session['user_id']
        messages = db.get_all_chat_messages()
        
        # Filter tin nhan cua user
        user_messages = [
            m for m in messages 
            if m.get('author_id') == user_id
        ]
        
        return jsonify({
            'success': True,
            'messages': user_messages[-50:]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/chat/clear', methods=['POST'])
@login_required
def clear_chat():
    """
    Xoa lich su chat
    """
    try:
        # Logic xoa chat o day
        return jsonify({
            'success': True,
            'message': 'Da xoa lich su chat'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

###############
@app.route("/logout_old")  # Đổi URL
def logout_old():
    session.clear()
    return redirect("/login")
##############
if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash,
    send_from_directory,
)
from functools import wraps
import os
import random
import re
from werkzeug.utils import secure_filename
import uuid
from PIL import Image, UnidentifiedImageError
from utils.auth import register_user, login_user, get_user_by_id, load_users, save_users
from utils.database import Database
from utils.gemini_api import (
    chat_with_gemini,
    generate_math_quiz,
    generate_teacher_exam,
    is_quiz_request,
    process_response,
)
from utils.gemini_api import grade_essay_with_ai  ############
from utils.storage import (
    FORUM_UPLOAD_DIR,
    attachment_storage_path,
    ensure_forum_upload_available,
    forum_upload_path,
    forum_upload_url,
    read_json,
    readable_data_file,
    sync_file_to_remote,
    writable_data_file,
    writable_state_file,
    write_json,
)
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)
app.config["SESSION_COOKIE_SECURE"] = False  # Đổi thành True nếu dùng HTTPS
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


db = Database()
HOME_STATS_CACHE_SECONDS = 60
_home_stats_cache = {"expires_at": None, "value": None}
QUESTIONS_FILE = writable_state_file("questions.json", {"topics": []})
SCORES_FILE = writable_state_file("scores.json", [])
FORUM_POINTS_FILE = writable_data_file("forum_points.json", [])
FORUM_REPORTS_FILE = writable_data_file("forum_reports.json", [])
FORUM_BANS_FILE = writable_data_file("forum_bans.json", [])
SHOP_ITEMS_FILE = writable_data_file("shop_items.json", [])
SHOP_ORDERS_FILE = writable_data_file("shop_orders.json", [])
USER_INVENTORY_FILE = writable_data_file("user_inventory.json", [])
USER_PROFILES_FILE = writable_data_file("user_profiles.json", [])
NOTIFICATIONS_FILE = writable_data_file("notifications.json", [])
GIFT_EVENTS_FILE = writable_data_file("gift_events.json", [])

FORUM_SUBJECTS = [
    "Toán",
    "Ngữ Văn",
    "Tiếng Anh",
    "Vật Lý",
    "Hóa Học",
    "Sinh Học",
    "Lịch Sử",
    "Địa Lý",
    "GDCD",
    "Công Nghệ",
    "Tin Học",
]
ALLOWED_GRADE_LEVELS = ["6", "7", "8", "9"]
FORUM_GRADES = [f"Lớp {grade}" for grade in ALLOWED_GRADE_LEVELS]
FORUM_REPORT_REASONS = {
    "spam": "Tài khoản spam",
    "insult": "Lăng mạ/xúc phạm",
    "wrong_content": "Nội dung không phù hợp",
    "cheating": "Gian lận điểm thưởng",
    "other": "Khác",
}
FORUM_REPORT_STATUSES = {
    "pending": "Chờ xử lý",
    "resolved": "Đã xử lý",
    "rejected": "Bỏ qua",
}
FORUM_REWARD_LEVELS = [10, 20, 30, 40, 50, 60]
ONLINE_USERS = {}
ONLINE_WINDOW_SECONDS = 300
GIFT_CHECKIN_POINTS = 5
WELCOME_BONUS_POINTS = 50
GIFT_BOX_REWARDS = {
    "blue": {"name": "Hộp xanh", "threshold": 5, "points": 8},
    "gold": {"name": "Hộp vàng", "threshold": 10, "points": 15},
    "red": {"name": "Hộp đỏ", "threshold": 15, "points": 25},
}
DAILY_MATH_QUESTIONS = [
    {
        "id": "math_01",
        "question": "Tính giá trị của biểu thức: 3(2x - 1) khi x = 4.",
        "options": ["18", "21", "23", "24"],
        "answer": 1,
        "explanation": "Thay x = 4, ta có 3(8 - 1) = 21.",
    },
    {
        "id": "math_02",
        "question": "Cho tam giác có hai góc 55° và 65°. Góc còn lại bằng bao nhiêu?",
        "options": ["50°", "55°", "60°", "65°"],
        "answer": 2,
        "explanation": "Tổng ba góc tam giác là 180°, nên góc còn lại là 180° - 55° - 65° = 60°.",
    },
    {
        "id": "math_03",
        "question": "Giải phương trình: 2x + 7 = 19.",
        "options": ["x = 5", "x = 6", "x = 7", "x = 8"],
        "answer": 1,
        "explanation": "2x = 12 nên x = 6.",
    },
    {
        "id": "math_04",
        "question": "Rút gọn phân số 24/36 được kết quả nào?",
        "options": ["1/2", "2/3", "3/4", "4/5"],
        "answer": 1,
        "explanation": "Chia cả tử và mẫu cho 12, ta được 2/3.",
    },
    {
        "id": "math_05",
        "question": "Nếu hình vuông có cạnh 7 cm thì diện tích là bao nhiêu?",
        "options": ["14 cm²", "28 cm²", "49 cm²", "56 cm²"],
        "answer": 2,
        "explanation": "Diện tích hình vuông bằng cạnh nhân cạnh: 7 x 7 = 49 cm².",
    },
    {
        "id": "math_06",
        "question": "Số nào là nghiệm của bất phương trình x - 3 > 4?",
        "options": ["6", "7", "8", "4"],
        "answer": 2,
        "explanation": "x - 3 > 4 nên x > 7. Trong các đáp án, 8 phù hợp.",
    },
]


@app.after_request
def prevent_stale_html_cache(response):
    if response.content_type.startswith("text/html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.template_filter("strip_option_prefix")
def strip_option_prefix(value):
    text = str(value or "").strip()
    return re.sub(r"^[A-Da-d]\s*[\.\)]\s*", "", text, count=1).strip()


def normalize_choice_answer(value):
    text = str(value or "").strip()
    letter_match = re.match(r"^([A-Da-d])(?:\s*[\.\)]|\s*$)", text)
    if letter_match:
        return letter_match.group(1).upper()
    return strip_option_prefix(text).casefold()


def youtube_embed_url(url):
    text = str(url or "").strip()
    if not text:
        return ""

    patterns = [
        r"(?:https?:)?//(?:www\.)?youtube\.com/watch\?[^#]*v=([^&#]+)",
        r"(?:https?:)?//youtu\.be/([^?&#/]+)",
        r"(?:https?:)?//(?:www\.)?youtube\.com/embed/([^?&#/]+)",
        r"(?:https?:)?//(?:www\.)?youtube\.com/shorts/([^?&#/]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            video_id = match.group(1).strip()
            if re.match(r"^[A-Za-z0-9_-]{6,}$", video_id):
                return f"https://www.youtube.com/embed/{video_id}"
    return ""


@app.template_filter("youtube_embed_url")
def youtube_embed_url_filter(value):
    return youtube_embed_url(value)


def sanitize_course_payload(course_data):
    clean_data = dict(course_data or {})
    grade = str(clean_data.get("grade", "")).strip()
    clean_data["grade"] = grade if grade in ALLOWED_GRADE_LEVELS else ""
    lessons = []
    for index, lesson in enumerate(clean_data.get("lessons", []), start=1):
        clean_lesson = dict(lesson or {})
        clean_lesson["id"] = str(clean_lesson.get("id") or index)
        clean_lesson["video_url"] = youtube_embed_url(clean_lesson.get("video_url"))
        lessons.append(clean_lesson)
    clean_data["lessons"] = lessons
    return clean_data


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Vui lòng đăng nhập để tiếp tục", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Vui lòng đăng nhập", "warning")
            return redirect(url_for("login"))

        user = get_user_by_id(session["user_id"])
        if not user or user["role"] != "teacher":
            flash("Chỉ giáo viên mới có quyền truy cập trang này", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated_function


def is_admin_account(user=None):
    if user is None and "user_id" in session:
        user = get_user_by_id(session["user_id"])
    if not user:
        return False
    return user.get("role") == "admin"


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Vui lòng đăng nhập", "warning")
            return redirect(url_for("login"))

        user = get_user_by_id(session["user_id"])
        if not is_admin_account(user):
            flash("Chỉ quản trị viên mới có quyền truy cập trang này", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated_function


def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Vui lòng đăng nhập", "warning")
            return redirect(url_for("login"))

        user = get_user_by_id(session["user_id"])
        if not user or user.get("role") not in {"teacher", "admin"}:
            flash("Chỉ giáo viên hoặc quản trị viên mới có quyền gửi thông báo", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated_function


def notification_records():
    records = read_json(NOTIFICATIONS_FILE, [])
    return records if isinstance(records, list) else []


def save_notification_records(records):
    write_json(NOTIFICATIONS_FILE, records)


def notification_visible_to(notification, user):
    if not user:
        return False
    if notification.get("audience") == "all_students":
        return user.get("role") == "student"
    return notification.get("recipient_id") == user.get("id")


def user_notification_items(user_id):
    user = get_user_by_id(user_id)
    items = [
        dict(record)
        for record in notification_records()
        if notification_visible_to(record, user)
    ]
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    for item in items:
        read_by = item.get("read_by") or []
        item["is_read"] = user_id in read_by
        try:
            created = datetime.fromisoformat(item.get("created_at", ""))
            item["created_label"] = created.strftime("%d/%m/%Y %H:%M")
        except Exception:
            item["created_label"] = "-"
    return items


def unread_notifications_count(user_id):
    return len([item for item in user_notification_items(user_id) if not item.get("is_read")])


def mark_notifications_read(user_id):
    changed = False
    user = get_user_by_id(user_id)
    records = notification_records()
    for record in records:
        if not notification_visible_to(record, user):
            continue
        read_by = record.setdefault("read_by", [])
        if user_id not in read_by:
            read_by.append(user_id)
            changed = True
    if changed:
        save_notification_records(records)


@app.context_processor
def inject_admin_state():
    user_id = session.get("user_id")
    return {
        "is_admin_session": is_admin_account(),
        "notification_unread_count": unread_notifications_count(user_id) if user_id else 0,
    }


def next_notification_id(records):
    return f"notice_{len(records) + 1:05d}_{uuid.uuid4().hex[:6]}"


def gift_events():
    records = read_json(GIFT_EVENTS_FILE, [])
    return records if isinstance(records, list) else []


def save_gift_events(records):
    write_json(GIFT_EVENTS_FILE, records)


def gift_date_key(dt=None):
    return (dt or datetime.now()).strftime("%Y-%m-%d")


def gift_month_key(dt=None):
    return (dt or datetime.now()).strftime("%Y-%m")


def gift_attendance_streak(user_events, dt=None):
    today = (dt or datetime.now()).date()
    attendance_dates = set()
    for event in user_events:
        if event.get("type") != "attendance" or not event.get("date"):
            continue
        try:
            checked_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if checked_date <= today:
            attendance_dates.add(checked_date)

    if not attendance_dates:
        return 0

    latest_date = max(attendance_dates)
    if (today - latest_date).days > 1:
        return 0

    streak = 0
    cursor = latest_date
    while cursor in attendance_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def daily_math_question_for(user_id, date_key=None):
    date_key = date_key or gift_date_key()
    seed = sum(ord(ch) for ch in f"{user_id}:{date_key}")
    question = DAILY_MATH_QUESTIONS[seed % len(DAILY_MATH_QUESTIONS)]
    return {
        "id": question["id"],
        "question": question["question"],
        "options": question["options"],
    }


def gift_user_events(user_id):
    return [record for record in gift_events() if record.get("user_id") == user_id]


def gift_status_payload(user_id):
    date_key = gift_date_key()
    month_key = gift_month_key()
    user_events = gift_user_events(user_id)
    today_checkin = next(
        (event for event in user_events if event.get("type") == "attendance" and event.get("date") == date_key),
        None,
    )
    today_question = next(
        (event for event in user_events if event.get("type") == "daily_question" and event.get("date") == date_key),
        None,
    )
    attendance_count = gift_attendance_streak(user_events)
    opened_counts = {
        box_type: len(
            [
                event
                for event in user_events
                if event.get("type") == "gift_box"
                and event.get("month") == month_key
                and event.get("box_type") == box_type
            ]
        )
        for box_type in GIFT_BOX_REWARDS
    }
    boxes = []
    for box_type, config in GIFT_BOX_REWARDS.items():
        earned = attendance_count // config["threshold"]
        boxes.append(
            {
                "type": box_type,
                "name": config["name"],
                "points": config["points"],
                "count": max(0, earned - opened_counts.get(box_type, 0)),
            }
        )
    return {
        "date": date_key,
        "question": daily_math_question_for(user_id, date_key),
        "question_answered": bool(today_question),
        "question_correct": bool(today_question.get("is_correct")) if today_question else False,
        "question_points": int(today_question.get("points", 0)) if today_question else 0,
        "attendance_claimed": bool(today_checkin),
        "attendance_points": GIFT_CHECKIN_POINTS,
        "attendance_count": attendance_count,
        "attendance_days": [{"day": day, "claimed": day <= min(attendance_count, 15)} for day in range(1, 16)],
        "boxes": boxes,
    }


@app.before_request
def track_online_user():
    user_id = session.get("user_id")
    if not user_id:
        return

    now = datetime.now()
    user = get_user_by_id(user_id)
    ONLINE_USERS[user_id] = {
        "user_id": user_id,
        "username": session.get("username") or (user.get("username") if user else "Unknown"),
        "role": session.get("role") or (user.get("role") if user else "student"),
        "last_seen": now,
    }

    expired_at = now - timedelta(seconds=ONLINE_WINDOW_SECONDS)
    for active_user_id, active_user in list(ONLINE_USERS.items()):
        if active_user.get("last_seen", now) < expired_at:
            ONLINE_USERS.pop(active_user_id, None)


def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Vui lòng đăng nhập", "warning")
            return redirect(url_for("login"))

        user = get_user_by_id(session["user_id"])
        if not user or user["role"] != "student":
            flash("Chỉ học sinh mới có quyền truy cập trang này", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated_function


def build_home_stats():
    now = datetime.now()
    cached_value = _home_stats_cache.get("value")
    cached_expires_at = _home_stats_cache.get("expires_at")
    if cached_value and cached_expires_at and now < cached_expires_at:
        return cached_value

    users = load_users()
    courses = db.get_all_courses()
    documents = [
        doc
        for doc in db.get_all_documents()
        if doc.get("grade") in ALLOWED_GRADE_LEVELS
    ]
    forum_posts = db.get_all_forum_posts()
    forum_comments = db._load_json(db.forum_comments_file)
    submissions = db.get_all_submissions()
    progress_rows = db._load_json(db.progress_file)
    exam_results = [
        result
        for result in read_json(readable_data_file("exam_results.json"), [])
        if str(result.get("grade", "")) in ALLOWED_GRADE_LEVELS
    ]

    course_by_id = {course.get("id"): course for course in courses}
    latest_course = max(courses, key=lambda c: c.get("created_at", ""), default=None)
    total_lessons = sum(len(course.get("lessons", [])) for course in courses)

    completed_lessons = 0
    tracked_lessons = 0
    for row in progress_rows:
        course = course_by_id.get(row.get("course_id"))
        if not course:
            continue
        lesson_count = len(course.get("lessons", []))
        if lesson_count <= 0:
            continue
        tracked_lessons += lesson_count
        completed_lessons += min(len(row.get("completed_lessons", [])), lesson_count)

    progress_percent = (
        round((completed_lessons / tracked_lessons) * 100)
        if tracked_lessons
        else 0
    )

    exam_subject_codes = [
        "toan",
        "anh",
        "li",
        "hoa",
        "sinh",
        "su",
        "dia",
        "nguvan",
        "gdcd",
        "congnghe",
        "tinhoc",
    ]
    total_exams = 0
    for subject_code in exam_subject_codes:
        subject_data = read_json(readable_data_file(f"{subject_code}.json"), {"exams": []})
        total_exams += len(subject_data.get("exams", [])) if isinstance(subject_data, dict) else 0

    subject_counts = {}
    for post in forum_posts:
        subject = post.get("subject") or "Khác"
        subject_counts[subject] = subject_counts.get(subject, 0) + 1

    max_subject_count = max(subject_counts.values(), default=0)
    chart_items = [
        {
            "label": subject,
            "value": count,
            "percent": round((count / max_subject_count) * 100) if max_subject_count else 0,
        }
        for subject, count in sorted(
            subject_counts.items(), key=lambda item: item[1], reverse=True
        )[:5]
    ]

    stats = {
        "students": len([user for user in users if user.get("role") == "student"]),
        "teachers": len([user for user in users if user.get("role") == "teacher"]),
        "courses": len(courses),
        "documents": len(documents),
        "lessons": total_lessons,
        "forum_posts": len(forum_posts),
        "forum_answers": len(forum_comments),
        "resolved_posts": len([post for post in forum_posts if post.get("status") == "resolved"]),
        "submissions": len(submissions),
        "exam_attempts": len(exam_results),
        "exams": total_exams,
        "progress_percent": progress_percent,
        "latest_course_title": latest_course.get("title") if latest_course else "Chưa có khóa học",
        "latest_course_lessons": len(latest_course.get("lessons", [])) if latest_course else 0,
        "chart_items": chart_items,
    }
    _home_stats_cache["value"] = stats
    _home_stats_cache["expires_at"] = now + timedelta(seconds=HOME_STATS_CACHE_SECONDS)
    return stats


@app.route("/")
def index():
    if "user_id" in session:
        if session.get("role") == "admin":
            return redirect(url_for("admin_home"))
        elif session.get("role") == "teacher":
            return redirect(url_for("teacher_dashboard"))
        else:
            return redirect(url_for("student_dashboard"))

    home_stats = build_home_stats()

    return render_template("index.html", home_stats=home_stats)


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        email = request.form.get("email", "").strip()

        if not username or not password or not email:
            flash("Vui lòng điền đầy đủ thông tin", "danger")
            return render_template("register.html")

        result = register_user(username, password, email, role="student")

        if result["success"]:
            add_forum_points(
                result["user_id"],
                result.get("username", username),
                result.get("role", "student"),
                WELCOME_BONUS_POINTS,
                "welcome_bonus",
            )
            flash(f"Đăng ký thành công! Bạn được tặng {WELCOME_BONUS_POINTS} kim cương khi bắt đầu.", "success")
            return redirect(url_for("login"))
        else:
            flash(result["message"], "danger")
            return render_template("register.html")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        selected_role = request.form.get("role", "").strip()

        if not username or not password or selected_role not in {"student", "teacher", "admin"}:
            flash("Vui lòng nhập đầy đủ tài khoản, mật khẩu và vai trò", "danger")
            return render_template("login.html")

        result = login_user(username, password)

        if result["success"]:
            if result["role"] != selected_role:
                flash("Tài khoản này không thuộc vai trò bạn đã chọn", "danger")
                return render_template("login.html")

            session["user_id"] = result["user_id"]
            session["username"] = result["username"]
            session["role"] = result["role"]

            flash(f"Chào mừng {result['username']}!", "success")

            if result["role"] == "admin":
                return redirect(url_for("admin_home"))
            elif result["role"] == "teacher":
                return redirect(url_for("teacher_dashboard"))
            else:
                return redirect(url_for("student_dashboard"))
        else:
            flash(result["message"], "danger")
            return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
def logout():
    username = session.get("username", "Người dùng")
    session.clear()
    flash(f"Tạm biệt {username}!", "info")
    return redirect(url_for("index"))


@app.route("/notifications")
@login_required
def notifications_page():
    user_id = session["user_id"]
    notifications = user_notification_items(user_id)
    mark_notifications_read(user_id)
    return render_template(
        "notifications.html",
        notifications=notifications,
        username=session.get("username"),
    )


@app.route("/notifications/send", methods=["GET", "POST"])
@login_required
@staff_required
def send_notification():
    users = load_users()
    students = sorted(
        [user for user in users if user.get("role") == "student"],
        key=lambda user: user.get("username", "").lower(),
    )

    if request.method == "POST":
        recipient_id = (request.form.get("recipient_id") or "all").strip()
        title = (request.form.get("title") or "Thông báo mới").strip()
        content = (request.form.get("content") or "").strip()

        if not content:
            flash("Vui lòng nhập nội dung thông báo", "warning")
            return redirect(url_for("send_notification"))
        if len(title) > 120:
            flash("Tiêu đề tối đa 120 ký tự", "warning")
            return redirect(url_for("send_notification"))
        if len(content) > 2000:
            flash("Nội dung thông báo tối đa 2000 ký tự", "warning")
            return redirect(url_for("send_notification"))

        records = notification_records()
        now = datetime.now().isoformat()
        sender = get_user_by_id(session["user_id"])
        base_notice = {
            "id": next_notification_id(records),
            "title": title or "Thông báo mới",
            "content": content,
            "sender_id": session["user_id"],
            "sender_name": session.get("username", "Unknown"),
            "sender_role": sender.get("role", session.get("role", "teacher")) if sender else session.get("role", "teacher"),
            "created_at": now,
            "read_by": [],
        }

        if recipient_id == "all":
            notice = dict(base_notice)
            notice.update(
                {
                    "audience": "all_students",
                    "recipient_id": "",
                    "recipient_name": "Tất cả học sinh",
                    "recipient_count": len(students),
                }
            )
            records.append(notice)
            flash(f"Đã gửi thông báo cho {len(students)} học sinh", "success")
        else:
            recipient = next((student for student in students if student.get("id") == recipient_id), None)
            if not recipient:
                flash("Không tìm thấy học sinh cần gửi", "danger")
                return redirect(url_for("send_notification"))
            notice = dict(base_notice)
            notice.update(
                {
                    "audience": "student",
                    "recipient_id": recipient["id"],
                    "recipient_name": recipient.get("username", "Học sinh"),
                    "recipient_count": 1,
                }
            )
            records.append(notice)
            flash(f"Đã gửi thông báo cho {recipient.get('username', 'học sinh')}", "success")

        save_notification_records(records)
        return redirect(url_for("send_notification"))

    sent_notifications = [
        dict(record)
        for record in notification_records()
        if record.get("sender_id") == session["user_id"] or is_admin_account()
    ]
    sent_notifications.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    for notice in sent_notifications:
        try:
            notice["created_label"] = datetime.fromisoformat(notice.get("created_at", "")).strftime("%d/%m/%Y %H:%M")
        except Exception:
            notice["created_label"] = "-"
    return render_template(
        "send_notifications.html",
        students=students,
        sent_notifications=sent_notifications[:20],
        username=session.get("username"),
    )


@app.route("/api/gift/status")
@login_required
def gift_status():
    return jsonify({"success": True, **gift_status_payload(session["user_id"])})


@app.route("/api/gift/checkin", methods=["POST"])
@login_required
def gift_checkin():
    user_id = session["user_id"]
    date_key = gift_date_key()
    events = gift_events()
    if any(event.get("user_id") == user_id and event.get("type") == "attendance" and event.get("date") == date_key for event in events):
        return jsonify({"success": False, "message": "Hôm nay bạn đã điểm danh rồi", **gift_status_payload(user_id)})

    user = get_user_by_id(user_id)
    add_forum_points(
        user_id,
        session.get("username", "Unknown"),
        user.get("role", session.get("role", "student")) if user else session.get("role", "student"),
        GIFT_CHECKIN_POINTS,
        "daily_attendance",
    )
    events.append(
        {
            "id": f"gift_{len(events) + 1:06d}",
            "type": "attendance",
            "user_id": user_id,
            "username": session.get("username", "Unknown"),
            "date": date_key,
            "month": gift_month_key(),
            "points": GIFT_CHECKIN_POINTS,
            "created_at": datetime.now().isoformat(),
        }
    )
    save_gift_events(events)
    return jsonify({"success": True, "message": f"Điểm danh thành công, bạn nhận {GIFT_CHECKIN_POINTS} kim cương", **gift_status_payload(user_id)})


@app.route("/api/gift/question", methods=["POST"])
@login_required
def gift_question_submit():
    user_id = session["user_id"]
    date_key = gift_date_key()
    events = gift_events()
    if any(event.get("user_id") == user_id and event.get("type") == "daily_question" and event.get("date") == date_key for event in events):
        return jsonify({"success": False, "message": "Bạn đã trả lời câu hỏi vui hôm nay rồi"})

    payload = request.get_json(silent=True) or {}
    try:
        selected = int(payload.get("answer"))
    except (TypeError, ValueError):
        selected = -1

    public_question = daily_math_question_for(user_id, date_key)
    question = next(item for item in DAILY_MATH_QUESTIONS if item["id"] == public_question["id"])
    is_correct = selected == int(question["answer"])
    points = random.randint(5, 10) if is_correct else 0
    user = get_user_by_id(user_id)
    if points:
        add_forum_points(
            user_id,
            session.get("username", "Unknown"),
            user.get("role", session.get("role", "student")) if user else session.get("role", "student"),
            points,
            "daily_math_question",
        )
    events.append(
        {
            "id": f"gift_{len(events) + 1:06d}",
            "type": "daily_question",
            "user_id": user_id,
            "username": session.get("username", "Unknown"),
            "date": date_key,
            "month": gift_month_key(),
            "question_id": question["id"],
            "selected_answer": selected,
            "is_correct": is_correct,
            "points": points,
            "created_at": datetime.now().isoformat(),
        }
    )
    save_gift_events(events)
    message = f"Chính xác! Bạn nhận {points} kim cương." if is_correct else f"Chưa đúng. {question['explanation']}"
    return jsonify({"success": True, "correct": is_correct, "points": points, "message": message, "explanation": question["explanation"], **gift_status_payload(user_id)})


@app.route("/api/gift/open", methods=["POST"])
@login_required
def gift_open_box():
    payload = request.get_json(silent=True) or {}
    box_type = (payload.get("box_type") or "").strip()
    if box_type not in GIFT_BOX_REWARDS:
        return jsonify({"success": False, "message": "Hộp quà không hợp lệ"}), 400

    status = gift_status_payload(session["user_id"])
    box = next((item for item in status["boxes"] if item["type"] == box_type), None)
    if not box or int(box.get("count", 0)) <= 0:
        return jsonify({"success": False, "message": "Bạn chưa có hộp quà này để mở"})

    points = int(GIFT_BOX_REWARDS[box_type]["points"])
    user = get_user_by_id(session["user_id"])
    add_forum_points(
        session["user_id"],
        session.get("username", "Unknown"),
        user.get("role", session.get("role", "student")) if user else session.get("role", "student"),
        points,
        "gift_box_open",
    )
    events = gift_events()
    events.append(
        {
            "id": f"gift_{len(events) + 1:06d}",
            "type": "gift_box",
            "box_type": box_type,
            "user_id": session["user_id"],
            "username": session.get("username", "Unknown"),
            "date": gift_date_key(),
            "month": gift_month_key(),
            "points": points,
            "created_at": datetime.now().isoformat(),
        }
    )
    save_gift_events(events)
    return jsonify({"success": True, "message": f"Bạn mở {GIFT_BOX_REWARDS[box_type]['name']} và nhận {points} kim cương", **gift_status_payload(session["user_id"])})


@app.route("/student/dashboard")
@login_required
@student_required
def student_dashboard():
    courses = db.get_all_courses()
    my_progress = db.get_student_progress(session["user_id"])

    enrolled_courses = []
    for progress in my_progress:
        course = db.get_course_by_id(progress["course_id"])
        if course:
            total_lessons = len(course.get("lessons", []))
            completed_lessons = len(progress.get("completed_lessons", []))
            percentage = (
                (completed_lessons / total_lessons * 100) if total_lessons > 0 else 0
            )

            enrolled_courses.append(
                {
                    "course": course,
                    "progress": progress,
                    "percentage": round(percentage, 1),
                }
            )

    return render_template(
        "student_dashboard.html",
        courses=courses,
        enrolled_courses=enrolled_courses,
        username=session.get("username"),
    )


@app.route("/teacher/dashboard")
@login_required
@teacher_required
def teacher_dashboard():
    my_courses = db.get_courses_by_teacher(session["user_id"])

    course_stats = []
    for course in my_courses:
        all_progress = db._load_json(db.progress_file)
        students_enrolled = len(
            [p for p in all_progress if p["course_id"] == course["id"]]
        )

        course_stats.append(
            {
                "course": course,
                "students_enrolled": students_enrolled,
                "total_lessons": len(course.get("lessons", [])),
            }
        )

    return render_template(
        "teacher_dashboard.html", courses=course_stats, username=session.get("username")
    )


@app.route("/courses")
@login_required
def courses():
    all_courses = db.get_all_courses()

    courses_with_teacher = []
    for course in all_courses:
        teacher = get_user_by_id(course["teacher_id"])
        course["teacher_name"] = teacher["username"] if teacher else "Unknown"
        courses_with_teacher.append(course)

    return render_template("courses.html", courses=courses_with_teacher)


@app.route("/course/<course_id>")
@login_required
def course_detail(course_id):
    course = db.get_course_by_id(course_id)

    if not course:
        flash("Khóa học không tồn tại", "danger")
        return redirect(url_for("courses"))

    teacher = get_user_by_id(course["teacher_id"])
    course["teacher_name"] = teacher["username"] if teacher else "Unknown"

    progress = db.get_course_progress(session["user_id"], course_id)
    completed_lessons = progress["completed_lessons"] if progress else []

    is_teacher = (
        session.get("role") == "teacher" and course["teacher_id"] == session["user_id"]
    )

    return render_template(
        "course_detail.html",
        course=course,
        completed_lessons=completed_lessons,
        is_teacher=is_teacher,
    )


@app.route("/teacher/create_course", methods=["GET", "POST"])
@teacher_required
def create_course():
    if request.method == "POST":
        try:
            data = sanitize_course_payload(request.get_json())

            if not data.get("title"):
                return jsonify(
                    {"success": False, "message": "Vui lòng nhập tên khóa học"}
                )

            if not data.get("grade"):
                return jsonify(
                    {"success": False, "message": "Vui lòng chọn lớp 6, 7, 8 hoặc 9"}
                )

            all_courses = db.get_all_courses()
            if any(
                c["title"].lower() == data["title"].lower()
                and c["teacher_id"] == session["user_id"]
                for c in all_courses
            ):
                return jsonify(
                    {"success": False, "message": "Bạn đã có khóa học trùng tên này"}
                )

            course_id = db.create_course(data, session["user_id"])

            return jsonify(
                {
                    "success": True,
                    "course_id": course_id,
                    "message": "Tạo khóa học thành công",
                }
            )

        except Exception as e:
            return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

    return render_template("create_course.html")


@app.route("/teacher/edit_course/<course_id>", methods=["GET", "POST"])
@teacher_required
def edit_course(course_id):
    course = db.get_course_by_id(course_id)

    if not course:
        flash("Khóa học không tồn tại", "danger")
        return redirect(url_for("teacher_dashboard"))

    if course["teacher_id"] != session["user_id"]:
        flash("Bạn không có quyền chỉnh sửa khóa học này", "danger")
        return redirect(url_for("teacher_dashboard"))

    if request.method == "POST":
        try:
            data = sanitize_course_payload(request.get_json())
            if not data.get("grade"):
                return jsonify(
                    {"success": False, "message": "Vui lòng chọn lớp 6, 7, 8 hoặc 9"}
                )

            success = db.update_course(course_id, data)

            if success:
                return jsonify(
                    {"success": True, "message": "Cập nhật khóa học thành công"}
                )
            else:
                return jsonify({"success": False, "message": "Cập nhật thất bại"})

        except Exception as e:
            return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

    return render_template("create_course.html", course=course, edit_mode=True)


@app.route("/teacher/delete_course/<course_id>", methods=["POST"])
@teacher_required
def delete_course(course_id):
    course = db.get_course_by_id(course_id)

    if not course:
        return jsonify({"success": False, "message": "Khóa học không tồn tại"})

    if course["teacher_id"] != session["user_id"]:
        return jsonify(
            {"success": False, "message": "Bạn không có quyền xóa khóa học này"}
        )

    courses = db.get_all_courses()
    courses = [c for c in courses if c["id"] != course_id]
    db._save_json(db.courses_file, courses)

    return jsonify({"success": True, "message": "Xóa khóa học thành công"})


@app.route("/exercises")
@login_required
def exercises():
    all_courses = db.get_all_courses()

    exercises_list = []
    for course in all_courses:
        for lesson in course.get("lessons", []):
            questions = lesson.get("questions", [])
            if questions:
                exercises_list.append(
                    {
                        "course_id": course["id"],
                        "course_title": course["title"],
                        "lesson_id": lesson["id"],
                        "lesson_title": lesson["title"],
                        "questions": questions,
                    }
                )

    try:
        all_submissions = (
            db._load_json(db.submissions_file)
            if hasattr(db, "submissions_file")
            else []
        )
    except:
        all_submissions = []

    my_submissions = [
        s for s in all_submissions if s.get("user_id") == session["user_id"]
    ]

    return render_template(
        "exercises.html", exercises=exercises_list, submissions=my_submissions
    )


@app.route("/submit_exercise", methods=["POST"])
@login_required
def submit_exercise():
    try:
        data = request.get_json()

        if (
            not data.get("course_id")
            or not data.get("lesson_id")
            or not data.get("answers")
        ):
            return jsonify({"success": False, "message": "Dữ liệu không đầy đủ"})

        submission_data = {
            "course_id": data["course_id"],
            "exercise_id": data["lesson_id"],
            "answers": data["answers"],
            "submitted_at": datetime.now().isoformat(),
        }

        submission_id = db.save_exercise_submission(session["user_id"], submission_data)

        course = db.get_course_by_id(data["course_id"])
        if course:
            lesson = next(
                (l for l in course.get("lessons", []) if l["id"] == data["lesson_id"]),
                None,
            )
            if lesson:
                questions = lesson.get("questions", [])
                correct = 0
                total = len(questions)

                for i, q in enumerate(questions):
                    user_answer = data["answers"].get(str(i), "").strip()
                    correct_answer = q.get("correct_answer", "").strip()

                    if user_answer and correct_answer:
                        if normalize_choice_answer(user_answer) == normalize_choice_answer(correct_answer):
                            correct += 1

                score = round((correct / total * 100) if total > 0 else 0, 1)

                return jsonify(
                    {
                        "success": True,
                        "submission_id": submission_id,
                        "score": score,
                        "correct": correct,
                        "total": total,
                        "message": "Nộp bài thành công",
                    }
                )

        return jsonify(
            {
                "success": True,
                "submission_id": submission_id,
                "message": "Nộp bài thành công",
            }
        )

    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})


###############


@app.route("/documents")
@login_required
def documents():
    # Lấy các tham số lọc từ query string
    grade_filter = request.args.get("grade", "all")  # 6, 7, 8, 9, hoặc all
    type_filter = request.args.get("type", "all")  # document, lecture, exam, hoặc all

    docs = db.get_all_documents()
    docs = [d for d in docs if d.get("grade") in ALLOWED_GRADE_LEVELS]

    if grade_filter != "all" and grade_filter not in ALLOWED_GRADE_LEVELS:
        grade_filter = "all"

    if grade_filter != "all":
        docs = [d for d in docs if d.get("grade") == grade_filter]
    if type_filter != "all":
        docs = [d for d in docs if d.get("doc_type") == type_filter]

    docs_by_grade = {
        grade: [d for d in docs if d.get("grade") == grade]
        for grade in ALLOWED_GRADE_LEVELS
    }

    return render_template(
        "documents.html",
        docs_by_grade=docs_by_grade,
        current_grade=grade_filter,
        current_type=type_filter,
    )


############
@app.route("/teacher/delete_document/<doc_id>", methods=["POST"])
@teacher_required
def delete_document(doc_id):
    """
    Xóa tài liệu - chỉ giáo viên mới có quyền xóa
    """
    try:
        docs = db.get_all_documents()
        doc = next((d for d in docs if d["id"] == doc_id), None)

        if not doc:
            return jsonify({"success": False, "message": "Tài liệu không tồn tại"})

        # Kiểm tra quyền: chỉ giáo viên tạo tài liệu mới được xóa
        if doc.get("teacher_id") != session["user_id"]:
            return jsonify(
                {"success": False, "message": "Bạn không có quyền xóa tài liệu này"}
            )

        # Xóa file đính kèm nếu có (nếu bạn lưu file local)
        if doc.get("attachments"):
            for attachment in doc.get("attachments", []):
                try:
                    attachment_path = attachment_storage_path(attachment)
                    if attachment_path.exists():
                        attachment_path.unlink()
                except:
                    pass

        # Xóa tài liệu khỏi database
        docs = [d for d in docs if d["id"] != doc_id]
        db._save_json(db.documents_file, docs)

        return jsonify({"success": True, "message": "Xóa tài liệu thành công"})

    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})


################
@app.route("/teacher/add_document", methods=["GET", "POST"])
@teacher_required
def add_document():
    if request.method == "POST":
        try:
            data = request.get_json()

            if not data.get("title") or not data.get("url"):
                return jsonify(
                    {"success": False, "message": "Vui lòng nhập đầy đủ thông tin"}
                )

            if not data.get("grade"):
                return jsonify({"success": False, "message": "Vui lòng chọn lớp học"})

            if not data.get("doc_type"):
                return jsonify(
                    {"success": False, "message": "Vui lòng chọn loại tài liệu"}
                )

            if "youtube.com" in data["url"] or "youtu.be" in data["url"]:
                data["link_type"] = "youtube"
            elif "drive.google.com" in data["url"]:
                data["link_type"] = "drive"
            else:
                data["link_type"] = data.get("link_type", "other")

            data["teacher_id"] = session["user_id"]

            doc_id = db.add_document(data)

            return jsonify(
                {
                    "success": True,
                    "doc_id": doc_id,
                    "message": "Thêm tài liệu thành công",
                }
            )

        except Exception as e:
            return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

    return render_template("add_document.html")


@app.route("/teacher/edit_document/<doc_id>", methods=["GET", "POST"])
@teacher_required
def edit_document(doc_id):
    """Chỉnh sửa tài liệu"""
    doc = db.get_document_by_id(doc_id)

    if not doc:
        flash("Tài liệu không tồn tại", "danger")
        return redirect(url_for("documents"))

    if doc.get("teacher_id") != session["user_id"]:
        flash("Bạn không có quyền chỉnh sửa tài liệu này", "danger")
        return redirect(url_for("documents"))

    if request.method == "POST":
        try:
            data = request.get_json()

            # Tự động nhận diện link_type nếu để auto
            if data.get("link_type") == "auto" or not data.get("link_type"):
                url = data.get("url", "")
                if "youtube.com" in url or "youtu.be" in url:
                    data["link_type"] = "youtube"
                elif "drive.google.com" in url:
                    data["link_type"] = "drive"
                else:
                    data["link_type"] = "other"

            success = db.update_document(doc_id, data)

            if success:
                return jsonify(
                    {"success": True, "message": "Cập nhật tài liệu thành công"}
                )
            else:
                return jsonify({"success": False, "message": "Cập nhật thất bại"})

        except Exception as e:
            return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

    return render_template("add_document.html", doc=doc, edit_mode=True)


#################################


@app.route("/update_progress", methods=["POST"])
@login_required
def update_progress():
    try:
        data = request.get_json()

        if not data.get("course_id") or not data.get("lesson_id"):
            return jsonify({"success": False, "message": "Dữ liệu không đầy đủ"})

        db.update_progress(
            session["user_id"],
            data["course_id"],
            data["lesson_id"],
            data.get("completed", True),
            timestamp=datetime.now().isoformat(),
        )

        return jsonify({"success": True, "message": "Cập nhật tiến độ thành công"})

    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})


@app.route("/teacher/students_progress")
@teacher_required
def students_progress():
    teacher_courses = db.get_courses_by_teacher(session["user_id"])
    teacher_course_ids = [c["id"] for c in teacher_courses]

    all_progress = db._load_json(db.progress_file)
    filtered_progress = [
        p for p in all_progress if p["course_id"] in teacher_course_ids
    ]

    progress_with_details = []
    for prog in filtered_progress:
        student = get_user_by_id(prog["user_id"])
        course = db.get_course_by_id(prog["course_id"])

        if student and course:
            total_lessons = len(course.get("lessons", []))
            completed = len(prog.get("completed_lessons", []))
            percentage = round(
                (completed / total_lessons * 100) if total_lessons > 0 else 0, 1
            )

            progress_with_details.append(
                {
                    "student_name": student["username"],
                    "student_email": student.get("email", ""),
                    "course_title": course["title"],
                    "completed": completed,
                    "total": total_lessons,
                    "percentage": percentage,
                    "last_updated": prog.get("last_updated", "Chưa cập nhật"),
                }
            )

    return render_template("student_progress.html", progress=progress_with_details)


@app.route("/teacher/view_submissions")
@teacher_required
def view_submissions():
    teacher_courses = db.get_courses_by_teacher(session["user_id"])
    teacher_course_ids = [c["id"] for c in teacher_courses]

    try:
        all_submissions = (
            db._load_json(db.submissions_file)
            if hasattr(db, "submissions_file")
            else []
        )
    except:
        all_submissions = []

    filtered_submissions = [
        s for s in all_submissions if s.get("course_id") in teacher_course_ids
    ]

    submissions_with_details = []
    for sub in filtered_submissions:
        student = get_user_by_id(sub["user_id"])
        course = db.get_course_by_id(sub.get("course_id"))

        if student and course:
            submissions_with_details.append(
                {
                    "student_name": student["username"],
                    "course_title": course["title"],
                    "exercise_id": sub.get("exercise_id"),
                    "answers": sub.get("answers", {}),
                    "submitted_at": sub.get("submitted_at", "Không rõ"),
                }
            )

    return render_template(
        "view_submissions.html", submissions=submissions_with_details
    )


@app.route("/api/course/<course_id>")
@login_required
def api_get_course(course_id):
    course = db.get_course_by_id(course_id)
    if course:
        return jsonify({"success": True, "course": course})
    return jsonify({"success": False, "error": "Course not found"}), 404


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("500.html"), 500


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
    "toan": {"name": "Toán", "icon": "🔢", "color": "#3498db"},
    "anh": {"name": "Tiếng Anh", "icon": "🇬🇧", "color": "#e74c3c"},
    "li": {"name": "Vật Lý", "icon": "⚡", "color": "#9b59b6"},
    "hoa": {"name": "Hóa Học", "icon": "🧪", "color": "#1abc9c"},
    "sinh": {"name": "Sinh Học", "icon": "🧬", "color": "#2ecc71"},
    "su": {"name": "Lịch Sử", "icon": "📜", "color": "#f39c12"},
    "dia": {"name": "Địa Lý", "icon": "🌍", "color": "#16a085"},
    "nguvan": {"name": "Ngữ Văn", "icon": "📖", "color": "#c0392b"},
    "gdcd": {"name": "GDCD", "icon": "⚖️", "color": "#8e44ad"},
    "congnghe": {"name": "Công Nghệ", "icon": "🔧", "color": "#34495e"},
    "tinhoc": {"name": "Tin Học", "icon": "💻", "color": "#2c3e50"},
}


def validate_subject(subject):
    """Kiểm tra môn học hợp lệ"""
    return subject in SUBJECTS


def _load_subject_exam_data(subject):
    json_file = readable_data_file(f"{subject}.json")
    data = read_json(json_file, {"exams": []})
    if not isinstance(data, dict):
        data = {"exams": []}
    if not isinstance(data.get("exams"), list):
        data["exams"] = []
    return data


def _save_subject_exam_data(subject, data):
    json_file = writable_data_file(f"{subject}.json")
    write_json(json_file, data)


def _generate_exam_id(subject, existing_exams):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    base_id = f"exam_{subject}_{timestamp}"
    existing_ids = {exam.get("id") for exam in existing_exams}
    exam_id = base_id
    suffix = 1
    while exam_id in existing_ids:
        suffix += 1
        exam_id = f"{base_id}_{suffix}"
    return exam_id


def _normalize_teacher_exam_payload(payload):
    subject = (payload.get("subject") or "").strip()
    if not validate_subject(subject):
        raise ValueError("Môn học không hợp lệ")

    title = (payload.get("title") or "").strip()
    if not title:
        raise ValueError("Vui lòng nhập tên đề")

    try:
        time_limit = int(payload.get("time_limit") or 30)
    except (TypeError, ValueError):
        time_limit = 30
    time_limit = max(5, min(time_limit, 180))

    questions = payload.get("questions") or []
    if not isinstance(questions, list) or not questions:
        raise ValueError("Đề phải có ít nhất 1 câu hỏi")
    if len(questions) > 60:
        raise ValueError("Mỗi đề tối đa 60 câu hỏi")

    normalized_questions = []
    for index, question in enumerate(questions, 1):
        question_text = (question.get("question") or "").strip()
        options = question.get("options") or {}
        correct_answer = (question.get("correct_answer") or "").strip().upper()

        if not question_text:
            raise ValueError(f"Câu {index} chưa có nội dung")

        normalized_options = {
            letter: str(options.get(letter, "")).strip()
            for letter in ("A", "B", "C", "D")
        }
        if not all(normalized_options.values()):
            raise ValueError(f"Câu {index} phải có đủ lựa chọn A, B, C, D")
        if correct_answer not in normalized_options:
            raise ValueError(f"Câu {index} phải chọn đáp án đúng A/B/C/D")

        normalized_questions.append(
            {
                "id": index,
                "number": index,
                "question": question_text,
                "options": normalized_options,
                "correct_answer": correct_answer,
                "explanation": (question.get("explanation") or "").strip(),
            }
        )

    return subject, {
        "title": title,
        "time_limit": time_limit,
        "description": (payload.get("description") or "").strip(),
        "questions": normalized_questions,
        "created_by": session.get("user_id"),
        "created_at": datetime.now().isoformat(),
    }


# ============================================================================
# ROUTE 1: Trang chọn đề thi - ĐÃ CẬP NHẬT CHO 10 MÔN
# ============================================================================
@app.route("/tracnghiem")
@login_required
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
            json_file = readable_data_file(f"{subject_code}.json")
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    exams_data = json.load(f)
                    exams = exams_data.get("exams", [])

                    for exam in exams:
                        exam["subject"] = subject_code
                        exam["subject_name"] = subject_info["name"]
                        exam["subject_icon"] = subject_info["icon"]
                        exam["subject_color"] = subject_info["color"]

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
                e for e in all_exams if e["subject"] == subject_code
            ]

        print(f"Total exams: {len(all_exams)}")
        for subject_code, subject_info in SUBJECTS.items():
            count = len(exams_by_subject[subject_code])
            print(f"{subject_info['name']}: {count} đề")

        return render_template(
            "tracnghiem.html",
            exams_by_subject=exams_by_subject,
            subjects=SUBJECTS,
            username=session.get("username"),
        )

    except Exception as e:
        print(f"ERROR in tracnghiem route: {str(e)}")
        import traceback

        traceback.print_exc()
        flash(f"Lỗi khi tải danh sách đề thi: {str(e)}", "danger")
        return redirect(url_for("student_dashboard"))


@app.route("/teacher/exams")
@login_required
@teacher_required
def teacher_exams():
    exams_by_subject = {}
    for subject_code, subject_info in SUBJECTS.items():
        data = _load_subject_exam_data(subject_code)
        exams = data.get("exams", [])
        for exam in exams:
            exam["subject"] = subject_code
            exam["subject_name"] = subject_info["name"]
        exams_by_subject[subject_code] = exams

    return render_template(
        "teacher_exams.html",
        subjects=SUBJECTS,
        exams_by_subject=exams_by_subject,
        username=session.get("username"),
    )


@app.route("/teacher/exams/create", methods=["POST"])
@login_required
@teacher_required
def teacher_create_exam():
    try:
        payload = request.get_json() or {}
        subject, exam_data = _normalize_teacher_exam_payload(payload)

        data = _load_subject_exam_data(subject)
        exam_data["id"] = _generate_exam_id(subject, data.get("exams", []))
        data["exams"].append(exam_data)
        _save_subject_exam_data(subject, data)

        return jsonify(
            {
                "success": True,
                "message": "Đã tạo đề trắc nghiệm",
                "exam": exam_data,
                "subject": subject,
                "url": url_for(
                    "lam_bai_tracnghiem", subject=subject, exam_id=exam_data["id"]
                ),
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/teacher/exams/ai-generate", methods=["POST"])
@login_required
@teacher_required
def teacher_ai_generate_exam():
    try:
        payload = request.get_json() or {}
        subject = (payload.get("subject") or "").strip()
        if not validate_subject(subject):
            return jsonify({"success": False, "message": "Môn học không hợp lệ"}), 400

        topic = (payload.get("topic") or "").strip()
        if not topic:
            return jsonify({"success": False, "message": "Vui lòng nhập yêu cầu cho AI"}), 400

        question_count = int(payload.get("question_count") or 10)
        time_limit = int(payload.get("time_limit") or 30)
        grade = (payload.get("grade") or "").strip()
        if grade and grade not in ALLOWED_GRADE_LEVELS:
            return jsonify({"success": False, "message": "Chỉ hỗ trợ tạo đề cho lớp 6, 7, 8, 9"}), 400
        subject_name = SUBJECTS[subject]["name"]

        exam = generate_teacher_exam(
            subject_name=subject_name,
            topic=topic,
            question_count=question_count,
            grade=grade,
            time_limit=time_limit,
        )
        exam["subject"] = subject

        return jsonify({"success": True, "exam": exam})
    except Exception as e:
        print(f"Lỗi AI tạo đề: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/teacher/exams/delete", methods=["POST"])
@login_required
@teacher_required
def teacher_delete_exam():
    try:
        payload = request.get_json() or {}
        subject = (payload.get("subject") or "").strip()
        exam_id = (payload.get("exam_id") or "").strip()
        if not validate_subject(subject) or not exam_id:
            return jsonify({"success": False, "message": "Dữ liệu không hợp lệ"}), 400

        data = _load_subject_exam_data(subject)
        before_count = len(data.get("exams", []))
        data["exams"] = [exam for exam in data.get("exams", []) if exam.get("id") != exam_id]
        if len(data["exams"]) == before_count:
            return jsonify({"success": False, "message": "Không tìm thấy đề cần xóa"}), 404

        _save_subject_exam_data(subject, data)
        return jsonify({"success": True, "message": "Đã xóa đề"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================================
# ROUTE 2: Trang làm bài thi - ĐÃ CẬP NHẬT
# ============================================================================
@app.route("/tracnghiem/lam-bai/<subject>/<exam_id>")
@login_required
def lam_bai_tracnghiem(subject, exam_id):
    """
    Hiển thị đề trắc nghiệm để học sinh làm bài
    ĐÃ CẬP NHẬT: Hỗ trợ 10 môn học
    """
    # Validate môn học (10 môn)
    if not validate_subject(subject):
        flash(" Môn học không hợp lệ", "danger")
        return redirect(url_for("tracnghiem"))

    subject_info = SUBJECTS[subject]
    json_file = readable_data_file(f"{subject}.json")

    try:
        with open(json_file, "r", encoding="utf-8") as f:
            exams_data = json.load(f)
            exams = exams_data.get("exams", [])

            exam = next((e for e in exams if e["id"] == exam_id), None)

            if not exam:
                flash("Đề thi không tồn tại", "danger")
                return redirect(url_for("tracnghiem"))

            time_limit = exam.get("time_limit", 15)

            if not isinstance(time_limit, (int, float)) or time_limit <= 0:
                time_limit = 15
                print(
                    f"Warning: Invalid time_limit in exam {exam_id}, using default 15 minutes"
                )

            session_key = f"exam_start_{subject}_{exam_id}"
            reset_param = request.args.get("reset", "no")

            if not session.permanent:
                session.permanent = True
                session.modified = True

            should_create_new_session = False
            remaining_time = time_limit * 60

            if reset_param == "yes":
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
                            flash(
                                " Đã hết thời gian làm bài! Vui lòng làm lại từ đầu.",
                                "warning",
                            )
                            session.pop(session_key, None)
                            session.modified = True
                            return redirect(url_for("tracnghiem"))

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
                print(
                    f"Created new session for exam {exam_id}, expires in {time_limit} minutes"
                )

            remaining_time = max(1, min(remaining_time, time_limit * 60))
            remaining_time = int(remaining_time)

            print(f"""
            ===== EXAM SESSION INFO =====
            Exam: {exam_id} | Subject: {subject}
            Time Limit: {time_limit} minutes
            Remaining: {remaining_time} seconds ({remaining_time // 60}m {remaining_time % 60}s)
            Session Key: {session_key}
            Session Permanent: {session.permanent}
            ============================
            """)

            return render_template(
                "baitap.html",
                exam=exam,
                subject=subject,
                subject_name=subject_info["name"],
                subject_icon=subject_info["icon"],
                subject_color=subject_info["color"],
                time_limit=time_limit,
                remaining_time=remaining_time,
                username=session.get("username"),
            )

    except FileNotFoundError:
        flash("⚠️ Không tìm thấy dữ liệu đề thi", "danger")
        return redirect(url_for("tracnghiem"))

    except json.JSONDecodeError as e:
        flash("⚠️ Dữ liệu đề thi bị lỗi định dạng", "danger")
        print(f"JSON decode error: {e}")
        return redirect(url_for("tracnghiem"))

    except Exception as e:
        flash(f"⚠️ Lỗi không xác định: {str(e)}", "danger")
        print(f"Unexpected error in lam_bai_tracnghiem: {e}")
        import traceback

        traceback.print_exc()
        return redirect(url_for("tracnghiem"))


# ============================================================================
# ROUTE 3: API kiểm tra thời gian - ĐÃ CẬP NHẬT
# ============================================================================
@app.route("/api/tracnghiem/check-time/<subject>/<exam_id>")
@login_required
def api_check_exam_time(subject, exam_id):
    """
    API kiểm tra thời gian còn lại - Hỗ trợ 10 môn
    """
    if not validate_subject(subject):
        return jsonify(
            {
                "success": False,
                "message": "Môn học không hợp lệ",
                "is_expired": True,
                "remaining_time": 0,
            }
        )

    session_key = f"exam_start_{subject}_{exam_id}"

    if session_key not in session:
        return jsonify(
            {
                "success": False,
                "message": "Session không tồn tại",
                "is_expired": True,
                "remaining_time": 0,
            }
        )

    try:
        json_file = readable_data_file(f"{subject}.json")
        with open(json_file, "r", encoding="utf-8") as f:
            exams_data = json.load(f)
            exams = exams_data.get("exams", [])
            exam = next((e for e in exams if e["id"] == exam_id), None)

            if not exam:
                return jsonify(
                    {
                        "success": False,
                        "message": "Đề thi không tồn tại",
                        "is_expired": True,
                        "remaining_time": 0,
                    }
                )

            time_limit = exam.get("time_limit", 15)

        start_time = datetime.fromisoformat(session[session_key])
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        remaining_seconds = (time_limit * 60) - elapsed_seconds

        if remaining_seconds <= 0:
            session.pop(session_key, None)
            session.modified = True

            return jsonify(
                {
                    "success": True,
                    "remaining_time": 0,
                    "is_expired": True,
                    "message": "Hết thời gian",
                }
            )

        return jsonify(
            {
                "success": True,
                "remaining_time": int(remaining_seconds),
                "is_expired": False,
                "time_limit_minutes": time_limit,
            }
        )

    except (ValueError, KeyError, TypeError) as e:
        print(f"Error in api_check_exam_time: {e}")
        return jsonify(
            {
                "success": False,
                "message": f"Lỗi session: {str(e)}",
                "is_expired": True,
                "remaining_time": 0,
            }
        )

    except Exception as e:
        print(f"Unexpected error in api_check_exam_time: {e}")
        return jsonify(
            {
                "success": False,
                "message": f"Lỗi: {str(e)}",
                "is_expired": True,
                "remaining_time": 0,
            }
        )


# ============================================================================
# ROUTE 4: Nộp bài thi -  ĐÃ TÍCH HỢP AI GEMINI
# ============================================================================
@app.route("/tracnghiem/nop-bai", methods=["POST"])
@login_required
def nop_bai_tracnghiem():
    """
    Nộp bài - Hỗ trợ cả trắc nghiệm và tự luận
    Điểm tổng luôn quy về thang 10
    ⭐ ĐÃ TÍCH HỢP AI PHÂN TÍCH ⭐
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify(
                {"success": False, "message": "Không nhận được dữ liệu"}
            ), 400

        subject = data.get("subject")
        exam_id = data.get("exam_id")
        answers = data.get("answers", {})  # Câu trắc nghiệm
        essays = data.get("essays", {})  # Câu tự luận (nếu có)

        # Validate
        if not subject or not exam_id:
            return jsonify({"success": False, "message": "Thiếu thông tin đề thi"}), 400

        if not validate_subject(subject):
            return jsonify({"success": False, "message": "Môn học không hợp lệ"}), 400

        # Kiểm tra session
        session_key = f"exam_start_{subject}_{exam_id}"
        if session_key not in session:
            return jsonify({"success": False, "message": "⚠️ Session đã hết hạn"}), 403

        # Load đề thi
        json_file = readable_data_file(f"{subject}.json")
        with open(json_file, "r", encoding="utf-8") as f:
            exams_data = json.load(f)
            exam = next(
                (e for e in exams_data.get("exams", []) if e["id"] == exam_id), None
            )

        if not exam:
            return jsonify({"success": False, "message": "Không tìm thấy đề thi"}), 404

        # Kiểm tra thời gian
        time_limit = exam.get("time_limit", 15)
        try:
            start_time = datetime.fromisoformat(session[session_key])
            elapsed_seconds = (datetime.now() - start_time).total_seconds()

            if elapsed_seconds > (time_limit * 60):
                session.pop(session_key, None)
                return jsonify({"success": False, "message": "⏰ Hết thời gian!"}), 403
        except:
            return jsonify({"success": False, "message": "Session không hợp lệ"}), 403

        # ========== LẤY CẤU HÌNH CHẤM ĐIỂM ==========
        scoring_config = exam.get("scoring_config", {})

        # Nếu không có scoring_config, mặc định 100% trắc nghiệm
        if not scoring_config:
            scoring_config = {"multiple_choice": {"weight_percent": 100, "points": 10}}

        mc_weight = (
            scoring_config.get("multiple_choice", {}).get("weight_percent", 100) / 100
        )
        essay_weight = scoring_config.get("essay", {}).get("weight_percent", 0) / 100

        # ========== KẾT QUẢ ==========
        result = {
            "multiple_choice": None,
            "essay": None,
            "total_score": 0,
            "wrong_answers": [],
        }

        # ========== CHẤM PHẦN TRẮC NGHIỆM ==========
        sections = exam.get("sections", [])

        # Nếu đề không có sections (đề cũ), dùng questions trực tiếp
        if not sections and exam.get("questions"):
            sections = [
                {"type": "multiple_choice", "questions": exam.get("questions", [])}
            ]

        mc_section = next((s for s in sections if s["type"] == "multiple_choice"), None)

        if mc_section:
            mc_questions = mc_section.get("questions", [])
            correct_count = 0

            for q in mc_questions:
                q_id = str(q["id"])
                user_answer = answers.get(q_id, "").strip().upper()
                correct_answer = q["correct_answer"].strip().upper()

                if user_answer == correct_answer:
                    correct_count += 1
                else:
                    result["wrong_answers"].append(
                        {
                            "question_number": q["number"],
                            "question_text": q["question"],
                            "user_answer": user_answer
                            if user_answer
                            else "Không trả lời",
                            "correct_answer": correct_answer,
                            "explanation": q.get("explanation", ""),
                        }
                    )

            total_mc = len(mc_questions)
            mc_percentage = (correct_count / total_mc) if total_mc > 0 else 0
            mc_score = mc_percentage * 10 * mc_weight

            result["multiple_choice"] = {
                "correct_count": correct_count,
                "total_questions": total_mc,
                "percentage": round(mc_percentage * 100, 1),
                "raw_score": round(mc_score, 2),
                "weight": mc_weight * 100,
            }

        # ========== CHẤM PHẦN TỰ LUẬN (NẾU CÓ) ==========
        essay_section = next((s for s in sections if s["type"] == "essay"), None)

        if essay_section and essay_weight > 0:
            essay_questions = essay_section.get("questions", [])
            essay_results = []
            total_essay_score = 0

            for q in essay_questions:
                q_id = str(q["id"])
                user_essay = essays.get(q_id, "").strip()

                # Validate độ dài
                word_count = len(user_essay.split()) if user_essay else 0
                min_words = q.get("min_words", 0)
                max_words = q.get("max_words", 999999)

                if word_count < min_words:
                    essay_results.append(
                        {
                            "question_number": q["number"],
                            "question": q["question"],
                            "score": 0,
                            "max_score": q.get("points", 0),
                            "feedback": f"Bài viết quá ngắn ({word_count}/{min_words} từ)",
                            "word_count": word_count,
                        }
                    )
                    continue

                if word_count > max_words:
                    essay_results.append(
                        {
                            "question_number": q["number"],
                            "question": q["question"],
                            "score": 0,
                            "max_score": q.get("points", 0),
                            "feedback": f"Bài viết quá dài ({word_count}/{max_words} từ)",
                            "word_count": word_count,
                        }
                    )
                    continue

                # Chấm bằng AI (nếu bật)
                if scoring_config.get("essay", {}).get("ai_grading", False):
                    try:
                        from utils.gemini_api import grade_essay_with_ai

                        ai_feedback = grade_essay_with_ai(user_essay, q, subject)

                        # Tính điểm theo rubric
                        rubric = q.get("grading_rubric", {})
                        essay_score = 0
                        max_points = q.get("points", 0)
                        details = {}

                        for criterion, config in rubric.items():
                            weight = config.get("weight_percent", 0) / 100
                            criterion_score = ai_feedback.get(criterion, {}).get(
                                "score", 5
                            )
                            weighted = (criterion_score / 10) * max_points * weight
                            essay_score += weighted

                            details[criterion] = {
                                "score": criterion_score,
                                "weighted_score": round(weighted, 2),
                                "feedback": ai_feedback.get(criterion, {}).get(
                                    "feedback", ""
                                ),
                            }

                        total_essay_score += essay_score

                        essay_results.append(
                            {
                                "question_number": q["number"],
                                "question": q["question"],
                                "user_answer": user_essay,
                                "score": round(essay_score, 2),
                                "max_score": max_points,
                                "word_count": word_count,
                                "feedback": ai_feedback.get("overall_feedback", ""),
                                "details": details,
                            }
                        )

                    except Exception as e:
                        print(f"❌ Lỗi chấm AI: {e}")
                        essay_results.append(
                            {
                                "question_number": q["number"],
                                "question": q["question"],
                                "score": 0,
                                "max_score": q.get("points", 0),
                                "feedback": "Lỗi hệ thống chấm bài",
                                "word_count": word_count,
                            }
                        )
                else:
                    # Không dùng AI, cho điểm trung bình
                    max_points = q.get("points", 0)
                    default_score = max_points * 0.7
                    total_essay_score += default_score

                    essay_results.append(
                        {
                            "question_number": q["number"],
                            "question": q["question"],
                            "user_answer": user_essay,
                            "score": round(default_score, 2),
                            "max_score": max_points,
                            "word_count": word_count,
                            "feedback": "Bài làm đã được nộp (chưa chấm chi tiết)",
                        }
                    )

            # Tính điểm tự luận
            max_essay_points = sum(q.get("points", 0) for q in essay_questions)
            essay_percentage = (
                (total_essay_score / max_essay_points) if max_essay_points > 0 else 0
            )
            essay_weighted = essay_percentage * 10 * essay_weight

            result["essay"] = {
                "total_score": round(total_essay_score, 2),
                "max_score": max_essay_points,
                "percentage": round(essay_percentage * 100, 1),
                "weighted_score": round(essay_weighted, 2),
                "weight": essay_weight * 100,
                "results": essay_results,
            }

        # ========== TỔNG ĐIỂM ==========
        mc_final = (
            result["multiple_choice"]["raw_score"] if result["multiple_choice"] else 0
        )
        essay_final = result["essay"]["weighted_score"] if result["essay"] else 0
        result["total_score"] = round(mc_final + essay_final, 2)

        # ========== XÓA SESSION ==========
        session.pop(session_key, None)
        session.modified = True

        # ⭐⭐⭐ TẠO PHÂN TÍCH AI ⭐⭐⭐
        ai_analysis = None

        # Chỉ tạo AI analysis nếu có câu sai
        if result.get("wrong_answers") and len(result["wrong_answers"]) > 0:
            try:
                print("🤖 Đang tạo phân tích AI...")

                from utils.gemini_api import analyze_exam_results

                subject_info = SUBJECTS.get(subject, {})

                # Chuẩn bị dữ liệu cho AI
                analysis_data = {
                    "subject": subject,
                    "subject_name": subject_info.get("name", subject),
                    "exam_title": exam.get("title", ""),
                    "total_score": result["total_score"],
                    "correct_count": result["multiple_choice"]["correct_count"]
                    if result.get("multiple_choice")
                    else 0,
                    "total_questions": result["multiple_choice"]["total_questions"]
                    if result.get("multiple_choice")
                    else 0,
                    "wrong_answers": result["wrong_answers"],
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
        results_file = writable_data_file("exam_results.json")

        all_results = read_json(results_file, [])

        subject_info = SUBJECTS.get(subject, {})

        all_results.append(
            {
                "user_id": session["user_id"],
                "username": session.get("username", "Unknown"),
                "subject": subject,
                "subject_name": subject_info.get("name", subject),
                "subject_icon": subject_info.get("icon", "📚"),
                "subject_color": subject_info.get("color", "#95a5a6"),
                "exam_id": exam_id,
                "exam_title": exam.get("title", ""),
                "result": result,
                "ai_analysis": ai_analysis,  # ⭐ THÊM AI ANALYSIS
                "submitted_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            }
        )

        write_json(results_file, all_results)

        return jsonify(
            {"success": True, "result": result, "message": "Nộp bài thành công"}
        )

    except FileNotFoundError:
        return jsonify({"success": False, "message": "Không tìm thấy file đề thi"}), 404
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"}), 500


# ============================================================================
# ROUTE 5: Lịch sử làm bài - ĐÃ CẬP NHẬT
# ============================================================================
@app.route("/tracnghiem/lich-su")
@login_required
def lich_su_tracnghiem():
    """
    Hiển thị lịch sử làm bài - Hỗ trợ 10 môn học
    """
    try:
        user_id = session.get("user_id")
        results_file = writable_data_file("exam_results.json")

        all_results = read_json(results_file, [])

        user_results = [r for r in all_results if r.get("user_id") == user_id]
        user_results.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)

        # Thêm tên môn học và icon
        for result in user_results:
            subject = result.get("subject", "")
            subject_info = SUBJECTS.get(subject, {"name": subject, "icon": "📚"})
            result["subject_name"] = subject_info["name"]
            result["subject_icon"] = subject_info["icon"]
            result["subject_color"] = subject_info.get("color", "#95a5a6")

        print(f"User {user_id} có {len(user_results)} bài đã làm")

        return render_template(
            "lichsu_tracnghiem.html",
            results=user_results,
            username=session.get("username"),
        )

    except Exception as e:
        print(f"ERROR in lich_su_tracnghiem: {str(e)}")
        import traceback

        traceback.print_exc()
        flash(f"Lỗi khi tải lịch sử: {str(e)}", "danger")
        return redirect(url_for("tracnghiem"))


# ============================================================================
# ROUTE 6: Reset session - GIỮ NGUYÊN
# ============================================================================
@app.route("/tracnghiem/reset/<subject>/<exam_id>")
@login_required
def reset_exam_session(subject, exam_id):
    """
    Reset session để làm lại bài thi
    """
    if not validate_subject(subject):
        flash("Môn học không hợp lệ", "danger")
        return redirect(url_for("tracnghiem"))

    session_key = f"exam_start_{subject}_{exam_id}"

    if session_key in session:
        session.pop(session_key)
        session.modified = True
        flash("Đã reset bài thi. Bạn có thể làm lại từ đầu!", "success")

    return redirect(
        url_for("lam_bai_tracnghiem", subject=subject, exam_id=exam_id, reset="yes")
    )


# ============================================================================
# ROUTE 7: Xem kết quả - ⭐ ĐÃ TÍCH HỢP HIỂN THỊ AI ANALYSIS ⭐
# ============================================================================
@app.route("/tracnghiem/ket-qua/<subject>/<exam_id>")
@login_required
def ket_qua_tracnghiem(subject, exam_id):
    """
    Hiển thị kết quả bài làm - ⭐ BAO GỒM PHÂN TÍCH AI
    """
    try:
        if not validate_subject(subject):
            flash("Môn học không hợp lệ", "danger")
            return redirect(url_for("tracnghiem"))

        user_id = session.get("user_id")
        results_file = writable_data_file("exam_results.json")

        all_results = read_json(results_file, [])
        if not all_results:
            flash("Không tìm thấy kết quả bài làm", "warning")
            return redirect(url_for("tracnghiem"))

        matching_results = [
            r
            for r in all_results
            if r.get("user_id") == user_id
            and r.get("subject") == subject
            and r.get("exam_id") == exam_id
        ]

        if not matching_results:
            flash("Không tìm thấy kết quả bài làm", "warning")
            return redirect(url_for("tracnghiem"))

        result_data = matching_results[-1]

        # Thêm thông tin môn học
        subject_info = SUBJECTS.get(
            subject, {"name": subject, "icon": "📚", "color": "#95a5a6"}
        )

        # ⭐ CHUẨN BỊ DỮ LIỆU CHO TEMPLATE
        # Lấy kết quả thực tế từ nested structure
        actual_result = result_data.get("result", {})

        # Tính toán các giá trị cần thiết
        if actual_result.get("multiple_choice"):
            mc_data = actual_result["multiple_choice"]
            correct_count = mc_data.get("correct_count", 0)
            total_questions = mc_data.get("total_questions", 0)
        else:
            correct_count = 0
            total_questions = 0

        # Tạo object result đơn giản cho template
        template_result = {
            "score": actual_result.get("total_score", 0),
            "correct_count": correct_count,
            "total_questions": total_questions,
            "wrong_answers": actual_result.get("wrong_answers", []),
            "subject": subject,
            "subject_name": subject_info["name"],
            "subject_icon": subject_info["icon"],
            "subject_color": subject_info["color"],
            "exam_id": exam_id,
            "exam_title": result_data.get("exam_title", ""),
            "submitted_at": result_data.get("submitted_at", ""),
        }

        # ⭐ LẤY PHÂN TÍCH AI (nếu có)
        ai_analysis = result_data.get("ai_analysis", None)

        if ai_analysis:
            print(f"✅ Hiển thị phân tích AI cho user {user_id}")
        else:
            print(f"⚠️ Không có phân tích AI cho bài thi này")

        return render_template(
            "ketqua.html",
            result=template_result,
            ai_analysis=ai_analysis,
            username=session.get("username"),
        )

    except Exception as e:
        print(f"ERROR in ket_qua_tracnghiem: {str(e)}")
        import traceback

        traceback.print_exc()
        flash(f"Lỗi khi hiển thị kết quả: {str(e)}", "danger")
        return redirect(url_for("tracnghiem"))


##############


UPLOAD_FOLDER = str(FORUM_UPLOAD_DIR)
ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "pdf",
    "doc",
    "docx",
    "txt",
    "zip",
    "rar",
}
MAX_FILE_SIZE = 10 * 1024 * 1024


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def optimized_image_payload(source_path, suffix, max_size=(720, 720), quality=82):
    source_path = os.fspath(source_path)
    source = os.path.abspath(source_path)
    stem = os.path.splitext(os.path.basename(source))[0]
    optimized_name = f"{stem}_{suffix}.webp"
    optimized_path = forum_upload_path(optimized_name)

    try:
        with Image.open(source) as image:
            image.seek(0)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if has_alpha else "RGB")
            image.save(optimized_path, "WEBP", quality=quality, method=6)
    except (UnidentifiedImageError, OSError, ValueError):
        return None

    sync_file_to_remote(optimized_path)
    return {
        "url": forum_upload_url(optimized_name),
        "storage_path": str(optimized_path),
        "size": os.path.getsize(optimized_path),
    }


@app.route("/uploads/forum/<path:filename>")
@login_required
def uploaded_forum_file(filename):
    ensure_forum_upload_available(filename)
    response = send_from_directory(FORUM_UPLOAD_DIR, filename)
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


def forum_month_key(dt=None):
    dt = dt or datetime.now()
    return dt.strftime("%Y-%m")


def forum_time_ago(iso_string):
    try:
        created = datetime.fromisoformat(iso_string)
        seconds = int((datetime.now() - created).total_seconds())
        if seconds < 60:
            return "vừa xong"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} phút trước"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} giờ trước"
        days = hours // 24
        if days < 30:
            return f"{days} ngày trước"
        months = days // 30
        return f"{months} tháng trước"
    except Exception:
        return ""


def forum_role_label(role):
    if role == "teacher":
        return "Giáo viên"
    if role == "admin":
        return "Quản trị viên"
    return "Học sinh"


def forum_normalize_question(post):
    tags = post.get("tags", [])
    subject = post.get("subject") or next((tag for tag in tags if tag in FORUM_SUBJECTS), "Khác")
    grade = post.get("grade") or next((tag for tag in tags if tag in FORUM_GRADES), "")
    status = post.get("status")
    if not status:
        status = "resolved" if post.get("accepted_answer_id") else ("answered" if post.get("comments_count", 0) else "open")
    post["subject"] = subject
    post["grade"] = grade
    post["status"] = status
    post["reward_points"] = int(post.get("reward_points") or 0)
    post["answers_count"] = int(post.get("comments_count") or 0)
    post["time_ago"] = forum_time_ago(post.get("created_at", ""))
    post["role_label"] = forum_role_label(post.get("author_role", "student"))
    post["is_first_question"] = bool(post.get("is_first_question", False))
    return post


def forum_points_events():
    return read_json(FORUM_POINTS_FILE, [])


def add_forum_points(user_id, username, role, points, reason, post_id=None, answer_id=None):
    points = int(points or 0)
    if points == 0:
        return None
    events = forum_points_events()
    event = {
        "id": f"fp_{len(events) + 1:06d}",
        "user_id": user_id,
        "username": username,
        "role": role,
        "points": points,
        "reason": reason,
        "post_id": post_id,
        "answer_id": answer_id,
        "month": forum_month_key(),
        "created_at": datetime.now().isoformat(),
    }
    events.append(event)
    write_json(FORUM_POINTS_FILE, events)
    return event


def shop_items():
    items = read_json(SHOP_ITEMS_FILE, [])
    if not isinstance(items, list):
        return []
    return [normalize_shop_item(item) for item in items]


def shop_item_by_id(item_id):
    return next((item for item in shop_items() if item.get("id") == item_id), None)


def normalize_shop_item(item):
    type_labels = {
        "badge": "Huy hiệu",
        "frame": "Khung avatar",
        "title": "Danh hiệu",
        "avatar": "Avatar",
        "sticker": "Sticker",
    }
    item = dict(item)
    item["type_label"] = item.get("type_label") or type_labels.get(item.get("type"), "Vật phẩm")
    item["price"] = int(item.get("price") or 0)
    item["icon"] = item.get("icon") or "◆"
    item["css_class"] = item.get("css_class") or ""
    item["image_url"] = item.get("image_url") or ""
    item["image_storage_path"] = item.get("image_storage_path") or ""
    item["original_image_url"] = item.get("original_image_url") or item["image_url"]
    item["optimized_storage_path"] = item.get("optimized_storage_path") or ""
    item["active"] = bool(item.get("active", True))
    return item


def shop_item_base_id(item_type, name):
    base = secure_filename(f"{item_type}_{name}".lower().replace(" ", "_"))
    return base or f"{item_type}_{uuid.uuid4().hex[:8]}"


def create_shop_item_id(item_type, name, existing_items):
    existing_ids = {item.get("id") for item in existing_items}
    base = shop_item_base_id(item_type, name)
    item_id = base
    suffix = 1
    while item_id in existing_ids:
        suffix += 1
        item_id = f"{base}_{suffix}"
    return item_id


def user_inventory_records(user_id=None):
    inventory = read_json(USER_INVENTORY_FILE, [])
    if not isinstance(inventory, list):
        return []
    if user_id is None:
        return inventory
    return [record for record in inventory if record.get("user_id") == user_id]


def save_user_inventory(records):
    write_json(USER_INVENTORY_FILE, records)


def user_profile_records():
    records = read_json(USER_PROFILES_FILE, [])
    return records if isinstance(records, list) else []


def save_user_profile_records(records):
    write_json(USER_PROFILES_FILE, records)


def user_profile_customization(user_id):
    records = user_profile_records()
    profile = next((record for record in records if record.get("user_id") == user_id), None)
    if profile:
        return profile
    return {
        "user_id": user_id,
        "avatar_url": "",
        "avatar_storage_path": "",
        "equipped_avatar_item_id": "",
        "equipped_frame_id": "",
        "equipped_title_id": "",
        "created_at": datetime.now().isoformat(),
    }


def save_user_profile_customization(user_id, updates):
    records = user_profile_records()
    now = datetime.now().isoformat()
    for record in records:
        if record.get("user_id") == user_id:
            record.update(updates)
            record["updated_at"] = now
            save_user_profile_records(records)
            return record

    profile = {
        "user_id": user_id,
        "avatar_url": "",
        "avatar_storage_path": "",
        "equipped_avatar_item_id": "",
        "equipped_frame_id": "",
        "equipped_title_id": "",
        "created_at": now,
    }
    profile.update(updates)
    records.append(profile)
    save_user_profile_records(records)
    return profile


def user_owned_items(user_id):
    owned_records = user_inventory_records(user_id)
    items_by_id = {item.get("id"): item for item in shop_items()}
    enriched = []
    for record in owned_records:
        item = items_by_id.get(record.get("item_id"))
        if item:
            enriched.append({**record, "item": item})
    return enriched


def grant_shop_item_to_user(user_id, item_id, source="admin_grant", note=""):
    item = shop_item_by_id(item_id)
    user = get_user_by_id(user_id)
    if not item or not user:
        return None, "Không tìm thấy vật phẩm hoặc tài khoản"

    inventory = user_inventory_records()
    existing = next(
        (record for record in inventory if record.get("user_id") == user_id and record.get("item_id") == item_id),
        None,
    )
    if existing:
        return existing, "Người dùng đã sở hữu vật phẩm"

    now = datetime.now().isoformat()
    record = {
        "id": f"inv_{len(inventory) + 1:06d}",
        "user_id": user_id,
        "username": user.get("username", "Unknown"),
        "item_id": item_id,
        "item_type": item.get("type"),
        "source": source,
        "note": note,
        "created_at": now,
    }
    inventory.append(record)
    save_user_inventory(inventory)

    if item.get("type") == "frame" and not user_profile_customization(user_id).get("equipped_frame_id"):
        save_user_profile_customization(user_id, {"equipped_frame_id": item_id})
    elif item.get("type") == "title" and not user_profile_customization(user_id).get("equipped_title_id"):
        save_user_profile_customization(user_id, {"equipped_title_id": item_id})

    orders = read_json(SHOP_ORDERS_FILE, [])
    orders.append(
        {
            "id": f"order_{len(orders) + 1:06d}",
            "user_id": user_id,
            "username": user.get("username", "Unknown"),
            "item_id": item_id,
            "item_name": item.get("name"),
            "price": 0,
            "source": source,
            "note": note,
            "created_at": now,
        }
    )
    write_json(SHOP_ORDERS_FILE, orders)
    return record, "Đã trao vật phẩm"


def user_equipped_items(user_id):
    profile = user_profile_customization(user_id)
    items_by_id = {item.get("id"): item for item in shop_items()}
    badges = [record["item"] for record in user_owned_items(user_id) if record["item"].get("type") == "badge"]
    return {
        "profile": profile,
        "frame": items_by_id.get(profile.get("equipped_frame_id")),
        "title": items_by_id.get(profile.get("equipped_title_id")),
        "badges": badges,
    }


def decorate_forum_author(payload, user_id):
    equipped = user_equipped_items(user_id)
    profile = equipped["profile"]
    payload["author_avatar_url"] = profile.get("avatar_url", "")
    payload["author_frame"] = equipped.get("frame")
    payload["author_title"] = equipped.get("title")
    payload["author_badges"] = equipped.get("badges", [])[:3]
    return payload


def normalize_answer_feedback(answer):
    thank_user_ids = answer.get("thank_user_ids") or answer.get("thanks") or []
    if not isinstance(thank_user_ids, list):
        thank_user_ids = []
    answer["thank_user_ids"] = list(dict.fromkeys(str(user_id) for user_id in thank_user_ids if user_id))

    ratings = answer.get("ratings") or {}
    if not isinstance(ratings, dict):
        ratings = {}
    normalized_ratings = {}
    for user_id, value in ratings.items():
        try:
            rating = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= rating <= 5:
            normalized_ratings[str(user_id)] = rating
    answer["ratings"] = normalized_ratings

    discussions = answer.get("discussions") or []
    if not isinstance(discussions, list):
        discussions = []
    answer["discussions"] = discussions
    return answer


def answer_feedback_summary(answer, viewer_id=None):
    answer = normalize_answer_feedback(answer)
    ratings = answer.get("ratings", {})
    rating_values = list(ratings.values())
    average_rating = round(sum(rating_values) / len(rating_values), 1) if rating_values else 0
    viewer_key = str(viewer_id) if viewer_id else ""
    return {
        "thanks_count": len(answer.get("thank_user_ids", [])),
        "ratings_count": len(rating_values),
        "average_rating": average_rating,
        "five_star_count": len([rating for rating in rating_values if rating == 5]),
        "current_user_thanked": viewer_key in answer.get("thank_user_ids", []),
        "current_user_rating": ratings.get(viewer_key, 0),
    }


def avatar_file_payload(file):
    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    if ext not in {"png", "jpg", "jpeg", "gif"}:
        raise ValueError("Chỉ hỗ trợ ảnh PNG, JPG, JPEG hoặc GIF")

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > 5 * 1024 * 1024:
        raise ValueError("Ảnh đại diện tối đa 5MB")

    unique_filename = f"avatar_{session['user_id']}_{uuid.uuid4().hex[:8]}_{filename}"
    file_path = forum_upload_path(unique_filename)
    file.save(file_path)
    sync_file_to_remote(file_path)
    optimized = optimized_image_payload(file_path, "avatar", max_size=(360, 360), quality=84)
    return {
        "url": optimized["url"] if optimized else forum_upload_url(unique_filename),
        "storage_path": str(file_path),
        "original_url": forum_upload_url(unique_filename),
        "optimized_storage_path": optimized["storage_path"] if optimized else "",
    }


def shop_asset_file_payload(file, item_type):
    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    if ext not in {"png", "jpg", "jpeg", "gif", "webp"}:
        raise ValueError("Chỉ hỗ trợ ảnh PNG, JPG, JPEG, GIF hoặc WEBP")

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > 5 * 1024 * 1024:
        raise ValueError("Ảnh vật phẩm tối đa 5MB")

    unique_filename = f"shop_{item_type}_{uuid.uuid4().hex[:8]}_{filename}"
    file_path = forum_upload_path(unique_filename)
    file.save(file_path)
    sync_file_to_remote(file_path)
    optimized = optimized_image_payload(file_path, "thumb", max_size=(360, 360), quality=82)
    return {
        "url": optimized["url"] if optimized else forum_upload_url(unique_filename),
        "storage_path": str(file_path),
        "original_url": forum_upload_url(unique_filename),
        "optimized_storage_path": optimized["storage_path"] if optimized else "",
    }


def forum_user_stats(user_id):
    posts = db.get_all_forum_posts()
    comments = db._load_json(db.forum_comments_file)
    points = forum_points_events()
    reports = read_json(FORUM_REPORTS_FILE, [])
    user_points = [event for event in points if event.get("user_id") == user_id]
    month = forum_month_key()
    posts_by_id = {post.get("id"): forum_normalize_question(dict(post)) for post in posts}
    helped_subject_groups = {
        "KHTN": 0,
        "KHXH": 0,
        "Ngoại Ngữ": 0,
        "Nghệ Thuật": 0,
        "KHCN": 0,
    }
    subject_groups = {
        "Toán": "KHTN",
        "Vật Lý": "KHTN",
        "Hóa Học": "KHTN",
        "Sinh Học": "KHTN",
        "Ngữ Văn": "KHXH",
        "Lịch Sử": "KHXH",
        "Địa Lý": "KHXH",
        "GDCD": "KHXH",
        "Tiếng Anh": "Ngoại Ngữ",
        "Công Nghệ": "KHCN",
        "Tin Học": "KHCN",
    }
    for comment in comments:
        if comment.get("author_id") != user_id:
            continue
        post = posts_by_id.get(comment.get("post_id"), {})
        group = subject_groups.get(post.get("subject"), "KHTN")
        helped_subject_groups[group] = helped_subject_groups.get(group, 0) + 1
    max_helped_subject = max(helped_subject_groups.values(), default=0) or 1
    helped_subjects = [
        {
            "label": label,
            "value": value,
            "percent": round((value / max_helped_subject) * 100) if value else 0,
        }
        for label, value in helped_subject_groups.items()
    ]

    user_answers = [comment for comment in comments if comment.get("author_id") == user_id]
    for comment in user_answers:
        normalize_answer_feedback(comment)

    return {
        "points": sum(int(event.get("points", 0)) for event in user_points),
        "monthly_points": sum(
            int(event.get("points", 0))
            for event in user_points
            if event.get("month") == month and int(event.get("points", 0)) > 0
        ),
        "questions_count": len([post for post in posts if post.get("author_id") == user_id]),
        "answers_count": len(user_answers),
        "best_answers_count": len([comment for comment in user_answers if comment.get("is_best_answer")]),
        "warnings_count": len([report for report in reports if report.get("reported_user_id") == user_id]),
        "thanks_count": sum(len(comment.get("thank_user_ids", [])) for comment in user_answers),
        "five_star_count": sum(
            len([rating for rating in comment.get("ratings", {}).values() if rating == 5])
            for comment in user_answers
        ),
        "verified_count": len([comment for comment in user_answers if comment.get("is_verified_answer")]),
        "helped_count": len({comment.get("post_id") for comment in user_answers}),
        "helped_subjects": helped_subjects,
    }


def forum_user_activity(user_id, limit=6):
    posts = [forum_normalize_question(dict(post)) for post in db.get_all_forum_posts()]
    comments = db._load_json(db.forum_comments_file)
    points = forum_points_events()
    posts_by_id = {post.get("id"): post for post in posts}

    user_questions = [post for post in posts if post.get("author_id") == user_id]
    for post in user_questions:
        post["created_at_formatted"] = format_datetime(post.get("created_at", ""))
        post["time_ago"] = forum_time_ago(post.get("created_at", ""))
    user_questions.sort(key=lambda item: item.get("created_at", ""), reverse=True)

    user_answers = []
    for comment in comments:
        if comment.get("author_id") != user_id:
            continue
        post = posts_by_id.get(comment.get("post_id"))
        if not post:
            continue
        points_total = int(comment.get("points_awarded") or 0) + int(comment.get("best_bonus_awarded") or 0)
        user_answers.append(
            {
                "id": comment.get("id"),
                "post_id": post.get("id"),
                "post_title": post.get("title", "Câu hỏi đã xóa"),
                "subject": post.get("subject", "Khác"),
                "grade": post.get("grade", ""),
                "content": comment.get("content", ""),
                "created_at": comment.get("created_at", ""),
                "time_ago": forum_time_ago(comment.get("created_at", "")),
                "is_best_answer": bool(comment.get("is_best_answer")),
                "is_verified_answer": bool(comment.get("is_verified_answer")),
                "verified_at": comment.get("verified_at", ""),
                "verified_by_name": comment.get("verified_by_name", ""),
                "points_total": points_total,
            }
        )
    user_answers.sort(key=lambda item: item.get("created_at", ""), reverse=True)

    user_point_history = [
        {
            **event,
            "time_ago": forum_time_ago(event.get("created_at", "")),
            "post_title": posts_by_id.get(event.get("post_id"), {}).get("title", "Hoạt động diễn đàn"),
        }
        for event in points
        if event.get("user_id") == user_id
    ]
    user_point_history.sort(key=lambda item: item.get("created_at", ""), reverse=True)

    return {
        "questions": user_questions[:limit],
        "all_questions": user_questions,
        "answers": user_answers[:limit],
        "best_answers": [answer for answer in user_answers if answer.get("is_best_answer")][:limit],
        "verified_answers": [answer for answer in user_answers if answer.get("is_verified_answer")][:limit],
        "point_history": user_point_history[:limit],
    }


def forum_leaderboard(limit=20):
    month = forum_month_key()
    totals = {}
    for event in forum_points_events():
        if event.get("month") != month:
            continue
        event_points = int(event.get("points", 0))
        if event_points <= 0:
            continue
        user_id = event.get("user_id")
        if not user_id:
            continue
        if user_id not in totals:
            totals[user_id] = {
                "user_id": user_id,
                "username": event.get("username", "Unknown"),
                "role": event.get("role", "student"),
                "points": 0,
            }
        totals[user_id]["points"] += event_points
    ranking = sorted(totals.values(), key=lambda item: item["points"], reverse=True)
    for index, item in enumerate(ranking, 1):
        item["rank"] = index
        item["role_label"] = forum_role_label(item.get("role", "student"))
        decorate_forum_author(item, item.get("user_id"))
    return ranking[:limit]


def forum_ban_records():
    records = read_json(FORUM_BANS_FILE, [])
    return records if isinstance(records, list) else []


def save_forum_ban_records(records):
    write_json(FORUM_BANS_FILE, records)


def forum_active_ban(user_id):
    now = datetime.now()
    records = forum_ban_records()
    changed = False
    active_records = []

    for record in records:
        if record.get("user_id") != user_id or record.get("status") != "active":
            continue

        banned_until = record.get("banned_until")
        if banned_until:
            try:
                if datetime.fromisoformat(banned_until) <= now:
                    record["status"] = "expired"
                    record["expired_at"] = now.isoformat()
                    changed = True
                    continue
            except Exception:
                pass
        active_records.append(record)

    if changed:
        save_forum_ban_records(records)

    active_records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return active_records[0] if active_records else None


def forum_ban_message(ban):
    if not ban:
        return ""
    if ban.get("ban_type") == "permanent":
        return "Tài khoản của bạn đang bị chặn vĩnh viễn khỏi chat/diễn đàn."
    try:
        until_text = format_datetime(ban.get("banned_until", ""))
    except Exception:
        until_text = ban.get("banned_until", "")
    return f"Tài khoản của bạn đang bị chặn chat/diễn đàn đến {until_text}."


def current_user_forum_ban():
    if "user_id" not in session:
        return None
    return forum_active_ban(session["user_id"])


def forum_ban_json_response():
    ban = current_user_forum_ban()
    if not ban:
        return None
    message = forum_ban_message(ban)
    return jsonify({"success": False, "message": message, "error": message, "banned": True}), 403


def forum_report_label(reason):
    return FORUM_REPORT_REASONS.get(reason, reason or "Khác")


def forum_report_status_label(status):
    return FORUM_REPORT_STATUSES.get(status, status or "Chờ xử lý")


def annotate_forum_report(report):
    report = dict(report)
    report["reason_label"] = forum_report_label(report.get("reason"))
    report["status_label"] = forum_report_status_label(report.get("status", "pending"))
    report["created_at_formatted"] = format_datetime(report.get("created_at", ""))
    report["active_ban"] = forum_active_ban(report.get("reported_user_id"))

    target_text = "Nội dung đã bị xóa hoặc không tìm thấy"
    if report.get("target_type") == "question":
        post = db.get_forum_post_by_id(report.get("target_id"))
        if post:
            target_text = post.get("title") or post.get("content", "")[:120]
            report["target_url"] = url_for("forum_post_detail", post_id=post.get("id"))
    else:
        comments = db._load_json(db.forum_comments_file)
        answer = next((c for c in comments if c.get("id") == report.get("target_id")), None)
        if answer:
            target_text = answer.get("content", "")[:160]
            report["target_url"] = url_for("forum_post_detail", post_id=answer.get("post_id"))

    report["target_text"] = target_text
    return report


def forum_admin_report_counts(reports):
    return {
        "pending": len([r for r in reports if r.get("status", "pending") == "pending"]),
        "resolved": len([r for r in reports if r.get("status") == "resolved"]),
        "rejected": len([r for r in reports if r.get("status") == "rejected"]),
        "active_bans": len([b for b in forum_ban_records() if b.get("status") == "active"]),
    }


def parse_iso_datetime(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def online_user_records():
    now = datetime.now()
    cutoff = now - timedelta(seconds=ONLINE_WINDOW_SECONDS)
    return [
        dict(user, last_seen_text=forum_time_ago(user.get("last_seen").isoformat()))
        for user in ONLINE_USERS.values()
        if user.get("last_seen") and user.get("last_seen") >= cutoff
    ]


def chart_percent(value, total):
    if not total:
        return 0
    return round((value / total) * 100)


def admin_dashboard_stats(reports):
    users = load_users()
    posts = db.get_all_forum_posts()
    comments = db._load_json(db.forum_comments_file)
    chat_messages = db.get_all_chat_messages()
    point_events = forum_points_events()
    active_users = online_user_records()

    role_counts = {
        "student": len([u for u in users if u.get("role") == "student"]),
        "teacher": len([u for u in users if u.get("role") == "teacher"]),
        "admin": len([u for u in users if u.get("role") == "admin"]),
    }
    total_users = sum(role_counts.values()) or 1
    role_rows = [
        {"label": "Học sinh", "value": role_counts["student"], "percent": chart_percent(role_counts["student"], total_users)},
        {"label": "Giáo viên", "value": role_counts["teacher"], "percent": chart_percent(role_counts["teacher"], total_users)},
        {"label": "Admin", "value": role_counts["admin"], "percent": chart_percent(role_counts["admin"], total_users)},
    ]

    today = datetime.now().date()
    daily_rows = []
    for days_ago in range(6, -1, -1):
        day = today - timedelta(days=days_ago)
        day_key = day.isoformat()
        question_count = len([p for p in posts if (parse_iso_datetime(p.get("created_at", "")) or datetime.min).date().isoformat() == day_key])
        answer_count = len([c for c in comments if (parse_iso_datetime(c.get("created_at", "")) or datetime.min).date().isoformat() == day_key])
        report_count = len([r for r in reports if (parse_iso_datetime(r.get("created_at", "")) or datetime.min).date().isoformat() == day_key])
        daily_rows.append(
            {
                "label": day.strftime("%d/%m"),
                "questions": question_count,
                "answers": answer_count,
                "reports": report_count,
                "total": question_count + answer_count + report_count,
            }
        )
    max_daily = max([row["total"] for row in daily_rows] + [1])
    for row in daily_rows:
        row["height"] = max(6, chart_percent(row["total"], max_daily)) if row["total"] else 4

    subject_totals = {}
    for post in posts:
        normalized = forum_normalize_question(dict(post))
        subject = normalized.get("subject") or "Khác"
        subject_totals[subject] = subject_totals.get(subject, 0) + 1
    max_subject = max(subject_totals.values(), default=1)
    subject_rows = [
        {"label": subject, "value": value, "percent": chart_percent(value, max_subject)}
        for subject, value in sorted(subject_totals.items(), key=lambda item: item[1], reverse=True)[:6]
    ]

    report_counts = forum_admin_report_counts(reports)
    total_reports = len(reports)
    report_rows = [
        {"label": "Chờ xử lý", "value": report_counts["pending"], "percent": chart_percent(report_counts["pending"], total_reports or 1)},
        {"label": "Đã xử lý", "value": report_counts["resolved"], "percent": chart_percent(report_counts["resolved"], total_reports or 1)},
        {"label": "Bỏ qua", "value": report_counts["rejected"], "percent": chart_percent(report_counts["rejected"], total_reports or 1)},
    ]

    resolved_rate = chart_percent(report_counts["resolved"], total_reports) if total_reports else 0
    total_diamonds = sum(int(event.get("points", 0)) for event in point_events)
    ai_chat_count = len([m for m in chat_messages if m.get("response") or m.get("quiz")])

    return {
        "total_users": len(users),
        "students": role_counts["student"],
        "teachers": role_counts["teacher"],
        "admins": role_counts["admin"],
        "online_students": len([u for u in active_users if u.get("role") == "student"]),
        "online_total": len(active_users),
        "active_users": sorted(active_users, key=lambda item: item.get("last_seen", datetime.min), reverse=True)[:8],
        "questions": len(posts),
        "answers": len(comments),
        "chat_messages": len(chat_messages),
        "ai_chat_count": ai_chat_count,
        "total_diamonds": total_diamonds,
        "resolved_rate": resolved_rate,
        "role_rows": role_rows,
        "daily_rows": daily_rows,
        "subject_rows": subject_rows,
        "report_rows": report_rows,
    }


def forum_attachment_payload(file):
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
    file_path = forum_upload_path(unique_filename)
    file.save(file_path)
    sync_file_to_remote(file_path)

    file_size = os.path.getsize(file_path)
    file_ext = filename.rsplit(".", 1)[1].lower()
    file_type = "image" if file_ext in {"png", "jpg", "jpeg", "gif", "webp"} else "file"
    optimized = (
        optimized_image_payload(file_path, "display", max_size=(960, 960), quality=82)
        if file_type == "image"
        else None
    )
    return {
        "type": file_type,
        "filename": filename,
        "path": forum_upload_url(unique_filename),
        "storage_path": str(file_path),
        "url": forum_upload_url(unique_filename),
        "thumb_url": optimized["url"] if optimized else "",
        "thumb_storage_path": optimized["storage_path"] if optimized else "",
        "size": file_size,
        "thumb_size": optimized["size"] if optimized else 0,
    }


def collect_forum_attachments():
    attachments = []
    if "files" not in request.files:
        return attachments
    for file in request.files.getlist("files"):
        if file and file.filename and allowed_file(file.filename):
            attachments.append(forum_attachment_payload(file))
    return attachments


@app.route("/forum")
@login_required
def forum():
    search_query = request.args.get("search", "").strip()
    filter_status = request.args.get("status", "all")
    filter_subject = request.args.get("subject", "all").strip()
    filter_grade = request.args.get("grade", "all").strip()

    if search_query:
        posts = db.search_forum_posts(search_query)
    else:
        posts = db.get_all_forum_posts()

    posts = [forum_normalize_question(post) for post in posts]

    if filter_subject != "all":
        posts = [p for p in posts if p.get("subject") == filter_subject]

    if filter_grade != "all":
        posts = [p for p in posts if p.get("grade") == filter_grade]

    if filter_status == "answered":
        posts = [p for p in posts if p.get("answers_count", 0) > 0]
    elif filter_status == "unanswered":
        posts = [p for p in posts if p.get("answers_count", 0) == 0]
    elif filter_status == "first":
        posts = [p for p in posts if p.get("is_first_question")]
    elif filter_status == "resolved":
        posts = [p for p in posts if p.get("status") == "resolved"]

    for post in posts:
        decorate_forum_author(post, post.get("author_id"))
        post["created_at_formatted"] = format_datetime(post["created_at"])
        if post.get("updated_at"):
            post["updated_at_formatted"] = format_datetime(post["updated_at"])

    return render_template(
        "forum.html",
        posts=posts,
        search_query=search_query,
        filter_status=filter_status,
        filter_subject=filter_subject,
        filter_grade=filter_grade,
        forum_subjects=FORUM_SUBJECTS,
        forum_grades=FORUM_GRADES,
        leaderboard=forum_leaderboard(5),
        current_user_stats=forum_user_stats(session["user_id"]),
        current_user_equipped=user_equipped_items(session["user_id"]),
        username=session.get("username"),
    )


@app.route("/forum/post/<post_id>")
@login_required
def forum_post_detail(post_id):
    post = db.get_forum_post_by_id(post_id)

    if not post:
        flash("Bài viết không tồn tại", "danger")
        return redirect(url_for("forum"))

    db.increment_post_views(post_id)
    post = forum_normalize_question(post)
    decorate_forum_author(post, post.get("author_id"))

    comments = db.get_comments_by_post(post_id)

    post["created_at_formatted"] = format_datetime(post["created_at"])
    if post.get("updated_at"):
        post["updated_at_formatted"] = format_datetime(post["updated_at"])

    for comment in comments:
        decorate_forum_author(comment, comment.get("author_id"))
        comment["created_at_formatted"] = format_datetime(comment["created_at"])
        comment["time_ago"] = forum_time_ago(comment.get("created_at", ""))
        comment["role_label"] = forum_role_label(comment.get("author_role", "student"))
        comment["points_awarded"] = int(comment.get("points_awarded") or 0)
        normalize_answer_feedback(comment)
        comment["feedback"] = answer_feedback_summary(comment, session["user_id"])
        for discussion in comment.get("discussions", []):
            decorate_forum_author(discussion, discussion.get("author_id"))
            discussion["time_ago"] = forum_time_ago(discussion.get("created_at", ""))
            discussion["role_label"] = forum_role_label(discussion.get("author_role", "student"))

    is_author = post["author_id"] == session["user_id"]
    can_verify_answers = session.get("role") in {"teacher", "admin"}

    return render_template(
        "forum_post_detail.html",
        post=post,
        comments=comments,
        is_author=is_author,
        can_verify_answers=can_verify_answers,
        user_stats=forum_user_stats(post.get("author_id")),
        username=session.get("username"),
    )


@app.route("/forum/create", methods=["GET", "POST"])
@login_required
def forum_create_post():
    if request.method == "POST":
        blocked_response = forum_ban_json_response()
        if blocked_response:
            return blocked_response

        try:
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()
            subject = request.form.get("subject", "").strip()
            grade = request.form.get("grade", "").strip()
            extra_tags = request.form.get("tags", "").strip()
            try:
                reward_points = int(request.form.get("reward_points", 10))
            except (TypeError, ValueError):
                reward_points = 10
            if reward_points not in FORUM_REWARD_LEVELS:
                return jsonify(
                    {
                        "success": False,
                        "message": "Điểm thưởng chỉ được chọn theo mức 10, 20, 30, 40, 50 hoặc 60",
                    }
                )

            if not title or not content or subject not in FORUM_SUBJECTS or grade not in FORUM_GRADES:
                return jsonify(
                    {
                        "success": False,
                        "message": "Vui lòng nhập đầy đủ tiêu đề, nội dung, môn học và lớp",
                    }
                )

            tags = [subject, grade]
            tags.extend(tag.strip() for tag in extra_tags.split(",") if tag.strip())
            tags = list(dict.fromkeys(tags))
            attachments = collect_forum_attachments()

            user = get_user_by_id(session["user_id"])
            existing_questions = db.get_forum_posts_by_user(session["user_id"])
            current_balance = forum_user_stats(session["user_id"])["points"]
            if current_balance < reward_points:
                return jsonify(
                    {
                        "success": False,
                        "message": f"Bạn cần có ít nhất {reward_points} kim cương để đặt câu hỏi mức {reward_points} điểm",
                    }
                )

            post_data = {
                "title": title,
                "content": content,
                "author_id": session["user_id"],
                "author_name": session.get("username", "Unknown"),
                "author_role": user.get("role", "student") if user else "student",
                "attachments": attachments,
                "tags": tags,
                "subject": subject,
                "grade": grade,
                "reward_points": reward_points,
                "status": "open",
                "accepted_answer_id": None,
                "is_first_question": len(existing_questions) == 0,
                "question_type": request.form.get("question_type", "question").strip() or "question",
            }

            post_id = db.create_forum_post(post_data)
            add_forum_points(
                session["user_id"],
                session.get("username", "Unknown"),
                user.get("role", "student") if user else "student",
                -reward_points,
                "question_reward_pool",
                post_id=post_id,
            )

            return jsonify(
                {
                    "success": True,
                    "post_id": post_id,
                    "message": "Đặt câu hỏi thành công",
                }
            )

        except Exception as e:
            return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

    return render_template(
        "forum_create_post.html",
        username=session.get("username"),
        forum_subjects=FORUM_SUBJECTS,
        forum_grades=FORUM_GRADES,
        reward_levels=FORUM_REWARD_LEVELS,
        current_user_stats=forum_user_stats(session["user_id"]),
    )


@app.route("/forum/edit/<post_id>", methods=["GET", "POST"])
@login_required
def forum_edit_post(post_id):
    post = db.get_forum_post_by_id(post_id)

    if not post:
        flash("Bài viết không tồn tại", "danger")
        return redirect(url_for("forum"))

    if post["author_id"] != session["user_id"]:
        flash("Bạn không có quyền chỉnh sửa bài viết này", "danger")
        return redirect(url_for("forum"))

    if request.method == "POST":
        blocked_response = forum_ban_json_response()
        if blocked_response:
            return blocked_response

        try:
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()
            subject = request.form.get("subject", "").strip()
            grade = request.form.get("grade", "").strip()
            extra_tags = request.form.get("tags", "").strip()
            reward_points = int(post.get("reward_points", 10) or 10)

            if not title or not content or subject not in FORUM_SUBJECTS or grade not in FORUM_GRADES:
                return jsonify(
                    {
                        "success": False,
                        "message": "Vui lòng nhập đầy đủ tiêu đề, nội dung, môn học và lớp",
                    }
                )

            tags = [subject, grade]
            tags.extend(tag.strip() for tag in extra_tags.split(",") if tag.strip())
            tags = list(dict.fromkeys(tags))

            attachments = post.get("attachments", [])

            attachments.extend(collect_forum_attachments())

            post_data = {
                "title": title,
                "content": content,
                "attachments": attachments,
                "tags": tags,
                "subject": subject,
                "grade": grade,
                "reward_points": reward_points,
                "question_type": request.form.get("question_type", post.get("question_type", "question")).strip() or "question",
            }

            success = db.update_forum_post(post_id, post_data)

            if success:
                return jsonify(
                    {"success": True, "message": "Cập nhật bài viết thành công"}
                )
            else:
                return jsonify({"success": False, "message": "Cập nhật thất bại"})

        except Exception as e:
            return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

    return render_template(
        "forum_create_post.html",
        post=post,
        edit_mode=True,
        username=session.get("username"),
        forum_subjects=FORUM_SUBJECTS,
        forum_grades=FORUM_GRADES,
        reward_levels=FORUM_REWARD_LEVELS,
        current_user_stats=forum_user_stats(session["user_id"]),
    )


@app.route("/forum/delete/<post_id>", methods=["POST"])
@login_required
def forum_delete_post(post_id):
    post = db.get_forum_post_by_id(post_id)

    if not post:
        return jsonify({"success": False, "message": "Bài viết không tồn tại"})

    if post["author_id"] != session["user_id"]:
        return jsonify(
            {"success": False, "message": "Bạn không có quyền xóa bài viết này"}
        )

    for attachment in post.get("attachments", []):
        try:
            attachment_path = attachment_storage_path(attachment)
            if attachment_path.exists():
                attachment_path.unlink()
        except:
            pass

    db.delete_forum_post(post_id)

    return jsonify({"success": True, "message": "Xóa bài viết thành công"})


def forum_answer_by_id(comment_id):
    comments = db._load_json(db.forum_comments_file)
    answer = next((comment for comment in comments if comment.get("id") == comment_id), None)
    return comments, answer


@app.route("/forum/answer/<comment_id>/thank", methods=["POST"])
@login_required
def forum_thank_answer(comment_id):
    comments, answer = forum_answer_by_id(comment_id)
    if not answer:
        return jsonify({"success": False, "message": "Không tìm thấy câu trả lời"}), 404
    if answer.get("author_id") == session["user_id"]:
        return jsonify({"success": False, "message": "Không thể tự cảm ơn câu trả lời của mình"}), 400

    normalize_answer_feedback(answer)
    viewer_id = str(session["user_id"])
    if viewer_id not in answer["thank_user_ids"]:
        answer["thank_user_ids"].append(viewer_id)
        write_json(db.forum_comments_file, comments)

    return jsonify(
        {
            "success": True,
            "message": "Đã cảm ơn câu trả lời",
            "feedback": answer_feedback_summary(answer, session["user_id"]),
        }
    )


@app.route("/forum/answer/<comment_id>/rate", methods=["POST"])
@login_required
def forum_rate_answer(comment_id):
    comments, answer = forum_answer_by_id(comment_id)
    if not answer:
        return jsonify({"success": False, "message": "Không tìm thấy câu trả lời"}), 404
    if answer.get("author_id") == session["user_id"]:
        return jsonify({"success": False, "message": "Không thể tự chấm sao câu trả lời của mình"}), 400

    payload = request.get_json() or {}
    try:
        rating = int(payload.get("rating"))
    except (TypeError, ValueError):
        rating = 0
    if rating < 1 or rating > 5:
        return jsonify({"success": False, "message": "Số sao phải từ 1 đến 5"}), 400

    normalize_answer_feedback(answer)
    answer["ratings"][str(session["user_id"])] = rating
    write_json(db.forum_comments_file, comments)

    return jsonify(
        {
            "success": True,
            "message": f"Đã chấm {rating} sao",
            "feedback": answer_feedback_summary(answer, session["user_id"]),
        }
    )


@app.route("/forum/answer/<comment_id>/discussion", methods=["POST"])
@login_required
def forum_add_answer_discussion(comment_id):
    blocked_response = forum_ban_json_response()
    if blocked_response:
        return blocked_response

    comments, answer = forum_answer_by_id(comment_id)
    if not answer:
        return jsonify({"success": False, "message": "Không tìm thấy câu trả lời"}), 404

    content = request.form.get("content", "").strip()
    if not content:
        return jsonify({"success": False, "message": "Vui lòng nhập bình luận"}), 400

    user = get_user_by_id(session["user_id"])
    normalize_answer_feedback(answer)
    answer["discussions"].append(
        {
            "id": f"discussion_{uuid.uuid4().hex[:10]}",
            "author_id": session["user_id"],
            "author_name": session.get("username", "Unknown"),
            "author_role": user.get("role", session.get("role", "student")) if user else session.get("role", "student"),
            "content": content,
            "created_at": datetime.now().isoformat(),
        }
    )
    write_json(db.forum_comments_file, comments)

    return jsonify({"success": True, "message": "Đã gửi bình luận thảo luận"})


@app.route("/forum/comment/<post_id>", methods=["POST"])
@login_required
def forum_add_comment(post_id):
    try:
        blocked_response = forum_ban_json_response()
        if blocked_response:
            return blocked_response

        post = db.get_forum_post_by_id(post_id)

        if not post:
            return jsonify({"success": False, "message": "Bài viết không tồn tại"})

        content = request.form.get("content", "").strip()

        if not content:
            return jsonify(
                {"success": False, "message": "Vui lòng nhập nội dung bình luận"}
            )

        attachments = collect_forum_attachments()

        user = get_user_by_id(session["user_id"])
        author_role = user.get("role", "student") if user else "student"
        reward_points = int(post.get("reward_points") or 0)
        existing_comments = db.get_comments_by_post(post_id)
        already_rewarded = any(
            comment.get("author_id") == session["user_id"]
            and int(comment.get("points_awarded") or 0) > 0
            for comment in existing_comments
        )
        points_awarded = 0
        if post.get("author_id") != session["user_id"] and reward_points > 0 and not already_rewarded:
            points_awarded = reward_points // 2

        comment_data = {
            "post_id": post_id,
            "author_id": session["user_id"],
            "author_name": session.get("username", "Unknown"),
            "author_role": author_role,
            "content": content,
            "attachments": attachments,
            "points_awarded": points_awarded,
            "best_bonus_awarded": 0,
            "is_best_answer": False,
            "thank_user_ids": [],
            "ratings": {},
            "discussions": [],
        }

        comment_id = db.add_comment(comment_data)

        if points_awarded:
            add_forum_points(
                session["user_id"],
                session.get("username", "Unknown"),
                author_role,
                points_awarded,
                "answer_half_reward",
                post_id=post_id,
                answer_id=comment_id,
            )

        if post.get("status") == "open":
            db.update_forum_post(post_id, {"status": "answered"})

        return jsonify(
            {
                "success": True,
                "comment_id": comment_id,
                "message": "Gửi câu trả lời thành công",
                "points_awarded": points_awarded,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})


@app.route("/forum/delete-comment/<comment_id>", methods=["POST"])
@login_required
def forum_delete_comment(comment_id):
    comments = db._load_json(db.forum_comments_file)
    comment = next((c for c in comments if c["id"] == comment_id), None)

    if not comment:
        return jsonify({"success": False, "message": "Bình luận không tồn tại"})

    if comment["author_id"] != session["user_id"] and not is_admin_account():
        return jsonify(
            {"success": False, "message": "Chỉ chủ câu trả lời hoặc admin mới được xóa bình luận này"}
        )

    for attachment in comment.get("attachments", []):
        try:
            attachment_path = attachment_storage_path(attachment)
            if attachment_path.exists():
                attachment_path.unlink()
        except:
            pass

    db.delete_comment(comment_id)

    return jsonify({"success": True, "message": "Xóa bình luận thành công"})


@app.route("/forum/accept-answer/<comment_id>", methods=["POST"])
@login_required
def forum_accept_answer(comment_id):
    comments = db._load_json(db.forum_comments_file)
    answer = next((c for c in comments if c["id"] == comment_id), None)
    if not answer:
        return jsonify({"success": False, "message": "Không tìm thấy câu trả lời"}), 404

    post = db.get_forum_post_by_id(answer["post_id"])
    if not post:
        return jsonify({"success": False, "message": "Không tìm thấy câu hỏi"}), 404
    if post.get("author_id") != session["user_id"]:
        return jsonify({"success": False, "message": "Chỉ người đặt câu hỏi mới được chọn câu hay nhất"}), 403
    if answer.get("author_id") == session["user_id"]:
        return jsonify({"success": False, "message": "Không thể tự chọn câu trả lời của chính mình"}), 400
    if post.get("status") == "resolved" or post.get("accepted_answer_id"):
        return jsonify({"success": False, "message": "Câu hỏi này đã chọn câu trả lời hay nhất"}), 400

    reward_points = int(post.get("reward_points") or 0)
    already_awarded = int(answer.get("points_awarded") or 0) + int(answer.get("best_bonus_awarded") or 0)
    bonus_points = max(0, reward_points - already_awarded)

    for comment in comments:
        if comment.get("post_id") == post["id"]:
            comment["is_best_answer"] = comment.get("id") == comment_id
            if comment.get("id") == comment_id:
                comment["best_bonus_awarded"] = int(comment.get("best_bonus_awarded") or 0) + bonus_points

    write_json(db.forum_comments_file, comments)
    db.update_forum_post(post["id"], {"status": "resolved", "accepted_answer_id": comment_id})

    if bonus_points:
        add_forum_points(
            answer["author_id"],
            answer.get("author_name", "Unknown"),
            answer.get("author_role", "student"),
            bonus_points,
            "best_answer_bonus",
            post_id=post["id"],
            answer_id=comment_id,
        )

    return jsonify({"success": True, "message": "Đã chọn câu trả lời hay nhất", "points_awarded": bonus_points})


@app.route("/forum/verify-answer/<comment_id>", methods=["POST"])
@login_required
@staff_required
def forum_verify_answer(comment_id):
    comments = db._load_json(db.forum_comments_file)
    answer = next((c for c in comments if c.get("id") == comment_id), None)
    if not answer:
        return jsonify({"success": False, "message": "Không tìm thấy câu trả lời"}), 404

    post = db.get_forum_post_by_id(answer.get("post_id"))
    if not post:
        return jsonify({"success": False, "message": "Không tìm thấy câu hỏi"}), 404
    if answer.get("is_verified_answer"):
        return jsonify({"success": False, "message": "Câu trả lời này đã được đánh giá"}), 400
    if answer.get("author_id") == session.get("user_id"):
        return jsonify({"success": False, "message": "Không thể tự xác thực câu trả lời của chính mình"}), 400

    now = datetime.now().isoformat()
    verifier = get_user_by_id(session["user_id"])
    for comment in comments:
        if comment.get("id") == comment_id:
            comment["is_verified_answer"] = True
            comment["verified_at"] = now
            comment["verified_by_id"] = session["user_id"]
            comment["verified_by_name"] = session.get("username", "Unknown")
            comment["verified_by_role"] = verifier.get("role", session.get("role", "teacher")) if verifier else session.get("role", "teacher")
            break

    write_json(db.forum_comments_file, comments)
    return jsonify({"success": True, "message": "Đã xác thực câu trả lời"})


@app.route("/forum/report", methods=["POST"])
@login_required
def forum_report():
    try:
        data = request.get_json() or {}
        target_type = data.get("target_type", "question")
        target_id = data.get("target_id")
        reason = (data.get("reason") or "").strip()
        detail = (data.get("detail") or "").strip()

        if target_type not in ("question", "answer") or not target_id or not reason:
            return jsonify({"success": False, "message": "Dữ liệu báo cáo không hợp lệ"}), 400

        reported_user_id = None
        reported_username = None
        post_id = None

        if target_type == "question":
            post = db.get_forum_post_by_id(target_id)
            if not post:
                return jsonify({"success": False, "message": "Không tìm thấy câu hỏi"}), 404
            reported_user_id = post.get("author_id")
            reported_username = post.get("author_name")
            post_id = post.get("id")
        else:
            comments = db._load_json(db.forum_comments_file)
            answer = next((c for c in comments if c.get("id") == target_id), None)
            if not answer:
                return jsonify({"success": False, "message": "Không tìm thấy câu trả lời"}), 404
            reported_user_id = answer.get("author_id")
            reported_username = answer.get("author_name")
            post_id = answer.get("post_id")

        reports = read_json(FORUM_REPORTS_FILE, [])
        report = {
            "id": f"fr_{len(reports) + 1:06d}",
            "target_type": target_type,
            "target_id": target_id,
            "post_id": post_id,
            "reason": reason,
            "detail": detail,
            "reported_user_id": reported_user_id,
            "reported_username": reported_username,
            "reporter_id": session["user_id"],
            "reporter_name": session.get("username", "Unknown"),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        reports.append(report)
        write_json(FORUM_REPORTS_FILE, reports)
        return jsonify({"success": True, "message": "Đã gửi báo cáo cho quản trị viên"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/forum/leaderboard")
@login_required
def forum_leaderboard_page():
    return render_template(
        "forum_leaderboard.html",
        leaderboard=forum_leaderboard(20),
        top5=forum_leaderboard(5),
        month=forum_month_key(),
        username=session.get("username"),
    )


@app.route("/profile")
@login_required
def my_profile():
    return redirect(url_for("forum_profile", user_id=session["user_id"]))


@app.route("/profile/basic", methods=["POST"])
@login_required
def update_profile_basic():
    users = load_users()
    user = next((record for record in users if record.get("id") == session["user_id"]), None)
    if not user:
        flash("Không tìm thấy tài khoản", "warning")
        return redirect(url_for("forum"))

    username = (request.form.get("username") or "").strip()
    full_name = " ".join((request.form.get("full_name") or "").strip().split())

    if not username:
        flash("Tên đăng nhập không được để trống", "warning")
        return redirect(url_for("my_profile"))
    if len(username) < 3 or len(username) > 30:
        flash("Tên đăng nhập cần từ 3 đến 30 ký tự", "warning")
        return redirect(url_for("my_profile"))
    if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in username):
        flash("Tên đăng nhập chỉ dùng chữ không dấu, số, dấu chấm, gạch dưới hoặc gạch ngang", "warning")
        return redirect(url_for("my_profile"))
    if len(full_name) > 80:
        flash("Họ và tên thật tối đa 80 ký tự", "warning")
        return redirect(url_for("my_profile"))
    if any(
        record.get("id") != user.get("id")
        and record.get("username", "").lower() == username.lower()
        for record in users
    ):
        flash("Tên đăng nhập này đã có người dùng", "warning")
        return redirect(url_for("my_profile"))

    user["username"] = username
    user["full_name"] = full_name
    save_users(users)
    session["username"] = username
    flash("Đã cập nhật hồ sơ", "success")
    return redirect(url_for("my_profile"))


@app.route("/profile/<user_id>")
@login_required
def forum_profile(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash("Không tìm thấy tài khoản", "warning")
        return redirect(url_for("forum"))
    stats = forum_user_stats(user_id)
    joined_at = user.get("created_at", "")
    try:
        age_days = max(1, (datetime.now() - datetime.fromisoformat(joined_at)).days + 1)
    except Exception:
        age_days = 1
    activity = forum_user_activity(user_id)
    customization = user_profile_customization(user_id)
    inventory = user_owned_items(user_id)
    equipped = user_equipped_items(user_id)
    return render_template(
        "forum_profile.html",
        profile_user=user,
        stats=stats,
        activity=activity,
        customization=customization,
        inventory=inventory,
        equipped=equipped,
        age_days=age_days,
        role_label=forum_role_label(user.get("role", "student")),
        username=session.get("username"),
    )


@app.route("/profile/<user_id>/verified")
@login_required
def forum_profile_verified_answers(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash("Không tìm thấy tài khoản", "warning")
        return redirect(url_for("forum"))

    activity = forum_user_activity(user_id, limit=200)
    return render_template(
        "forum_verified_answers.html",
        profile_user=user,
        verified_answers=activity["verified_answers"],
        username=session.get("username"),
    )


@app.route("/profile/avatar", methods=["POST"])
@login_required
def update_profile_avatar():
    file = request.files.get("avatar")
    if not file or not file.filename:
        flash("Vui lòng chọn ảnh đại diện", "warning")
        return redirect(url_for("my_profile"))

    try:
        payload = avatar_file_payload(file)
        save_user_profile_customization(
            session["user_id"],
            {
                "avatar_url": payload["url"],
                "avatar_storage_path": payload["storage_path"],
                "avatar_original_url": payload.get("original_url", payload["url"]),
                "avatar_optimized_storage_path": payload.get("optimized_storage_path", ""),
                "equipped_avatar_item_id": "",
            },
        )
        flash("Đã cập nhật avatar", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for("my_profile"))


@app.route("/shop")
@login_required
def shop():
    stats = forum_user_stats(session["user_id"])
    owned_item_ids = {record.get("item_id") for record in user_inventory_records(session["user_id"])}
    equipped = user_equipped_items(session["user_id"])
    items = []
    for item in shop_items():
        if not item.get("active", True) and item.get("id") not in owned_item_ids:
            continue
        item = dict(item)
        item["owned"] = item.get("id") in owned_item_ids
        item["equipped"] = item.get("id") in {
            equipped["profile"].get("equipped_avatar_item_id"),
            equipped["profile"].get("equipped_frame_id"),
            equipped["profile"].get("equipped_title_id"),
        }
        items.append(item)

    type_order = {"avatar": 1, "frame": 2, "title": 3, "badge": 4, "sticker": 5}
    items.sort(key=lambda item: (type_order.get(item.get("type"), 9), int(item.get("price", 0))))
    return render_template(
        "shop.html",
        items=items,
        balance=stats["points"],
        equipped=equipped,
        username=session.get("username"),
    )


@app.route("/shop/redeem/<item_id>", methods=["POST"])
@login_required
def redeem_shop_item(item_id):
    item = shop_item_by_id(item_id)
    if not item or not item.get("active", True):
        flash("Vật phẩm không tồn tại", "danger")
        return redirect(url_for("shop"))

    inventory = user_inventory_records()
    if any(record.get("user_id") == session["user_id"] and record.get("item_id") == item_id for record in inventory):
        flash("Bạn đã sở hữu vật phẩm này", "warning")
        return redirect(url_for("shop"))

    price = int(item.get("price", 0))
    balance = forum_user_stats(session["user_id"])["points"]
    if balance < price:
        flash("Bạn chưa đủ kim cương để đổi vật phẩm này", "warning")
        return redirect(url_for("shop"))

    user = get_user_by_id(session["user_id"])
    add_forum_points(
        session["user_id"],
        session.get("username", "Unknown"),
        user.get("role", "student") if user else session.get("role", "student"),
        -price,
        "shop_redeem",
    )

    now = datetime.now().isoformat()
    inventory_record = {
        "id": f"inv_{len(inventory) + 1:06d}",
        "user_id": session["user_id"],
        "item_id": item_id,
        "item_type": item.get("type"),
        "created_at": now,
    }
    inventory.append(inventory_record)
    save_user_inventory(inventory)

    orders = read_json(SHOP_ORDERS_FILE, [])
    orders.append(
        {
            "id": f"order_{len(orders) + 1:06d}",
            "user_id": session["user_id"],
            "username": session.get("username", "Unknown"),
            "item_id": item_id,
            "item_name": item.get("name"),
            "price": price,
            "created_at": now,
        }
    )
    write_json(SHOP_ORDERS_FILE, orders)

    if item.get("type") == "avatar":
        save_user_profile_customization(
            session["user_id"],
            {
                "avatar_url": item.get("image_url", ""),
                "avatar_storage_path": item.get("image_storage_path", ""),
                "equipped_avatar_item_id": item_id,
            },
        )
    elif item.get("type") == "frame":
        save_user_profile_customization(session["user_id"], {"equipped_frame_id": item_id})
    elif item.get("type") == "title":
        save_user_profile_customization(session["user_id"], {"equipped_title_id": item_id})

    flash("Đổi vật phẩm thành công", "success")
    return redirect(url_for("shop"))


@app.route("/shop/equip/<inventory_id>", methods=["POST"])
@login_required
def equip_shop_item(inventory_id):
    record = next(
        (item for item in user_inventory_records(session["user_id"]) if item.get("id") == inventory_id),
        None,
    )
    if not record:
        flash("Không tìm thấy vật phẩm trong túi đồ", "danger")
        return redirect(url_for("my_profile"))

    item = shop_item_by_id(record.get("item_id"))
    if not item:
        flash("Vật phẩm không còn tồn tại", "danger")
        return redirect(url_for("my_profile"))

    if item.get("type") == "avatar":
        if not item.get("image_url"):
            flash("Avatar này chưa có ảnh để sử dụng", "warning")
            return redirect(url_for("my_profile"))
        save_user_profile_customization(
            session["user_id"],
            {
                "avatar_url": item.get("image_url", ""),
                "avatar_storage_path": item.get("image_storage_path", ""),
                "equipped_avatar_item_id": item.get("id"),
            },
        )
        flash("Đã dùng avatar", "success")
    elif item.get("type") == "frame":
        save_user_profile_customization(session["user_id"], {"equipped_frame_id": item.get("id")})
        flash("Đã dùng khung avatar", "success")
    elif item.get("type") == "title":
        save_user_profile_customization(session["user_id"], {"equipped_title_id": item.get("id")})
        flash("Đã dùng danh hiệu", "success")
    else:
        flash("Huy hiệu sẽ tự hiển thị trên profile", "info")
    return redirect(url_for("my_profile"))


@app.route("/admin")
@login_required
@admin_required
def admin_home():
    return redirect(url_for("admin_forum_reports"))


@app.route("/admin/shop", methods=["GET", "POST"])
@login_required
@admin_required
def admin_shop():
    allowed_types = {
        "badge": "Huy hiệu",
        "frame": "Khung avatar",
        "title": "Danh hiệu",
        "avatar": "Avatar",
        "sticker": "Sticker",
    }

    if request.method == "POST":
        items = read_json(SHOP_ITEMS_FILE, [])
        items = items if isinstance(items, list) else []
        item_type = request.form.get("type", "badge").strip()
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        icon = request.form.get("icon", "◆").strip() or "◆"
        css_class = request.form.get("css_class", "").strip()
        image_url = request.form.get("image_url", "").strip()
        image_storage_path = ""
        try:
            price = max(0, int(request.form.get("price", 0)))
        except (TypeError, ValueError):
            price = 0

        if item_type not in allowed_types or not name:
            flash("Vui lòng nhập đúng loại vật phẩm và tên vật phẩm", "danger")
            return redirect(url_for("admin_shop"))

        image_file = request.files.get("image_file")
        if image_file and image_file.filename:
            try:
                image_payload = shop_asset_file_payload(image_file, item_type)
                image_url = image_payload["url"]
                image_storage_path = image_payload["storage_path"]
                original_image_url = image_payload.get("original_url", image_url)
                optimized_storage_path = image_payload.get("optimized_storage_path", "")
            except ValueError as exc:
                flash(str(exc), "danger")
                return redirect(url_for("admin_shop"))
        else:
            original_image_url = image_url
            optimized_storage_path = ""

        if item_type in {"avatar", "sticker"} and not image_url:
            flash("Avatar hoặc sticker cần có ảnh upload hoặc URL ảnh", "warning")
            return redirect(url_for("admin_shop"))

        item = {
            "id": create_shop_item_id(item_type, name, items),
            "type": item_type,
            "type_label": allowed_types[item_type],
            "name": name,
            "description": description,
            "price": price,
            "icon": icon,
            "css_class": css_class,
            "image_url": image_url,
            "image_storage_path": image_storage_path,
            "original_image_url": original_image_url,
            "optimized_storage_path": optimized_storage_path,
            "active": True,
            "created_by": session["user_id"],
            "created_at": datetime.now().isoformat(),
        }
        items.append(item)
        write_json(SHOP_ITEMS_FILE, items)
        flash("Đã tạo vật phẩm mới", "success")
        return redirect(url_for("admin_shop"))

    items = shop_items()
    items.sort(key=lambda item: (item.get("type", ""), item.get("price", 0), item.get("name", "")))
    top5 = forum_leaderboard(5)
    return render_template(
        "admin_shop.html",
        items=items,
        item_types=allowed_types,
        top5=top5,
        username=session.get("username"),
    )


@app.route("/admin/shop/<item_id>/toggle", methods=["POST"])
@login_required
@admin_required
def admin_toggle_shop_item(item_id):
    items = read_json(SHOP_ITEMS_FILE, [])
    items = items if isinstance(items, list) else []
    for item in items:
        if item.get("id") == item_id:
            item["active"] = not bool(item.get("active", True))
            item["updated_by"] = session["user_id"]
            item["updated_at"] = datetime.now().isoformat()
            write_json(SHOP_ITEMS_FILE, items)
            flash("Đã cập nhật trạng thái vật phẩm", "success")
            return redirect(url_for("admin_shop"))

    flash("Không tìm thấy vật phẩm", "danger")
    return redirect(url_for("admin_shop"))


@app.route("/admin/shop/award-top5", methods=["POST"])
@login_required
@admin_required
def admin_award_top5_shop_item():
    item_id = request.form.get("item_id", "").strip()
    item = shop_item_by_id(item_id)
    if not item:
        flash("Vui lòng chọn vật phẩm hợp lệ", "danger")
        return redirect(url_for("admin_shop"))

    top5 = forum_leaderboard(5)
    if not top5:
        flash("Chưa có dữ liệu top 5 tháng này", "warning")
        return redirect(url_for("admin_shop"))

    awarded = 0
    skipped = 0
    for user in top5:
        record, message = grant_shop_item_to_user(
            user.get("user_id"),
            item_id,
            source="admin_award_top5",
            note=f"Trao thưởng top {user.get('rank')} tháng {forum_month_key()}",
        )
        if record and message == "Đã trao vật phẩm":
            awarded += 1
        else:
            skipped += 1

    flash(f"Đã trao cho {awarded} user top 5. Bỏ qua {skipped} user đã sở hữu.", "success")
    return redirect(url_for("admin_shop"))


@app.route("/admin/forum-reports")
@login_required
@admin_required
def admin_forum_reports():
    reports = read_json(FORUM_REPORTS_FILE, [])
    reports = reports if isinstance(reports, list) else []
    status_filter = request.args.get("status", "pending")

    counts = forum_admin_report_counts(reports)
    dashboard_stats = admin_dashboard_stats(reports)
    if status_filter != "all":
        reports = [r for r in reports if r.get("status", "pending") == status_filter]

    annotated_reports = [annotate_forum_report(report) for report in reports]
    annotated_reports.sort(key=lambda item: item.get("created_at", ""), reverse=True)

    active_bans = []
    for ban in forum_ban_records():
        active_ban = forum_active_ban(ban.get("user_id"))
        if ban.get("status") != "active" or not active_ban or active_ban.get("id") != ban.get("id"):
            continue
        ban = dict(ban)
        ban["created_at_formatted"] = format_datetime(ban.get("created_at", ""))
        ban["banned_until_formatted"] = (
            "Vĩnh viễn" if ban.get("ban_type") == "permanent" else format_datetime(ban.get("banned_until", ""))
        )
        active_bans.append(ban)
    active_bans.sort(key=lambda item: item.get("created_at", ""), reverse=True)

    return render_template(
        "admin_forum_reports.html",
        reports=annotated_reports,
        active_bans=active_bans,
        counts=counts,
        stats=dashboard_stats,
        status_filter=status_filter,
        username=session.get("username"),
    )


@app.route("/admin/forum-reports/<report_id>/status", methods=["POST"])
@login_required
@admin_required
def admin_update_forum_report_status(report_id):
    reports = read_json(FORUM_REPORTS_FILE, [])
    reports = reports if isinstance(reports, list) else []
    new_status = request.form.get("status", "pending")
    if new_status not in FORUM_REPORT_STATUSES:
        flash("Trạng thái báo cáo không hợp lệ", "danger")
        return redirect(url_for("admin_forum_reports"))

    for report in reports:
        if report.get("id") == report_id:
            report["status"] = new_status
            report["admin_note"] = request.form.get("admin_note", "").strip()
            report["reviewed_by"] = session["user_id"]
            report["reviewed_at"] = datetime.now().isoformat()
            write_json(FORUM_REPORTS_FILE, reports)
            flash("Đã cập nhật báo cáo", "success")
            return redirect(url_for("admin_forum_reports", status=new_status))

    flash("Không tìm thấy báo cáo", "danger")
    return redirect(url_for("admin_forum_reports"))


@app.route("/admin/forum-bans", methods=["POST"])
@login_required
@admin_required
def admin_create_forum_ban():
    user_id = request.form.get("user_id", "").strip()
    report_id = request.form.get("report_id", "").strip()
    duration = request.form.get("duration", "24h")
    reason = request.form.get("reason", "").strip() or "Vi phạm quy định cộng đồng"

    user = get_user_by_id(user_id)
    if not user:
        flash("Không tìm thấy tài khoản cần chặn", "danger")
        return redirect(url_for("admin_forum_reports"))
    if is_admin_account(user):
        flash("Không thể chặn tài khoản quản trị viên", "danger")
        return redirect(url_for("admin_forum_reports"))

    now = datetime.now()
    if duration == "permanent":
        ban_type = "permanent"
        banned_until = None
    else:
        ban_type = "24h"
        banned_until = (now + timedelta(hours=24)).isoformat()

    bans = forum_ban_records()
    for ban in bans:
        if ban.get("user_id") == user_id and ban.get("status") == "active":
            ban["status"] = "replaced"
            ban["replaced_at"] = now.isoformat()

    ban = {
        "id": f"fb_{len(bans) + 1:06d}",
        "user_id": user_id,
        "username": user.get("username", "Unknown"),
        "role": user.get("role", "student"),
        "ban_type": ban_type,
        "banned_until": banned_until,
        "reason": reason,
        "source_report_id": report_id,
        "status": "active",
        "banned_by": session["user_id"],
        "banned_by_name": session.get("username", "admin"),
        "created_at": now.isoformat(),
    }
    bans.append(ban)
    save_forum_ban_records(bans)

    if report_id:
        reports = read_json(FORUM_REPORTS_FILE, [])
        for report in reports:
            if report.get("id") == report_id:
                report["status"] = "resolved"
                report["admin_note"] = f"Đã chặn {ban['username']} ({'vĩnh viễn' if ban_type == 'permanent' else '24h'})."
                report["reviewed_by"] = session["user_id"]
                report["reviewed_at"] = now.isoformat()
                break
        write_json(FORUM_REPORTS_FILE, reports)

    flash("Đã chặn tài khoản khỏi chat/diễn đàn", "success")
    return redirect(url_for("admin_forum_reports", status="pending"))


@app.route("/admin/forum-bans/<ban_id>/lift", methods=["POST"])
@login_required
@admin_required
def admin_lift_forum_ban(ban_id):
    bans = forum_ban_records()
    for ban in bans:
        if ban.get("id") == ban_id:
            if ban.get("status") != "active":
                flash("Lệnh chặn này không còn hiệu lực", "warning")
                return redirect(url_for("admin_forum_reports", status="all"))
            ban["status"] = "lifted"
            ban["lifted_by"] = session["user_id"]
            ban["lifted_by_name"] = session.get("username", "admin")
            ban["lifted_at"] = datetime.now().isoformat()
            save_forum_ban_records(bans)
            flash("Đã gỡ chặn tài khoản", "success")
            return redirect(url_for("admin_forum_reports", status="all"))

    flash("Không tìm thấy lệnh chặn", "danger")
    return redirect(url_for("admin_forum_reports", status="all"))


def format_datetime(iso_string):
    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%d/%m/%Y %H:%M")
    except:
        return iso_string


#######
@app.route("/chat")
@login_required
def chat_room():
    messages = db.get_all_chat_messages()

    for msg in messages:
        msg["created_at_formatted"] = format_datetime(msg["created_at"])

    return render_template(
        "chat_room.html", messages=messages, username=session.get("username")
    )


@app.route("/api/chat/send", methods=["POST"])
@login_required
def send_chat_message():
    try:
        blocked_response = forum_ban_json_response()
        if blocked_response:
            return blocked_response

        data = request.get_json()
        content = data.get("content", "").strip()
        reply_to = data.get("reply_to")

        if not content:
            return jsonify(
                {"success": False, "message": "Nội dung không được để trống"}
            )

        user = get_user_by_id(session["user_id"])

        message_data = {
            "content": content,
            "author_id": session["user_id"],
            "author_name": session.get("username", "Unknown"),
            "author_role": user.get("role", "student") if user else "student",
            "reply_to": reply_to,
        }

        message_id = db.add_chat_message(message_data)
        message = db.get_chat_message_by_id(message_id)
        message["created_at_formatted"] = format_datetime(message["created_at"])

        return jsonify({"success": True, "message": message})

    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})


@app.route("/api/chat/messages")
@login_required
def get_chat_messages():
    try:
        last_id = request.args.get("last_id", "")
        messages = db.get_chat_messages_after(last_id)

        for msg in messages:
            msg["created_at_formatted"] = format_datetime(msg["created_at"])

        return jsonify({"success": True, "messages": messages})

    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})


@app.route("/api/chat/delete/<message_id>", methods=["POST"])
@login_required
def delete_chat_message(message_id):
    try:
        message = db.get_chat_message_by_id(message_id)

        if not message:
            return jsonify({"success": False, "message": "Tin nhắn không tồn tại"})

        if message["author_id"] != session["user_id"]:
            return jsonify(
                {"success": False, "message": "Bạn không có quyền xóa tin nhắn này"}
            )

        db.delete_chat_message(message_id)

        return jsonify({"success": True, "message": "Đã xóa tin nhắn"})

    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})


################
# game

# ============ QUẢN LÝ CÂU HỎI GAME (GIÁO VIÊN) ============


def normalize_game_bank(raw=None):
    raw = raw if raw is not None else read_json(QUESTIONS_FILE, {"topics": []})
    if isinstance(raw, dict) and isinstance(raw.get("topics"), list):
        topics = raw.get("topics", [])
    else:
        topics = []

    normalized_topics = []
    for index, topic in enumerate(topics, 1):
        if not isinstance(topic, dict):
            continue
        title = (topic.get("title") or "").strip()
        grade = (topic.get("grade") or "").strip()
        topic_id = (topic.get("id") or f"topic_{index:04d}").strip()
        questions = []
        for question in topic.get("questions", []):
            if not isinstance(question, dict):
                continue
            options = question.get("options") or []
            if not isinstance(options, list):
                continue
            answer = question.get("answer")
            question_text = (question.get("question") or "").strip()
            if question_text and len(options) >= 2 and answer in options:
                questions.append(
                    {
                        "question": question_text,
                        "options": [str(option) for option in options[:4]],
                        "answer": str(answer),
                        "difficulty": int(question.get("difficulty") or 1),
                    }
                )
        if topic_id and title and grade:
            normalized_topics.append(
                {
                    "id": topic_id,
                    "title": title,
                    "grade": grade,
                    "created_by": topic.get("created_by", ""),
                    "created_by_name": topic.get("created_by_name", ""),
                    "created_at": topic.get("created_at", datetime.now().isoformat()),
                    "questions": questions,
                }
            )
    return {"topics": normalized_topics}


def save_game_bank(bank):
    write_json(QUESTIONS_FILE, normalize_game_bank(bank))


def game_topics():
    return normalize_game_bank().get("topics", [])


def find_game_topic(topic_id):
    return next((topic for topic in game_topics() if topic.get("id") == topic_id), None)


def slugify_game_topic(title, grade):
    base = f"{grade}-{title}".lower()
    safe = "".join(ch if ch.isalnum() else "-" for ch in base)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe[:48] or uuid.uuid4().hex[:10]


@app.route("/teacher/game_questions")
@login_required
@teacher_required
def teacher_game_questions():
    """Trang quản lý câu hỏi game cho giáo viên"""
    topics = game_topics()
    return render_template("teacher_game_questions.html", topics=topics, forum_grades=FORUM_GRADES)


@app.route("/teacher/game_questions/add", methods=["POST"])
@login_required
@teacher_required
def teacher_add_game_question():
    """Thêm câu hỏi game mới"""
    try:
        topic_title = request.form.get("topic_title", "").strip()
        grade = request.form.get("grade", "").strip()
        question_text = request.form.get("question", "").strip()
        option_a = request.form.get("option_a", "").strip()
        option_b = request.form.get("option_b", "").strip()
        option_c = request.form.get("option_c", "").strip()
        option_d = request.form.get("option_d", "").strip()
        answer = request.form.get("answer", "").strip()

        if not all([topic_title, grade, question_text, option_a, option_b, option_c, option_d, answer]):
            flash("Vui lòng điền đầy đủ thông tin câu hỏi", "danger")
            return redirect(url_for("teacher_game_questions"))

        if grade not in FORUM_GRADES:
            flash("Lớp không hợp lệ. Chỉ hỗ trợ lớp 6, 7, 8, 9", "danger")
            return redirect(url_for("teacher_game_questions"))

        if answer not in [option_a, option_b, option_c, option_d]:
            flash("Đáp án đúng phải trùng với một trong 4 lựa chọn", "danger")
            return redirect(url_for("teacher_game_questions"))

        bank = normalize_game_bank()
        topics = bank["topics"]
        topic = next(
            (
                item
                for item in topics
                if item.get("title", "").casefold() == topic_title.casefold()
                and item.get("grade") == grade
            ),
            None,
        )
        if not topic:
            topic_id = f"topic_{slugify_game_topic(topic_title, grade)}_{uuid.uuid4().hex[:6]}"
            topic = {
                "id": topic_id,
                "title": topic_title,
                "grade": grade,
                "created_by": session.get("user_id", ""),
                "created_by_name": session.get("username", "Giáo viên"),
                "created_at": datetime.now().isoformat(),
                "questions": [],
            }
            topics.append(topic)

        new_question = {
            "question": question_text,
            "options": [option_a, option_b, option_c, option_d],
            "answer": answer,
            "difficulty": 1,
        }
        topic["questions"].append(new_question)

        save_game_bank(bank)

        flash(f"Đã thêm câu hỏi vào chủ đề {topic_title}", "success")
        return redirect(url_for("teacher_game_questions"))

    except Exception as e:
        flash(f"Lỗi: {str(e)}", "danger")
        return redirect(url_for("teacher_game_questions"))


@app.route("/teacher/game_questions/delete", methods=["POST"])
@login_required
@teacher_required
def teacher_delete_game_question():
    """Xóa câu hỏi game"""
    try:
        topic_id = request.form.get("topic_id", "")
        index = int(request.form.get("index", -1))

        bank = normalize_game_bank()
        topic = next((item for item in bank["topics"] if item.get("id") == topic_id), None)

        if topic and 0 <= index < len(topic.get("questions", [])):
            topic["questions"].pop(index)
            if not topic["questions"]:
                bank["topics"] = [item for item in bank["topics"] if item.get("id") != topic_id]
            save_game_bank(bank)
            flash("Đã xóa câu hỏi!", "success")
        else:
            flash("Không tìm thấy câu hỏi cần xóa", "danger")

        return redirect(url_for("teacher_game_questions"))
    except Exception as e:
        flash(f"Lỗi: {str(e)}", "danger")
        return redirect(url_for("teacher_game_questions"))


# ============ GAME (HỌC SINH) ============


@app.route("/enter_nickname")
@login_required
def enter_nickname():
    topics = [topic for topic in game_topics() if topic.get("questions")]
    return render_template("nickname.html", topics=topics, username=session.get("username"))


@app.route("/start_game", methods=["POST"])
@login_required
def start_game():
    topic_id = request.form.get("topic_id", "").strip()
    topic = find_game_topic(topic_id)
    if not topic or not topic.get("questions"):
        flash("Chủ đề game không tồn tại hoặc chưa có câu hỏi", "warning")
        return redirect(url_for("enter_nickname"))
    session["game_topic_id"] = topic_id
    return redirect("/game")


@app.route("/game")
@login_required
def game():
    topic = find_game_topic(session.get("game_topic_id", ""))
    if not topic or not topic.get("questions"):
        return redirect("/enter_nickname")
    return render_template("game.html", topic=topic, username=session.get("username"))


@app.route("/get_questions")
@login_required
def get_questions():
    topic = find_game_topic(session.get("game_topic_id", ""))
    questions = [dict(question) for question in (topic or {}).get("questions", [])]
    random.shuffle(questions)
    for q in questions:
        q["options"] = list(q.get("options", []))
        random.shuffle(q["options"])
    return jsonify(questions[:20])


@app.route("/submit_score", methods=["POST"])
@login_required
def submit_score():
    topic_id = session.get("game_topic_id")
    topic = find_game_topic(topic_id)
    payload_data = request.get_json(silent=True) or {}
    try:
        score = max(0, int(payload_data.get("score") or 0))
        total = max(0, int(payload_data.get("total") or 0))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid score"}), 400

    if not topic:
        return jsonify({"status": "error", "message": "No topic found"})

    scores = read_json(SCORES_FILE, [])
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    existing = next(
        (
            s
            for s in scores
            if s.get("user_id") == session["user_id"]
            and s.get("topic_id") == topic_id
        ),
        None,
    )

    payload = {
        "user_id": session["user_id"],
        "username": session.get("username", "Người chơi"),
        "score": score,
        "total": total,
        "time": now,
        "topic_id": topic_id,
        "topic_title": topic.get("title", ""),
        "grade": topic.get("grade", ""),
    }

    if existing:
        if score > int(existing.get("score", 0)) or (
            score == int(existing.get("score", 0)) and total > int(existing.get("total", 0))
        ):
            existing.update(payload)
    else:
        scores.append(payload)

    filtered = [s for s in scores if s.get("topic_id") == topic_id]
    top50 = sorted(
        filtered,
        key=lambda x: (int(x.get("score", 0)), int(x.get("total", 0))),
        reverse=True,
    )[:50]

    others = [s for s in scores if s.get("topic_id") != topic_id]
    final_scores = others + top50

    write_json(SCORES_FILE, final_scores)

    return jsonify({"status": "ok"})


@app.route("/leaderboard")
@login_required
def leaderboard():
    topic_id = session.get("game_topic_id", "")
    topic = find_game_topic(topic_id)

    scores = read_json(SCORES_FILE, [])
    filtered = [s for s in scores if s.get("topic_id") == topic_id]
    top5 = sorted(
        filtered,
        key=lambda x: (int(x.get("score", 0)), int(x.get("total", 0))),
        reverse=True,
    )[:10]

    return render_template("leaderboard.html", players=top5, topic=topic)


# Nếu cần giữ cả hai, đổi tên route
@app.route("/chatbot")
@login_required
def chatbot():
    """
    Hien thi trang chatbot
    """
    return render_template(
        "chatbot.html", username=session.get("username"), user_role=session.get("role")
    )


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    """
    API chat - xử lý cả text và ảnh
    """
    try:
        blocked_response = forum_ban_json_response()
        if blocked_response:
            return blocked_response

        # Kiểm tra Content-Type
        is_json = request.content_type and "application/json" in request.content_type

        # Kiểm tra có file ảnh không
        has_image = "image" in request.files
        image_data = None

        if has_image:
            file = request.files["image"]

            if file and file.filename:
                # Validate định dạng
                allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}
                file_ext = (
                    file.filename.rsplit(".", 1)[1].lower()
                    if "." in file.filename
                    else ""
                )

                if file_ext not in allowed_extensions:
                    return jsonify(
                        {
                            "success": False,
                            "error": "Chỉ chấp nhận ảnh: PNG, JPG, JPEG, GIF, WEBP",
                        }
                    ), 400

                # Đọc ảnh
                image_data = file.read()

                # Kiểm tra kích thước (max 10MB)
                if len(image_data) > 10 * 1024 * 1024:
                    return jsonify(
                        {"success": False, "error": "Ảnh quá lớn. Tối đa 10MB"}
                    ), 400

        # Lấy message - ưu tiên form, fallback về JSON
        if is_json:
            user_message = request.get_json().get("message", "").strip()
        else:
            user_message = request.form.get("message", "").strip()

        if not user_message and not image_data:
            return jsonify(
                {"success": False, "error": "Vui lòng nhập tin nhắn hoặc gửi ảnh"}
            ), 400

        if user_message and not image_data and is_quiz_request(user_message):
            quiz = generate_math_quiz(user_message)
            response = f"Mình đã tạo {len(quiz['questions'])} câu trắc nghiệm. Bạn làm trực tiếp bên dưới nhé."
            processed = {
                "text": response,
                "svgs": [],
                "mermaids": [],
                "has_diagrams": False,
            }

            chat_message_id = db.add_chat_message(
                {
                    "content": user_message,
                    "author_id": session["user_id"],
                    "author_name": session["username"],
                    "author_role": session.get("role", "student"),
                    "response": response,
                    "processed": processed,
                    "quiz": quiz,
                    "has_diagrams": False,
                    "has_image": False,
                }
            )

            return jsonify(
                {
                    "success": True,
                    "response": response,
                    "processed": processed,
                    "quiz": quiz,
                    "chat_message_id": chat_message_id,
                }
            )

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
        chat_message_id = db.add_chat_message(
            {
                "content": user_message if user_message else "[Đã gửi ảnh]",
                "author_id": session["user_id"],
                "author_name": session["username"],
                "author_role": session.get("role", "student"),
                "response": response,
                "processed": processed,
                "has_diagrams": processed["has_diagrams"],
                "has_image": bool(image_data),
            }
        )

        return jsonify({
            "success": True,
            "response": response,
            "processed": processed,
            "chat_message_id": chat_message_id,
        })

    except Exception as e:
        print(f"Lỗi chat API: {str(e)}")
        import traceback

        traceback.print_exc()
        return jsonify(
            {
                "success": False,
                "error": "Có lỗi xảy ra khi xử lý tin nhắn",
                "details": str(e),
            }
        ), 500


@app.route("/api/chat/history", methods=["GET"])
@login_required
def get_chat_history():
    """
    Lay lich su chat cua user
    """
    try:
        user_id = session["user_id"]
        messages = db.get_all_chat_messages()

        # Filter AI chat records cua user. Chat room messages share the same file.
        user_messages = [
            m for m in messages
            if m.get("author_id") == user_id and (m.get("response") or m.get("quiz"))
        ]

        return jsonify({"success": True, "messages": user_messages[-50:]})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/chat/quiz-submit", methods=["POST"])
@login_required
def submit_chat_quiz():
    """
    Luu ket qua lam quiz trong chatbot de user mo lai van thay diem.
    """
    try:
        data = request.get_json() or {}
        message_id = data.get("message_id")
        answers = data.get("answers", [])

        if not message_id or not isinstance(answers, list):
            return jsonify({"success": False, "error": "Du lieu nop bai khong hop le"}), 400

        message = db.get_chat_message_by_id(message_id)
        if not message or message.get("author_id") != session["user_id"]:
            return jsonify({"success": False, "error": "Khong tim thay bai quiz"}), 404

        quiz = message.get("quiz") or {}
        questions = quiz.get("questions") or []
        if not questions:
            return jsonify({"success": False, "error": "Bai quiz khong hop le"}), 400

        normalized_answers = []
        score = 0
        for index, question in enumerate(questions):
            answer = answers[index] if index < len(answers) else None
            try:
                answer = int(answer) if answer is not None else None
            except (TypeError, ValueError):
                answer = None

            if answer is not None and (answer < 0 or answer > 3):
                answer = None

            correct_index = int(question.get("correct_index"))
            is_correct = answer == correct_index
            if is_correct:
                score += 1

            normalized_answers.append({
                "answer": answer,
                "correct_index": correct_index,
                "is_correct": is_correct,
            })

        total = len(questions)
        quiz_result = {
            "answers": normalized_answers,
            "score": score,
            "total": total,
            "percent": round((score / total) * 100) if total else 0,
            "submitted_at": datetime.now().isoformat(),
        }

        db.update_chat_message(message_id, {"quiz_result": quiz_result})

        return jsonify({"success": True, "quiz_result": quiz_result})

    except Exception as e:
        print(f"Loi luu ket qua quiz: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/chat/clear", methods=["POST"])
@login_required
def clear_chat():
    """
    Xoa lich su chat
    """
    try:
        # Logic xoa chat o day
        return jsonify({"success": True, "message": "Da xoa lich su chat"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


###############
@app.route("/logout_old")  # Đổi URL
def logout_old():
    session.clear()
    return redirect("/login")


##############
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    os.makedirs("static/css", exist_ok=True)
    os.makedirs("static/js", exist_ok=True)
    os.makedirs("templates", exist_ok=True)

    app.run(debug=True, host="0.0.0.0", port=5000)

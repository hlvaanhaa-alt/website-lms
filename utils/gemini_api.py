import google.generativeai as genai
from dotenv import load_dotenv
import re
import json
from PIL import Image
import io
import os

# Cấu hình API key
load_dotenv()

# Lấy API key từ biến môi trường
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    raise ValueError(" Không tìm thấy GEMINI_API_KEY trong file .env")

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = 'gemini-2.5-flash'

SYSTEM_PROMPT_BASE = """
Bạn là trợ lý AI cho học sinh THCS Việt Nam.

QUY TẮC PHẢN HỒI - BẮT BUỘC:

0. NGẮN GỌN, ĐẦY ĐỦ:
   - Trả lời thẳng vào vấn đề, KHÔNG dài dòng mở đầu
   - Giải bài toán: trình bày các bước cần thiết, KHÔNG giải thích thừa
   - KHÔNG lặp lại câu hỏi của học sinh
   - KHÔNG kết thúc bằng "Nếu bạn cần thêm thông tin..." hay câu tương tự
   - Mỗi câu trả lời nên ngắn nhất có thể mà vẫn đúng và đủ ý

1. MỌI công thức toán phải nằm RIÊNG BIỆT trên dòng mới:

   SAI:
   "Giải phương trình 2x + 3 = 7, ta có x = 2"

   ĐÚNG:
   "Giải phương trình

   $$2x + 3 = 7$$

   Ta có

   $$x = 2$$"

2. HỆ PHƯƠNG TRÌNH - Format chuẩn:

   $$\\begin{cases}
   2x + y = 7 \\\\
   x - y = 2
   \\end{cases}$$

   CHÚ Ý:
   - Dùng 2 dấu \\\\ (4 backslash) giữa các dòng
   - Mỗi phương trình trên 1 dòng riêng
   - KHÔNG thêm số thứ tự (1), (2) trong cases

3. CÚ PHÁP LATEX:
   - Phân số: \\frac{tử}{mẫu}
   - Lũy thừa: x^2 hoặc x^{10}
   - Chỉ số dưới: x_1 hoặc x_{10}
   - Căn bậc hai: \\sqrt{x}
   - Nhân: \\times hoặc \\cdot
   - Chia: \\div

4. INLINE MATH ($...$):
   - CHỈ dùng cho số/biến đơn giản trong câu: "với $x = 3$"
   - KHÔNG dùng cho công thức phức tạp

5. QUY TẮC QUAN TRỌNG:
   - Sau mỗi $$...$$ phải có dòng trống
   - TUYỆT ĐỐI KHÔNG trộn công thức với text:
     ❌ "Bước 1: $$x = 2$$ nên ta có..."
     ✅ "Bước 1:

     $$x = 2$$

     Vậy ta có..."

6. VẼ HÌNH:
   - Hình học/mạch điện/đồ thị: Dùng SVG trong ```svg ... ```
   - Sơ đồ tư duy: Dùng Mermaid trong ```mermaid ... ```
   - Luôn giải thích trước và sau khi vẽ

7. FORMAT VĂN BẢN:
   - KHÔNG dùng markdown **, __, # trong văn bản thường
   - KHÔNG dùng icon, emoji không cần thiết
   - Viết rõ ràng, dễ hiểu, phù hợp học sinh THCS
6. VẼ HÌNH VÀ SƠ ĐỒ:
   
   A. HÌNH HỌC/MẠCH ĐIỆN/ĐỒ THỊ → SVG:
```svg
   <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
     <circle cx="100" cy="100" r="50" fill="lightblue" stroke="black"/>
   </svg>
```

   B. SƠ ĐỒ TƯ DUY → MERMAID MINDMAP:
   
   **CÚ PHÁP CHUẨN:**
```mermaid
   mindmap
     root((Chủ đề chính))
       Nhánh 1
         Chi tiết 1.1
         Chi tiết 1.2
       Nhánh 2
         Chi tiết 2.1
```

   **QUY TẮC BẮT BUỘC:**
   - Dòng đầu PHẢI là `mindmap`
   - Node gốc: `root((text))` - dùng 2 ngoặc tròn
   - Thụt đầu dòng: 2 SPACES mỗi cấp (KHÔNG dùng tab)
   - KHÔNG dùng dấu `:` trong tên node
   - KHÔNG dùng `()` `[]` `{}` trong text (trừ root)
   - Text tiếng Việt viết bình thường, không cần escape
   - Mỗi node trên 1 dòng riêng
   - **LỖI THƯỜNG GẶP CẦN TRÁNH:**
     ❌ `root(Chủ đề)` → thiếu ngoặc kép
     ❌ Thụt bằng tab → dùng spaces
     ❌ `Tác giả: Tô Hữu` → có dấu `:`
     ❌ `Năm (1954)` → có dấu ngoặc

   **VÍ DỤ HOÀN CHỈNH:**
```mermaid
   mindmap
     root((Bài thơ Việt Bắc))
       Tác giả Tô Hữu
         Nhà thơ cách mạng
         Sinh năm 1920
       Hoàn cảnh sáng tác
         Kháng chiến chống Pháp
         Năm 1954
       Nội dung
         Cảnh đẹp thiên nhiên
         Con người Việt Bắc
         Tinh thần kháng chiến
       Nghệ thuật
         Ngôn ngữ giản dị
         Hình ảnh sinh động
```

   C. LUÔN GIẢI THÍCH:
   - Viết text giới thiệu TRƯỚC khi vẽ
   - Giải thích ý nghĩa SAU khi vẽ
   
   D. KHI NÀO VẼ SƠ ĐỒ TƯ DUY:
   - Học sinh hỏi "vẽ sơ đồ tư duy về..."
   - Cần tổng hợp kiến thức có cấu trúc
   - Phân tích tác phẩm văn học, sự kiện lịch sử
"""


# ==================== CORE FUNCTIONS ====================

def chat_with_gemini(user_message, chat_history=None):
    """
    Chat với Gemini AI (có hỗ trợ context)
    
    Args:
        user_message (str): Câu hỏi của học sinh
        chat_history (list, optional): Lịch sử chat [{'role': 'user/model', 'parts': ['...']}]
    
    Returns:
        str: Phản hồi từ AI
    """
    try:
        if not user_message or not user_message.strip():
            return "Vui lòng nhập câu hỏi."
            
        model = genai.GenerativeModel(
            MODEL_NAME,
            system_instruction=SYSTEM_PROMPT_BASE,
            generation_config={
                "temperature": 0.3,
                "top_p": 1,
                "top_k": 1,
                "max_output_tokens": 1024,
            }
        )
        
        if chat_history:
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(user_message)
        else:
            response = model.generate_content(user_message)
        
        response_text = response.text
        
        # DEBUG: In ra để kiểm tra
        print("=" * 60)
        print("RAW RESPONSE (first 500 chars):")
        print(response_text[:500])
        print("=" * 60)
        
        formatted = format_latex(response_text)
        
        print("AFTER FORMAT (first 500 chars):")
        print(formatted[:500])
        print("=" * 60)
        
        return formatted
    
    except Exception as e:
        print(f"❌ Error in chat_with_gemini: {str(e)}")
        return f"❌ Lỗi: {str(e)}"


def process_response(response_text):
    """
    Tách text và diagrams từ response
    
    Returns:
        dict: {
            'text': str,
            'svgs': list,
            'mermaids': list,
            'has_diagrams': bool
        }
    """
    svg_pattern = r'```svg\s*(.*?)\s*```'
    mermaid_pattern = r'```mermaid\s*(.*?)\s*```'
    
    svgs = re.findall(svg_pattern, response_text, re.DOTALL)
    mermaids = re.findall(mermaid_pattern, response_text, re.DOTALL)
    
    clean_text = response_text
    for svg in svgs:
        clean_text = re.sub(r'```svg\s*' + re.escape(svg) + r'\s*```', '', clean_text, flags=re.DOTALL)
    for mermaid in mermaids:
        clean_text = re.sub(r'```mermaid\s*' + re.escape(mermaid) + r'\s*```', '', clean_text, flags=re.DOTALL)
    
    return {
        'text': clean_text.strip(),
        'svgs': [svg.strip() for svg in svgs],
        'mermaids': [m.strip() for m in mermaids],
        'has_diagrams': len(svgs) > 0 or len(mermaids) > 0
    }


def format_latex(text):
    """
    Format LaTeX ổn định cho KaTeX.
    Bảo toàn mọi môi trường LaTeX quan trọng và tránh trùng lặp $$.
    """
    import re

    # 1. Chuẩn hoá xuống dòng
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # ======================================================
    # 2. CHUẨN HÓA NỘI DUNG CASES (Hệ phương trình)
    # ======================================================
    def clean_cases_internal(match):
        content = match.group(1).strip()
        # Thay thế \\, \\\\, \n, và \ bằng newline duy nhất để split
        content = re.sub(r"\\\\+|\\(?!\w)|\n+", "\n", content)
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        return " \\\\\n".join(lines)

    # Làm sạch nội dung bên trong cases nhưng CHƯA bọc $$ tại đây
    text = re.sub(
        r"\\begin\{cases\}(.*?)\\end\{cases\}",
        lambda m: f"\\begin{{cases}}\n{clean_cases_internal(m)}\n\\end{{cases}}",
        text,
        flags=re.DOTALL
    )

    # ======================================================
    # 3. CHUYỂN \[ ... \] thành dạng chuẩn của display math
    # ======================================================
    text = re.sub(r"\\\[(.*?)\\\]", r"$$\n\1\n$$", text, flags=re.DOTALL)

    # ======================================================
    # 4. CHUYỂN \( ... \) thành inline math chuẩn
    # ======================================================
    text = re.sub(r"\\\((.*?)\\\)", r"$\1$", text)

    # ======================================================
    # 5. GIẢI QUYẾT TRÙNG LẶP VÀ ĐẢM BẢO $$ BAO QUANH
    # ======================================================
    
    # Chuẩn hóa khoảng trắng quanh các block quan trọng
    text = re.sub(r"\s*(\\begin\{(cases|align|matrix|array)\}.*?\\end\{\2\})\s*", r"\n\n\1\n\n", text, flags=re.DOTALL)
    
    # Xử lý trường hợp đã có $$ bao quanh: $$ \begin... $$ -> Chuẩn hóa về 1 giao diện duy nhất
    text = re.sub(r"\$\$\s*(\\begin\{(cases|align|matrix|array)\}.*?\\end\{\2\})\s*\$\$", r"TEMP_DISPLAY_START\1TEMP_DISPLAY_END", text, flags=re.DOTALL)

    # Bao quanh các block môi trường CHƯA có $$ bằng $$
    text = re.sub(r"(?<!TEMP_DISPLAY_START)(\\begin\{(cases|align|matrix|array)\}.*?\\end\{\2\})(?!TEMP_DISPLAY_END)", r"$$\n\1\n$$", text, flags=re.DOTALL)
    
    # Trả lại $$ từ TEMP
    text = text.replace("TEMP_DISPLAY_START", "\n\n$$\n").replace("TEMP_DISPLAY_END", "\n$$\n\n")

    # Đảm bảo display math ($$ ... $$) chuẩn
    text = re.sub(r"\$\$(.*?)\$\$", lambda m: f"\n\n$$\n{m.group(1).strip()}\n$$\n\n", text, flags=re.DOTALL)

    # ======================================================
    # 6. INLINE MATH ($ ... $)
    # ======================================================
    # Tương tự như cũ, chỉ xử lý phần text ngoài $$
    parts = text.split("$$")
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"\$(?!\$)([^$]+?)\$(?!\$)", lambda m: f"${m.group(1).strip()}$", parts[i])
    text = "$$".join(parts)

    # ======================================================
    # 7. DỌN DẸP CUỐI
    # ======================================================
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Xử lý trường hợp bot trả về \\ \\ (lỗi user nêu) còn sót lại
    text = text.replace("\\ \\", "\\\\")
    
    return text.strip() + "\n"


# ==================== EXAM ANALYSIS ====================

def analyze_exam_results(exam_data):
    """
    Phân tích kết quả bài thi bằng AI
    
    Args:
        exam_data (dict): {
            'subject_name': str,
            'exam_title': str,
            'score': float,
            'correct_count': int,
            'total_questions': int,
            'wrong_answers': list,
            'time_spent_seconds': int
        }
    
    Returns:
        dict: {
            'success': bool,
            'overall_assessment': str,
            'strengths': str,
            'weaknesses': str,
            'study_plan': str,
            'encouragement': str,
            'error': str (nếu có)
        }
    """
    try:
        subject_name = exam_data.get('subject_name', 'Môn học')
        exam_title = exam_data.get('exam_title', 'Bài kiểm tra')
        score = exam_data.get('score', 0)
        correct_count = exam_data.get('correct_count', 0)
        total_questions = exam_data.get('total_questions', 0)
        wrong_answers = exam_data.get('wrong_answers', [])
        time_spent = exam_data.get('time_spent_seconds', 0)
        
        percentage = round((correct_count / total_questions * 100), 1) if total_questions > 0 else 0
        
        # Tạo danh sách câu sai (tối đa 5 câu)
        wrong_list = ""
        if wrong_answers:
            for idx, wrong in enumerate(wrong_answers[:5], 1):
                wrong_list += f"""
{idx}. Câu {wrong['question_number']}: {wrong['question_text']}
    Học sinh chọn: {wrong['user_answer']}
    Đáp án đúng: {wrong['correct_answer']}
"""
            if len(wrong_answers) > 5:
                wrong_list += f"\n... và {len(wrong_answers) - 5} câu sai khác\n"
        else:
            wrong_list = "✓ Học sinh làm đúng tất cả!"
        
        # Xác định xếp loại
        if score >= 9:
            level = "Xuất sắc 🏆"
        elif score >= 8:
            level = "Giỏi ⭐"
        elif score >= 6.5:
            level = "Khá 👍"
        elif score >= 5:
            level = "Trung bình 📚"
        else:
            level = "Cần cố gắng 💪"
        
        prompt = f"""
Bạn là giáo viên {subject_name} giàu kinh nghiệm, tận tâm với học sinh THCS.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 THÔNG TIN BÀI THI:
• Môn: {subject_name} - {exam_title}
• Điểm: {score}/10 ({percentage}%)
• Đúng: {correct_count}/{total_questions}
• Xếp loại: {level}
• Thời gian: {time_spent // 60}p {time_spent % 60}s

📝 CÁC CÂU SAI:
{wrong_list}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NHIỆM VỤ: Phân tích chi tiết, cụ thể, động viên học sinh.

YÊU CẦU:
1. ĐÁNH GIÁ TỔNG QUAN (3-4 câu): Nhận xét điểm số, thời gian, ấn tượng chung
2. ĐIỂM MẠNH (3-4 điểm): Kiến thức đã nắm vững, kỹ năng thành thạo
3. ĐIỂM YẾU (3-4 điểm): Phân tích lỗi cụ thể, nguyên nhân
4. KẾ HOẠCH HỌC TẬP (4-5 bước): Lộ trình cải thiện rõ ràng
5. LỜI ĐỘNG VIÊN (2-3 câu): Khích lệ tinh thần

QUY TẮC:
✓ Thân thiện, gần gũi, phù hợp THCS (12-15 tuổi)
✓ Cụ thể, dễ hiểu, ít thuật ngữ chuyên môn
✓ Sử dụng emoji phù hợp
✓ Động viên và tôn trọng học sinh

TRẢ LỜI ĐÚNG ĐỊNH DẠNG JSON (KHÔNG thêm ```json):
{{
  "overall_assessment": "...",
  "strengths": "...",
  "weaknesses": "...",
  "study_plan": "...",
  "encouragement": "..."
}}
"""
        
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        
        # Parse JSON
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()
        
        analysis = json.loads(result_text)
        
        # Validate
        required_fields = ['overall_assessment', 'strengths', 'weaknesses', 'study_plan', 'encouragement']
        for field in required_fields:
            if field not in analysis:
                analysis[field] = f"(Đang cập nhật...)"
        
        return {
            'success': True,
            **analysis
        }
        
    except json.JSONDecodeError as e:
        return {
            'success': False,
            'error': 'AI trả về định dạng không hợp lệ'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


# ==================== ESSAY GRADING ====================

def grade_essay_with_ai(user_essay, question, subject):
    """
    Chấm bài tự luận bằng AI
    
    Args:
        user_essay (str): Bài làm của học sinh
        question (dict): {'question': str, 'grading_rubric': dict, 'keywords': list}
        subject (str): Môn học
    
    Returns:
        dict: {
            'content': {'score': 0-10, 'feedback': '...'},
            'language': {'score': 0-10, 'feedback': '...'},
            'structure': {'score': 0-10, 'feedback': '...'},
            'overall_feedback': '...'
        }
    """
    try:
        rubric = question.get('grading_rubric', {})
        keywords = question.get('keywords', [])
        
        prompt = f"""
Bạn là giáo viên môn {subject}. Chấm bài tự luận sau:

**CÂU HỎI:** {question['question']}

**BÀI LÀM:**
{user_essay}

**TIÊU CHÍ CHẤM:**
"""
        for criterion, config in rubric.items():
            prompt += f"\n{criterion.upper()} ({config.get('weight_percent', 0)}%):"
            for c in config.get('criteria', []):
                prompt += f"\n  - {c}"
        
        prompt += f"""

**TỪ KHÓA QUAN TRỌNG:** {', '.join(keywords)}

TRẢ LỜI JSON (KHÔNG thêm ```json):
{{
  "content": {{"score": 0-10, "feedback": "..."}},
  "language": {{"score": 0-10, "feedback": "..."}},
  "structure": {{"score": 0-10, "feedback": "..."}},
  "overall_feedback": "Tổng kết 2-3 câu"
}}
"""
        
        model = genai.GenerativeModel(
            MODEL_NAME,
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 1024,
            }
        )
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()
        
        return json.loads(result_text)
    
    except Exception as e:
        print(f"❌ Lỗi AI: {e}")
        return {
            'content': {'score': 5, 'feedback': 'Lỗi hệ thống'},
            'language': {'score': 5, 'feedback': 'Lỗi hệ thống'},
            'structure': {'score': 5, 'feedback': 'Lỗi hệ thống'},
            'overall_feedback': 'Không thể chấm bài. Vui lòng liên hệ giáo viên.'
        }
###############
# THÊM hàm mới này vào gemini_api.py
def chat_with_gemini_image(user_message, image_data=None):
    """
    Chat với Gemini - hỗ trợ cả text và ảnh
    
    Args:
        user_message (str): Tin nhắn của user
        image_data (bytes): Dữ liệu ảnh dạng bytes
    
    Returns:
        str: Phản hồi từ AI
    """
    try:
        model = genai.GenerativeModel(
            MODEL_NAME,
            system_instruction=SYSTEM_PROMPT_BASE,
            generation_config={
                "temperature": 0.4,
                "top_p": 1,
                "top_k": 32,
                "max_output_tokens": 2048,
            }
        )
        
        if image_data:
            # Xử lý ảnh
            image = Image.open(io.BytesIO(image_data))
            
            # Resize nếu quá lớn
            max_dimension = 1024
            if max(image.size) > max_dimension:
                ratio = max_dimension / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # Gửi cả text và ảnh
            if user_message and user_message.strip():
                response = model.generate_content([user_message, image])
            else:
                response = model.generate_content(["Hãy mô tả và phân tích ảnh này chi tiết", image])
        else:
            # Chỉ text
            response = model.generate_content(user_message)
        
        return format_latex(response.text)
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return f"❌ Lỗi khi xử lý: {str(e)}"

# ==================== TEST ====================

if __name__ == "__main__":
    print("=== Test chat cơ bản ===")
    response = chat_with_gemini("Công thức tính diện tích hình tròn?")
    print(response)
    print("\n" + "="*50 + "\n")
    
    print("=== Test giải hệ phương trình ===")
    response = chat_with_gemini("Giải hệ phương trình: 2x + y = 7 và x - y = 2")
    print(response)
    print("\n" + "="*50 + "\n")
    
    print("=== Test vẽ hình ===")
    response = chat_with_gemini("Vẽ tam giác vuông có cạnh 3cm và 4cm")
    processed = process_response(response)
    print("Text:", processed['text'][:150])
    print("Số SVG:", len(processed['svgs']))
    print("Có diagram:", processed['has_diagrams'])
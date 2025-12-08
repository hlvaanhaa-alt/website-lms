import google.generativeai as genai
import re
import json
# Cấu hình API key
GEMINI_API_KEY = "AIzaSyBkLdxy3pn3gHmXcm9Z2aW0cxr9XXKpVsg"
genai.configure(api_key=GEMINI_API_KEY)

def chat_with_gemini(user_message):
    """
    Gửi tin nhắn đến Gemini AI và nhận phản hồi
    CO CHUC NANG VE HINH
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        system_prompt = """
        Bạn là trợ lý AI cho học sinh THCS Việt Nam.
        
        QUAN TRONG - BAT BUOC PHAI TUAN THU:
        Khi trả lời câu hỏi về toán, vật lý, hóa học, bạn PHẢI viết công thức theo định dạng LaTeX:
        - Công thức block (riêng dòng): $$công_thức$$
        - Công thức inline (trong câu): $công_thức$
        
        CU PHAP LATEX:
        - Phân số: \\frac{tử}{mẫu}
        - Lũy thừa: x^2
        - Chỉ số dưới: x_1
        
        VI DU CU THE:
        
        Học sinh hỏi: "công thức động năng"
        Bạn PHẢI trả lời:
        
        Công thức động năng:
        
        $$W_đ = \\frac{1}{2}mv^2$$
        
        Trong đó:
        - $W_đ$ là động năng (J)
        - $m$ là khối lượng (kg)  
        - $v$ là vận tốc (m/s)
        
        TUYET DOI KHONG viết: "Wđ = 1/2 * m * v²"
        PHẢI viết: $$W_đ = \\frac{1}{2}mv^2$$
        
        KHI HOC SINH YEU CAU VE HINH:
        
        1. HINH HOC (tam giác, tứ giác, hình tròn...):
           - Trả về code SVG hoàn chỉnh
           - Đặt trong ```svg ... ```
           - Vẽ chính xác theo số đo
           - Thêm label cho các đỉnh, cạnh
           
           VI DU:
           ```svg
           <svg width="400" height="400" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
             <polygon points="200,50 100,350 300,350" fill="none" stroke="#d946ef" stroke-width="2"/>
             <text x="200" y="40" text-anchor="middle" fill="#7c3aed" font-size="18" font-weight="bold">A</text>
             <text x="90" y="370" text-anchor="middle" fill="#7c3aed" font-size="18" font-weight="bold">B</text>
             <text x="310" y="370" text-anchor="middle" fill="#7c3aed" font-size="18" font-weight="bold">C</text>
           </svg>
           ```
        
        2. SO DO MACH DIEN:
           - Vẽ các linh kiện: pin, bóng đèn, điện trở, công tắc
           - Dùng ký hiệu chuẩn
           - Hiển thị giá trị (6V, 3 ohm, 2A...)
           - Dùng SVG
           
           KY HIEU CHUAN:
           - Pin: Hai vạch song song (dài-ngắn)
           - Bóng đèn: Hình tròn có dây tóc
           - Điện trở: Hình chữ nhật răng cưa
           - Công tắc: Đường gấp khúc
           - Dây dẫn: Đường thẳng
           
           VI DU:
           ```svg
           <svg width="500" height="300" viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
             <line x1="50" y1="150" x2="150" y2="150" stroke="#333" stroke-width="2"/>
             <rect x="150" y="130" width="20" height="40" fill="none" stroke="#333" stroke-width="2"/>
             <line x1="155" y1="130" x2="165" y2="170" stroke="#333" stroke-width="2"/>
             <text x="160" y="120" text-anchor="middle" fill="#333" font-size="14">6V</text>
             <line x1="170" y1="150" x2="250" y2="150" stroke="#333" stroke-width="2"/>
             <circle cx="280" cy="150" r="25" fill="none" stroke="#333" stroke-width="2"/>
             <line x1="270" y1="160" x2="290" y2="140" stroke="#333" stroke-width="1.5"/>
             <line x1="305" y1="150" x2="400" y2="150" stroke="#333" stroke-width="2"/>
           </svg>
           ```
        
        3. DO THI HAM SO:
           - Vẽ hệ trục tọa độ Oxy
           - Vẽ đường biểu diễn hàm số
           - Đánh dấu các điểm đặc biệt
           - Ghi chú phương trình
           
           VI DU:
           ```svg
           <svg width="400" height="400" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
             <line x1="50" y1="350" x2="350" y2="350" stroke="#333" stroke-width="2"/>
             <line x1="50" y1="350" x2="50" y2="50" stroke="#333" stroke-width="2"/>
             <text x="360" y="355" fill="#333" font-size="16">x</text>
             <text x="45" y="40" fill="#333" font-size="16">y</text>
             <path d="M 50,350 Q 200,50 350,350" fill="none" stroke="#d946ef" stroke-width="2"/>
             <text x="200" y="30" text-anchor="middle" fill="#d946ef" font-size="14">y = x^2</text>
           </svg>
           ```
        
        4. SO DO TU DUY / FLOWCHART:
           - Dùng Mermaid diagram syntax
           - Đặt trong ```mermaid ... ```
           - Cấu trúc rõ ràng, logic
           
           VI DU:
           ```mermaid
           graph TD
             A[Quang hợp] --> B[Điều kiện]
             A --> C[Sản phẩm]
             B --> D[Ánh sáng]
             B --> E[Nước]
             B --> F[CO2]
             C --> G[Glucose]
             C --> H[O2]
           ```
        
        QUY TAC QUAN TRONG:
        - LUON giải thích trước khi vẽ
        - Code SVG/Mermaid phải HOAN CHINH, có thể render ngay
        - KHONG dùng ảnh external, chỉ dùng code SVG
        - Màu sắc đẹp: #d946ef, #a855f7, #ec4899, #7c3aed
        - Kích thước hợp lý: 300-500px
        - Sau khi vẽ, giải thích chi tiết về hình vẽ
        
        KHONG DUOC:
        - Trả về link ảnh
        - Yêu cầu học sinh tự vẽ
        - Code SVG sai cú pháp
        - Quên đóng thẻ SVG
        
        Không dùng dấu ** __ # trong văn bản.
        Không dùng icon, emoji.
        """
        
        full_prompt = f"{system_prompt}\n\nCâu hỏi của học sinh: {user_message}"
        
        response = model.generate_content(full_prompt)
        
        return response.text
    
    except Exception as e:
        return f"Xin lỗi, có lỗi xảy ra: {str(e)}"

def chat_with_context(user_message, chat_history=[]):
    """
    Chat với context (lịch sử hội thoại)
    """
    try:
        model = genai.GenerativeModel(
            'gemini-2.0-flash-exp',
            generation_config={
                'temperature': 0.7,
            },
            system_instruction="""
            Bạn là trợ lý AI cho học sinh THCS Việt Nam.
            
            BAT BUOC:
            - Công thức toán học PHẢI dùng LaTeX: $$công_thức$$
            - Không dùng markdown **, __, #, ```
            - Không dùng icon, emoji
            
            VI DU: $$\\rho = \\frac{m}{V}$$
            
            KHI HOC SINH YEU CAU VE HINH:
            - Hình học: Trả về SVG trong ```svg ... ```
            - Mạch điện: Trả về SVG với ký hiệu chuẩn
            - Đồ thị: Trả về SVG với trục tọa độ
            - Sơ đồ tư duy: Trả về Mermaid trong ```mermaid ... ```
            
            LUON giải thích trước và sau khi vẽ hình.
            """
        )
        
        chat = model.start_chat(history=[])
        
        for msg in chat_history:
            if msg['role'] == 'user':
                chat.send_message(msg['content'])
        
        response = chat.send_message(user_message)
        
        return response.text
    
    except Exception as e:
        return f"Xin lỗi, có lỗi xảy ra: {str(e)}"


# Ham xu ly response de tach text va diagram
def process_response(response_text):
    """
    Tách text và diagrams từ response của Gemini
    Return: {
        'text': str,
        'svgs': list,
        'mermaids': list,
        'has_diagrams': bool
    }
    """
    # Tìm SVG
    svg_pattern = r'```svg\s*(.*?)\s*```'
    svgs = re.findall(svg_pattern, response_text, re.DOTALL)
    
    # Tìm Mermaid
    mermaid_pattern = r'```mermaid\s*(.*?)\s*```'
    mermaids = re.findall(mermaid_pattern, response_text, re.DOTALL)
    
    # Loại bỏ code blocks khỏi text
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

###############
def analyze_exam_results(exam_data):
    """
     HÀM MỚI: Phân tích kết quả bài thi bằng AI Gemini
    
    Args:
        exam_data (dict): {
            'subject': 'toan',
            'subject_name': 'Toán',
            'exam_title': 'Đề thi học kỳ 1',
            'score': 8.5,
            'correct_count': 17,
            'total_questions': 20,
            'wrong_answers': [
                {
                    'question_number': 5,
                    'question_text': 'Tính đạo hàm của x^2?',
                    'user_answer': 'A. x',
                    'correct_answer': 'B. 2x',
                    'explanation': '...'
                }
            ],
            'time_spent_seconds': 720
        }
    
    Returns:
        dict: {
            'success': True/False,
            'overall_assessment': 'Đánh giá tổng quan...',
            'strengths': 'Điểm mạnh...',
            'weaknesses': 'Điểm yếu...',
            'study_plan': 'Kế hoạch học tập...',
            'encouragement': 'Lời động viên...',
            'error': 'Lỗi nếu có'
        }
    """
    try:
        print(" [AI Analysis] Bắt đầu phân tích bài thi...")
        
        # Lấy thông tin từ exam_data
        subject_name = exam_data.get('subject_name', 'Môn học')
        exam_title = exam_data.get('exam_title', 'Bài kiểm tra')
        score = exam_data.get('score', 0)
        correct_count = exam_data.get('correct_count', 0)
        total_questions = exam_data.get('total_questions', 0)
        wrong_answers = exam_data.get('wrong_answers', [])
        time_spent = exam_data.get('time_spent_seconds', 0)
        
        # Tính phần trăm
        percentage = round((correct_count / total_questions * 100), 1) if total_questions > 0 else 0
        
        # Tạo danh sách câu sai (chỉ lấy 5 câu đầu để prompt không quá dài)
        wrong_list = ""
        if wrong_answers:
            for idx, wrong in enumerate(wrong_answers[:5], 1):
                wrong_list += f"""
{idx}. Câu {wrong['question_number']}: {wrong['question_text']}
    Học sinh chọn: {wrong['user_answer']}
    Đáp án đúng: {wrong['correct_answer']}
    Giải thích: {wrong.get('explanation', 'Không có giải thích')}
"""
            
            if len(wrong_answers) > 5:
                wrong_list += f"\n... và {len(wrong_answers) - 5} câu sai khác\n"
        else:
            wrong_list = " Học sinh làm đúng tất cả các câu! Xuất sắc!"
        
        # Xác định mức độ
        if score >= 9:
            level = "Xuất sắc"
            emoji = "🏆"
        elif score >= 8:
            level = "Giỏi"
            emoji = "⭐"
        elif score >= 6.5:
            level = "Khá"
            emoji = "👍"
        elif score >= 5:
            level = "Trung bình"
            emoji = "📚"
        else:
            level = "Yếu"
            emoji = "💪"
        
        print(f" [AI Analysis] Điểm: {score}/10 - Xếp loại: {level}")
        
        # Tạo prompt cho AI
        prompt = f"""
Bạn là một giáo viên {subject_name} giàu kinh nghiệm, tận tâm và am hiểu tâm lý học sinh THCS (12-15 tuổi).

 THÔNG TIN BÀI THI:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Môn học: {subject_name}
• Đề thi: {exam_title}
• Điểm số: {score}/10 ({percentage}%)
• Số câu đúng: {correct_count}/{total_questions}
• Xếp loại: {level} {emoji}
• Thời gian làm bài: {time_spent // 60} phút {time_spent % 60} giây

 CÁC CÂU SAI:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{wrong_list}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NHIỆM VỤ CỦA BẠN:
Hãy phân tích kết quả bài thi một cách CHI TIẾT, CỤ THỂ và ĐỘNG VIÊN học sinh. 

YÊU CẦU PHÂN TÍCH:

1. **ĐÁNH GIÁ TỔNG QUAN** (3-4 câu):
   - Nhận xét về điểm số và mức độ hoàn thành
   - Đánh giá thời gian làm bài (nhanh/chậm/vừa phải)
   - Ấn tượng tổng thể về bài làm

2. **ĐIỂM MẠNH** (3-4 điểm cụ thể):
   - Những phần kiến thức học sinh đã nắm vững
   - Kỹ năng đã thành thạo
   - Điểm đáng khen ngợi trong cách làm bài


3. **ĐIỂM YẾU** (3-4 điểm cụ thể):
   - Phân tích CỤ THỂ từng loại lỗi dựa trên các câu sai
   - Xác định kiến thức còn thiếu
   - Nguyên nhân có thể dẫn đến sai (hiểu nhầm khái niệm, tính nhẩm sai, đọc đề không kỹ...)


4. **KẾ HOẠCH HỌC TẬP** (4-5 bước CỤ THỂ):
   - Bước 1: Ôn lại kiến thức cơ bản về... (cụ thể chủ đề)
   - Bước 2: Làm bài tập về... (gợi ý loại bài tập)
   - Bước 3: Xem video/đọc tài liệu về... (nếu cần)
   - Bước 4: Luyện thêm đề thi tương tự
   - Bước 5: Nhờ thầy/cô giải đáp thắc mắc về...


5. **LỜI ĐỘNG VIÊN** (2-3 câu):
   - Khích lệ tinh thần học sinh
   - Tin tưởng vào khả năng tiến bộ
   - Động viên không ngừng cố gắng
   

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

QUY TẮC QUAN TRỌNG:
 Viết bằng tiếng Việt có dấu
 Giọng văn thân thiện, gần gũi, như đang nói chuyện trực tiếp với học sinh
 Cụ thể, dễ hiểu, tránh dùng thuật ngữ quá chuyên môn
 Luôn ĐỘNG VIÊN và TÔN TRỌNG học sinh
 Phù hợp với độ tuổi THCS (12-15 tuổi)
 Sử dụng emoji phù hợp để tạo cảm giác thân thiện
 Nếu học sinh làm rất tốt (>9 điểm), hãy khen ngợi nhiệt tình!
 Nếu học sinh làm chưa tốt (<5 điểm), hãy động viên và đưa ra lộ trình cải thiện rõ ràng

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ĐỊNH DẠNG TRẢ LỜI:
Trả lời CHÍNH XÁC theo định dạng JSON sau (KHÔNG thêm markdown ```json, KHÔNG thêm giải thích):

{{
  "overall_assessment": "Nội dung đánh giá tổng quan ở đây (3-4 câu)",
  "strengths": "Nội dung điểm mạnh ở đây (3-4 điểm, mỗi điểm 1 dòng, bắt đầu bằng emoji)",
  "weaknesses": "Nội dung điểm yếu ở đây (3-4 điểm, mỗi điểm 1 dòng, bắt đầu bằng emoji)",
  "study_plan": "Nội dung kế hoạch học tập ở đây (4-5 bước, mỗi bước 1 dòng, bắt đầu bằng emoji)",
  "encouragement": "Nội dung động viên ở đây (2-3 câu)"
}}
"""
        
        print(" [AI Analysis] Đang gửi request đến Gemini API...")
        
        # Gọi Gemini API
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        
        print(" [AI Analysis] Nhận được response từ Gemini")
        print(f" [AI Analysis] Response length: {len(result_text)} ký tự")
        
        # Parse JSON từ response
        # Loại bỏ markdown code block nếu có
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
            print(" [AI Analysis] Đã loại bỏ ```json markers")
        elif '```' in result_text:
            # Tìm JSON trong code block
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result_text, re.DOTALL)
            if json_match:
                result_text = json_match.group(1).strip()
                print(" [AI Analysis] Đã extract JSON từ code block")
            else:
                result_text = result_text.split('```')[1].split('```')[0].strip()
                print(" [AI Analysis] Đã loại bỏ ``` markers")
        
        # Parse JSON
        analysis = json.loads(result_text)
        
        print(" [AI Analysis] Parse JSON thành công")
        
        # Validate các trường bắt buộc
        required_fields = ['overall_assessment', 'strengths', 'weaknesses', 'study_plan', 'encouragement']
        for field in required_fields:
            if field not in analysis or not analysis[field]:
                print(f" [AI Analysis] Thiếu trường: {field}")
                analysis[field] = f"(Đang cập nhật {field}...)"
        
        print(" [AI Analysis] Phân tích thành công!")
        
        return {
            'success': True,
            'overall_assessment': analysis.get('overall_assessment', ''),
            'strengths': analysis.get('strengths', ''),
            'weaknesses': analysis.get('weaknesses', ''),
            'study_plan': analysis.get('study_plan', ''),
            'encouragement': analysis.get('encouragement', '')
        }
        
    except json.JSONDecodeError as e:
        print(f" [AI Analysis] Lỗi parse JSON: {e}")
        if 'result_text' in locals():
            print(f" [AI Analysis] Response text (500 ký tự đầu):")
            print(result_text[:500])
        
        return {
            'success': False,
            'error': 'AI trả về định dạng không hợp lệ',
            'raw_response': result_text[:500] if 'result_text' in locals() else ''
        }
    
    except Exception as e:
        print(f" [AI Analysis] Lỗi không mong muốn: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'success': False,
            'error': str(e)
        }
#########
def grade_essay_with_ai(user_essay, question, subject):
    """
    Chấm bài tự luận bằng Gemini AI
    
    Args:
        user_essay (str): Bài làm của học sinh
        question (dict): Thông tin câu hỏi
        subject (str): Môn học
    
    Returns:
        dict: Kết quả chấm điểm {criterion: {score, feedback}, ...}
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
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
            prompt += f"\n{criterion.upper()} ({config.get('weight_percent')}%):"
            for c in config.get('criteria', []):
                prompt += f"\n  - {c}"
        
        prompt += f"""

**TỪ KHÓA:** {', '.join(keywords)}

Trả về JSON:
{{
  "content": {{"score": 0-10, "feedback": "..."}},
  "language": {{"score": 0-10, "feedback": "..."}},
  "structure": {{"score": 0-10, "feedback": "..."}},
  "overall_feedback": "Tổng kết 2-3 câu"
}}
"""
        
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        
        # Parse JSON
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()
        
        result = json.loads(result_text)
        return result
    
    except Exception as e:
        print(f"❌ Lỗi AI: {e}")
        # Trả về điểm mặc định
        return {
            'content': {'score': 5, 'feedback': 'Lỗi hệ thống'},
            'language': {'score': 5, 'feedback': 'Lỗi hệ thống'},
            'structure': {'score': 5, 'feedback': 'Lỗi hệ thống'},
            'overall_feedback': 'Không thể chấm bài. Vui lòng liên hệ giáo viên.'
        }

# Test
if __name__ == "__main__":
    print("=== Test ve hinh hoc ===")
    response = chat_with_gemini("Vẽ tam giác vuông có cạnh góc vuông 3cm và 4cm")
    print(response)
    print("\n" + "="*50 + "\n")
    
    processed = process_response(response)
    print("Text:", processed['text'][:200])
    print("SVGs:", len(processed['svgs']))
    print("Mermaids:", len(processed['mermaids']))
    print("Has diagrams:", processed['has_diagrams'])
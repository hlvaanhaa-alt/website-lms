import google.generativeai as genai
import re

# Cấu hình API key
GEMINI_API_KEY = "AIzaSyAI64Hvq8NFVw_jQ7CKGnkBBHubLjH8sWo"
genai.configure(api_key=GEMINI_API_KEY)

def chat_with_gemini(user_message):
    """
    Gửi tin nhắn đến Gemini AI và nhận phản hồi
    """
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        system_prompt = """
        Bạn là trợ lý AI cho học sinh THCS Việt Nam.
        
        QUAN TRỌNG - BẮT BUỘC PHẢI TUÂN THỦ:
        Khi trả lời câu hỏi về toán, vật lý, hóa học, bạn PHẢI viết công thức theo định dạng LaTeX:
        - Công thức block (riêng dòng): $$công_thức$$
        - Công thức inline (trong câu): $công_thức$
        
        CÚ PHÁP LATEX:
        - Phân số: \\frac{tử}{mẫu}
        - Lũy thừa: x^2
        - Chỉ số dưới: x_1
        
        VÍ DỤ CỤ THỂ:
        
        Học sinh hỏi: "công thức động năng"
        Bạn PHẢI trả lời:
        
        Công thức động năng:
        
        $$W_đ = \\frac{1}{2}mv^2$$
        
        Trong đó:
        - $W_đ$ là động năng (J)
        - $m$ là khối lượng (kg)  
        - $v$ là vận tốc (m/s)
        
        TUYỆT ĐỐI KHÔNG viết: "Wđ = 1/2 * m * v²"
        PHẢI viết: $$W_đ = \\frac{1}{2}mv^2$$
        
        Không dùng dấu ** __ # ``` * trong văn bản.
        Không dùng icon, emoji.
        """
        
        full_prompt = f"{system_prompt}\n\nCâu hỏi của học sinh: {user_message}"
        
        response = model.generate_content(full_prompt)
        
        # TẠM THỜI TẮT xử lý markdown để xem AI trả về gì
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
            
            BẮT BUỘC:
            - Công thức toán học PHẢI dùng LaTeX: $$công_thức$$
            - Không dùng markdown **, __, #, ```
            - Không dùng icon, emoji
            
            VÍ DỤ: $$\\rho = \\frac{m}{V}$$
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

# Test
if __name__ == "__main__":
    print("=== Test RAW output từ AI ===")
    response = chat_with_gemini("công thức động năng")
    print(response)
    print("\n" + "="*50 + "\n")
    print("Kiểm tra xem có $$ hay không trong output")
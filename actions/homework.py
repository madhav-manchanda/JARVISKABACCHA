import os
import urllib.request
import textwrap
import logging
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
from config import CONFIG
import uuid

logger = logging.getLogger(__name__)

FONTS = {
    "cursive": "https://github.com/google/fonts/raw/main/ofl/caveat/Caveat-Regular.ttf",
    "neat": "https://github.com/google/fonts/raw/main/ofl/patrickhand/PatrickHand-Regular.ttf",
    "messy": "https://github.com/google/fonts/raw/main/ofl/shadowsintolight/ShadowsIntoLight.ttf",
    "default": "https://github.com/google/fonts/raw/main/ofl/indieflower/IndieFlower-Regular.ttf"
}

def _download_fonts():
    os.makedirs("data/fonts", exist_ok=True)
    for name, url in FONTS.items():
        path = f"data/fonts/{name}.ttf"
        if not os.path.exists(path):
            try:
                urllib.request.urlretrieve(url, path)
            except Exception as e:
                logger.warning(f"Failed to download font {name}: {e}")

def analyze_handwriting_style(image_path: str) -> str:
    """Uses Gemini Vision to analyze the handwriting style and map it to our fonts."""
    try:
        genai.configure(api_key=CONFIG.get_active_llm_key())
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        sample_file = genai.upload_file(path=image_path)
        prompt = "Analyze the handwriting in this image. Is it 'cursive', 'neat', or 'messy'? Respond with ONLY ONE of those three words."
        
        response = model.generate_content([sample_file, prompt])
        style = response.text.strip().lower()
        
        # Clean up the file on Google's servers
        genai.delete_file(sample_file.name)
        
        if "cursive" in style:
            return "cursive"
        if "neat" in style:
            return "neat"
        if "messy" in style:
            return "messy"
        return "default"
    except Exception as e:
        logger.error(f"Error analyzing handwriting: {e}")
        return "default"

def generate_homework_image(text: str, style: str) -> str:
    """Generates an image of the text written on notebook paper."""
    _download_fonts()
    
    # 1. Create a blank piece of notebook paper
    width, height = 800, 1000
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    
    # Draw horizontal blue lines
    line_spacing = 40
    for y in range(80, height, line_spacing):
        draw.line([(0, y), (width, y)], fill=(150, 200, 255), width=2)
        
    # Draw vertical red margin
    margin_x = 100
    draw.line([(margin_x, 0), (margin_x, height)], fill=(255, 150, 150), width=2)
    
    # 2. Setup Font
    font_path = f"data/fonts/{style}.ttf"
    if not os.path.exists(font_path):
        font_path = f"data/fonts/default.ttf"
    
    try:
        font = ImageFont.truetype(font_path, 32)
    except IOError:
        font = ImageFont.load_default()
        
    # 3. Write Text
    start_x = margin_x + 20
    start_y = 80 - 32  # align baseline near the line
    
    # Wrap text to fit width
    chars_per_line = 45 # rough estimate
    lines = textwrap.wrap(text, width=chars_per_line)
    
    current_y = start_y
    for line in lines:
        if current_y > height - 40:
            break # out of space
        # Add slight randomness to y to simulate real handwriting
        import random
        y_offset = random.randint(-2, 2)
        draw.text((start_x, current_y + y_offset), line, font=font, fill=(10, 10, 50))
        current_y += line_spacing
        
    # 4. Save and return
    os.makedirs("downloads", exist_ok=True)
    filename = f"homework_{uuid.uuid4().hex[:8]}.jpg"
    filepath = os.path.join("downloads", filename)
    img.save(filepath)
    
    return f"/downloads/{filename}"

async def process_homework(image_bytes: bytes, text: str) -> dict:
    """Main entrypoint for homework route"""
    os.makedirs("downloads", exist_ok=True)
    temp_img_path = os.path.join("downloads", f"temp_{uuid.uuid4().hex[:8]}.jpg")
    
    try:
        with open(temp_img_path, "wb") as f:
            f.write(image_bytes)
            
        style = analyze_handwriting_style(temp_img_path)
        output_url = generate_homework_image(text, style)
        
        return {
            "success": True,
            "image_url": output_url,
            "style": style
        }
    finally:
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)

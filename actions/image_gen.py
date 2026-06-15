import urllib.parse

def generate_image(prompt: str, ratio: str = "square") -> dict:
    """
    Generates an image based on a prompt using Pollinations.ai.
    """
    encoded_prompt = urllib.parse.quote(prompt)
    
    width, height = 1024, 1024
    if ratio == "wide":
        width, height = 1280, 720
    elif ratio == "tall":
        width, height = 720, 1280

    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"
    
    return {
        "success": True,
        "image_url": image_url,
        "message": f"I have generated the image for you."
    }

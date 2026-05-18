import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))
from app.services.gemini_service import get_gemini_service

async def main():
    try:
        service = get_gemini_service()
        print("Testing text generation...")
        res = await service.generate("Say hello")
        print(f"Result: {res}")
        
        print("Testing structured generation...")
        res2 = await service.generate_structured("Return JSON with a key 'message' saying hello. Also wrap in ```json block.")
        print(f"Result JSON: {res2}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

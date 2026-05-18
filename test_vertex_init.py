import asyncio
import os
import sys

# Add src to python path so app imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from app.services.gemini_service import get_gemini_service
from app.core.config import get_settings

async def main():
    print("Testing Gemini Client Initialization...")
    settings = get_settings()
    print(f"GOOGLE_CLOUD_PROJECT: {settings.GOOGLE_CLOUD_PROJECT}")
    print(f"GOOGLE_CLOUD_LOCATION: {settings.GOOGLE_CLOUD_LOCATION}")
    
    try:
        service = get_gemini_service()
        client = service.client
        
        # In the new google-genai SDK, the client structure is a bit different,
        # but if we initialized without error, that's a good sign.
        print("\nSUCCESS! Gemini service initialized properly.")
        print(f"Client object: {type(client)}")
        
        if settings.GOOGLE_CLOUD_PROJECT:
             print("It is using Vertex AI mode.")
        else:
             print("It is using API key mode.")
             
    except Exception as e:
        print(f"\nERROR initializing Gemini service:")
        print(e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
from google import genai

from dotenv import load_dotenv
load_dotenv()

async def main():
    print("Project:", os.getenv('GOOGLE_CLOUD_PROJECT'))
    print("Location:", os.getenv('GOOGLE_CLOUD_LOCATION'))
    
    try:
        client = genai.Client(
            vertexai=True,
            project=os.getenv('GOOGLE_CLOUD_PROJECT'),
            location=os.getenv('GOOGLE_CLOUD_LOCATION')
        )
        print("Client init success.")

        config = {
            "response_modalities": ["AUDIO"]
        }
        
        async with client.aio.live.connect(model="gemini-live-2.5-flash-native-audio", config=config) as session:
            print("Connected!")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 

import asyncio
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from app.services.voice_service import get_voice_service
from app.core.prompts import get_prompt_manager

async def test_voice():
    with open("voice_test_out.txt", "w") as f:
        try:
            f.write("Starting test...\n")
            service = get_voice_service()
            f.write("Service created.\n")
            
            # Start session
            f.write("Starting session...\n")
            # We must pass the context expected by the voice service
            # Let's mock a simple context
            context = {
               "fullName": {"display": "Full Name", "description": "The doctor's full name", "required": True}
            }
            session, greeting = await service.start_session(language="en", context=context)
            f.write(f"Greeting: {greeting}\n")
            
            # Process message
            f.write("Sending transcript...\n")
            updated_session, ai_response = await service.process_message(
                session_id=session.session_id,
                user_message="My name is Dr. John Doe, I'm ready.",
                context=context
            )
            f.write(f"AI Response: {ai_response}\n")
            f.write(f"Collected Data: {updated_session.collected_data}\n")
            f.write("DONE successfully.\n")
        except Exception as e:
            f.write(f"ERROR: {e}\n")
            import traceback
            f.write(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(test_voice())

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai.types import FunctionResponse

from ..core.config import get_settings
from ..core.logger import logger, session_context, cost_tracker
from .voice_tools import get_update_form_tool
from ..core.prompts import get_prompt_manager


class GeminiLiveService:
    """
    Manages the real-time WebSocket connection proxying to the Gemini Live API.
    
    Attributes:
        websocket (WebSocket): The client WebSocket connection.
        context (Dict[str, Any]): The state and context of the onboarding form.
        settings (Any): The application configuration settings.
        model_id (Optional[str]): The specific Gemini model ID to use.
        client (genai.Client): The Google GenAI client instance.
    """
    
    def __init__(self, websocket: WebSocket, context: Optional[Dict[str, Any]] = None) -> None:
        self.websocket = websocket
        self.context = context or {}
        self.settings = get_settings()
        self.model_id = getattr(self.settings, "GEMINI_MODEL")
        
        # Determine whether to use Vertex AI or AI Studio
        use_vertex = False
        if getattr(self.settings, "GOOGLE_APPLICATION_CREDENTIALS", None):
            import os
            cred_path = self.settings.GOOGLE_APPLICATION_CREDENTIALS
            if os.path.exists(cred_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
                use_vertex = True
                
        # Vertex AI doesn't support gemini-3.1 yet, so fallback to AI Studio if that model is requested
        if self.model_id and "gemini-3.1" in self.model_id and getattr(self.settings, "GOOGLE_API_KEY", None):
            use_vertex = False
            
        if use_vertex:
            self.client = genai.Client(
                vertexai=True,
                project=self.settings.GOOGLE_CLOUD_PROJECT,
                location=self.settings.GOOGLE_CLOUD_LOCATION,
                http_options={'api_version': 'v1beta1'}
            )
            # Vertex AI expects no prefix
            if self.model_id.startswith("models/"):
                self.model_id = self.model_id.replace("models/", "")
        else:
            self.client = genai.Client(api_key=self.settings.GOOGLE_API_KEY)
            # AI Studio expects 'models/' prefix
            if not self.model_id.startswith("models/"):
                self.model_id = f"models/{self.model_id}"
        
        self.turn_start_time = None

        # Cost tracking
        # Vertex AI gemini-2.0-flash-live-001 pricing (per 1M tokens):
        #   Audio input  : $0.70  → 1 tok / 1,280 bytes
        #   Audio output : $2.10  → 1 tok / 1,920 bytes
        #   Text input   : $0.075 → ~4 chars per token
        self._session_start_time: float = 0.0
        self._audio_in_bytes: int = 0
        self._audio_out_bytes: int = 0
        self._text_in_chars: int = 0

    def _get_system_instruction(self) -> str:
        """
        Constructs the system instruction for the AI, integrating the dynamic form context.
        
        Returns:
            str: The fully constructed system instruction prompt.
        """
        pm = get_prompt_manager()
        
        prompt = pm.get("voice_onboarding.system_prompt", default="You are a helpful voice assistant for doctor onboarding.")
        
        manual_fields = self.context.get('manual_fields_skipped', [])
        if manual_fields:
            formatted_fields = ", ".join(manual_fields) if isinstance(manual_fields, list) else manual_fields
            manual_fields_rule = (
                f"MANUAL FIELDS RULE: When all voice fields are complete, you MUST tell the user exactly: "
                f"'Kindly enter {formatted_fields.lower()} manually on the screen, then click Next.' "
                "Say nothing about any other manual fields."
            )
        else:
            manual_fields_rule = (
                "MANUAL FIELDS RULE: There are NO manual fields for this section. "
                "When all voice fields are complete, simply thank the user and end your turn. "
                "Do NOT mention Practice Locations, Profile Image, or any other manual fields."
            )
        with open("context_debug.json", "w") as f:
            json.dump(self.context, f, indent=2)

        # Sanitize Context to prevent toxic instructions from frontend overriding AI behavior
        clean_context = dict(self.context)
        frontend_rule = ""
        if "instruction" in clean_context:
            frontend_rule = str(clean_context.pop("instruction", ""))
        
        # Also remove any debug data from context to avoid AI confusion
        clean_context.pop("_debug_formData", None)

        context_str = json.dumps(clean_context, indent=2) if clean_context else "{}"
        tools_instruction = (
            f"- FRONTEND INSTRUCTION (Handling Skips): {frontend_rule}\n"
            "# Instructions for Tools\n"
            "You have access to a tool called `update_form`.\n"
            "- RULE: Call 'update_form' immediately after the user provides their information.\n"
            "- RULE: Do NOT ask new questions until you have successfully called 'update_form' to save the previous answer.\n"
            "- RULE: Never assume or invent values for fields. If the user only says 'Hello', do not fill in empty fields. DO NOT return fields you haven't explicitly asked about. DO NOT set unasked fields to [SKIPPED].\n"
            "- RULE: NO SELF-RECORDING. DO NOT save your own greetings, system prompts, or questions (e.g. 'Great progress!', 'Let's start') into the form fields. Only extract what the user actually said.\n"
            "- RULE: Include the exact, verbatim `transcript` of what the user said when calling the tool.\n"
            "- RULE: Extract ONLY the necessary core information (e.g. if user says 'My name is Rahul', extract 'Rahul').\n"
        )

        return (
            prompt + "\n\n"
            "# Current Form Context (What you need to ask the user)\n"
            + context_str + "\n\n"
            + tools_instruction + "\n"
            "# " + manual_fields_rule
        )

    async def run(self) -> None:
        """
        Executes the main lifecycle of the Gemini Live session.
        Establishes the connection, sends the initial greeting, and starts the duplex streams.
        """
        step = self.context.get("step")
        short_id = uuid.uuid4().hex[:8]

        # Set session context so all log lines for this connection are prefixed automatically
        session_context.set(f"Step {step} | {short_id}")

        tools = [get_update_form_tool(step)]
        config: Any = {
            "response_modalities": ["AUDIO"],
            "tools": tools,
            "system_instruction": self._get_system_instruction(),
            "generation_config": {
                "temperature": getattr(self.settings, "GEMINI_TEMPERATURE", 0.1),
                "max_output_tokens": getattr(self.settings, "GEMINI_MAX_TOKENS", 4096),
            },
            # VAD: wait 1.5 s of silence before treating the user's turn as complete.
            # LOW end-of-speech sensitivity avoids cutting off mid-sentence.
            # This prevents the model from calling update_form while the user is
            # still speaking. 1500 ms is a good balance — responsive but not rushed.
            "realtime_input_config": {
                "automatic_activity_detection": {
                    "disabled": False,
                    "end_of_speech_sensitivity": "END_SENSITIVITY_LOW",
                    "silence_duration_ms": 1500
                }
            }
        }
        
        logger.info(f"[Step {step}] Connecting to Gemini Live API — model={self.model_id}")
        self._session_start_time = time.time()
        self._text_in_chars = len(self._get_system_instruction())
        
        try:
            async with self.client.aio.live.connect(
                model=self.model_id, 
                config=config
            ) as session:
                logger.info(f"[Step {step}] Session established")
                
                try:
                    missing_fields = self.context.get("missing_fields", [])
                    
                    # Ensure focused_field_key is prioritized in missing_fields
                    focused_field_key = self.context.get("focused_field_key")
                    if focused_field_key and missing_fields:
                        focused_item = next((f for f in missing_fields if f.get('key') == focused_field_key), None)
                        if focused_item:
                            missing_fields.remove(focused_item)
                            missing_fields.insert(0, focused_item)

                    if len(missing_fields) == 0:
                        greeting = "Hi, all the details are filled, how can I help you today? If you want to make any changes let me know."
                        msg_text = f"Say exactly: '{greeting}'. Do NOT ask for any specific fields. If the user does not respond, remain absolutely silent and do NOT prompt them again. Stop speaking."
                        await session.send_client_content(turns={"role": "user", "parts": [{"text": msg_text}]}, turn_complete=True)
                    else:
                        if str(step) == "1":
                            greeting = "Hello! I'm CAEPY AI, your onboarding assistant. I'll help you complete your profile."
                        else:
                            greeting = "Great progress! Let's handle this section."
                        msg_text = f"Say exactly: '{greeting}'. Then naturally ask the user for the first two fields from the missing_fields list. Combine them into ONE smooth question. Do NOT repeat yourself. Stop speaking after that."
                        await session.send_client_content(turns={"role": "user", "parts": [{"text": msg_text}]}, turn_complete=True)
                    logger.info(f"[Step {step}] Greeting sent to model")
                except Exception as e:
                    logger.error(f"[Step {step}] Failed to send greeting: {e}")
                
                receive_task = asyncio.create_task(self._receive_from_client(session))
                send_task = asyncio.create_task(self._receive_from_gemini(session))
                
                try:
                    await asyncio.wait(
                        [receive_task, send_task], 
                        return_when=asyncio.FIRST_COMPLETED
                    )
                except Exception as e:
                    logger.error(f"[Step {step}] Run loop error: {e}")
                finally:
                    receive_task.cancel()
                    send_task.cancel()
                    await asyncio.gather(receive_task, send_task, return_exceptions=True)
                    logger.info(f"[Step {step}] Session tasks cleaned up")
                    self._log_cost_estimate()
                    
        except Exception as e:
            logger.error(f"[Step {step}] Session error: {type(e).__name__}: {e}", exc_info=True)
            try:
                await self.websocket.send_json({"type": "error", "message": f"Connection to AI service failed: {str(e)}"})
            except Exception:
                pass
        finally:
            self.session = None


    async def _receive_from_client(self, session: Any) -> None:
        """
        Receives PCM audio blobs from the WebSocket and forwards them to Gemini.
        
        Args:
            session (Any): The active Gemini Live stream session.
        """
        step = self.context.get("step")
        try:
            while True:
                try:
                    message = await self.websocket.receive()
                except RuntimeError:
                    logger.info(f"[Step {step}] Client disconnected")
                    break
                    
                if "bytes" in message:
                    data = message["bytes"]
                    self._audio_in_bytes += len(data)
                    try:
                        await session.send_realtime_input(audio={"data": data, "mime_type": "audio/pcm"})
                    except Exception as e:
                        logger.error(f"[Step {step}] Error forwarding audio to Gemini: {e}")
                        break
                elif "text" in message:
                    text = message["text"]
                    try:
                        parsed = json.loads(text)
                        if parsed.get("type") == "context_update":
                            logger.info(f"[Step {step}] Context update received from client")
                            msg_text = f"The user form context has been updated: {json.dumps(parsed.get('context'))}"
                            await session.send_client_content(turns={"role": "user", "parts": [{"text": msg_text}]}, turn_complete=True)
                    except Exception:
                        pass
        except WebSocketDisconnect:
            logger.info(f"[Step {step}] Client disconnected gracefully")
        except asyncio.CancelledError:
            pass


    async def _receive_from_gemini(self, session: Any) -> None:
        """
        Receives responses (audio, text, tools) from Gemini and routes them to the WebSocket.
        
        Args:
            session (Any): The active Gemini Live stream session.
        """
        step = self.context.get("step")
        try:
            while True:
                try:
                    async for response in session.receive():
                        if response.tool_call and response.tool_call.function_calls:
                            await self._handle_all_function_calls(
                                session, response.tool_call.function_calls
                            )

                        if response.server_content and response.server_content.model_turn:
                            for part in response.server_content.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    self._audio_out_bytes += len(part.inline_data.data)
                                    await self.websocket.send_bytes(part.inline_data.data)

                        if response.server_content and getattr(response.server_content, 'turn_complete', False):
                            if getattr(self, 'is_final_turn', False):
                                logger.info(f"[Step {step}] Sending session_complete signal to client")
                                await self.websocket.send_text(json.dumps({"type": "session_complete"}))

                except Exception as stream_err:
                    if "ConnectionClosed" in type(stream_err).__name__ or "1000" in str(stream_err):
                        logger.info(f"[Step {step}] Gemini Live session closed")
                    else:
                        logger.error(f"[Step {step}] Gemini receive error: {stream_err}")
                    break
        except asyncio.CancelledError:
            pass


    def _log_cost_estimate(self) -> None:
        """
        Computes and logs the estimated token cost for the session, 
        and updates the global cumulative tracker.
        """
        try:
            step = self.context.get("step")
            duration_s = time.time() - self._session_start_time

            audio_in_tokens  = self._audio_in_bytes  / 1_280
            audio_out_tokens = self._audio_out_bytes / 1_920
            text_in_tokens   = self._text_in_chars   / 4

            AUDIO_IN_PRICE  = 0.70  / 1_000_000
            AUDIO_OUT_PRICE = 2.10  / 1_000_000
            TEXT_IN_PRICE   = 0.075 / 1_000_000

            cost_audio_in  = audio_in_tokens  * AUDIO_IN_PRICE
            cost_audio_out = audio_out_tokens * AUDIO_OUT_PRICE
            cost_text_in   = text_in_tokens   * TEXT_IN_PRICE
            total_cost     = cost_audio_in + cost_audio_out + cost_text_in

            # Per-session log
            logger.info(
                f"[Step {step}][COST] duration={duration_s:.1f}s | "
                f"audio_in={self._audio_in_bytes/1024:.1f}KB (~{audio_in_tokens:.0f} tok, ${cost_audio_in:.6f}) | "
                f"audio_out={self._audio_out_bytes/1024:.1f}KB (~{audio_out_tokens:.0f} tok, ${cost_audio_out:.6f}) | "
                f"text_in={self._text_in_chars} chars (~{text_in_tokens:.0f} tok, ${cost_text_in:.6f}) | "
                f"SESSION TOTAL=${total_cost:.6f} USD"
            )

            # Update global tracker and print process-lifetime totals
            cost_tracker.record_live_session(
                audio_in_bytes=self._audio_in_bytes,
                audio_out_bytes=self._audio_out_bytes,
                text_in_chars=self._text_in_chars,
                duration_s=duration_s,
            )
            cost_tracker.log_totals()

        except Exception as e:
            logger.warning(f"[COST] Could not compute cost estimate: {e}")


    async def _handle_all_function_calls(self, session: Any, function_calls: List[Any]) -> None:
        """
        Processes ALL tool calls from a single Gemini response together.
        Sends UI updates for each, merges state, then sends ONE combined
        FunctionResponse list with end_of_turn=True.
        
        Args:
            session (Any): The active Gemini Live stream session.
            function_calls (List[Any]): The list of function calls requested by the model.
        """
        step = self.context.get("step")
        responses = []
        all_saved_keys = []

        for fc in function_calls:
            if fc.name != "update_form":
                logger.warning(f"[Step {step}][Tool] Unknown tool called: {fc.name}")
                responses.append(FunctionResponse(
                    name=fc.name,
                    response={"status": "unknown_tool"},
                    id=fc.id
                ))
                continue

            # Parse args
            args = fc.args
            data = {}
            try:
                if isinstance(args, dict):
                    data = args
                elif hasattr(args, "to_dict"):
                    data = args.to_dict()
                elif hasattr(args, "items"):
                    data = dict(args.items())
                else:
                    data = dict(args)
            except Exception as e:
                logger.error(f"[Step {step}][Tool] Failed to parse tool args: {e}")

            # Strip transcript from saved keys — it's metadata, not a form field
            field_keys = [k for k in data.keys() if k != "transcript"]
            logger.info(f"[Step {step}][Tool] update_form — saved fields: {field_keys}")

            # Push tool_update to frontend
            payload = {"type": "tool_update", "data": data}
            try:
                await self.websocket.send_text(json.dumps(payload))
                logger.info(f"[Step {step}][Tool] tool_update dispatched to frontend")
            except Exception as e:
                logger.error(f"[Step {step}][Tool] Failed to dispatch tool_update: {e}")

            # Update backend state — remove collected keys from missing_fields.
            # field_keys already excludes 'transcript', so matching is precise.
            if 'missing_fields' in self.context and isinstance(self.context['missing_fields'], list):
                self.context['missing_fields'] = [
                    f for f in self.context['missing_fields']
                    if f.get('key') not in field_keys
                ]

            all_saved_keys.extend(field_keys)

            responses.append(FunctionResponse(
                name=fc.name,
                response={"status": "success", "updated_keys": field_keys},
                id=fc.id
            ))

        if not responses:
            return

        remaining_fields = [
            {
                "key": f.get('key'),
                "label": f.get('label'),
                "description": f.get('description', '')
            }
            for f in self.context.get('missing_fields', [])
        ]

        if len(remaining_fields) == 0:
            manual_fields = self.context.get('manual_fields_skipped', [])
            if manual_fields:
                formatted_fields = ", ".join(manual_fields) if isinstance(manual_fields, list) else manual_fields
                final_instruction = (
                    f"All voice fields are complete! "
                    f"You MUST tell the user exactly: 'Kindly enter {formatted_fields.lower()} manually on the screen, then click Next.' "
                    "Then end your turn."
                )
            else:
                final_instruction = "All neccessary fields are complete! Thank the user and SAY 'Click Next to continue' and then end your turn."
            logger.info(f"[Step {step}][Tool] All fields captured — session complete")
            self.is_final_turn = True
        else:
            total_original = len(self.context.get('missing_fields', [])) + len(all_saved_keys)
            fields_done = len(all_saved_keys)
            fields_left = len(remaining_fields)
            
            # SLICE EXPLICITLY SO THE AI CANNOT SEE MORE THAN 2 FIELDS AT A TIME
            next_two = remaining_fields[:2]

            final_instruction = (
                f"Saved fields: {all_saved_keys}. Remaining fields to collect in total: {fields_left}\n"
                f"ACTION: You must exclusively ask the user for ONLY the following {len(next_two)} fields:\n"
                f"{next_two}\n\n"
                "Acknowledge their answer naturally, then combine the next fields into ONE single question. DO NOT ask about any other fields. DO NOT repeat the question twice. STOP talking and wait for their answer."
            )
            logger.info(f"[Step {step}][Tool] Remaining fields: {fields_left}. Sending slice to AI: {next_two}")

        # Patch instruction onto last response
        last = responses[-1]
        last.response["instruction"] = final_instruction  # type: ignore

        logger.info(f"[Step {step}][Tool] Sending {len(responses)} FunctionResponse(s) with end_of_turn=True")
        await session.send_tool_response(function_responses=responses)

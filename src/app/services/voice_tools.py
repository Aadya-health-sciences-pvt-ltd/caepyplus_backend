import os
from typing import Any, Dict, List, Optional
from google.genai.types import Tool, FunctionDeclaration, Schema, Type

from ..core.logger import logger

def load_form_config() -> List[Any]:
    """Load the form configuration from info_config.json, similar to InfoBot_2."""
    # The application forms are conceptually driven by the UI, but we can hardcode 
    # the schema generator based on Caepy_AI's expected OnboardingFormData structure
    
    # Rather than a complex dynamic config loader (since Caepy_AI's UI drives it internally),
    # we define exactly the properties Gemini should extract.
    return []

def get_update_form_tool(step: Optional[int] = None) -> Tool:
    """Generates the update_form tool declaration with Caepy AI fields."""
    
    properties: Dict[str, Schema] = {
        # Block 1
        "fullName": Schema(type=Type.STRING, description="The doctor's full name, including title (Dr. etc)"),
        "email": Schema(type=Type.STRING, description="A valid email address (must contain @)"),
        "phone": Schema(type=Type.STRING, description="Phone number. Must contain only numbers and optional + prefix, with a maximum length of 13 characters"),
        "specialty": Schema(type=Type.STRING, description="Primary medical specialty"),
        "primaryLocation": Schema(type=Type.STRING, description="Primary practice location or hospital"),
        "languages": Schema(type=Type.STRING, description="Comma-separated list of languages spoken"),
        "experience": Schema(type=Type.STRING, description="Total years of experience"),
        "postSpecialisationExperience": Schema(type=Type.STRING, description="Years of experience after specialisation"),
        "registrationNumber": Schema(type=Type.STRING, description="Medical council registration number"),
        "medicalCouncil": Schema(type=Type.STRING, description="State or national medical council name"),

        # Block 2
        "mbbsYear": Schema(type=Type.STRING, description="Year of MBBS graduation"),
        "specialisationYear": Schema(type=Type.STRING, description="Year of post-grad specialisation"),
        "fellowships": Schema(type=Type.STRING, description="Comma-separated list of fellowships"),
        "qualifications": Schema(type=Type.STRING, description="Degrees and qualifications"),
        "memberships": Schema(type=Type.STRING, description="Professional memberships"),
        "awards": Schema(type=Type.STRING, description="Awards and recognitions"),

        # Block 3
        "areasOfInterest": Schema(type=Type.STRING, description="Comma-separated list of sub-specialties or areas of interest"),
        "practiceSegments": Schema(type=Type.STRING, description="Comma-separated list of practice segments"),
        "commonConditions": Schema(type=Type.STRING, description="Comma-separated list of common conditions treated"),
        "knownForConditions": Schema(type=Type.STRING, description="Comma-separated list of conditions or procedures known for"),
        "wantToTreatConditions": Schema(type=Type.STRING, description="Specific conditions they want to treat more"),
        
        # Block 4
        "trainingExperience": Schema(type=Type.STRING, description="Training challenges — output exactly ONE single string containing the FULL spoken paragraph. Do not listify or summarise."),
        "motivation": Schema(type=Type.STRING, description="What motivates them — output exactly ONE single string containing the FULL spoken paragraph. Do not listify or summarise."),
        "unwinding": Schema(type=Type.STRING, description="How they unwind — output exactly ONE single string containing the FULL spoken paragraph. Do not listify or summarise."),
        "recognition": Schema(type=Type.STRING, description="How they like to be recognised — record the doctor's FULL verbatim answer, do not summarise"),
        "qualityTime": Schema(type=Type.STRING, description="How they spend quality time — record the doctor's FULL verbatim answer, do not summarise"),
        "freeText": Schema(type=Type.STRING, description="Any other free text information"),
        "proudAchievement": Schema(type=Type.STRING, description="A professional achievement — record the doctor's FULL verbatim answer as a complete sentence or paragraph, do not abbreviate"),
        "personalAchievement": Schema(type=Type.STRING, description="A personal achievement — record the doctor's FULL verbatim answer as a complete sentence or paragraph, do not abbreviate"),
        "professionalAspiration": Schema(type=Type.STRING, description="Professional aspirations — record the doctor's FULL verbatim answer as a complete sentence or paragraph, do not abbreviate"),
        "personalAspiration": Schema(type=Type.STRING, description="Personal aspirations — record the doctor's FULL verbatim answer as a complete sentence or paragraph, do not abbreviate"),
        
        # Block 5
        "patientValue": Schema(type=Type.STRING, description="What patients value most — record the doctor's FULL verbatim answer, do not summarise"),
        "careApproach": Schema(type=Type.STRING, description="Approach to patient care — record the doctor's FULL verbatim answer, do not summarise"),
        "practicePhilosophy": Schema(type=Type.STRING, description="Philosophy of practice — record the doctor's FULL verbatim answer, do not summarise"),
        "consultationFee": Schema(type=Type.STRING, description="Consultation fee"),
        
        # Block 6: Content Seed
        "contentSeed.conditionName": Schema(type=Type.STRING, description="Name of the condition"),
        "contentSeed.presentation": Schema(type=Type.STRING, description="Typical presentation of the condition"),
        "contentSeed.investigations": Schema(type=Type.STRING, description="Required investigations"),
        "contentSeed.treatment": Schema(type=Type.STRING, description="Treatment options"),
        "contentSeed.delayConsequences": Schema(type=Type.STRING, description="Consequences of delaying treatment"),
        "contentSeed.prevention": Schema(type=Type.STRING, description="Preventive measures"),
        "contentSeed.additionalInsights": Schema(type=Type.STRING, description="Any additional insights"),
        
        "transcript": Schema(type=Type.STRING, description="The exact text that the user spoke to trigger this update. Required.")
    }

    step_mapping = {
        1: ["fullName", "email", "phone", "specialty","languages", "primaryLocation", "experience", "postSpecialisationExperience", "registrationNumber", "medicalCouncil"],
        2: ["mbbsYear", "specialisationYear", "fellowships", "qualifications", "memberships", "awards"],
        3: ["areasOfInterest", "practiceSegments", "commonConditions", "knownForConditions", "wantToTreatConditions"],
        4: ["trainingExperience", "motivation", "unwinding", "recognition", "qualityTime", "freeText", "proudAchievement", "personalAchievement", "professionalAspiration", "personalAspiration"],
        5: ["patientValue", "careApproach", "practicePhilosophy", "languages", "consultationFee"],
        6: ["contentSeed.conditionName", "contentSeed.presentation", "contentSeed.investigations", "contentSeed.treatment", "contentSeed.delayConsequences", "contentSeed.prevention", "contentSeed.additionalInsights"]
    }

    if step is not None:
        try:
            step_int = int(step)
            if step_int in step_mapping:
                allowed_keys = set(step_mapping[step_int] + ["transcript"])
                properties = {k: v for k, v in properties.items() if k in allowed_keys}
                logger.info(f"[Tool Schema] Building update_form for Step {step_int} — {len(allowed_keys) - 1} field(s)")
        except (ValueError, TypeError):
            pass

    return Tool(
        function_declarations=[
            FunctionDeclaration(
                name="update_form",
                description="""Updates the onboarding doctor profile form with data collected from the user's voice.
                CRITICAL RULES:
                1. NEVER call this tool until the user has actually spoken and provided information.
                   Do NOT call it during your greeting or before the user responds.
                2. Extract the exact value required for each field. For basic fields (like Full Name, Specialty, Experience), extract ONLY the concise value without any conversational filler (e.g., extract 'Rahul' instead of 'My name is Rahul').
                   For long-form descriptive fields (like Training Experience, Achievements), follow the field's description to capture the verbatim full answer.
                3. ANTI-DUPLICATION: Map the user's answer ONLY to the specific field they are addressing.
                   Do NOT copy the same answer into multiple fields simultaneously.
                4. NO AUTO-FILL: Only include fields that the user has explicitly spoken about in this exact turn. DO NOT include fields you haven't asked about yet. DO NOT use [SKIPPED] unless the user explicitly said the word "skip" for that specific field.
                5. NEVER extract or update voiceskip fields like practiceLocations.
                6. NO SELF-RECORDING: DO NOT save your own greetings, system prompts, or questions (e.g. 'Great progress!', 'Let's handle this') into the form fields. Only extract what the user actually said.
                7. You can call this multiple times as you collect more information.
                8. ALWAYS include the transcript of what the user just said.""",
                parameters=Schema(
                    type=Type.OBJECT,
                    properties=properties,
                    required=["transcript"]
                )
            )
        ]
    )

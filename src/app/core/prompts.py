"""
Prompt Manager.

Centralized management of AI prompts loaded from external configuration.
Follows 12-Factor App methodology - no hardcoded prompts in code.

Features:
- Multi-variant prompt support for content regeneration
- External YAML configuration
- Template variable substitution
- Hot-reload support for development
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# Supported content sections for profile generation
PROFILE_SECTIONS = ["professional_overview", "about_me", "professional_tagline"]

# Default number of variants per section
DEFAULT_VARIANT_COUNT = 3
class PromptManager:
    """
    Manager for loading and accessing AI prompts from YAML configuration.
    
    Centralizes all prompt management with:
    - Lazy loading with caching
    - Template variable substitution
    - Validation of required prompts
    - Hot-reload support (in development)
    
    Usage:
        manager = get_prompt_manager()
        prompt = manager.get("resume_extraction.system_prompt")
        formatted = manager.format("voice_onboarding.greeting_template", name="Dr. Smith")
    """

    def __init__(self, config_path: Path | None = None) -> None:
        """
        Initialize the prompt manager.
        
        Args:
            config_path: Path to prompts.yaml. Defaults to config/prompts.yaml
        """
        if config_path is None:
            # Default to config/prompts.yaml relative to project root (three levels above src/app/core/)
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "prompts.yaml"

        self.config_path = config_path
        self._prompts: dict[str, Any] | None = None
        self._load_prompts()

    def _load_prompts(self) -> None:
        """Load prompts from YAML configuration file."""
        if not self.config_path.exists():
            raise ConfigurationError(
                f"Prompt configuration file not found: {self.config_path}"
            )

        try:
            with open(self.config_path, encoding="utf-8") as f:
                self._prompts = yaml.safe_load(f)

            logger.info("Loaded prompts from %s", self.config_path)

        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Invalid YAML in prompts configuration: {e}"
            )

    def reload(self) -> None:
        """Reload prompts from disk (useful for development)."""
        self._prompts = None
        self._load_prompts()
        logger.info("Prompts reloaded")

    def get(self, path: str, default: str | None = None) -> str:
        """
        Get a prompt by dot-notation path.
        
        Args:
            path: Dot-separated path to prompt (e.g., "resume_extraction.system_prompt")
            default: Default value if path not found
            
        Returns:
            The prompt string
            
        Raises:
            KeyError: If path not found and no default provided
            
        Example:
            prompt = manager.get("voice_onboarding.greeting_template")
        """
        if self._prompts is None:
            self._load_prompts()

        keys = path.split(".")
        value: Any = self._prompts

        try:
            for key in keys:
                if isinstance(value, dict):
                    value = value[key]
                else:
                    raise KeyError(key)

            if not isinstance(value, str):
                raise KeyError(f"Path '{path}' does not point to a string")

            return value

        except KeyError:
            if default is not None:
                return default
            raise KeyError(f"Prompt not found: {path}")

    def get_dict(self, path: str) -> dict[str, Any]:
        """
        Get a nested dictionary of prompts.
        
        Args:
            path: Dot-separated path to prompt section
            
        Returns:
            Dictionary of prompts
        """
        if self._prompts is None:
            self._load_prompts()

        keys = path.split(".")
        value: Any = self._prompts

        for key in keys:
            if isinstance(value, dict):
                value = value[key]
            else:
                raise KeyError(f"Invalid path: {path}")

        if not isinstance(value, dict):
            raise KeyError(f"Path '{path}' does not point to a dictionary")

        return value

    def get_value(self, path: str) -> Any:
        """
        Get any value (dict, list, str, etc.) from config by path.
        
        Args:
            path: Dot-separated path to the value
            
        Returns:
            The value at the path (any type)
        """
        if self._prompts is None:
            self._load_prompts()

        keys = path.split(".")
        value: Any = self._prompts

        for key in keys:
            if isinstance(value, dict):
                value = value[key]
            else:
                raise KeyError(f"Invalid path: {path}")

        return value

    def format(self, path: str, **kwargs: Any) -> str:
        """
        Get a prompt and format it with template variables.
        
        Args:
            path: Dot-separated path to prompt template
            **kwargs: Template variables to substitute
            
        Returns:
            Formatted prompt string
            
        Example:
            message = manager.format(
                "voice_onboarding.completion_message",
                doctor_name="Dr. Smith"
            )
        """
        template = self.get(path)

        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing template variable in {path}: {e}")

    def get_resume_extraction_prompt(self) -> str:
        """
        Get the complete resume extraction prompt.
        
        Combines system prompt, schema, and instruction.
        """
        system = self.get("resume_extraction.system_prompt")
        schema = self.get("resume_extraction.response_schema")
        instruction = self.get("resume_extraction.instruction")

        return f"{system}\n\n{schema}\n\n{instruction}"

    def get_voice_greeting(self) -> str:
        """Get the voice session greeting message."""
        return self.get("voice_onboarding.greeting_template")

    def get_voice_field_prompt(self, field_name: str, prompt_type: str = "question") -> str:
        """
        Get a field-specific voice prompt.
        
        Args:
            field_name: Name of the field (e.g., "full_name", "email")
            prompt_type: Type of prompt ("question", "clarification", "confirmation")
            
        Returns:
            The field prompt string
        """
        path = f"voice_onboarding.field_prompts.{field_name}.{prompt_type}"
        return self.get(path, default=f"Please provide your {field_name.replace('_', ' ')}.")

    def get_voice_extraction_prompt(
        self,
        user_message: str,
        collected_fields: list[str],
        missing_fields: list[str],
    ) -> str:
        """
        Get the formatted voice extraction prompt.
        
        Args:
            user_message: The user's latest message
            collected_fields: List of already collected field names
            missing_fields: List of fields still needed
            
        Returns:
            Formatted extraction prompt
        """
        template = self.get("voice_onboarding.extraction_prompt")

        return template.format(
            user_message=user_message,
            collected_fields=", ".join(collected_fields) if collected_fields else "None",
            missing_fields=", ".join(missing_fields) if missing_fields else "None",
        )

    def get_voice_confirmation_prompt(self, collected_data: dict[str, Any]) -> str:
        """Get the confirmation prompt with collected data."""
        template = self.get("voice_onboarding.confirmation_prompt")

        # Format collected data as readable text
        data_lines = [f"- {k.replace('_', ' ').title()}: {v}" for k, v in collected_data.items()]
        data_text = "\n".join(data_lines)

        return template.format(collected_data=data_text)

    def get_profile_generation_prompt(self, doctor_data: dict[str, Any]) -> str:
        """Build prompt for generating profile overview and about-me text."""

        system = self.get("profile_generation.system_prompt")
        schema = self.get("profile_generation.response_schema")
        instruction = self.get("profile_generation.instruction")

        doctor_json = json.dumps(doctor_data, ensure_ascii=False, indent=2)

        return (
            f"{system}\n\n"
            f"## DOCTOR ONBOARDING DATA (JSON)\n{doctor_json}\n\n"
            f"## REQUIRED OUTPUT FORMAT\n{schema}\n\n"
            f"## TASK\n{instruction}"
        )

    def get_profile_generation_prompt_with_variants(
        self,
        doctor_data: dict[str, Any],
        variant_indices: dict[str, int],
    ) -> str:
        """
        Build prompt for generating profile content with specific variants.
        
        Args:
            doctor_data: Doctor's onboarding data
            variant_indices: Dict mapping section name to variant index (0-based)
                            e.g., {"professional_overview": 0, "about_me": 1, "professional_tagline": 2}
        
        Returns:
            Complete prompt with variant-specific instructions
        """
        doctor_json = json.dumps(doctor_data, ensure_ascii=False, indent=2)
        schema = self.get("profile_generation.response_schema")
        base_instruction = self.get("profile_generation.base_instruction")

        # Build section-specific prompts
        section_prompts = []

        for section in PROFILE_SECTIONS:
            variant_idx = variant_indices.get(section, 0)
            variant_data = self._get_variant_data(section, variant_idx)

            if variant_data:
                section_prompts.append(
                    f"### {section.upper().replace('_', ' ')}\n"
                    f"Variant Style: {variant_data['name']}\n"
                    f"System Context:\n{variant_data['system_prompt']}\n"
                    f"Instructions:\n{variant_data['instruction']}"
                )

        sections_text = "\n\n".join(section_prompts)

        prompt = (
            f"# PROFILE CONTENT GENERATION\n\n"
            f"## DOCTOR ONBOARDING DATA (JSON)\n{doctor_json}\n\n"
            f"## SECTION-SPECIFIC INSTRUCTIONS\n\n{sections_text}\n\n"
            f"## OUTPUT FORMAT\n{schema}\n\n"
            f"## GENERAL RULES\n{base_instruction}"
        )

        logger.debug("Generated variant prompt with indices: %s", variant_indices)
        return prompt

    def _get_variant_data(self, section: str, variant_idx: int) -> dict[str, Any] | None:
        """
        Get variant data for a specific section and index.
        
        Args:
            section: Section name (professional_overview, about_me, professional_tagline)
            variant_idx: 0-based variant index
            
        Returns:
            Variant data dict with system_prompt, instruction, name, id
        """
        try:
            variants = self.get_value(f"profile_generation.{section}.variants")

            if isinstance(variants, list) and 0 <= variant_idx < len(variants):
                return variants[variant_idx]  # type: ignore[no-any-return]

            # Fallback to first variant if index out of range
            if variants:
                logger.warning("Variant index %s out of range for %s, using 0", variant_idx, section)
                return variants[0]  # type: ignore[no-any-return]

        except KeyError:
            logger.warning("No variants found for section: %s", section)

        return None

    def get_variant_count(self, section: str) -> int:
        """Get the number of available variants for a section."""
        try:
            variants = self.get_value(f"profile_generation.{section}.variants")
            return len(variants) if isinstance(variants, list) else DEFAULT_VARIANT_COUNT
        except KeyError:
            return DEFAULT_VARIANT_COUNT

    def get_all_variant_info(self) -> dict[str, list[dict[str, Any]]]:
        """
        Get information about all available variants for each section.
        
        Returns:
            Dict mapping section name to list of variant info dicts
        """
        result = {}

        for section in PROFILE_SECTIONS:
            try:
                variants = self.get_value(f"profile_generation.{section}.variants")
                if isinstance(variants, list):
                    result[section] = [
                        {
                            "id": v.get("id"),
                            "name": v.get("name"),
                            "description": v.get("description"),
                        }
                        for v in variants
                    ]
                else:
                    result[section] = []
            except KeyError:
                result[section] = []

        return result

    def get_blog_topics_prompt(self) -> str:
        """Get the combined prompt for generating blog topics."""
        system = self.get("blog_studio.topics.system_prompt")
        schema = self.get("blog_studio.topics.response_schema")

        return f"{system}\n\n## REQUIRED OUTPUT FORMAT\n{schema}"

    def get_blog_keywords_prompt(self, topic: str) -> str:
        """Get the combined prompt for generating blog keywords for a topic."""
        system = self.get("blog_studio.keywords.system_prompt")
        schema = self.get("blog_studio.keywords.response_schema")

        # Format topic into system prompt
        formatted_system = system.format(topic=topic)

        return f"{formatted_system}\n\n## REQUIRED OUTPUT FORMAT\n{schema}"

    def get_blog_content_prompt(self, topic: str, keywords: list[str]) -> str:
        """Get the combined prompt for generating blog content."""
        system = self.get("blog_studio.content.system_prompt")
        schema = self.get("blog_studio.content.response_schema")

        # Format topic and keywords into system prompt
        formatted_system = system.format(topic=topic, keywords=", ".join(keywords))

        return f"{formatted_system}\n\n## REQUIRED OUTPUT FORMAT\n{schema}"
# -----------------------------------------------------------------------------
# Singleton Pattern with Lazy Initialization
# -----------------------------------------------------------------------------

_prompt_manager: PromptManager | None = None

def get_prompt_manager() -> PromptManager:
    """
    Get the global prompt manager instance.
    
    Uses lazy initialization and caching for efficiency.
    """
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager


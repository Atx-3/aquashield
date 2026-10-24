"""
AQUA SHIELD AI Intent & Tool Router.

Orchestrates user request processing, Ollama LLM queries,
validation against allowed investigation tools, and structured response generation.

Pipeline of route():
    user text -> build prompt -> ask LLM (Ollama) -> extract JSON from its reply
              -> is the intent one of the 8 allowed tools?
                    yes -> clean up the arguments -> RouterResponse(intent, arguments)
                    no  -> RouterResponse("unsupported")
The key safety idea: we never trust the LLM blindly - its answer is checked against a
fixed whitelist, so it can't trigger anything outside the 8 tools.
"""

import json
import logging
import re
import sys
from typing import Any, Dict, Optional

from .llm import OllamaClient, OllamaError
from .prompts import AQUA_SHIELD_SYSTEM_PROMPT, build_user_prompt
from .response import DEFAULT_UNSUPPORTED_MESSAGE, RouterResponse
from .tools import ALLOWED_INVESTIGATION_INTENTS, sanitize_arguments

logger = logging.getLogger("aquashield.router")


class AquaShieldRouter:
    """
    Router for parsing natural language queries and mapping them
    to validated AQUA SHIELD investigation tools.
    """

    def __init__(
        self,
        llm_client: Optional[OllamaClient] = None,
        verbose: bool = True,
    ):
        """
        Initialize the router.

        :param llm_client: Configured OllamaClient instance (creates default if None).
        :param verbose: Whether to print/log step-by-step pipeline output.
        """
        self.llm_client = llm_client or OllamaClient()
        self.verbose = verbose

    def _extract_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Safely extract and parse JSON object from LLM output,
        stripping potential markdown fences, think tags, or trailing text.
        """
        if not raw_text or not raw_text.strip():
            return None

        cleaned = raw_text.strip()

        # Remove <think>...</think> block if present
        # (Qwen3 may "think out loud" before answering; re.DOTALL lets "." match newlines too)
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

        # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        # First direct parse attempt
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Regex fallback to find outermost { ... }
        # (handles replies like 'Sure! {"intent": ...} Hope that helps')
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        return None

    def _log_trace(self, user_input: str, llm_output: str, validated_intent: str, arguments: Dict[str, Any]) -> None:
        """
        Log required pipeline traces:
        USER INPUT
        -> LLM OUTPUT
        -> VALIDATED INTENT
        -> ARGUMENTS
        """
        trace = (
            f"\n--------------------------------------------------\n"
            f"USER INPUT: {user_input}\n"
            f"-> LLM OUTPUT: {llm_output}\n"
            f"-> VALIDATED INTENT: {validated_intent}\n"
            f"-> ARGUMENTS: {json.dumps(arguments)}\n"
            f"--------------------------------------------------"
        )
        if self.verbose:
            try:
                print(trace)
            except UnicodeEncodeError:
                print(trace.encode(sys.stdout.encoding or "ascii", errors="replace").decode(sys.stdout.encoding or "ascii"))
        logger.info(trace)

    def process_query(self, user_input: str) -> RouterResponse:
        """Alias for route() method for backward compatibility."""
        return self.route(user_input)

    def route(self, user_input: str) -> RouterResponse:
        """
        Process a user input string and route it to a validated AQUA SHIELD intent.

        :param user_input: Natural language request from the user.
        :return: RouterResponse instance containing validated intent & arguments.
        """
        trimmed_input = user_input.strip() if user_input else ""

        # Handle empty input safely
        if not trimmed_input:
            resp = RouterResponse.unsupported(
                message="No input was provided. Please enter a AQUA SHIELD investigation command."
            )
            self._log_trace(
                user_input=user_input,
                llm_output="<empty_input>",
                validated_intent=resp.intent,
                arguments=resp.arguments,
            )
            return resp

        # Query LLM without restrictive JSON grammar to allow Qwen's thinking tokens,
        # prompt guarantees valid JSON output which is cleaned and parsed by _extract_json.
        prompt = build_user_prompt(trimmed_input)
        try:
            raw_output = self.llm_client.generate(
                prompt=prompt,
                system=AQUA_SHIELD_SYSTEM_PROMPT,
                format=None,
                temperature=0.0,
            )
        except OllamaError as err:
            logger.error(f"Ollama execution error: {err}")
            resp = RouterResponse.unsupported(
                message=f"Investigation router service unavailable: {err}",
                raw_llm_output=str(err),
            )
            self._log_trace(
                user_input=trimmed_input,
                llm_output=f"<error: {err}>",
                validated_intent=resp.intent,
                arguments=resp.arguments,
            )
            return resp

        # Parse JSON
        parsed_json = self._extract_json(raw_output)
        if not parsed_json:
            resp = RouterResponse.unsupported(
                message=DEFAULT_UNSUPPORTED_MESSAGE,
                raw_llm_output=raw_output,
            )
            self._log_trace(
                user_input=trimmed_input,
                llm_output=raw_output,
                validated_intent=resp.intent,
                arguments=resp.arguments,
            )
            return resp

        # Extract and validate intent
        raw_intent = str(parsed_json.get("intent", "")).strip().lower()
        raw_arguments = parsed_json.get("arguments", {})

        # Whitelist check - the core safety step
        if raw_intent in ALLOWED_INVESTIGATION_INTENTS:
            sanitized_args = sanitize_arguments(raw_intent, raw_arguments)
            resp = RouterResponse(
                intent=raw_intent,
                arguments=sanitized_args,
                raw_llm_output=raw_output,
            )
        else:
            # Out-of-scope, unsupported, or invalid intent
            custom_msg = parsed_json.get("message") or DEFAULT_UNSUPPORTED_MESSAGE
            resp = RouterResponse.unsupported(
                message=custom_msg,
                raw_llm_output=raw_output,
            )

        self._log_trace(
            user_input=trimmed_input,
            llm_output=raw_output,
            validated_intent=resp.intent,
            arguments=resp.arguments,
        )
        return resp

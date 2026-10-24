"""
AQUA SHIELD AI Structured Response Schema.

Provides clean dataclasses for formatted router outputs.

Every call to the router returns one RouterResponse, for example:
    RouterResponse(intent="forecast_spill", arguments={"forecast_hours": 24})
or, for off-topic requests:
    RouterResponse(intent="unsupported", message="I can only help with ...")
"""

from dataclasses import dataclass, field
import json
from typing import Any, Dict, Optional

# Reply used whenever a request is not one of the 8 investigation tools
DEFAULT_UNSUPPORTED_MESSAGE = "I can only help with AQUA SHIELD investigation commands."


# @dataclass auto-generates __init__ (and more) from the fields listed below,
# so RouterResponse(intent="x") works without writing a constructor by hand.
@dataclass
class RouterResponse:
    """
    Structured output returned by the AQUA SHIELD AI intent router.
    """
    intent: str                                               # chosen tool name, or "unsupported"
    arguments: Dict[str, Any] = field(default_factory=dict)  # extracted parameters (new empty dict per object)
    message: Optional[str] = None                             # optional text for the user
    raw_llm_output: Optional[str] = None                      # exact LLM text, kept for debugging

    def to_dict(self, include_metadata: bool = False) -> Dict[str, Any]:
        """Convert response to standard dictionary format."""
        data: Dict[str, Any] = {
            "intent": self.intent,
            "arguments": self.arguments,
        }
        # Only include optional fields when they have a value
        if self.message is not None:
            data["message"] = self.message
        if include_metadata and self.raw_llm_output is not None:
            data["raw_llm_output"] = self.raw_llm_output
        return data

    def to_json(self, indent: int = 2, include_metadata: bool = False) -> str:
        """Serialize to formatted JSON string."""
        return json.dumps(self.to_dict(include_metadata=include_metadata), indent=indent)

    @classmethod
    def unsupported(cls, message: str = DEFAULT_UNSUPPORTED_MESSAGE, raw_llm_output: Optional[str] = None) -> "RouterResponse":
        """Factory for unsupported / invalid queries."""
        # Shortcut to build the standard "I can't help with that" response
        return cls(
            intent="unsupported",
            arguments={},
            message=message,
            raw_llm_output=raw_llm_output,
        )

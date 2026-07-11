"""AskUserQuestion tool — let the model clarify requirements with the user."""

from __future__ import annotations

from cowcode.tool import Result


class AskUserQuestionTool:
    """A read-only tool that the model calls when requirements are unclear.

    This tool is intercepted by the Agent/TUI layer: it pauses the current turn,
    shows the question to the user, waits for an answer, then resumes the Agent
    loop with the user's response injected into the conversation.
    """

    @property
    def read_only(self) -> bool:
        return True

    def name(self) -> str:
        return "AskUserQuestion"

    def description(self) -> str:
        return (
            "Ask the user a clarifying question when you don't have enough "
            "information to proceed. Call this when requirements are ambiguous, "
            "you need a decision between options, or you lack essential context "
            "that only the user can provide. Do NOT use this to confirm a finished "
            "plan — the user approves plans with /do. Ask only the most critical "
            "questions; don't quiz the user on low-level details. "
            "After receiving the answer, continue with your task."
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user. Be specific and focused.",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional. A short list of suggested answers for the user "
                        "to choose from. If you can predict reasonable options, "
                        "list them here so the user can pick or provide an alternative."
                    ),
                },
            },
            "required": ["question"],
        }

    async def execute(self, args: str) -> Result:
        """Fallback execute — the real interaction is handled by Agent/TUI."""
        return Result(
            content="This tool should have been intercepted by the Agent. "
            "The question will be shown to the user by the TUI.",
            is_error=False,
        )

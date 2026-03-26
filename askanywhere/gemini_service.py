from google import genai


class GeminiChatService:
    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = genai.Client(api_key=api_key)
        self._chat = self._client.chats.create(model=model)

    def send_message(self, selected_text: str, user_input: str) -> str:
        prompt = (
            "Use the selected text as context. Keep answers concise unless asked for detail.\n\n"
            f"Selected text:\n{selected_text or '(none)'}\n\n"
            f"User message:\n{user_input}"
        )
        response = self._chat.send_message(prompt)
        text = (response.text or "").strip()
        return text or "I could not generate a response for that message."

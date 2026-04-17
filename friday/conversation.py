"""
friday/conversation.py — Internet check + Groq conversational AI
"""

import socket

SYSTEM_PROMPT = (
    "You are Friday, a helpful and friendly female AI assistant. "
    "Keep responses concise and natural for voice output — "
    "no bullet points, no markdown, no lists. "
    "Speak in short, clear sentences. Max 3 sentences per reply."
)


def check_internet(host="8.8.8.8", port=53, timeout=2):
    """Returns True if internet is reachable."""
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


class GroqChat:
    """Conversational AI using Groq's free-tier API."""

    def __init__(self, api_key, model):
        from groq import Groq
        self.client = Groq(api_key=api_key)
        self.model = model
        self.history = []  # last N message pairs kept for context

    def ask(self, user_text):
        """Send user_text to Groq and return the assistant's reply."""
        self.history.append({"role": "user", "content": user_text})

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.history[-10:]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=200,
            temperature=0.7
        )

        reply = response.choices[0].message.content.strip()
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self):
        """Clear conversation history — call when entering a new chat session."""
        self.history = []

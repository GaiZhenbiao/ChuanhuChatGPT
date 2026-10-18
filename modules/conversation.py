"""List-compatible chat history with a persistent conversation identity."""

from uuid import UUID, uuid4


class ConversationHistory(list):
    def __init__(self, messages=(), conversation_id=None):
        super().__init__(messages)
        try:
            self._conversation_id = str(UUID(conversation_id))
        except (ValueError, TypeError, AttributeError):
            self._conversation_id = str(uuid4())

    @property
    def conversation_id(self):
        return self._conversation_id

    def __getitem__(self, key):
        value = super().__getitem__(key)
        # Removing a turn or trimming context still belongs to the same chat.
        if isinstance(key, slice):
            return ConversationHistory(value, self.conversation_id)
        return value

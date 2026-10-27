"""异步操作使用不可变作用域，旧会话结果不能写回当前聊天。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationScope:
    owner: str
    target: str
    history_path: str | None
    generation: str | None

    @classmethod
    def capture(cls, model, *, history_target=False):
        return cls(model._owner, model.agent_choice_target, model.history_file_path if history_target else None, model._state.get('generation'))

    def current(self, model):
        return not model._retired and self == self.capture(model, history_target=self.history_path is not None)


@dataclass(frozen=True)
class TaskScope:
    """Execution identity does not depend on a browser visit or retirement."""
    owner: str
    conversation: str
    history_path: str
    generation: str | None

    @classmethod
    def capture(cls, model, **_):
        return cls(model._owner, model._conversation_id, model.history_file_path, model._state.get('generation'))

    def current(self, model):
        return (not getattr(model, '_history_deleted', False)
                and not getattr(getattr(model, '_background_task', None), 'deleted', False)
                and self == self.capture(model))

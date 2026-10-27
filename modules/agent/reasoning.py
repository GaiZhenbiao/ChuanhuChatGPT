"""Model reasoning compatibility, shared by UI and every submission boundary.

Official model references checked 2026-10-06:
https://developers.openai.com/api/docs/models/gpt-6-astra
https://developers.openai.com/api/docs/models/gpt-6-sol
https://developers.openai.com/api/docs/models/gpt-6.1-sol
The SDK's union of efforts is not a per-model capability list.
"""
SDK_EFFORTS = ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max')
MODEL_EFFORTS = {
    'gpt-6-astra': ('low', 'medium', 'high', 'xhigh', 'max'),
    'gpt-6-sol': ('none', 'low', 'medium', 'high', 'xhigh', 'max'),
    'gpt-6.1-sol': ('low', 'medium', 'high', 'xhigh', 'max'),
}


class ReasoningConfigurationError(ValueError):
    pass


def normalize_reasoning(value):
    return None if value in (None, 'default') else value


def compatible_reasoning(model, value):
    """Keep valid selections; migrate only unsupported known-model legacy values.

    The user approved low as the compatible minimum. Custom models retain their
    SDK-valid effort and are checked by their provider; never invent capabilities.
    """
    value = normalize_reasoning(value)
    if value is None:
        return None, ''
    if not isinstance(value, str) or value not in SDK_EFFORTS:
        raise ReasoningConfigurationError('请选择有效的 Agent 推理强度；消息尚未发送')
    supported = MODEL_EFFORTS.get(model)
    if supported is not None and value not in supported:
        return 'low', f'{model} 不支持 {value} 推理强度，已调整为支持的最低强度 low'
    return value, ''


def reasoning_options(model, current=None):
    supported = MODEL_EFFORTS.get(model)
    if supported is not None:
        return ['default', *supported]
    # An unknown model has no asserted support list. Retain its explicit value
    # and allow an SDK effort to be entered, without silently switching it.
    current = normalize_reasoning(current)
    return ['default', *([current] if current in SDK_EFFORTS else [])]

"""Network-free payload verification against the single project SDK's types."""
import collections.abc
import json
import socket
import sys
import types
from typing import Any, Annotated, Literal, Union, get_args, get_origin, get_type_hints
from typing_extensions import Required, NotRequired
import openai
from openai._utils import maybe_transform
from openai.types.beta.agents.session_create_params import SessionCreateParamsStreaming
from openai.types.beta.agents.session_update_params import SessionUpdateParams
from openai.types.beta.agents.sessions.event_create_params import EventCreateParams


def validate(value, hint, path='payload'):
    origin=get_origin(hint)
    args=get_args(hint)
    if hint in (Any, object):return
    if origin in (Required,NotRequired,Annotated):return validate(value,args[0],path)
    if origin in (Union,types.UnionType):
        for choice in args:
            try:
                validate(value,choice,path)
                return
            except AssertionError:pass
        raise AssertionError(path+': no matching SDK union type')
    if origin is Literal:
        assert any(type(value) is type(choice) and value==choice for choice in args), path+': invalid SDK literal'
        return
    if hasattr(hint,'__required_keys__') and hasattr(hint,'__total__'):
        assert type(value) is dict,path+': expected object'
        # Required/NotRequired annotations must be resolved: __required_keys__
        # alone is incorrect for these generated postponed annotations.
        fields=get_type_hints(hint,include_extras=True)
        assert set(value)<=set(fields),path+': unknown SDK fields'
        for key,field in fields.items():
            field_origin=get_origin(field)
            required=field_origin is Required or (field_origin is not NotRequired
                and key not in hint.__optional_keys__
                and (key in hint.__required_keys__ or hint.__total__))
            assert not required or key in value,path+'.'+key+': missing required SDK field'
            if key in value:validate(value[key],field,path+'.'+key)
        return
    if origin is dict:
        assert type(value) is dict,path+': expected mapping'
        for key,item in value.items():
            validate(key,args[0],path+'.key');validate(item,args[1],path+'.value')
        return
    if origin in (list,tuple,collections.abc.Iterable,collections.abc.Sequence):
        assert isinstance(value,(list,tuple)),path+': expected sequence'
        for item in value:validate(item,args[0],path+'[]')
        return
    if hint is type(None):assert value is None,path+': expected null';return
    assert hint in (str,int,bool,float),path+': unhandled SDK contract type'
    assert type(value) is hint,path+': incorrect primitive type'


def check(payload, kind='create'):
    assert openai.__version__=='3.22.0','Contract test requires the pinned SDK'
    hint = {'create':SessionCreateParamsStreaming, 'update':SessionUpdateParams, 'events':EventCreateParams}[kind]
    validate(payload,hint)
    if kind == 'create':
        assert payload.get('agent_id') or payload.get('agent',{}).get('model'),'Inline agent requires model'
    metadata=payload.get('metadata') or {}
    assert len(metadata)<=16 and all(len(key)<=64 and len(value)<=512 for key,value in metadata.items()),'SDK metadata bounds'
    wire=maybe_transform(payload,hint)
    validate(wire,hint)
    return {'sdk_version':openai.__version__,'serialized':wire}

if __name__=='__main__':
    socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('Network forbidden in contract test'))
    print(json.dumps(check(json.load(sys.stdin)),ensure_ascii=False))

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import threading
import pytest
from modules import extensions as ext, plugin_callbacks as callbacks

@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    ext._loaded = False
    ext._loaded_extensions = []
    ext._configured_disabled_extensions = []
    callbacks.clear_callbacks()
    monkeypatch.setattr(ext, 'EXTENSIONS_DIR', tmp_path / 'extensions')
    monkeypatch.setattr(ext, 'STATE_FILE', tmp_path / 'extension_state.json')
    yield
    for item in ext.get_loaded_extensions():
        ext._unload_extension(item)
    callbacks.clear_callbacks()


def plugin(name, metadata=None, script=None):
    path = ext.extensions_dir() / name
    path.mkdir()
    (path / 'metadata.json').write_text(json.dumps(metadata or {'id': name, 'name': name}))
    if script:
        (path / 'extension.py').write_text(script)
    return path

SCRIPT = 'from modules.plugin_callbacks import on_before_chat\n@on_before_chat\ndef run(context):\n context.append("called")\n'


def test_toggle_survives_refresh_force_reload_and_restart():
    plugin('sample', script=SCRIPT)
    ext.load_extensions()
    ext._set_extension_enabled('sample', False)
    ext.refresh_extension_list()
    assert not ext.get_loaded_extensions()[0].enabled
    ext.load_extensions(force=True)
    context = []
    callbacks.invoke('before_chat', context)
    assert context == []
    ext._set_extension_enabled('sample', True)
    callbacks.invoke('before_chat', context)
    assert context == ['called']
    # A persisted explicit enable overrides legacy config disabled IDs.
    ext._loaded = False
    ext.load_extensions(disabled_extensions=['sample'])
    assert ext.get_loaded_extensions()[0].enabled


def test_state_write_failure_does_not_change_runtime(monkeypatch):
    plugin('sample', script=SCRIPT)
    ext.load_extensions()
    monkeypatch.setattr(ext.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('read only')))
    assert '保存插件状态失败' in ext._set_extension_enabled('sample', False)
    assert ext.get_loaded_extensions()[0].enabled
    assert callbacks.is_extension_enabled('sample')

@pytest.mark.parametrize('metadata', [[], {'id': '../oops'}, {'id':'ok','priority':True}, {'id':'ok','enabled':'false'}, {'id':'ok','name': []}])
def test_invalid_metadata_is_isolated(metadata):
    plugin('broken')
    (ext.EXTENSIONS_DIR / 'broken' / 'metadata.json').write_text(json.dumps(metadata))
    plugin('valid', script=SCRIPT)
    found = ext.load_extensions()
    assert next(x for x in found if x.path.name == 'broken').error
    context = []
    callbacks.invoke('before_chat', context)
    assert context == ['called']


def test_duplicates_load_neither_and_do_not_execute():
    plugin('first', {'id':'duplicate'}, 'raise AssertionError("executed")')
    plugin('second', {'id':'duplicate'}, 'raise AssertionError("executed")')
    assert all(x.error.startswith('Duplicate') and not x.loaded_scripts for x in ext.load_extensions())


def test_partial_import_rolls_back_callbacks_and_modules():
    plugin('broken', script=SCRIPT + '\nraise RuntimeError("broken import")\n')
    plugin('valid', script=SCRIPT)
    found = ext.load_extensions()
    broken = next(x for x in found if x.id == 'broken')
    assert not broken.module_names and not broken.loaded_scripts
    assert [r.extension_id for r in callbacks.iter_callbacks('before_chat')] == ['valid']
    before = len([n for n in sys.modules if n.startswith('chuanhu_extension_')])
    ext.load_extensions(force=True)
    assert len([n for n in sys.modules if n.startswith('chuanhu_extension_')]) == before


def test_callback_exception_does_not_block_next_plugin():
    with callbacks.extension_context('bad'):
        callbacks.on_before_chat(lambda context: 1/0)
    with callbacks.extension_context('good'):
        callbacks.on_before_chat(lambda context: context.append('good'))
    result = []
    callbacks.invoke('before_chat', result)
    assert result == ['good']
    assert callbacks.get_errors()[0]['extension'] == 'bad'


def test_ownership_is_context_local():
    barrier = threading.Barrier(2)
    def register(owner):
        with callbacks.extension_context(owner):
            barrier.wait()
            callbacks.on_before_chat(lambda context: None)
    threads = [threading.Thread(target=register, args=(x,)) for x in ('a','b')]
    for t in threads: t.start()
    for t in threads: t.join()
    assert {r.extension_id for r in callbacks.iter_callbacks('before_chat')} == {'a','b'}


def test_direct_events_and_generators_obey_disable():
    with callbacks.extension_context('sample'):
        wrapped = callbacks.guarded_callback(lambda: 'ok')
        def generator():
            yield 1
            yield 2
        stream = callbacks.guarded_callback(generator)
    callbacks.set_extension_enabled('sample', True)
    iterator = stream()
    assert next(iterator) == 1
    callbacks.set_extension_enabled('sample', False)
    with pytest.raises(Exception, match='disabled'): wrapped()
    with pytest.raises(Exception, match='disabled'): next(iterator)


def test_install_stages_validates_disables_without_execution(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source/'metadata.json').write_text('{"id":"new_plugin"}')
    (source/'extension.py').write_text('raise AssertionError("must not execute")')
    assert '默认禁用' in ext.install_extension(str(source))
    assert not ext.get_loaded_extensions()[0].enabled
    assert not ext.get_loaded_extensions()[0].loaded_scripts
    assert not list(ext.EXTENSIONS_DIR.glob('.install-*'))
    (source/'metadata.json').write_text('{"id":"duplicate","priority":"bad"}')
    (source/'other').mkdir()
    other = source/'other'
    (other/'metadata.json').write_text('[]')
    assert '安装失败' in ext.install_extension(str(other))
    assert not (ext.EXTENSIONS_DIR/'other').exists()


def test_corrupted_state_fails_closed():
    plugin('sample', script=SCRIPT)
    ext.STATE_FILE.write_text('not json')
    assert all(not x.enabled and x.error for x in ext.load_extensions())


def git(path, *args):
    return subprocess.run(['git','-C',str(path),*args], check=True, capture_output=True, text=True).stdout


def test_git_update_dirty_guard_and_restart(tmp_path):
    upstream = tmp_path/'upstream'
    upstream.mkdir()
    git(upstream,'init','-b','main')
    git(upstream,'config','user.email','test@example.invalid')
    git(upstream,'config','user.name','Test')
    (upstream/'metadata.json').write_text('{"id":"git_plugin"}')
    (upstream/'extension.py').write_text(SCRIPT)
    git(upstream,'add','.')
    git(upstream,'commit','-m','initial')
    target = ext.extensions_dir()/'git_plugin'
    subprocess.run(['git','clone',str(upstream),str(target)],check=True,capture_output=True)
    ext.load_extensions()
    old_head = git(target,'rev-parse','HEAD')
    (target/'untracked.txt').write_text('do not delete')
    assert '本地修改' in ext.update_extension('git_plugin')
    assert git(target,'rev-parse','HEAD') == old_head
    (target/'untracked.txt').unlink()
    (upstream/'extension.py').write_text(SCRIPT+'\n# version 2\n')
    git(upstream,'add','.')
    git(upstream,'commit','-m','update')
    assert not ext._git_extension_has_updates(ext.get_loaded_extensions()[0])
    assert '有更新' in ext.check_extension_updates()
    assert '请重启' in ext.update_extension('git_plugin')
    assert ext.get_loaded_extensions()[0].restart_required
    assert not callbacks.iter_callbacks('before_chat')
    ext.refresh_extension_list()
    assert ext.get_loaded_extensions()[0].restart_required
    ext.load_extensions(force=True)
    assert len(callbacks.iter_callbacks('before_chat')) == 1

@pytest.mark.parametrize('payload', ['[]','null','{"action":"toggle","id":7}','{"action":"toggle","id":"sample","enabled":"false"}'])
def test_action_payload_rejected(payload):
    assert '参数无效' in ext.handle_extension_action(payload)[0]


def test_relative_helpers_are_namespaced_and_failure_helpers_removed():
    a=plugin('first',script='from .helper import VALUE\nfrom modules.plugin_callbacks import on_before_chat\n@on_before_chat\ndef run(context): context.append(VALUE)\n')
    b=plugin('second',script='from .helper import VALUE\nfrom modules.plugin_callbacks import on_before_chat\n@on_before_chat\ndef run(context): context.append(VALUE)\n')
    (a/'helper.py').write_text('VALUE="first"\n')
    (b/'helper.py').write_text('VALUE="second"\n')
    broken=plugin('broken',script='from . import helper\nraise RuntimeError("broken")\n')
    (broken/'helper.py').write_text(SCRIPT)
    loaded=ext.load_extensions()
    result=[];callbacks.invoke('before_chat',result)
    assert result==['first','second']
    failed=next(x for x in loaded if x.id=='broken')
    assert not failed.module_names
    assert not any(getattr(module,'__file__','') and str(broken) in str(getattr(module,'__file__','')) for module in sys.modules.values())
    ext.load_extensions(force=True)
    result=[];callbacks.invoke('before_chat',result)
    assert result==['first','second']


def test_legacy_bare_helper_collision_fails_instead_of_crossusing():
    a=plugin('first',script='import same_helper\n')
    b=plugin('second',script='import same_helper\n')
    (a/'same_helper.py').write_text('VALUE="first"\n')
    (b/'same_helper.py').write_text('VALUE="second"\n')
    loaded=ext.load_extensions()
    assert next(x for x in loaded if x.id=='second').error
    assert 'conflicts' in next(x for x in loaded if x.id=='second').error

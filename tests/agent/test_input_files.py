from dataclasses import FrozenInstanceError, replace
import hashlib
import os
from pathlib import Path

import pytest

from modules.agent.input_files import AgentInputFiles, InputFileError, MAX_FILE_BYTES, read_snapshot_file


@pytest.fixture
def stager(tmp_path):
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    instance = AgentInputFiles([uploads], staging_parent=tmp_path)
    yield instance
    instance.close()


def upload(stager, name='report.csv', contents=b'a,b\n1,2\n', folder='one'):
    target = stager.upload_roots[0] / folder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(contents)
    return target


def test_snapshot_copies_bytes_hashes_and_keeps_safe_paths(stager):
    source = upload(stager, '报告 1.csv')
    record, = stager.set_pending([source])
    assert record.name == '报告 1.csv' and record.basename == '报告_1.csv'
    assert record.remote_path == f'/workspace/inputs/{record.input_id}/报告_1.csv'
    assert record.size == len(source.read_bytes())
    assert record.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert Path(record.staged_path) != source
    assert read_snapshot_file(record.to_dict(), staging_root=stager.staging_root) == source.read_bytes()
    assert Path(record.staged_path).stat().st_mode & 0o777 == 0o400
    with pytest.raises(FrozenInstanceError):
        record.size = 0


def test_repeated_event_and_duplicate_path_reuse_snapshot(stager):
    source = upload(stager)
    first = stager.set_pending([source, str(source)])
    second = stager.set_pending([source])
    assert first == second and len(first) == 1
    assert len(list(stager.staging_root.iterdir())) == 1
    stager.clear()
    assert stager.set_pending([source]) == first


def test_same_name_different_content_and_replaced_upload_stay_independent(stager):
    one = upload(stager, contents=b'one')
    two = upload(stager, contents=b'two', folder='two')
    first, second = stager.set_pending([one, two])
    assert first.name == second.name and first.input_id != second.input_id
    one.write_bytes(b'new')
    third, = stager.set_pending([one])
    assert third.input_id != first.input_id
    assert read_snapshot_file(first, staging_root=stager.staging_root) == b'one'


def test_submitted_selection_gets_new_id_without_deleting_retained_snapshot(stager):
    source = upload(stager)
    first, = stager.set_pending([source])
    stager.mark_submitted([first.input_id])
    stager.clear()
    second, = stager.set_pending([source])
    assert second.input_id != first.input_id and second.remote_path != first.remote_path
    assert read_snapshot_file(first, staging_root=stager.staging_root) == source.read_bytes()
    assert stager.set_pending([source]) == (second,)


def test_remove_and_clear_preserve_inflight_snapshot(stager):
    one, two = stager.set_pending([upload(stager), upload(stager, folder='two')])
    in_flight = stager.snapshot()
    assert stager.remove(one.input_id) == (two,)
    assert stager.clear() == ()
    assert len(in_flight) == 2
    for record in in_flight:
        assert read_snapshot_file(record, staging_root=stager.staging_root)


@pytest.mark.parametrize('kind', ['outside', 'sibling', 'link', 'directory_link', 'directory', 'missing', 'traversal', 'fifo'])
def test_reject_untrusted_and_nonregular_sources(stager, tmp_path, kind):
    source = upload(stager)
    outside = tmp_path / 'outside.csv'
    outside.write_bytes(b'private synthetic file')
    candidate = outside
    if kind == 'sibling':
        sibling = tmp_path / 'uploads-elsewhere'
        sibling.mkdir()
        candidate = sibling / 'file.csv'
        candidate.write_bytes(b'synthetic')
    elif kind == 'link':
        candidate = stager.upload_roots[0] / 'link.csv'
        candidate.symlink_to(source)
    elif kind == 'directory_link':
        link = stager.upload_roots[0] / 'link'
        link.symlink_to(source.parent, target_is_directory=True)
        candidate = link / source.name
    elif kind == 'directory':
        candidate = source.parent
    elif kind == 'missing':
        candidate = source.parent / 'missing'
    elif kind == 'traversal':
        candidate = stager.upload_roots[0] / '..' / outside.name
    elif kind == 'fifo':
        candidate = stager.upload_roots[0] / 'fifo'
        os.mkfifo(candidate)
    with pytest.raises(InputFileError):
        stager.set_pending([candidate])
    assert stager.snapshot() == ()


def test_failed_selection_keeps_existing_pending(stager, tmp_path):
    previous = stager.set_pending([upload(stager)])
    with pytest.raises(InputFileError):
        stager.set_pending([upload(stager, folder='two'), tmp_path / 'untrusted'])
    assert stager.snapshot() == previous


def test_add_merges_without_duplicating_and_is_atomic(stager, tmp_path):
    one = upload(stager)
    first = stager.add([one])
    both = stager.add([one, upload(stager, folder='two')])
    assert len(both) == 2 and both[0] == first[0]
    with pytest.raises(InputFileError):
        stager.add([tmp_path / 'not-an-upload'])
    assert stager.snapshot() == both


def test_file_limit_checked_before_copy_and_no_arbitrary_count_limit(stager):
    oversized = upload(stager)
    with oversized.open('wb') as target:
        target.truncate(MAX_FILE_BYTES + 1)
    with pytest.raises(InputFileError, match='50 MiB'):
        stager.set_pending([oversized])
    assert not list(stager.staging_root.iterdir())
    records = stager.set_pending([upload(stager, folder=str(index), contents=b'') for index in range(51)])
    assert len(records) == 51 and all(record.size == 0 for record in records)


@pytest.mark.parametrize('tamper', ['same_size', 'size', 'symlink', 'metadata', 'remote', 'escape'])
def test_worker_read_rejects_changed_or_forged_snapshot(stager, tmp_path, tamper):
    record, = stager.set_pending([upload(stager, contents=b'abc')])
    path = Path(record.staged_path)
    if tamper in ('same_size', 'size'):
        path.chmod(0o600)
        path.write_bytes(b'xyz' if tamper == 'same_size' else b'longer')
    elif tamper == 'symlink':
        path.unlink()
        path.symlink_to(upload(stager, contents=b'abc', folder='two'))
    elif tamper == 'metadata':
        record = replace(record, size=True)
    elif tamper == 'remote':
        record = replace(record, remote_path='/workspace/wrong')
    else:
        record = replace(record, staged_path=str(tmp_path / record.basename))
    with pytest.raises(InputFileError):
        read_snapshot_file(record.to_dict(), staging_root=stager.staging_root)


def test_different_conversations_have_separate_staging_roots(stager, tmp_path):
    other = AgentInputFiles(stager.upload_roots, staging_parent=tmp_path)
    try:
        source = upload(stager)
        one, = stager.set_pending([source])
        two, = other.set_pending([source])
        assert one.input_id != two.input_id and one.staged_path != two.staged_path
        with pytest.raises(InputFileError):
            read_snapshot_file(one, staging_root=other.staging_root)
    finally:
        other.close()


def test_default_root_uses_gradio_upload_directory(monkeypatch, tmp_path):
    from gradio import utils
    upload_root = tmp_path / 'gradio-upload'
    upload_root.mkdir()
    monkeypatch.setattr(utils, 'get_upload_folder', lambda: str(upload_root))
    stager = AgentInputFiles(staging_parent=tmp_path)
    try:
        assert stager.upload_roots == (upload_root,)
    finally:
        stager.close()


@pytest.fixture
def aliased_stager(tmp_path):
    canonical_parent = tmp_path / 'private' / 'tmp'
    canonical_parent.mkdir(parents=True)
    canonical_root = canonical_parent / 'gradio'
    canonical_root.mkdir()
    alias = tmp_path / 'tmp'
    alias.symlink_to(canonical_parent, target_is_directory=True)
    instance = AgentInputFiles([alias / 'gradio'], staging_parent=alias)
    yield instance, alias, canonical_root
    instance.close()


def test_configured_root_aliases_and_staging_parent_are_canonicalized(aliased_stager):
    stager, alias, canonical_root = aliased_stager
    canonical_file = upload(stager, contents=b'alias-safe snapshot')
    alias_file = alias / 'gradio' / canonical_file.relative_to(canonical_root)
    first = stager.set_pending([alias_file])
    assert stager.upload_roots == (canonical_root,)
    assert stager.staging_root.parent == canonical_root.parent
    assert stager.staging_root == stager.staging_root.resolve()
    assert stager.set_pending([canonical_file, alias_file]) == first
    assert len(list(stager.staging_root.iterdir())) == 1
    assert read_snapshot_file(first[0].to_dict(), staging_root=stager.staging_root) == b'alias-safe snapshot'


@pytest.mark.parametrize('through_alias', [False, True])
@pytest.mark.parametrize('kind', ['file_link', 'directory_link'])
def test_canonicalized_root_still_rejects_links_inside_uploads(aliased_stager, through_alias, kind):
    stager, alias, canonical_root = aliased_stager
    source = upload(stager)
    if kind == 'file_link':
        candidate = canonical_root / 'linked.csv'
        candidate.symlink_to(source)
    else:
        link = canonical_root / 'linked-directory'
        link.symlink_to(source.parent, target_is_directory=True)
        candidate = link / source.name
    if through_alias:
        candidate = alias / 'gradio' / candidate.relative_to(canonical_root)
    with pytest.raises(InputFileError):
        stager.set_pending([candidate])
    assert stager.snapshot() == ()


def test_configured_alias_is_not_reresolved_for_each_file(aliased_stager, tmp_path):
    stager, alias, canonical_root = aliased_stager
    source = upload(stager, contents=b'original trusted root')
    replacement = tmp_path / 'replacement'
    counterfeit = replacement / 'gradio' / source.relative_to(canonical_root)
    counterfeit.parent.mkdir(parents=True)
    counterfeit.write_bytes(b'new alias target')
    alias.unlink()
    alias.symlink_to(replacement, target_is_directory=True)
    record, = stager.set_pending([alias / 'gradio' / source.relative_to(canonical_root)])
    assert read_snapshot_file(record, staging_root=stager.staging_root) == b'original trusted root'


def test_alias_prefix_does_not_allow_sibling_or_traversal(aliased_stager, tmp_path):
    stager, alias, _ = aliased_stager
    sibling = tmp_path / 'tmp-sibling' / 'gradio' / 'file.csv'
    sibling.parent.mkdir(parents=True)
    sibling.write_bytes(b'synthetic outside data')
    for candidate in (sibling, alias / 'gradio' / '..' / 'file.csv'):
        with pytest.raises(InputFileError):
            stager.set_pending([candidate])

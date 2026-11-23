import pytest

from app.errors import DeskError
from app.input import sample
from app.modules.archive.service import archive
from app.modules.archive.store import Archive
from app.modules.legs.contracts import references
from app.modules.retags.identity import resolve
from app.modules.retags.service import read_retags
from app.pipeline import compute


@pytest.fixture
def retag():
    return compute(sample('retag'))


def _orders(files):
    from app.modules.legs.contracts import references
    _, manifest, _ = references(files['legs.csv'], files['manifest.csv'])
    return read_retags(files['retags.csv'], manifest)


def test_late_offload_returns_to_original_piece(retag):
    # TRAP-RETAG-1：迟到撤下按生效时刻归回换牌前的原实物，末态仍为装载
    rows = [r for r in retag['replay']['rows'] if r['piece'] == '000301']
    assert [(r['event'], r['tag'], r['late'], r['after']) for r in rows] == [
        ('R01', '000201', False, 'LOADED'),
        ('R02', '000201', True, 'OFFLOADED'),
        ('R03', '000301', False, 'LOADED'),
    ]
    state = next(s for s in retag['replay']['states'] if s['piece'] == '000301')
    assert state['state'] == 'LOADED' and state['tags'] == ['000201', '000301']


def test_reissued_old_tag_is_a_separate_piece(retag):
    # TRAP-RETAG-2：旧牌换发后再出现是另一件，禁止并入新牌实物的装机
    row = next(r for r in retag['replay']['rows'] if r['event'] == 'R04')
    assert row['piece'] == '000201' and row['attribution'] == 'TAG_REISSUED'
    decision = next(r for r in retag['exceptions']['rows'] if r['piece'] == '000201')
    assert decision['status'] == 'unlisted'
    original = next(r for r in retag['exceptions']['rows'] if r['piece'] == '000301')
    assert original['status'] == 'loaded' and original['manifest_tag'] == '000201'


def test_anchor_before_retag_is_uncertain_and_traceable(retag):
    # TRAP-RETAG-3：新牌早于换牌生效出现，归属存疑隔离，原行号可查原件
    uncertain = retag['replay']['uncertain']
    assert [(r['event'], r['reason'], r['line']) for r in uncertain] == [('R06', 'RETAG_ANCHOR', 7)]
    decision = next(r for r in retag['exceptions']['rows'] if r['piece'] == '000303')
    assert decision['status'] == 'pending' and decision['reason'] == 'UNCERTAIN'
    assert 7 in decision['source_lines']


def test_ledger_counts_physical_pieces(retag):
    counts = retag['ledger']['counts']
    assert (counts['manifest'], counts['pieces'], counts['retagged'], counts['unlisted']) == (3, 4, 2, 1)
    assert retag['ledger']['balanced']
    # 航段小计只含有计划的实物，清单外另发的一件不摊入航段
    assert sum(r['pieces'] for r in retag['ledger']['rows']) == 3
    assert sum(r['manifest'] for r in retag['ledger']['rows']) == 3


def test_missing_slip_inflates_pieces_then_corrects():
    without = compute(dict(sample('retag'), **{'retags.csv': ''}))
    with_slip = compute(sample('retag'))
    assert without['ledger']['counts']['pieces'] == 5
    assert without['ledger']['counts']['unlisted'] == 2
    assert with_slip['ledger']['counts']['pieces'] == 4
    # 补单后同一实物只计一件，待证回落
    assert with_slip['ledger']['counts']['pending'] == 1


def test_identity_guard_against_blind_merge():
    files = sample('retag')
    parsed = _orders(files)
    # 构造：换牌后旧牌的装机不能算到新牌实物上
    rows = [dict(event='X1', tag='000201', leg='NX-01', action='LOAD',
                 effective='2026-11-20T15:55:00.000000Z', received='2026-11-20T15:56:00.000000Z', line=9)]
    identity = resolve(rows, parsed['indexes'])
    assert identity['rows'][0]['piece'] == '000201'
    assert identity['rows'][0]['attribution'] == 'TAG_REISSUED'


def test_new_tag_loading_before_effective_is_anchored():
    files = sample('retag')
    parsed = _orders(files)
    rows = [dict(event='X2', tag='000301', leg='NX-01', action='LOAD',
                 effective='2026-11-20T15:40:00.000000Z', received='2026-11-20T15:41:00.000000Z', line=10)]
    identity = resolve(rows, parsed['indexes'])
    assert not identity['rows']
    assert identity['isolated'][0]['reason'] == 'RETAG_ANCHOR'


def test_hard_error_when_new_tag_already_planned():
    files = sample('retag')
    _, manifest, _ = references(files['legs.csv'], files['manifest.csv'])
    bad = files['retags.csv'].replace('000201,000301', '000201,000202')
    with pytest.raises(DeskError, match='虚增待证件'):
        read_retags(bad, manifest)


def test_duplicate_old_tag_rejected():
    files = sample('retag')
    _, manifest, _ = references(files['legs.csv'], files['manifest.csv'])
    bad = files['retags.csv'] + '000201,000399,2026-11-21T00:20:00+08:00\n'
    with pytest.raises(DeskError, match='换牌链'):
        read_retags(bad, manifest)


def test_chained_retag_rejected_in_either_direction():
    files = sample('retag')
    _, manifest, _ = references(files['legs.csv'], files['manifest.csv'])
    chain = ('old_tag,new_tag,effective\n'
             '000201,000301,2026-11-20T23:50:00+08:00\n'
             '000301,000399,2026-11-21T00:00:00+08:00\n')
    with pytest.raises(DeskError) as exc:
        read_retags(chain, manifest)
    assert exc.value.code == 'RETAG_CHAIN'


def test_bad_timestamp_isolated_as_time_not_missing():
    files = sample('retag')
    _, manifest, _ = references(files['legs.csv'], files['manifest.csv'])
    result = read_retags(
        'old_tag,new_tag,effective\n000250,000350,不是时刻\n' + files['retags.csv'], manifest)
    assert [row['reason'] for row in result['isolated']] == ['TIME']
    assert result['counts']['orders'] == 2


def test_missing_fields_are_isolated_not_fatal():
    files = sample('retag')
    _, manifest, _ = references(files['legs.csv'], files['manifest.csv'])
    result = read_retags(files['retags.csv'] + '000250,,2026-11-21T00:20:00+08:00\n', manifest)
    assert result['counts']['orders'] == 2 and result['isolated'][0]['reason'] == 'MISSING'


def test_archive_rerun_is_idempotent(tmp_path):
    store = Archive(tmp_path / 'retag.sqlite3')
    first = archive(store, sample('retag'), compute)
    second = archive(store, sample('retag'), compute)
    assert first['id'] == second['id'] and second['reused']
    assert second['manifest']['result_sha256'] == first['manifest']['result_sha256']
    assert len(store.list()) == 1 and second['counts']['pieces'] == 4


def test_slip_added_changes_batch_and_keeps_single_archive(tmp_path):
    store = Archive(tmp_path / 'two.sqlite3')
    without = archive(store, dict(sample('retag'), **{'retags.csv': ''}), compute)
    with_slip = archive(store, sample('retag'), compute)
    assert without['id'] != with_slip['id']
    assert len(store.list()) == 2
    # 同批重跑不产生第三条归档
    again = archive(store, sample('retag'), compute)
    assert again['id'] == with_slip['id'] and len(store.list()) == 2


def test_build_indexes_roundtrip():
    files = sample('retag')
    parsed = _orders(files)
    assert set(parsed['indexes']['by_old']) == {'000201', '000203'}
    assert set(parsed['indexes']['by_new']) == {'000301', '000303'}


def test_api_stages_and_rendered_views(desk):
    payload = desk.get('/api/stage/replay?sample=retag').json
    assert payload['counts']['retag_pieces'] == 2
    assert [r['reason'] for r in payload['uncertain']] == ['RETAG_ANCHOR']
    for view in ('replay', 'ledger', 'exceptions', 'legs'):
        response = desk.get(f'/desk/{view}?sample=retag')
        assert response.status_code == 200
    assert desk.get('/api/stage/ledger?sample=retag').json['counts']['pieces'] == 4


def test_api_accepts_three_files_without_slip(desk):
    files = {key: value for key, value in sample('retag').items() if key != 'retags.csv'}
    response = desk.post('/api/archive', json={'files': files})
    assert response.status_code == 200 and response.json['counts']['pieces'] == 5


def test_rejected_retag_batch_leaves_no_archive(desk):
    files = {
        'scans.csv': 'event,tag,flight,leg_hint,action,effective,received\nZ1,000201,NX518,,LOAD,2026-11-20T23:42:00+08:00,2026-11-20T23:43:00+08:00\n',
        'legs.csv': 'leg,flight,start,end,destination\nNX-01,NX518,2026-11-20T23:00:00+08:00,2026-11-21T00:30:00+08:00,宁波\n',
        'manifest.csv': 'tag,planned\n000201,NX-01\n000202,NX-01\n',
        'retags.csv': 'old_tag,new_tag,effective\n000201,000202,2026-11-20T23:50:00+08:00\n',
    }
    response = desk.post('/api/archive', json={'files': files})
    assert (response.status_code, response.json['code']) == (422, 'RETAG_PLAN_CONFLICT')
    assert desk.get('/api/archive').json['count'] == 0


def test_leg_unresolved_rows_still_follow_piece_identity():
    files = dict(sample('retag'))
    files['scans.csv'] += 'R08,000301,ZZ999,,LOAD,2026-11-21T00:10:00+08:00,2026-11-21T00:11:00+08:00\n'
    merged = compute(files)
    row = next(r for r in merged['exceptions']['rows'] if r['piece'] == '000301')
    assert 9 in row['source_lines'] and row['status'] == 'pending'

    other_files = dict(sample('retag'))
    other_files['scans.csv'] += 'R09,000201,ZZ999,,LOAD,2026-11-21T00:10:00+08:00,2026-11-21T00:11:00+08:00\n'
    separate = compute(other_files)
    other = next(r for r in separate['exceptions']['rows'] if r['piece'] == '000201')
    assert other['status'] == 'unlisted' and 9 in other['source_lines']
    assert separate['ledger']['counts']['pieces'] == 4


def test_evidence_bundle_contains_retag_original(desk):
    saved = desk.post('/api/archive', json={'sample': 'retag'}).json
    bundle = desk.get(f"/api/evidence/{saved['id']}/export").json
    assert 'retags.csv' in bundle['originals']
    assert bundle['manifest']['inputs']['retags.csv']
    assert bundle['manifest']['version'] == 'leg-luggage/2'
    page = desk.get(f"/desk/evidence?run={saved['id']}")
    assert page.status_code == 200 and 'retags.csv' in page.get_data(as_text=True)
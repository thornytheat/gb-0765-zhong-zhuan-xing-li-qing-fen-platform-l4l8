from .modules.scans.service import ingest
from .modules.legs.contracts import references
from .modules.legs.service import associate
from .modules.retags.service import read_retags
from .modules.retags.identity import resolve
from .modules.replay.service import replay
from .modules.exceptions.service import classify
from .modules.ledger.service import reconcile


def compute(files, until=None):
    scans = ingest(files['scans.csv'])
    if until == 'scans':
        return scans
    legs, manifest, master_errors = references(files['legs.csv'], files['manifest.csv'])
    retags = read_retags(files.get('retags.csv', ''), manifest)
    linked = associate(scans['rows'], legs)
    linked.update(legs=list(legs.values()), manifest=list(manifest.values()), reference_isolated=master_errors,
                  retags=retags['orders'], retag_counts=retags['counts'])
    if until == 'legs':
        return linked
    identity = resolve(linked['rows'], retags['indexes'])
    history = replay(identity['rows'], identity['isolated'])
    history.update(orders=retags['orders'], retag_isolated=retags.get('isolated', []))
    if until == 'replay':
        return history
    decisions = classify(manifest, history['states'],
                         scans['isolated'] + linked['isolated'] + identity['isolated'], retags['indexes'])
    if until == 'exceptions':
        return decisions
    ledger = reconcile(decisions, legs, scans['counts'])
    if until == 'ledger':
        return ledger
    return dict(scans=scans, legs=linked, replay=history, exceptions=decisions, ledger=ledger)

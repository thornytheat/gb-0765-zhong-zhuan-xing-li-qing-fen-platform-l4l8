from itertools import groupby
from .radio import sequence


def replay(rows, uncertain=None):
    timeline, states, conflicts, repeats = [], [], [], []
    uncertain = uncertain or []
    for (piece, leg), stream in groupby(sequence(rows), key=lambda r: (r['piece'], r['leg'])):
        state, sources, tags, retag_lines = 'UNSEEN', [], set(), set()
        for _, same_time in groupby(stream, key=lambda r: r['effective']):
            group = list(same_time)
            motions = {r['action'] for r in group} - {'SORT'}
            before = state
            if len(motions) == 2:
                state = 'CONFLICT'
                conflicts.extend(dict(r, reason='SIMULTANEOUS') for r in group if r['action'] in motions)
            elif motions:
                state = 'LOADED' if 'LOAD' in motions else 'OFFLOADED'
            sources.extend(r['line'] for r in group)
            tags.update(r['tag'] for r in group)
            retag_lines.update(r['retag']['line'] for r in group if r.get('retag'))
            seen = set()
            for r in group:
                if r['action'] in seen:
                    repeats.append(dict(r, reason='RF_REPEAT'))
                else:
                    timeline.append(dict(r, before=before, after=state))
                seen.add(r['action'])
        states.append(dict(tag=piece, piece=piece, leg=leg, state=state, source_lines=sources,
                           tags=sorted(tags), retag_lines=sorted(retag_lines)))
    return dict(rows=timeline, states=states, isolated=conflicts, repeats=repeats,
                uncertain=uncertain,
                counts=dict(late=sum(row['late'] for row in timeline), states=len(states),
                            conflicts=len(conflicts), retag_pieces=len({s['piece'] for s in states if s['retag_lines']})))

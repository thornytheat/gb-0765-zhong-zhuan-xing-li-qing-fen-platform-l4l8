from collections import Counter, defaultdict
from .policy import verdict


def classify(manifest, states, undecided, indexes=None):
    indexes = indexes or {'by_old': {}, 'by_new': {}}
    by_piece, issues = defaultdict(dict), defaultdict(list)
    for state in states:
        by_piece[state['piece']][state['leg']] = state
    for row in undecided:
        if row.get('tag') and row.get('action') != 'SORT':
            issues[_owner(row, indexes)].append(row['line'])
    # 清单牌号 -> 实物件；planned 仍记计划航段号，保持对账口径不变
    planned_piece = {tag: _piece_of(tag, indexes) for tag in manifest}
    piece_manifest = {owner: tag for tag, owner in planned_piece.items()}
    decisions, wrong = [], []
    pieces = set(by_piece) | set(issues) | set(planned_piece.values())
    for piece in sorted(pieces):
        manifest_tag = piece_manifest.get(piece)
        entry = manifest.get(manifest_tag) if manifest_tag else None
        planned_leg = entry['planned'] if entry else None
        known = by_piece[piece]
        off_plan = sorted(leg for leg, state in known.items()
                          if planned_leg and leg != planned_leg and state['state'] == 'LOADED')
        for leg in off_plan:
            wrong.append(dict(known[leg], planned=planned_leg, reason='WRONG_LEG'))
        disputed = issues[piece] or any(state['state'] == 'CONFLICT' for state in known.values())
        status, reason = verdict(known.get(planned_leg, {}).get('state'), off_plan, disputed) if entry else ('unlisted', 'UNLISTED')
        lines = sorted(set(issues[piece]).union(*(state['source_lines'] for state in known.values())))
        observed = set().union(*(state['tags'] for state in known.values())) if known else set()
        if manifest_tag:
            observed.add(manifest_tag)
        decisions.append(dict(tag=piece, piece=piece, tags=sorted(observed), planned=planned_leg,
                              manifest_tag=manifest_tag, manifest_line=entry['line'] if entry else None,
                              retagged=piece in indexes['by_new'],
                              status=status, reason=reason, wrong_legs=off_plan, source_lines=lines))
    return dict(rows=decisions, wrong=wrong, counts=dict(Counter(row['status'] for row in decisions)))


def _piece_of(tag, indexes):
    order = indexes['by_old'].get(tag)
    return order['new_tag'] if order else tag


def _owner(row, indexes):
    """存疑/隔离行没有 piece 字段时，按换牌单推断实物，查不到则以牌自成一件。"""
    piece = row.get('piece')
    if piece:
        return piece
    order = indexes['by_old'].get(row['tag'])
    if order and row['effective'] < order['effective']:
        return order['new_tag']
    order = indexes['by_new'].get(row['tag'])
    if order and row['effective'] >= order['effective']:
        return order['new_tag']
    return row['tag']

def resolve(rows, indexes):
    """把每条航段关联后的扫描归到实物件。

    归属规则（换牌单按生效时刻切分）：
    - 旧牌扫描：生效早于换牌 -> 原实物（换牌后旧牌会发给别的行李，晚到的撤下按生效时刻仍归原件）；
      生效不早于换牌 -> 旧牌已另发，独立成件，禁止贸然并入新牌实物；
    - 新牌扫描：生效不早于换牌 -> 换牌实物；早于换牌 -> 归属存疑，整行隔离，可凭原行号查原件；
    - 无换牌单：牌即实物。
    """
    by_old, by_new = indexes['by_old'], indexes['by_new']
    linked, uncertain = [], []
    for row in rows:
        tag = row['tag']
        order = by_old.get(tag)
        if order is not None:
            if row['effective'] < order['effective']:
                linked.append(_piece(row, order['new_tag'], order, 'BEFORE_RETAG'))
            else:
                linked.append(_piece(row, tag, None, 'TAG_REISSUED'))
            continue
        order = by_new.get(tag)
        if order is not None:
            if row['effective'] >= order['effective']:
                linked.append(_piece(row, tag, order, 'AFTER_RETAG'))
            else:
                uncertain.append(dict(row, reason='RETAG_ANCHOR'))
            continue
        linked.append(_piece(row, tag, None, None))
    return dict(rows=linked, isolated=uncertain, counts=dict(
        resolved=len(linked), uncertain=len(uncertain)))


def _piece(row, piece, order, attribution):
    extra = dict(piece=piece, attribution=attribution)
    if order is not None:
        extra['retag'] = dict(old_tag=order['old_tag'], new_tag=order['new_tag'],
                              effective=order['effective'], line=order['line'])
    return dict(row, **extra)

from app.clock import utc
from app.errors import DeskError
from app.modules.scans.csvio import read_table
from app.modules.scans.normalize import SENTINELS

COLUMNS = ('old_tag', 'new_tag', 'effective')


def read_retags(text, manifest):
    """解析换牌单。缺单（空文本）按无换牌处理，整单矛盾则拒绝整批。"""
    if text is None or not text.strip():
        return dict(orders=[], indexes=dict(by_old={}, by_new={}), isolated=[], counts=dict(orders=0, missing=0))
    rows, isolated, counts = read_table(text, COLUMNS, 'retags.csv')
    orders, missing = [], []
    for row in rows:
        row.update({field: row[field].strip() for field in COLUMNS})
        if any(row[field] in SENTINELS for field in COLUMNS):
            missing.append(dict(row, reason='MISSING'))
            continue
        try:
            row['effective'] = utc(row['effective'])
        except ValueError:
            missing.append(dict(row, reason='TIME'))
            continue
        orders.append(row)
    _hard_validate(orders, manifest)
    indexes = build_indexes(orders)
    counts.update(orders=len(orders), missing=len(missing))
    return dict(orders=orders, indexes=indexes, isolated=missing, counts=counts)


def _hard_validate(orders, manifest):
    seen_old, seen_new = set(), set()
    for row in orders:
        if row['old_tag'] in seen_old:
            raise DeskError('RETAG_CHAIN', f"retags.csv 第 {row['line']} 行旧牌重复换牌，换牌链暂不支持")
        if row['new_tag'] in seen_new:
            raise DeskError('MASTER_CONFLICT', f"retags.csv 第 {row['line']} 行新牌重复")
        if row['old_tag'] == row['new_tag']:
            raise DeskError('RETAG_SAME_TAG', f"retags.csv 第 {row['line']} 行新旧牌相同")
        if row['old_tag'] in seen_new or row['new_tag'] in seen_old:
            raise DeskError('RETAG_CHAIN', f"retags.csv 第 {row['line']} 行与另一换牌首尾相接，换牌链暂不支持")
        seen_old.add(row['old_tag'])
        seen_new.add(row['new_tag'])
    planned = set(manifest)
    overlap = sorted(planned & seen_new)
    if overlap:
        raise DeskError('RETAG_PLAN_CONFLICT', f"新牌 {overlap[0]} 已在清单计件，换牌会虚增待证件")


def build_indexes(orders):
    """旧牌 -> 换牌序列；新牌 -> 换牌序列。同旧牌至多一单（硬校验保证）。"""
    by_old, by_new = {}, {}
    for row in orders:
        by_old[row['old_tag']] = row
        by_new[row['new_tag']] = row
    return dict(by_old=by_old, by_new=by_new)

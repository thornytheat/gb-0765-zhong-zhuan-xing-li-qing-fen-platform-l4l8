# 深度登记 中转行李清分台

中转主管逐牌核对航段窗口与动作末态。跨日同航班号不能替代航段实例。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 扫描原件采信 | 查看射频重报和隔离行 | `/desk/scans` `/api/stage/scans` | `app/modules/scans/service.py` | `tests/test_scans.py` |
| M2 航段候选关联 | 核对候选段和提示 | `/desk/legs` `/api/stage/legs` | `app/modules/legs/service.py` | `tests/test_legs.py` |
| M3 扫件有序回放 | 按生效时刻核对动作（含换牌实物归属） | `/desk/replay` `/api/stage/replay` | `app/modules/replay/service.py` `app/modules/retags/identity.py` | `tests/test_replay.py` `tests/test_retags.py` |
| M4 错载与漏扫归因 | 按牌追踪待证与错装 | `/desk/exceptions` `/api/stage/exceptions` | `app/modules/exceptions/service.py` | `tests/test_exceptions.py` |
| M5 行李去向对账 | 勾稽计划段与去向件数 | `/` `/api/stage/ledger` | `app/modules/ledger/service.py` | `tests/test_ledger.py` |
| M6 批次留档复跑 | 保存并复算原件 | `/desk/archive` `POST /api/archive` | `app/modules/archive/service.py` `app/modules/archive/store.py` | `tests/test_archive.py` |
| M7 联程证据签发 | 验摘要并下载联程证据 | `/desk/evidence` `/api/evidence/<run>/export` | `app/modules/evidence/bundle.py` | `tests/test_evidence.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-02 | 脏扫描首列 BOM | 扫描号丢失 | 解码时去首 BOM | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_bom` |
| TRAP-04 | 脏扫描第 16 行重复表头 | 误计为扫描 | 计独立分段 | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_sections` |
| TRAP-05 | E17 多余分隔列 | 宽度误收 | 原行隔离 | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_bad_width` |
| TRAP-07 | E18 时间 N/A | 默认零时 | 空值隔离 | `app/modules/scans/normalize.py` | `tests/test_scans.py::test_sentinel` |
| TRAP-08 | 清单 000101 | 强转丢零 | 字符串关联 | `app/modules/legs/contracts.py` | `tests/test_legs.py::test_tag_preserved` |
| TRAP-11 | E03 特殊偏移重复 | 误认成不同事件 | UTC 后比较 | `app/modules/scans/normalize.py` | `tests/test_scans.py::test_equivalent_offset_duplicate` |
| TRAP-13 | E02 迟到撤下 | 收件顺序末态错误 | 标迟到后按生效回放 | `app/modules/replay/radio.py` | `tests/test_replay.py::test_late_offload_before_reload` |
| TRAP-14 | E12 同键相反动作 | 后写覆盖 | 全组隔离 | `app/modules/scans/service.py` | `tests/test_scans.py::test_conflicting_id` |
| TRAP-23 | E04 恰逢跨日换窗 | 同时匹配两段 | 左闭右开 | `app/modules/legs/service.py` | `tests/test_legs.py::test_boundary_handoff` |
| TRAP-31 | 破损行李换牌，迟到撤下挂旧牌 | 按收件顺序或按牌并件，撤下丢失或错配 | 按生效时刻把换牌前扫描归原实物，回放以实物件为键 | `app/modules/retags/identity.py` `app/modules/replay/radio.py` | `tests/test_retags.py::test_late_offload_returns_to_original_piece` |
| TRAP-32 | 换牌后旧牌发给别的行李 | 贸然把新旧牌合并，别件装机被算进来 | 换牌生效后旧牌扫描独立成件 `TAG_REISSUED`，清单外另列 | `app/modules/retags/identity.py` | `tests/test_retags.py::test_reissued_old_tag_is_a_separate_piece` |
| TRAP-33 | 换牌单未到齐 | 新旧牌各算一件，虚增待证件数 | 无单时按牌计件保留差异；补单后按实物纠偏，哈希决定新批次 | `app/modules/retags/service.py` `app/pipeline.py` | `tests/test_retags.py::test_missing_slip_inflates_pieces_then_corrects` |
| TRAP-34 | 新牌扫描早于换牌生效 | 直接采信造成身份穿越 | `RETAG_ANCHOR` 整行隔离、计待证，原行号可查原件 | `app/modules/retags/identity.py` | `tests/test_retags.py::test_anchor_before_retag_is_uncertain_and_traceable` |
| TRAP-35 | 同批重跑重复记件 | 复算产生新批次或件数累加 | 内容哈希唯一键，同源复用归档 | `app/modules/archive/store.py` | `tests/test_retags.py::test_archive_rerun_is_idempotent` |

## 对账规则

脏样例清单 12 = 3 已装 + 8 待证 + 1 明确未装，错装 2 件另列。扫描原件记录 24 = 17 采信 + 4 隔离 + 1 重报 + 1 重复表头 + 1 空行。

换牌样例按实物计 4 件 = 2 已装 + 1 待证 + 1 清单外；清单 3 件映射到 3 个实物，其中 2 件持换牌单。撤掉换牌单后退化为按牌 5 件（清单外 2 件），补单即更正。

## 已知范围

文件内容通过限长 JSON 提交。样例为机场单站观测，时间窗由机场清单提供。扫描尾播放已采信记录的收件流。换牌仅支持旧牌一次性换发（同旧牌重复换牌按换牌链拒绝），换牌单为可选第四份原件。

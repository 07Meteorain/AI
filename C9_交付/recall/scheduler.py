"""SM-2 排程器。

**没有自创算法。** 间隔重复已经被研究了几十年，一个自创且未经验证的公式
最可能的结果是「看起来很科学，实际上把复习节奏搞乱」。这里采用 SuperMemo 2
（1987 年公开的规格），它的每个数字都能手算核对，出错时也容易定位。

规格（与公开描述一致）：
- 初始 EF = 2.5；
- q >= 3 时：第 1 次间隔 1 天，第 2 次 6 天，之后 round(上次间隔 × EF)；
- q < 3 时：重复次数清零，间隔回到 1 天（当天记为一次 lapse）；
- EF' = EF + (0.1 - (5-q) × (0.08 + (5-q) × 0.02))，下限 1.3。

评分映射（四档 → SM-2 的 q）：
1 忘记 → 2 ｜ 2 困难 → 3 ｜ 3 记得 → 4 ｜ 4 简单 → 5

召回率目标 90%（SM-2 的原始假设），因此 `due` 就是「今天该复习」。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

MIN_EF = 1.3
LEECH_THRESHOLD = 8

GRADE_LABELS = {1: "忘记", 2: "困难", 3: "记得", 4: "简单"}
_QUALITY = {1: 2, 2: 3, 3: 4, 4: 5}


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def today_iso() -> str:
    return date.today().isoformat()


@dataclass(frozen=True)
class State:
    ef: float = 2.5
    reps: int = 0
    interval: int = 0
    due: str = ""
    lapses: int = 0
    suspended: bool = False
    last_review: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "ef": round(self.ef, 4),
            "reps": self.reps,
            "interval": self.interval,
            "due": self.due,
            "lapses": self.lapses,
            "suspended": self.suspended,
            "last_review": self.last_review,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, object]]) -> "State":
        if not data:
            return cls()
        return cls(
            ef=float(data.get("ef", 2.5)),
            reps=int(data.get("reps", 0)),
            interval=int(data.get("interval", 0)),
            due=str(data.get("due", "")),
            lapses=int(data.get("lapses", 0)),
            suspended=bool(data.get("suspended", False)),
            last_review=str(data.get("last_review", "")),
        )

    @property
    def is_new(self) -> bool:
        return self.reps == 0 and self.interval == 0 and not self.due


def review(state: State, grade: int, today: Optional[date] = None) -> State:
    """执行一次复习，返回新状态。grade 为 1–4。"""
    if grade not in _QUALITY:
        raise ValueError("grade 必须是 1–4，收到 {!r}".format(grade))
    today = today or date.today()
    q = _QUALITY[grade]
    ef = state.ef
    reps = state.reps
    interval = state.interval
    lapses = state.lapses

    if q < 3:
        reps = 0
        interval = 1
        lapses += 1
    else:
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            # 显式「四舍五入」而不是 Python 的银行家舍入，
            # 以便与 Web 端 JS 的 Math.round 逐位一致。
            interval = max(1, int(interval * ef + 0.5))
        reps += 1

    # EF 的更新使用「本次评分之前」的间隔，这是 SM-2 的原始顺序
    ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    ef = max(MIN_EF, round(ef, 4))

    due = (today + timedelta(days=interval)).isoformat()
    return State(
        ef=ef,
        reps=reps,
        interval=interval,
        due=due,
        lapses=lapses,
        suspended=lapses >= LEECH_THRESHOLD,
        last_review=today.isoformat(),
    )


def is_due(state: State, today: Optional[date] = None) -> bool:
    if state.suspended or not state.due:
        return False
    today = today or date.today()
    try:
        return parse_date(state.due) <= today
    except ValueError:
        return False


def days_until(due: str, today: Optional[date] = None) -> int:
    if not due:
        return 0
    try:
        return (parse_date(due) - (today or date.today())).days
    except ValueError:
        return 0


def retentivity(state: State, today: Optional[date] = None) -> float:
    """粗略的当前记忆保持率 R = 0.9^(elapsed/interval)。

    只用于展示（告诉用户「这张卡大概还记得多少」），不参与排程决策。
    """
    if not state.due or state.interval <= 0:
        return 0.0
    elapsed = max(0, state.interval - days_until(state.due, today))
    return round(0.9 ** (elapsed / max(1, state.interval)), 3)


def due_cards(
    cards: Sequence[object],
    states: Dict[str, State],
    today: Optional[date] = None,
) -> List[object]:
    out = []
    for card in cards:
        state = states.get(getattr(card, "id", ""))
        if state and is_due(state, today):
            out.append(card)
    out.sort(key=lambda c: (states[getattr(c, "id")].due, getattr(c, "source", ""), getattr(c, "line", 0)))
    return out


def build_queue(
    cards: Sequence[object],
    states: Dict[str, State],
    today: Optional[date] = None,
    limit: int = 20,
    new_limit: int = 20,
    include_candidates: bool = False,
) -> List[Tuple[object, bool]]:
    """返回 [(card, is_new)]：先到期，再新卡，最后才是提前复习。"""
    today = today or date.today()
    approved = [
        c
        for c in cards
        if include_candidates or getattr(c, "status", "approved") == "approved"
    ]
    due: List[object] = []
    new: List[object] = []
    for card in approved:
        state = states.get(getattr(card, "id", ""))
        if state is None:
            new.append(card)
        elif state.suspended:
            continue
        elif is_due(state, today):
            due.append(card)
    due.sort(key=lambda c: (states[getattr(c, "id")].due, getattr(c, "source", ""), getattr(c, "line", 0)))
    new.sort(key=lambda c: (getattr(c, "source", ""), getattr(c, "line", 0)))
    queue = [(card, False) for card in due]
    queue.extend((card, True) for card in new[:new_limit])
    return queue[:limit]


def golden_vectors() -> List[Dict[str, object]]:
    """给 Web 端 JS 用的对照向量，保证两端排程完全一致。"""
    sequences = [
        ("new-good-x4", [], [3, 3, 3, 3]),
        ("new-easy", [], [4]),
        ("new-hard", [], [2]),
        ("new-again", [], [1]),
        ("good-then-again", [], [3, 1]),
        ("good-again-good", [], [3, 1, 3]),
        ("mixed", [], [4, 3, 2, 3, 4]),
        ("leech", [{"lapses": 7, "reps": 0, "interval": 1, "ef": 2.5}], [1]),
    ]
    start = date(2026, 1, 1)
    vectors: List[Dict[str, object]] = []
    for name, initial, grades in sequences:
        state = State.from_dict(initial[0]) if initial else State()
        steps = []
        current = date(2026, 1, 1)
        for grade in grades:
            state = review(state, int(grade), current)
            steps.append({"grade": grade, "state": state.to_dict(), "day": current.isoformat()})
            current = current + timedelta(days=1)
        vectors.append({"name": name, "start": State().to_dict() if not initial else initial[0], "steps": steps})
    return vectors

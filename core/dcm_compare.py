"""
Comparison and merge logic for DCM files.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from .dcm_model import DCMFile, DCMParameter, ParameterType


class DiffStatus(Enum):
    IDENTICAL = "identical"
    MODIFIED = "modified"
    ONLY_LEFT = "only_left"
    ONLY_RIGHT = "only_right"


@dataclass
class ParamDiff:
    name: str
    status: DiffStatus
    left: Optional[DCMParameter] = None
    right: Optional[DCMParameter] = None
    # For MODIFIED: list of (row, col, left_val, right_val)
    value_diffs: List[Tuple[int, int, Any, Any]] = field(default_factory=list)

    @property
    def has_value_diffs(self) -> bool:
        return bool(self.value_diffs)

    def summary(self) -> str:
        if self.status == DiffStatus.IDENTICAL:
            return "相同"
        if self.status == DiffStatus.ONLY_LEFT:
            return "仅在左侧"
        if self.status == DiffStatus.ONLY_RIGHT:
            return "仅在右侧"
        n = len(self.value_diffs)
        return f"差异 ({n} 处数值不同)"


@dataclass
class DCMDiff:
    left_path: str
    right_path: str
    diffs: Dict[str, ParamDiff] = field(default_factory=dict)

    @property
    def modified(self) -> List[ParamDiff]:
        return [d for d in self.diffs.values() if d.status == DiffStatus.MODIFIED]

    @property
    def only_left(self) -> List[ParamDiff]:
        return [d for d in self.diffs.values() if d.status == DiffStatus.ONLY_LEFT]

    @property
    def only_right(self) -> List[ParamDiff]:
        return [d for d in self.diffs.values() if d.status == DiffStatus.ONLY_RIGHT]

    @property
    def identical(self) -> List[ParamDiff]:
        return [d for d in self.diffs.values() if d.status == DiffStatus.IDENTICAL]

    def stats(self) -> Dict[str, int]:
        return {
            "total": len(self.diffs),
            "identical": len(self.identical),
            "modified": len(self.modified),
            "only_left": len(self.only_left),
            "only_right": len(self.only_right),
        }


def _values_equal(a: Any, b: Any, tol: float = 1e-10) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tol
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_values_equal(x, y, tol) for x, y in zip(a, b))
    return a == b


def _find_value_diffs(
    left: DCMParameter, right: DCMParameter
) -> List[Tuple[int, int, Any, Any]]:
    diffs = []

    if left.is_scalar:
        if not _values_equal(left.values, right.values):
            diffs.append((0, 0, left.values, right.values))
        return diffs

    if left.is_1d:
        lv = left.values or []
        rv = right.values or []
        for i, (a, b) in enumerate(zip(lv, rv)):
            if not _values_equal(a, b):
                diffs.append((0, i, a, b))
        return diffs

    if left.is_2d:
        lv = left.values or []
        rv = right.values or []
        for r_idx, (lr, rr) in enumerate(zip(lv, rv)):
            for c_idx, (a, b) in enumerate(zip(lr, rr)):
                if not _values_equal(a, b):
                    diffs.append((r_idx, c_idx, a, b))
        return diffs

    return diffs


def compare_dcm(left: DCMFile, right: DCMFile) -> DCMDiff:
    diff = DCMDiff(left_path=left.file_path, right_path=right.file_path)
    all_names = set(left.parameters) | set(right.parameters)

    for name in sorted(all_names):
        lp = left.parameters.get(name)
        rp = right.parameters.get(name)

        if lp is None:
            diff.diffs[name] = ParamDiff(name=name, status=DiffStatus.ONLY_RIGHT, right=rp)
        elif rp is None:
            diff.diffs[name] = ParamDiff(name=name, status=DiffStatus.ONLY_LEFT, left=lp)
        else:
            vd = _find_value_diffs(lp, rp)
            status = DiffStatus.MODIFIED if vd else DiffStatus.IDENTICAL
            diff.diffs[name] = ParamDiff(name=name, status=status, left=lp, right=rp, value_diffs=vd)

    return diff


class MergeStrategy(Enum):
    KEEP_LEFT = "keep_left"
    KEEP_RIGHT = "keep_right"
    KEEP_BOTH = "keep_both"


def merge_dcm(
    left: DCMFile,
    right: DCMFile,
    diff: DCMDiff,
    # Per-parameter override: name -> MergeStrategy
    overrides: Optional[Dict[str, MergeStrategy]] = None,
    default_modified: MergeStrategy = MergeStrategy.KEEP_LEFT,
    include_only_left: bool = True,
    include_only_right: bool = True,
) -> DCMFile:
    """Merge two DCM files according to diff results and strategies."""
    import copy
    if overrides is None:
        overrides = {}

    result = DCMFile(
        version=left.version,
        functions=list(left.functions),
    )

    # Preserve left order, then append right-only
    for name in left.order:
        pdiff = diff.diffs.get(name)
        if pdiff is None:
            result.parameters[name] = copy.deepcopy(left.parameters[name])
            result.order.append(name)
            continue

        strategy = overrides.get(name, default_modified)

        if pdiff.status == DiffStatus.IDENTICAL:
            result.parameters[name] = copy.deepcopy(left.parameters[name])
            result.order.append(name)
        elif pdiff.status == DiffStatus.ONLY_LEFT:
            if include_only_left:
                result.parameters[name] = copy.deepcopy(left.parameters[name])
                result.order.append(name)
        elif pdiff.status == DiffStatus.MODIFIED:
            if strategy == MergeStrategy.KEEP_LEFT:
                result.parameters[name] = copy.deepcopy(left.parameters[name])
            else:
                result.parameters[name] = copy.deepcopy(right.parameters[name])
            result.order.append(name)

    # Add right-only params
    for name in right.order:
        if name in left.parameters:
            continue
        pdiff = diff.diffs.get(name)
        if pdiff and pdiff.status == DiffStatus.ONLY_RIGHT and include_only_right:
            result.parameters[name] = copy.deepcopy(right.parameters[name])
            result.order.append(name)

    return result

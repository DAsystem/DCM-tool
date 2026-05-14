"""
Data models for Vector DCM (KONSERVIERUNG_FORMAT) calibration files.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import copy


class ParameterType(Enum):
    SCALAR = "KENNWERT"
    CURVE = "KENNLINIE"
    FIXED_CURVE = "FESTKENNLINIE"
    MAP = "KENNFELD"
    FIXED_MAP = "FESTKENNFELD"
    GROUP_CURVE = "GRUPPENKENNLINIE"
    GROUP_MAP = "GRUPPENKENNFELD"
    DISTRIBUTION = "STUETZSTELLENVERTEILUNG"
    GROUP_PARAM = "GRUPPENPARAMETER"
    TEXT = "TEXTSTRING"


PARAM_TYPE_LABELS = {
    ParameterType.SCALAR: "标量 (Scalar)",
    ParameterType.CURVE: "一维特性曲线 (1D Curve)",
    ParameterType.FIXED_CURVE: "固定一维曲线 (Fixed 1D)",
    ParameterType.MAP: "二维特性图 (2D Map)",
    ParameterType.FIXED_MAP: "固定二维图 (Fixed 2D Map)",
    ParameterType.GROUP_CURVE: "组一维曲线 (Group 1D)",
    ParameterType.GROUP_MAP: "组二维图 (Group 2D Map)",
    ParameterType.DISTRIBUTION: "分布 (Distribution)",
    ParameterType.GROUP_PARAM: "组参数 (Group Param)",
    ParameterType.TEXT: "文本 (Text)",
}


@dataclass
class DCMFunction:
    name: str
    description: str = ""
    version: str = ""

    def __repr__(self):
        return f"DCMFunction({self.name!r})"


@dataclass
class DCMParameter:
    name: str
    param_type: ParameterType
    long_name: str = ""
    function: str = ""
    display_name: str = ""
    unit_x: str = ""
    unit_y: str = ""
    unit_w: str = ""
    x_values: List[float] = field(default_factory=list)
    y_values: List[float] = field(default_factory=list)
    # scalar: single float; 1D: List[float]; 2D: List[List[float]]
    values: Any = None
    x_dim: int = 0
    y_dim: int = 0
    comment: str = ""
    # raw extra lines we don't fully parse (EINHEIT_X_ALIAS etc.)
    extra_attrs: Dict[str, str] = field(default_factory=dict)

    @property
    def is_scalar(self) -> bool:
        return self.param_type == ParameterType.SCALAR

    @property
    def is_1d(self) -> bool:
        return self.param_type in (
            ParameterType.CURVE,
            ParameterType.FIXED_CURVE,
            ParameterType.GROUP_CURVE,
            ParameterType.DISTRIBUTION,
        )

    @property
    def is_2d(self) -> bool:
        return self.param_type in (
            ParameterType.MAP,
            ParameterType.FIXED_MAP,
            ParameterType.GROUP_MAP,
        )

    @property
    def is_text(self) -> bool:
        return self.param_type in (ParameterType.GROUP_PARAM, ParameterType.TEXT)

    def clone(self) -> DCMParameter:
        return copy.deepcopy(self)

    def get_value_at(self, row: int, col: int = 0) -> Optional[float]:
        if self.is_scalar:
            return self.values
        if self.is_1d and self.values:
            try:
                return self.values[col]
            except IndexError:
                return None
        if self.is_2d and self.values:
            try:
                return self.values[row][col]
            except IndexError:
                return None
        return None

    def set_value_at(self, value: float, row: int, col: int = 0):
        if self.is_scalar:
            self.values = value
        elif self.is_1d and self.values is not None:
            self.values[col] = value
        elif self.is_2d and self.values is not None:
            self.values[row][col] = value

    def __repr__(self):
        return f"DCMParameter({self.name!r}, {self.param_type.value})"


@dataclass
class DCMFile:
    file_path: str = ""
    version: str = "2.0"
    functions: List[DCMFunction] = field(default_factory=list)
    parameters: Dict[str, DCMParameter] = field(default_factory=dict)
    # preserves original order for round-trip writing
    order: List[str] = field(default_factory=list)

    @property
    def scalar_params(self) -> Dict[str, DCMParameter]:
        return {n: p for n, p in self.parameters.items() if p.is_scalar}

    @property
    def curve_params(self) -> Dict[str, DCMParameter]:
        return {n: p for n, p in self.parameters.items() if p.is_1d}

    @property
    def map_params(self) -> Dict[str, DCMParameter]:
        return {n: p for n, p in self.parameters.items() if p.is_2d}

    @property
    def text_params(self) -> Dict[str, DCMParameter]:
        return {n: p for n, p in self.parameters.items() if p.is_text}

    def get_by_type(self, ptype: ParameterType) -> Dict[str, DCMParameter]:
        return {n: p for n, p in self.parameters.items() if p.param_type == ptype}

    def stats(self) -> Dict[str, int]:
        return {
            "total": len(self.parameters),
            "scalar": len(self.scalar_params),
            "curve": len(self.curve_params),
            "map": len(self.map_params),
            "text": len(self.text_params),
            "functions": len(self.functions),
        }

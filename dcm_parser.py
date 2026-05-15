"""
Parser for Vector DCM (KONSERVIERUNG_FORMAT) calibration files.

Handles the text-based format produced by Vector CANape / INCA tools.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import List, Optional, Tuple
from dcm_model import (
    DCMFile, DCMFunction, DCMParameter, ParameterType,
)

# Block keywords that start a parameter definition
PARAM_KEYWORDS = {
    "KENNWERT": ParameterType.SCALAR,
    "KENNLINIE": ParameterType.CURVE,
    "FESTKENNLINIE": ParameterType.FIXED_CURVE,
    "KENNFELD": ParameterType.MAP,
    "FESTKENNFELD": ParameterType.FIXED_MAP,
    "GRUPPENKENNLINIE": ParameterType.GROUP_CURVE,
    "GRUPPENKENNFELD": ParameterType.GROUP_MAP,
    "STUETZSTELLENVERTEILUNG": ParameterType.DISTRIBUTION,
    "GRUPPENPARAMETER": ParameterType.GROUP_PARAM,
    "TEXTSTRING": ParameterType.TEXT,
}


def _parse_floats(tokens: List[str]) -> List[float]:
    result = []
    for t in tokens:
        try:
            result.append(float(t))
        except ValueError:
            pass
    return result


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


class DCMParser:
    def __init__(self):
        self._lines: List[str] = []
        self._pos: int = 0

    def parse_file(self, path: str) -> DCMFile:
        p = Path(path)
        # Try common encodings used in German automotive tools
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                text = p.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = p.read_bytes().decode("latin-1", errors="replace")
        return self.parse_string(text, str(path))

    def parse_string(self, text: str, file_path: str = "") -> DCMFile:
        self._lines = text.splitlines()
        self._pos = 0
        dcm = DCMFile(file_path=file_path)

        while self._pos < len(self._lines):
            line = self._current_line()
            stripped = line.strip()

            if not stripped or stripped.startswith("*"):
                self._advance()
                continue

            tokens = stripped.split()
            keyword = tokens[0].upper()

            if keyword == "KONSERVIERUNG_FORMAT":
                if len(tokens) > 1:
                    dcm.version = tokens[1]
                self._advance()

            elif keyword == "FUNKTIONEN":
                self._advance()
                self._parse_functions(dcm)

            elif keyword in PARAM_KEYWORDS:
                param = self._parse_parameter(tokens, PARAM_KEYWORDS[keyword])
                if param:
                    dcm.parameters[param.name] = param
                    dcm.order.append(param.name)

            else:
                self._advance()

        return dcm

    def _current_line(self) -> str:
        if self._pos < len(self._lines):
            return self._lines[self._pos]
        return ""

    def _advance(self):
        self._pos += 1

    def _parse_functions(self, dcm: DCMFile):
        while self._pos < len(self._lines):
            line = self._current_line().strip()
            if line.upper() == "END":
                self._advance()
                return
            if line.upper().startswith("FKT"):
                parts = line.split(None, 1)
                rest = parts[1] if len(parts) > 1 else ""
                # Extract quoted fields
                quoted = re.findall(r'"([^"]*)"', rest)
                name_match = re.match(r'(\S+)', rest)
                name = name_match.group(1) if name_match else rest.strip()
                desc = quoted[0] if len(quoted) > 0 else ""
                ver = quoted[1] if len(quoted) > 1 else ""
                dcm.functions.append(DCMFunction(name=name, description=desc, version=ver))
            self._advance()

    def _parse_parameter(self, first_tokens: List[str], ptype: ParameterType) -> Optional[DCMParameter]:
        # First line: KEYWORD name [xdim [ydim]]
        name = first_tokens[1] if len(first_tokens) > 1 else ""
        x_dim = int(first_tokens[2]) if len(first_tokens) > 2 else 0
        y_dim = int(first_tokens[3]) if len(first_tokens) > 3 else 0

        param = DCMParameter(name=name, param_type=ptype, x_dim=x_dim, y_dim=y_dim)
        x_vals_buf: List[float] = []
        y_vals_buf: List[float] = []
        w_rows: List[List[float]] = []
        text_lines: List[str] = []

        self._advance()

        while self._pos < len(self._lines):
            line = self._current_line()
            stripped = line.strip()

            if not stripped:
                self._advance()
                continue

            # Line comment (not axis label)
            if stripped.startswith("*") and not stripped.startswith("*SSTX") and not stripped.startswith("*SSTY"):
                self._advance()
                continue

            if stripped.upper() == "END":
                self._advance()
                break

            tokens = stripped.split()
            kw = tokens[0].upper()

            if kw == "LANGNAME":
                param.long_name = _strip_quotes(stripped[len("LANGNAME"):].strip())
            elif kw == "FUNKTION":
                param.function = tokens[1] if len(tokens) > 1 else ""
            elif kw == "DISPLAYNAME":
                param.display_name = _strip_quotes(stripped[len("DISPLAYNAME"):].strip())
            elif kw == "EINHEIT_X":
                param.unit_x = _strip_quotes(stripped[len("EINHEIT_X"):].strip())
            elif kw == "EINHEIT_Y":
                param.unit_y = _strip_quotes(stripped[len("EINHEIT_Y"):].strip())
            elif kw == "EINHEIT_W":
                param.unit_w = _strip_quotes(stripped[len("EINHEIT_W"):].strip())
            elif kw == "VAR":
                # VAR WERT=1.234 or VAR NAME=value
                rest = stripped[len("VAR"):].strip()
                m = re.search(r'WERT\s*=\s*([^\s]+)', rest, re.IGNORECASE)
                if m:
                    try:
                        param.values = float(m.group(1))
                    except ValueError:
                        param.values = m.group(1)
            elif kw in ("ST/X", "STX"):
                x_vals_buf.extend(_parse_floats(tokens[1:]))
            elif kw in ("ST/Y", "STY"):
                y_vals_buf.extend(_parse_floats(tokens[1:]))
            elif kw == "WERT":
                if ptype == ParameterType.SCALAR:
                    # WERT value (alternative form)
                    if len(tokens) > 1:
                        try:
                            param.values = float(tokens[1])
                        except ValueError:
                            param.values = tokens[1]
                elif ptype in (ParameterType.CURVE, ParameterType.FIXED_CURVE,
                                ParameterType.GROUP_CURVE, ParameterType.DISTRIBUTION):
                    w_rows.extend(_parse_floats(tokens[1:]))
                else:
                    # 2D: each WERT line is one row
                    w_rows.append(_parse_floats(tokens[1:]))
            elif kw == "TEXT":
                text_lines.append(_strip_quotes(stripped[len("TEXT"):].strip()))
            elif stripped.startswith("*SSTX") or stripped.startswith("*SSTY"):
                pass  # axis comment labels, skip
            else:
                # Store unknown attributes
                param.extra_attrs[kw] = stripped[len(kw):].strip()

            self._advance()

        # Finalize values
        if x_vals_buf:
            param.x_values = x_vals_buf
        if y_vals_buf:
            param.y_values = y_vals_buf

        if ptype in (ParameterType.CURVE, ParameterType.FIXED_CURVE,
                     ParameterType.GROUP_CURVE, ParameterType.DISTRIBUTION):
            if w_rows:
                param.values = w_rows  # flat list
        elif ptype in (ParameterType.MAP, ParameterType.FIXED_MAP, ParameterType.GROUP_MAP):
            if w_rows:
                param.values = w_rows  # list of rows
        elif ptype in (ParameterType.GROUP_PARAM, ParameterType.TEXT):
            param.values = text_lines

        return param


def parse_dcm(path: str) -> DCMFile:
    return DCMParser().parse_file(path)


def parse_dcm_string(text: str, path: str = "") -> DCMFile:
    return DCMParser().parse_string(text, path)

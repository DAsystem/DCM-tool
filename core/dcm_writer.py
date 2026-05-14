"""
Writer for Vector DCM (KONSERVIERUNG_FORMAT) calibration files.
Produces output compatible with Vector CANape / INCA tools.
"""
from __future__ import annotations
from io import StringIO
from typing import List
from .dcm_model import DCMFile, DCMParameter, DCMFunction, ParameterType


_VALUES_PER_LINE = 6  # wrap long value rows


def _fmt(v) -> str:
    """Format a number for DCM output (no unnecessary trailing zeros)."""
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return f"{int(v)}.0"
        # use up to 10 significant digits, strip trailing zeros
        s = f"{v:.10g}"
        return s
    return str(v)


def _write_values_line(buf: StringIO, keyword: str, values: List[float]):
    """Write a WERT or ST/X row, wrapping at _VALUES_PER_LINE."""
    chunks = [values[i:i + _VALUES_PER_LINE] for i in range(0, len(values), _VALUES_PER_LINE)]
    for i, chunk in enumerate(chunks):
        if i == 0:
            buf.write(f"   {keyword}")
        else:
            buf.write(f"   {keyword}")
        for v in chunk:
            buf.write(f"   {_fmt(v)}")
        buf.write("\n")


class DCMWriter:
    def write(self, dcm: DCMFile) -> str:
        buf = StringIO()
        self._write_header(buf, dcm)
        self._write_functions(buf, dcm)
        for name in dcm.order:
            if name in dcm.parameters:
                self._write_parameter(buf, dcm.parameters[name])
        # Write any params not in order list (shouldn't happen, safety net)
        for name, param in dcm.parameters.items():
            if name not in dcm.order:
                self._write_parameter(buf, param)
        return buf.getvalue()

    def write_file(self, dcm: DCMFile, path: str):
        content = self.write(dcm)
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(content)

    def _write_header(self, buf: StringIO, dcm: DCMFile):
        buf.write(f"KONSERVIERUNG_FORMAT {dcm.version}\n\n")

    def _write_functions(self, buf: StringIO, dcm: DCMFile):
        if not dcm.functions:
            return
        buf.write("FUNKTIONEN\n")
        for fn in dcm.functions:
            desc = f' "{fn.description}"' if fn.description else ' ""'
            ver = f' "{fn.version}"' if fn.version else ' ""'
            buf.write(f"   FKT {fn.name}{desc}{ver}\n")
        buf.write("END\n\n")

    def _write_common_attrs(self, buf: StringIO, param: DCMParameter):
        if param.long_name:
            buf.write(f'   LANGNAME      "{param.long_name}"\n')
        if param.function:
            buf.write(f'   FUNKTION      {param.function}\n')
        if param.display_name:
            buf.write(f'   DISPLAYNAME   "{param.display_name}"\n')

    def _write_parameter(self, buf: StringIO, param: DCMParameter):
        ptype = param.param_type
        kw = ptype.value

        if ptype == ParameterType.SCALAR:
            buf.write(f"{kw} {param.name}\n")
            self._write_common_attrs(buf, param)
            if param.unit_w:
                buf.write(f'   EINHEIT_W     "{param.unit_w}"\n')
            val = param.values if param.values is not None else 0.0
            buf.write(f"   VAR           WERT={_fmt(val)}\n")

        elif ptype in (ParameterType.CURVE, ParameterType.FIXED_CURVE,
                       ParameterType.GROUP_CURVE, ParameterType.DISTRIBUTION):
            size = len(param.x_values) or param.x_dim
            buf.write(f"{kw} {param.name} {size}\n")
            self._write_common_attrs(buf, param)
            if param.unit_x:
                buf.write(f'   EINHEIT_X     "{param.unit_x}"\n')
            if param.unit_w:
                buf.write(f'   EINHEIT_W     "{param.unit_w}"\n')
            if param.x_values:
                _write_values_line(buf, "ST/X", param.x_values)
            if param.values:
                _write_values_line(buf, "WERT", param.values)

        elif ptype in (ParameterType.MAP, ParameterType.FIXED_MAP, ParameterType.GROUP_MAP):
            xsz = len(param.x_values) or param.x_dim
            ysz = len(param.y_values) or param.y_dim
            buf.write(f"{kw} {param.name} {xsz} {ysz}\n")
            self._write_common_attrs(buf, param)
            if param.unit_x:
                buf.write(f'   EINHEIT_X     "{param.unit_x}"\n')
            if param.unit_y:
                buf.write(f'   EINHEIT_Y     "{param.unit_y}"\n')
            if param.unit_w:
                buf.write(f'   EINHEIT_W     "{param.unit_w}"\n')
            if param.x_values:
                _write_values_line(buf, "ST/X", param.x_values)
            if param.y_values:
                _write_values_line(buf, "ST/Y", param.y_values)
            if param.values:
                for row in param.values:
                    _write_values_line(buf, "WERT", row)

        elif ptype in (ParameterType.GROUP_PARAM, ParameterType.TEXT):
            buf.write(f"{kw} {param.name}\n")
            self._write_common_attrs(buf, param)
            if isinstance(param.values, list):
                for line in param.values:
                    buf.write(f'   TEXT          "{line}"\n')
            elif param.values:
                buf.write(f'   TEXT          "{param.values}"\n')

        else:
            # Generic fallback
            buf.write(f"{kw} {param.name}\n")
            self._write_common_attrs(buf, param)

        buf.write("END\n\n")


def write_dcm(dcm: DCMFile, path: str):
    DCMWriter().write_file(dcm, path)


def dcm_to_string(dcm: DCMFile) -> str:
    return DCMWriter().write(dcm)

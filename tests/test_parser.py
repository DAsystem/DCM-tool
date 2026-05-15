"""Tests for DCM parser, writer, and compare logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from dcm_parser import parse_dcm, parse_dcm_string
from dcm_writer import dcm_to_string, DCMWriter
from dcm_compare import compare_dcm, DiffStatus, merge_dcm, MergeStrategy
from dcm_model import ParameterType


SAMPLE_DCM = """KONSERVIERUNG_FORMAT 2.0

FUNKTIONEN
   FKT TEST_FUNC "Test Function" "V1.0"
END

KENNWERT MyScalar
   LANGNAME      "A test scalar"
   FUNKTION      TEST_FUNC
   EINHEIT_W     "rpm"
   VAR           WERT=1234.5
END

KENNLINIE MyCurve 5
   LANGNAME      "A 1D curve"
   FUNKTION      TEST_FUNC
   EINHEIT_X     "degC"
   EINHEIT_W     "%"
   ST/X          0.0   25.0   50.0   75.0   100.0
   WERT          1.0    2.0    3.0    4.0     5.0
END

KENNFELD MyMap 3 2
   LANGNAME      "A 2D map"
   FUNKTION      TEST_FUNC
   EINHEIT_X     "rpm"
   EINHEIT_Y     "load"
   EINHEIT_W     "ms"
   ST/X          1000.0   2000.0   3000.0
   ST/Y          0.5   1.0
   WERT          1.1   2.2   3.3
   WERT          4.4   5.5   6.6
END

GRUPPENPARAMETER MyText
   LANGNAME      "Text param"
   FUNKTION      TEST_FUNC
   TEXT          "Line 1"
   TEXT          "Line 2"
END
"""


class TestParser(unittest.TestCase):
    def setUp(self):
        self.dcm = parse_dcm_string(SAMPLE_DCM)

    def test_version(self):
        self.assertEqual(self.dcm.version, "2.0")

    def test_functions(self):
        self.assertEqual(len(self.dcm.functions), 1)
        fn = self.dcm.functions[0]
        self.assertEqual(fn.name, "TEST_FUNC")
        self.assertEqual(fn.description, "Test Function")
        self.assertEqual(fn.version, "V1.0")

    def test_scalar_parsed(self):
        self.assertIn("MyScalar", self.dcm.parameters)
        p = self.dcm.parameters["MyScalar"]
        self.assertEqual(p.param_type, ParameterType.SCALAR)
        self.assertAlmostEqual(p.values, 1234.5)
        self.assertEqual(p.unit_w, "rpm")
        self.assertEqual(p.long_name, "A test scalar")

    def test_curve_parsed(self):
        self.assertIn("MyCurve", self.dcm.parameters)
        p = self.dcm.parameters["MyCurve"]
        self.assertEqual(p.param_type, ParameterType.CURVE)
        self.assertEqual(len(p.x_values), 5)
        self.assertEqual(len(p.values), 5)
        self.assertAlmostEqual(p.x_values[2], 50.0)
        self.assertAlmostEqual(p.values[4], 5.0)

    def test_map_parsed(self):
        self.assertIn("MyMap", self.dcm.parameters)
        p = self.dcm.parameters["MyMap"]
        self.assertEqual(p.param_type, ParameterType.MAP)
        self.assertEqual(len(p.x_values), 3)
        self.assertEqual(len(p.y_values), 2)
        self.assertEqual(len(p.values), 2)
        self.assertEqual(len(p.values[0]), 3)
        self.assertAlmostEqual(p.values[1][2], 6.6)

    def test_text_parsed(self):
        self.assertIn("MyText", self.dcm.parameters)
        p = self.dcm.parameters["MyText"]
        self.assertEqual(p.param_type, ParameterType.GROUP_PARAM)
        self.assertEqual(p.values, ["Line 1", "Line 2"])

    def test_order_preserved(self):
        self.assertEqual(self.dcm.order, ["MyScalar", "MyCurve", "MyMap", "MyText"])

    def test_stats(self):
        s = self.dcm.stats()
        self.assertEqual(s["scalar"], 1)
        self.assertEqual(s["curve"], 1)
        self.assertEqual(s["map"], 1)
        self.assertEqual(s["total"], 4)


class TestWriter(unittest.TestCase):
    def test_roundtrip_scalar(self):
        dcm = parse_dcm_string(SAMPLE_DCM)
        text = dcm_to_string(dcm)
        dcm2 = parse_dcm_string(text)
        p1 = dcm.parameters["MyScalar"]
        p2 = dcm2.parameters["MyScalar"]
        self.assertAlmostEqual(p1.values, p2.values)

    def test_roundtrip_curve(self):
        dcm = parse_dcm_string(SAMPLE_DCM)
        text = dcm_to_string(dcm)
        dcm2 = parse_dcm_string(text)
        p1 = dcm.parameters["MyCurve"]
        p2 = dcm2.parameters["MyCurve"]
        for a, b in zip(p1.values, p2.values):
            self.assertAlmostEqual(a, b)

    def test_roundtrip_map(self):
        dcm = parse_dcm_string(SAMPLE_DCM)
        text = dcm_to_string(dcm)
        dcm2 = parse_dcm_string(text)
        p1 = dcm.parameters["MyMap"]
        p2 = dcm2.parameters["MyMap"]
        for r1, r2 in zip(p1.values, p2.values):
            for a, b in zip(r1, r2):
                self.assertAlmostEqual(a, b)

    def test_format_header(self):
        dcm = parse_dcm_string(SAMPLE_DCM)
        text = dcm_to_string(dcm)
        self.assertTrue(text.startswith("KONSERVIERUNG_FORMAT 2.0"))

    def test_all_params_in_output(self):
        dcm = parse_dcm_string(SAMPLE_DCM)
        text = dcm_to_string(dcm)
        for name in dcm.parameters:
            self.assertIn(name, text)


SAMPLE_A = """KONSERVIERUNG_FORMAT 2.0
KENNWERT Param1
   VAR WERT=10.0
END
KENNWERT Param2
   VAR WERT=20.0
END
KENNWERT OnlyInA
   VAR WERT=99.0
END
"""

SAMPLE_B = """KONSERVIERUNG_FORMAT 2.0
KENNWERT Param1
   VAR WERT=10.0
END
KENNWERT Param2
   VAR WERT=25.0
END
KENNWERT OnlyInB
   VAR WERT=77.0
END
"""


class TestCompare(unittest.TestCase):
    def setUp(self):
        self.a = parse_dcm_string(SAMPLE_A, "file_a.dcm")
        self.b = parse_dcm_string(SAMPLE_B, "file_b.dcm")
        self.diff = compare_dcm(self.a, self.b)

    def test_identical_detected(self):
        d = self.diff.diffs["Param1"]
        self.assertEqual(d.status, DiffStatus.IDENTICAL)

    def test_modified_detected(self):
        d = self.diff.diffs["Param2"]
        self.assertEqual(d.status, DiffStatus.MODIFIED)
        self.assertEqual(len(d.value_diffs), 1)
        row, col, lv, rv = d.value_diffs[0]
        self.assertAlmostEqual(lv, 20.0)
        self.assertAlmostEqual(rv, 25.0)

    def test_only_left_detected(self):
        d = self.diff.diffs["OnlyInA"]
        self.assertEqual(d.status, DiffStatus.ONLY_LEFT)

    def test_only_right_detected(self):
        d = self.diff.diffs["OnlyInB"]
        self.assertEqual(d.status, DiffStatus.ONLY_RIGHT)

    def test_stats(self):
        s = self.diff.stats()
        self.assertEqual(s["identical"], 1)
        self.assertEqual(s["modified"], 1)
        self.assertEqual(s["only_left"], 1)
        self.assertEqual(s["only_right"], 1)
        self.assertEqual(s["total"], 4)


class TestMerge(unittest.TestCase):
    def setUp(self):
        self.a = parse_dcm_string(SAMPLE_A, "file_a.dcm")
        self.b = parse_dcm_string(SAMPLE_B, "file_b.dcm")
        self.diff = compare_dcm(self.a, self.b)

    def test_merge_keep_left(self):
        result = merge_dcm(self.a, self.b, self.diff,
                           default_modified=MergeStrategy.KEEP_LEFT,
                           include_only_left=True, include_only_right=True)
        self.assertAlmostEqual(result.parameters["Param2"].values, 20.0)
        self.assertIn("OnlyInA", result.parameters)
        self.assertIn("OnlyInB", result.parameters)

    def test_merge_keep_right(self):
        result = merge_dcm(self.a, self.b, self.diff,
                           default_modified=MergeStrategy.KEEP_RIGHT,
                           include_only_left=True, include_only_right=True)
        self.assertAlmostEqual(result.parameters["Param2"].values, 25.0)

    def test_merge_exclude_only_right(self):
        result = merge_dcm(self.a, self.b, self.diff,
                           include_only_left=True, include_only_right=False)
        self.assertNotIn("OnlyInB", result.parameters)
        self.assertIn("OnlyInA", result.parameters)

    def test_per_param_override(self):
        result = merge_dcm(
            self.a, self.b, self.diff,
            overrides={"Param2": MergeStrategy.KEEP_RIGHT},
            default_modified=MergeStrategy.KEEP_LEFT,
            include_only_left=True, include_only_right=True,
        )
        self.assertAlmostEqual(result.parameters["Param2"].values, 25.0)


class TestSampleFile(unittest.TestCase):
    def _sample_path(self, name):
        base = os.path.join(os.path.dirname(__file__), "..", "resources", name)
        return os.path.abspath(base)

    def test_parse_sample_v1(self):
        dcm = parse_dcm(self._sample_path("sample_engine.dcm"))
        self.assertEqual(dcm.version, "2.0")
        self.assertIn("IdleSpeed_rpm", dcm.parameters)
        self.assertIn("FuelInjMap_mg", dcm.parameters)
        self.assertEqual(dcm.parameters["FuelInjMap_mg"].param_type, ParameterType.MAP)

    def test_parse_sample_v2(self):
        dcm = parse_dcm(self._sample_path("sample_engine_v2.dcm"))
        self.assertIn("KnockRetardLimit_deg", dcm.parameters)

    def test_compare_samples(self):
        v1 = parse_dcm(self._sample_path("sample_engine.dcm"))
        v2 = parse_dcm(self._sample_path("sample_engine_v2.dcm"))
        diff = compare_dcm(v1, v2)
        self.assertGreater(diff.stats()["modified"], 0)
        self.assertGreater(diff.stats()["only_right"], 0)

    def test_roundtrip_sample(self):
        path = self._sample_path("sample_engine.dcm")
        dcm = parse_dcm(path)
        text = dcm_to_string(dcm)
        dcm2 = parse_dcm_string(text)
        self.assertEqual(set(dcm.parameters.keys()), set(dcm2.parameters.keys()))


if __name__ == "__main__":
    unittest.main(verbosity=2)

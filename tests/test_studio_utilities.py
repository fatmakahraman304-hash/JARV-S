import unittest
from decimal import Decimal
from core import studio_utilities as u
from plugins import studio_utilities as plugin


class UtilityTests(unittest.TestCase):
    def test_convert_and_portions(self):
        self.assertEqual(u.convert(2,"km","m"),"2000")
        self.assertEqual(u.convert(32,"f","c"),"0")
        self.assertEqual(u.portions([{"name":"Un","amount":150,"unit":"g"}],2,5)[0]["amount"],"375")
        with self.assertRaises(ValueError):
            u.convert(2,"kg","m")
        with self.assertRaises(ValueError):
            u.portions([{"amount":1}],0,2)

    def test_cost_and_totals(self):
        result = u.split_cost("10.00",[1,1,1])
        self.assertEqual(result, ["3.34","3.33","3.33"])
        self.assertEqual(sum(map(Decimal,result)),Decimal("10"))
        self.assertTrue(u.check_total(["0.1","0.2"],"0.3")["matches"])
        self.assertIsNone(u.compare(0,4)["percentage_change"])

    def test_stats(self):
        r = u.stats([1,2,3,4,100])
        self.assertEqual(r["median"],3)
        self.assertEqual(r["outlier_indices_zero_based"],[4])
        with self.assertRaises(ValueError):
            u.stats(["NaN"])

    def test_conflicts_and_diff(self):
        a = {"start":"2026-01-01T10:00:00+03:00","end":"2026-01-01T11:00:00+03:00"}
        b = {"start":"2026-01-01T07:30:00+00:00","end":"2026-01-01T08:30:00+00:00"}
        c = {"start":"2026-01-01T11:00:00+03:00","end":"2026-01-01T12:00:00+03:00"}
        self.assertEqual(u.conflicts([a,b,c]),[[0,1],[1,2]])
        self.assertIn("+b",u.text_diff("a","b")["diff"])
        self.assertTrue(u.text_diff("a","a")["identical"])

    def test_dice_formula_and_plugin(self):
        rolls = u.dice(10,6)["rolls"]
        self.assertEqual(len(rolls),10)
        self.assertTrue(all(1 <= x <= 6 for x in rolls))
        self.assertEqual(u.formula("SUM","a",1,10),"=SUM(A1:A10)")
        self.assertIn("status=failed",plugin.run({"operation":"unknown","arguments":"{}"}))
        self.assertIn("status=done",plugin.run({"operation":"convert","arguments":'{"value":2,"source":"m","target":"cm"}'}))

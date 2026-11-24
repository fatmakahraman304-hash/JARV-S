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

    def test_templates_are_explicit_drafts(self):
        from core.studio_templates import FIELDS, draft
        self.assertEqual(len(FIELDS),16)
        for n in FIELDS:
            item = draft(n)
            self.assertEqual(item["tags"], f"mod-{n}")
            self.assertTrue(item["body"])
        self.assertIn("Malzemeler",draft(590)["body"])

    def test_project_schedule_budget_and_weighted_options(self):
        from core import studio_utilities as u
        result = u.task_schedule([{"id":"C","minutes":10,"depends":["A","B"]},
                                  {"id":"A","minutes":20},{"id":"B","minutes":15}])
        self.assertEqual(result["minimum_elapsed_minutes"],"30")
        self.assertEqual(result["total_work_minutes"],"45")
        with self.assertRaises(ValueError):
            u.task_schedule([{"id":"A","minutes":1,"depends":["B"]},
                             {"id":"B","minutes":1,"depends":["A"]}])
        with self.assertRaises(ValueError):
            u.task_schedule([{"id":"A","minutes":1,"depends":["missing"]}])
        budget = u.budget_summary("100.00",[{"category":"Ev","amount":"20.10"},
                                          {"category":"Ev","amount":"0.20"}])
        self.assertEqual(budget["remaining"],"79.7")
        self.assertEqual(budget["by_category"],{"Ev":"20.3"})
        ranked = u.weighted_options({"Fiyat":2,"Kalite":1},
            [{"name":"A","ratings":{"Fiyat":9,"Kalite":3}},
             {"name":"B","ratings":{"Fiyat":6,"Kalite":6}}])
        self.assertEqual(ranked["ranking"],[{"name":"A","score":"7"},{"name":"B","score":"6"}])
        with self.assertRaises(ValueError):
            u.weighted_options({"Fiyat":1},[{"name":"A","ratings":{"Fiyat":11}}])

    def test_data_quality_and_trend(self):
        quality=u.data_quality([{"A":1,"B":None},{"A":"x","B":False},{"B":" "}])
        self.assertEqual(quality["row_count"],3)
        self.assertEqual(quality["columns"][0],{"column":"A","missing":1,"present":2,
            "types":{"number":1,"text":1},"mixed_types":True})
        self.assertEqual(quality["columns"][1]["missing"],2)
        self.assertEqual(quality["columns"][1]["types"],{"boolean":1})
        with self.assertRaises(ValueError):
            u.data_quality([{"A":[1]}])
        with self.assertRaises(ValueError):
            u.data_quality([{"A":float("inf")}])
        result=u.trend([2,4,6,8])
        self.assertAlmostEqual(result["slope_per_step"],2)
        self.assertAlmostEqual(result["intercept_at_step_zero"],2)
        self.assertAlmostEqual(result["r_squared"],1)
        self.assertIsNone(u.trend([2,2,2])["r_squared"])
        with self.assertRaises(ValueError):
            u.trend([1])

    def test_exact_allocation_and_excel_boundary(self):
        amount="999999999999.99"
        shares=u.split_cost(amount,["0.000000000001","999999999999","999999999998"])
        self.assertEqual(sum(map(Decimal,shares)),Decimal(amount))
        self.assertEqual(u.formula("SUM","XFD",1,1048576),"=SUM(XFD1:XFD1048576)")
        with self.assertRaises(ValueError):
            u.formula("SUM","XFE",1,2)
        with self.assertRaises(ValueError):
            u.number("0"*101)

    def test_critical_path_and_slack(self):
        result=u.task_schedule([{"id":"A","minutes":4},{"id":"B","minutes":2},
             {"id":"C","minutes":3,"depends":["A","B"]},{"id":"D","minutes":1}])
        self.assertEqual(result["critical_path"],["A","C"])
        self.assertEqual(result["critical_tasks"],["A","C"])
        self.assertEqual(result["minimum_elapsed_minutes"],"7")
        self.assertEqual({t["id"]:t["slack_minutes"] for t in result["tasks"]},
                         {"A":"0","B":"2","C":"0","D":"6"})
        tied=u.task_schedule([{"id":"A","minutes":2},{"id":"B","minutes":2},
                              {"id":"C","minutes":1,"depends":["A","B"]}])
        self.assertEqual(set(tied["critical_tasks"]),{"A","B","C"})
        self.assertEqual(tied["critical_path"],["A","C"])

    def test_priority_matrix(self):
        result=u.priority_matrix([{"name":"A","important":True,"urgent":True},
            {"name":"B","important":True,"urgent":False},
            {"name":"C","important":False,"urgent":True},
            {"name":"D","important":False,"urgent":False}])
        self.assertEqual(result["groups"],{"do_first":["A"],"schedule":["B"],
            "delegate_or_review":["C"],"defer_or_review":["D"]})
        with self.assertRaises(ValueError):
            u.priority_matrix([{"name":"A","important":"true","urgent":True}])
        with self.assertRaises(ValueError):
            u.priority_matrix([{"name":"A","important":True,"urgent":False}]*2)

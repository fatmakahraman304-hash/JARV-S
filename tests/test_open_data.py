import unittest
from unittest import mock

from core import open_data


class WeatherTest(unittest.TestCase):
    def test_city_forecast_in_turkish(self):
        def fake(url, timeout=12):
            if "geocoding" in url:
                return {"results": [{"latitude": 35.18, "longitude": 33.36, "name": "Lefkoşa", "country": "Kıbrıs"}]}
            return {"current": {"temperature_2m": 23.4, "apparent_temperature": 24.1, "weather_code": 2, "wind_speed_10m": 11},
                    "daily": {"time": ["2026-11-18", "2026-11-19", "2026-11-20"], "temperature_2m_min": [14, 13, 12],
                              "temperature_2m_max": [24, 22, 20], "weather_code": [2, 61, 0],
                              "precipitation_probability_max": [5, 70, 0]}}
        with mock.patch.object(open_data, "_get", side_effect=fake):
            out = open_data.weather("Lefkoşa")
        self.assertIn("Lefkoşa, Kıbrıs: şu an 23°C, parçalı bulutlu", out)
        self.assertIn("Yarın: 13–22°C, hafif yağmurlu, yağış ihtimali %70", out)
        self.assertIn("Cuma", out)                      # 2026-11-20

    def test_unknown_place_and_failure(self):
        with mock.patch.object(open_data, "_get", return_value={"results": []}):
            self.assertIn("bulamadım", open_data.weather("Xyzabad"))
        with mock.patch.object(open_data, "_get", side_effect=OSError("ağ yok")):
            self.assertIn("alınamadı", open_data.weather("Lefkoşa"))

    def test_desktop_tool_says_real_numbers(self):
        from actions import weather_report
        with mock.patch("core.open_data.weather", return_value="Lefkoşa: şu an 23°C") as w:
            out = weather_report.weather_action({"city": "Lefkoşa", "time": "bu hafta"})
        self.assertEqual(out, "Lefkoşa: şu an 23°C")
        self.assertEqual(w.call_args.kwargs["days"], 7)


class CurrencyTest(unittest.TestCase):
    def test_turkish_words_and_format(self):
        seen = {}

        def fake(url, timeout=12):
            seen["url"] = url
            return {"amount": 100.0, "base": "EUR", "date": "2026-11-18", "rates": {"TRY": 4875.5}}
        with mock.patch.object(open_data, "_get", side_effect=fake):
            out = open_data.currency("euro", "lira", 100)
        self.assertIn("base=EUR", seen["url"])
        self.assertIn("symbols=TRY", seen["url"])
        self.assertIn("100 EUR = 4.875,50 TRY", out)

    def test_plugin(self):
        from plugins import currency
        with mock.patch("core.open_data.currency", return_value="1 USD = 42,00 TRY") as c:
            self.assertEqual(currency.run({"base": "dolar"}), "1 USD = 42,00 TRY")
        self.assertEqual(c.call_args[0][:2], ("dolar", "TRY"))


if __name__ == "__main__":
    unittest.main()

import asyncio
import copy
from pathlib import Path
import time
import unittest

from app.adaptive.config import AdaptiveConfigStore
from app.adaptive.context import ContextHub
from app.adaptive.policy import PolicyEngine
from app.adaptive.schemas import InputSample


CONFIG_DIR = Path(__file__).resolve().parents[1] / "app" / "config"


class AdaptiveContextPolicyTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = AdaptiveConfigStore(CONFIG_DIR)
        self.inputs = self.store.get("inputs")

    def test_rejects_duplicate_and_out_of_order_samples(self):
        hub = ContextHub(self.inputs)
        self.assertTrue(hub.ingest(InputSample(source_id="bci.primary", kind="bci", sequence=2, values={})))
        self.assertFalse(hub.ingest(InputSample(source_id="bci.primary", kind="bci", sequence=2, values={})))
        self.assertFalse(hub.ingest(InputSample(source_id="bci.primary", kind="bci", sequence=1, values={})))

    def test_bci_holds_then_returns_smoothly_to_neutral(self):
        hub = ContextHub(self.inputs)
        timestamp = time.time() - 7.0
        hub.ingest(InputSample(
            source_id="bci.primary", kind="bci", timestamp=timestamp, sequence=1, quality=1.0,
            values={"valence": 1.0, "arousal": 0.0, "confidence": 1.0},
        ))
        frame = hub.frame(now=timestamp + 7.0)
        self.assertTrue(frame.degraded)
        self.assertAlmostEqual(frame.valence, 0.9, places=2)
        self.assertAlmostEqual(frame.arousal, 0.1, places=2)
        neutral = hub.frame(now=timestamp + 16.0)
        self.assertAlmostEqual(neutral.valence, 0.5, places=3)
        self.assertAlmostEqual(neutral.arousal, 0.5, places=3)
        self.assertEqual(neutral.bci_confidence, 0.0)

    def test_auxiliary_inputs_modulate_but_do_not_replace_bci_valence(self):
        hub = ContextHub(self.inputs)
        now = time.time()
        hub.ingest(InputSample(
            source_id="bci.primary", kind="bci", timestamp=now, sequence=1, quality=0.95,
            values={"valence": 0.2, "arousal": 0.25, "confidence": 0.95},
        ))
        hub.ingest(InputSample(source_id="sensor.heart", kind="heart_rate", timestamp=now, sequence=1, values={"bpm": 160}))
        hub.ingest(InputSample(source_id="sensor.motion", kind="motion", timestamp=now, sequence=1, values={"intensity": 1.0, "cadence": 160}))
        intent = PolicyEngine(self.store.get("policy")).resolve(hub.frame(now=now + 0.01))
        self.assertAlmostEqual(intent.valence, 0.2)
        self.assertGreater(intent.energy, 0.25)
        self.assertLess(intent.energy, 0.6)

    async def test_weather_opens_circuit_after_three_fast_failures(self):
        config = copy.deepcopy(self.inputs)
        config["weather"].update({"enabled": True, "latitude": 31.2, "longitude": 121.5})
        hub = ContextHub(config)

        def fail(_config):
            raise OSError("offline")

        hub._fetch_weather = fail
        for _ in range(3):
            await hub._refresh_weather()
        self.assertEqual(hub.weather_failures, 3)
        self.assertGreater(hub.weather_circuit_until, time.time())
        await hub._refresh_weather()
        status = hub.statuses["weather.open_meteo"]
        self.assertEqual(status.health, "circuit_open")


if __name__ == "__main__":
    unittest.main()

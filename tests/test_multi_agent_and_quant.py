import unittest
from data.market_news import fetch_forexfactory_news
from engine.multi_agent_consensus import MultiAgentConsensusEngine
from engine.quant_dinge_engine import QuantDingerEngine


class TestMultiAgentAndQuantEngine(unittest.TestCase):

    def test_forexfactory_news_fetcher(self):
        ff_news = fetch_forexfactory_news()
        self.assertTrue(isinstance(ff_news, list))
        self.assertGreater(len(ff_news), 0)
        self.assertEqual(ff_news[0].get('priority'), 1)
        self.assertTrue(ff_news[0].get('source', '').startswith('ForexFactory'))

    def test_multi_agent_consensus_engine(self):
        engine = MultiAgentConsensusEngine()
        res = engine.evaluate(
            spot_close=24000.0,
            pred_open=24100.0,
            atr=200.0,
            news_items=[{'title': 'Test Growth Event', 'source': 'ForexFactory (Priority #1)'}],
            sentiment_data={'score': 0.3, 'intensity': 'bullish', 'bullish_count': 3, 'bearish_count': 1},
            us_summary={'VIX': {'price': 15.0}},
            option_chain={'pcr': 1.15}
        )
        self.assertIn('verdict', res)
        self.assertIn('overall_confidence', res)
        self.assertIn('agents', res)
        self.assertIn('fundamental', res['agents'])

    def test_quant_dinge_engine(self):
        engine = QuantDingerEngine()
        setup = engine.generate_strategy_setup(
            index_name="NIFTY 50",
            spot_close=24000.0,
            pred_open=24120.0,
            pred_high=24250.0,
            pred_low=23950.0,
            pred_close=24180.0,
            atr=200.0,
            vix=15.0,
            sentiment_score=0.4,
            consensus_score=0.35,
            option_chain={'pcr': 1.2}
        )
        self.assertEqual(setup['index'], "NIFTY 50")
        self.assertIn('regime', setup)
        self.assertIn('action', setup)
        self.assertGreater(setup['entry_price'], 0)
        self.assertGreater(setup['stop_loss'], 0)


if __name__ == '__main__':
    unittest.main()

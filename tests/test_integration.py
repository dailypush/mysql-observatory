"""Live MySQL integration checks. Run inside the app container."""
import copy
import sys
import unittest
sys.path.insert(0, '/app')
from server import app


class LiveDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

    def test_health_and_assets(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['version'].startswith('9.7.'))
        self.assertEqual(response.json['orders'], 30000)
        for path in ['/', '/app.js', '/styles.css']:
            with self.client.get(path) as asset:
                self.assertEqual(asset.status_code, 200, path)

    def test_document_roundtrip_both_modes_and_stale_write(self):
        original = self.client.get('/api/customers/1').json['data']['document']
        try:
            for mode in ['modern', 'classic']:
                url = '/api/customers/1?mode=' + mode
                loaded = self.client.get(url).json['data']
                updated = copy.deepcopy(loaded['document'])
                updated['city'] = 'Seattle' if mode == 'modern' else 'Austin'
                payload = {'document': updated, 'version': loaded['version']}
                saved = self.client.put(url, json=payload)
                self.assertEqual(saved.status_code, 200, saved.json)
                self.assertEqual(saved.json['data']['row']['city'], updated['city'])
                self.assertEqual(saved.json['data']['document']['city'], updated['city'])
                self.assertEqual(self.client.put(url, json=payload).status_code, 409)
                fresh = self.client.get('/api/customers/1').json['data']['document']
                self.assertEqual(fresh['city'], updated['city'])
        finally:
            current = self.client.get('/api/customers/1').json['data']
            restored = self.client.put('/api/customers/1', json={'document': original, 'version': current['version']})
            self.assertEqual(restored.status_code, 200, restored.json)

    def test_document_validation_and_missing_records(self):
        loaded = self.client.get('/api/customers/1').json['data']
        for change in [{'tier':'Admin'}, {'email':'invalid'}, {'_id':2}, {'name':''}, {'city':['bad']}, {'extra':'bad'}]:
            doc = {**loaded['document'], **change}
            response = self.client.put('/api/customers/1', json={'document':doc,'version':loaded['version']})
            self.assertEqual(response.status_code, 400, change)
        self.assertEqual(self.client.get('/api/customers/999999').status_code,404)
        self.assertEqual(self.client.put('/api/customers/1',json=[]).status_code,400)
        self.assertEqual(self.client.get('/api/customers/1?mode=bad').status_code,400)

    def test_native_vectors_and_keyword_comparison(self):
        query = 'weekend outdoor adventure'
        classic = self.client.get('/api/search',query_string={'q':query,'mode':'classic'}).json['data']
        modern = self.client.get('/api/search',query_string={'q':query,'mode':'modern'}).json['data']
        self.assertEqual(len(classic['products']),0)
        self.assertEqual(len(modern['products']),6)
        self.assertEqual(modern['products'][0]['category'],'Outdoors')
        self.assertEqual(modern['products'][0]['dimensions'],6)
        scores=[r['score'] for r in modern['products']]
        self.assertEqual(scores,sorted(scores,reverse=True))
        unknown=self.client.get('/api/search?q=zzzzzzz').json['data']
        self.assertEqual(unknown['products'],[])
        self.assertEqual(self.client.get('/api/search?q=%25&mode=classic').json['data']['products'],[])
        self.assertEqual(self.client.get('/api/search?q=').status_code,400)
        self.assertEqual(self.client.get('/api/search?q=x&mode=bad').status_code,400)

    def test_optimizer_correctness_and_real_plans(self):
        result=self.client.post('/api/benchmark',json={'city':'Portland','status':'Delivered'})
        self.assertEqual(result.status_code,200,result.json)
        data=result.json['data']
        self.assertTrue(data['same_results'])
        self.assertEqual(len(data['classic']['rows']),12)
        for mode in ['classic','hypergraph']:
            self.assertGreater(data[mode]['median_ms'],0)
            self.assertEqual(len(data[mode]['samples_ms']),5)
            self.assertIn('actual time=',data[mode]['plan'])
        self.assertNotEqual(data['classic']['plan'],data['hypergraph']['plan'])
        self.assertEqual(self.client.post('/api/benchmark',json={'city':"' OR 1=1"}).status_code,400)

if __name__=='__main__':
    unittest.main(verbosity=2)

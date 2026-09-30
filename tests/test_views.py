"""View metadata, insert persistence, and atomicity against live MySQL."""
import copy
import random
import sys
import unittest
sys.path.insert(0, '/app')
from server import app
from database import connect


class ViewStudioTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        # Reserve an isolated test range probabilistically, then confirm no row exists.
        while True:
            self.base = random.SystemRandom().randrange(1_000_000_000, 2_000_000_000)
            self.ids = list(range(self.base, self.base + 10))
            with connect() as db, db.cursor() as cur:
                cur.execute('SELECT id FROM customers WHERE id BETWEEN %s AND %s UNION ALL SELECT id FROM customer_addresses WHERE id BETWEEN %s AND %s', (self.ids[0],self.ids[-1],self.ids[0],self.ids[-1]))
                if not cur.fetchall():
                    break

    def tearDown(self):
        with connect() as db, db.cursor() as cur:
            cur.execute('DELETE FROM customer_addresses WHERE id BETWEEN %s AND %s', (self.ids[0], self.ids[-1]))
            cur.execute('DELETE FROM customers WHERE id BETWEEN %s AND %s', (self.ids[0], self.ids[-1]))
            db.commit()

    def profile(self, offset=0):
        return {'_id':self.base+offset, 'name':'Test Customer', 'email':'test@example.com',
                'city':'Seattle','tier':'Explorer', 'addresses':[
                    {'id':self.base+offset,'label':'Home','street':'42 Test Lane','city':'Seattle','country':'United States'}]}

    def post(self, name, record):
        return self.client.post('/api/views/'+name+'/rows', json={'record':record})

    def test_catalog_and_live_definitions(self):
        self.assertEqual(len(self.client.get('/api/views').json['data']), 3)
        for name in ['customer_directory','customer_profiles','customer_summary']:
            res = self.client.get('/api/views/'+name)
            self.assertEqual(res.status_code,200,res.json)
            self.assertIn(name,res.json['data']['definition'])
            self.assertTrue(res.json['data']['columns'])
        self.assertEqual([col['name'] for col in self.client.get('/api/views/customer_directory').json['data']['columns']], ['id','name','email','city','tier'])
        summary=self.client.get('/api/views/customer_summary').json['data']
        self.assertFalse(summary['insertable'])
        self.assertIsNone(summary['template'])
        self.assertEqual(self.client.get('/api/views/customers').status_code,404)
        self.assertEqual(self.client.get('/api/views/x%60%3BSELECT%201').status_code,404)

    def test_sql_view_insert(self):
        profile=self.profile(); profile['id']=profile.pop('_id'); profile.pop('addresses')
        result=self.post('customer_directory',profile)
        self.assertEqual(result.status_code,201,result.json)
        self.assertEqual(result.json['data']['base_tables']['customers'][0],profile)
        self.assertTrue(result.json['trace'][0]['sql'].startswith('INSERT INTO customer_directory'))
        self.assertEqual(self.post('customer_directory',profile).status_code,409)
        with connect() as db, db.cursor() as cur:
            cur.execute('SELECT name FROM customers WHERE id=%s',(self.base,))
            self.assertEqual(cur.fetchone()['name'],'Test Customer')

    def test_nested_insert_and_child_conflict_rolls_back(self):
        original=self.profile()
        created=self.post('customer_profiles',original)
        self.assertEqual(created.status_code,201,created.json)
        self.assertEqual(created.json['data']['inserted_rows'],2)
        self.assertEqual(created.json['data']['base_tables']['customer_addresses'][0]['customer_id'],self.base)
        self.assertTrue(created.json['trace'][0]['sql'].startswith('INSERT INTO customer_profiles'))
        self.assertEqual(self.post('customer_profiles',original).status_code,409)
        # The first child is new; the second child conflicts with the earlier document.
        second=self.profile(1)
        second['addresses'].append(copy.deepcopy(original['addresses'][0]))
        rejected=self.post('customer_profiles',second)
        self.assertEqual(rejected.status_code,409,rejected.json)
        with connect() as db, db.cursor() as cur:
            cur.execute('SELECT id FROM customers WHERE id=%s',(self.base+1,))
            self.assertIsNone(cur.fetchone())
            cur.execute('SELECT id FROM customer_addresses WHERE id=%s',(self.base+1,))
            self.assertIsNone(cur.fetchone())
        # Retrying with unique IDs can create multiple children in the same INSERT.
        second['addresses'][1]['id']=self.base+2
        valid=self.post('customer_profiles',second)
        self.assertEqual(valid.status_code,201,valid.json)
        self.assertEqual(valid.json['data']['inserted_rows'],3)
        self.assertEqual(len(valid.json['data']['record']['addresses']),2)
        persisted=self.client.get('/api/customers/'+str(self.base+1))
        self.assertEqual(persisted.json['data']['document']['name'],'Test Customer')

    def test_rejections(self):
        self.assertEqual(self.post('customer_summary',{}).status_code,405)
        self.assertEqual(self.post('customers',{}).status_code,404)
        invalid=[None, [], {}, {**self.profile(),'_id':True}, {**self.profile(),'addresses':[]},
                 {**self.profile(),'email':'bad'}, {**self.profile(),'tier':'Admin'},
                 {**self.profile(),'_metadata':{}}, {**self.profile(),'name':{'bad':1}}]
        for record in invalid:
            self.assertEqual(self.post('customer_profiles',record).status_code,400,record)
        duplicate=self.profile();duplicate['addresses']*=2
        self.assertEqual(self.post('customer_profiles',duplicate).status_code,400)
        with connect() as db, db.cursor() as cur:
            cur.execute('SELECT id FROM customers WHERE id=%s',(self.base,))
            self.assertIsNone(cur.fetchone())

if __name__ == '__main__':
    unittest.main(verbosity=2)

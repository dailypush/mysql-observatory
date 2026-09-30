import hashlib
import json
import math
import re
import statistics
import time
from decimal import Decimal

import pymysql
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from database import connect

app = Flask(__name__, static_folder='static', static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 16384


def clean(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def query(cur, sql, params=(), trace=None):
    start = time.perf_counter()
    cur.execute(sql, params)
    rows = cur.fetchall() if cur.description else []
    if trace is not None:
        trace.append({'sql': sql, 'params': list(params), 'ms': round((time.perf_counter()-start)*1000, 3)})
    return clean(rows)


def document(cur, customer_id, mode, trace):
    if mode == 'classic':
        rows = query(cur, 'SELECT id, name, email, city, tier FROM customers WHERE id = %s', (customer_id,), trace)
        if not rows:
            return None
        row = rows[0]
        row['_id'] = row.pop('id')
        return row
    rows = query(cur, "SELECT data FROM customer_documents WHERE data->>'$._id' = %s", (str(customer_id),), trace)
    return json.loads(rows[0]['data']) if rows else None


def version(doc):
    public = {k: v for k, v in doc.items() if k != '_metadata'}
    return hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()


def response(data, trace):
    return jsonify(clean({'data': data, 'trace': trace}))


@app.get('/')
def index():
    return app.send_static_file('index.html')


@app.get('/api/health')
def health():
    with connect() as db, db.cursor() as cur:
        rows = query(cur, 'SELECT VERSION() AS version, @@version_comment AS edition')
        counts = query(cur, 'SELECT (SELECT COUNT(*) FROM customers) AS customers, (SELECT COUNT(*) FROM orders) AS orders, (SELECT COUNT(*) FROM products) AS products')
    return jsonify({'status': 'ok', **rows[0], **counts[0]})


@app.route('/api/customers/<int:customer_id>', methods=['GET', 'PUT'])
def customer(customer_id):
    mode = request.args.get('mode', 'modern')
    if mode not in ('classic', 'modern'):
        return jsonify(error='Unknown mode'), 400
    trace = []
    with connect() as db, db.cursor() as cur:
        if request.method == 'PUT':
            payload = request.get_json()
            if not isinstance(payload, dict) or not isinstance(payload.get('document'), dict):
                return jsonify(error='A document object is required.'), 400
            doc = payload['document']
            fields = {'name':100, 'email':150, 'city':80, 'tier':20}
            if set(doc) - (set(fields) | {'_id', '_metadata'}):
                return jsonify(error='Only name, email, city, and tier are editable.'), 400
            if type(doc.get('_id')) is not int or doc['_id'] != customer_id:
                return jsonify(error='The document ID cannot be changed.'), 400
            for key, limit in fields.items():
                if not isinstance(doc.get(key), str) or not doc[key].strip() or len(doc[key]) > limit:
                    return jsonify(error=f'{key} must be nonempty text of at most {limit} characters.'), 400
            if doc['tier'] not in ('Explorer', 'Plus', 'Pro') or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', doc['email']):
                return jsonify(error='Use a valid email and tier (Explorer, Plus, or Pro).'), 400
            query(cur, 'SELECT id FROM customers WHERE id = %s FOR UPDATE', (customer_id,), trace)
            current = document(cur, customer_id, mode, trace)
            if current is None:
                return jsonify(error='Customer not found.'), 404
            if payload.get('version') != version(current):
                return jsonify(error='This profile changed since it was loaded. Reload before saving.'), 409
            if mode == 'modern':
                new_doc = {k: doc[k] for k in ['_id', *fields]}
                # Use the database-provided metadata from the locked current document.
                if '_metadata' in current:
                    new_doc['_metadata'] = current['_metadata']
                query(cur, "UPDATE customer_documents SET data = %s WHERE data->>'$._id' = %s", (json.dumps(new_doc), str(customer_id)), trace)
            else:
                query(cur, 'UPDATE customers SET name=%s, email=%s, city=%s, tier=%s WHERE id=%s', tuple(doc[k] for k in fields)+(customer_id,), trace)
            db.commit()
        doc = document(cur, customer_id, mode, trace)
        if doc is None:
            return jsonify(error='Customer not found.'), 404
        rows = query(cur, 'SELECT id, name, email, city, tier FROM customers WHERE id = %s', (customer_id,), trace)
    return response({'document': doc, 'row': rows[0], 'version': version(doc), 'mode': mode}, trace)


# Deliberately small, transparent feature vectors; these are not learned embeddings.
CONCEPTS = [
    {'outdoor','outdoors','trail','trails','hike','hiking','mountain','camp','adventure','adventures','nature'},
    {'tech','technology','wireless','digital','audio','music','camera','headphones','keyboard'},
    {'home','cozy','comfort','coffee','ceramic','linen','soft','reading'},
    {'fitness','running','run','workout','training','yoga','wellness','exercise','sport'},
    {'travel','trip','trips','weekend','portable','commute','lightweight','bag','pack'},
    {'work','workspace','desk','studio','creative','design','focus','focused','productive'},
]


def embed(text):
    words = set(re.findall(r'[a-z]+', text.lower()))
    values = [float(len(words & concept)) for concept in CONCEPTS]
    return values if any(values) else None


def cosine(a, b):
    norm = math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
    return sum(x*y for x,y in zip(a,b))/norm if norm else 0


@app.get('/api/search')
def search():
    text = request.args.get('q', '').strip()
    mode = request.args.get('mode', 'modern')
    if not text or len(text) > 200 or mode not in ('classic', 'modern'):
        return jsonify(error='Enter a search of 1–200 characters and a valid mode.'), 400
    trace = []
    vec = embed(text)
    with connect() as db, db.cursor() as cur:
        if mode == 'classic':
            escaped = text.replace('!', '!!').replace('%', '!%').replace('_', '!_')
            rows = query(cur, "SELECT id, name, category, description, price FROM products WHERE name LIKE %s ESCAPE '!' OR description LIKE %s ESCAPE '!' ORDER BY id", (f'%{escaped}%', f'%{escaped}%'), trace)
        else:
            rows = query(cur, 'SELECT id, name, category, description, price, VECTOR_TO_STRING(embedding) AS embedding, VECTOR_DIM(embedding) AS dimensions FROM products', (), trace)
            for row in rows:
                row['score'] = round(cosine(vec, json.loads(row.pop('embedding')))*100, 1) if vec else 0
            rows = sorted(rows, key=lambda row: (-row['score'], row['id']))[:6] if vec else []
    return response({'products':rows, 'query_vector':vec, 'mode':mode, 'ranking':'Python cosine similarity over MySQL VECTOR values; hand-authored six-dimensional features, no AI model.'}, trace)


BENCHMARK_SQL = """SELECT p.category, c.tier, COUNT(*) AS order_count,
       ROUND(SUM(o.total), 2) AS revenue
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN products p ON p.id = o.product_id
WHERE o.status = %s AND c.city = %s
GROUP BY p.category, c.tier
ORDER BY revenue DESC, p.category, c.tier"""


@app.post('/api/benchmark')
def benchmark():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error='Expected a JSON object.'), 400
    city = payload.get('city', 'Portland')
    status = payload.get('status', 'Delivered')
    if city not in ('Portland','Austin','Brooklyn','Seattle','Denver') or status not in ('Delivered','Processing','Shipped'):
        return jsonify(error='Choose a valid city and order status.'), 400
    trace, results = [], {}
    with connect() as db, db.cursor() as cur:
        # Both optimizers share a consistent transaction snapshot.
        for label, switch in [('classic','off'), ('hypergraph','on')]:
            query(cur, f"SET SESSION optimizer_switch='hypergraph_optimizer={switch}'", (), trace)
            query(cur, BENCHMARK_SQL, (status,city))  # warmup
            times = []
            for _ in range(5):
                start = time.perf_counter()
                rows = query(cur, BENCHMARK_SQL, (status,city))
                times.append((time.perf_counter()-start)*1000)
            plan = query(cur, 'EXPLAIN ANALYZE '+BENCHMARK_SQL, (status,city), trace)
            results[label] = {'median_ms':round(statistics.median(times),3), 'samples_ms':[round(t,3) for t in times], 'rows':rows, 'plan':'\n'.join(str(next(iter(row.values()))) for row in plan)}
    results['same_results'] = results['classic']['rows'] == results['hypergraph']['rows']
    results['method'] = 'Same MySQL server and transaction; one warmup, then five client-observed SELECT timings per optimizer. Classic runs first. EXPLAIN ANALYZE is measured separately. This is a small demonstration, not a cross-version benchmark.'
    return response(results, trace)


@app.errorhandler(pymysql.MySQLError)
def database_error(error):
    app.logger.exception('Database operation failed')
    return jsonify(error='The database operation failed. Check the app container logs for details.'), 503


@app.errorhandler(HTTPException)
def http_error(error):
    return jsonify(error=error.description), error.code


@app.after_request
def headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    resp.headers['Cache-Control'] = 'no-store'
    return resp

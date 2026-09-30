"""An allowlisted view catalog. View names never come from arbitrary SQL input."""
import json
import re
import pymysql
from flask import Blueprint, jsonify, request
from database import connect, clean, query

views = Blueprint('views', __name__)
CATALOG = {
    'customer_directory': {
        'title': 'Customer directory', 'kind': 'sql', 'insertable': True,
        'tables': ['customers'],
        'description': 'A conventional SQL view. Its column metadata builds the form. INSERT writes one customer row.',
        'availability': 'Established MySQL feature; writable SQL views are not new in 9.7.',
    },
    'customer_profiles': {
        'title': 'Customer + addresses', 'kind': 'json_duality', 'insertable': True,
        'tables': ['customers', 'customer_addresses'],
        'description': 'One nested JSON document inserts a customer and their addresses atomically through a JSON duality view.',
        'availability': 'JSON duality introduced in 9.4; Community DML support added in 9.7.',
    },
    'customer_summary': {
        'title': 'Customers by city & tier', 'kind': 'aggregate', 'insertable': False,
        'tables': ['customers'],
        'description': 'COUNT and GROUP BY produce a read-only view. There is no single source row for an aggregate result.',
        'availability': 'Read-only aggregate views are an established MySQL feature.',
    },
}


def envelope(data, trace, status=200):
    return jsonify(clean({'data': data, 'trace': trace})), status


def sample_rows(cur, name, trace):
    if name == 'customer_profiles':
        rows = query(cur, 'SELECT data FROM customer_profiles ORDER BY CAST(data->>\'$._id\' AS UNSIGNED) DESC LIMIT 5', (), trace)
        return [json.loads(row['data']) for row in rows]
    order = 'city, tier' if name == 'customer_summary' else 'id DESC'
    return query(cur, f'SELECT * FROM `{name}` ORDER BY {order} LIMIT 5', (), trace)


@views.get('/api/views')
def catalog():
    return envelope([{'name': name, **info} for name, info in CATALOG.items()], [])


@views.get('/api/views/<name>')
def inspect_view(name):
    if name not in CATALOG:
        return jsonify(error='Unknown demo view.'), 404
    trace = []
    with connect() as db, db.cursor() as cur:
        ddl = query(cur, f'SHOW CREATE VIEW `{name}`', (), trace)[0]['Create View']
        columns = query(cur, '''SELECT COLUMN_NAME AS name, DATA_TYPE AS type,
            IS_NULLABLE AS nullable, CHARACTER_MAXIMUM_LENGTH AS max_length
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION''', (name,), trace)
        sample = sample_rows(cur, name, trace)
        template = None
        if CATALOG[name]['insertable']:
            customer_id = query(cur, 'SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM customers', (), trace)[0]['next_id']
            template = {'id': customer_id, 'name': 'Jordan Lee', 'email': 'jordan@example.com', 'city': 'Seattle', 'tier': 'Explorer'}
            if name == 'customer_profiles':
                address_id = query(cur, 'SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM customer_addresses', (), trace)[0]['next_id']
                template['_id'] = template.pop('id')
                template['addresses'] = [{'id':address_id, 'label':'Home', 'street':'42 Cedar Lane', 'city':'Seattle', 'country':'United States'}]
    return envelope({'name':name, **CATALOG[name], 'definition':ddl, 'columns':columns,
                     'template':template, 'rows':sample,
                     'metadata_note':'SQL form fields come from INFORMATION_SCHEMA.COLUMNS. The nested JSON example is an explicit application contract matching the view definition. Insert support is allowlisted, not inferred from IS_UPDATABLE.',
                     'id_note':'Suggested IDs are not reserved. A concurrent insert may require loading a fresh example.'}, trace)


def validate_record(record, nested):
    if not isinstance(record, dict):
        return 'Provide one object, not an array or scalar.'
    pk = '_id' if nested else 'id'
    expected = {pk, 'name', 'email', 'city', 'tier'} | ({'addresses'} if nested else set())
    if set(record) != expected:
        return 'Use exactly the fields shown in the example, including all required fields.'
    if type(record[pk]) is not int or not 1 <= record[pk] <= 2147483647:
        return 'Customer ID must be a positive 32-bit integer.'
    for field, limit in [('name',100),('email',150),('city',80),('tier',20)]:
        if not isinstance(record[field], str) or not record[field].strip() or len(record[field]) > limit:
            return f'{field} must contain 1–{limit} characters.'
    if record['tier'] not in ('Explorer','Plus','Pro') or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', record['email']):
        return 'Use a valid email and tier (Explorer, Plus, or Pro).'
    if nested:
        addresses = record['addresses']
        if not isinstance(addresses, list) or not 1 <= len(addresses) <= 5:
            return 'Include between one and five address objects.'
        ids = set()
        for address in addresses:
            if not isinstance(address, dict) or set(address) != {'id','label','street','city','country'}:
                return 'Each address requires id, label, street, city, and country.'
            if type(address['id']) is not int or not 1 <= address['id'] <= 2147483647 or address['id'] in ids:
                return 'Address IDs must be distinct positive 32-bit integers.'
            ids.add(address['id'])
            for field, limit in [('label',30),('street',150),('city',80),('country',80)]:
                if not isinstance(address[field], str) or not address[field].strip() or len(address[field]) > limit:
                    return f'Address {field} must contain 1–{limit} characters.'
    return None


@views.post('/api/views/<name>/rows')
def insert_view(name):
    if name not in CATALOG:
        return jsonify(error='Unknown demo view.'), 404
    if not CATALOG[name]['insertable']:
        return jsonify(error='This aggregate view is read-only. Choose a writable view.'), 405
    payload = request.get_json()
    if not isinstance(payload, dict) or set(payload) != {'record'}:
        return jsonify(error='Provide a record object.'), 400
    record = payload['record']
    nested = name == 'customer_profiles'
    problem = validate_record(record, nested)
    if problem:
        return jsonify(error=problem), 400
    customer_id = record['_id' if nested else 'id']
    trace = []
    with connect() as db, db.cursor() as cur:
        try:
            if nested:
                # MySQL derives each child's customer_id from the view relationship.
                query(cur, 'INSERT INTO customer_profiles VALUES (%s)', (json.dumps(record),), trace)
                created = json.loads(query(cur, "SELECT data FROM customer_profiles WHERE data->>'$._id' = %s", (str(customer_id),), trace)[0]['data'])
            else:
                fields = ('id','name','email','city','tier')
                query(cur, 'INSERT INTO customer_directory (id, name, email, city, tier) VALUES (%s, %s, %s, %s, %s)', tuple(record[k] for k in fields), trace)
                created = query(cur, 'SELECT * FROM customer_directory WHERE id = %s', (customer_id,), trace)[0]
            base = {'customers': query(cur, 'SELECT * FROM customers WHERE id = %s', (customer_id,), trace)}
            if nested:
                base['customer_addresses'] = query(cur, 'SELECT * FROM customer_addresses WHERE customer_id = %s ORDER BY id', (customer_id,), trace)
            db.commit()
        except pymysql.MySQLError as exc:
            db.rollback()
            # 6492: an existing child would violate the duality-view relationship.
            if exc.args[0] in (1062, 6492):
                return jsonify(error='A customer or address ID already exists. Nothing was inserted. Load a fresh example or choose unused IDs.'), 409
            raise
    return envelope({'name':name, 'record':created, 'base_tables':base,
                     'inserted_rows':sum(len(rows) for rows in base.values()),
                     'committed':True}, trace, 201)

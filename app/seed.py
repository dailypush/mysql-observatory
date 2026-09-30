"""Deterministic, restart-safe sample data. No external AI or data service."""
import datetime
import json
import random
import time
from database import connect

PRODUCTS = [
    (1, 'Summit daypack', 'Outdoors', 'Lightweight waterproof pack for trails and weekend escapes.', 89, [1,.1,.1,.5,.9,.2]),
    (2, 'Trail running shoes', 'Outdoors', 'Grippy, lightweight shoes for mountain runs and outdoor training.', 135, [1,.1,.2,.7,.8,.1]),
    (3, 'Studio headphones', 'Technology', 'Immersive wireless audio with noise cancellation for focused work.', 249, [.1,1,.2,.8,.2,.7]),
    (4, 'Mechanical keyboard', 'Technology', 'A tactile, compact keyboard for a productive creative workspace.', 159, [.1,1,.3,.6,.1,.9]),
    (5, 'Pour-over set', 'Home', 'Slow mornings start with a handcrafted ceramic coffee set.', 64, [.1,.1,1,.2,.1,.8]),
    (6, 'Linen throw', 'Home', 'Soft natural texture and a little everyday comfort for your home.', 79, [.1,.1,1,.1,.2,.6]),
    (7, 'Travel camera', 'Technology', 'A compact camera for capturing adventures in beautiful detail.', 549, [.7,1,.1,.5,.7,.8]),
    (8, 'Insulated flask', 'Outdoors', 'Hot coffee or cold water, from your morning commute to the trail.', 38, [.8,.1,.5,.4,1,.2]),
    (9, 'Desk lamp', 'Home', 'Warm adjustable light for reading, studying, and focused work.', 95, [.1,.5,.9,.2,.1,1]),
    (10, 'Yoga mat', 'Wellness', 'A cushioned natural rubber mat for balance and daily movement.', 72, [.4,.1,.5,1,.3,.2]),
    (11, 'Smart watch', 'Wellness', 'Track your runs, workouts, and daily activity on the go.', 299, [.7,.9,.1,1,.7,.3]),
    (12, 'Weekender bag', 'Outdoors', 'A versatile canvas companion for short trips and city breaks.', 119, [.8,.2,.3,.2,1,.7]),
]


def seed():
    for attempt in range(30):
        try:
            db = connect()
            break
        except Exception:
            if attempt == 29:
                raise
            time.sleep(2)
    try:
        with db.cursor() as cur:
            cur.execute('SELECT GET_LOCK(%s, 30) AS locked', ('observatory_seed',))
            if cur.fetchone()['locked'] != 1:
                raise RuntimeError('Could not acquire seed lock')
            cur.execute('SELECT COUNT(*) AS n FROM customers')
            if cur.fetchone()['n']:
                print('Existing sample data retained.', flush=True)
                return
            rng = random.Random(42)
            cities = ['Portland', 'Austin', 'Brooklyn', 'Seattle', 'Denver']
            people = [(1, 'Alex Morgan', 'alex@example.com', 'Portland', 'Plus')]
            people += [(i, f'Customer {i:04}', f'customer{i}@example.com', rng.choice(cities), rng.choice(['Explorer', 'Plus', 'Pro'])) for i in range(2, 2001)]
            cur.executemany('INSERT INTO customers VALUES (%s,%s,%s,%s,%s)', people)
            cur.executemany('INSERT INTO products VALUES (%s,%s,%s,%s,%s,STRING_TO_VECTOR(%s))', [(*p[:5], json.dumps(p[5])) for p in PRODUCTS])
            rows = []
            for i in range(1, 30001):
                product = rng.choice(PRODUCTS)
                quantity = rng.randint(1, 4)
                rows.append((i, rng.randint(1, 2000), product[0], quantity, product[4] * quantity, rng.choice(['Delivered']*7 + ['Processing']*2 + ['Shipped']), datetime.date(2026, 1, 1) + datetime.timedelta(days=rng.randrange(270))))
            cur.executemany('INSERT INTO orders VALUES (%s,%s,%s,%s,%s,%s,%s)', rows)
            db.commit()
            cur.execute('ANALYZE TABLE customers, products, orders')
            print('Seeded 2,000 customers, 12 vectors, and 30,000 orders.', flush=True)
    finally:
        db.close()

if __name__ == '__main__':
    seed()

CREATE TABLE IF NOT EXISTS customer_addresses (
  id INT PRIMARY KEY,
  customer_id INT NOT NULL,
  label VARCHAR(30) NOT NULL,
  street VARCHAR(150) NOT NULL,
  city VARCHAR(80) NOT NULL,
  country VARCHAR(80) NOT NULL,
  FOREIGN KEY (customer_id) REFERENCES customers(id)
);
CREATE OR REPLACE VIEW customer_directory AS
SELECT id, name, email, city, tier FROM customers;
CREATE OR REPLACE JSON DUALITY VIEW customer_profiles AS
SELECT JSON_DUALITY_OBJECT(WITH (INSERT)
  '_id': c.id, 'name': c.name, 'email': c.email,
  'city': c.city, 'tier': c.tier,
  'addresses': (
    SELECT JSON_ARRAYAGG(JSON_DUALITY_OBJECT(WITH (INSERT)
      'id': a.id, 'label': a.label, 'street': a.street,
      'city': a.city, 'country': a.country
    )) FROM customer_addresses a WHERE a.customer_id = c.id
  )
) FROM customers c;
CREATE OR REPLACE VIEW customer_summary AS
SELECT city, tier, COUNT(*) AS customer_count
FROM customers GROUP BY city, tier;

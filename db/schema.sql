USE observatory;
CREATE TABLE customers (
  id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL,
  city VARCHAR(80) NOT NULL,
  tier VARCHAR(20) NOT NULL,
  CHECK (tier IN ('Explorer', 'Plus', 'Pro'))
);
CREATE TABLE products (
  id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  category VARCHAR(40) NOT NULL,
  description VARCHAR(300) NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  embedding VECTOR(6) NOT NULL
);
CREATE TABLE orders (
  id INT PRIMARY KEY,
  customer_id INT NOT NULL,
  product_id INT NOT NULL,
  quantity INT NOT NULL,
  total DECIMAL(10,2) NOT NULL,
  status VARCHAR(20) NOT NULL,
  created_at DATE NOT NULL,
  FOREIGN KEY (customer_id) REFERENCES customers(id),
  FOREIGN KEY (product_id) REFERENCES products(id),
  INDEX idx_status_date(status, created_at)
);
CREATE JSON DUALITY VIEW customer_documents AS
SELECT JSON_DUALITY_OBJECT(WITH (UPDATE)
  '_id': id, 'name': name, 'email': email, 'city': city, 'tier': tier
) FROM customers;

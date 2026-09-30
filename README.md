# MySQL Observatory

A Dockerized, interactive demo of MySQL 9.7 Community with a responsive frontend, a Python/Flask API, and a real persistent database. Explore changes in the interface, API contract, SQL, and query execution side by side.

## Start

Requires Docker Desktop (running) or Docker Engine with Compose. No local Python, Node, API keys, or enterprise license required. Supports Apple Silicon and x86-64 through the official images.

```sh
docker compose up -d --build --wait
```

Open **http://localhost:8097**. First launch downloads the images and seeds the database; allow a few minutes. Subsequent starts preserve edits. The application starts only after MySQL is healthy, and its health check covers database connectivity.

```sh
docker compose ps
docker compose logs -f app
```

Port 8097 avoids commonly cached localhost apps. Override with `APP_PORT=8098 docker compose up -d --build --wait`, or copy `.env.example` to `.env` and customize it. The app binds to `127.0.0.1`; MySQL is accessible only on the Compose network. The sample credentials are for this local demo. Set passwords **before first launch**; changing environment variables does not rotate credentials in an existing database volume.

## Five-minute presentation

1. **JSON duality:** Select **Before** to show a conventional customer form and column-based UPDATE. Switch to **After**, change `city` in the JSON editor, and save. The real `customer_documents` JSON duality view writes back to the `customers` table. The updated relational row is visible below the editor. Open **SQL** and **API response** in the inspector to explain each layer. **Reload** discards unsaved edits and reads current database state.
2. **Vector discovery:** In **Before**, search `weekend outdoor adventure`: the literal phrase produces no matches. **After** returns ranked outdoor products using native `VECTOR(6)` storage and Python cosine similarity. Try `focused creative workspace` and `cozy home coffee`. The query vector is shown below the results.
3. **Query optimizer:** Run a comparison to execute the same three-table analytics query with the classic optimizer and the new Community hypergraph optimizer. See measured median timings, identical-result verification, all result rows, and expandable `EXPLAIN ANALYZE` trees. Change city or status and rerun. Use **What changed** for presenter notes and official references.

The in-app **Demo guide** and **Architecture** dialogs explain the flow.

## What is actually new?

| Lab | Frontend change | Backend change | Version / scope |
| --- | --- | --- | --- |
| JSON duality | Field form → editable JSON document | Column UPDATE → UPDATE against a real JSON duality view | JSON duality views introduced in 9.4; Community DML available in 9.7 |
| Vector discovery | Literal phrase results → ranked concept matches | LIKE → native VECTOR reads + Python cosine ranking | VECTOR type introduced in 9.0 |
| Query optimizer | Live timings, result comparison, execution plans | Session-scoped classic vs hypergraph optimizer | Hypergraph available in Community in 9.7 |

**Before/After compares application approaches on one current server, not two database versions.** The demo pins the published official Docker image `mysql:9.7.2` rather than a floating latest tag.

**Vector scope:** The six features are hand-authored and transparent: outdoors, technology, home, wellness, travel, and workspace. Query terms map to a small dictionary in `app/server.py`. This is an educational similarity example, not an AI embedding model. MySQL Community stores and converts vectors; ranking occurs in Python over all 12 products. Community has neither the `DISTANCE()` function nor native ANN indexing. No external service is called. Unknown vocabulary yields an explicit empty result.

**Optimizer scope:** Both planners run on the same MySQL server and consistent transaction snapshot. Each gets one warmup and five measured SELECTs; classic runs first. The reported median includes client/driver overhead, and plan collection happens separately. Small warm-cache timings are noisy and order-biased; this is not a production benchmark or a promise of improvement. EXPLAIN ANALYZE itself dates to MySQL 8.0.18. The inspector displays SET and EXPLAIN statements; the timing samples also include the SELECT runs described above.

**Document scope:** One base table keeps the example focused. MySQL also supports nested relational projections. The API validates inputs, parameterizes SQL, locks the row while saving, and rejects stale versions with HTTP 409. The visible proof SELECT is an additional demonstration query, not required by the duality view. `_metadata` is database-managed and omitted from the editor.

## Architecture

```text
Browser (HTML / CSS / JavaScript)
  │ same-origin HTTP :8097 → container :8080
  ▼
app: Python 3.12 / Flask / Gunicorn / PyMySQL
  │ parameterized SQL over private Compose network
  ▼
db: MySQL 9.7.2 Community
  └─ mysql_data named volume
```

- `app/static/`: responsive frontend, live inspector, dialogs, loading/error/empty states.
- `app/server.py`: health, document, search, and optimizer API routes.
- `app/seed.py`: deterministic, transactional, restart-safe data seed with an advisory lock.
- `db/schema.sql`: relational schema, native VECTOR column, writable JSON duality view.
- `tests/test_integration.py`: integration tests against the actual database.
- `compose.yaml`: health checks, persistent database volume, localhost-only app port.

Data: 2,000 synthetic customers, 12 products, 30,000 synthetic orders generated with a fixed random seed. Dates are fixed to January–September 2026 for repeatability.

## API

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/health` | Live version, edition, and dataset counts |
| GET | `/api/customers/1?mode=modern` | JSON duality document, relational row, version token, SQL trace |
| PUT | `/api/customers/1?mode=modern` | Save `{ "document": {...}, "version": "<read token>" }` |
| GET | `/api/search?q=weekend%20outdoor%20adventure&mode=modern` | Ranked products and query vector |
| POST | `/api/benchmark` | Compare planners; optional `{ "city": "Portland", "status": "Delivered" }` |

Document and search routes also accept `mode=classic`. Each lab response includes executed SQL, bound parameters, and measured database call durations for the inspector. This intentional debug visibility and lack of authentication make the app a local presentation tool, not a production deployment template.

## Verify

```sh
docker compose exec -T app python /tests/test_integration.py
```

Tests cover live server/version and assets, document writes through both paths, database readback, stale-edit conflicts, input validation, missing records, keyword vs vector results, wildcard handling, and optimizer result parity with real execution plans. The document test restores its original customer data in a `finally` block. Run tests without concurrently editing that demo customer.

## Develop

Edit source files, then rebuild the application:

```sh
docker compose up -d --build --wait app
```

Schema initialization runs only on a new MySQL volume. For intentional schema changes, use a migration or explicitly reset this demo’s data as below.

## Stop / reset

Stop while preserving data:

```sh
docker compose down
```

To intentionally erase this demo’s database and regenerate the original sample data:

```sh
# Destructive: removes only this Compose project's sample database volume.
docker compose down -v
docker compose up -d --build --wait
```

If a first-time schema initialization fails, inspect `docker compose logs db` before resetting. Do not point this demo at an existing production database.

## Official feature references

- [MySQL 9.7 release notes](https://dev.mysql.com/doc/relnotes/mysql/9.7/en/news-9-7-0.html)
- [JSON duality view syntax and constraints](https://dev.mysql.com/doc/refman/9.7/en/create-json-duality-view.html)
- [Vector functions and edition restrictions](https://dev.mysql.com/doc/refman/9.7/en/vector-functions.html)
- [Hypergraph optimizer in MySQL 9.7 Community](https://blogs.oracle.com/mysql/the-hypergraph-optimizer-is-now-available-in-mysql-9-7-community-edition)
- [Official MySQL Docker images](https://hub.docker.com/_/mysql)

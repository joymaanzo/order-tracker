# Order Tracker

A small order tracking app for the AI Dev Tools Zoomcamp observability homework. It includes a web page, API, tests, and a Docker Compose setup. You add telemetry, alerts, and an incident responder in Homework 4.

The main user flow is creating an order and checking its status. Three sample orders are created on first startup.

## Run it

You need Docker with Compose. To run the tests, you also need Python 3.11+ and `uv`.

```bash
docker compose up --build -d --wait
```

Open <http://127.0.0.1:8000>. The API is at `/api/orders`, and the health check is at `/healthz`. Data is stored in a Docker volume and survives container recreation.

Grafana is available at <http://127.0.0.1:3000> with the default `admin` / `admin` credentials. The provisioned `Order Tracker Observability` dashboard uses Prometheus for request metrics and has Loki and Tempo configured for log and trace exploration. The app sends OTLP telemetry to the Compose collector, which forwards metrics to Prometheus, logs to Loki, and traces to Tempo.

The incident responder listens at `http://127.0.0.1:8001/alerts` and saves webhook records under `incident-response/alerts`. It invokes `CODING_AGENT_COMMAND` from the mounted repository workspace; by default this is `claude -p --dangerously-skip-permissions`. Install Claude Code in the responder image or override that variable with an available headless coding-agent command before relying on automated fixes. The agent is instructed to inspect logs and tests, commit real fixes, and explain false positives.

If port 8000 is occupied, set `ORDER_TRACKER_PORT`, for example:

```bash
ORDER_TRACKER_PORT=18080 docker compose up --build -d --wait
```

Run tests with `uv run --frozen pytest -q`. Stop the app with `docker compose down`. Add `-v` only if you also want to delete the order data.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Web page |
| GET | `/healthz` | Database health check |
| GET | `/api/orders` | List orders |
| POST | `/api/orders` | Create an order |
| GET | `/api/orders/{id}` | Check an order |
| PATCH | `/api/orders/{id}` | Change an order status |

The app uses SQLite to keep setup small. Run one app container at a time. The course exercise is about detecting and handling an incident, not scaling the database.

# kube-administration
scripts for administration kubernetes with kubectl and api

# delete_old_release.py
The script is designed to remove helm releases older than a certain number of days.

# json_to_yaml.py
script for modifying yaml files with data from json

# k8s-db-inventory

A small Python script that discovers which databases and message brokers each application in a Kubernetes cluster connects to, and stores the result in InfluxDB for visualization in Grafana.

It answers questions like:

- Which databases does a given service use?
- Which applications connect to a given database server?
- How has the set of connections changed over time?

## How it works

1. Finds application namespaces by the label `purpose=app`.
2. Reads all deployments in those namespaces via `kubectl`.
3. Scans environment variables of init containers (optionally main containers too) for connection strings.
4. Parses each connection string into host, database name and storage type.
5. Removes duplicate connections within a deployment.
6. Writes one point per connection to InfluxDB.

### Supported connection string formats

| Format | Example | Detected type |
|---|---|---|
| PostgreSQL URL | `postgresql://user:pass@host:5432/db` | `postgres` |
| PostgreSQL libpq | `host=host port=5432 dbname=db user=user` | `postgres` |
| Redis | `redis://:pass@host:6379/0` | `redis` |
| RabbitMQ | `amqp://user:pass@host:5672/vhost` | `rabbitmq` |
| ClickHouse | `clickhouse://user:pass@host:9000/db` | `clickhouse` |
| Kafka | `kafka://host:9092` | `kafka` |

SQLAlchemy-style schemes such as `postgresql+asyncpg://` are supported. Vault placeholders like `${vault:secret/data/app#DB_PASS}` are recognized and skipped, so the script never reads or stores secrets.

## Requirements

- Python 3.8+
- `kubectl` configured with read access to namespaces and deployments of the target cluster
- InfluxDB 2.x

## Installation

```bash
git clone https://github.com/<your-org>/k8s-db-inventory.git
cd k8s-db-inventory
pip install influxdb-client
```

## Configuration

The InfluxDB connection is configured via environment variables:

| Variable | Required | Description |
|---|---|---|
| `INFLUXDB_TOKEN` | yes | InfluxDB API token with write access to the bucket |
| `INFLUXDB_URL` | no | InfluxDB URL |
| `INFLUXDB_ORG` | no | InfluxDB organization |
| `INFLUXDB_BUCKET` | no | Target bucket |

Set `INCLUDE_MAIN_CONTAINERS = True` in the script to scan main containers in addition to init containers.

## Usage

```bash
export INFLUXDB_TOKEN="<your-token>"
python3 k8s_db_inventory.py
```

The script prints every connection it finds:

```
dev1-auth: host=db-pgsql-dev01.example.local db=dev1_sky_backoffice type=postgres
stage-quotes-backend: host=db-ch-01.example.local db=quotes type=clickhouse
stage-quotes-backend: host=stage-redis-quotes db=0 type=redis
```

To collect data regularly, run it on a schedule, for example with cron or a Kubernetes CronJob.

## Data model

All points are written to the `db_access` measurement:

| Key | Kind | Description |
|---|---|---|
| `deployment` | tag | Deployment name |
| `db_type` | tag | `postgres`, `redis`, `rabbitmq`, `clickhouse` or `kafka` |
| `db_host` | tag | Database or broker host |
| `db_name` | tag | Database name, Redis DB number or AMQP vhost |
| `present` | field | Always `1`; marks that the connection existed at that time |

All points from one run share the same timestamp.

Example in line protocol:

```
db_access,deployment=dev1-auth,db_type=postgres,db_host=db-pgsql-dev01.example.local,db_name=dev1_sky_backoffice present=1i 1790000000000000000
```

## Grafana

Example Flux query for a table of current connections. The bucket name is taken from the selected data source variable:

```flux
from(bucket: "${datasource:text}")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_measurement"] == "db_access")
  |> filter(fn: (r) => r["_field"] == "present")
  |> last()
```

This assumes that the Grafana data source names match the InfluxDB bucket names.

## Limitations

- Only variables with an inline `value` are read. Variables set via `valueFrom` or `envFrom` (Secrets, ConfigMaps) are not scanned.
- Only deployments are scanned; StatefulSets, DaemonSets and CronJobs are not.
- Connection strings without a scheme (for example, a bare `host:9092`) are not detected.

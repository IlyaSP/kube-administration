# kube-administration
scripts for administration kubernetes with kubectl and api
#----------------------------------------------------------------------------------------------
# delete_old_release.py
The script is designed to remove helm releases older than a certain number of days.
#----------------------------------------------------------------------------------------------
# json_to_yaml.py
script for modifying yaml files with data from json

#----------------------------------------------------------------------------------------------
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

#-----------------------------------------------------------------------------------------------------------------------

# k8s-prod-audit

A Python script that audits a production Kubernetes cluster for common configuration and monitoring gaps. It reads data from the cluster, Uptime Kuma and Zabbix, and prints color-coded warnings to the terminal.

The script is read-only: it never changes anything in the cluster or in the monitoring systems.

## Checks

### 1. Resource limits

Finds containers in production deployments that have no `resources.limits` set.

```
The deployment prod-api container app has no limits
```

### 2. Liveness and readiness probes

Finds containers in production deployments that have no `livenessProbe` or `readinessProbe`. Both probes are checked independently.

```
The prod-api container app has no LivenessProbe
The prod-api container app has no ReadinessProbe
```

### 3. Uptime monitoring in Uptime Kuma

Collects hostnames from production ingresses and compares them with the URLs of Uptime Kuma monitors. Reports every production host that has no monitor.

```
The api.example.com is not present in the Kuma
```

### 4. Node monitoring in Zabbix

Compares the list of cluster nodes with the hosts in the Zabbix group `Discovered hosts`. Reports every node that is not added to Zabbix.

```
The node aws-east1-prod-kub-05 has not been added to Zabbix
```

### What counts as production

| Object | Rule |
|---|---|
| Deployments | name starts with `prod` or `rc` |
| Ingresses | name starts with `prod-` |
| Zabbix hosts | name matches `aws-east1-prod-kub-*` |

Deployments and ingresses are collected from all namespaces.

## Requirements

- Python 3.8+
- `kubectl` configured with read access to deployments, ingresses and nodes of the target cluster
- Access to the Uptime Kuma instance
- Access to the Zabbix API

## Installation

```bash
git clone https://github.com/<your-org>/k8s-prod-audit.git
cd k8s-prod-audit
pip install uptime-kuma-api zabbix_utils
```

## Configuration

Credentials are passed via environment variables:

| Variable | Description |
|---|---|
| `KUMA_USER` | Uptime Kuma username |
| `KUMA_PASSWD` | Uptime Kuma password |
| `ZABBIX_USER` | Zabbix username |
| `ZABBIX_PASSWD` | Zabbix password |

The Uptime Kuma and Zabbix URLs, the monitored domains and the name filters are currently set in the script itself. Adjust them for your environment before the first run.

## Usage

```bash
export KUMA_USER="<user>"
export KUMA_PASSWD="<password>"
export ZABBIX_USER="<user>"
export ZABBIX_PASSWD="<password>"

python3 k8s_prod_audit.py
```

Example output:

```
START
 Check prod app limits
 The deployment prod-api container app has no limits
 Check prod app probes
 The prod-worker container worker has no ReadinessProbe
 Check prod ingress and kuma
 All prod hosts are present in monitoring
 Check zabbix
 The node aws-east1-prod-kub-05 has not been added to Zabbix
```

In the terminal, section headers are blue, warnings yellow, missing Zabbix nodes red and successful checks cyan.

## Known issues

The following issues are known and marked with `TODO` in the code:

- Warning messages do not include the namespace, so deployments with the same name in different namespaces cannot be told apart.
- The deployment name filters differ between the limits check (`^(prod|rc)`) and the probes check (`^(prod|rc)-`).
- Only the first host of each ingress (`rules[0]`) is checked.
- If the Uptime Kuma login fails, the script continues and then crashes.
- Uptime Kuma monitors without a URL (ping, TCP, DNS) cause the script to crash.
- If the Zabbix group `Discovered hosts` does not exist, the script crashes.
- `kubectl` errors are not handled and result in an unclear JSON parsing error.

## Limitations

- Only variables with an inline `value` are read. Variables set via `valueFrom` or `envFrom` (Secrets, ConfigMaps) are not scanned.
- Only deployments are scanned; StatefulSets, DaemonSets and CronJobs are not.
- Connection strings without a scheme (for example, a bare `host:9092`) are not detected.
#-------------------------------------------------------------------------------------------------------------------

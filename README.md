# kube-administration
scripts for administration kubernetes with kubectl and api

# delete_old_release.py
The script is designed to remove helm releases older than a certain number of days.

# json_to_yaml.py
script for modifying yaml files with data from json

# k8s-db-inventory

A small Python script that discovers which databases and message brokers each application in a Kubernetes cluster connects to, and stores the result in InfluxDB for visualization in Grafana.

It answers questions like:

Which databases does a given service use?
Which applications connect to a given database server?
How has the set of connections changed over time?
How it works
Finds application namespaces by the label purpose=app.
Reads all deployments in those namespaces via kubectl.
Scans environment variables of init containers (optionally main containers too) for connection strings.
Parses each connection string into host, database name and storage type.
Removes duplicate connections within a deployment.
Writes one point per connection to InfluxDB.
Supported connection string formats
Format	Example	Detected type
PostgreSQL URL	postgresql://user:pass@host:5432/db	postgres
PostgreSQL libpq	host=host port=5432 dbname=db user=user	postgres
Redis	redis://:pass@host:6379/0	redis
RabbitMQ	amqp://user:pass@host:5672/vhost	rabbitmq
ClickHouse	clickhouse://user:pass@host:9000/db	clickhouse
Kafka	kafka://host:9092	kafka

SQLAlchemy-style schemes such as postgresql+asyncpg:// are supported. Vault placeholders like ${vault:secret/data/app#DB_PASS} are recognized and skipped, so the script never reads or stores secrets.

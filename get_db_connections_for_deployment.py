import subprocess
import json
import datetime
import re
import influxdb_client, os, time
from influxdb_client import InfluxDBClient, Point, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS
from jinja2 import Template
from urllib.parse import urlparse

# Схема URL -> тип хранилища
SCHEME_TO_TYPE = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "redis": "redis",
    "rediss": "redis",
    "amqp": "rabbitmq",
    "amqps": "rabbitmq",
    "kafka": "kafka",
    "clickhouse": "clickhouse",
}
 
URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)
# Плейсхолдеры вида ${vault:secret/data/...#KEY}: внутри есть '/' и '#', которые ломают urlparse
# находит ${, затем любые символы, кроме }, затем }
PLACEHOLDER_RE = re.compile(r"\$\{[^}]*\}")
# ищет пары host=... и dbname=..., где значение тянется до пробела или ;. findall возвращает список кортежей, например [('host', 'db-pgsql-dev01...'), ('dbname', 'stage_quotes')]
KV_RE = re.compile(r"\b(host|dbname)=([^\s;]+)")

INCLUDE_MAIN_CONTAINERS = False

def get_namespaces_list():
    with subprocess.Popen(
        ["kubectl get namespaces -l purpose=app -o json"],
        shell=True,
        stdout=subprocess.PIPE,
        text=True,
    ) as ns_proc:
        ns_raw_string = ns_proc.stdout.read()
        ns_json = json.loads(ns_raw_string)
    namespaces = [item["metadata"]["name"] for item in ns_json.get("items", [])]

    return namespaces

def parse_connection(value):
    """Разобрать строку подключения. Вернуть {host, db_name, db_type} или None."""
    value = PLACEHOLDER_RE.sub("secret", value) # находит выражение вида ${vault:secret/data/sky-backoffice/dev1#DEV1_DB_PASS} и заменяет на слово secret все такие фрагменты
    m = URL_RE.search(value) # ищем url
    if m:
        url = urlparse(m.group(0)) # разбираем url на части
        """
        функция urlparse раскладывает его на компоненты:

        Атрибут	Значение
        url.scheme	postgresql
        url.username	dev1_sky_backoffice
        url.password	secret
        url.hostname	db-pgsql-dev01.myjet.local
        url.port	5432
        url.path	/dev1_sky_backoffice
        """
        scheme = url.scheme.lower().split("+")[0]  # postgresql+asyncpg -> postgresql
        db_type = SCHEME_TO_TYPE.get(scheme)
        if db_type and url.hostname: # тип базы известен  и хост удалось вытащить
            if db_type and url.hostname:
                db_name = url.path.strip("/") # поулчаем имя базы
            if not db_name: # если имя базы пустое
                if db_type == "redis":
                    db_name = "0"  # в Redis по умолчанию база номер 0
                else:
                    db_name = ""
            return {"host": url.hostname, "db_name": db_name, "db_type": db_type}
    # libpq-формат: "host=... port=... dbname=..."
    # Сюда функция попадает в трёх случаях: URL не найден, схема неизвестна или хост пустой.
    kv = dict(KV_RE.findall(value))
    if "host" in kv:
        return {"host": kv["host"], "db_name": kv.get("dbname", ""), "db_type": "postgres"}
 
    return None

def iter_env_values(pod_spec):
    """
    Вернуть список непустых строковых env-значений init-контейнеров
    (и основных контейнеров, если INCLUDE_MAIN_CONTAINERS = True).
    """
    containers = list(pod_spec.get("initContainers") or [])
    if INCLUDE_MAIN_CONTAINERS:
        containers += pod_spec.get("containers") or []
    values = []
    for container in containers:
        for env in container.get("env") or []:
            value = env.get("value")  # у valueFrom значения здесь нет
            """
            isinstance(value, str): value является строкой. Если переменная окружения задана через valueFrom (из секрета или ConfigMap), 
            ключа value у неё нет, и env.get("value") возвращает None. Такое значение отсекается, иначе регулярки в parse_connection упали бы с TypeError.
            and value: строка не пустая. Пустая строка "" в Python считается ложью, поэтому value: "" 
            тоже пропускается, разбирать в ней нечего.
            """
            if isinstance(value, str) and value:
                values.append(value)
    return values

def kubectl_json(*args):
    """Выполнить kubectl и вернуть распарсенный JSON. Падает, если kubectl вернул ошибку."""
    proc = subprocess.run(
        ["kubectl", *args, "-o", "json"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)

def get_db_list_deployment(namespaces):
    """Вернуть список записей {namespace, deployment, host, db_name, db_type}."""
    wanted = set(namespaces)    # делаем множество из списка
    records = []
    # получаем все деплойменты в кластере
    for dep in kubectl_json("get", "deployments", "-A").get("items", []):
        ns = dep["metadata"]["namespace"]
        if ns not in wanted:    # если наэмспейс не входит во множество wanted берём следующий деплоймент
            continue
        else:
            name = dep["metadata"]["name"]    # имя деплоймента
            pod_spec = dep["spec"]["template"]["spec"]    # секция spec пода
 
            seen = set()
            for value in iter_env_values(pod_spec): 
                conn = parse_connection(value)
                if not conn:
                    continue
                else:
                    key = (conn["host"], conn["db_name"], conn["db_type"])    # собираем кортеж 
                if key in seen:
                    continue
                else:
                    seen.add(key)
                    records.append({"namespace": ns, "deployment": name, **conn})    # **conn распаковывает словарь подключения, добавляя его ключи host, db_name и db_type на тот же уровень
                    #print(f"{ns}/{name}: {conn}")
 
    return records

def upload_to_influx(records):
    url = os.environ.get("INFLUXDB_URL", "http://influx.myjet.local:8086")
    token = os.environ["INFLUXDB_TOKEN"]
    org = os.environ.get("INFLUXDB_ORG", "123")
    bucket = os.environ.get("INFLUXDB_BUCKET", "service-db")

    now = time.time_ns()    # одно время на весь запуск
    points = []
    for r in records:
        point = (
            Point("db_access")
            .tag("deployment", r["deployment"])
            .tag("db_type", r["db_type"])
            .tag("db_host", r["host"])
            .tag("db_name", r["db_name"])
            .field("present", 1)    # поле обязательно, сами данные лежат в тегах
            .time(now)
        )
        points.append(point)

    with InfluxDBClient(url=url, token=token, org=org) as client:
        client.write_api(write_options=SYNCHRONOUS).write(bucket=bucket, record=points)

if __name__ == "__main__":
    print("START")
    namespaces = get_namespaces_list()
    records = get_db_list_deployment(namespaces)
    print(namespaces)
    for i in records:
        print(f"{i['deployment']}: host={i['host']} db={i['db_name']} type={i['db_type']}")
    upload_to_influx(records)

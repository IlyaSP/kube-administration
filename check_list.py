import os
import re
import subprocess
import json
import datetime
from uptime_kuma_api import UptimeKumaApi, MonitorType
#from pyzabbix.api import ZabbixAPI
from zabbix_utils import ZabbixAPI

class bcolors:
    """ANSI-коды для раскраски вывода в терминале."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def get_deployments_list():
    '''Получить список всех деплойментов из всех namespace кластера (сырые объекты из kubectl).'''
    # TODO: kubectl вызывается через Popen с shell=True без проверки кода возврата.
    #  Если kubectl вернёт ошибку, json.loads упадёт с непонятным сообщением.
    #  Перейти на subprocess.run([...], check=True). То же в get_ingresses_list и get_nodes_list.
    # TODO: флаг -A стоит перед командой get. Проверить, что это работает в используемой
    #  версии kubectl, или переписать в привычном порядке: kubectl get deployments -A -o json.
    with subprocess.Popen(["kubectl get deployments -A -o json"],shell=True, stdout=subprocess.PIPE, text=True) as proc:
        raw_string = proc.stdout.read()
        tmp_full_deployments_json = json.loads(raw_string)
    full_deployments_list = tmp_full_deployments_json.get("items")
    return full_deployments_list

def get_deployments_without_limits(full_deployments_list):
    """Вывести предупреждение для каждого контейнера prod/rc-деплойментов, у которого не заданы resources.limits."""
    print(f"{bcolors.OKBLUE} Check prod app limits {bcolors.ENDC}")
    for deployment in full_deployments_list:
        containers = deployment.get("spec").get("template").get("spec").get("containers")
        deployment_name = deployment.get("metadata").get("name")
        # TODO: фильтр имён ^(prod|rc) отличается от ^(prod|rc)\- в get_deployments_without_probes.
        #  Разобраться, какой правильный, и использовать одинаковый в обеих проверках.
        if re.search(r'^(prod|rc)', deployment_name):
            for limits in containers:
                container_name = limits.get("name")
                #if len(limits.get("resources")) == 0:
                #    print(f"{bcolors.WARNING} The deployment {deployment_name} has no limits and requests {bcolors.ENDC}")
                # TODO: деплойменты собираются из всех namespace, а в сообщении namespace нет.
                #  Одноимённые деплойменты из разных namespace будут неотличимы. Добавить namespace в вывод.
                if limits.get("resources").get("limits") == None:
                    print(f"{bcolors.WARNING} The deployment {deployment_name} container {container_name} has no limits {bcolors.ENDC}")
                else:
                    continue
        else:
            continue

def get_deployments_without_probes(full_deployments_list):
    """Вывести предупреждение для prod/rc-деплойментов, у контейнеров которых нет livenessProbe или readinessProbe."""
    print(f"{bcolors.OKBLUE} Check prod app probes {bcolors.ENDC}")
    for deployment in full_deployments_list:
        containers = deployment.get("spec").get("template").get("spec").get("containers")
        deployment_name = deployment.get("metadata").get("name")
        if re.search(r'^(prod|rc)\-', deployment_name):
            for probe in containers:
                #print (deployment_name, probe.get("livenessProbe"))
                #print ("readinessProbe=== ", probe.get("readinessProbe"))
                # TODO: деплойменты собираются из всех namespace, а в сообщении namespace нет.
                #  Добавить namespace в вывод, как и в get_deployments_without_limits.
                container_name = probe.get("name")
                if probe.get("livenessProbe") == None:
                    #print (deployment_name, probe.get("livenessProbe"))
                    print(f"{bcolors.WARNING} The {deployment_name} container {container_name} has no LivenessProbe{bcolors.ENDC}")
                if probe.get("readinessProbe") == None:
                    print(f"{bcolors.WARNING} The {deployment_name} container {container_name} has no ReadinessProbe{bcolors.ENDC}")
        else:
            continue
def get_ingresses_list():
    '''Получить список всех ингрессов из всех namespace кластера (сырые объекты из kubectl).'''
    with subprocess.Popen(["kubectl get ingresses -A -o json"], shell=True, stdout=subprocess.PIPE, text=True) as proc:
        raw_string = proc.stdout.read()
        tmp_full_ingresses_json = json.loads(raw_string)
    full_ingresses_list = tmp_full_ingresses_json.get("items")
    return full_ingresses_list

def get_hosts_from_ingress(full_ingresses_list):
    """Вернуть множество доменных имён из ингрессов, чьё имя начинается с prod-."""
    hosts = []
    for i in full_ingresses_list:
        ingress_name = i.get("metadata").get("name")
        if re.search(r'^prod\-', ingress_name):
            #print(i.get("spec").get("rules")[0].get("host"))
            # TODO: из ингресса берётся только первый хост (rules[0]). Если в ингрессе
            #  несколько правил с разными доменами, остальные не проверяются.
            #  Нужно перебирать все rules.
            host = i.get("spec").get("rules")[0].get("host")
            hosts.append(host)
    return set(hosts)
def get_hosts_from_kuma(kuma_user, kuma_passwd):
    """Залогиниться в Uptime Kuma и вернуть множество хостов из URL мониторов на доменах office.myjet.tech и mysky.com."""
    # print("KUMA")
    with UptimeKumaApi('https://health.office.myjet.tech') as api:
        try:
            api.login(kuma_user, kuma_passwd)
        except Exception as e:
            # TODO: Kuma может уронить скрипт. При ошибке логина исключение только печатается,
            #  и скрипт падает дальше на get_monitors(). Нужно прерывать выполнение
            #  с понятным сообщением или пропускать проверку Kuma.
            print(e)
        # print(api)
        monitors = api.get_monitors()

    hosts_kuma = []
    # TODO: непонятное !? в начале регулярки, похоже на опечатку. Строка не raw (r"..."),
    #  из-за чего Python выдаёт SyntaxWarning про \/. Точки в доменах не экранированы.
    url_pattern = "!?^https?:\/\/(.*(office.myjet.tech|mysky.com))"
    for monitor in monitors:
        # TODO: Kuma может уронить скрипт. У мониторов не HTTP-типа (ping, TCP, DNS)
        #  url бывает None, и re.search упадёт с TypeError. Нужно пропускать такие мониторы.
        if re.search(url_pattern, monitor.get("url")) != None:
            # print(re.search(url_pattern, monitor.get("url")).group(1))
            host = re.search(url_pattern, monitor.get("url")).group(1)
            hosts_kuma.append(host)
    # print(monitor.get("name"), monitor.get("id"), monitor.get("url"))
    # print(len(hosts_kuma))
    # print(hosts_kuma)
    return set(hosts_kuma)
def check_kuma_monotiring(hosts, hosts_kuma):
    """Сравнить хосты из ингрессов с хостами в Kuma и вывести те, что не стоят на мониторинге."""
    print(f"{bcolors.OKBLUE} Check prod ingress and kuma {bcolors.ENDC}")
    hosts_no_monitoring = hosts - hosts_kuma
    # print(hosts_no_monitoring)
    # print(len(hosts_no_monitoring))
    if len(hosts_no_monitoring) != 0:
        for host in hosts_no_monitoring:
            print(f"{bcolors.WARNING} The {host} is not present in the Kuma {bcolors.ENDC}")
    else:
        print(f"{bcolors.OKCYAN} All prod hosts are present in monitoring {bcolors.ENDC}")

def get_nodes_list():
    '''Вернуть список коротких имён (до первой точки) всех нод кластера.'''
    with subprocess.Popen(["kubectl get nodes -o json"],shell=True, stdout=subprocess.PIPE, text=True) as proc:
        raw_string = proc.stdout.read()
        tmp_full_nodes_json = json.loads(raw_string)
    full_nodes_list_json = tmp_full_nodes_json.get("items")
    full_nodes_list = []
    for item in full_nodes_list_json:
        if item.get("kind") == "Node":
            node_name = item.get("metadata").get("name").split(".")[0]
            full_nodes_list.append(node_name)
    return full_nodes_list

def get_nodes_list_zabbix(zabbix_user, zabbix_passwd):
    '''Вернуть короткие имена хостов aws-east1-prod-kub-* из группы "Discovered hosts" в Zabbix.'''
    with ZabbixAPI(url='https://zabbix.myjet.tech/', user=zabbix_user, password=zabbix_passwd) as zapi:
        #answer = zapi.do_request('apiinfo.version')
        #print("Version:", answer['result'])
        groups = zapi.hostgroup.get(output=['groupid', 'name'])    # get list all groups
        # TODO: если группа "Discovered hosts" не найдена, group_id не будет определена,
        #  и zapi.host.get упадёт с NameError. Нужно явно обработать этот случай.
        for group in groups:
            #print (group['groupid'], group['name'])
            if re.search(r'Discovered hosts', group["name"]):
                group_id = group['groupid']
                #print (group_id)
                break
            else:
                continue
        hosts_in_group = zapi.host.get(groupids=group_id, output=['hostid', 'name'])    # get list all hosts in group
    #print(hosts_in_group)
    kube_nodes = []
    for host in hosts_in_group:
        if re.search(r'aws-east1-prod-kub-\w+', host.get("name")):
            host_kube = host.get("name").split(".")[0]
            kube_nodes.append(host_kube)
    #print(kube_nodes)
    return kube_nodes
def check_nodes_zabbix_monitoring(full_nodes_list, kube_nodes_zabbix):
    """Сравнить ноды кластера с хостами в Zabbix и вывести ноды, которые не добавлены в Zabbix."""
    print(f"{bcolors.OKBLUE} Check zabbix {bcolors.ENDC}")
    check_result = set(full_nodes_list) - set(kube_nodes_zabbix)
    #print(check_result)
    if len(check_result) != 0:
        for node in check_result:
            print(f"{bcolors.FAIL} The node {node} has not been added to Zabbix {bcolors.ENDC}")
    else:
        print(f"{bcolors.OKCYAN} All prod cluster nodes added to zabbix {bcolors.ENDC}")

if __name__ == "__main__":
    print("START")
    full_deployments_list = get_deployments_list()
    #print(full_deployments_list)
    get_deployments_without_limits(full_deployments_list)
    get_deployments_without_probes(full_deployments_list)
    full_ingresses_list = get_ingresses_list()
    hosts = get_hosts_from_ingress(full_ingresses_list)
    kuma_user = os.getenv("KUMA_USER")
    kuma_passwd = os.getenv("KUMA_PASSWD")
    hosts_kuma = get_hosts_from_kuma(kuma_user, kuma_passwd)
    check_kuma_monotiring(hosts,hosts_kuma)
    full_nodes_list = get_nodes_list()
    zabbix_user = os.getenv("ZABBIX_USER")
    zabbix_passwd = os.getenv("ZABBIX_PASSWD")
    kube_nodes_zabbix = get_nodes_list_zabbix(zabbix_user, zabbix_passwd)
    check_nodes_zabbix_monitoring(full_nodes_list, kube_nodes_zabbix)

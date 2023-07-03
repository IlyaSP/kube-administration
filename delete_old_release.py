import os
import re
import subprocess
import json
import datetime

def get_release_list():
    '''get all helm releases in kubernetes cluster'''
    with subprocess.Popen(["helm -n default list -a -o json"],shell=True, stdout=subprocess.PIPE, text=True) as proc:
        raw_string = proc.stdout.read()
        list_json = json.loads(raw_string)
    return list_json

def get_date_deploy_release(list_json):
    '''create dict wich name helm release and data deploy'''
    release_and_date = {}
    for i in list_json:
        date_str = i["updated"].split(" ")[0]
        date_deploy = datetime.datetime.strptime(date_str, '%Y-%m-%d')
        release_and_date[i["name"]] = date_deploy
    return release_and_date

def delete_old_release(release_and_date):
    '''removes helm releases older than seven days '''
    date_now = datetime.datetime.now()
    for name,date_deploy in release_and_date.items():
        if re.search(r'^((?!stage).)*\-tax\-', name):
            age_release = date_now-date_deploy
            if age_release.days >= 7 :
                print(name, age_release.days)
                cmd = "helm -n default uninstall {0}".format(name)
                print(cmd)
                try:
                   with subprocess.Popen([cmd],shell=True, stdout=subprocess.PIPE, text=True) as proc:
                       print(proc.stdout.read())
                except Exception as e:
                   print(e)

if __name__ == "__main__":
    print("START")
    list_json = get_release_list()
    #print(list_json)
    release_and_date = get_date_deploy_release(list_json)
    #print(release_and_date)
    delete_old_release(release_and_date)

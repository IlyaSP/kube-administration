import sys
import json
import ruamel.yaml
import os

yaml = ruamel.yaml.YAML()
yaml.preserve_quotes = True

test=os.getenv("VARIABLES")
print(test)
json_param='{"configMap":[{"AUTH_COOKIE_NAME":"stage_auth","OFFLOADING_TOKEN":"test_token"}],"interConnections":[{"BUCKET_NAME":"files-storage","FRONT_URL":"https://${stand_name}.office","HOST":"https://api-${stand_name}.office","INTEGRATIONS_URL":"https://dev-int.office","LEDGER_API_URL":"https://api-stage.office/api","FINICITY_KEY":"77777","FINICITY_REDIRECT_URI":"https://api-${stand_name}.office/finicity","OFFLOADING_API_URL":"https://api-stage-loader.office","ANALYTICS_API_URL":"https://api-stage.office","FINDOCS_API_URL":"https://stage-office.office"}],"dbDSN":[{"envName":"DSN","name":"office","user":"dev","password":"PASS","host":"db-dev01","port":5432},{"envName":"RO_DSN","name":"dev1","user":"dev","password":"PASS","host":"db-dev01","port":5432},{"envName":"DSN","name":"dev1_list","user":"dev","password":"DSN","host":"db-dev01","port":5432}],"redisDSN":[{"envName":"URL","password":"PASSWORD","host":"redis-1"}]}'
print(json.loads(json_param))
json_param_dict = json.loads(json_param)
path_yaml="./test.yaml"
#================================== show input dictionary =============================================
for keys,values in json_param_dict.items():
    print("{0} -- {1}".format(keys, values))

#====================== Заполнение параметров из json (Filling parameters from json)===============================
json_param_interConnections=json_param_dict.get("interConnections")
json_param_configMap=json_param_dict.get("configMap")
print("json", json_param_configMap)
json_param_observability=json_param_dict.get("observability")
json_param_dbDSN=json_param_dict.get("dbDSN")
json_param_redisDSN=json_param_dict.get("redisDSN")

#============================== проверка корректности данных для конфигмапа (checking the correctness of the data for the configmap) ====================================

if json_param_interConnections != 'None':
    if (type(json_param_interConnections) is list and len(json_param_interConnections) == 1):
        json_param_interConnections=json_param_interConnections[0]
    elif (type(json_param_interConnections) is list and len(json_param_interConnections) != 1):
        sys.exit("incorrect number of parameters in interConnections")

if json_param_configMap != 'None':
    if (type(json_param_configMap) is list and len(json_param_configMap) == 1):
        json_param_configMap=json_param_configMap[0]
    elif (type(json_param_configMap) is list and len(json_param_configMap) != 1):
        sys.exit("incorrect number of parameters in configMap")

if json_param_observability != 'None':
    if (type(json_param_observability) is list and len(json_param_observability) == 1):
        json_param_observability=json_param_observability[0]
    elif (type(json_param_observability) is list and len(json_param_observability) != 1):
        sys.exit("incorrect number of parameters in observability")

#====================== Заполнение параметров из yaml (Filling parameters from yaml)===============================

with open(path_yaml) as yaml_file:
    yaml_param_dict = yaml.load(yaml_file)

#print(yaml_param_dict["interConnections"])

yaml_param_interConnections=yaml_param_dict.get('interConnections')
yaml_param_configMap=yaml_param_dict.get('configMap')
yaml_param_observability=yaml_param_dict.get('observability')
yaml_param_dbDSN=yaml_param_dict.get('dbDSN')
yaml_param_redisDSN=yaml_param_dict.get('redisDSN')

#================================= создание/иземенение секции configMap (creating/changing the configMap section)===============

if (yaml_param_configMap == None and json_param_configMap != None):
    yaml_param_dict.insert(1, 'configMap', json_param_configMap)
elif (yaml_param_configMap != None and json_param_configMap != None):
    for keys,values in json_param_configMap.items():
        if keys in yaml_param_configMap:
            yaml_param_configMap[keys] = values
        else:
            yaml_param_configMap[keys]=str(values)

#================================= создание/иземенение секции interConnections (creating/changing the interConnections section) ===============

if (yaml_param_interConnections == None and json_param_interConnections != None):
    yaml_param_dict.insert(1, 'interConnections', json_param_interConnections)
elif (yaml_param_interConnections != None and json_param_interConnections != None):
    for keys,values in json_param_interConnections.items():
        if keys in yaml_param_interConnections:
            yaml_param_interConnections[keys] = values
        else:
            yaml_param_interConnections[keys]=str(values)

#================================= создание/иземенение секции observability (creating/changing the observability section)===============

if (yaml_param_observability == None and json_param_observability != None):
    yaml_param_dict.insert(1, 'observability', json_param_observability)
elif (yaml_param_observability != None and json_param_observability != None):
    for keys,values in json_param_observability.items():
        if keys in yaml_param_observability:
            yaml_param_observability[keys] = values
        else:
            yaml_param_observability[keys]=str(values)

#================================= создание/иземенение секции dbDSN (creating/changing the dbDSN section)===============

if (yaml_param_dbDSN == None and json_param_dbDSN != None):
    yaml_param_dict.insert(1, 'dbDSN', json_param_dbDSN)
elif (yaml_param_dbDSN != None and json_param_dbDSN != None):
    tmp_list=[]
    for yaml_db_connect in yaml_param_dbDSN:
      tmp_dict = {}
      for yaml_key,yaml_value in yaml_db_connect.items():
          tmp_dict[yaml_key] = yaml_value
      tmp_list.append(tmp_dict)
    yaml_list = []
    for json_db_connect in json_param_dbDSN:
        for yaml_db_connect in tmp_list:
            if yaml_db_connect.get("envName") == json_db_connect.get("envName"):
                for json_key,json_value in json_db_connect.items():
                    yaml_db_connect[json_key] = json_value
                yaml_list.append(yaml_db_connect)
                tmp_list.remove(yaml_db_connect)
                json_param_dbDSN.remove(json_db_connect)
    new_yaml_param_db = tmp_list + json_param_dbDSN + yaml_list
    yaml_param_dict["dbDSN"] = new_yaml_param_db

#================================= создание/иземенение секции redisDSN (creating/changing the redisDSN section)===============

if (yaml_param_redisDSN == None and json_param_redisDSN != None):
    yaml_param_dict.insert(1, 'redisDSN', json_param_redisDSN)
elif (yaml_param_redisDSN != None and json_param_redisDSN != None):
    tmp_list=[]
    for yaml_db_connect in yaml_param_redisDSN:
      tmp_dict = {}
      for yaml_key,yaml_value in yaml_db_connect.items():
          tmp_dict[yaml_key] = yaml_value
      tmp_list.append(tmp_dict)
    yaml_list = []
    for json_db_connect in json_param_redisDSN:
        for yaml_db_connect in tmp_list:
            if yaml_db_connect.get("envName") == json_db_connect.get("envName"):
                for json_key,json_value in json_db_connect.items():
                    yaml_db_connect[json_key] = json_value
                yaml_list.append(yaml_db_connect)
                tmp_list.remove(yaml_db_connect)
                json_param_redisDSN.remove(json_db_connect)
    new_yaml_param_db = tmp_list + json_param_redisDSN + yaml_list
    yaml_param_dict["redisDSN"] = new_yaml_param_db

#================== output of the resulting config =============================
ruamel.yaml.round_trip_dump(yaml_param_dict, sys.stdout, )

#================== writing the result to a file ===============================
with open("data.yaml", "w") as f:
    ruamel.yaml.round_trip_dump(yaml_param_dict, f)

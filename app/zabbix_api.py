# app/zabbix_api.py
import requests
import json
import time
import logging

def fazer_request_zabbix(body, zabbix_url, allow_retry=True):
    headers = {'Content-Type': 'application/json-rpc', 'Accept-Encoding': 'gzip'}
    max_retries = 2 if allow_retry else 1
    for attempt in range(max_retries):
        try:
            response = requests.post(zabbix_url, headers=headers, data=json.dumps(body), timeout=120)
            # response = requests.post(zabbix_url, headers=headers, data=json.dumps(body), verify=False, timeout=120)
            if response.status_code >= 500 and attempt < max_retries - 1:
                logging.warning(f"Servidor Zabbix retornou erro {response.status_code}. Tentando novamente...")
                time.sleep(5)
                continue
            response.raise_for_status()
            response_json = response.json()
            if 'result' in response_json:
                return response_json['result']
            elif 'error' in response_json:
                error_details = f"{response_json['error']['message']}: {response_json['error']['data']}"
                logging.error(f"ERRO API Zabbix: {error_details}")
                return {'error': 'APIError', 'details': error_details}
            return []
        except requests.exceptions.RequestException as e:
            logging.error(f"ERRO DE CONEXÃO: Falha ao conectar com a API do Zabbix: {e}")
            return {'error': 'RequestException', 'details': str(e)}
    return None

def obter_config_e_token_zabbix(app_config, task_id="generic_task"):
    is_threaded_task = task_id != "generic_task"
    if is_threaded_task:
        # A função update_status não está neste arquivo, então remova a chamada.
        # update_status(task_id, "Conectando ao Zabbix...")
        pass

    config_zabbix = {
        'ZABBIX_URL': app_config['ZABBIX_URL'],
        'ZABBIX_USER': app_config['ZABBIX_USER'],
        'ZABBIX_PASSWORD': app_config['ZABBIX_PASSWORD'],
        'ZABBIX_TOKEN': app_config.get('ZABBIX_TOKEN')
    }
    if not all([config_zabbix['ZABBIX_URL'], config_zabbix['ZABBIX_USER'], config_zabbix['ZABBIX_PASSWORD']]):
        return None, "Variáveis de ambiente do Zabbix (URL, USER, PASSWORD) não configuradas."

    if not config_zabbix.get('ZABBIX_TOKEN'):
        body = {'jsonrpc': '2.0', 'method': 'user.login', 'params': {'username': config_zabbix['ZABBIX_USER'], 'password': config_zabbix['ZABBIX_PASSWORD']}, 'id': 1}
        token_response = fazer_request_zabbix(body, config_zabbix['ZABBIX_URL'])
        if token_response and 'error' not in token_response:
            config_zabbix['ZABBIX_TOKEN'] = token_response
            if is_threaded_task:
                # Remova a chamada para a função update_status, pois ela não pertence a este módulo
                pass
        else:
            details = token_response.get('details', 'N/A') if isinstance(token_response, dict) else 'Erro desconhecido'
            return None, f"Falha no login do Zabbix. Verifique as credenciais. Detalhes: {details}"

    return config_zabbix, None

def get_host_groups(config, url):
    """
    Busca todos os grupos de hosts disponíveis no Zabbix.
    """
    body = {
        "jsonrpc": "2.0",
        "method": "hostgroup.get",
        "params": {
            "output": ["groupid", "name"],
            "sortfield": "name"
        },
        "auth": config['ZABBIX_TOKEN'],
        "id": 1
    }
    response = fazer_request_zabbix(body, url)
    if isinstance(response, list):
        return response
    # Retorna lista vazia em caso de erro ou resposta inesperada
    return []
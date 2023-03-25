import requests
import logging
from modules.presets import timeout_all, BALANCE_API_URL,standard_error_msg,connection_timeout_prompt,error_retrieve_prompt,read_timeout_prompt
from modules import shared
import os


def get_usage_response(openai_api_key):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}",
    }

    timeout = timeout_all

    # 获取环境变量中的代理设置
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get(
        "HTTPS_PROXY") or os.environ.get("https_proxy")

    # 如果存在代理设置，使用它们
    proxies = {}
    if http_proxy:
        logging.info(f"使用 HTTP 代理: {http_proxy}")
        proxies["http"] = http_proxy
    if https_proxy:
        logging.info(f"使用 HTTPS 代理: {https_proxy}")
        proxies["https"] = https_proxy

    # 如果有代理，使用代理发送请求，否则使用默认设置发送请求
    """
    暂不支持修改
    if shared.state.balance_api_url != BALANCE_API_URL:
        logging.info(f"使用自定义BALANCE API URL: {shared.state.balance_api_url}")
    """
    if proxies:
        response = requests.get(
            BALANCE_API_URL,
            headers=headers,
            timeout=timeout,
            proxies=proxies,
        )
    else:
        response = requests.get(
            BALANCE_API_URL,
            headers=headers,
            timeout=timeout,
        )
    return response

def get_usage(openai_api_key):
    try:
        response=get_usage_response(openai_api_key=openai_api_key)
        logging.debug(response.json())
        try:
            balance = response.json().get("total_available") if response.json().get(
                "total_available") else 0
            total_used = response.json().get("total_used") if response.json().get(
                "total_used") else 0
        except Exception as e:
            logging.error(f"API使用情况解析失败:"+str(e))
            balance = 0
            total_used=0
        return f"**API使用情况**（已用/余额）\u3000{total_used}$ / {balance}$"
    except requests.exceptions.ConnectTimeout:
        status_text = standard_error_msg + connection_timeout_prompt + error_retrieve_prompt
        return status_text
    except requests.exceptions.ReadTimeout:
        status_text = standard_error_msg + read_timeout_prompt + error_retrieve_prompt
        return status_text

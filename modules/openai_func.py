import requests
import logging
from modules.presets import timeout_all, BALANCE_API_URL,standard_error_msg,connection_timeout_prompt,error_retrieve_prompt,read_timeout_prompt
from modules import shared
from modules.utils import get_proxies
import os


def get_usage_response(openai_api_key):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}",
    }

    timeout = timeout_all

    proxies = get_proxies()
    """
    暂不支持修改
    if shared.state.balance_api_url != BALANCE_API_URL:
        logging.info(f"使用自定义BALANCE API URL: {shared.state.balance_api_url}")
    """
    response = requests.get(
        BALANCE_API_URL,
        headers=headers,
        timeout=timeout,
        proxies=proxies,
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
    except Exception as e:
        logging.error(f"获取API使用情况失败:"+str(e))
        return standard_error_msg + error_retrieve_prompt

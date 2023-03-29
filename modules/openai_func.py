import requests
import logging
from modules.presets import (
    timeout_all,
    USAGE_API_URL,
    BALANCE_API_URL,
    standard_error_msg,
    connection_timeout_prompt,
    error_retrieve_prompt,
    read_timeout_prompt
)

from modules import shared
from modules.utils import get_proxies
import os
from datetime import datetime, timedelta

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
        return f"**API免费额度使用情况**（已用/余额）\u3000${total_used} / ${balance}"
    except requests.exceptions.ConnectTimeout:
        status_text = standard_error_msg + connection_timeout_prompt + error_retrieve_prompt
        return status_text
    except requests.exceptions.ReadTimeout:
        status_text = standard_error_msg + read_timeout_prompt + error_retrieve_prompt
        return status_text
    except Exception as e:
        logging.error(f"获取API使用情况失败:"+str(e))
        return standard_error_msg + error_retrieve_prompt

def get_usage_for_current_month_response(openai_api_key):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}",
    }

    timeout = timeout_all
    today = datetime.today()
    first_day_of_month = today.replace(day=1).date()
    last_day_of_month = get_last_day_of_month(today).date()
    
    proxies = get_proxies()
    response = requests.get(
        f"{USAGE_API_URL}?start_date={first_day_of_month}&end_date={last_day_of_month}",
        headers=headers,
        timeout=timeout,
        proxies=proxies,
    )
        
    return response

def get_dollar_usage_for_current_month(openai_api_key):
    try:
        response=get_usage_for_current_month_response(openai_api_key=openai_api_key)
        usage = 0
        upper_limit = "120" # hardcoded as 120 dollars for now
        try:
            usage = round(response.json().get("total_usage")/100, 2) if response.json().get(
                "total_usage") else 0
        except Exception as e:
            logging.error(f"API使用情况解析失败:"+str(e))
        return f"**本月API使用情况**（已用/限额）\u3000${usage} / ${upper_limit}"
    except requests.exceptions.ConnectTimeout:
        status_text = standard_error_msg + connection_timeout_prompt + error_retrieve_prompt
        return status_text
    except requests.exceptions.ReadTimeout:
        status_text = standard_error_msg + read_timeout_prompt + error_retrieve_prompt
        return status_text
    except Exception as e:
        logging.error(f"获取API使用情况失败:"+str(e))
        return standard_error_msg + error_retrieve_prompt
    
def get_last_day_of_month(any_day):
    # The day 28 exists in every month. 4 days later, it's always next month
    next_month = any_day.replace(day=28) + timedelta(days=4)
    # subtracting the number of the current day brings us back one month
    return next_month - timedelta(days=next_month.day)
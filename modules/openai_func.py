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

from . import shared
from modules.config import retrieve_proxy
import os, datetime

def get_billing_data(openai_api_key, billing_url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}"
    }
    
    timeout = timeout_all
    with retrieve_proxy():
        response = requests.get(
            billing_url,
            headers=headers,
            timeout=timeout,
        )
    
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
    

def get_usage(openai_api_key):
    try:
        balance_data=get_billing_data(openai_api_key, shared.state.balance_api_url)
        logging.debug(balance_data)
        try:
            balance = balance_data["total_available"] if balance_data["total_available"] else 0
            total_used = balance_data["total_used"] if balance_data["total_used"] else 0
            usage_percent = round(total_used / (total_used+balance) * 100, 2) if balance > 0 else 0
        except Exception as e:
            logging.error(f"API使用情况解析失败:"+str(e))
            balance = 0
            total_used=0
            return f"**API使用情况解析失败**"
        if balance == 0:
            curr_time = datetime.datetime.now()
            last_day_of_month = get_last_day_of_month(curr_time).strftime("%Y-%m-%d")
            first_day_of_month = curr_time.replace(day=1).strftime("%Y-%m-%d")
            usage_url = f"{shared.state.usage_api_url}?start_date={first_day_of_month}&end_date={last_day_of_month}"
            try:
                usage_data = get_billing_data(openai_api_key, usage_url)
            except Exception as e:
                logging.error(f"获取API使用情况失败:"+str(e))
                return f"**获取API使用情况失败**"
            usage_rounded = round(usage_data['total_usage'] / 100, 2)
            return f"**本月使用金额** \u3000 ${usage_rounded}"
        
        # return f"**免费额度**（已用/余额）\u3000${total_used} / ${balance}"
        return f"""\
        <b>免费额度使用情况</b>
        <div class="progress-bar">
            <div class="progress" style="width: {usage_percent}%;">
                <span class="progress-text">{usage_percent}%</span>
            </div>
        </div>
        <div style="display: flex; justify-content: space-between;"><span>已用 ${total_used}</span><span>可用 ${balance}</span></div>
        """
    
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
    next_month = any_day.replace(day=28) + datetime.timedelta(days=4)
    # subtracting the number of the current day brings us back one month
    return next_month - datetime.timedelta(days=next_month.day)
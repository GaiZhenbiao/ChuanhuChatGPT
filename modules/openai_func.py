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
        curr_time = datetime.datetime.now()
        last_day_of_month = get_last_day_of_month(curr_time).strftime("%Y-%m-%d")
        first_day_of_month = curr_time.replace(day=1).strftime("%Y-%m-%d")
        usage_url = f"{shared.state.usage_api_url}?start_date={first_day_of_month}&end_date={last_day_of_month}"
        try:
            usage_data = get_billing_data(openai_api_key, usage_url)
        except Exception as e:
            logging.error(f"获取API使用情况失败:"+str(e))
            return f"**获取API使用情况失败**"
        rounded_usage = "{:.5f}".format(usage_data['total_usage']/100)
        return f"**本月使用金额** \u3000 ${rounded_usage}"
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
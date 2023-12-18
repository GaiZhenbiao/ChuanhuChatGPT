import os
import logging
import traceback

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
import gradio as gr
import ujson as json
import commentjson
import openpyxl

import modules.presets as presets
from modules.utils import get_file_hash, count_token
from modules.presets import i18n

def excel_to_jsonl(filepath, preview=False):
    # 打开Excel文件
    workbook = openpyxl.load_workbook(filepath)

    # 获取第一个工作表
    sheet = workbook.active

    # 获取所有行数据
    data = []
    for row in sheet.iter_rows(values_only=True):
        data.append(row)

    # 构建字典列表
    headers = data[0]
    jsonl = []
    for row in data[1:]:
        row_data = dict(zip(headers, row))
        if any(row_data.values()):
            jsonl.append(row_data)
    formatted_jsonl = []
    for i in jsonl:
            if "提问" in i and "答案" in i:
                if "系统" in i :
                    formatted_jsonl.append({
                        "messages":[
                            {"role": "system", "content": i["系统"]},
                            {"role": "user", "content": i["提问"]},
                            {"role": "assistant", "content": i["答案"]}
                        ]
                    })
                else:
                    formatted_jsonl.append({
                        "messages":[
                            {"role": "user", "content": i["提问"]},
                            {"role": "assistant", "content": i["答案"]}
                        ]
                    })
            else:
                logging.warning(f"跳过一行数据，因为没有找到提问和答案: {i}")
    return formatted_jsonl

def jsonl_save_to_disk(jsonl, filepath):
    file_hash = get_file_hash(file_paths = [filepath])
    os.makedirs("files", exist_ok=True)
    save_path = f"files/{file_hash}.jsonl"
    with open(save_path, "w") as f:
        f.write("\n".join([json.dumps(i, ensure_ascii=False) for i in jsonl]))
    return save_path

def estimate_cost(ds):
    dialogues = []
    for l in ds:
        for m in l["messages"]:
            dialogues.append(m["content"])
    dialogues = "\n".join(dialogues)
    tokens = count_token(dialogues)
    return f"Token 数约为 {tokens}，预估每轮（epoch）费用约为 {tokens / 1000 * 0.008} 美元。"


def handle_dataset_selection(file_src):
    logging.info(f"Loading dataset {file_src.name}...")
    preview = ""
    if file_src.name.endswith(".jsonl"):
        with open(file_src.name, "r") as f:
            ds = [json.loads(l) for l in f.readlines()]
    else:
        ds = excel_to_jsonl(file_src.name)
    preview = ds[0]

    return preview, gr.update(interactive=True), estimate_cost(ds)

def upload_to_openai(file_src):
    dspath = file_src.name
    msg = ""
    logging.info(f"Uploading dataset {dspath}...")
    if dspath.endswith(".xlsx"):
        jsonl = excel_to_jsonl(dspath)
        dspath = jsonl_save_to_disk(jsonl, dspath)
    try:
        uploaded = client.files.create(file=open(dspath, "rb"),
        purpose='fine-tune')
        return uploaded.id, f"上传成功"
    except Exception as e:
        traceback.print_exc()
        return "", f"上传失败，原因：{ e }"

def build_event_description(id, status, trained_tokens, name=i18n("暂时未知")):
    # convert to markdown
    return f"""
    #### 训练任务 {id}

    模型名称：{name}

    状态：{status}

    已经训练了 {trained_tokens} 个token
    """

def start_training(file_id, suffix, epochs):
    try:
        job = client.fine_tuning.jobs.create(training_file=file_id, model="gpt-3.5-turbo", suffix=suffix, hyperparameters={"n_epochs": epochs})
        return build_event_description(job.id, job.status, job.trained_tokens)
    except Exception as e:
        traceback.print_exc()
        if "is not ready" in str(e):
            return "训练出错，因为文件还没准备好。OpenAI 需要一点时间准备文件，过几分钟再来试试。"
        return f"训练失败，原因：{ e }"

def get_training_status():
    active_jobs = [build_event_description(job.id, job.status, job.trained_tokens, job.fine_tuned_model) for job in client.fine_tuning.jobs.list().data if job.status != "cancelled"]
    return "\n\n".join(active_jobs), gr.update(interactive=True) if len(active_jobs) > 0 else gr.update(interactive=False)

def handle_dataset_clear():
    return gr.update(value=None), gr.update(interactive=False)

def add_to_models():
    succeeded_jobs = [job for job in client.fine_tuning.jobs.list().data if job.status == "succeeded"]
    extra_models = [job.fine_tuned_model for job in succeeded_jobs]
    for i in extra_models:
        if i not in presets.MODELS:
            presets.MODELS.append(i)

    with open('config.json', 'r') as f:
        data = commentjson.load(f)
    if 'extra_models' in data:
        for i in extra_models:
            if i not in data['extra_models']:
                data['extra_models'].append(i)
    else:
        data['extra_models'] = extra_models
    with open('config.json', 'w') as f:
        commentjson.dump(data, f, indent=4)

    return gr.update(choices=presets.MODELS), f"成功添加了 {len(succeeded_jobs)} 个模型。"

def cancel_all_jobs():
    jobs = [job for job in client.fine_tuning.jobs.list().data if job.status not in ["cancelled", "succeeded"]]
    for job in jobs:
        client.fine_tuning.jobs.cancel(job.id)
    return f"成功取消了 {len(jobs)} 个训练任务。"

import os
import logging
import traceback

import openai
import gradio as gr
import ujson as json

import modules.presets as presets
from modules.utils import get_file_hash
from modules.presets import i18n

def excel_to_jsonl(filepath, preview=False):
    jsonl = []
    with open(filepath, "rb") as f:
        import pandas as pd
        df = pd.read_excel(f)
        for row in df.iterrows():
            jsonl.append(row[1].to_dict())
            if preview:
                break
    return jsonl

def jsonl_save_to_disk(jsonl, filepath):
    file_hash = get_file_hash(file_paths = [filepath])
    os.makedirs("files", exist_ok=True)
    save_path = f"files/{file_hash}.jsonl"
    with open(save_path, "w") as f:
        f.write("\n".join([json.dumps(i, ensure_ascii=False) for i in jsonl]))
    return save_path

def handle_dataset_selection(file_src):
    logging.info(f"Loading dataset {file_src.name}...")
    preview = ""
    if file_src.name.endswith(".jsonl"):
        with open(file_src.name, "r") as f:
            preview = f.readline()
    else:
        preview = excel_to_jsonl(file_src.name)[0]
    return preview, gr.update(interactive=True), "预估数据集 token 数量: 这个功能还没实现"

def upload_to_openai(file_src):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    dspath = file_src.name
    msg = ""
    logging.info(f"Uploading dataset {dspath}...")
    if dspath.endswith(".xlsx"):
        jsonl = excel_to_jsonl(dspath)
        tmp_jsonl = []
        for i in jsonl:
            if "提问" in i and "答案" in i:
                if "系统" in i :
                    tmp_jsonl.append({
                        "messages":[
                            {"role": "system", "content": i["系统"]},
                            {"role": "user", "content": i["提问"]},
                            {"role": "assistant", "content": i["答案"]}
                        ]
                    })
                else:
                    tmp_jsonl.append({
                        "messages":[
                            {"role": "user", "content": i["提问"]},
                            {"role": "assistant", "content": i["答案"]}
                        ]
                    })
            else:
                logging.warning(f"跳过一行数据，因为没有找到提问和答案: {i}")
        jsonl = tmp_jsonl
        dspath = jsonl_save_to_disk(jsonl, dspath)
    try:
        uploaded = openai.File.create(
            file=open(dspath, "rb"),
            purpose='fine-tune'
            )
        return uploaded.id, f"上传成功，文件ID: {uploaded.id}"
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
    openai.api_key = os.getenv("OPENAI_API_KEY")
    try:
        job = openai.FineTuningJob.create(training_file=file_id, model="gpt-3.5-turbo", suffix=suffix, hyperparameters={"n_epochs": epochs})
        return build_event_description(job.id, job.status, job.trained_tokens)
    except Exception as e:
        traceback.print_exc()
        if "is not ready" in str(e):
            return "训练出错，因为文件还没准备好。OpenAI 需要一点时间准备文件，过几分钟再来试试。"
        return f"训练失败，原因：{ e }"

def get_training_status():
    openai.api_key = os.getenv("OPENAI_API_KEY")
    active_jobs = [build_event_description(job["id"], job["status"], job["trained_tokens"], job["fine_tuned_model"]) for job in openai.FineTuningJob.list(limit=10)["data"] if job["status"] != "cancelled"]
    return "\n\n".join(active_jobs), gr.update(interactive=True) if len(active_jobs) > 0 else gr.update(interactive=False)

def handle_dataset_clear():
    return gr.update(value=None), gr.update(interactive=False)

def add_to_models():
    openai.api_key = os.getenv("OPENAI_API_KEY")
    succeeded_jobs = [job for job in openai.FineTuningJob.list(limit=10)["data"] if job["status"] == "succeeded"]
    presets.MODELS.extend([job["fine_tuned_model"] for job in succeeded_jobs])
    return gr.update(choices=presets.MODELS), f"成功添加了 {len(succeeded_jobs)} 个模型。"
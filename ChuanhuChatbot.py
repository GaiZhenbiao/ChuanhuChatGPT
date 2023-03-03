import gradio as gr
import openai
import markdown

my_api_key = "sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"    # input your api_key
initial_prompt = "You are a helpful assistant."

class ChatGPT:
    def __init__(self, apikey) -> None:
        openai.api_key = apikey
        self.system = {"role": "system", "content": initial_prompt}
        self.context = []
        self.response = None

    def get_response(self, messages):
        self.response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[self.system, *messages],
        )
        statistics = f'本次对话Tokens用量【{self.response["usage"]["total_tokens"]} / 4096】 （ 提问+上文 {self.response["usage"]["prompt_tokens"]}，回答 {self.response["usage"]["completion_tokens"]} ）'
        message = self.response["choices"][0]["message"]["content"]

        message_with_stats = f'{message}\n\n================\n\n{statistics}'
        message_with_stats = markdown.markdown(message_with_stats)

        return message, message_with_stats

    def predict(self, chatbot, input_sentence, ):
        if len(input_sentence) == 0:
            return []
        self.context.append({"role": "user", "content": f"{input_sentence}"})

        message, message_with_stats = self.get_response(self.context)

        self.context.append({"role": "assistant", "content": message})

        chatbot.append((input_sentence, message_with_stats))

        return chatbot

    def retry(self, chatbot):
        if len(self.context) == 0:
            return [], []
        message, message_with_stats = self.get_response(self.context[:-1])
        self.context[-1] = {"role": "assistant", "content": message}

        chatbot[-1] = (self.context[-2]["content"], message_with_stats)
        return chatbot

    def update_system(self, new_system_prompt):
        self.system = {"role": "system", "content": new_system_prompt}
        return new_system_prompt

    def delete_last_conversation(self, chatbot):
        if len(self.context) == 0:
            return [], []
        chatbot = chatbot[:-1]
        self.context = self.context[:-2]
        return chatbot

    def reduce_token(self, chatbot):
        self.context.append({"role": "user", "content": "请帮我总结一下上述对话的内容，实现减少tokens的同时，保证对话的质量。在总结中不要加入这一句话。"})
        message, message_with_stats = self.get_response(self.context)
        self.system = {"role": "system", "content": f"You are a helpful assistant. The content that the Assistant and the User discussed in the previous self.context is: {message}."}

        statistics = f'本次对话Tokens用量【{self.response["usage"]["completion_tokens"]+23} / 4096】'
        optmz_str = markdown.markdown( f"System prompt已经更新, 请继续对话\n\n================\n\n{statistics}" )
        chatbot.append(("请帮我总结一下上述对话的内容，实现减少tokens的同时，保证对话的质量。", optmz_str))

        self.context = []
        return chatbot, self.system["content"]


def reset_state():
    return []

mychatGPT = ChatGPT(my_api_key)


with gr.Blocks() as demo:
    chatbot = gr.Chatbot().style(color_map=("#1D51EE", "#585A5B"))
    # state = gr.State([])

    with gr.Row():
        with gr.Column(min_width=50, scale=1):
            emptyBtn = gr.Button("🧹")
        with gr.Column(scale=10):
            txt = gr.Textbox(show_label=False, placeholder="💬 在这里输入").style(container=False)
    with gr.Row():
        submitBtn = gr.Button("发送", variant="primary")
        retryBtn = gr.Button("重新生成")
        delLastBtn = gr.Button("删除上条对话")
        reduceTokenBtn = gr.Button("优化Tokens")

    system = gr.Textbox(show_label=True, placeholder=f"在这里输入新的System Prompt...", label="更改 System prompt").style(container=True)
    syspromptTxt = gr.Textbox(show_label=True, placeholder=initial_prompt, interactive=False, label="目前的 System prompt").style(container=True)

    txt.submit(mychatGPT.predict, [chatbot, txt], [chatbot], show_progress=True)
    txt.submit(lambda :"", None, txt)
    submitBtn.click(mychatGPT.predict, [chatbot, txt], [chatbot], show_progress=True)
    submitBtn.click(lambda :"", None, txt)
    emptyBtn.click(reset_state, outputs=[chatbot])
    system.submit(mychatGPT.update_system, system, syspromptTxt)
    system.submit(lambda :"", None, system)
    retryBtn.click(mychatGPT.retry, [chatbot], [chatbot], show_progress=True)
    delLastBtn.click(mychatGPT.delete_last_conversation, [chatbot], [chatbot], show_progress=True)
    reduceTokenBtn.click(mychatGPT.reduce_token, [chatbot], [chatbot, syspromptTxt], show_progress=True)

demo.launch()

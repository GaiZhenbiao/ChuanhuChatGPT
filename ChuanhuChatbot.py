import gradio as gr
import openai
import markdown

my_api_key = "sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"    # input your api_key
initial_prompt = "You are a helpful assistant."

class ChatGPT:
    def __init__(self, apikey) -> None:
        openai.api_key = apikey
        self.system = {"role": "system", "content": initial_prompt}


    def get_response(self, messages):
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[self.system, *messages],
        )
        response = response["choices"][0]["message"]["content"]
        response = markdown.markdown(response)
        return response

    def predict(self, chatbot, input_sentence, context):
        if len(input_sentence) == 0:
            return [], context
        context.append({"role": "user", "content": f"{input_sentence}"})

        response = self.get_response(context)

        context.append({"role": "assistant", "content": response})

        chatbot.append((input_sentence, response))

        return chatbot, context

    def retry(self, chatbot, context):
        if len(context) == 0:
            return [], []
        response = self.get_response(context[:-1])
        context[-1] = {"role": "assistant", "content": response}

        chatbot[-1] = (context[-2]["content"], response)
        return chatbot, context

    def update_system(self, new_system_prompt):
        self.system = {"role": "system", "content": new_system_prompt}
        return new_system_prompt

def reset_state():
    return [], []

mychatGPT = ChatGPT(my_api_key)


with gr.Blocks() as demo:
    chatbot = gr.Chatbot().style(color_map=("#1D51EE", "#585A5B"))
    state = gr.State([])

    with gr.Column():
            txt = gr.Textbox(show_label=False, placeholder="💬 在这里输入").style(container=False)
    with gr.Row():
        emptyBth = gr.Button("重置")
        retryBth = gr.Button("再试一次")

    system = gr.Textbox(show_label=True, placeholder=f"在这里输入新的System Prompt...", label="更改 System prompt").style(container=False)
    syspromptTxt = gr.Textbox(show_label=True, placeholder=initial_prompt, interactive=False, label="目前的 System prompt").style(container=False)

    txt.submit(mychatGPT.predict, [chatbot, txt, state], [chatbot, state], show_progress=True)
    txt.submit(lambda :"", None, txt)
    emptyBth.click(reset_state, outputs=[chatbot, state])
    system.submit(mychatGPT.update_system, system, syspromptTxt)
    system.submit(lambda :"", None, system)
    retryBth.click(mychatGPT.retry, [chatbot, state], [chatbot, state], show_progress=True)

demo.launch()

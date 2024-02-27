
from collections import namedtuple
import os
import gradio as gr

from . import shared

# with open("./assets/ChuanhuChat.js", "r", encoding="utf-8") as f, \
#     open("./assets/external-scripts.js", "r", encoding="utf-8") as f1:
#     customJS = f.read()
#     externalScripts = f1.read()


def get_html(filename):
    path = os.path.join(shared.chuanhu_path, "web_assets", "html", filename)
    if os.path.exists(path):
        with open(path, encoding="utf8") as file:
            return file.read()
    return ""

def webpath(fn):
    if fn.startswith(shared.assets_path):
        web_path = os.path.relpath(fn, shared.chuanhu_path).replace('\\', '/')
    else:
        web_path = os.path.abspath(fn)
    return f'file={web_path}?{os.path.getmtime(fn)}'

ScriptFile = namedtuple("ScriptFile", ["basedir", "filename", "path"])

def javascript_html():
    head = ""
    for script in list_scripts("javascript", ".js"):
        head += f'<script type="text/javascript" src="{webpath(script.path)}"></script>\n'
    for script in list_scripts("javascript", ".mjs"):
        head += f'<script type="module" src="{webpath(script.path)}"></script>\n'
    return head

def css_html():
    head = ""
    for cssfile in list_scripts("stylesheet", ".css"):
        head += f'<link rel="stylesheet" property="stylesheet" href="{webpath(cssfile.path)}">'
    return head

def list_scripts(scriptdirname, extension):
    scripts_list = []
    scripts_dir = os.path.join(shared.chuanhu_path, "web_assets", scriptdirname)
    if os.path.exists(scripts_dir):
        for filename in sorted(os.listdir(scripts_dir)):
            scripts_list.append(ScriptFile(shared.assets_path, filename, os.path.join(scripts_dir, filename)))
    scripts_list = [x for x in scripts_list if os.path.splitext(x.path)[1].lower() == extension and os.path.isfile(x.path)]
    return scripts_list


def reload_javascript():
    js = javascript_html()
    js += '<script async type="module" src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>'
    js += '<script async type="module" src="https://spin.js.org/spin.umd.js"></script><link type="text/css" href="https://spin.js.org/spin.css" rel="stylesheet" />'
    js += '<script async src="https://cdn.jsdelivr.net/npm/@fancyapps/ui@5.0/dist/fancybox/fancybox.umd.js"></script><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fancyapps/ui@5.0/dist/fancybox/fancybox.css" />'
    
    meta = """
        <meta name="apple-mobile-web-app-title" content="川虎 Chat">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="application-name" content="川虎 Chat">
        <meta name='viewport' content='width=device-width, initial-scale=1.0, user-scalable=no, viewport-fit=cover'>
        <meta name="theme-color" content="#ffffff">

        <link rel="apple-touch-icon-precomposed" href="/file=web_assets/icon/mask-icon-512.png" crossorigin="use-credentials">
        <link rel="apple-touch-icon" href="/file=web_assets/icon/mask-icon-512.png" crossorigin="use-credentials">
        
        <link rel="manifest" href="/file=web_assets/manifest.json" crossorigin="use-credentials">
    """
    css = css_html()

    def template_response(*args, **kwargs):
        res = GradioTemplateResponseOriginal(*args, **kwargs)
        res.body = res.body.replace(b'</head>', f'{meta}{js}</head>'.encode("utf8"))
        # res.body = res.body.replace(b'</head>', f'{js}</head>'.encode("utf8"))
        res.body = res.body.replace(b'</body>', f'{css}</body>'.encode("utf8"))
        res.init_headers()
        return res

    gr.routes.templates.TemplateResponse = template_response

GradioTemplateResponseOriginal = gr.routes.templates.TemplateResponse
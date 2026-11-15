"""OpenAI 兼容接口（默认本地 Ollama）。思考模式必须关闭：开着会慢几十倍，还常输出坏 JSON。"""
import json
import re
import urllib.error
import urllib.request


class ModelUnavailable(RuntimeError):
    """模型服务连不上（没启动、地址不对）。重试没有意义，直接停下并说明原因。"""


def list_models(chat_url, timeout=5):
    """模型服务上已有的模型名（环境检查用）。返回 (查询地址, 名字列表)，连不上时抛 OSError。"""
    models_url = chat_url.split("/v1/")[0] + "/v1/models"
    with urllib.request.urlopen(models_url, timeout=timeout) as r:
        return models_url, [m["id"] for m in json.load(r)["data"]]


def ask_json(url, model, system, user, timeout=900):
    """发一次对话请求，返回模型回复中的 JSON 数组。格式不对时抛 ValueError，由调用方重试。"""
    body = {
        "model": model,
        "temperature": 0,
        "reasoning_effort": "none",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = json.load(r)["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise ModelUnavailable(f"模型服务 {url} 返回 {e.code}：检查配置里的模型名 {model!r} 是否已下载") from e
    except (urllib.error.URLError, ConnectionError) as e:
        raise ModelUnavailable(f"连不上模型服务 {url}：请先启动 Ollama（已翻译的段落都在缓存里，启动后重跑即可续上）") from e
    m = re.search(r"\[.*\]", content, re.S)
    if not m:
        raise ValueError("回复里没有 JSON 数组")
    return json.loads(m.group(0))

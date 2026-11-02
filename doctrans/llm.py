"""OpenAI 兼容接口（默认本地 Ollama）。思考模式必须关闭：开着会慢几十倍，还常输出坏 JSON。"""
import json
import re
import urllib.request


def ask_json(url, model, system, user, timeout=900):
    """发一次对话请求，返回模型回复中的 JSON 数组。格式不对时抛 ValueError，由调用方重试。"""
    body = {
        "model": model,
        "temperature": 0,
        "reasoning_effort": "none",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        content = json.load(r)["choices"][0]["message"]["content"]
    m = re.search(r"\[.*\]", content, re.S)
    if not m:
        raise ValueError("回复里没有 JSON 数组")
    return json.loads(m.group(0))

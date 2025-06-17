import json, torch, os, base64, requests
from qwen_agent.tools.base import BaseTool, register_tool

@register_tool("vision_describe")
class VisionDescribe(BaseTool):
    description = "输入 image_path，返回图片的文字描述和 OCR 结果"
    parameters  = [{"name": "image_path", "type": "string",
                    "description": "本地路径或 http(s) URL", "required": True}]

    def __init__(self):
        self.qwen_key = os.getenv("QWEN_KEY")
        if not self.qwen_key:
            raise ValueError("请设置 QWEN_KEY 环境变量")

    def call(self, params: str, **kw):
        path = json.loads(params)["image_path"]

        with open(path, "rb") as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode('utf-8')

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.qwen_key}"
        }

        payload = {
            "model": "qwen-vl-plus",
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe and OCR this image"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    }
                ]
            }]
        }

        try:
            response = requests.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers=headers,
                json=payload
            )

            if response.status_code != 200:
                return json.dumps({"error": f"API错误: {response.text}"}, ensure_ascii=False)
            
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                caption = result["choices"][0]["message"]["content"]
                return json.dumps({"caption": caption}, ensure_ascii=False)
            else:
                return json.dumps({"error": "未知响应格式"}, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({"error": f"请求失败: {str(e)}"}, ensure_ascii=False)
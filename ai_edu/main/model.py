import json, os, re, time, pathlib, sys, torch
from typing import List, Dict
from openai import OpenAI
from tqdm import tqdm
from dotenv import load_dotenv
import os
from transformers import AutoProcessor, AutoModelForImageTextToText
from PIL import Image
from pathlib import Path


MODEL_PATH =  r"E:\hugging_face_model\qwen2.5-vl-3b\models--Qwen--Qwen2.5-VL-3B-Instruct\snapshots\66285546d2b821cf421d4f5eb2576359d3770cd3"
JSON_IN         = r"E:\NLP_Model\ai_edu\data\processed_data\nantong2021_questions.json"
JSON_OUT        = r"E:\NLP_Model\ai_edu\data\processed_data\taizhou2023_tagged_third.json"
IMAGE_DIR       = pathlib.Path(r"E:\NLP_Model\ai_edu\data\processed_data\images")  # 所有图片都在此
DEVICE_MAP = "auto"

processor = AutoProcessor.from_pretrained(MODEL_PATH)
model = (AutoModelForImageTextToText.from_pretrained(MODEL_PATH, torch_dtype=torch.float16, device_map=DEVICE_MAP).eval())

# ---------- Prompt 模板 ----------
PROMPT_TMPL = """### 任务
你是一名资深中学数学命题专家，只需判断“题目”所属的【一级知识模块】：
1. 数与代数     核心：实数运算、代数式变换、方程与不等式、函数体系
2. 图形与几何   核心：平面几何性质、图形变换、坐标系应用
3. 统计与概率   核心：数据统计方法、概率模型

**注意**  
- 只选以上 4 个标签之一，不能自创标签。  
- 二级 / 三级 / 难度题型字段暂时留空，占位即可。  
- 必须输出 **严格一行 JSON**，键名固定为 "L1" "L2" "L3" "L4" ，其余不得包含任何多余字符。

**输出示例**  
{{"L1":"图形与几何","L2":"","L3":"","L4":""}}

### 题目
{QUESTION_BLOCK}

### 开始回答：
"""

# 从脚本 E:\NLP_Model\ai_edu\main\model.py 访问
PROJECT_ROOT = Path(__file__).parent.parent  # 假设脚本在 main/ 目录
json_fewshot_path = PROJECT_ROOT / "data" / "processed_data" / "few-shot.json"
FEW_SHOT = json.load(open(json_fewshot_path, encoding="utf-8"))


_rd_img = re.compile(r"\[IMG:([^\]]+?)\]")

def make_example_line(sample: Dict[str, str]) -> str:
    """构建示例题目的 prompt文本, 同时返回相关图片"""
    # md = build_question_block(sample)
    txt, images = md_to_qwen(build_question_block(sample))
    # 获取 L1 标签，正确访问嵌套字典
    label = sample.get('label', {}).get('L1', "未分类")
    if label == "":
        print(label = "未分类")
    return (f"""【示例题目】
{txt}

【示例标签】
{{"L1":"{label}","L2":"","L3":"","L4":""}}
""", images)

def build_prompt_with_shots(q: Dict) -> tuple[str, list]:
    """构建完整带有示例的 prompt， 并返回所有相关图片"""
    all_images = []
    example_texts = []

    # 收集所有示例文本和图片
    for s in FEW_SHOT:
        example_text, example_images = make_example_line(s)
        example_texts.append(example_text)
        all_images.extend(example_images)

    example_block = "\n".join(example_texts)
    # 待分类题目
    q_text, q_imgs = md_to_qwen(build_question_block(q))
    all_images.extend(q_imgs)

    prompt = f"""{example_block}

【待分类题目】
{q_text}

【请输出唯一一行JSON标签】："""
    return prompt, all_images

def build_question_block(q: Dict) -> str:
    """
    用题干 + 选项拼出给 LLM 的 markdown 区块
    直接将 [IMG:xxx] 转为 <img>，同时返回图片路径列表
    """
    try:
        body = q["content"]
        body = _rd_img.sub(lambda m: "<img>", body)

        result = body

        if q.get("options"):
            opts = []
            for o in q["options"]:
                opt_text = o["text"]
                opt_text = _rd_img.sub(lambda m: "<img>", opt_text)
                opts.append(opt_text)

            opts_text = "\n".join(opts)
            result = f"{body}\n\n**选项**\n{opts_text}"
        return result
    except (TypeError, KeyError) as e:
        print(f"处理题目时出错: {e}, 题目数据: {q}")
        return "题目数据格式有误" 

# _md_img = re.compile(r"!\[\]\((.*?)\)")

def md_to_qwen(markdown: str):
    """
    把 markdown 中的 <img> 转换为图片，
    同时查找原文中的 [IMG:xxx] 模式，加载对应图片文件
    """
    images = []
    img_matches = re.findall(r'\[IMG:([^\]]+?)\]', markdown)
    for img_name in img_matches:
        try:
            img_path = IMAGE_DIR / img_name
            images.append(Image.open(img_path).convert("RGB"))
            print(f"加载图片: {img_path}")
        except Exception as e:
            print(f"[warn] 加载图片 {img_path} 失败: {e}", file=sys.stderr)

    text = _rd_img.sub("<img>", markdown)
    return text, images

def call_llm(prompt_md: str, max_retry: int = 3) -> str:
    """
    调用 Qwen2.5-VL 模型处理文本和图像
    """
    for i in range(max_retry):
        try:
            text, images = md_to_qwen(prompt_md)
            inputs = processor(text=text,
                                images=images if images else None,
                                return_tensors="pt",).to(model.device)
            with torch.no_grad():
                out = model.generate(**inputs, 
                                    max_new_tokens=64,
                                    do_sample=False,
                                    eos_token_id=processor.tokenizer.eos_token_id)
            reply = processor.batch_decode(out, skip_special_tokens=True)[0].strip()
            print(reply)
            return reply
        except RuntimeError as e:
            torch.cuda.empty_cache()  # 清理显存
            if i == max_retry - 1:
                raise

        except Exception as e:
            if i == max_retry - 1:
                raise
                
            # 指数退避
            wait = 2 ** i
            print(f"[warn] {e}. retry in {wait}s …", file=sys.stderr)
            time.sleep(wait)

def call_llm_with_images(text: str, images:list, max_retry: int = 3) -> str:
    """
    调用 Qwen2.5-VL 模型处理文本和已预处理的图像
    """
    for i in range(max_retry):
        try:
            inputs = processor(
                text=text,
                images=images if images else None,
                return_tensors="pt",
            ).to(model.device)

            with torch.no_grad():
                out = model.generate(
                    **inputs,
                    max_new_tokens=64,
                    do_sample=False,
                    eos_token_id=processor.tokenizer.eos_token_id
                )

            reply = processor.batch_decode(out, skip_special_tokens=True)[0].strip()
            return reply
        except RuntimeError as e:
            torch.cuda.empty_cache()
            if i == max_retry - 1:
                raise
        except Exception as e:
            if i == max_retry - 1:
                raise

            wait = 2 ** i
            print(f"[warn] {e}. retry in {wait}s …", file=sys.stderr)
            time.sleep(wait)

def clean_json_block(s: str) -> str:
    """
     清理模型返回的 JSON 字符串，处理以下情况:
    1. 去掉代码块标记: ```json ... ``` 或 ``` ... ```
    2. 提取第一个有效的 JSON 对象
    3. 处理可能的重复 JSON 字符串
    """
    json_match = re.search(r"```(?:json)?(.*?)```", s, re.DOTALL)
    if json_match:
        s = json_match.group(1).strip()
    else:
        s = s.strip()

    json_obj_match = re.search(r"(\{.*?\})", s, re.DOTALL)
    if json_obj_match:
        return json_obj_match.group(1).strip()

    return s.strip()

def safe_json_line(s: str) -> Dict:
    """
    从模型返回的单行 JSON 字符串解析成 dict；
    若解析失败则返回占位空标签
    """
    print(f"原始输出: {s!r}")
    try:
        s_clean = clean_json_block(s)
        print(f"清理后输出: {s_clean!r}")
        obj = json.loads(s_clean)

        for k in {"L1","L2","L3","L4"}:
            if k not in obj:
                obj[k] = ""

        print(f"解析结果: {obj}")
        return obj
    except Exception as e:
        print(f"解析 JSON 失败: {e}")
        l1_match = re.search(r'"L1"\s*:\s*"([^"]+)"', s)
        if l1_match:
            l1_value = l1_match.group(1)
            print(f"使用正则提取到 L1: {l1_value}")
            return {"L1": l1_value, "L2":"", "L3":"", "L4":""}
    return {"L1":"", "L2":"", "L3":"", "L4":""}

def main():
    questions: List[Dict] = json.load(open(JSON_IN, encoding="utf-8"))
    for q in tqdm(questions, desc="Tagging with Few-Shot"):
        # 获取提示文本和所有图片
        prompt_text, all_images = build_prompt_with_shots(q)

        # 将提示文本替换到模板中
        full_prompt = PROMPT_TMPL.format(QUESTION_BLOCK=prompt_text)

        # 调用增强版的 call_llm 函数，直接传递预处理的图片
        raw = call_llm_with_images(full_prompt, all_images)

        # text = md_to_qwen(prompt)
        # print(text[0])

        # raw = call_llm(prompt)
        q["label"] = safe_json_line(raw)
    
    print(json.dumps(questions, ensure_ascii=False, indent=2))
    # json.dump(questions, open(JSON_OUT,"w",encoding="utf8"),
    #           ensure_ascii=False, indent=2)
    # print(f"共处理 {len(questions)} 道题。")

if __name__ == "__main__":
    main()
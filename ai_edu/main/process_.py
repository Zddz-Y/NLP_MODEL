from docx import Document
import pandas as pd
import re
import os
import zipfile
import requests
import json
import base64
from wand.image import Image
import subprocess
import pathlib
import uuid

qwen_key = os.getenv("QWEN_KEY")

# 提取图片和公式
def extract_images_from_runs(paragraph, doc, qid):
    images = []
    segment = ""
    for run in paragraph.runs:
        xml = run._element.xml
        text = run.text
        if text:
            segment += text
        # 查找所有 r:id="rIdXXX"
        rids = re.findall(r'(?:r:id|r:embed)="(rId\d+)"', xml)
        for rid in rids:  # 这里不是元组，而是直接的rId字符串
            try:
                rel = doc.part.rels.get(rid)
                if rel and "image" in rel.target_ref:
                    image_name = os.path.basename(rel.target_ref)
                    images.append(image_name)
                    segment += f"[IMG:{image_name}]"
            except Exception as e:
                print(f"处理rId {rid}时出错: {e}")
    return images, segment

# 提取文档中的文本、图片及结构化题目
def extract_doc_content(doc_path):
    """提取文档中的文本、图片及结构化题目"""
    doc = Document(doc_path)
    questions = []
    current_question = None
    collecting = False

    for para in doc.paragraphs:
        raw = para.text.strip()
        # # 遍历文档xml格式
        # for run in paragraph.runs:
        #     print(run.element.xml)
        # 匹配题号（如 "1."）
        m_q = re.match(r'^\d+\.', raw)
        if m_q:
            if current_question:
                questions.append(current_question)
            qid = m_q.group(1)
            current_question = {
                "id": int(qid),
                "content": "",
                "options": [],
                "images": [],
                "formulas": []
            }
            collecting = True
        
        if not collecting or current_question is None:
            continue

        images, segment = extract_images_from_runs(para, doc, current_question["id"])
        current_question["images"].extend(images)

        # 去除空白段
        if not segment.strip():
            continue

        # 匹配选项（如 "A."）
        m_opt = re.match(r'^[A-D]\.', segment.strip())
        if m_opt:
            # 新增一个选项 dict，也可以保留占位符在 option text 中
            current_question["options"].append({
                "text": segment.strip(),
                "images": re.findall(r'\[IMG:(.*?)\]', segment)
            })
        # 其他内容也提取图片
        else:
            # 普通题干，直接累加，并保留换行
            if current_question["content"]:
                current_question["content"] += "\n" + segment
            else:
                current_question["content"] = segment
    # 添加最后一个题目
    if current_question:
        questions.append(current_question)
    return questions


# 提取并存储图片/公式
def extract_media(docx_path, output_dir):
     # 清空目标文件夹
    if os.path.exists(output_dir):
        # 删除目录下所有文件
        for filename in os.listdir(output_dir):
            file_path = os.path.join(output_dir, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
            # 如果需要也删除子目录，取消下面注释
            # elif os.path.isdir(file_path):
            #     shutil.rmtree(file_path)
        print(f"已清空目录 {output_dir}")

    # 创建输出目录（确保media文件夹存在）
    os.makedirs(output_dir, exist_ok=True)
    image_map = {}

    with zipfile.ZipFile(docx_path, 'r') as zip_ref:
        media_files = [f for f in zip_ref.namelist() if f.startswith('word/media/')]
        print(f"找到 {len(media_files)} 个媒体文件")

        for file in media_files:
            #获取为文件数据直接写入新位置
            filename = os.path.basename(file)
            if not filename:
                print(f"警告：跳过空文件名 {file}")
                continue

            temp_path = os.path.join(output_dir, filename)
            try:
                # 提取文件内容并直接写入目标路径
                with zip_ref.open(file) as source, open(temp_path, 'wb') as target:
                    target.write(source.read())

                # 检查是否需要转换格式
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext == '.wmf':
                    png_filename = filename.replace('.wmf', '.png')
                    png_path = os.path.join(output_dir, png_filename)
                    try:
                        with Image(filename=temp_path) as img:
                            img.format = 'png'
                            img.save(filename=png_path)

                        os.unlink(temp_path)  # 删除原WMF文件
                        print(f"已将 {filename} 转换为 {png_filename}")

                        image_map[filename] = png_path
                        image_map[png_filename] = png_path
                    except Exception as e:
                        print(f"转换 {filename} 时出错: {e}")
                        image_map[filename] = temp_path

                else:
                    image_map[filename] = temp_path

            except Exception as e:
                print(f"提取 {file} 时出错: {e}")
    return image_map

# qwen-vl图片公式提取
def qwen_vl_ocr(image_path):
    # 编码图片为base64
    with open(image_path, "rb") as img_file:
        img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
    
    # 调用Qwen-VL API（示例URL）
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer{qwen_key}"  # 替换为你的API Key
               }
    payload = {
        "model": "qwen-vl-plus",
        "messages": [{
            "role": "user",
            "content": [
                    {
                        "type": "text",
                        "text": "提取图片中的文字和数学公式，公式用LaTeX表示"
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
    response = requests.post(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        headers=headers,
        json=payload
    )
    # 打印完整响应，用于调试
    print(f"API响应状态码: {response.status_code}")
    if response.status_code != 200:
        print(f"API错误: {response.text[:200]}...")  # 只打印前200字符避免日志过长
    
    # 增加错误处理
    try:
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        elif "error" in result:
            return f"API错误: {result.get('error', {}).get('message', '未知错误')}"
        else:
            return f"未知响应格式: {result}"
    except Exception as e:
        return f"解析响应出错: {e}"

def process_questions(questions, image_map):
    """处理题目中的图片和公式"""
    # for question in questions:
    #     # 处理题干中的图片
    #     for img_ref in question["images"]:
    #         img_path = image_map.get(img_ref)
    #         if img_path:
    #             ocr_result = qwen_vl_ocr(img_path)
    #             # 替换图片引用为OCR结果（保留原始内容）
    #             question["content"] = question["content"].replace(
    #                 f"![]({img_ref})",
    #                 f"[图片内容：{ocr_result}]"
    #             )
        
    #     # 处理选项中的图片
    #     for option in question["options"]:
    #         for img_ref in option["image_refs"]:
    #             img_path = image_map.get(img_ref)
    #             if img_path:
    #                 ocr_result = qwen_vl_ocr(img_path)
    #                 option["text"] = option["text"].replace(
    #                     f"![]({img_ref})",
    #                     f"[选项内容：{ocr_result}]"
    #                 )
    # return questions
    for question in questions:
        pass
    
    return questions


if __name__ == "__main__":
    # 主程序
    docx_path = r"E:\NLP_Model\ai_edu\data\math\2023年江苏省泰州市中考数学真题（原卷版）.docx"
    output_dir = r"E:\NLP_Model\ai_edu\data\processed_data"

    # 1. 解析文档结构
    questions = extract_doc_content(docx_path)

    # 2. 提取图片到本地
    image_map = extract_media(docx_path, os.path.join(output_dir, "media"))

    # 3. 使用Qwen-VL处理图片内容
    processed_questions = process_questions(questions, image_map)

    # 4. 保存结构化数据
    import json
    with open(os.path.join(output_dir, "labeled_questions.json"), "w", encoding="utf-8") as f:
        json.dump(processed_questions, f, indent=2, ensure_ascii=False)
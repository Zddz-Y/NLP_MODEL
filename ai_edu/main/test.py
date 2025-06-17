import json, os, re, time, pathlib, sys
from typing import List, Dict, Any
import docx
from docx.document import Document as DocxDocument
from docx.parts.image import ImagePart
import io
from PIL import Image
from openai import OpenAI
from tqdm import tqdm
from dotenv import load_dotenv
import base64

# 确保加载环境变量
load_dotenv()

# 确保能导入VisionDescribe工具
MODEL_DIR = pathlib.Path(r"E:\NLP_Model\ai_edu\model")
sys.path.append(str(MODEL_DIR.parent))  # 添加父目录到系统路径
print(f"添加路径: {MODEL_DIR.parent}")

# 导入与model_process_image.py相同的VisionDescribe工具
try:
    from model.vision_tool import VisionDescribe
    vision_tool = VisionDescribe()
    print("成功导入VisionDescribe工具")
except Exception as e:
    print(f"导入VisionDescribe失败: {e}")
    sys.exit(1)

# 检查vision_tool是否可用
try:
    test_output = vision_tool.call(json.dumps({"test": "connection"}))
    print(f"VisionTool连接测试: {test_output[:100]}...")
except Exception as e:
    print(f"VisionTool连接测试失败: {e}")

total_prompt_tokens = 0
total_completion_tokens = 0
total_tokens = 0

client = OpenAI(
    api_key = os.getenv("QWEN_KEY"),
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 输入文件和输出目录
QUESTIONS_JSON = r"E:\NLP_Model\ai_edu\data\processed_data\suzhou2024\suzhou2024_questions.json"
ANSWERS_JSON = r"E:\NLP_Model\ai_edu\data\processed_data\suzhou2024\suzhou2024_questions_answer.json"
OUTPUT_DIR = r"E:\NLP_Model\ai_edu\data\processed_data\suzhou2024"
JSON_OUT = os.path.join(OUTPUT_DIR, "suzhou2024_labeled_question.json")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")

# 确保输出目录存在
os.makedirs(OUTPUT_DIR, exist_ok=True)

PROMPT_TMPL = """### 任务
你是一名资深中学数学命题专家，需要分析数学题目并进行六维度标签分类。

**重要说明：**
- 当你看到 [IMG:filename.png] 时，必须先调用 vision_describe 工具来分析图片内容
- 根据图片中的数学题目内容进行准确分类

### 六维度标签体系
**维度1：知识模块维度（基于课标核心结构）**
D1_L1：固定为"知识模块"
D1_L2：二级标签（选择一个）
- 数与式
- 方程不等式  
- 函数
- 几何性质
- 几何变换

D1_L3：三级标签（根据D1_L2选择）
- 数与式下：有理数、实数、代数式
- 方程不等式下：线性方程、二次方程、不等式
- 函数下：初等函数、图像分析
- 几何性质下：三角形、四边形、圆
- 几何变换下：对称变换、旋转变换

D1_L4：四级标签（根据D1_L3具体选择，共48个细分标签）
- 有理数下: 运算律、绝对值应用、科学计数法
- 实数下: 无理数识别、数轴比大小、根式化简
- 代数式下: 整式运算、因式分解(4法)、分式化简
- 线性方程下: 含参方程,应用题建模、解的关系
- 二次方程下: 判别式应用、韦达定理、整数根问题
- 不等式下: 含参不等式组,绝对值不等式,区域解
- 初等函数下: 待定系数法、函数性质综合、参数影响
- 图像分析下: 交点问题,动态图像,最值区域
- 三角形下: 全等模型、相似模型、勾股定理应用
- 四边形下: 判定定理、对角线性质、中点四边形
- 园下: 垂径定理、圆周角定理,切线长定理
- 对称变换下: 折叠问题,对称最值、性质应用 
- 旋转变换下: 旋转构图、轨迹分析、综合变换

**维度2：认知操作维度**
D2_L1：固定为“认知操作”
D2_L2：二级标签（选择一个）

- 识别再现

- 关联转换

- 推理论证

- 建模求解

- 批判验证

D2_L3：三级标签（根据D2_L2选择）

- 识别再现下：概念识别、公式调用

- 关联转换下：符号·图形互译、条件等价转换

- 推理论证下：直接演绎、复杂演绎、归纳类比

- 建模求解下：问题数学化、模型优化

- 批判验证下：解域检验、反例构造

D2_L4：四级标签（根据D2_L3具体选择）

- 概念识别下：直接辨认定义/定理

- 公式调用下：直接套用公式计算结果

- 符号·图形互译下：函数式↔图像特征、几何条件↔方程

- 条件等价转换下：换元法、参数消去、等量代换

- 直接演绎下：定理链式推导(≤3步)

- 复杂演绎下：多分支证明(2–4步以上)

- 归纳类比下：从特例总结规律/结构类比迁移

- 问题数学化下：实际问题→数学模型(方程/函数)

- 模型优化下：参数调整、约束条件处理

- 解域检验下：范围验证(定义域/几何约束)

- 反例构造下：举反例证伪命题 

**维度3：解题策略维度**
D3_L1：固定为“解题策略”
D3_L2：二级标签（选择一个）

- 直接策略

- 构造策略

- 转化策略

- 分类策略

- 逆向策略

D3_L3：三级标签（根据D3_L2选择）

- 直接策略下：公式代入法、定理直推法

- 构造策略下：辅助线构造、辅助函数法、参数设定法

- 转化策略下：等价转化法、数形转换法、降维分解法

- 分类策略下：参数分类法、位置分类法

- 逆向策略下：反证法、逆推分析法

D3_L4：四级标签（根据D3_L3具体选择）

- 公式代入法下：直接套用公式(如求根公式)

- 定理直推法下：使用单一定理直接推导

- 辅助线构造下：几何—做平行线/补形/倍长中线

- 辅助函数法下：引入新函数(如判别式构造)

- 参数设定法下：设未知参数简化关系

- 等价转化法下：同解变形/等面积转换

- 数形转换法下：代数问题几何化/几何问题坐标化

- 降维分解法下：高次→低次、复合→基本

- 参数分类法下：依据参数取值讨论(k存在性等)

- 位置分类法下：几何动态点位置分类

- 反证法下：假设结论不成立推导矛盾

- 逆推分析法下：从结论反向寻找条件 

**维度4：数学思想维度**
D4_L1：固定为“数学思想”
D4_L2：二级标签（选择一个）

- 数形结合

- 分类讨论

- 转化化归

- 函数方程

- 极限思想

D4_L3：三级标签（根据D4_L2选择）

- 数形结合下：以数解形、以形助数

- 分类讨论下：概念分类、过程分类

- 转化化归下：等价化归、特殊化归

- 函数方程下：函数思想、方程思想

- 极限思想下：边界分析、逼近思想

D4_L4：四级标签（根据D4_L3具体选择）

- 以数解形下：坐标系解几何问题

- 以形助数下：图像法解代数最值

- 概念分类下：定义域分类(如绝对值)

- 过程分类下：多情况解题路径

- 等价化归下：复杂→简单(如换元)

- 特殊化归下：一般→特殊(如极端位置)

- 函数思想下：动态问题函数建模

- 方程思想下：等量关系建模

- 边界分析下：取值范围临界点

- 逼近思想下：无限逼近精确解 

**维度5：作答形式维度**
D5_L1：固定为“作答形式”
D5_L2：二级标签（选择一个）

- 客观题型

- 主观题型

D5_L3：三级标签（根据D5_L2选择）

- 客观题型下：单选题、多选题、填空题

- 主观题型下：计算题、证明题、探究题

D5_L4：四级标签（根据D5_L3具体选择）

- 单选题下：唯一正确答案

- 多选题下：多选全对得分

- 填空题下：结果唯一性

- 计算题下：过程分步骤赋分

- 证明题下：逻辑链完整性评分

- 探究题下：创新性解法加分 

**维度6：难度控制维度**
D6_L1：固定为“难度控制”
D6_L2：二级标签（选择一个）

- 知识量

- 思维步数

- 障碍密度

D6_L3：三级标签（根据D6_L2选择）

- 知识量下：单点知识、双知识链、多模块综合

- 思维步数下：直接步骤(≤3)、中等步骤(4–5)、复杂步骤(>6)

- 障碍密度下：无干扰项、单一干扰、多重干扰

D6_L4：四级标签（根据D6_L3具体选择）

- 单点知识下：仅1个核心知识点

- 双知识链下：2个知识点串联

- 多模块综合下：2–3个模块知识交织

- 直接步骤下：≤3步，无需转化

- 中等步骤下：4–5步，含1–2次转化

- 复杂步骤下：多数转化+构造（如23次转化+构造）

- 无干扰项下：条件直给

- 单一干扰下：1个隐含条件/陷阱

- 多重干扰下：≥2个干扰项+临界分析

**注意事项**:  
- 遇到图片时，先调用工具分析图片内容，再进行分类
- 必须输出**严格一行 JSON**，包含所有18个标签
- 键名固定为：D1_L1, D1_L2, D1_L3, D1_L4, D2_L1, D2_L2, D2_L3, D2_L4, D3_L1, D3_L2, D3_L3, D3_L4, D4_L1, D4_L2, D4_L3, D4_L4, D5_L1, D5_L2, D5_L3, D5_L4, D6_L1, D6_L2, D6_L3
- 所有键都必须有值，不允许出现空值或未分类情况
- 所有标签都必须从上述体系中选择，不能自创标签


### 题目内容
{QUESTION_BLOCK}

### 分析步骤
1. 先调用vision_describe工具分析图片内容
2. 基于图片中的题目信息进行标签分类
3. 输出JSON格式结果
"""

def load_questions_and_answers() -> List[Dict]:
    """从JSON文件中加载题目和答案数据"""
    print("从JSON文件加载题目和答案...")
    
    # 检查文件是否存在
    if not os.path.exists(QUESTIONS_JSON):
        print(f"错误: 题目文件不存在 - {QUESTIONS_JSON}")
        return []
    
    # 注释掉答案文件检查
    if not os.path.exists(ANSWERS_JSON):
        print(f"错误: 答案文件不存在 - {ANSWERS_JSON}")
        return []
    
    # 加载题目数据
    with open(QUESTIONS_JSON, 'r', encoding='utf-8') as f:
        questions_data = json.load(f)
    print(f"加载了 {len(questions_data)} 道题目")
    
    # 加载答案数据
    with open(ANSWERS_JSON, 'r', encoding='utf-8') as f:
        answers_data = json.load(f)
    print(f"加载了 {len(answers_data)} 个答案")
    
    # 合并题目和答案
    questions = []
    for i, question in enumerate(questions_data):
        # 获取对应的答案
        answer = answers_data[i] if i < len(answers_data) else None
        
        merged_question = {
            "id": i + 1,
            "question_data": question,
            "answer_data": answer,
            "content": question.get("content", ""),
            "question_images": extract_image_placeholders(question),
            "answer_images": extract_image_placeholders(answer) if answer else [],
            "type": "question_with_answer_from_json"
            # "type": "question_only"
        }
        questions.append(merged_question)
    
    print(f"合并后共有 {len(questions)} 道题目")
    return questions


def extract_image_placeholders(data: Dict) -> List[str]:
    """从JSON数据中提取图片占位符"""
    if not data:
        return []
    
    image_placeholders = []
    
    def find_images_recursive(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "image" or key == "images":
                    if isinstance(value, str) and value:
                        image_placeholders.append(value)
                    elif isinstance(value, list):
                        image_placeholders.extend([img for img in value if img])
                else:
                    find_images_recursive(value)
        elif isinstance(obj, list):
            for item in obj:
                find_images_recursive(item)
        elif isinstance(obj, str):
            # 查找文本中的图片占位符，如 [IMG:xxx.png] 或 {img:xxx.jpg}
            import re
            img_patterns = [
                r'\[IMG:([^\]]+)\]',
                r'\{img:([^}]+)\}',
                r'image_\d+\.(png|jpg|jpeg)',
                r'img_\d+\.(png|jpg|jpeg)'
            ]
            for pattern in img_patterns:
                matches = re.findall(pattern, obj, re.IGNORECASE)
                if matches:
                    image_placeholders.extend(matches if isinstance(matches[0], str) else [m[0] for m in matches])
    
    find_images_recursive(data)
    return list(set(image_placeholders))  # 去重

def build_question_block(q: Dict) -> str:
    """构建题目内容块"""
    question_data = q.get("question_data", {})
    content = q.get("content", "")
    
    # 如果content为空，尝试从question_data中提取
    if not content:
        content = question_data.get("content", "") or question_data.get("text", "") or question_data.get("question", "")
    
    # 添加图片占位符
    if q.get("question_images"):
        content += "\n\n题目图片："
        for img in q["question_images"]:
            content += f"\n[IMG:{img}]"
    
    # 添加选项（如果有）
    options = question_data.get("options", [])
    if options:
        content += "\n\n选项："
        for i, option in enumerate(options):
            if isinstance(option, dict):
                option_text = option.get("text", "") or option.get("content", "")
            else:
                option_text = str(option)
            content += f"\n{chr(65+i)}. {option_text}"
    
    return content

def build_answer_block(q: Dict) -> str:
    """构建答案内容块"""
    # return ""
    answer_data = q.get("answer_data", {})
    if not answer_data:
        return "无答案数据"
    
    answer_content = "答案内容："
    
    # 添加答案文本
    answer_text = answer_data.get("answer", "") or answer_data.get("content", "") or answer_data.get("text", "")
    if answer_text:
        answer_content += f"\n{answer_text}"
    
    # 添加答案图片
    if q.get("answer_images"):
        answer_content += "\n\n答案图片："
        for i, img in enumerate(q["answer_images"], 1):
            answer_content += f"\n{i}. [IMG:{img}]"
    
    return answer_content

def call_llm_with_tools(prompt: str, max_retry: int = 3) -> str:
    """调用支持工具的LLM - 支持从images目录读取图片"""
    global total_completion_tokens, total_prompt_tokens, total_tokens

    tools = [
        {
            "type": "function",
            "function": {
                "name": "vision_describe",
                "description": "分析数学题目或答案图片，识别其中的文本内容、数学公式、几何图形、解题步骤等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {
                            "type": "string",
                            "description": "图片文件路径或占位符"
                        }
                    },
                    "required": ["image_path"]
                }
            }
        }
    ]

    for attempt in range(max_retry):
        try:
            messages = [{"role": "user", "content": prompt}]
            print(f"发送请求到LLM (尝试 {attempt + 1}/{max_retry})")

            while True:
                resp = client.chat.completions.create(
                    model="qwen-plus",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.0,
                    max_tokens=4096
                )

                message = resp.choices[0].message
                messages.append(message)

                # 统计token
                if hasattr(resp, 'usage') and resp.usage:
                    prompt_tokens = resp.usage.prompt_tokens
                    completion_tokens = resp.usage.completion_tokens
                    total_tokens_used = resp.usage.total_tokens

                    total_prompt_tokens += prompt_tokens
                    total_completion_tokens += completion_tokens
                    total_tokens += total_tokens_used
                    print(f"Token使用: prompt={prompt_tokens}, completion={completion_tokens}")

                # 处理工具调用
                if message.tool_calls:
                    print(f"检测到 {len(message.tool_calls)} 个工具调用")
                    
                    for tool_call in message.tool_calls:
                        if tool_call.function.name == "vision_describe":
                            try:
                                print(f"调用工具参数: {tool_call.function.arguments}")
                                args = json.loads(tool_call.function.arguments)
                                image_placeholder = args["image_path"]
                                
                                # 清理图片占位符，获取实际文件名
                                image_filename = image_placeholder
                                if image_filename.startswith("[IMG:") and image_filename.endswith("]"):
                                    image_filename = image_filename[5:-1]
                                
                                # 在images目录中查找图片
                                full_image_path = os.path.join(IMAGES_DIR, image_filename)
                                
                                # 如果直接路径不存在，尝试不同的扩展名
                                if not os.path.exists(full_image_path):
                                    base_name = os.path.splitext(image_filename)[0]
                                    for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif']:
                                        test_path = os.path.join(IMAGES_DIR, base_name + ext)
                                        if os.path.exists(test_path):
                                            full_image_path = test_path
                                            break
                                
                                print(f"分析图片: {full_image_path}")
                                
                                if not os.path.exists(full_image_path):
                                    error_msg = f"图片文件不存在: {full_image_path}"
                                    print(error_msg)
                                    tool_result = json.dumps({
                                        "error": error_msg,
                                        "image_path": image_placeholder
                                    }, ensure_ascii=False)
                                else:
                                    # 调用vision工具
                                    vision_params = json.dumps({"image_path": full_image_path})
                                    tool_result = vision_tool.call(vision_params)
                                    print(f"工具返回结果长度: {len(tool_result)}")
                                    print(f"工具返回结果前200字符: {tool_result[:200]}")

                                # 添加工具调用结果到消息历史
                                messages.append({
                                    "tool_call_id": tool_call.id,
                                    "role": "tool",
                                    "content": tool_result
                                })

                            except Exception as e:
                                print(f"工具调用失败: {e}")
                                import traceback
                                traceback.print_exc()
                                
                                error_result = json.dumps({
                                    "error": f"图片分析失败: {str(e)}",
                                    "image_path": args.get("image_path", "unknown")
                                }, ensure_ascii=False)
                                
                                messages.append({
                                    "tool_call_id": tool_call.id,
                                    "role": "tool",
                                    "content": error_result
                                })
                    
                    # 继续对话，让模型基于工具结果生成最终答案
                    print("继续对话，等待最终答案...")
                    continue
                else:
                    # 没有工具调用，返回最终结果
                    final_response = message.content.strip()
                    print(f"获得最终响应: {final_response[:200]}...")
                    return final_response

        except Exception as e: 
            print(f"请求失败 (尝试 {attempt + 1}/{max_retry}): {e}")
            import traceback
            traceback.print_exc()
            
            if attempt == max_retry - 1:
                raise
            # 指数退避
            wait_time = 2 ** attempt
            print(f"等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)

def clean_json_block(s: str) -> str:
    """清理JSON字符串"""
    # 移除markdown代码块标记
    s = re.sub(r"^```json|^```|```$", "", s.strip(), flags=re.MULTILINE)
    # 移除多余的空白字符
    s = s.strip()
    return s

def safe_json_line(s: str) -> Dict:
    """安全解析JSON"""
    try:
        s_clean = clean_json_block(s)
        print(f"尝试解析JSON: {s_clean[:200]}...")
        
        # 尝试找到JSON部分
        json_match = re.search(r'\{.*\}', s_clean, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            obj = json.loads(json_str)
        else:
            obj = json.loads(s_clean)
        
        # 检查必需的18个标签
        required_labels = {
            "D1_L1": "知识模块", "D1_L2": "未分类", "D1_L3": "未分类",
            "D2_L1": "认知操作", "D2_L2": "未分类", "D2_L3": "未分类",
            "D3_L1": "解题策略", "D3_L2": "未分类", "D3_L3": "未分类",
            "D4_L1": "数学思想", "D4_L2": "未分类", "D4_L3": "未分类",
            "D5_L1": "作答形式", "D5_L2": "未分类", "D5_L3": "未分类",
            "D6_L1": "难度控制", "D6_L2": "未分类", "D6_L3": "未分类"
        }
        
        # 补充缺失的标签
        for label, default_value in required_labels.items():
            if label not in obj or not obj[label] or obj[label].strip() == "":
                obj[label] = default_value
                print(f"补充标签 {label} = {default_value}")
        
        print(f"JSON解析成功，包含 {len(obj)} 个标签")
        return obj
        
    except Exception as e:
        print(f"JSON解析失败: {e}")
        print(f"原始响应: {s}")
        # 返回默认标签
        return {
            "D1_L1": "知识模块", "D1_L2": "解析失败", "D1_L3": "解析失败",
            "D2_L1": "认知操作", "D2_L2": "解析失败", "D2_L3": "解析失败",
            "D3_L1": "解题策略", "D3_L2": "解析失败", "D3_L3": "解析失败",
            "D4_L1": "数学思想", "D4_L2": "解析失败", "D4_L3": "解析失败",
            "D5_L1": "作答形式", "D5_L2": "解析失败", "D5_L3": "解析失败",
            "D6_L1": "难度控制", "D6_L2": "解析失败", "D6_L3": "解析失败"
        }

def main():
    print("开始处理已提取的JSON数据...")
    
    # 从JSON文件加载题目和答案
    questions = load_questions_and_answers()
    
    if not questions:
        print("没有加载到题目和答案数据，程序退出")
        return
    
    print(f"准备处理 {len(questions)} 道题目")
    
    # 检查images目录是否存在
    if not os.path.exists(IMAGES_DIR):
        print(f"警告: 图片目录不存在 - {IMAGES_DIR}")
        print("请确保图片已正确提取到该目录")
    else:
        image_files = os.listdir(IMAGES_DIR)
        print(f"图片目录包含 {len(image_files)} 个文件")
    
    # 为每道题目打标签
    for i, q in enumerate(questions):
        try:
            print(f"\n{'='*60}")
            print(f"处理题目 {i+1}/{len(questions)}: ID={q.get('id', 'unknown')}")
            
            # 显示题目和答案图片信息
            if q.get('question_images'):
                print(f"题目图片: {', '.join(q['question_images'])}")
                for img in q['question_images']:
                    img_path = os.path.join(IMAGES_DIR, img)
                    if os.path.exists(img_path):
                        img_size = os.path.getsize(img_path)
                        print(f"  ✓ {img} 存在 (大小: {img_size/1024:.1f}KB)")
                    else:
                        print(f"  ✗ {img} 不存在")
            
            if q.get('answer_images'):
                print(f"答案图片: {', '.join(q['answer_images'])}")
                for img in q['answer_images']:
                    img_path = os.path.join(IMAGES_DIR, img)
                    if os.path.exists(img_path):
                        img_size = os.path.getsize(img_path)
                        print(f"  ✓ {img} 存在 (大小: {img_size/1024:.1f}KB)")
                    else:
                        print(f"  ✗ {img} 不存在")
            
            # 跳过已经处理过的题目
            if q.get('label') and q['label'].get('D1_L2') not in ['未分类', '处理失败', '解析失败']:
                print(f"题目已处理过，跳过: {q['label']['D1_L2']}, {q['label']['D5_L2']}")
                continue
            
            # 构建包含题目和答案的prompt
            question_block = build_question_block(q)
            answer_block = build_answer_block(q)  # 注释掉答案块构建
            prompt = PROMPT_TMPL.format(
                QUESTION_BLOCK=question_block,
                ANSWER_BLOCK=answer_block  # 答案块
            )
            
            print("调用LLM进行标注...")
            raw_response = call_llm_with_tools(prompt)
            
            # 解析结果
            q["label"] = safe_json_line(raw_response)
            print(f"标注完成: {q['label']['D1_L2']}, {q['label']['D5_L2']}")
            
            # 每处理一个题目就保存一次结果
            with open(JSON_OUT, 'w', encoding='utf-8') as f:
                json.dump(questions, f, ensure_ascii=False, indent=2)
                print(f"中间结果已保存到: {JSON_OUT}")
            
        except Exception as e:
            print(f"处理题目失败: {e}")
            import traceback
            traceback.print_exc()
            
            q["label"] = {
                "D1_L1": "知识模块", "D1_L2": "处理失败", "D1_L3": "处理失败",
                "D2_L1": "认知操作", "D2_L2": "处理失败", "D2_L3": "处理失败",
                "D3_L1": "解题策略", "D3_L2": "处理失败", "D3_L3": "处理失败",
                "D4_L1": "数学思想", "D4_L2": "处理失败", "D4_L3": "处理失败",
                "D5_L1": "作答形式", "D5_L2": "处理失败", "D5_L3": "处理失败",
                "D6_L1": "难度控制", "D6_L2": "处理失败", "D6_L3": "处理失败"
            }

    # 保存最终结果
    with open(JSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    # 输出统计信息
    print(f"\n{'='*60}")
    print("处理完成统计:")
    print(f"总题目数: {len(questions)}")
    print(f"Token使用:")
    print(f"  提示tokens: {total_prompt_tokens}")
    print(f"  完成tokens: {total_completion_tokens}")
    print(f"  总tokens: {total_tokens}")
    print(f"结果保存到: {JSON_OUT}")

    # 输出标签统计
    label_stats = {"D1_L2": {}, "D2_L2": {}, "D5_L2": {}}
    for q in questions:
        if not q.get('label'):
            continue
        for dim in ["D1_L2", "D2_L2", "D5_L2"]:
            value = q['label'].get(dim, "未分类")
            if value not in label_stats[dim]:
                label_stats[dim][value] = 0
            label_stats[dim][value] += 1
    
    print("\n标签统计:")
    for dim, counts in label_stats.items():
        print(f"\n{dim} 分布:")
        for label, count in counts.items():
            print(f"  {label}: {count}题 ({count/len(questions)*100:.1f}%)")


if __name__ == "__main__":
    main()
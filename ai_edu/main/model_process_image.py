import json, os, re, time, pathlib, sys
from typing import List, Dict
from openai import OpenAI
from tqdm import tqdm
from dotenv import load_dotenv
import os
from model.vision_tool import VisionDescribe

total_prompt_tokens = 0
total_completion_tokens = 0
total_tokens = 0

client = OpenAI(
    api_key = os.getenv("QWEN_KEY"),
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
# qwen_key = os.getenv("QWEN_KEY")
# openai.api_key  = os.getenv("QWEN_KEY")
# MODEL_NAME      = "qwen-vl-plus"       # 改成控制台里实际可用的名字

vision_tool = VisionDescribe()

JSON_IN         = r"E:\NLP_Model\ai_edu\data\processed_data\taizhou2023.json"
JSON_OUT        = r"E:\NLP_Model\ai_edu\data\processed_data\taizhou2023_tagged2.json"
IMAGE_DIR       = pathlib.Path(r"E:\NLP_Model\ai_edu\data\processed_data\images")  # 所有图片都在此

# ---------- Prompt 模板 ----------
PROMPT_TMPL = """### 任务
你是一名资深中学数学命题专家，严格按照每个维度的标签体系，为该题目打上最合适的标签。对于每一个维度，你都必须按照要求，在指定的层级中选择且仅选择一个最贴切的标签，不能自行创建标签。

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

**输出示例**:  
{{"D1_L1":"知识模块","D1_L2":"几何性质","D1_L3":"三角形","D1_L4":"全等模型","D2_L1":"认知操作","D2_L2":"推理论证","D2_L3":"直接演绎","D2_L3“,"D3_L1":"解题策略","D3_L2":"构造策略","D3_L3":"辅助线构造","D4_L1":"数学思想","D4_L2":"数形结合","D4_L3":"以形助数","D5_L1":"作答形式","D5_L2":"主观题型","D5_L3":"证明题","D6_L1":"难度控制","D6_L2":"思维步数","D6_L3":"中等步骤(4-5)"}}

### 题目
{QUESTION_BLOCK}

### 开始回答（如有图片请先调用工具，仅输出一行JSON）:
"""

_rd_img = re.compile(r"\[IMG:([^\]]+?)\]")

# 图片工具调用时，弃用
def placeholder_to_md(text: str) -> str:
    """
    把 [IMG:xxx.png] → ![](images/xxx.png)
    """
    def _repl(m):
        fname = m.group(1)
        return f"![]({IMAGE_DIR / fname})"
    return _rd_img.sub(_repl, text)

def build_question_block(q: Dict) -> str:
    """
    直接返回原始题目文本，不预处理图片
    """
    content = q["content"]
    if q.get("options"):
        opts = "\n".join(o["text"] for o in q["options"])
        return f"{content}\n\n选项：\n{opts}"
    return content

def call_llm_with_tools(prompt: str, max_retry: int = 3) -> str:
    """
    调用支持工具的LLM，让其智能决定何时调用vision工具
    """
    global total_completion_tokens, total_prompt_tokens, total_tokens

    tools = [
        {
            "type": "function",
            "function": {
                "name": "vision_describe",
                "description": "分析数学题目中的图片内容，包括数学公式、几何图形、统计图表等。输入图片文件名（如：1_a9791995.png），返回图片的详细描述和OCR识别结果。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {
                            "type": "string",
                            "desciption": "图片文件名，例如：1_a9791995.png, 2_formula.jpg等。会自动在images目录中查找该文件。"
                        }
                    },
                    "required": ["image_path"]
                }
            }
        }
    ]

    for i in range(max_retry):
        try:
            # 发送初始请求
            messages = [{"role": "user", "content": prompt}]

            while True:
                resp = client.chat.completions.create(
                    model="qwen-vl-plus",
                    messages=messages,
                    tool_choice="auto",
                    temperature=0.0,
                )

                message = resp.choices[0].message
                messages.append(message)

                # 统计token使用
                if hasattr(resp, 'usage') and resp.usage:
                    prompt_tokens = resp.usage.prompt_tokens
                    completion_tokens = resp.usage.completion_tokens
                    total_tokens_used = resp.usage.total_tokens

                    total_prompt_tokens += prompt_tokens
                    total_completion_tokens += completion_tokens
                    total_tokens += total_tokens_used
                    print(f"本次请求tokens: 提示={prompt_tokens}, 完成={completion_tokens}, 总计={total_tokens_used}")
                
                # 检查是否有工具调用
                if message.tool_calls:
                    print(f"检测到 {len(message.tool_calls)} 个工具调用")

                    for tool_call in message.tool_calls:
                        if tool_call.function.name == "vision_describe":
                            try:
                                # 解析工具调用用参数
                                args = json.loads(tool_call.function.arguments)
                                image_filename = args["image_path"]

                                # 构建完整路径
                                full_image_path = str(IMAGE_DIR / image_filename)
                                print(f"正在分析图片: {image_filename}")

                                # 调用vision工具
                                vision_params = json.dumps({"image_path": full_image_path})
                                vision_result = vision_tool.call(vision_params)
                                if vision_result is None:
                                    raise ValueError("工具调用返回结果为空或格式错误")

                                # 添加工具调用结果到消息历史
                                messages.append({
                                    "tool_call_id": tool_call.id,
                                    "role": "tool",
                                    "content": vision_result
                                })

                            except Exception as e:
                                print(f"工具调用失败: {e}")
                                # 添加错误信息
                                messages.append({
                                    "tool_call_id": tool_call.id,
                                    "role": "tool",
                                    "content": json.dumps({"error": f"图片分析失败: {str(e)}"}, ensure_ascii=False)
                                })
                    # 继续对话,让模型基于工具结果生成最终答案
                    continue
                else:
                    # 没有工具调用,返回最终结果
                    return message.content.strip()

        except Exception as e: 
            if i == max_retry - 1:
                raise
            # 指数退避
            wait = 2 ** i
            print(f"[warn] {e}. retry in {wait}s …", file=sys.stderr)
            time.sleep(wait)

def clean_json_block(s: str) -> str:
    """
    清理模型返回的 JSON 字符串，去掉开头的 ```json 或 ```，以及结尾的 ```
    """
    return re.sub(r"^```json|^```|```$", "", s.strip(), flags=re.MULTILINE).strip()

def safe_json_line(s: str) -> Dict:
    """
    从模型返回的单行 JSON 字符串解析成 dict；
    若解析失败则返回占位标签，确保L1有值
    """
    try:
        s_clean = clean_json_block(s)
        obj = json.loads(s_clean)
        
        # 确保所有必需的标签都有值
        required_labels = {
            # 维度1：知识模块
            "D1_L1": "知识模块", "D1_L2": "未分类", "D1_L3": "未分类", "D1_L4": "未分类",
            # 维度2：认知操作
            "D2_L1": "认知操作", "D2_L2": "未分类", "D2_L3": "未分类",
            # 维度3：解题策略
            "D3_L1": "解题策略", "D3_L2": "未分类", "D3_L3": "未分类",
            # 维度4：数学思想
            "D4_L1": "数学思想", "D4_L2": "未分类", "D4_L3": "未分类",
            # 维度5：作答形式
            "D5_L1": "作答形式", "D5_L2": "未分类", "D5_L3": "未分类",
            # 维度6：难度控制
            "D6_L1": "难度控制", "D6_L2": "未分类", "D6_L3": "未分类"
        }
        
        for label, default_value in required_labels.items():
            if label not in obj or not obj[label] or obj[label].strip() == "":
                obj[label] = default_value
                print(f"警告：{label}标签为空，自动设为'{default_value}'")
        
        return obj
    except Exception as e:
        print(f"解析JSON失败: {e}")
        print(f"原始响应: {s}")
        # 返回默认值
        return {
            "D1_L1": "知识模块", "D1_L2": "未分类", "D1_L3": "未分类", "D1_L4": "未分类",
            "D2_L1": "认知操作", "D2_L2": "未分类", "D2_L3": "未分类",
            "D3_L1": "解题策略", "D3_L2": "未分类", "D3_L3": "未分类",
            "D4_L1": "数学思想", "D4_L2": "未分类", "D4_L3": "未分类",
            "D5_L1": "作答形式", "D5_L2": "未分类", "D5_L3": "未分类",
            "D6_L1": "难度控制", "D6_L2": "未分类", "D6_L3": "未分类"
        }

def main():
    questions: List[Dict] = json.load(open(JSON_IN, encoding="utf-8"))
    for q in tqdm(questions, desc="智能标注处理"):
        try:
            prompt = PROMPT_TMPL.format(QUESTION_BLOCK=build_question_block(q))
            # print(prompt)
            raw = call_llm_with_tools(prompt)
            q["label"] = safe_json_line(raw)
    
        except Exception as e:
            print(f"处理题目 {q.get('id', 'unknown')} 时出错: {e}")
            # 设置默认标签
            q["label"] = {
                "D1_L1": "知识点", "D1_L2": "未分类", "D1_L3": "未分类", "D1_L4": "未分类"
            }

    # 输出token使用总量统计
    print("\n===== Token使用统计 =====")
    print(f"提示tokens总计: {total_prompt_tokens}")
    print(f"完成tokens总计: {total_completion_tokens}")
    print(f"总计tokens: {total_tokens}")
    # print(f"估算费用: ${total_prompt_tokens/1000 * 0.0015 + total_completion_tokens/1000 * 0.0045:.4f} (按1000tokens $0.001计算)")
    print("=======================\n")

    print(json.dumps(questions, ensure_ascii=False, indent=2))
    # json.dump(questions, open(JSON_OUT,"w",encoding="utf8"),
    #           ensure_ascii=False, indent=2)
    # print(f"共处理 {len(questions)} 道题。")

if __name__ == "__main__":
    main()
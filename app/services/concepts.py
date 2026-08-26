from __future__ import annotations

import re
from typing import Any


# The active catalog follows the Math II syllabus: calculus through ordinary
# differential equations, plus the six linear-algebra chapters.  The keyword
# rules are deliberately conservative; source questions can still carry an
# out-of-syllabus tag without entering the adaptive Math II blocks.
MATH2_CONCEPTS: list[dict[str, Any]] = [
    {
        "id": "limit-continuity",
        "name": "极限与连续",
        "subject": "高等数学",
        "keywords": ["极限", "连续", "无穷小", "无穷大", "间断"],
    },
    {
        "id": "derivative",
        "name": "一元函数微分学",
        "subject": "高等数学",
        "keywords": ["导数", "可导", "可微", "切线", "单调", "极值", "凹凸", "曲率"],
    },
    {
        "id": "integral",
        "name": "一元函数积分学",
        "subject": "高等数学",
        "keywords": ["积分", "\\int", "原函数", "不定积分", "定积分", "反常积分", "变限积分", "积分上限", "积分中值定理", "牛顿-莱布尼茨", "换元积分", "分部积分", "旋转体", "平面图形的面积", "弧长"],
    },
    {
        "id": "multivariable",
        "name": "多元函数微分学",
        "subject": "高等数学",
        "keywords": ["偏导", "全微分", "多元函数", "多元复合", "隐函数", "二元函数", "多元极值"],
    },
    {
        "id": "multiple-integral",
        "name": "二重积分",
        "subject": "高等数学",
        "keywords": ["二重积分", "二重积分的概念", "二重积分的计算", "积分区域", "\\iint", "\\int\\int"],
    },
    {
        "id": "differential-equation",
        "name": "常微分方程",
        "subject": "高等数学",
        # Do not use generic words such as "通解" or "齐次方程" here:
        # linear-algebra questions also ask for a general solution and use
        # the phrase "齐次线性方程组".  The explicit chapter phrase is the
        # reliable boundary for source-level concept tagging.
        "keywords": ["微分方程"],
    },
    {
        "id": "matrix",
        "name": "行列式与矩阵",
        "subject": "线性代数",
        "keywords": ["矩阵", "行列式", "初等变换", "逆矩阵", "伴随矩阵", "分块矩阵"],
    },
    {
        "id": "linear-equation",
        "name": "线性方程组",
        "subject": "线性代数",
        "keywords": ["线性方程组", "齐次线性方程组", "非齐次线性方程组", "克拉默", "基础解系"],
    },
    {
        "id": "vector-space",
        "name": "向量组与线性相关性",
        "subject": "线性代数",
        "keywords": ["向量组", "线性组合", "线性表示", "线性相关", "线性无关", "极大线性无关组", "等价向量组", "向量组的秩", "内积", "正交规范化", "施密特"],
    },
    {
        "id": "eigenvalue",
        "name": "特征值、特征向量与二次型",
        "subject": "线性代数",
        "keywords": ["特征值", "特征向量", "相似矩阵", "相似对角化", "二次型", "正定", "合同矩阵", "惯性定理"],
    },
]


# These labels are intentionally kept outside the active catalog.  They let
# the library retain and explain source questions that are outside the Math II
# syllabus, without turning them into adaptive Math II training blocks.
OUT_OF_SYLLABUS_CONCEPTS: list[dict[str, Any]] = [
    {
        "id": "series",
        "name": "无穷级数",
        "subject": "非数学二范围",
        "scope_note": "数学一、数学三相关范围",
        "keywords": ["级数", "幂级数", "傅里叶级数", "收敛半径", "收敛区间"],
    },
    {
        "id": "vector-calculus",
        "name": "向量代数与空间解析几何",
        "subject": "非数学二范围",
        "scope_note": "数学一相关范围；数学三不考此部分",
        "keywords": ["向量积", "混合积", "方向余弦", "空间解析几何", "空间曲线", "空间直线", "曲面方程", "空间曲面", "曲线积分", "曲面积分", "格林公式", "高斯公式", "斯托克斯公式", "散度", "旋度"],
    },
    {
        "id": "triple-integral",
        "name": "三重积分",
        "subject": "非数学二范围",
        "scope_note": "数学一相关范围；数学二不考",
        "keywords": ["三重积分"],
    },
    {
        "id": "vector-space-extra",
        "name": "向量空间、基与维数",
        "subject": "非数学二范围",
        "scope_note": "数学一、数学三相关范围；数学二不要求",
        "keywords": ["向量空间", "过渡矩阵", "规范正交基", "基与维数", "基、维数", "向量空间的基", "向量空间的维数"],
    },
    {
        "id": "multivariable-extra",
        "name": "方向导数、梯度与拉格朗日乘数",
        "subject": "非数学二范围",
        "scope_note": "数学一、数学三大纲差异内容",
        "keywords": ["方向导数", "梯度", "拉格朗日乘数", "法平面", "切平面"],
    },
    {
        "id": "differential-equation-extra",
        "name": "数学一/三扩展微分方程",
        "subject": "非数学二范围",
        "scope_note": "数学一、数学三大纲差异内容",
        "keywords": ["伯努利方程", "全微分方程", "欧拉方程", "差分方程", "微分方程组"],
    },
    {
        "id": "probability",
        "name": "概率基础",
        "subject": "非数学二范围",
        "scope_note": "数学一、数学三范围；数学二不考概率论",
        "keywords": ["概率", "事件", "条件概率", "独立", "贝叶斯"],
    },
    {
        "id": "random-variable",
        "name": "随机变量及其分布",
        "subject": "非数学二范围",
        "scope_note": "数学一、数学三范围；数学二不考概率论",
        "keywords": ["随机变量", "分布函数", "概率密度", "分布律", "随机向量"],
    },
    {
        "id": "expectation-variance",
        "name": "随机变量的数字特征",
        "subject": "非数学二范围",
        "scope_note": "数学一、数学三范围；数学二不考概率论",
        "keywords": ["数学期望", "方差", "协方差", "相关系数"],
    },
    {
        "id": "statistics",
        "name": "数理统计",
        "subject": "非数学二范围",
        "scope_note": "数学一、数学三范围；数学二不考数理统计",
        "keywords": ["样本", "统计量", "参数估计", "点估计", "最大似然", "假设检验", "置信区间"],
    },
]


CONCEPTS = MATH2_CONCEPTS + OUT_OF_SYLLABUS_CONCEPTS
CONCEPT_META = {item["id"]: (item["name"], item["subject"]) for item in MATH2_CONCEPTS}
CONCEPT_DISPLAY_META = {item["id"]: item for item in CONCEPTS}
MATH2_CONCEPT_IDS = frozenset(item["id"] for item in MATH2_CONCEPTS)
OUT_OF_SYLLABUS_CONCEPT_IDS = frozenset(item["id"] for item in OUT_OF_SYLLABUS_CONCEPTS)


def concept_descriptor(concept_id: str) -> dict[str, str]:
    item = CONCEPT_DISPLAY_META.get(concept_id)
    if item is None:
        return {
            "id": concept_id,
            "name": concept_id,
            "subject": "未分类",
            "scope": "unknown",
            "scope_label": "未标注范围",
            "scope_note": "来源标签未纳入当前分类表",
        }
    is_math2 = concept_id in MATH2_CONCEPT_IDS
    return {
        "id": concept_id,
        "name": item["name"],
        "subject": item["subject"],
        "scope": "math2" if is_math2 else "out-of-syllabus",
        "scope_label": "数学二大纲" if is_math2 else "非数学二范围",
        "scope_note": item.get("scope_note", "数学二考试大纲范围"),
    }


def infer_concepts(text: str, section: str) -> list[str]:
    text = str(text or "")
    section = str(section or "")
    compact = re.sub(r"\s+", "", text.lower())
    active: list[str] = []
    extra: list[str] = []
    integral_core = ["原函数", "不定积分", "定积分", "反常积分", "变限积分", "积分上限", "积分中值定理", "牛顿-莱布尼茨", "换元积分", "分部积分", "旋转体", "平面图形的面积", "弧长"]
    non_single_integral = ["二重积分", "三重积分", "曲线积分", "曲面积分", "格林公式", "高斯公式", "斯托克斯公式"]
    for concept in MATH2_CONCEPTS:
        if concept["id"] == "integral" and any(item in text for item in non_single_integral) and not any(item in text for item in integral_core):
            continue
        if any(keyword in text for keyword in concept["keywords"]):
            active.append(concept["id"])

    # Older source pages often put the entire stem in a formula and therefore
    # do not contain the Chinese word "极限" or "导数".  Add only high-signal
    # structural cues here so the chapter filter is not driven by the source
    # section heading alone.
    if ("\\lim" in compact or "lim_{" in compact or "趋于" in text or "趋近" in text or re.search(r"[a-z]_\{?n\}?", text, re.IGNORECASE)) and "limit-continuity" not in active:
        active.append("limit-continuity")
    if ("\\iint" in compact or "\\int\\int" in compact or "二重积分" in text) and "multiple-integral" not in active:
        active.append("multiple-integral")
    if ("\\begin{pmatrix}" in compact or "\\begin{bmatrix}" in compact or "行列式" in text or "矩阵" in text) and "matrix" not in active:
        active.append("matrix")
    if ("\\partial" in compact or "偏导" in text or "全微分" in text) and "multivariable" not in active:
        active.append("multivariable")
    if ("线性方程组" in text or "齐次线性方程组" in text or "非齐次线性方程组" in text) and "linear-equation" not in active:
        active.append("linear-equation")
    if ("特征值" in text or "特征向量" in text or "二次型" in text) and "eigenvalue" not in active:
        active.append("eigenvalue")
    if any(marker in text for marker in ("有界函数", "无界函数", "周期函数", "奇函数", "偶函数", "定义域", "函数关系")) and "limit-continuity" not in active:
        active.append("limit-continuity")
    if re.search(r"(?:y|f)\s*\^\s*\{?\\?prime", text, re.IGNORECASE) and "derivative" not in active:
        active.append("derivative")
    if any(marker in text for marker in ("速度", "路程", "距离", "运动的路程", "平均值", "功", "压力", "质心", "形心", "面积", "弧长", "极坐标方程")) and "integral" not in active:
        active.append("integral")
    if any(marker in text for marker in ("f[x]", "f[f(", "f\\left[f", "f\\left\\{", "f(-x)", "f\\left(-x", "分段函数", "复合函数", "函数复合")) and "limit-continuity" not in active:
        active.append("limit-continuity")
    if any(marker in text for marker in ("f'_x", "f'_y", "偏导", "二元函数", "f(x,y)", "f(x, y)")) and "multivariable" not in active:
        active.append("multivariable")
    if any(marker in text for marker in ("合同", "正交矩阵", "正交变换")) and "eigenvalue" not in active:
        active.append("eigenvalue")
    if any(marker in text for marker in ("变化率与", "成正比", "冷却", "减速", "人口模型")) and "differential-equation" not in active:
        active.append("differential-equation")
    if any(marker in text for marker in ("向量", "向量组", "线性表示", "线性相关", "线性无关")) and "vector-space" not in active:
        active.append("vector-space")
    if any(marker in text for marker in ("质量", "油罐", "速率", "曲线所围成的图形", "曲线的面积")) and "integral" not in active:
        active.append("integral")
    if any(marker in text for marker in ("速率", "变化率", "dy", "d}y", "导数")) and "derivative" not in active:
        active.append("derivative")
    if any(marker in text for marker in ("最长距离", "最短距离", "最大距离", "最小距离")) and "multivariable" not in active:
        active.append("multivariable")
    if "相似" in text and "eigenvalue" not in active:
        active.append("eigenvalue")
    if "方程组" in text and "linear-equation" not in active:
        active.append("linear-equation")
    if re.search(r"(?:\\boldsymbol\{?a|a)_\{?\d", text, re.IGNORECASE) or "\\boldsymbol{a}_{" in text:
        if "vector-space" not in active:
            active.append("vector-space")
    if re.search(r"\\mathrm\{?d\}?", text) and "derivative" not in active:
        active.append("derivative")
    for concept in OUT_OF_SYLLABUS_CONCEPTS:
        if any(keyword in text for keyword in concept["keywords"]):
            extra.append(concept["id"])

    if not active and not extra:
        if "线代" in section or "线性" in section:
            active.append("matrix")
        elif "概率" in section:
            extra.append("probability")
        else:
            active.append("derivative")
    # Keep both the in-syllabus topic and the precise out-of-syllabus marker
    # when a source question crosses the boundary.  Six tags are enough for
    # display while avoiding the old four-tag truncation.
    return (active + extra)[:6]

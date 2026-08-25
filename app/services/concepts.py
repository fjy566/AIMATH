from __future__ import annotations

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
        "keywords": ["导数", "微分", "切线", "单调", "极值", "凹凸", "曲率"],
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
        "keywords": ["微分方程", "特征根", "通解", "齐次方程", "可降阶"],
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
    active: list[str] = []
    extra: list[str] = []
    integral_core = ["原函数", "不定积分", "定积分", "反常积分", "变限积分", "积分上限", "积分中值定理", "牛顿-莱布尼茨", "换元积分", "分部积分", "旋转体", "平面图形的面积", "弧长"]
    non_single_integral = ["二重积分", "三重积分", "曲线积分", "曲面积分", "格林公式", "高斯公式", "斯托克斯公式"]
    for concept in MATH2_CONCEPTS:
        if concept["id"] == "integral" and any(item in text for item in non_single_integral) and not any(item in text for item in integral_core):
            continue
        if any(keyword in text for keyword in concept["keywords"]):
            active.append(concept["id"])
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

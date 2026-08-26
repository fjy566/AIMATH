from __future__ import annotations

from typing import Any, Iterable

from app.services.concepts import CONCEPT_META, MATH2_CONCEPTS, MATH2_CONCEPT_IDS, concept_descriptor


QUESTION_TYPES = ("choice", "fill", "solution")
QUESTION_TYPE_LABELS = {"choice": "选择题", "fill": "填空题", "solution": "解答题"}


def _topic(
    subtype_id: str,
    name: str,
    goal: str,
    conditions: str,
    method: str,
    check: str,
    signals: tuple[str, ...],
    memory_aid: str,
) -> dict[str, Any]:
    return {
        "id": subtype_id,
        "name": name,
        "summary": goal,
        "overview": f"本题型围绕{name}展开，核心任务是{goal}。作答时要把定理条件、目标形式和结论方向连成一条可核验的推理链。",
        "framework": [
            f"识别题型：看到与{name}有关的条件后，先把题目目标改写为“{goal}”。",
            f"核对前提：逐项确认{conditions}，不满足时先补构造或分情况讨论。",
            f"执行主线：{method}",
            f"收尾复核：{check}，再单独写出题目要求的结论。",
        ],
        "mistakes": [
            f"没有检查{conditions}，直接套用结论。",
            f"主步骤应当是“{method}”，却只写公式或跨过关键构造，导致得分点不可见。",
            f"结尾没有完成“{check}”，出现范围、符号、维数或充分必要性错误。",
        ],
        "memory_aid": memory_aid,
        "signals": signals,
    }


SUBTYPE_CATALOG: dict[str, list[dict[str, Any]]] = {
    "limit-continuity": [
        _topic("function-properties", "函数性质与函数关系建立", "判断定义域、奇偶性、周期性、单调性并建立函数关系", "定义域、对应法则和自变量范围", "先化简解析式或按区间拆分，再逐项验证函数性质；应用题先定义变量并写出约束。", "把结论代回原定义域，并检查分段点和端点", ("定义域", "奇函数", "偶函数", "周期", "单调", "函数关系"), "性质判断先回到定义，不能只看图像印象。"),
        _topic("sequence-limit", "数列极限与递推数列", "求数列极限或证明递推数列收敛", "单调性、有界性和极限方程可解性", "显式数列先做等价变形；递推数列先证单调有界，再令极限为 A 解极限方程。", "排除极限方程中的增根，并验证初值所在区间", ("数列", "a_n", "x_n", "递推", "单调有界", "数项"), "递推极限：先证存在，再解方程。"),
        _topic("function-limit", "函数极限与左右极限", "计算函数极限或依据左右极限判定极限存在", "趋近方向、定义域和分母非零条件", "先判型，再选择约分、有理化、变量替换或左右分开计算。", "左右极限一致且结果满足原趋近条件", ("左极限", "右极限", "x\\to", "趋于", "函数极限", "极限存在"), "先判型，后变形；分段点必须看左右。"),
        _topic("equivalent-infinitesimal", "等价无穷小与阶的比较", "用等价替换或阶数比较化简极限", "各因子都处于同一极限过程且替换位置允许", "把基本等价无穷小拆成乘除因子，必要时先提取主部，再比较阶数。", "替换没有发生在加减项内部，并核对常数系数", ("等价无穷小", "无穷小", "高阶", "低阶", "同阶", "o(", "主部"), "乘除可替换，加减先提主部。"),
        _topic("important-limits", "重要极限与夹逼准则", "识别标准结构并用重要极限、夹逼或单调有界准则求极限", "变量确实趋于标准点且底数保持有意义", "把表达式改造成正弦型或 1 的无穷次幂型；不便改造时寻找上下界夹逼。", "指数、底数和替换变量的趋向全部一致", ("重要极限", "夹逼", "单调有界", "sin x", "1+", "无穷次幂"), "标准结构要完整，底数和指数一起看。"),
        _topic("continuity-discontinuity", "连续性与间断点分类", "确定连续参数、判别间断点并区分类型", "函数值、左右极限及极限与函数值的关系", "在可疑点分别求左极限、右极限和函数值，按三者关系分类。", "列出全部间断点并写明可去、跳跃或无穷等类型", ("连续", "间断点", "可去", "跳跃", "左连续", "右连续"), "三件套：左极限、右极限、函数值。"),
        _topic("closed-interval-theorems", "闭区间连续函数性质", "应用有界、最值、零点和介值性质证明存在性", "函数在闭区间连续以及端点值满足所需关系", "根据目标选择最值定理、零点定理或介值定理，明确写出区间和端点信息。", "存在性结论落在题目要求的开区间或闭区间内", ("零点定理", "介值", "最大值", "最小值", "闭区间", "至少存在"), "闭区间连续给性质，端点关系定结论。"),
    ],
    "derivative": [
        _topic("derivative-definition", "导数定义与可导性", "用差商极限求导或判断连续、可导与可微关系", "差商中的基点、增量和双侧极限", "写出定义差商，分段点分别考察左右导数，再比较连续性与可导性。", "左右导数相等且函数在该点连续", ("导数定义", "差商", "左导数", "右导数", "可导", "可微"), "分段点可导：连续加左右导数相等。"),
        _topic("differentiation-techniques", "复合、隐函数与参数方程求导", "正确计算复合函数、隐函数或参数方程确定函数的导数", "各层函数可导且参数导数分母不为零", "画出依赖层次，逐层链式求导；隐函数保留 y'，参数方程用 dy/dx=(dy/dt)/(dx/dt)。", "导数最终回到题目变量并检查漏乘内层导数", ("隐函数", "参数方程", "复合函数", "反函数", "dy", "dx", "链式"), "复合逐层乘，隐函数见 y 就带 y'。"),
        _topic("higher-derivative", "高阶导数与莱布尼茨公式", "求高阶导数或指定点的高阶导数值", "函数具有所需阶数的导数", "识别周期型导数、幂级规律或使用莱布尼茨公式，先写通项再代入阶数。", "阶数下标、组合数和符号周期正确", ("高阶导数", "n阶导数", "莱布尼茨", "f^{(", "二阶导数", "三阶导数"), "先找导数循环，再写第 n 阶。"),
        _topic("tangent-normal-curvature", "切线、法线与曲率", "求曲线切法线、曲率或曲率半径", "曲线在目标点可导，曲率题还需二阶导数", "先求点坐标和斜率，再写直线；曲率按参数式或显函数公式代入。", "竖直切线、法线斜率和绝对值没有遗漏", ("切线", "法线", "曲率", "曲率半径", "斜率", "切点"), "先点后斜率，竖直情形单独判。"),
        _topic("rolle-theorem", "罗尔定理的应用", "构造端点等值的辅助函数并证明区间内导数为零", "闭区间连续、开区间可导、两端函数值相等", "把待证等式整理成 F'(ξ)=0，反推辅助函数 F，再验证罗尔定理三项条件。", "ξ 位于指定开区间，辅助函数端点确实相等", ("罗尔", "rolle", "导数为0", "导数为零", "f'(ξ)=0"), "端点等值找罗尔，目标导数反推辅助函数。"),
        _topic("lagrange-mvt", "拉格朗日中值定理的应用", "把函数增量表示成某点导数乘区间长度并用于估值或证明", "闭区间连续、开区间可导", "选定两个端点，写 f(b)-f(a)=f'(ξ)(b-a)，再结合导数范围或目标式变形。", "区间方向、ξ 的范围和导数估计方向一致", ("拉格朗日", "lagrange", "中值定理", "f(b)-f(a)", "函数增量"), "函数差配导数，两个端点定区间。"),
        _topic("cauchy-taylor", "柯西中值定理与泰勒公式", "处理两个函数增量之比、带余项展开或高阶局部估计", "柯西定理的分母导数不为零，泰勒展开点和阶数明确", "比值问题构造两个函数用柯西定理；局部高阶问题选展开点并保留足够阶的余项。", "余项阶数足够且展开范围覆盖目标点", ("柯西", "cauchy", "泰勒", "taylor", "余项", "麦克劳林", "展开"), "两个增量用柯西，局部高阶用泰勒。"),
        _topic("lhopital-limit", "洛必达法则求未定式极限", "把极限化为允许的未定式并通过分子分母求导求值", "确为 0/0 或无穷/无穷型，邻域内分母导数不为零", "先判未定式，乘积、差式或幂指式先改写成商，再逐次使用洛必达。", "每次求导后仍核对型，不能对和式逐项使用法则", ("洛必达", "l'hospital", "0/0", "无穷/无穷", "未定式"), "洛必达先验型，幂指式先取对数。"),
        _topic("monotonicity-extrema", "单调性、极值与最值", "用导数符号划分单调区间并求极值或最值", "驻点、不可导点和区间端点完整", "求导并列出临界点，制作符号表；最值题还要比较端点和所有候选值。", "区间开闭、极值点与极值、最值点与最值不混淆", ("单调区间", "单调性", "极值", "最大值", "最小值", "驻点"), "单调看符号，极值看变号，最值还比端点。"),
        _topic("concavity-asymptote", "凹凸、拐点、渐近线与图形", "利用一二阶导数和极限分析函数图形", "定义域、不可导点和无穷远行为完整", "先定定义域和渐近线，再用一阶导数判增减、二阶导数判凹凸，最后汇总关键点。", "拐点要求函数连续且凹凸性改变，斜渐近线同时求斜率和截距", ("凹凸", "拐点", "渐近线", "函数图形", "斜渐近线", "描绘"), "先定义域和渐近线，再一阶增减、二阶凹凸。"),
        _topic("zeros-differential-inequality", "零点问题与微分不等式", "证明方程根的个数、导数零点关系或函数不等式", "连续性、可导性以及端点或初值条件", "存在性用零点或罗尔，唯一性用单调性；不等式构造差函数后研究导数符号。", "存在与唯一分别证明，不等号方向覆盖整个目标区间", ("零点", "根的个数", "唯一根", "微分不等式", "证明不等式", "至多"), "存在看端点，唯一看单调，不等式看差函数。"),
    ],
    "integral": [
        _topic("antiderivative-basic", "原函数与基本不定积分", "依据导数反查原函数并完成基本积分", "被积函数在讨论区间有意义", "先拆项和提常数，再套基本积分公式，必要时配凑微分。", "不定积分补常数 C，并回求导核验", ("原函数", "不定积分", "积分常数", "+c", "基本积分"), "不定积分最后一定写 C。"),
        _topic("substitution-integration", "换元积分法", "通过第一类或第二类换元把积分化为基本型", "换元关系单调可逆或微分替换完整", "识别复合内层或根式结构，选择变量替换并同步替换微分与定积分上下限。", "所有旧变量消失，定积分不用重复换回原变量", ("换元", "令", "代换", "变量替换", "作变换"), "变量、微分、上下限三项一起换。"),
        _topic("integration-by-parts", "分部积分与递推积分", "降低乘积中某一因子的复杂度或建立积分递推式", "u 与 dv 的选择能使后续积分更简单", "按反对幂三指的优先次序选 u，写出 uv-∫vdu；重复型积分可设元并移项。", "边界项、负号和重复积分移项系数正确", ("分部积分", "递推公式", "积分递推", "uv", "反对幂三指"), "分部积分看降阶，边界项先代再减。"),
        _topic("special-integrals", "有理式、三角有理式与根式积分", "把特殊被积函数化成可积的部分分式或标准三角形式", "分母分解、根式定义域和三角替换范围正确", "有理式先因式分解并作部分分式；三角有理式用万能代换；根式按标准结构选换元。", "拆分系数和换元后的定义域没有改变", ("有理函数", "部分分式", "三角有理", "万能代换", "根式积分"), "先识别结构，再选专用换元。"),
        _topic("definite-properties", "定积分性质、对称性与周期性", "利用区间、奇偶、周期或积分中值性质简化定积分", "积分区间和函数对称中心明确", "先画区间关系，检查奇偶与 f(a+b-x) 型对称，再决定换元、拆区间或使用周期。", "换元后上下限和符号正确，不能把局部对称当全局对称", ("定积分性质", "奇函数", "偶函数", "周期函数", "对称", "积分中值"), "对称积分先看区间中心，再看函数变换。"),
        _topic("variable-upper-limit", "变限积分与积分上限函数", "求变限积分的导数、极限、单调性或相关方程", "被积函数连续且上下限函数可导", "先用链式法则求导，双变限写成两个单上限积分之差；综合题再研究所得导数。", "上下限贡献的正负号和内层导数完整", ("变限积分", "积分上限", "上限函数", "\\int_0^x", "f(t)"), "上限正、下限负，变限还乘内层导数。"),
        _topic("improper-integral", "反常积分计算与敛散性", "判断无穷区间或无界函数积分是否收敛并求值", "所有瑕点和无穷端点分别处理", "拆开每个反常端点，写成极限；敛散判断可用比较、等价或 p 型积分。", "每一段都收敛才可合并，参数范围取所有条件交集", ("反常积分", "广义积分", "敛散", "收敛", "+\\infty", "瑕点"), "反常积分分端点，全部收敛才收敛。"),
        _topic("geometric-integral", "面积、体积与弧长", "用定积分表示并计算平面面积、旋转体体积或曲线弧长", "交点、区间、旋转轴和曲线表示方式明确", "先画示意并求交点，再选直角坐标、参数式或极坐标公式分段积分。", "面积非负，旋转半径和内外半径顺序正确", ("面积", "旋转体", "体积", "弧长", "侧面积", "平面图形"), "先画图定上下，再列积分。"),
        _topic("integral-identity-inequality", "积分等式与积分不等式", "证明积分恒等式、估计积分或证明含积分不等式", "被积函数连续性、符号和单调性条件明确", "等式优先换元、分部或构造变限函数；不等式用最值估计、积分中值或差函数。", "不等号方向与函数符号一致，等号成立条件完整", ("积分等式", "积分不等式", "证明", "估计", "等号成立"), "积分等式找变换，不等式先看符号和界。"),
        _topic("physical-average-integral", "定积分的物理量与平均值", "计算功、压力、质心、形心或函数平均值", "微元含义、密度或受力函数及积分区间明确", "选择位置变量，写出微元对应的物理量，再在完整范围积分；平均值最后除以区间长度或总质量。", "单位、微元系数和归一化分母正确", ("平均值", "功", "压力", "质心", "形心", "引力", "物理"), "先写微元，再积分；平均值别忘除总量。"),
    ],
    "multivariable": [
        _topic("partial-full-differential", "偏导数与全微分", "计算偏导、全微分或判断多元函数可微性", "定义域、偏导存在性和可微条件", "求偏导时固定其他变量；可微判断用增量减去线性主部后除以距离取极限。", "偏导存在不等于可微，特殊点必须回到定义", ("偏导", "全微分", "可微", "偏导数", "dz", "增量"), "偏导是必要信息，可微还要验余项。"),
        _topic("multivariable-chain", "多元复合函数链式求导", "沿变量依赖图计算复合函数的一阶或二阶偏导", "所有中间变量的依赖关系清楚", "画依赖树，对每条从目标到自变量的路径求导并相加；二阶导继续对每项求导。", "遗漏路径、混淆固定变量或重复乘导数", ("复合函数", "链式", "z=", "u=", "v=", "偏导"), "多元链式：每条路径相乘，所有路径相加。"),
        _topic("implicit-partial", "多元隐函数求导", "由方程组确定的隐函数求一阶或二阶偏导", "相应雅可比或目标偏导分母不为零", "对方程两边关于目标变量求偏导，收集未知偏导并解出；方程组可写成线性系统。", "分母条件和二阶求导中的乘积项完整", ("隐函数", "方程组确定", "f(x", "偏导", "雅可比"), "隐函数先整体求导，再解未知偏导。"),
        _topic("multivariable-extrema", "多元函数极值与条件极值", "求二元函数极值、最值或拉格朗日条件极值", "驻点完整，闭区域还要检查边界", "无约束题解梯度为零并用 Hessian 判别；约束题构造拉格朗日函数，边界与内部统一比较。", "判别式等于零时不能强判，最值题不能漏边界和角点", ("条件极值", "拉格朗日乘数", "多元", "极值", "驻点"), "内部看梯度与 Hessian，约束看乘子，最值还查边界。"),
    ],
    "multiple-integral": [
        _topic("double-region-order", "积分区域、换序与分块", "把积分限还原为区域并改写积分次序", "区域边界、交点和投影范围明确", "先画区域，写成 x 型或 y 型区域；边界切换处必须分块，再按新次序写上下限。", "新积分区域与原区域完全相同，没有漏块或重叠", ("交换积分次序", "换序", "积分区域", "累次积分", "改写"), "换序先画区域，边界变点就分块。"),
        _topic("double-cartesian", "直角坐标二重积分", "在矩形或一般平面区域上计算二重积分", "区域能正确表示为累次积分", "先判断是否可拆成乘积，不能则按区域边界选更简洁的积分次序逐层积分。", "内层积分变量和外层上下限一致", ("二重积分", "直角坐标", "累次积分", "区域d", "dxdy", "dydx"), "内层先算谁，上下限就不能含谁。"),
        _topic("double-polar", "极坐标二重积分", "利用圆域、扇形或径向结构化简二重积分", "区域关于原点或某中心适合极坐标表示", "写 x=r cosθ、y=r sinθ 和面积元 r dr dθ，按射线与边界交点确定 r 范围。", "面积元中的 r、角度范围和负半径问题正确", ("极坐标", "rdr", "r dr", "圆域", "扇形", "x^2+y^2"), "极坐标三件套：变量、区域、面积元 r。"),
        _topic("double-symmetry", "二重积分的对称性", "利用区域和被积函数的奇偶或轮换对称快速计算", "区域关于坐标轴、原点或变量交换保持不变", "把被积函数拆成对称与反对称部分，分别使用轴对称、中心对称或 x-y 轮换。", "对称的是区域和测度，不只看被积函数外观", ("对称性", "关于x轴", "关于y轴", "关于原点", "交换x,y", "轮换对称"), "先验区域对称，再判函数变号。"),
        _topic("double-application", "二重积分的几何与物理应用", "计算平面薄片质量、质心或曲顶柱体体积", "区域、密度函数和高度函数明确", "先确定面积微元，再分别列质量、一阶矩或体积积分，必要时利用对称性。", "质心分母为总质量，密度和高度没有混用", ("曲顶柱体", "质量", "质心", "薄片", "体积", "二重积分"), "面积元乘什么，取决于要求的物理量。"),
    ],
    "differential-equation": [
        _topic("separable-homogeneous-ode", "可分离变量与齐次一阶方程", "识别并求解可分离变量或可化齐次的一阶方程", "分离过程中没有除掉可能的常值解", "可分离方程把 y 项与 x 项分居两侧；齐次方程令 y=ux 后化为可分离形式。", "补回被除掉的特解，并用初值确定常数", ("可分离", "分离变量", "齐次方程", "y/x", "y=ux"), "能分则分，齐次一阶先令 y=ux。"),
        _topic("first-order-linear-ode", "一阶线性微分方程", "用通解公式或常数变易法求一阶线性方程", "方程已化为 y'+P(x)y=Q(x) 标准形", "求积分因子 e^{∫Pdx}，将左端化为乘积导数后积分。", "P 的符号、积分因子和积分常数正确", ("一阶线性", "积分因子", "y'+", "常数变易", "通解公式"), "先标准化，再找积分因子。"),
        _topic("bernoulli-ode", "伯努利方程", "通过幂代换把非线性一阶方程化为线性方程", "方程具有 y'+P(x)y=Q(x)y^n 且 n 不为 0、1", "除以 y^n 后令 z=y^{1-n}，化成关于 z 的一阶线性方程。", "代换指数、常值解和还原 y 的范围正确", ("伯努利", "bernoulli", "y^n", "非线性"), "伯努利的目的只有一个：幂代换化线性。"),
        _topic("reducible-higher-ode", "可降阶高阶微分方程", "对不显含 y、x 或特定导数的高阶方程降阶", "方程缺失变量的结构识别正确", "不含 y 时令 p=y'；不含 x 时令 p(y)=y' 并用 y''=p dp/dy；逐次积分恢复 y。", "每降一阶都补一个积分常数", ("可降阶", "不含y", "不含x", "p=y'", "高阶微分方程"), "缺谁就围绕谁换元，降几阶补几个常数。"),
        _topic("constant-coefficient-ode", "常系数线性微分方程", "求二阶常系数齐次或非齐次方程通解", "特征方程和非齐次项类型识别正确", "先由特征根写齐次通解，再按指数、多项式、三角型设特解；共振时乘足够次 x。", "重根、复根和共振次数正确，通解为齐次解加特解", ("常系数", "特征方程", "特征根", "非齐次", "二阶线性", "共振"), "先齐次后特解，共振就乘 x。"),
        _topic("ode-modeling", "微分方程建模与综合应用", "根据变化率、几何关系或物理过程建立并求解方程", "状态量、独立变量、初值和单位明确", "把题目中的变化率关系翻译成微分方程，求通解后利用初值或边界条件定常数。", "解满足原模型范围、初值和单位", ("建立微分方程", "变化率", "初始条件", "初值问题", "应用问题"), "先列变化率关系，再解方程和代初值。"),
    ],
    "matrix": [
        _topic("determinant-properties", "行列式性质与展开计算", "利用行列式性质、按行列展开或递推计算行列式", "变换对行列式数值的影响记录完整", "优先制造零元素，再按最简行列展开；特殊结构可递推、加边或拆项。", "换行变号、倍乘因子和展开符号正确", ("行列式", "按行展开", "按列展开", "代数余子式", "det"), "行列式变换每一步都记倍数和符号。"),
        _topic("abstract-determinant", "抽象行列式与伴随关系", "由矩阵关系、特征值或伴随矩阵计算行列式", "矩阵阶数和可逆条件明确", "对矩阵等式两边取行列式，使用 |AB|=|A||B|、|A*|=|A|^{n-1} 等关系。", "常数矩阵的行列式要按 n 次幂处理", ("抽象行列式", "伴随矩阵", "|ab|", "det", "行列式"), "矩阵等式取行列式，常数别忘 n 次方。"),
        _topic("matrix-operations-powers", "矩阵运算与矩阵幂", "完成矩阵乘法、转置、分块运算或求矩阵幂", "矩阵维数匹配且乘法顺序固定", "先识别对角、三角、幂等、秩一或可对角化结构，再选择直接乘、递推或分解。", "矩阵乘法不可交换，转置会反转乘积顺序", ("矩阵乘法", "矩阵的幂", "a^n", "转置", "分块矩阵", "幂等"), "先看结构再算幂，矩阵乘法守顺序。"),
        _topic("inverse-adjugate", "逆矩阵与伴随矩阵", "判断可逆并求逆矩阵或处理伴随矩阵关系", "方阵且行列式非零或秩满", "优先用初等变换求逆；低阶可用 A^{-1}=A*/|A|，抽象题结合 AA*=|A|E。", "可逆条件、伴随矩阵阶数和常数倍关系正确", ("逆矩阵", "可逆", "伴随矩阵", "a^{-1}", "aa*"), "先判可逆，再选初等变换或伴随公式。"),
        _topic("elementary-transform", "初等变换与初等矩阵", "用初等行列变换化简矩阵或解释矩阵等价", "行变换与列变换的目标及对应乘法方向明确", "求秩和解方程组用行变换；处理等价或标准形时记录主元位置和变换矩阵。", "不能在同一推导中无说明地混用行变换和列变换", ("初等变换", "初等矩阵", "行变换", "列变换", "等价矩阵"), "行变换管左乘，列变换管右乘。"),
        _topic("matrix-rank", "矩阵秩与参数秩", "求矩阵秩或确定参数使秩满足条件", "主元个数、非零子式和参数特殊值完整", "一般参数先消元，遇到可能为零的主元时分情况；也可用非零子式给下界。", "所有参数分支覆盖且秩不超过矩阵维数", ("矩阵的秩", "秩为", "r(a)", "rank", "最高阶非零子式"), "消元遇参数主元，必须分零与非零。"),
        _topic("block-matrix-equation", "分块矩阵与矩阵方程", "利用分块结构化简乘法、求逆或解 AX=B", "分块尺寸相容且相关子块可逆", "按块做矩阵运算；矩阵方程优先用初等变换或可逆矩阵左乘、右乘，严格保持顺序。", "块乘法尺寸、逆矩阵位置和左右乘顺序正确", ("分块矩阵", "矩阵方程", "ax=", "xa=", "块矩阵"), "分块先验尺寸，矩阵方程分清左乘和右乘。"),
    ],
    "linear-equation": [
        _topic("homogeneous-system", "齐次线性方程组", "判断非零解、求基础解系和通解", "系数矩阵秩与未知量个数明确", "行化简找主元和自由变量，基础解系向量个数为 n-r(A)，通解写线性组合。", "基础解系线性无关且确实满足 Ax=0", ("齐次方程组", "非零解", "基础解系", "ax=0", "自由变量"), "齐次解空间维数等于未知数个数减秩。"),
        _topic("nonhomogeneous-system", "非齐次线性方程组", "判断有解、唯一解或无穷多解并写通解", "系数矩阵与增广矩阵的秩比较完整", "同时化简增广矩阵；秩相等有解，再由秩与未知量个数判断唯一或无穷多。", "通解写成一个特解加齐次通解", ("非齐次方程组", "增广矩阵", "有解", "无解", "唯一解", "无穷多解"), "先比两秩判有解，再看未知数判解数。"),
        _topic("parameter-system", "含参数方程组与解的结构", "确定参数使方程组满足指定解的个数或关系", "所有可能改变秩的参数值都单独讨论", "对增广矩阵消元，含参数主元先保留；按零与非零分支比较秩并写对应解。", "参数分支无遗漏，特殊值不能代入一般分支公式", ("参数", "方程组", "唯一解", "无穷多解", "无解", "取何值"), "参数主元一旦可能为零，就必须分情况。"),
        _topic("common-equivalent-systems", "公共解、同解与方程组反问题", "处理两个方程组的公共解、同解或由解反求系数", "公共解需同时满足两组方程，同解要求解集完全相同", "公共解联立增广；同解比较行空间或用互相线性表示；反问题把给定解代入并结合秩。", "不能把存在公共解误写成两个方程组同解", ("公共解", "同解", "解集相同", "同时满足", "反求"), "公共解是交集，同解是两个解集完全相等。"),
    ],
    "vector-space": [
        _topic("linear-combination", "向量线性表示", "判断一个向量能否由向量组线性表示并求表示系数", "向量维数一致，列向量排列与未知系数对应", "把表示关系写成矩阵方程 Ax=b，用秩判定可表示性并解系数。", "系数顺序与原向量组顺序一致", ("线性表示", "表示为", "向量组", "表示系数", "组合"), "线性表示就是把向量作列组成方程组。"),
        _topic("linear-dependence", "线性相关与线性无关", "判定向量组相关性或利用相关性推导参数关系", "向量个数、维数和零向量情况明确", "解齐次组合方程，只有零解则无关；也可用秩、行列式或向量个数与维数快速判断。", "局部无关与整体无关、添加向量后的结论不混淆", ("线性相关", "线性无关", "相关性", "只有零解", "向量个数"), "相关看非零系数组合为零，无关看只有零解。"),
        _topic("max-independent-rank", "向量组的秩与极大无关组", "求向量组秩、极大无关组及其余向量的表示", "列变换与原向量对应关系得到保留", "把向量作列矩阵只做行变换，主元列对应原向量的极大无关组，再回代表示其余向量。", "不能把化简后矩阵的列直接当作原向量组", ("极大无关组", "向量组的秩", "最大无关组", "主元列"), "求原向量极大无关组，只做行变换并看原主元列。"),
        _topic("vector-relations", "向量组关系与秩的综合", "由两个向量组的线性表示关系比较秩与相关性", "谁能由谁表示、表示矩阵方向和可逆性明确", "写成矩阵关系 B=AP，通过乘积秩不等式比较；若能相互表示或 P 可逆，再推出等价。", "单向可表示只能得到单向秩不等式", ("向量组等价", "相互表示", "秩的关系", "b=ap", "线性表示"), "谁由谁表示，谁的秩不超过谁。"),
    ],
    "eigenvalue": [
        _topic("eigen-computation", "特征值与特征向量计算", "求矩阵特征值、特征向量和特征子空间", "特征方程、重根和每个特征值对应方程完整", "解 |λE-A|=0，再对每个 λ 解 (λE-A)x=0，分别写基础解系。", "不同特征值的向量分组清楚，特征向量不能为零", ("特征值", "特征向量", "特征方程", "λe-a", "特征多项式"), "先特征值，后逐个求特征向量。"),
        _topic("eigen-properties", "特征值性质与反求矩阵", "利用迹、行列式、幂、逆或多项式关系推导特征值", "矩阵阶数、可逆性和多项式作用范围明确", "使用特征值的和等于迹、积等于行列式；A 的多项式对应对特征值作同一多项式。", "重数、零特征值和逆矩阵特征值条件正确", ("特征值的性质", "迹", "tr", "特征值之和", "特征值之积"), "和看迹、积看行列式，多项式直接作用到特征值。"),
        _topic("similar-diagonalization", "相似与可对角化", "判断矩阵是否可相似对角化并求相似变换", "每个特征值的几何重数与代数重数", "求全部特征空间，检查是否有 n 个线性无关特征向量，再按列组成 P 并写 P^{-1}AP=Λ。", "P 的列顺序与对角阵特征值顺序一致", ("相似对角化", "可对角化", "相似矩阵", "p^{-1}ap", "线性无关特征向量"), "能否对角化只看能否凑齐 n 个无关特征向量。"),
        _topic("symmetric-orthogonal", "实对称矩阵正交对角化", "利用实对称矩阵性质求正交矩阵和对角阵", "矩阵实对称，不同特征值向量正交", "求各特征空间，同一特征值内施密特正交化并单位化，按列组成正交矩阵 Q。", "所有列向量单位正交，Q^TAQ 的对角顺序一致", ("实对称矩阵", "正交对角化", "正交矩阵", "施密特", "q^taq"), "实对称必可正交对角化，重根空间内还要正交化。"),
        _topic("quadratic-standard-form", "二次型标准形与规范形", "用正交变换或配方法化二次型为标准形", "二次型矩阵写法中的交叉项系数正确", "先写对称矩阵；正交法用特征值，配方法逐步消交叉项并记录变量变换。", "交叉项系数减半，变换可逆且标准形系数对应正确", ("二次型", "标准形", "规范形", "配方法", "正交变换", "合同"), "交叉项进矩阵要除以二，标准形来自合同变换。"),
        _topic("positive-definite", "正定二次型与正定矩阵", "判断正定性或确定参数使二次型正定", "矩阵实对称", "根据结构选择顺序主子式、特征值或配方法；含参数时逐条联立严格大于零条件。", "正定要求严格大于零，半正定不能混入", ("正定", "正定矩阵", "顺序主子式", "正惯性指数"), "正定三条路：特征值正、顺序主子式正、标准形系数正。"),
        _topic("quadratic-extrema", "二次型最值与合同综合", "在约束下求二次型最值或比较合同、相似关系", "约束集合和矩阵对称性明确", "单位球约束用特征值界定最值；一般约束可用拉格朗日乘子或合同变换化简。", "最值对应向量满足约束，合同与相似的保持量不混淆", ("二次型", "最大特征值", "最小特征值", "合同矩阵", "惯性指数"), "单位球上二次型最值就是最小和最大特征值。"),
    ],
}


SUBTYPES_BY_ID = {
    item["id"]: {**item, "concept_id": concept_id}
    for concept_id, items in SUBTYPE_CATALOG.items()
    for item in items
}


def _difficulty_label(year: Any) -> tuple[str, str]:
    try:
        value = int(year)
    except (TypeError, ValueError):
        return "other", "待分层"
    if 1987 <= value <= 2019:
        return "basic", "基础题"
    if 2020 <= value <= 2026:
        return "advanced", "提高题"
    return "other", "待分层"


def _question_public(question: dict[str, Any], *, reveal: bool = True) -> dict[str, Any]:
    excluded = {"raw_markdown"}
    if not reveal:
        excluded.update({"answer_markdown", "solution_markdown"})
    result = {key: value for key, value in question.items() if key not in excluded}
    band, label = _difficulty_label(question.get("year"))
    result["difficulty_band"] = band
    result["difficulty_label"] = label
    result["answer_available"] = bool(question.get("has_answer"))
    result["solution_available"] = bool(question.get("has_solution"))
    result["concept_labels"] = [concept_descriptor(item) for item in question.get("concept_ids", [])]
    return result


def _question_sort_key(question: dict[str, Any]) -> tuple[int, int, int, str]:
    try:
        difficulty = int(question.get("difficulty", 3))
    except (TypeError, ValueError):
        difficulty = 3
    try:
        year = int(question.get("year", 0))
    except (TypeError, ValueError):
        year = 0
    try:
        number = int(question.get("number", 0))
    except (TypeError, ValueError):
        number = 0
    return (abs(difficulty - 3), -year, number, str(question.get("id", "")))


def _unique_questions(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        identifier = str(item.get("id", ""))
        if identifier and identifier not in seen:
            seen.add(identifier)
            result.append(item)
    return result


def _question_text(question: dict[str, Any], *, include_solution: bool) -> str:
    fields = ["question_markdown", "answer_markdown"]
    if include_solution:
        fields.append("solution_markdown")
    return " ".join(str(question.get(field, "")).lower() for field in fields)


def _subtype_score(question: dict[str, Any], subtype: dict[str, Any]) -> int:
    question_text = _question_text(question, include_solution=False)
    full_text = _question_text(question, include_solution=True)
    score = 0
    for signal in subtype.get("signals", ()):
        normalized = signal.lower()
        if normalized in question_text:
            score += 4
        elif normalized in full_text:
            score += 1
    return score


def _concept_questions(questions: list[dict[str, Any]], concept_id: str) -> list[dict[str, Any]]:
    return [item for item in questions if item.get("exam_type") == "数学二" and concept_id in item.get("concept_ids", [])]


def _question_pool(questions: list[dict[str, Any]], concept_id: str, subtype: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept_pool = _concept_questions(questions, concept_id)
    scored = [(item, _subtype_score(item, subtype)) for item in concept_pool]
    matched = [item for item, score in sorted(scored, key=lambda pair: (-pair[1], _question_sort_key(pair[0]))) if score > 0]
    supplements = [item for item in sorted(concept_pool, key=_question_sort_key) if item not in matched]
    return _unique_questions(matched), _unique_questions(supplements)


def _copy_template(concept_id: str, subtype: dict[str, Any]) -> dict[str, Any]:
    concept_name, subject = CONCEPT_META[concept_id]
    return {
        "concept_id": concept_id,
        "concept_name": concept_name,
        "subject": subject,
        "subtype_id": subtype["id"],
        "subtype_name": subtype["name"],
        "subtype_summary": subtype["summary"],
        "overview": subtype["overview"],
        "framework": list(subtype["framework"]),
        "mistakes": list(subtype["mistakes"]),
        "memory_aid": subtype["memory_aid"],
        "source": "数学二公开大纲、公开教材目录与开源笔记结构交叉整理",
    }


def _apply_override(template: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return template
    for key in ("overview", "framework", "mistakes", "memory_aid"):
        if key in override and override[key] not in (None, "", []):
            template[key] = override[key]
    template["customized"] = True
    template["updated_at"] = override.get("updated_at", "")
    return template


def is_valid_subtype(concept_id: str, subtype_id: str) -> bool:
    subtype = SUBTYPES_BY_ID.get(subtype_id)
    return bool(subtype and subtype.get("concept_id") == concept_id)


def build_workbench_template(
    questions: list[dict[str, Any]], concept_id: str, subtype_id: str, override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if concept_id not in MATH2_CONCEPT_IDS:
        raise ValueError("Workbench 只支持数学二大纲内知识块。")
    if not is_valid_subtype(concept_id, subtype_id):
        raise ValueError("无效的细分题型。")
    subtype = SUBTYPES_BY_ID[subtype_id]
    matched, supplements = _question_pool(questions, concept_id, subtype)
    selected = _unique_questions(matched + supplements)[:4]
    example = selected[0] if selected else None
    variants = selected[1:4]
    matched_ids = {item.get("id") for item in matched}
    template = _apply_override(_copy_template(concept_id, subtype), override)
    template["matched_question_count"] = len(matched)
    template["available_count"] = len(matched) + len(supplements)
    template["example_source"] = "细分题型命中" if example and example.get("id") in matched_ids else "同知识块补充"
    template["question_format_counts"] = {
        question_type: sum(1 for item in matched if item.get("question_type") == question_type)
        for question_type in QUESTION_TYPES
    }
    template["example"] = {
        "question": _question_public(example, reveal=True) if example else None,
        "analysis": example.get("solution_markdown", "") if example else "当前题库没有找到可用的真实例题。",
        "answer": example.get("answer_markdown", "") if example else "",
        "difficulty": example.get("difficulty", 0) if example else 0,
        "source_scope": template["example_source"],
    }
    template["variants"] = [
        {
            "question": _question_public(item, reveal=True),
            "analysis": item.get("solution_markdown", ""),
            "answer": item.get("answer_markdown", ""),
            "difficulty": item.get("difficulty", 0),
            "source_scope": "细分题型命中" if item.get("id") in matched_ids else "同知识块补充",
        }
        for item in variants
    ]
    template["has_real_example"] = example is not None
    template["variant_count"] = len(variants)
    return template


def workbench_catalog(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for concept in MATH2_CONCEPTS:
        concept_id = concept["id"]
        concept_questions = _concept_questions(questions, concept_id)
        subtypes = []
        for subtype in SUBTYPE_CATALOG[concept_id]:
            matched, _ = _question_pool(questions, concept_id, subtype)
            subtypes.append({
                "id": subtype["id"],
                "name": subtype["name"],
                "summary": subtype["summary"],
                "matched_question_count": len(matched),
                "question_format_counts": {
                    question_type: sum(1 for item in matched if item.get("question_type") == question_type)
                    for question_type in QUESTION_TYPES
                },
            })
        result.append({
            "id": concept_id,
            "name": concept["name"],
            "subject": concept["subject"],
            "scope": "math2",
            "template_count": len(subtypes),
            "subtype_count": len(subtypes),
            "total_questions": len(concept_questions),
            "subtypes": subtypes,
        })
    return result


def subtype_count() -> int:
    return len(SUBTYPES_BY_ID)

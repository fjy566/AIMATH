// Hide the application while the session is being checked, but do this from
// JavaScript rather than the HTML shell. If an older desktop browser cannot
// parse this bundle, the shell remains visible and the user gets a useful
// fallback instead of a blank window.
document.body?.classList.add("auth-pending");

const state = {
  view: "overview",
  userId: "local-user",
  user: null,
  csrfToken: "",
  authenticated: false,
  authMode: "login",
  adminUsers: [],
  adminUsersAll: [],
  adminAudit: [],
  adminAuditAll: [],
  adminUserFilters: { search: "", role: "", status: "" },
  adminAuditFilters: { action: "", search: "" },
  accountSettings: null,
  stats: null,
  progress: null,
  forecast: null,
  analytics: null,
  blocks: [],
  nextQuestions: [],
  concepts: [],
  exams: [],
  settings: null,
  serverSettings: null,
  workbenchCatalog: [],
  workbenchConceptId: "",
  workbenchSubtypeId: "",
  workbenchSubtypeQuery: "",
  workbenchTemplate: null,
  workbenchEditingTemplate: false,
  workbenchVariantIndex: 0,
  workbenchAnalytics: null,
  notes: [],
  currentNote: null,
  noteEditorMode: "rich",
  noteFavoriteOnly: false,
  noteSearchTimer: null,
  noteSavedRange: null,
  currentQuestion: null,
  practiceSession: null,
  practiceQuestionIndex: 0,
  currentSimulation: null,
  simulationTimer: null,
  simulationDeadline: null,
  simulationCurrentIndex: 0,
  simulationCardFilter: "all",
  libraryLoaded: false,
};

const viewMeta = {
  overview: ["STUDY DESK / OVERVIEW", "今天，把薄弱处练成得分点"],
  workbench: ["WORKBENCH / ANSWER PATTERNS + NOTES", "学习工作台"],
  library: ["ARCHIVE / REAL QUESTIONS", "真题库"],
  blocks: ["ADAPTIVE PRACTICE / BLOC TRAINING", "分块训练"],
  simulation: ["FULL PAPER / TIMED PRACTICE", "模拟考"],
  analytics: ["ANALYTICS / EVIDENCE", "学习分析"],
  settings: ["SETTINGS / MODEL + SERVER", "设置"],
  admin: ["ADMIN / ACCESS CONTROL", "管理后台"],
};

const $ = (id) => document.getElementById(id);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, "&#096;");
}

function replaceAllLiteral(value, search, replacement) {
  return String(value).split(String(search)).join(String(replacement));
}

// A few imported/template records contain an extra slash before a TeX command
// (for example "\\le"). Normalize only known command names so matrix row
// breaks ("\\") remain intact.
const TEX_COMMAND_PATTERN = /(?<!\\)\\\\(?=(?:begin|end|frac|dfrac|tfrac|sqrt|binom|left|right|mathrm|mathbf|mathit|text|operatorname|mathbb|mathsf|mathcal|mathscr|displaystyle|textstyle|scriptstyle|lim|sin|cos|tan|cot|sec|csc|arcsin|arccos|arctan|ln|log|exp|sum|prod|int|iint|iiint|partial|nabla|infty|to|sim|le|ge|leq|geq|leqslant|geqslant|ne|neq|in|notin|subset|subseteq|forall|exists|varnothing|emptyset|Longleftrightarrow|Longrightarrow|Longleftarrow|Rightarrow|Leftrightarrow|leftarrow|rightarrow|cdot|times|pm|mp|approx|asymp|nsim|quad|qquad|det|lambda|xi|mu|alpha|beta|gamma|delta|theta|pi|Delta|Lambda|Omega|ell|eta|rho|psi|sigma|zeta|varphi|varepsilon|phi|boldsymbol|vec|overline|underline|overbrace|underbrace|widehat|hat|check|tilde|dot|ddot|cdots|ldots|dots|vdots|ddots|prime|mid|middle|boxed|hspace|limits|substack|max|min|Big|big|bigl|bigr|bigg|Bigg|Bigl|Bigr|Biggl|Biggr|cup|cap|setminus|circ|perp|downarrow|uparrow|triangle|ker|pmod|mod)\b)/g;

function normalizeTexSource(value) {
  return String(value || "")
    .replace(TEX_COMMAND_PATTERN, "\\")
    .replace(/(?<!\\)\\\\(?=[,;!])/g, "\\");
}

function renderMarkdown(source) {
  let text = String(source || "").replace(/\r/g, "");
  const formulas = [];
  const formulaPattern = /\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^$\n]+\$|\\begin\{(?:cases|aligned|array|matrix|pmatrix|bmatrix|Bmatrix|vmatrix|Vmatrix|smallmatrix)\}[\s\S]*?\\end\{(?:cases|aligned|array|matrix|pmatrix|bmatrix|Bmatrix|vmatrix|Vmatrix|smallmatrix)\}/g;
  text = text.replace(formulaPattern, (raw) => {
    let display = false;
    let tex = raw;
    if (raw.startsWith("$$")) {
      display = true;
      tex = raw.slice(2, -2);
    } else if (raw.startsWith("\\[")) {
      display = true;
      tex = raw.slice(2, -2);
    } else if (raw.startsWith("\\(")) {
      tex = raw.slice(2, -2);
    } else if (raw.startsWith("$")) {
      tex = raw.slice(1, -1);
    } else if (raw.startsWith("\\begin")) {
      display = true;
    }
    const token = `MATHTOKEN${formulas.length}END`;
    formulas.push({ token, display, tex });
    return token;
  });

  const inline = (line) => {
    const media = [];
    const prepared = String(line || "")
      .replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g, (raw, alt, url, title) => {
        const safe = safeNoteUrl(url);
        if (!safe) return raw;
        const token = `MARKDOWNMEDIATOKEN${media.length}END`;
        media.push({
          token,
          html: `<img src="${escapeAttr(safe)}" alt="${escapeAttr(alt)}"${title ? ` title="${escapeAttr(title)}"` : ""} />`,
        });
        return token;
      })
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (raw, label, url) => {
        const safe = safeNoteUrl(url);
        if (!safe) return raw;
        const token = `MARKDOWNMEDIATOKEN${media.length}END`;
        media.push({
          token,
          html: `<a href="${escapeAttr(safe)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`,
        });
        return token;
      });
    let html = escapeHtml(prepared);
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/==(.+?)==/g, "<mark>$1</mark>");
    html = html.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");
    html = html.replace(/__([^_\n]+?)__/g, "<u>$1</u>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    for (const formula of formulas) {
      const math = renderFormula(formula.tex, formula.display);
      html = replaceAllLiteral(html, formula.token, math);
    }
    for (const item of media) html = replaceAllLiteral(html, item.token, item.html);
    return html;
  };

  const output = [];
  let paragraph = [];
  let listType = null;
  const closeList = () => {
    if (listType) {
      output.push(`</${listType}>`);
      listType = null;
    }
  };
  const closeParagraph = () => {
    if (paragraph.length) {
      output.push(`<p>${paragraph.join("<br />")}</p>`);
      paragraph = [];
    }
  };

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      closeParagraph();
      closeList();
      continue;
    }
    // Source files use a trailing `---` as a section delimiter. Treat both
    // the normal Markdown form and the escaped `\---` variant as structure,
    // not answer text, so the delimiter cannot appear as a broken tail in
    // source answers or explanations.
    if (/^\\?(?:-{3,}|_{3,}|\*{3,})$/.test(line)) {
      closeParagraph();
      closeList();
      continue;
    }
    const heading = line.match(/^#{1,4}\s+(.+)$/);
    if (heading) {
      closeParagraph();
      closeList();
      output.push(`<h4>${inline(heading[1])}</h4>`);
      continue;
    }
    const subquestion = line.match(/^[（(](\d+)[）)]\s*(.*)$/);
    if (subquestion) {
      closeParagraph();
      closeList();
      output.push(`<div class="subquestion-line"><span>${escapeHtml(`（${subquestion[1]}）`)}</span><div>${inline(subquestion[2])}</div></div>`);
      continue;
    }
    const unordered = line.match(/^[-*]\s+(.+)$/);
    const ordered = line.match(/^\d+[.、]\s+(.+)$/);
    if (unordered || ordered) {
      closeParagraph();
      const nextType = unordered ? "ul" : "ol";
      if (listType !== nextType) {
        closeList();
        output.push(`<${nextType}>`);
        listType = nextType;
      }
      output.push(`<li>${inline((unordered || ordered)[1])}</li>`);
      continue;
    }
    if (line.startsWith(">")) {
      closeParagraph();
      closeList();
      output.push(`<blockquote>${inline(line.replace(/^>\s?/, ""))}</blockquote>`);
      continue;
    }
    closeList();
    paragraph.push(inline(line));
  }
  closeParagraph();
  closeList();
  return output.join("") || `<p class="muted-copy">暂无内容</p>`;
}

function renderFormula(tex, display) {
  const source = normalizeTexSource(tex).trim();
  if (window.katex?.renderToString) {
    try {
      return window.katex.renderToString(source, {
        displayMode: display,
        throwOnError: false,
        strict: "ignore",
        trust: false,
      });
    } catch (error) {
      console.warn("KaTeX render fallback", error);
    }
  }
  const fallbackClass = display ? "math math-block math-fallback" : "math math-fallback";
  return `<span class="${fallbackClass}">${escapeHtml(source)}</span>`;
}

const RICH_FORMULA_PATTERN = /\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^$\n]+\$|\\begin\{(?:cases|aligned|array|matrix|pmatrix|bmatrix|Bmatrix|vmatrix|Vmatrix|smallmatrix)\}[\s\S]*?\\end\{(?:cases|aligned|array|matrix|pmatrix|bmatrix|Bmatrix|vmatrix|smallmatrix)\}/g;

function renderInlineFormulaText(value) {
  const formulas = [];
  const replaced = String(value || "").replace(/\r/g, "").replace(RICH_FORMULA_PATTERN, (raw) => {
    let display = false;
    let tex = raw;
    if (raw.startsWith("$$")) {
      display = true;
      tex = raw.slice(2, -2);
    } else if (raw.startsWith("\\[")) {
      display = true;
      tex = raw.slice(2, -2);
    } else if (raw.startsWith("\\(")) {
      tex = raw.slice(2, -2);
    } else if (raw.startsWith("$")) {
      tex = raw.slice(1, -1);
    } else if (raw.startsWith("\\begin")) {
      display = true;
    }
    const token = "RICHMATHTOKEN" + formulas.length + "END";
    formulas.push({ token, display, tex });
    return token;
  });
  let html = escapeHtml(replaced).replace(/\n/g, "<br />");
  for (const formula of formulas) html = replaceAllLiteral(html, formula.token, renderFormula(formula.tex, formula.display));
  return html;
}

function renderTemplateText(value) {
  return "<div class=\"markdown-body template-rich-text\">" + renderMarkdown(value) + "</div>";
}

function renderLearningText(value, className = "") {
  return `<div class="markdown-body learning-rich-text ${escapeAttr(className)}">${renderMarkdown(value || "")}</div>`;
}

function renderAnswerStructure(template) {
  const items = template?.answer_structure || [];
  if (!items.length) return "";
  const steps = items.map((item, index) => "<article class=\"template-answer-step\"><span class=\"template-answer-step-index\">" + String(index + 1).padStart(2, "0") + "</span><div><strong>" + escapeHtml(item.label || "答题步骤") + "</strong><p>" + escapeHtml(item.prompt || "") + "</p><div class=\"markdown-body\">" + renderMarkdown(item.content || "") + "</div></div></article>").join("");
  return "<section class=\"template-answer-structure\"><div class=\"template-answer-structure-head\"><div><span class=\"template-section-label\">可直接套写的答题纸结构</span><h4>把这类题写成完整得分链</h4></div><small>将题设中的字母、区间和数值代入对应位置，再逐步核对易错点。</small></div><div class=\"template-answer-structure-grid\">" + steps + "</div></section>";
}

function typeset(root) {
  // KaTeX renders synchronously inside renderMarkdown. Keep this hook so
  // question/result rendering has one stable call site.
  return root;
}

function previewSource(source, maxChars = 420) {
  const lines = String(source || "").replace(/\r/g, "").split("\n");
  const blocks = [];
  let current = [];
  const flush = () => {
    const block = current.join("\n").trim();
    if (block) blocks.push(block);
    current = [];
  };
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (/^\*\*(答案|解析)/.test(line) || /^#{1,6}\s*(答案|解析)/.test(line)) break;
    if (!line) {
      flush();
      continue;
    }
    if (/^#{1,6}\s+/.test(line)) continue;
    current.push(line);
  }
  flush();
  const selected = [];
  let length = 0;
  for (const block of blocks) {
    if (selected.length && length + block.length > maxChars) break;
    selected.push(block);
    length += block.length;
  }
  return selected.join("\n\n") || blocks[0] || "";
}

function renderQuestionPreview(source, maxChars = 420) {
  return renderMarkdown(previewSource(source, maxChars));
}

function renderAnswerPreview(value) {
  const source = String(value || "").trim();
  if (!source) return `<p class="muted-copy">输入答案后，这里会实时预览。点击下方工具可以插入常用公式模板。</p>`;
  const hasMathDelimiters = /\$\$?[\s\S]*?\$\$?|\\\(|\\\[/.test(source);
  const looksLikeStandaloneLatex = !hasMathDelimiters && !/[，。！？\n]/.test(source) && /\\[A-Za-z]+|[{}^_]/.test(source);
  return renderMarkdown(looksLikeStandaloneLatex ? `$$${source}$$` : source);
}

const BEGINNER_FORMULA_GROUPS = [
  {
    label: "基础结构",
    items: [
      { label: "分数", symbol: "½", tex: "\\frac{a}{b}", select: "a", title: "插入分数，先填写分子" },
      { label: "根号", symbol: "√x", tex: "\\sqrt{x}", select: "x", title: "插入平方根" },
      { label: "n 次根", symbol: "ⁿ√x", tex: "\\sqrt[n]{x}", select: "n", title: "插入 n 次根式" },
      { label: "次方", symbol: "xⁿ", tex: "x^{n}", select: "n", title: "插入次方" },
      { label: "下标", symbol: "xᵢ", tex: "x_{i}", select: "i", title: "插入下标" },
      { label: "括号", symbol: "( )", tex: "\\left( x \\right)", select: "x", title: "插入可伸缩括号" },
      { label: "绝对值", symbol: "|x|", tex: "\\left|x\\right|", select: "x", title: "插入绝对值" },
      { label: "分段", symbol: "{ x", tex: "\\begin{cases}x,&x\\ge 0\\\\-x,&x<0\\end{cases}", select: "x", wrap: "display", title: "插入分段函数" },
      { label: "组合数", symbol: "Cⁿₖ", tex: "\\binom{n}{k}", select: "n", title: "插入组合数" },
    ],
  },
  {
    label: "微积分",
    items: [
      { label: "一阶导", symbol: "dy/dx", tex: "\\frac{dy}{dx}", select: "dy", title: "插入一阶导数" },
      { label: "二阶导", symbol: "d²y", tex: "\\frac{d^2y}{dx^2}", select: "d^2y", title: "插入二阶导数" },
      { label: "偏导", symbol: "∂f/∂x", tex: "\\frac{\\partial f}{\\partial x}", select: "f", title: "插入一阶偏导数" },
      { label: "二阶偏导", symbol: "∂²f", tex: "\\frac{\\partial^2 f}{\\partial x^2}", select: "f", title: "插入二阶偏导数" },
      { label: "微分", symbol: "dx", tex: "\\mathrm{d}x", select: "x", title: "插入微分符号" },
      { label: "积分", symbol: "∫", tex: "\\int_{a}^{b} f(x)\\,\\mathrm{d}x", select: "a", wrap: "display", title: "插入定积分" },
      { label: "二重积分", symbol: "∬", tex: "\\iint_{D} f(x,y)\\,\\mathrm{d}A", select: "D", wrap: "display", title: "插入二重积分" },
      { label: "三重积分", symbol: "∭", tex: "\\iiint_{V} f(x,y,z)\\,\\mathrm{d}V", select: "V", wrap: "display", title: "插入三重积分" },
      { label: "极限", symbol: "lim", tex: "\\lim_{x\\to a} f(x)", select: "x\\to a", wrap: "display", title: "插入极限" },
      { label: "求和", symbol: "Σ", tex: "\\sum_{i=1}^{n} a_i", select: "i=1", wrap: "display", title: "插入求和" },
      { label: "连乘", symbol: "Π", tex: "\\prod_{i=1}^{n} a_i", select: "i=1", wrap: "display", title: "插入连乘" },
      { label: "梯度", symbol: "∇f", tex: "\\nabla f", select: "f", title: "插入梯度" },
      { label: "原函数", symbol: "F(x)", tex: "F(x)=\\int f(x)\\,\\mathrm{d}x", select: "F(x)", wrap: "display", title: "插入原函数关系" },
      { label: "牛顿莱布尼茨", symbol: "F(b)-F(a)", tex: "\\int_{a}^{b} f(x)\\,\\mathrm{d}x=F(b)-F(a)", select: "a", wrap: "display", title: "插入牛顿莱布尼茨公式" },
      { label: "泰勒展开", symbol: "f(a)+...", tex: "f(x)=f(a)+f'(a)(x-a)+\\frac{f''(a)}{2!}(x-a)^2+\\cdots", select: "f(a)", wrap: "display", title: "插入二阶泰勒展开模板" },
    ],
  },
  {
    label: "函数与符号",
    items: [
      { label: "正弦", symbol: "sin", tex: "\\sin x", select: "x", title: "插入正弦函数" },
      { label: "余弦", symbol: "cos", tex: "\\cos x", select: "x", title: "插入余弦函数" },
      { label: "正切", symbol: "tan", tex: "\\tan x", select: "x", title: "插入正切函数" },
      { label: "反三角", symbol: "arcsin", tex: "\\arcsin x", select: "x", title: "插入反三角函数" },
      { label: "自然对数", symbol: "ln", tex: "\\ln x", select: "x", title: "插入自然对数" },
      { label: "常用对数", symbol: "log", tex: "\\log_a x", select: "a", title: "插入以 a 为底的对数" },
      { label: "指数", symbol: "eˣ", tex: "e^{x}", select: "x", title: "插入指数函数" },
      { label: "函数导数", symbol: "f′", tex: "f'(x)", select: "f", title: "插入函数导数记号" },
      { label: "无穷大", symbol: "∞", tex: "\\infty", title: "插入无穷大" },
      { label: "趋于", symbol: "→", tex: "\\to", title: "插入趋于符号" },
      { label: "正负", symbol: "±", tex: "\\pm", title: "插入正负号" },
      { label: "近似", symbol: "≈", tex: "\\approx", title: "插入约等于" },
      { label: "不等式", symbol: "≤ ≥", tex: "a \\le b", select: "a", title: "插入不等式" },
      { label: "不等于", symbol: "≠", tex: "a \\ne b", select: "a", title: "插入不等于" },
      { label: "乘号", symbol: "·", tex: "\\cdot", title: "插入点乘号" },
    ],
  },
  {
    label: "线性代数",
    items: [
      { label: "列向量", symbol: "[x]", tex: "\\begin{bmatrix}x_1\\\\x_2\\\\x_3\\end{bmatrix}", select: "x_1", wrap: "display", title: "插入三维列向量" },
      { label: "二阶矩阵", symbol: "▦", tex: "\\begin{pmatrix}a&b\\\\c&d\\end{pmatrix}", select: "a", wrap: "display", title: "插入二阶矩阵" },
      { label: "矩阵", symbol: "A", tex: "A=(a_{ij})_{m\\times n}", select: "A", wrap: "display", title: "插入一般矩阵记号" },
      { label: "行列式", symbol: "|A|", tex: "\\begin{vmatrix}a&b\\\\c&d\\end{vmatrix}", select: "a", wrap: "display", title: "插入二阶行列式" },
      { label: "向量", symbol: "a⃗", tex: "\\vec{a}", select: "a", title: "插入向量记号" },
      { label: "列向量加粗", symbol: "𝐱", tex: "\\mathbf{x}", select: "x", title: "插入加粗向量" },
      { label: "转置", symbol: "Aᵀ", tex: "A^{\\mathsf T}", select: "A", title: "插入转置矩阵" },
      { label: "逆矩阵", symbol: "A⁻¹", tex: "A^{-1}", select: "A", title: "插入逆矩阵" },
      { label: "单位矩阵", symbol: "Iₙ", tex: "I_n", select: "n", title: "插入 n 阶单位矩阵" },
      { label: "零矩阵", symbol: "O", tex: "O_{m\\times n}", select: "m", title: "插入零矩阵" },
      { label: "行列式值", symbol: "det A", tex: "\\det(A)", select: "A", title: "插入行列式函数" },
      { label: "矩阵秩", symbol: "rank", tex: "\\operatorname{rank}(A)", select: "A", title: "插入矩阵的秩" },
      { label: "特征方程", symbol: "|A-λI|", tex: "\\det(A-\\lambda I)=0", select: "A", wrap: "display", title: "插入特征方程" },
      { label: "特征向量", symbol: "Ax=λx", tex: "A\\mathbf{x}=\\lambda\\mathbf{x}", select: "A", wrap: "display", title: "插入特征值特征向量关系" },
      { label: "向量内积", symbol: "a·b", tex: "\\mathbf{a}\\cdot\\mathbf{b}", select: "a", title: "插入向量内积" },
      { label: "向量范数", symbol: "‖x‖", tex: "\\left\\|\\mathbf{x}\\right\\|", select: "x", title: "插入向量范数" },
      { label: "内积括号", symbol: "⟨a,b⟩", tex: "\\langle \\mathbf{a},\\mathbf{b}\\rangle", select: "a", title: "插入内积括号" },
    ],
  },
  {
    label: "集合与关系",
    items: [
      { label: "属于", symbol: "∈", tex: "x\\in D", select: "x", title: "插入属于关系" },
      { label: "不属于", symbol: "∉", tex: "x\\notin D", select: "x", title: "插入不属于关系" },
      { label: "子集", symbol: "⊂", tex: "A\\subset B", select: "A", title: "插入子集关系" },
      { label: "任意", symbol: "∀", tex: "\\forall x\\in D", select: "x", title: "插入任意量词" },
      { label: "存在", symbol: "∃", tex: "\\exists x\\in D", select: "x", title: "插入存在量词" },
      { label: "实数集", symbol: "ℝ", tex: "\\mathbb{R}", title: "插入实数集" },
      { label: "自然数集", symbol: "ℕ", tex: "\\mathbb{N}", title: "插入自然数集" },
      { label: "空集", symbol: "∅", tex: "\\varnothing", title: "插入空集" },
      { label: "等价", symbol: "⇔", tex: "\\Longleftrightarrow", title: "插入等价关系" },
      { label: "推出", symbol: "⇒", tex: "\\Longrightarrow", title: "插入推出关系" },
      { label: "因为所以", symbol: "∵∴", tex: "\\because\\quad \\therefore", title: "插入因为和所以" },
      { label: "点集坐标", symbol: "(x₀,y₀)", tex: "(x_0,y_0)", select: "x_0", title: "插入坐标点" },
    ],
  },
];

function domId(value) {
  return String(value || "field").replace(/[^a-zA-Z0-9_-]/g, "-");
}

function extractChoiceOptions(source) {
  const options = [];
  let current = null;
  for (const rawLine of String(source || "").replace(/\r/g, "").split("\n")) {
    const line = rawLine.trim();
    const match = line.match(/^(?:[-*]\s*)?([A-D])[\.．、\)]\s*(.*)$/i);
    if (match) {
      if (current) options.push(current);
      current = { label: match[1].toUpperCase(), text: match[2].trim() };
    } else if (current && line) {
      current.text = `${current.text} ${line}`.trim();
    }
  }
  if (current) options.push(current);
  return options.length ? options : ["A", "B", "C", "D"].map((label) => ({ label, text: `选项 ${label}` }));
}

function formulaToolMarkup(item) {
  const content = `<span class="formula-tool-glyph">${escapeHtml(item.symbol || item.label)}</span><span class="formula-tool-caption">${escapeHtml(item.label)}</span>`;
  return `<button type="button" class="formula-tool beginner-formula-tool" data-formula-tool data-formula-tex="${escapeAttr(item.tex)}" data-formula-select="${escapeAttr(item.select || "")}" data-formula-wrap="${escapeAttr(item.wrap || "inline")}" title="${escapeAttr(item.title || item.label)}">${content}</button>`;
}

function formulaGroupsMarkup(editorId, groups) {
  const tabs = groups.map((group, index) => `<button type="button" class="formula-category-tab ${index === 0 ? "is-active" : ""}" data-formula-category="${index}" role="tab" aria-selected="${index === 0 ? "true" : "false"}" aria-controls="${escapeAttr(editorId)}-formula-category-panel-${index}" tabindex="${index === 0 ? "0" : "-1"}"><span>${escapeHtml(group.label)}</span><small>${group.items.length}</small></button>`).join("");
  const panels = groups.map((group, index) => `<section class="formula-beginner-group formula-group-panel" id="${escapeAttr(editorId)}-formula-category-panel-${index}" data-formula-group-panel="${index}" role="tabpanel" ${index === 0 ? "" : "hidden"}><div class="formula-group-panel-head"><span class="formula-group-label">${escapeHtml(group.label)}</span><span>${group.items.length} 个常用工具</span></div><div class="formula-beginner-list">${group.items.map((item) => formulaToolMarkup(item)).join("")}</div></section>`).join("");
  return `<div class="formula-category-tabs" role="tablist" aria-label="公式分类">${tabs}</div><div class="formula-beginner-groups">${panels}</div>`;
}

function answerStructureMarkup(editorId, questionType) {
  if (questionType !== "solution") return "";
  return `<div class="answer-structure-panel" id="${escapeAttr(editorId)}-answer-structure" data-answer-structure-panel="${escapeAttr(editorId)}" hidden>
    <div class="answer-structure-head"><strong>把解题过程排得更清楚</strong><span>按钮会在光标处插入编号</span></div>
    <div class="answer-structure-actions">
      <button type="button" class="structure-action" data-structure-action="point"><span>1.</span> 添加分点</button>
      <button type="button" class="structure-action" data-structure-action="subquestion"><span>（1）</span> 添加小题</button>
      <button type="button" class="structure-action" data-structure-action="newline"><span>↵</span> 换一行</button>
    </div>
    <p class="answer-structure-hint">先把光标放到要继续作答的位置，再点按钮。已有文字不会被覆盖。</p>
  </div>`;
}

function formulaToolbarMarkup(editorId, readonly = false, questionType = "fill", includeText = true) {
  if (readonly) return `<p class="formula-readonly-note">本题已提交。可查看公式，但不能修改。</p>`;
  return `<div class="answer-toolbox">
    <div class="answer-tool-row">
      <span class="answer-tool-prompt">不懂 LaTeX 也没关系，直接点你想要的公式</span>
      <div class="answer-tool-actions">
        <button type="button" class="answer-tool-toggle" data-formula-toggle aria-expanded="false" aria-controls="${escapeAttr(editorId)}-formula-tools"><span>Σ</span> 公式工具</button>
        ${questionType === "solution" ? `<button type="button" class="answer-tool-toggle" data-answer-structure-toggle aria-expanded="false" aria-controls="${escapeAttr(editorId)}-answer-structure"><span>☷</span> 作答结构</button>` : ""}
      </div>
    </div>
    ${includeText ? `<div class="answer-format-bar" role="toolbar" aria-label="文字作答工具">
      <button type="button" data-editor-command="bold" title="加粗 Ctrl+B"><b>B</b></button>
      <button type="button" data-editor-command="italic" title="斜体 Ctrl+I"><i>I</i></button>
      <button type="button" data-editor-command="underline" title="下划线 Ctrl+U"><u>U</u></button>
      <button type="button" data-editor-command="heading" title="小标题">标题</button>
      <button type="button" data-editor-command="highlight" title="高亮重点">高亮</button>
      <button type="button" data-editor-command="link" title="插入链接 Ctrl+K">链接</button>
      <button type="button" data-editor-insert="quote" title="插入引用">引用</button>
      <button type="button" data-editor-insert="point" title="插入分点">分点</button>
      <button type="button" data-editor-insert="subquestion" title="插入小题">小题</button>
      <button type="button" data-editor-insert="unordered" title="插入无序列表">列表</button>
      <button type="button" data-editor-insert="ordered" title="插入有序列表">编号</button>
      <span class="answer-format-spacer"></span>
      <button type="button" data-editor-command="undo" title="撤销 Ctrl+Z">撤销</button>
      <button type="button" data-editor-command="redo" title="重做 Ctrl+Y">重做</button>
    </div>` : ""}
    <div class="formula-tools-panel" id="${escapeAttr(editorId)}-formula-tools" data-formula-tools-panel hidden>
      <div class="formula-beginner-head"><strong>先选一类，再插入公式</strong><span>插入后可以继续修改字母和数字</span></div>
      <div role="toolbar" aria-label="常用数学公式工具">${formulaGroupsMarkup(editorId, BEGINNER_FORMULA_GROUPS)}</div>
      <p class="formula-helper"><span>点击按钮插入模板，蓝色文字会自动选中，可直接替换</span><span><kbd>$</kbd> 行内 · <kbd>$$</kbd> 行间 · <kbd>Ctrl</kbd> + <kbd>Enter</kbd> 提交</span></p>
    </div>
    ${answerStructureMarkup(editorId, questionType)}
  </div>`;
}

// Shared touch-first handwriting surface. Strokes are persisted as normalized
// vectors so a draft survives resizing and fullscreen editing without bitmap
// quality loss.
const HANDWRITING_STORAGE_PREFIX = "ai-math-handwriting-v1:";
const HANDWRITING_STATE = new WeakMap();
const HANDWRITING_UPLOAD_CACHE = new Map();
const HANDWRITING_MAX_STROKES = 320;
const HANDWRITING_MAX_POINTS = 6000;

function answerHandwritingKey(mode, questionId, contextId = "") {
  const owner = state.userId || "local-user";
  const scope = String(mode || "modal");
  const context = contextId ? `${String(contextId)}:` : "";
  return `${owner}:${scope}:${context}${String(questionId || "unknown")}`;
}

function handwritingStorageKey(key) {
  return `${HANDWRITING_STORAGE_PREFIX}${encodeURIComponent(String(key || "unknown"))}`;
}

function normalizeHandwritingStrokes(strokes) {
  if (!Array.isArray(strokes)) return [];
  const normalized = [];
  let pointBudget = HANDWRITING_MAX_POINTS;
  for (const stroke of strokes.slice(-HANDWRITING_MAX_STROKES)) {
    if (pointBudget <= 0) break;
    const points = Array.isArray(stroke?.points)
      ? stroke.points.slice(-Math.min(HANDWRITING_MAX_POINTS, pointBudget)).map((point) => ({
        x: Math.max(0, Math.min(1, Number(point?.x) || 0)),
        y: Math.max(0, Math.min(1, Number(point?.y) || 0)),
        p: Math.max(.08, Math.min(1, Number(point?.p) || .5)),
      })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
      : [];
    if (points.length) {
      const mode = stroke?.mode === "eraser" ? "eraser" : "pen";
      normalized.push({ mode, width: Math.max(1, Math.min(40, Number(stroke?.width) || (mode === "eraser" ? 14 : 2.4))), points });
      pointBudget -= points.length;
    }
  }
  return normalized;
}

function readHandwritingDraft(key) {
  try {
    const raw = localStorage.getItem(handwritingStorageKey(key));
    if (!raw) return { strokes: [], updatedAt: "" };
    const parsed = JSON.parse(raw);
    return { strokes: normalizeHandwritingStrokes(parsed?.strokes), updatedAt: String(parsed?.updatedAt || "") };
  } catch {
    return { strokes: [], updatedAt: "" };
  }
}

function handwritingHasDraft(key) {
  return readHandwritingDraft(key).strokes.length > 0;
}

function handwritingPadHasContent(pad) {
  const stateForPad = handwritingStateFor(pad);
  return Boolean(stateForPad?.strokes?.length || (pad?.dataset.handwritingKey && handwritingHasDraft(pad.dataset.handwritingKey)));
}

function handwritingStateFor(pad) {
  return pad ? HANDWRITING_STATE.get(pad) : null;
}

function handwritingFormatUpdatedAt(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `保存于 ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function writeHandwritingDraft(stateForPad) {
  if (!stateForPad?.key) return "";
  const strokes = normalizeHandwritingStrokes(stateForPad.strokes);
  const updatedAt = new Date().toISOString();
  try {
    if (strokes.length) localStorage.setItem(handwritingStorageKey(stateForPad.key), JSON.stringify({ version: 1, updatedAt, strokes }));
    else localStorage.removeItem(handwritingStorageKey(stateForPad.key));
  } catch {
    // Private browsing or a full storage quota should not block writing.
  }
  stateForPad.strokes = strokes;
  stateForPad.updatedAt = strokes.length ? updatedAt : "";
  return updatedAt;
}

function forgetHandwritingDraft(padOrKey) {
  const stateForPad = typeof padOrKey === "string" ? null : handwritingStateFor(padOrKey);
  const key = typeof padOrKey === "string" ? padOrKey : stateForPad?.key || padOrKey?.dataset?.handwritingKey;
  if (!key) return;
  try { localStorage.removeItem(handwritingStorageKey(key)); } catch { /* storage may be unavailable */ }
  HANDWRITING_UPLOAD_CACHE.delete(key);
  if (stateForPad) {
    stateForPad.strokes = [];
    stateForPad.redo = [];
    stateForPad.updatedAt = "";
    drawHandwritingPad(padOrKey);
    updateHandwritingStatus(padOrKey, "已提交");
  }
}

function handwritingPoint(canvas, event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width))),
    y: Math.max(0, Math.min(1, (event.clientY - rect.top) / Math.max(1, rect.height))),
    p: Math.max(.08, Math.min(1, Number(event.pressure) > 0 ? Number(event.pressure) : .5)),
  };
}

function drawHandwritingStroke(context, stroke, width, height, color = "#173f45") {
  const points = stroke?.points || [];
  if (!points.length) return;
  context.save();
  context.globalCompositeOperation = stroke?.mode === "eraser" ? "destination-out" : "source-over";
  context.strokeStyle = color;
  context.fillStyle = color;
  context.lineCap = "round";
  context.lineJoin = "round";
  if (points.length === 1) {
    const point = points[0];
    context.beginPath();
    context.arc(point.x * width, point.y * height, Math.max(1.2, (stroke.width || 2.4) * (0.65 + point.p * .35)), 0, Math.PI * 2);
    context.fill();
    context.restore();
    return;
  }
  context.beginPath();
  context.moveTo(points[0].x * width, points[0].y * height);
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const point = points[index];
    context.quadraticCurveTo(previous.x * width, previous.y * height, (previous.x + point.x) * width / 2, (previous.y + point.y) * height / 2);
  }
  const last = points[points.length - 1];
  context.lineTo(last.x * width, last.y * height);
  context.lineWidth = Math.max(1.2, (stroke.width || 2.4) * (0.76 + last.p * .24));
  context.stroke();
  context.restore();
}

function drawHandwritingPad(pad) {
  const stateForPad = handwritingStateFor(pad);
  const canvas = pad?.querySelector("[data-handwriting-canvas]");
  if (!stateForPad || !canvas) return;
  const context = stateForPad.context || canvas.getContext("2d");
  if (!context) return;
  stateForPad.context = context;
  const width = stateForPad.width || Math.max(1, canvas.clientWidth || 640);
  const height = stateForPad.height || Math.max(1, canvas.clientHeight || 260);
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.clearRect(0, 0, canvas.width, canvas.height);
  const ratio = stateForPad.dpr || 1;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  const ink = getComputedStyle(pad).getPropertyValue("--ink-soft").trim() || "#173f45";
  stateForPad.strokes.forEach((stroke) => drawHandwritingStroke(context, stroke, width, height, ink));
  pad.classList.toggle("has-content", stateForPad.strokes.length > 0);
  const empty = pad.querySelector("[data-handwriting-empty]");
  if (empty) empty.hidden = stateForPad.strokes.length > 0;
  const undo = pad.querySelector("[data-handwriting-undo]");
  const redo = pad.querySelector("[data-handwriting-redo]");
  const clear = pad.querySelector("[data-handwriting-clear]");
  const save = pad.querySelector("[data-handwriting-save]");
  const pen = pad.querySelector('[data-handwriting-tool="pen"]');
  const eraser = pad.querySelector('[data-handwriting-tool="eraser"]');
  const size = pad.querySelector("[data-handwriting-size]");
  const toolLabel = pad.querySelector("[data-handwriting-tool-label]");
  if (undo) undo.disabled = stateForPad.readonly || !stateForPad.strokes.length;
  if (redo) redo.disabled = stateForPad.readonly || !stateForPad.redo.length;
  if (clear) clear.disabled = stateForPad.readonly || !stateForPad.strokes.length;
  if (save) save.disabled = stateForPad.readonly || !stateForPad.strokes.length;
  if (pen) { pen.disabled = stateForPad.readonly; pen.classList.toggle("is-active", stateForPad.tool === "pen"); pen.setAttribute("aria-pressed", String(stateForPad.tool === "pen")); }
  if (eraser) { eraser.disabled = stateForPad.readonly; eraser.classList.toggle("is-active", stateForPad.tool === "eraser"); eraser.setAttribute("aria-pressed", String(stateForPad.tool === "eraser")); }
  if (size) { size.disabled = stateForPad.readonly; size.value = String(stateForPad.strokeWidth); }
  if (toolLabel) toolLabel.textContent = stateForPad.tool === "eraser" ? "橡皮" : "画笔";
}

function resizeHandwritingPad(pad) {
  const stateForPad = handwritingStateFor(pad);
  const canvas = pad?.querySelector("[data-handwriting-canvas]");
  if (!stateForPad || !canvas) return;
  const width = Math.max(280, Math.floor(canvas.parentElement?.clientWidth || canvas.clientWidth || 640));
  const height = Math.max(190, Math.floor(canvas.clientHeight || 260));
  const dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
  if (stateForPad.width === width && stateForPad.height === height && stateForPad.dpr === dpr) {
    drawHandwritingPad(pad);
    return;
  }
  stateForPad.width = width;
  stateForPad.height = height;
  stateForPad.dpr = dpr;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  drawHandwritingPad(pad);
}

function dispatchHandwritingChange(pad, source = "draw") {
  pad?.dispatchEvent(new CustomEvent("handwritingchange", { bubbles: true, detail: { key: pad.dataset.handwritingKey || "", source, hasContent: handwritingPadHasContent(pad) } }));
}

function updateHandwritingStatus(pad, message = "") {
  const stateForPad = handwritingStateFor(pad);
  if (!stateForPad) return;
  const status = pad.querySelector("[data-handwriting-status]");
  const updated = pad.querySelector("[data-handwriting-updated]");
  if (status) status.textContent = message || (stateForPad.strokes.length ? "已暂存，可提交" : stateForPad.readonly ? "已提交 · 只读查看" : "未开始");
  if (updated) updated.textContent = stateForPad.updatedAt ? handwritingFormatUpdatedAt(stateForPad.updatedAt) : "未提交前仅保存在本机";
}

function saveHandwritingPad(pad, source = "save") {
  const stateForPad = handwritingStateFor(pad);
  if (!stateForPad || stateForPad.readonly) return;
  writeHandwritingDraft(stateForPad);
  updateHandwritingStatus(pad);
  drawHandwritingPad(pad);
  dispatchHandwritingChange(pad, source);
}

function setHandwritingTool(pad, tool = "pen") {
  const stateForPad = handwritingStateFor(pad);
  if (!stateForPad || stateForPad.readonly) return;
  stateForPad.tool = tool === "eraser" ? "eraser" : "pen";
  updateHandwritingStatus(pad, stateForPad.tool === "eraser" ? "橡皮已启用" : "画笔已启用");
  drawHandwritingPad(pad);
}

function handwritingToolButtonMarkup(tool, label, readonly) {
  return `<button type="button" class="handwriting-action handwriting-tool" data-handwriting-tool="${tool}" aria-label="${label}工具" title="${label}工具" aria-pressed="${tool === "pen" ? "true" : "false"}" ${readonly ? "disabled" : ""}>${label}</button>`;
}

function setHandwritingFullscreen(pad, active) {
  if (!pad) return;
  pad.classList.toggle("is-fullscreen-fallback", active);
  pad.classList.toggle("is-fullscreen-active", active || document.fullscreenElement === pad);
  document.body.classList.toggle("handwriting-fullscreen-open", Boolean(active || document.fullscreenElement));
  const button = pad.querySelector("[data-handwriting-fullscreen]");
  if (button) button.textContent = active || document.fullscreenElement === pad ? "退出全屏" : (pad.classList.contains("is-readonly") ? "全屏查看" : "全屏书写");
  window.requestAnimationFrame?.(() => resizeHandwritingPad(pad));
}

async function toggleHandwritingFullscreen(pad) {
  if (document.fullscreenElement === pad) {
    await document.exitFullscreen?.();
    return;
  }
  if (pad.classList.contains("is-fullscreen-fallback")) {
    setHandwritingFullscreen(pad, false);
    return;
  }
  try {
    if (pad.requestFullscreen) {
      await pad.requestFullscreen();
      setHandwritingFullscreen(pad, true);
      return;
    }
  } catch {
    // Embedded browsers may refuse the API; use the fixed-position fallback.
  }
  setHandwritingFullscreen(pad, true);
}

function bindHandwritingDocumentEvents() {
  if (document.documentElement.dataset.handwritingEventsBound === "true") return;
  document.documentElement.dataset.handwritingEventsBound = "true";
  document.addEventListener("fullscreenchange", () => $$('[data-handwriting-pad]').forEach((pad) => setHandwritingFullscreen(pad, document.fullscreenElement === pad || pad.classList.contains("is-fullscreen-fallback"))));
  window.addEventListener("resize", () => $$('[data-handwriting-pad]').forEach(resizeHandwritingPad), { passive: true });
}

function bindHandwritingPads(root = document) {
  bindHandwritingDocumentEvents();
  const pads = [];
  if (root?.matches?.("[data-handwriting-pad]")) pads.push(root);
  pads.push(...$$('[data-handwriting-pad]', root));
  pads.forEach((pad) => {
    if (pad.dataset.handwritingBound === "true") return;
    pad.dataset.handwritingBound = "true";
    const key = pad.dataset.handwritingKey || "unknown";
    const saved = readHandwritingDraft(key);
    const stateForPad = { key, readonly: pad.dataset.handwritingReadonly === "true", strokes: saved.strokes, redo: [], updatedAt: saved.updatedAt, width: 0, height: 0, dpr: 1, activeStroke: null, context: null, drawFrame: 0, tool: "pen", strokeWidth: 2.4 };
    HANDWRITING_STATE.set(pad, stateForPad);
    const canvas = pad.querySelector("[data-handwriting-canvas]");
    const wrap = pad.querySelector("[data-handwriting-canvas-wrap]");
    const finishStroke = () => {
      if (!stateForPad.activeStroke) return;
      stateForPad.activeStroke = null;
      saveHandwritingPad(pad, "draw");
    };
    const scheduleDraw = () => {
      if (stateForPad.drawFrame) return;
      stateForPad.drawFrame = window.requestAnimationFrame?.(() => { stateForPad.drawFrame = 0; drawHandwritingPad(pad); }) || 0;
      if (!stateForPad.drawFrame) drawHandwritingPad(pad);
    };
    canvas?.addEventListener("pointerdown", (event) => {
      if (stateForPad.readonly || event.button > 0) return;
      event.preventDefault();
      canvas.setPointerCapture?.(event.pointerId);
      const baseWidth = Number(stateForPad.strokeWidth) || 2.4;
      const stroke = { mode: stateForPad.tool, width: stateForPad.tool === "eraser" ? Math.max(10, baseWidth * 5) : (event.pointerType === "pen" ? baseWidth * .88 : baseWidth), points: [handwritingPoint(canvas, event)] };
      stateForPad.strokes.push(stroke);
      stateForPad.redo = [];
      stateForPad.activeStroke = stroke;
      scheduleDraw();
    });
    canvas?.addEventListener("pointermove", (event) => {
      if (!stateForPad.activeStroke) return;
      event.preventDefault();
      (event.getCoalescedEvents?.() || [event]).forEach((pointEvent) => {
        if (stateForPad.activeStroke.points.length < HANDWRITING_MAX_POINTS) stateForPad.activeStroke.points.push(handwritingPoint(canvas, pointEvent));
      });
      scheduleDraw();
    });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach((name) => canvas?.addEventListener(name, finishStroke));
    canvas?.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && pad.classList.contains("is-fullscreen-fallback")) { event.preventDefault(); setHandwritingFullscreen(pad, false); }
      if (stateForPad.readonly) return;
      const modifier = event.ctrlKey || event.metaKey;
      if (modifier && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) pad.querySelector("[data-handwriting-redo]")?.click();
        else pad.querySelector("[data-handwriting-undo]")?.click();
      } else if (!modifier && event.key.toLowerCase() === "e") {
        event.preventDefault();
        setHandwritingTool(pad, "eraser");
      } else if (!modifier && event.key.toLowerCase() === "p") {
        event.preventDefault();
        setHandwritingTool(pad, "pen");
      }
    });
    pad.querySelector("[data-handwriting-toggle]")?.addEventListener("click", () => {
      const collapsed = pad.classList.toggle("is-collapsed");
      const button = pad.querySelector("[data-handwriting-toggle]");
      button?.setAttribute("aria-expanded", String(!collapsed));
      const label = button?.querySelector("[data-handwriting-toggle-label]");
      if (label) label.textContent = collapsed ? "展开手写" : "收起手写";
      window.requestAnimationFrame?.(() => resizeHandwritingPad(pad));
    });
    pad.querySelector("[data-handwriting-fullscreen]")?.addEventListener("click", () => toggleHandwritingFullscreen(pad));
    $$('[data-handwriting-tool]', pad).forEach((button) => button.addEventListener("click", () => setHandwritingTool(pad, button.dataset.handwritingTool)));
    pad.querySelector("[data-handwriting-size]")?.addEventListener("input", (event) => {
      if (stateForPad.readonly) return;
      stateForPad.strokeWidth = Math.max(1, Math.min(8, Number(event.target.value) || 2.4));
      updateHandwritingStatus(pad, `笔画 ${stateForPad.strokeWidth.toFixed(1)} px`);
    });
    pad.querySelector("[data-handwriting-save]")?.addEventListener("click", () => {
      if (stateForPad.readonly || !stateForPad.strokes.length) return;
      saveHandwritingPad(pad, "manual-save");
      updateHandwritingStatus(pad, "已暂存，可直接提交");
    });
    pad.querySelector("[data-handwriting-undo]")?.addEventListener("click", () => {
      if (stateForPad.readonly || !stateForPad.strokes.length) return;
      stateForPad.redo.push(stateForPad.strokes.pop());
      saveHandwritingPad(pad, "undo");
    });
    pad.querySelector("[data-handwriting-redo]")?.addEventListener("click", () => {
      if (stateForPad.readonly || !stateForPad.redo.length) return;
      stateForPad.strokes.push(stateForPad.redo.pop());
      saveHandwritingPad(pad, "redo");
    });
    pad.querySelector("[data-handwriting-clear]")?.addEventListener("click", () => {
      if (stateForPad.readonly || !stateForPad.strokes.length) return;
      if (typeof window.confirm === "function" && !window.confirm("清空当前手写作答吗？")) return;
      stateForPad.redo = stateForPad.strokes.slice();
      stateForPad.strokes = [];
      HANDWRITING_UPLOAD_CACHE.delete(stateForPad.key);
      saveHandwritingPad(pad, "clear");
    });
    if (typeof ResizeObserver !== "undefined" && wrap) new ResizeObserver(() => resizeHandwritingPad(pad)).observe(wrap);
    resizeHandwritingPad(pad);
    updateHandwritingStatus(pad);
    drawHandwritingPad(pad);
  });
}

function renderHandwritingPad({ key = "unknown", readonly = false, expanded = false } = {}) {
  return `<section class="handwriting-pad ${readonly ? "is-readonly" : ""} ${expanded ? "" : "is-collapsed"}" data-handwriting-pad data-handwriting-key="${escapeAttr(key)}" data-handwriting-readonly="${readonly ? "true" : "false"}">
    <div class="handwriting-pad-head"><div><strong>手写作答</strong><span data-handwriting-status aria-live="polite">${readonly ? "已提交 · 只读查看" : "未开始"}</span></div><div class="handwriting-actions" role="toolbar" aria-label="手写作答工具">
      ${handwritingToolButtonMarkup("pen", "笔", readonly)}
      ${handwritingToolButtonMarkup("eraser", "橡皮", readonly)}
      <label class="handwriting-size-control"><span>粗细</span><input type="range" data-handwriting-size min="1" max="8" step="0.5" value="2.4" aria-label="笔画粗细" ${readonly ? "disabled" : ""} /></label>
      <button type="button" class="handwriting-action" data-handwriting-toggle aria-expanded="${expanded ? "true" : "false"}"><span data-handwriting-toggle-label>${expanded ? "收起" : "展开"}</span></button>
      <button type="button" class="handwriting-action handwriting-fullscreen-button" data-handwriting-fullscreen>${readonly ? "全屏查看" : "全屏书写"}</button>
      <button type="button" class="handwriting-action icon-action" data-handwriting-undo aria-label="撤销手写" title="撤销（Ctrl/Cmd + Z）" ${readonly ? "disabled" : ""}>↶</button>
      <button type="button" class="handwriting-action icon-action" data-handwriting-redo aria-label="重做手写" title="重做（Ctrl/Cmd + Shift + Z）" ${readonly ? "disabled" : ""}>↷</button>
      <button type="button" class="handwriting-action" data-handwriting-save ${readonly ? "disabled" : ""}>暂存</button>
      <button type="button" class="handwriting-action" data-handwriting-clear ${readonly ? "disabled" : ""}>清空</button>
    </div></div>
    <div class="handwriting-canvas-wrap" data-handwriting-canvas-wrap><canvas class="handwriting-canvas" data-handwriting-canvas tabindex="0" role="img" aria-label="手写作答区域" aria-keyshortcuts="P E Control+Z Control+Shift+Z"></canvas><span class="handwriting-empty" data-handwriting-empty>在这里完成手写答案 · 支持手指、触控笔和鼠标</span></div>
    <div class="handwriting-pad-foot"><span data-handwriting-updated>未提交前仅保存在本机</span><span>手写内容会作为作答图片提交 · <span data-handwriting-tool-label>画笔</span></span></div>
  </section>`;
}

function renderFormulaEditor({ id, value = "", readonly = false, answerAttribute = "", label = "LaTeX 作答", placeholder = "先写文字，再用工具插入公式，例如：函数在区间上连续。", questionType = "fill" }) {
  const editorId = domId(id);
  const inputId = editorId === "modal-answer" ? "answer-input" : `${editorId}-input`;
  return `<div class="formula-editor" data-formula-editor="${escapeAttr(editorId)}">
    <div class="formula-editor-layout">
      <div class="formula-source-pane">
        <div class="formula-pane-head"><label for="${escapeAttr(inputId)}">${escapeHtml(label)}</label><span>文字和公式混合</span></div>
        <textarea id="${escapeAttr(inputId)}" ${answerAttribute} data-formula-input="${escapeAttr(editorId)}" rows="5" spellcheck="false" ${readonly ? "readonly" : ""} placeholder="${escapeAttr(placeholder)}">${escapeHtml(value)}</textarea>
        <div class="editor-meta-row"><span>Enter 自动延续分点 · Tab 缩进 · Ctrl/Cmd + B 加粗</span><span class="editor-count" data-editor-count aria-live="polite">${editorCharacterCount(value)} 字</span></div>
        ${formulaToolbarMarkup(editorId, readonly, questionType)}
      </div>
      <div class="formula-preview-pane">
        <div class="formula-pane-head"><span>实时预览</span><span class="formula-engine">KaTeX</span></div>
        <div class="formula-live-preview" data-formula-preview="${escapeAttr(editorId)}">${renderAnswerPreview(value)}</div>
      </div>
    </div>
  </div>`;
}

function renderChoiceEditor({ question, value = "", readonly = false, answerAttribute = "", id = "modal-choice" }) {
  const selected = String(value || "").trim().toUpperCase();
  const editorId = domId(id);
  const inputId = editorId === "modal-choice" ? "answer-input" : `${editorId}-input`;
  const options = extractChoiceOptions(question.question_markdown);
  return `<div class="choice-editor" data-choice-editor="${escapeAttr(editorId)}" tabindex="0" role="radiogroup" aria-label="选择题选项">
    <div class="choice-editor-head"><span>选择一个选项</span><span><kbd>A</kbd>-<kbd>D</kbd> 或 <kbd>1</kbd>-<kbd>4</kbd> 快速作答</span></div>
    <div class="choice-options">${options.map((option, index) => `<button type="button" class="choice-option ${selected === option.label ? "selected" : ""}" data-choice-value="${escapeAttr(option.label)}" role="radio" aria-checked="${selected === option.label ? "true" : "false"}" ${readonly ? "disabled" : ""}><span class="choice-letter">${escapeHtml(option.label)}</span><span class="choice-option-text markdown-body">${renderMarkdown(option.text)}</span><span class="choice-check" aria-hidden="true">✓</span></button>`).join("")}</div>
    <textarea id="${escapeAttr(inputId)}" class="choice-value" ${answerAttribute} data-choice-input="${escapeAttr(editorId)}" aria-hidden="true" tabindex="-1" ${readonly ? "readonly" : ""}>${escapeHtml(selected)}</textarea>
    <p class="choice-helper">还没想好也没关系，先选最有把握的一项，提交后可以回看解析。</p>
  </div>`;
}

function renderAnswerEditor(question, { mode = "modal", value = "", readonly = false, contextId = "", draftKey = "" } = {}) {
  const answerAttribute = mode === "practice"
    ? `data-practice-answer="${escapeAttr(question.id)}"`
    : mode === "simulation"
      ? `data-sim-answer="${escapeAttr(question.id)}"`
      : "";
  const handwritingKey = draftKey || answerHandwritingKey(mode, question.id, contextId);
  const workspaceHint = question.question_type === "choice"
    ? "选项、手写或图片"
    : question.question_type === "fill"
      ? "文字、公式、手写或图片"
      : "步骤、手写或图片";
  const workspaceState = readonly ? "已提交 · 只读查看" : "提交前可随时暂存";
  const workspace = (content) => `<section class="answer-workspace" data-answer-workspace data-answer-question="${escapeAttr(question.id)}" data-answer-mode="${escapeAttr(mode)}"><div class="answer-workspace-head"><div><strong>作答工作区</strong><span>${escapeHtml(workspaceState)}</span></div><span class="answer-workspace-hint">${escapeHtml(workspaceHint)}</span></div>${content}</section>`;
  if (question.question_type === "choice") {
    return workspace(`<div class="answer-editor-surface">${renderChoiceEditor({ question, value, readonly, answerAttribute, id: mode === "modal" ? "modal-choice" : `${mode}-choice-${question.id}` })}${renderHandwritingPad({ key: handwritingKey, readonly, expanded: mode === "modal" })}</div>`);
  }
  const editor = renderFormulaEditor({
    id: mode === "modal" ? "modal-answer" : `${mode}-answer-${question.id}`,
    value,
    readonly,
    answerAttribute,
    label: question.question_type === "fill" ? "填写答案" : "我的解题过程",
    placeholder: question.question_type === "fill" ? "输入最终结果，点击工具插入分数、根式、积分等公式。" : "先写解题步骤，公式直接点工具插入，需要时再修改字母或数字。",
    questionType: question.question_type,
  });
  return workspace(`<div class="answer-editor-surface">${editor}${renderHandwritingPad({ key: handwritingKey, readonly, expanded: mode === "modal" })}</div>`);
}

function insertFormulaSnippet(field, button) {
  const tex = button.dataset.formulaTex || "";
  const select = button.dataset.formulaSelect || "";
  const display = button.dataset.formulaWrap === "display";
  const wrapper = display ? "$$" : "$";
  const start = field.selectionStart ?? field.value.length;
  const end = field.selectionEnd ?? start;
  const before = field.value.slice(0, start);
  const after = field.value.slice(end);
  const spacer = before && !/\s$/.test(before) ? " " : "";
  const snippet = `${wrapper}${tex}${wrapper}`;
  const insertAt = start + spacer.length;
  field.value = `${before}${spacer}${snippet}${after}`;
  const selectionAt = select ? snippet.indexOf(select) : snippet.length;
  const selectionEnd = select ? selectionAt + select.length : selectionAt;
  field.focus();
  field.setSelectionRange(insertAt + selectionAt, insertAt + selectionEnd);
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

function insertFormulaIntoContentEditable(editor, button) {
  if (!editor) return;
  const tex = button.dataset.formulaTex || "";
  const wrapper = button.dataset.formulaWrap === "display" ? "$$" : "$";
  editor.focus();
  restoreNoteSelection();
  document.execCommand("insertText", false, `${wrapper}${tex}${wrapper}`);
  state.noteSavedRange = null;
  markNoteDirty();
}

function nextStructuredNumber(value, pattern) {
  const numbers = [...String(value || "").matchAll(pattern)].map((match) => Number(match[1])).filter(Number.isFinite);
  return numbers.length ? Math.max(...numbers) + 1 : 1;
}

function cursorAfterFormula(value, position) {
  const source = String(value || "");
  const patterns = [/\$\$[\s\S]*?\$\$/g, /\$[^$\n]*\$/g, /\\\([\s\S]*?\\\)/g, /\\\[[\s\S]*?\\\]/g];
  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) {
      const start = match.index ?? 0;
      const end = start + match[0].length;
      if (position >= start && position <= end) return end;
    }
  }
  return position;
}

function insertAnswerStructure(field, action) {
  if (!field) return;
  const cursor = cursorAfterFormula(field.value, field.selectionEnd ?? field.value.length);
  const before = field.value.slice(0, cursor);
  const after = field.value.slice(cursor);
  const trailingNewlines = before.match(/\n*$/)?.[0].length || 0;
  const requiredBreaks = action === "subquestion" ? 2 : 1;
  const lineBreak = "\n".repeat(Math.max(0, requiredBreaks - trailingNewlines));
  const marker = action === "point"
    ? `${nextStructuredNumber(field.value, /(?:^|\n)\s*(\d+)[.、)]\s/g)}. `
    : action === "subquestion"
      ? `（${nextStructuredNumber(field.value, /(?:^|\n)\s*[（(](\d+)[）)]\s/g)}） `
      : "";
  const insertion = `${lineBreak}${marker}`;
  field.value = `${before}${insertion}${after}`;
  const nextCursor = cursor + insertion.length;
  field.focus();
  field.setSelectionRange(nextCursor, nextCursor);
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

function editorCharacterCount(value) {
  return Array.from(String(value || "")).length;
}

function updateEditorCount(root, value) {
  const counter = root?.querySelector?.("[data-editor-count]") || (root?.matches?.("[data-editor-count]") ? root : null);
  if (counter) counter.textContent = String(editorCharacterCount(value)) + " 字";
}

const TEXT_EDITOR_HISTORY = new WeakMap();

function ensureTextEditorHistory(field) {
  if (!field || typeof field.value !== "string") return null;
  let history = TEXT_EDITOR_HISTORY.get(field);
  if (!history) {
    history = {
      past: [],
      future: [],
      value: field.value,
      selectionStart: field.selectionStart ?? field.value.length,
      selectionEnd: field.selectionEnd ?? field.value.length,
    };
    TEXT_EDITOR_HISTORY.set(field, history);
  }
  return history;
}

function resetTextEditorHistory(field) {
  if (!field) return;
  TEXT_EDITOR_HISTORY.delete(field);
  ensureTextEditorHistory(field);
}

function rememberTextEditorChange(field) {
  const history = ensureTextEditorHistory(field);
  if (!history || history.value === field.value) return;
  history.past.push({ value: history.value, selectionStart: history.selectionStart, selectionEnd: history.selectionEnd });
  if (history.past.length > 80) history.past.shift();
  history.future = [];
  history.value = field.value;
  history.selectionStart = field.selectionStart ?? field.value.length;
  history.selectionEnd = field.selectionEnd ?? history.selectionStart;
}

function dispatchEditorInput(field) {
  rememberTextEditorChange(field);
  field?.dispatchEvent(new Event("input", { bubbles: true }));
}

function insertTextAtSelection(field, text, selectStart = String(text || "").length, selectEnd = selectStart) {
  if (!field) return;
  const value = String(field.value || "");
  const start = field.selectionStart ?? value.length;
  const end = field.selectionEnd ?? start;
  const insertion = String(text || "");
  field.value = value.slice(0, start) + insertion + value.slice(end);
  const nextStart = start + selectStart;
  field.focus();
  field.setSelectionRange(nextStart, start + selectEnd);
  dispatchEditorInput(field);
}

function wrapTextareaSelection(field, before, after, placeholder) {
  if (!field) return;
  const value = String(field.value || "");
  const start = field.selectionStart ?? value.length;
  const end = field.selectionEnd ?? start;
  const selected = value.slice(start, end) || placeholder;
  const insertion = String(before || "") + selected + String(after || "");
  field.value = value.slice(0, start) + insertion + value.slice(end);
  const innerStart = start + String(before || "").length;
  field.focus();
  field.setSelectionRange(innerStart, innerStart + selected.length);
  dispatchEditorInput(field);
}

function insertMarkdownLink(field) {
  if (!field) return;
  const value = String(field.value || "");
  const start = field.selectionStart ?? value.length;
  const end = field.selectionEnd ?? start;
  const label = value.slice(start, end) || "链接文字";
  const insertion = "[" + label + "](https://)";
  const urlStart = start + label.length + 3;
  field.value = value.slice(0, start) + insertion + value.slice(end);
  field.focus();
  field.setSelectionRange(urlStart, urlStart + 8);
  dispatchEditorInput(field);
}

function handleStructuredTextKeydown(field, event) {
  if (!field || event.isComposing) return false;
  const value = String(field.value || "");
  const start = field.selectionStart ?? value.length;
  const end = field.selectionEnd ?? start;
  const modifier = event.ctrlKey || event.metaKey;
  if (event.key === "Tab" && !modifier && !event.altKey) {
    event.preventDefault();
    const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    if (event.shiftKey) {
      const removed = value.slice(lineStart, lineStart + 2).match(/^ {1,2}/)?.[0] || "";
      if (!removed) return true;
      field.value = value.slice(0, lineStart) + value.slice(lineStart + removed.length);
      field.focus();
      field.setSelectionRange(Math.max(lineStart, start - removed.length), Math.max(lineStart, end - removed.length));
    } else {
      field.value = value.slice(0, lineStart) + "  " + value.slice(lineStart);
      field.focus();
      field.setSelectionRange(start + 2, end + 2);
    }
    dispatchEditorInput(field);
    return true;
  }
  if (event.key === "Enter" && !event.shiftKey && !modifier && !event.altKey && start === end) {
    const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    const linePrefix = value.slice(lineStart, start);
    const lineEnd = value.indexOf("\n", start);
    const line = value.slice(lineStart, lineEnd < 0 ? value.length : lineEnd);
    const unordered = linePrefix.match(/^(\s*)([-*+])\s+(.*)$/);
    const ordered = linePrefix.match(/^(\s*)(\d+)([.、)])\s+(.*)$/);
    const emptyUnordered = linePrefix.match(/^(\s*)([-*+])\s*$/);
    const emptyOrdered = linePrefix.match(/^(\s*)(\d+)([.、)])\s*$/);
    if (emptyUnordered || emptyOrdered) {
      event.preventDefault();
      const indent = (emptyUnordered || emptyOrdered)[1] || "";
      const replacement = indent + "\n";
      field.value = value.slice(0, lineStart) + replacement + value.slice(start);
      field.focus();
      field.setSelectionRange(lineStart + replacement.length, lineStart + replacement.length);
      dispatchEditorInput(field);
      return true;
    }
    if (unordered || ordered) {
      event.preventDefault();
      const indent = (unordered || ordered)[1] || "";
      const marker = unordered
        ? (unordered[2] || "-") + " "
        : String(Number(ordered[2]) + 1) + (ordered[3] || ".") + " ";
      const insertion = "\n" + indent + marker;
      field.value = value.slice(0, start) + insertion + value.slice(start);
      field.focus();
      field.setSelectionRange(start + insertion.length, start + insertion.length);
      dispatchEditorInput(field);
      return true;
    }
    if (line && linePrefix === line && /^\s+$/.test(line)) {
      event.preventDefault();
      const indent = line.match(/^\s*/)?.[0] || "";
      insertTextAtSelection(field, "\n" + indent);
      return true;
    }
  }
  if (modifier && !event.altKey) {
    const key = event.key.toLowerCase();
    if (key === "b" || key === "i" || key === "u") {
      event.preventDefault();
      const marks = { b: ["**", "**"], i: ["*", "*"], u: ["__", "__"] };
      wrapTextareaSelection(field, marks[key][0], marks[key][1], key === "b" ? "重点内容" : "文字");
      return true;
    }
    if (key === "k") {
      event.preventDefault();
      insertMarkdownLink(field);
      return true;
    }
  }
  return false;
}

function runTextEditorCommand(field, command) {
  if (!field || field.readOnly) return;
  field.focus();
  if (command === "link") {
    insertMarkdownLink(field);
    return;
  }
  if (command === "bold" || command === "italic" || command === "underline") {
    const marks = {
      bold: ["**", "**", "重点内容"],
      italic: ["*", "*", "文字"],
      underline: ["__", "__", "文字"],
    }[command];
    wrapTextareaSelection(field, marks[0], marks[1], marks[2]);
    return;
  }
  if (command === "heading") {
    insertTextAtSelection(field, "\n### ");
    return;
  }
  if (command === "highlight") {
    wrapTextareaSelection(field, "==", "==", "重点内容");
    return;
  }
  if (command === "undo" || command === "redo") {
    const history = ensureTextEditorHistory(field);
    if (!history) return;
    const from = command === "undo" ? history.past : history.future;
    const to = command === "undo" ? history.future : history.past;
    if (!from.length) return;
    to.push({ value: field.value, selectionStart: field.selectionStart ?? field.value.length, selectionEnd: field.selectionEnd ?? field.value.length });
    const snapshot = from.pop();
    field.value = snapshot.value;
    field.focus();
    field.setSelectionRange(snapshot.selectionStart, snapshot.selectionEnd);
    history.value = field.value;
    history.selectionStart = snapshot.selectionStart;
    history.selectionEnd = snapshot.selectionEnd;
    dispatchEditorInput(field);
  }
}

function setDisclosure(button, panel, open) {
  if (!button || !panel) return;
  panel.hidden = !open;
  button.setAttribute("aria-expanded", String(open));
  button.classList.toggle("is-open", open);
}

function selectFormulaCategory(editor, category) {
  const selected = String(category);
  $$('[data-formula-category]', editor).forEach((button) => {
    const active = button.dataset.formulaCategory === selected;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  $$('[data-formula-group-panel]', editor).forEach((panel) => {
    panel.hidden = panel.dataset.formulaGroupPanel !== selected;
  });
}

function selectChoice(editor, value) {
  const input = editor.querySelector("[data-choice-input]");
  if (!input) return;
  input.value = value;
  $$('[data-choice-value]', editor).forEach((button) => {
    const selected = button.dataset.choiceValue === value;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-checked", selected ? "true" : "false");
  });
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function bindAnswerEditors(root = document) {
  $$('[data-formula-editor]', root).forEach((editor) => {
    if (editor.dataset.bound === "true") return;
    editor.dataset.bound = "true";
    const editorId = editor.dataset.formulaEditor || "";
    const field = editor.querySelector("[data-formula-input]")
      || (editorId === "note-markdown" ? $("note-markdown-editor") : null);
    const richNoteTarget = editorId === "note-rich" ? $("note-rich-editor") : null;
    const preview = editor.querySelector("[data-formula-preview]");
    ensureTextEditorHistory(field);
    const update = () => {
      if (field) rememberTextEditorChange(field);
      if (preview && field) preview.innerHTML = renderAnswerPreview(field.value);
      if (richNoteTarget) {
        renderNoteRichPreview();
        updateNoteEditorStats();
      }
      updateEditorCount(editor, field?.value || richNoteTarget?.innerText || "");
      if (state.practiceSession) updatePracticeSessionStatus();
    };
    field?.addEventListener("input", update);
    $$('[data-formula-tool]', editor).forEach((button) => button.addEventListener("click", () => {
      if (field) insertFormulaSnippet(field, button);
      else if (richNoteTarget) insertFormulaIntoContentEditable(richNoteTarget, button);
    }));
    $$('[data-editor-command]', editor).forEach((button) => button.addEventListener("click", () => runTextEditorCommand(field, button.dataset.editorCommand)));
    $$('[data-editor-insert]', editor).forEach((button) => button.addEventListener("click", () => {
      const action = button.dataset.editorInsert;
      if (action === "point" || action === "subquestion") insertAnswerStructure(field, action);
      else if (action === "quote") insertTextAtSelection(field, "\n> ");
      else if (action === "unordered") insertTextAtSelection(field, "\n- ");
      else if (action === "ordered") insertTextAtSelection(field, "\n1. ");
    }));
    field?.addEventListener("keydown", (event) => {
      const handled = handleStructuredTextKeydown(field, event);
      if (handled) return;
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && editor.closest(".practice-session-shell")) {
        event.preventDefault();
        $("submit-practice-session")?.click();
      }
    });
    $$('[data-formula-toggle]', editor).forEach((button) => button.addEventListener("click", () => {
      setDisclosure(button, editor.querySelector("[data-formula-tools-panel]"), button.getAttribute("aria-expanded") !== "true");
    }));
    $$('[data-formula-category]', editor).forEach((button) => button.addEventListener("click", () => {
      selectFormulaCategory(editor, button.dataset.formulaCategory);
    }));
    $$('[data-answer-structure-toggle]', editor).forEach((button) => button.addEventListener("click", () => {
      setDisclosure(button, editor.querySelector("[data-answer-structure-panel]"), button.getAttribute("aria-expanded") !== "true");
    }));
    $$('[data-structure-action]', editor).forEach((button) => button.addEventListener("click", () => insertAnswerStructure(field, button.dataset.structureAction)));
  });
  $$('[data-choice-editor]', root).forEach((editor) => {
    if (editor.dataset.bound === "true") return;
    editor.dataset.bound = "true";
    $$('[data-choice-value]', editor).forEach((button) => button.addEventListener("click", () => selectChoice(editor, button.dataset.choiceValue)));
    editor.addEventListener("keydown", (event) => {
      const key = event.key.toUpperCase();
      const digitIndex = /^[1-4]$/.test(event.key) ? Number(event.key) - 1 : -1;
      const choice = /^[A-D]$/.test(key) ? key : editor.querySelectorAll("[data-choice-value]")[digitIndex]?.dataset.choiceValue;
      if (choice) {
        event.preventDefault();
        const button = $$('[data-choice-value]', editor).find((item) => item.dataset.choiceValue === choice);
        if (button && !button.disabled) selectChoice(editor, choice);
      }
    });
  });
  bindHandwritingPads(root);
}

function typeLabel(type) {
  return { choice: "选择", fill: "填空", solution: "解答" }[type] || type || "题目";
}

function conceptName(id) {
  return state.concepts.find((concept) => concept.id === id)?.name || id;
}

function workbenchConcept(conceptId) {
  return (state.workbenchCatalog || []).find((concept) => concept.id === conceptId) || null;
}

function subtypeDescriptor(subtypeId) {
  for (const concept of state.workbenchCatalog || []) {
    const subtype = (concept.subtypes || []).find((item) => item.id === subtypeId);
    if (subtype) return { ...subtype, concept_id: subtype.concept_id || concept.id, concept_name: concept.name };
  }
  return null;
}

function subtypeName(subtypeId) {
  return subtypeDescriptor(subtypeId)?.name || subtypeId || "未细分";
}

function questionSubtypeLabels(question) {
  if (Array.isArray(question?.subtype_labels) && question.subtype_labels.length) return question.subtype_labels;
  return (question?.subtype_ids || []).map((id) => ({ id, name: subtypeName(id) }));
}

function questionSubtypeMarkup(question) {
  const labels = questionSubtypeLabels(question);
  if (!labels.length) return `<span class="concept-label classification-unassigned">待纠正分类</span>`;
  return labels.map((item) => `<span class="concept-label subtype-label" title="${escapeAttr(item.summary || item.name || "")}">${escapeHtml(item.name || subtypeName(item.id))}</span>`).join("");
}

function math2ConceptOptions(selected = "") {
  return (state.concepts || []).map((concept) => `<option value="${escapeAttr(concept.id)}" ${concept.id === selected ? "selected" : ""}>${escapeHtml(concept.name)}</option>`).join("");
}

function subtypeOptionsMarkup(conceptId = "", selected = "", includeAll = false) {
  const groups = conceptId
    ? [workbenchConcept(conceptId)].filter(Boolean)
    : (state.workbenchCatalog || []);
  const options = groups.flatMap((concept) => (concept.subtypes || []).map((item) => ({ ...item, concept_name: concept.name })));
  const prefix = includeAll ? `<option value="">全部细分题型</option>` : `<option value="">选择具体题型</option>`;
  const body = options.map((item) => `<option value="${escapeAttr(item.id)}" ${item.id === selected ? "selected" : ""}>${escapeHtml(conceptId ? item.name : `${item.concept_name} · ${item.name}`)}</option>`).join("");
  return prefix + body;
}

function classificationEditorMarkup(question, location = "row") {
  const concepts = questionConceptLabels(question);
  const math2Concept = concepts.find((item) => item.scope === "math2")?.id || question.concept_ids?.[0] || "";
  const subtypeId = questionSubtypeLabels(question)[0]?.id || "";
  const sourceLabel = question.classification_source === "user-correction" ? "用户纠正" : question.classification_source === "unclassified" ? "待分类" : "规则分类";
  return `<div class="classification-control ${location === "modal" ? "classification-control-modal" : ""}" data-classification-question="${escapeAttr(question.id)}">
    <div class="classification-summary"><span class="classification-source">${escapeHtml(sourceLabel)}</span><span class="classification-summary-text">${escapeHtml(subtypeName(subtypeId))}</span><button type="button" class="text-button classification-open" data-open-correction>纠正分类</button></div>
    <div class="classification-editor" data-correction-panel hidden>
      <div class="classification-editor-head"><strong>重新归类</strong><span>只影响你的筛选、训练和推荐，不改动原始真题。</span></div>
      <div class="classification-fields"><label>知识块<select data-correction-concept>${math2ConceptOptions(math2Concept)}</select></label><label>具体题型<select data-correction-subtype>${subtypeOptionsMarkup(math2Concept, subtypeId)}</select></label></div>
      <textarea data-correction-note rows="2" maxlength="240" placeholder="可选：写下为什么这样归类，方便以后复核。">${escapeHtml(question.classification_note || "")}</textarea>
      <div class="classification-editor-actions"><button type="button" class="secondary-button classification-cancel" data-cancel-correction>取消</button><button type="button" class="primary-button classification-save" data-save-classification>保存分类</button></div>
      <p class="classification-status" data-classification-status></p>
    </div>
  </div>`;
}

function populateSubtypeFilter() {
  const select = $("filter-subtype");
  if (!select) return;
  const current = select.value;
  select.innerHTML = subtypeOptionsMarkup($("filter-concept")?.value || "", current, true);
  if ([...select.options].some((option) => option.value === current)) select.value = current;
  else select.value = "";
}

function populateCorrectionSubtype(select, conceptId, selected = "") {
  if (!select) return;
  select.innerHTML = subtypeOptionsMarkup(conceptId, selected, false);
  if (![...select.options].some((option) => option.value === selected)) select.value = "";
}

function questionConceptLabels(question) {
  if (Array.isArray(question?.concept_labels) && question.concept_labels.length) return question.concept_labels;
  return (question?.concept_ids || []).map((id) => ({ id, name: conceptName(id), scope: "unknown", scope_label: "未标注范围" }));
}

function questionConceptMarkup(question) {
  return questionConceptLabels(question).map((concept) => `<span class="concept-label ${concept.scope === "out-of-syllabus" ? "out-of-syllabus" : ""}">${escapeHtml(concept.scope === "out-of-syllabus" ? `${concept.scope_label} · ${concept.name}` : concept.name)}</span>`).join("");
}

function practiceQuestionSubtypeLine(question) {
  return questionSubtypeLabels(question).map((item) => item.name || subtypeName(item.id)).join(" · ") || typeLabel(question.question_type);
}

function formatScore(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "暂无";
  const number = Number(value);
  return Number.isInteger(number) ? String(number) : number.toFixed(1);
}

function showToast(message, error = false) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.toggle("error", error);
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3200);
}

function showNotice(message) {
  const notice = $("app-notice");
  notice.textContent = message;
  notice.classList.toggle("show", Boolean(message));
}

function readCookie(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const pair = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith(prefix));
  return pair ? decodeURIComponent(pair.slice(prefix.length)) : "";
}

function renderAuthenticatedUser() {
  const user = state.user || {};
  state.userId = user.id || "local-user";
  const label = user.display_name || user.username || "本地学习者";
  const avatar = [...label].slice(0, 1).join("").toUpperCase() || "L";
  $("user-avatar") && ($("user-avatar").textContent = avatar);
  $("user-chip-name") && ($("user-chip-name").textContent = label);
  const admin = user.role === "admin";
  const adminNav = $("admin-nav") || document.querySelector(".admin-nav");
  if (adminNav) adminNav.hidden = !admin;
  const badge = $("account-role-badge");
  if (badge) badge.textContent = admin ? "⌁ 管理员" : "⌁ 用户";
  const logout = $("logout-button");
  if (logout) logout.hidden = !state.authenticated;
}

function resetUserScopedState() {
  window.clearInterval(state.simulationTimer);
  state.userId = "local-user";
  state.user = null;
  state.csrfToken = "";
  state.authenticated = false;
  state.stats = null;
  state.progress = null;
  state.forecast = null;
  state.analytics = null;
  state.blocks = [];
  state.nextQuestions = [];
  state.concepts = [];
  state.exams = [];
  state.settings = null;
  state.serverSettings = null;
  state.accountSettings = null;
  state.workbenchCatalog = [];
  state.workbenchTemplate = null;
  state.notes = [];
  state.currentNote = null;
  state.currentQuestion = null;
  state.practiceSession = null;
  state.currentSimulation = null;
  state.simulationTimer = null;
  state.simulationDeadline = null;
  state.simulationCurrentIndex = 0;
  state.view = "overview";
  $$(".view").forEach((element) => element.classList.toggle("active", element.id === "view-overview"));
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === "overview"));
  if ($("view-kicker") && viewMeta.overview) $("view-kicker").textContent = viewMeta.overview[0];
  if ($("view-title") && viewMeta.overview) $("view-title").textContent = viewMeta.overview[1];
  document.body.classList.remove("theme-dark");
}

function setAuthState(payload) {
  const nextUser = payload?.user || null;
  if (state.user?.id && nextUser?.id && state.user.id !== nextUser.id) resetUserScopedState();
  state.user = nextUser;
  state.userId = state.user?.id || "local-user";
  state.csrfToken = payload?.csrf_token || readCookie("ai_math_csrf");
  state.authenticated = Boolean(state.user?.id);
  renderAuthenticatedUser();
  if (state.authenticated) applyAccountTheme(state.user?.preferences?.theme || "system");
}

function setAuthMode(mode) {
  state.authMode = mode === "register" ? "register" : "login";
  const register = state.authMode === "register";
  $("login-form")?.toggleAttribute("hidden", register);
  $("register-form")?.toggleAttribute("hidden", !register);
  const activeForm = register ? $("register-form") : $("login-form");
  activeForm?.classList.remove("auth-form-enter");
  if (activeForm) window.requestAnimationFrame?.(() => activeForm.classList.add("auth-form-enter"));
  if ($("auth-title")) $("auth-title").textContent = register ? "创建你的学习空间" : "登录你的学习空间";
  if ($("auth-description")) $("auth-description").textContent = register ? "首个账户会成为本地工作区管理员，之后可以管理账户和权限。" : "登录后，作答、笔记、训练进度和模型配置都会只属于当前账户。";
  if ($("auth-switch-copy")) $("auth-switch-copy").textContent = register ? "已经有账户？" : "还没有账户？";
  if ($("auth-switch")) $("auth-switch").textContent = register ? "返回登录" : "注册新账户";
  if ($("auth-mode-badge")) $("auth-mode-badge").textContent = register ? "CREATE A SPACE" : "SECURE SIGN IN";
  const progress = $("auth-progress");
  if (progress) progress.toggleAttribute("hidden", !register);
  if ($("auth-progress-copy")) $("auth-progress-copy").textContent = register ? "账户凭据 · 可选资料稍后补充" : "";
  if ($("auth-step-mark")) $("auth-step-mark").textContent = register ? "STEP 1 / 1" : "LOCAL / PRIVATE";
  const optional = $("register-optional-fields");
  if (!register && optional) optional.open = false;
  $("auth-status")?.classList.remove("error");
  if ($("auth-status")) $("auth-status").textContent = "";
}

function setAuthConnection(message = "", visible = false) {
  const connection = $("auth-connection");
  if (!connection) return;
  connection.toggleAttribute("hidden", !visible);
  if (message && $("auth-connection-copy")) $("auth-connection-copy").textContent = message;
}

function showAuthScreen(message = "", { connection = false, info = false } = {}) {
  resetUserScopedState();
  setAuthMode("login");
  document.body.classList.add("auth-pending");
  $("auth-screen")?.removeAttribute("hidden");
  $("auth-status") && ($("auth-status").textContent = message);
  $("auth-status")?.classList.toggle("error", Boolean(message && !info && !connection));
  setAuthConnection(connection ? message : "", connection);
  $("login-identifier")?.focus({ preventScroll: true });
}

function hideAuthScreen() {
  document.body.classList.remove("auth-pending");
  $("auth-screen")?.setAttribute("hidden", "");
  setAuthConnection();
}

async function submitAuthForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector("button[type=submit]");
  const status = $("auth-status");
  if (submit) { submit.disabled = true; submit.setAttribute("aria-busy", "true"); }
  if (status) { status.textContent = "正在验证……"; status.classList.remove("error"); }
  try {
    const payload = state.authMode === "register"
      ? { username: $("register-username")?.value || "", email: $("register-email")?.value || "", display_name: $("register-display-name")?.value || "", password: $("register-password")?.value || "" }
      : { identifier: $("login-identifier")?.value || "", password: $("login-password")?.value || "" };
    const response = await fetchJSON(state.authMode === "register" ? "/api/auth/register" : "/api/auth/login", jsonOptions(payload));
    setAuthState(response);
    hideAuthScreen();
    if (status) status.textContent = "";
    showToast(state.authMode === "register" && response.first_account_is_admin ? "账户已创建，你是本地工作区管理员。" : "登录成功。");
    await loadOverview();
  } catch (error) {
    if (status) { status.textContent = error.message; status.classList.add("error"); }
  } finally {
    if (submit) { submit.disabled = false; submit.removeAttribute("aria-busy"); }
  }
}

async function bootstrapAuth() {
  try {
    const payload = await fetchJSON("/api/auth/me", { timeoutMs: 12000 });
    setAuthState(payload);
    hideAuthScreen();
    return true;
  } catch (error) {
    const message = String(error?.message || "");
    const connectionError = error?.name === "TypeError" || error?.name === "TimeoutError" || /Failed to fetch|NetworkError|Load failed|无法连接|超时/i.test(message);
    if (connectionError) {
      showAuthScreen("无法连接本地服务，请先运行启动脚本后重试。", { connection: true });
    } else if (message.includes("尚未注册")) {
      showAuthScreen("请先创建账户，首个账户将自动获得管理员权限。", { info: true });
    } else {
      showAuthScreen("登录已失效，请重新登录。");
    }
    return false;
  }
}

async function retryAuthConnection() {
  const button = $("auth-retry");
  if (button) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "连接中……";
  }
  try {
    if (await bootstrapAuth()) {
      applyWorkbenchTheme();
      await loadOverview();
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.textContent = "重新连接";
    }
  }
}

async function logout() {
  try {
    await fetchJSON("/api/auth/logout", { method: "POST" });
  } catch (error) {
    if (!String(error.message).includes("请先登录")) showToast(`退出登录失败：${error.message}`, true);
  }
  state.user = null;
  state.authenticated = false;
  state.csrfToken = "";
  showAuthScreen();
}

async function fetchJSON(url, options = {}) {
  const requestOptions = { ...options, credentials: "same-origin" };
  const timeoutMs = Number(options.timeoutMs) > 0 ? Number(options.timeoutMs) : 30000;
  delete requestOptions.timeoutMs;
  const headers = new Headers(options.headers || {});
  const method = String(requestOptions.method || "GET").toUpperCase();
  if (!new Set(["GET", "HEAD", "OPTIONS"]).has(method) && state.csrfToken) headers.set("X-CSRF-Token", state.csrfToken);
  requestOptions.headers = headers;
  let timeoutId = 0;
  let controller = null;
  if (!requestOptions.signal && typeof AbortController !== "undefined") {
    controller = new AbortController();
    requestOptions.signal = controller.signal;
    timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  }
  let response;
  try {
    response = await fetch(url, requestOptions);
  } catch (error) {
    if (error?.name === "AbortError" && controller) {
      const timeoutError = new Error("本地服务响应超时，请确认服务已启动。");
      timeoutError.name = "TimeoutError";
      throw timeoutError;
    }
    throw error;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) {
    if (response.status === 401 && state.authenticated) showAuthScreen("登录已失效，请重新登录。");
    throw new Error(payload.detail || `请求失败（HTTP ${response.status}）`);
  }
  return payload;
}

function jsonOptions(payload) {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) };
}

function validateImageFile(file) {
  const allowed = ["image/png", "image/jpeg", "image/webp", "image/gif"];
  if (!file) return "";
  if (!allowed.includes(file.type)) return "只支持 PNG、JPG、WebP 或 GIF 图片。";
  if (file.size > 8 * 1024 * 1024) return "图片不能超过 8 MB。";
  return "";
}

function clearImagePreview(preview) {
  if (!preview) return;
  const objectUrl = preview.dataset.objectUrl;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  preview.dataset.objectUrl = "";
  preview.innerHTML = "";
  preview.hidden = true;
}

function showImagePreview(file, preview, status) {
  const error = validateImageFile(file);
  clearImagePreview(preview);
  if (error) {
    if (status) status.textContent = error;
    return false;
  }
  if (!file) {
    if (status) status.textContent = "支持 PNG/JPG/WebP/GIF，单张不超过 8 MB";
    return true;
  }
  const objectUrl = URL.createObjectURL(file);
  preview.dataset.objectUrl = objectUrl;
  preview.innerHTML = `<img src="${escapeAttr(objectUrl)}" alt="作答图片预览" /><span>${escapeHtml(file.name)} · ${(file.size / 1024 / 1024).toFixed(2)} MB</span>`;
  preview.hidden = false;
  if (status) status.textContent = "已选择，提交作答时会保存到本机";
  return true;
}

async function uploadAnswerImage(file, questionId) {
  const error = validateImageFile(file);
  if (error) throw new Error(error);
  const formData = new FormData();
  formData.append("file", file);
  formData.append("user_id", state.userId);
  formData.append("question_id", questionId);
  return fetchJSON("/api/uploads/answer-image", { method: "POST", body: formData });
}

function handwritingPadToBlob(pad) {
  const canvas = pad?.querySelector("[data-handwriting-canvas]");
  if (!canvas || typeof canvas.toBlob !== "function" || !handwritingPadHasContent(pad)) return Promise.resolve(null);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
}

async function uploadHandwritingPad(pad, questionId) {
  const stateForPad = handwritingStateFor(pad);
  if (!stateForPad || stateForPad.readonly || !questionId || !handwritingPadHasContent(pad)) return null;
  const cachedId = HANDWRITING_UPLOAD_CACHE.get(stateForPad.key) || pad.dataset.handwritingAttachmentId;
  if (cachedId) return cachedId;
  updateHandwritingStatus(pad, "正在整理手写作答……");
  const blob = await handwritingPadToBlob(pad);
  if (!blob) throw new Error("当前手写内容无法生成图片，请重试。");
  const file = typeof File === "function"
    ? new File([blob], `handwriting-${String(questionId).slice(0, 48)}.png`, { type: "image/png" })
    : blob;
  const uploaded = await uploadAnswerImage(file, questionId);
  const attachmentId = uploaded?.attachment_id || "";
  if (!attachmentId) throw new Error("手写图片上传未返回附件编号。");
  HANDWRITING_UPLOAD_CACHE.set(stateForPad.key, attachmentId);
  pad.dataset.handwritingAttachmentId = attachmentId;
  updateHandwritingStatus(pad, "已准备提交");
  return attachmentId;
}

async function collectHandwritingAttachments(root, target, { questionId = "" } = {}) {
  const pads = $$('[data-handwriting-pad]', root);
  for (const pad of pads) {
    const workspace = pad.closest("[data-answer-workspace]");
    const resolvedQuestionId = workspace?.dataset.answerQuestion || questionId;
    if (!resolvedQuestionId) continue;
    const attachmentId = await uploadHandwritingPad(pad, resolvedQuestionId);
    if (!attachmentId) continue;
    if (Array.isArray(target)) {
      if (!target.includes(attachmentId)) target.push(attachmentId);
    } else {
      const current = Array.isArray(target[resolvedQuestionId]) ? target[resolvedQuestionId] : [];
      if (!current.includes(attachmentId)) target[resolvedQuestionId] = [...current, attachmentId];
    }
  }
  return target;
}

function clearHandwritingDrafts(root) {
  $$('[data-handwriting-pad]', root).forEach((pad) => forgetHandwritingDraft(pad));
}

function simulationDraftKey(simulationId) {
  return `ai-math-simulation-draft-${state.userId || "local-user"}-${simulationId}`;
}

function simulationPointerKey() {
  return `ai-math-simulation-${state.userId || "local-user"}`;
}

function readSavedSimulationId() {
  return localStorage.getItem(simulationPointerKey()) || localStorage.getItem("ai-math-simulation");
}

function saveSimulationPointer(simulationId) {
  localStorage.setItem(simulationPointerKey(), simulationId);
  // The unscoped key existed before accounts. Remove it once the pointer has
  // been claimed by the current account so another account cannot inherit it.
  localStorage.removeItem("ai-math-simulation");
}

function readSimulationDraft(simulation = state.currentSimulation) {
  const empty = { answers: {}, selfGrades: {} };
  if (!simulation?.id) return empty;
  try {
    const parsed = JSON.parse(localStorage.getItem(simulationDraftKey(simulation.id)) || "{}");
    return {
      answers: parsed.answers && typeof parsed.answers === "object" ? parsed.answers : {},
      selfGrades: parsed.selfGrades && typeof parsed.selfGrades === "object" ? parsed.selfGrades : {},
    };
  } catch {
    return empty;
  }
}

function simulationDraftForQuestion(simulation, question, draft = readSimulationDraft(simulation)) {
  return {
    answer: draft.answers[question.id] ?? question.attempt?.answer ?? "",
    selfGrade: draft.selfGrades[question.id] ?? "",
  };
}

function simulationHandwritingKey(simulation, questionId) {
  return answerHandwritingKey("simulation", questionId, simulation?.id || "draft");
}

function simulationDataField(root, attribute, dataKey, questionId) {
  return $$(`[${attribute}]`, root).find((field) => field.dataset[dataKey] === String(questionId));
}

function simulationQuestionHasDraft(simulation, question, draft = readSimulationDraft(simulation), root = null) {
  const answerField = root ? simulationDataField(root, "data-sim-answer", "simAnswer", question.id) : null;
  const gradeField = root ? simulationDataField(root, "data-sim-grade", "simGrade", question.id) : null;
  const imageField = root ? simulationDataField(root, "data-sim-image", "simImage", question.id) : null;
  const answer = answerField ? answerField.value : draft.answers[question.id] ?? question.attempt?.answer ?? "";
  const selfGrade = gradeField ? gradeField.value : draft.selfGrades[question.id] ?? "";
  const hasImage = Boolean(imageField?.files?.length || question.attempt?.attachments?.length);
  return Boolean(String(answer || "").trim() || String(selfGrade || "").trim() || hasImage || handwritingHasDraft(simulationHandwritingKey(simulation, question.id)));
}

function collectSimulationDraft(root = document) {
  const answers = {};
  const selfGrades = {};
  $$('[data-sim-answer]', root).forEach((field) => { answers[field.dataset.simAnswer] = field.value; });
  $$('[data-sim-grade]', root).forEach((field) => { selfGrades[field.dataset.simGrade] = field.value; });
  return { answers, selfGrades, updatedAt: new Date().toISOString() };
}

function saveSimulationDraft(root = document) {
  const simulation = state.currentSimulation;
  if (!simulation?.id || simulation.status === "finished") return;
  const draft = collectSimulationDraft(root);
  const hasAnswer = Object.values(draft.answers).some((value) => String(value || "").trim());
  const hasGrade = Object.values(draft.selfGrades).some((value) => String(value || "").trim());
  const hasHandwriting = (simulation.questions || []).some((question) => handwritingHasDraft(simulationHandwritingKey(simulation, question.id)));
  if (hasAnswer || hasGrade || hasHandwriting) localStorage.setItem(simulationDraftKey(simulation.id), JSON.stringify(draft));
  else localStorage.removeItem(simulationDraftKey(simulation.id));
}

function simulationQuestionAnswered(simulation, question, root = document, draft = readSimulationDraft(simulation)) {
  return simulationQuestionHasDraft(simulation, question, draft, root);
}

function simulationAnsweredCount(simulation = state.currentSimulation, root = document) {
  if (!simulation) return 0;
  const draft = readSimulationDraft(simulation);
  return (simulation.questions || []).filter((question) => simulationQuestionAnswered(simulation, question, root, draft)).length;
}

function renderSimulationAnswerCard(simulation, finished) {
  const questions = simulation.questions || [];
  const draft = readSimulationDraft(simulation);
  const answered = questions.filter((question) => simulationQuestionHasDraft(simulation, question, draft)).length;
  const cardMarkup = questions.map((question, index) => {
    const isAnswered = simulationQuestionHasDraft(simulation, question, draft);
    const isCurrent = index === state.simulationCurrentIndex;
    const status = isAnswered ? "已作答" : "未作答";
    return `<button type="button" class="simulation-card-item ${isAnswered ? "answered" : "unanswered"} ${isCurrent ? "current" : ""}" data-sim-card data-sim-index="${index}" data-sim-question="${escapeAttr(question.id)}" aria-label="第 ${question.number} 题，${status}" ${isCurrent ? 'aria-current="true"' : ""}><span class="simulation-card-number">${String(index + 1).padStart(2, "0")}</span><span class="simulation-card-type">${escapeHtml(typeLabel(question.question_type))}</span></button>`;
  }).join("");
  return `<div class="simulation-answer-card ${finished ? "finished" : ""}">
    <div class="simulation-card-head"><div><span class="simulation-card-kicker">ANSWER MAP</span><h4>答题卡</h4></div><strong><span data-sim-answered-count>${answered}</span><small> / ${questions.length}</small></strong></div>
    <div class="simulation-card-progress-copy"><span>已完成题目</span><span>点击题号可跳转</span></div>
    <div class="simulation-card-filters" role="tablist" aria-label="答题卡筛选">
      <button type="button" class="simulation-card-filter is-active" data-sim-filter="all" role="tab" aria-selected="true"><span>全部</span><b data-sim-filter-count="all">${questions.length}</b></button>
      <button type="button" class="simulation-card-filter" data-sim-filter="unanswered" role="tab" aria-selected="false"><span>未答</span><b data-sim-filter-count="unanswered">${questions.length - answered}</b></button>
      <button type="button" class="simulation-card-filter" data-sim-filter="answered" role="tab" aria-selected="false"><span>已答</span><b data-sim-filter-count="answered">${answered}</b></button>
    </div>
    <div class="simulation-card-grid">${cardMarkup || `<p class="simulation-card-empty">暂无题目</p>`}</div>
    <div class="simulation-card-legend"><span><i class="answered"></i>已答</span><span><i class="unanswered"></i>未答</span><span><i class="current"></i>当前</span></div>
  </div>`;
}

function applySimulationCardFilter(root = document) {
  const filter = state.simulationCardFilter;
  $$('[data-sim-card]', root).forEach((card) => {
    const hide = filter === "answered" ? !card.classList.contains("answered") : filter === "unanswered" ? !card.classList.contains("unanswered") : false;
    card.classList.toggle("is-filtered", hide);
  });
  $$('[data-sim-filter]', root).forEach((button) => {
    const active = button.dataset.simFilter === filter;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
}

function setSimulationCurrent(index, root = document) {
  const total = state.currentSimulation?.questions?.length || 0;
  const maxIndex = Math.max(0, total - 1);
  state.simulationCurrentIndex = Math.max(0, Math.min(Number(index) || 0, maxIndex));
  $$('[data-sim-card]', root).forEach((card) => {
    const current = Number(card.dataset.simIndex) === state.simulationCurrentIndex;
    card.classList.toggle("current", current);
    if (current) card.setAttribute("aria-current", "true");
    else card.removeAttribute("aria-current");
  });
  $$('.simulation-question[data-sim-index]', root).forEach((question) => question.classList.toggle("is-current", Number(question.dataset.simIndex) === state.simulationCurrentIndex));
}

function refreshSimulationAnswerCard(root = document) {
  const simulation = state.currentSimulation;
  if (!simulation) return;
  const draft = readSimulationDraft(simulation);
  let answered = 0;
  $$('[data-sim-card]', root).forEach((card) => {
    const index = Number(card.dataset.simIndex);
    const question = simulation.questions?.[index];
    if (!question) return;
    const isAnswered = simulationQuestionAnswered(simulation, question, root, draft);
    if (isAnswered) answered += 1;
    card.classList.toggle("answered", isAnswered);
    card.classList.toggle("unanswered", !isAnswered);
    card.setAttribute("aria-label", `第 ${question.number} 题，${isAnswered ? "已作答" : "未作答"}`);
  });
  $$('[data-sim-answered-count]', root).forEach((element) => { element.textContent = String(answered); });
  $$('[data-sim-filter-count="all"]', root).forEach((element) => { element.textContent = String(simulation.questions?.length || 0); });
  $$('[data-sim-filter-count="answered"]', root).forEach((element) => { element.textContent = String(answered); });
  $$('[data-sim-filter-count="unanswered"]', root).forEach((element) => { element.textContent = String((simulation.questions?.length || 0) - answered); });
  const bar = $("simulation-progress-bar");
  if (bar) bar.style.setProperty("--progress", String(answered / Math.max(1, simulation.questions?.length || 1)));
  setSimulationCurrent(state.simulationCurrentIndex, root);
  applySimulationCardFilter(root);
}

function bindSimulationPlatform(root) {
  if (!root || root.dataset.simPlatformBound === "true") return;
  root.dataset.simPlatformBound = "true";
  const updateDraft = () => {
    saveSimulationDraft(root);
    refreshSimulationAnswerCard(root);
  };
  root.addEventListener("input", (event) => {
    if (event.target?.matches?.("[data-sim-answer], [data-sim-grade]")) updateDraft();
  });
  root.addEventListener("change", (event) => {
    if (event.target?.matches?.("[data-sim-answer], [data-sim-grade]")) updateDraft();
  });
  root.addEventListener("handwritingchange", updateDraft);
  root.addEventListener("focusin", (event) => {
    const question = event.target.closest?.(".simulation-question[data-sim-index]");
    if (question) setSimulationCurrent(question.dataset.simIndex, root);
  });
  $$('[data-sim-filter]', root).forEach((button) => button.addEventListener("click", () => {
    state.simulationCardFilter = button.dataset.simFilter || "all";
    applySimulationCardFilter(root);
  }));
  $$('[data-sim-card]', root).forEach((button) => button.addEventListener("click", () => {
    const index = Number(button.dataset.simIndex);
    setSimulationCurrent(index, root);
    const question = $$('.simulation-question[data-sim-index]', root).find((item) => Number(item.dataset.simIndex) === index);
    question?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    const focusTarget = question?.querySelector("[data-formula-input], [data-choice-editor]");
    focusTarget?.focus?.({ preventScroll: true });
  }));
  refreshSimulationAnswerCard(root);
}

function canLeaveSimulation(nextView) {
  const simulation = state.currentSimulation;
  if (!simulation || simulation.status === "finished" || state.view !== "simulation" || nextView === "simulation") return true;
  const answered = simulationAnsweredCount(simulation, $("simulation-container") || document);
  const total = simulation.questions?.length || 0;
  return window.confirm(`模拟考尚未交卷，当前已答 ${answered} / ${total} 题。离开后计时仍会继续，文字与手写内容会保留。确定离开吗？`);
}

function handleSimulationBeforeUnload(event) {
  if (!state.currentSimulation || state.currentSimulation.status === "finished") return;
  event.preventDefault();
  event.returnValue = "模拟考尚未交卷";
}

function navigate(view) {
  if (!viewMeta[view]) return;
  if (!state.authenticated) { showAuthScreen(); return; }
  if (view === "admin" && state.user?.role !== "admin") { showToast("只有管理员可以打开管理后台。", true); return; }
  if (!canLeaveSimulation(view)) return;
  state.view = view;
  $$(".view").forEach((element) => element.classList.toggle("active", element.id === `view-${view}`));
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("view-kicker").textContent = viewMeta[view][0];
  $("view-title").textContent = viewMeta[view][1];
  if (view === "overview") return loadOverview();
  if (view === "workbench") return loadWorkbench();
  if (view === "library") return loadLibrary();
  if (view === "blocks") return loadBlocks();
  if (view === "simulation") return loadSimulationCatalog();
  if (view === "analytics") return loadAnalytics();
  if (view === "settings") return loadSettings();
  if (view === "admin") return loadAdmin();
  return undefined;
}

async function refreshCurrentView() {
  const button = $("refresh-button");
  const originalLabel = button.textContent;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = "刷新中…";
  try {
    await navigate(state.view);
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.textContent = originalLabel;
  }
}

function renderOverview() {
  const stats = state.stats || {};
  const progress = state.progress || {};
  const forecast = state.forecast || {};
  const scoreRange = forecast.score_range || {};
  const outerRange = forecast.outer_range || {};
  $("metric-questions").textContent = stats.total_questions ?? "读取中";
  $("metric-attempts").textContent = progress.attempts ?? 0;
  $("metric-mastery").textContent = progress.overall_mastery == null ? "0%" : `${formatScore(progress.overall_mastery)}%`;
  $("metric-focus").textContent = state.blocks[0]?.concept?.name || "暂无";
  $("forecast-score-range").innerHTML = forecast.available ? `${formatScore(scoreRange.low)}<i>至</i>${formatScore(scoreRange.high)}<span> / ${formatScore(forecast.max_score)}</span>` : "0<i>至</i>0<span> / 150</span>";
  $("forecast-outer-low").textContent = forecast.available ? formatScore(outerRange.low) : "0";
  $("forecast-outer-high").textContent = forecast.available ? formatScore(outerRange.high) : "0";
  $("forecast-meta").textContent = forecast.available ? `置信度 ${forecast.confidence} · 已使用 ${forecast.attempts_used} 次作答 · 覆盖 ${forecast.concepts_used || 0} 个知识块 · 近三年 ${((forecast.paper_years || []).join("、")) || "—"}` : (forecast.reason || "等待题库数据");
  $("forecast-note").textContent = forecast.note || "区间会随着真实作答和模拟考更新。";

  const blocks = state.blocks.slice(0, 3);
  $("overview-blocks").innerHTML = blocks.length ? blocks.map(renderBlockPreview).join("") : `<div class="loading-card">完成第一道题后，系统会生成你的训练分块。</div>`;
  $$("[data-block-concept]", $("overview-blocks")).forEach((element) => element.addEventListener("click", () => {
    navigate("blocks");
  }));

  const questions = state.nextQuestions.slice(0, 4);
  $("overview-questions").innerHTML = questions.length ? questions.map(renderQuestionMini).join("") : `<div class="loading-card">当前没有可推荐题目。</div>`;
  bindQuestionOpeners($("overview-questions"));
}

function notePreviewText(note) {
  if (note?.content_markdown) return note.content_markdown;
  const holder = document.createElement("div");
  holder.innerHTML = note?.content_html || "";
  return holder.innerText || holder.textContent || "";
}

function renderWorkbenchConcepts() {
  const root = $("workbench-concept-list");
  if (!root) return;
  const concepts = state.workbenchCatalog || [];
  $("workbench-total").textContent = concepts.length ? `${concepts.length} 个知识块` : "暂无";
  root.innerHTML = concepts.length
    ? concepts.map((concept) => {
      return `<button type="button" class="workbench-concept-item ${concept.id === state.workbenchConceptId ? "is-active" : ""}" data-workbench-concept="${escapeAttr(concept.id)}"><span class="workbench-concept-copy"><strong>${escapeHtml(concept.name)}</strong><small>${escapeHtml(concept.subject)} / ${concept.total_questions || 0} 道真题</small></span><span class="workbench-concept-count" title="${concept.subtype_count || 0} 个细分题型">${concept.subtype_count || 0}</span></button>`;
    }).join("")
    : `<div class="loading-card">题库没有可用知识块。</div>`;
  $$('[data-workbench-concept]', root).forEach((button) => button.addEventListener("click", () => selectWorkbenchConcept(button.dataset.workbenchConcept)));
}

function renderWorkbenchSubtypeTabs() {
  const root = $("workbench-type-tabs");
  if (!root) return;
  const concept = state.workbenchCatalog.find((item) => item.id === state.workbenchConceptId) || {};
  const subtypes = concept.subtypes || [];
  if (!subtypes.some((item) => item.id === state.workbenchSubtypeId)) state.workbenchSubtypeId = subtypes[0]?.id || "";
  const query = state.workbenchSubtypeQuery.trim().toLocaleLowerCase("zh-CN");
  const visibleSubtypes = query
    ? subtypes.filter((item) => `${item.name} ${item.summary || ""}`.toLocaleLowerCase("zh-CN").includes(query))
    : subtypes;
  const count = $("workbench-subtype-count");
  if (count) count.textContent = query ? `${visibleSubtypes.length} / ${subtypes.length} 类匹配` : `${subtypes.length} 类具体考法`;
  root.innerHTML = visibleSubtypes.length
    ? visibleSubtypes.map((item) => `<button type="button" class="workbench-type-tab ${item.id === state.workbenchSubtypeId ? "is-active" : ""}" data-workbench-subtype="${escapeAttr(item.id)}" role="tab" aria-selected="${item.id === state.workbenchSubtypeId ? "true" : "false"}" tabindex="${item.id === state.workbenchSubtypeId ? "0" : "-1"}"><strong>${escapeHtml(item.name)}</strong><small>${item.matched_question_count || 0} 道真题命中 · 已做 ${item.attempted_question_count || 0} 道</small></button>`).join("")
    : `<div class="workbench-subtype-empty"><strong>没有匹配的细分题型</strong><span>换一个关键词，或清空筛选查看当前知识块的全部题型。</span><button type="button" class="text-button" id="clear-workbench-subtype-search">清空筛选</button></div>`;
  $$('[data-workbench-subtype]', root).forEach((button) => button.addEventListener("click", () => selectWorkbenchSubtype(button.dataset.workbenchSubtype)));
  $("clear-workbench-subtype-search")?.addEventListener("click", () => {
    state.workbenchSubtypeQuery = "";
    const input = $("workbench-subtype-search");
    if (input) input.value = "";
    renderWorkbenchSubtypeTabs();
    input?.focus();
  });
}

function workbenchQuestionMarkup(item, label, variant = false) {
  const question = item?.question;
  if (!question) return `<article class="workbench-question-card empty-question"><span class="eyebrow">${escapeHtml(label)}</span><p>当前题库没有找到真实题目。</p></article>`;
  const analysis = item.analysis || question.solution_markdown || "";
  const answer = item.answer || question.answer_markdown || "";
  const yearAndNumber = `${question.year} 年第 ${question.number} 题`;
  const solutionHint = variant ? "完成后再展开" : "来源答案与完整解析";
  return `<article class="workbench-question-card ${variant ? "variant-question" : "example-question"}">
    <header class="workbench-question-head"><div class="workbench-question-identity"><span>${escapeHtml(label)}</span><strong>${escapeHtml(yearAndNumber)}</strong></div><div class="workbench-question-badges"><span class="difficulty-pill ${escapeAttr(question.difficulty_band || "other")}">${escapeHtml(question.difficulty_label || "待分层")}</span><span class="type-pill">${escapeHtml(typeLabel(question.question_type))}</span>${questionAttemptMarkup(question, true)}</div></header>
    <div class="workbench-study-grid">
      <section class="workbench-question-pane" aria-label="${escapeAttr(label)}题目"><div class="workbench-pane-head"><strong>题目</strong><span>完整题面</span></div><div class="workbench-question-body markdown-body">${renderMarkdown(question.question_markdown || "")}</div><footer class="workbench-question-foot"><span>${escapeHtml(item.source_scope || (question.concept_labels || []).map((concept) => concept.name).join("、") || "真实题库")}</span>${questionAttemptMarkup(question, true)}<button type="button" class="text-button" data-question-id="${escapeAttr(question.id)}">进入作答</button></footer></section>
      <aside class="workbench-solution-pane" aria-label="${escapeAttr(label)}答案与解析"><details class="workbench-solution-details" ${variant ? "" : "open"}><summary><span><strong>答案与解析</strong><small>${escapeHtml(solutionHint)}</small></span><b aria-hidden="true">展开</b></summary><div class="workbench-solution-content">${answer ? `<div class="workbench-answer-line"><b>答案</b><span class="markdown-body">${renderMarkdown(answer)}</span></div>` : ""}<div class="workbench-analysis-body markdown-body">${renderMarkdown(analysis)}</div></div></details></aside>
    </div>
  </article>`;
}

function templateListEditor(key, values) {
  const items = values.length ? values : [""];
  return `<div class="template-edit-list" data-template-list="${escapeAttr(key)}">${items.map((value, index) => `<div class="template-edit-row"><span>${index + 1}</span><input type="text" value="${escapeAttr(value)}" data-template-list-item="${escapeAttr(key)}" /><button type="button" class="text-button" data-template-remove="${escapeAttr(key)}" aria-label="删除第 ${index + 1} 项">删除</button></div>`).join("")}<button type="button" class="text-button template-add-button" data-template-add="${escapeAttr(key)}">＋ 添加一条</button></div>`;
}

function workbenchSectionHeadingMarkup(title, description, meta = "") {
  return `<div class="workbench-section-head"><div><h4>${escapeHtml(title)}</h4><p>${escapeHtml(description)}</p></div>${meta ? `<span>${escapeHtml(meta)}</span>` : ""}</div>`;
}

function templateInsightCards(items, options = {}) {
  const titleKey = options.titleKey || "label";
  const bodyKey = options.bodyKey || "content";
  const className = options.className || "template-insight-grid";
  return `<div class="${escapeAttr(className)}">${(items || []).map((item, index) => `<article class="template-insight-card"><span>${String(index + 1).padStart(2, "0")}</span><div><strong>${escapeHtml(item[titleKey] || "学习提示")}</strong><div class="markdown-body">${renderMarkdown(item[bodyKey] || "")}</div></div></article>`).join("")}</div>`;
}

function templateQuestionTypeMarkup(items) {
  return `<div class="template-format-grid">${(items || []).map((item) => `<article class="template-format-card" data-question-format="${escapeAttr(item.type || "")}"><header><strong>${escapeHtml(item.label || "题型")}</strong>${renderLearningText(item.focus, "template-format-focus")}</header>${renderLearningText(item.steps, "template-format-steps")}<footer>${renderLearningText(item.finish, "template-format-finish")}</footer></article>`).join("")}</div>`;
}

function templatePracticeMarkup(levels, checklist) {
  const levelMarkup = (levels || []).map((item, index) => `<li><span>${String(index + 1).padStart(2, "0")}</span><div><strong>${escapeHtml(item.level || "训练")}</strong>${renderLearningText(item.task, "template-practice-task")}<div class="template-practice-standard"><span>达标：</span>${renderLearningText(item.standard)}</div></div></li>`).join("");
  const checklistMarkup = (checklist || []).map((item) => `<li><input type="checkbox" tabindex="-1" aria-hidden="true" />${renderLearningText(item, "template-check-item")}</li>`).join("");
  return `<div class="template-practice-check-grid"><section><span class="template-section-label">三层训练路径</span><ol class="template-practice-levels">${levelMarkup}</ol></section><section><span class="template-section-label">交卷前 30 秒检查</span><ul class="template-exam-checklist">${checklistMarkup}</ul></section></div>`;
}

function templateGuideMarkup(template, framework, formulaSheet, mistakes) {
  const recognition = template.recognition || [];
  const directions = template.exam_directions || [];
  return `<div class="template-guide">
    <nav class="template-quick-nav" aria-label="答题模板段落导航"><span>快速定位</span><button type="button" data-template-target="template-recognition">识别题型</button><button type="button" data-template-target="template-directions">命题方向</button><button type="button" data-template-target="template-answer-chain">答题得分链</button><button type="button" data-template-target="template-formats">分题型策略</button><button type="button" data-template-target="template-example">真实例题</button></nav>
    <section class="template-overview template-rich-text markdown-body" id="template-recognition"><span class="template-section-label">这类题在考什么</span>${renderMarkdown(template.overview || "")}${templateInsightCards(recognition)}</section>
    <section class="template-directions" id="template-directions">${workbenchSectionHeadingMarkup("常见命题方向", "从直接计算到参数、证明、综合与伪装变式，先识别命题层级再动笔。", `${directions.length} 类方向`)}${templateInsightCards(directions, { titleKey: "title", bodyKey: "detail", className: "template-direction-grid" })}</section>
    ${formulaSheet ? `<section class="template-formula-card"><div><span class="template-section-label">公式卡片</span><small>先理解使用条件，再代入计算</small></div><div class="template-formula-body markdown-body">${renderMarkdown(formulaSheet)}</div></section>` : ""}
    <div id="template-answer-chain">${renderAnswerStructure(template)}</div>
    <section class="template-format-section" id="template-formats">${workbenchSectionHeadingMarkup("选择、填空、解答怎么写", "同一知识点在不同题面形式下，计算深度、书写要求和验算方式不同。", "3 种题面形式")}${templateQuestionTypeMarkup(template.question_type_guides)}</section>
    <section class="template-training-section">${workbenchSectionHeadingMarkup("从会认到会迁移", "按层训练，避免只会复述模板却无法识别变式。", "识别 · 执行 · 迁移")}${templatePracticeMarkup(template.practice_levels, template.exam_checklist)}</section>
    <div class="template-guide-columns"><section><span class="template-section-label">推荐作答顺序</span><ol>${framework.map((item) => `<li>${renderTemplateText(item)}</li>`).join("")}</ol></section><section class="template-mistakes"><span class="template-section-label">容易丢分的地方</span><ul>${mistakes.map((item) => `<li>${renderTemplateText(item)}</li>`).join("")}</ul></section></div>
    <section class="template-memory"><span>考场提醒</span>${renderTemplateText(template.memory_aid || "")}</section>
  </div>`;
}

function templateAnswerText(template) {
  return (template.answer_structure || []).map((item, index) => `${index + 1}. ${item.label}\n${item.content}`).join("\n\n");
}

async function copyWorkbenchAnswerTemplate() {
  const text = templateAnswerText(state.workbenchTemplate || {});
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    showToast("六步答题骨架已复制，可粘贴到答题区或笔记。", false);
  } catch {
    showToast("无法自动复制，请在模板中手动选择答题结构。", true);
  }
}

function bindWorkbenchTemplateActions(card) {
  $$('[data-template-target]', card).forEach((button) => button.addEventListener("click", () => {
    card.querySelector(`#${button.dataset.templateTarget}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  $("copy-workbench-answer-template")?.addEventListener("click", copyWorkbenchAnswerTemplate);
  $("start-workbench-practice")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await navigate("blocks");
      await startPracticeSession(state.workbenchConceptId, "", state.workbenchSubtypeId, [], button);
    } catch (error) {
      showToast(`专项训练启动失败：${error.message}`, true);
      button.disabled = false;
    }
  });
}

function renderWorkbenchTemplate() {
  const template = state.workbenchTemplate;
  const card = $("workbench-template-card");
  if (!card) return;
  const concept = state.workbenchCatalog.find((item) => item.id === state.workbenchConceptId) || {};
  $("workbench-current-title").textContent = template ? `${template.concept_name} / ${template.subtype_name}` : (concept.name || "选择知识块");
  $("workbench-current-meta").textContent = template ? `${template.matched_question_count || 0} 道细分命中 / 选择、填空、解答仅作题面形式标签${template.customized ? " / 已有个人修改" : ""}` : "每种具体考法都配有框架、易错点和真实题例。";
  if (!template) {
    card.innerHTML = `<div class="loading-card">请选择一个知识块和细分题型。</div>`;
    return;
  }
  const framework = template.framework || [];
  const formulaSheet = template.formula_sheet || "";
  const mistakes = template.mistakes || [];
  const summaryMarkup = state.workbenchEditingTemplate
    ? `<div class="template-editing-form"><label>题型概述<textarea rows="4" data-template-field="overview">${escapeHtml(template.overview || "")}</textarea></label><div class="template-edit-columns"><label>解题思路框架${templateListEditor("framework", framework)}</label><label>常见易错点${templateListEditor("mistakes", mistakes)}</label></div><label>记忆提醒<input type="text" data-template-field="memory_aid" value="${escapeAttr(template.memory_aid || "")}" /></label></div>`
    : templateGuideMarkup(template, framework, formulaSheet, mistakes);
  const variantItems = template.variants || [];
  state.workbenchVariantIndex = Math.max(0, Math.min(state.workbenchVariantIndex, Math.max(variantItems.length - 1, 0)));
  const activeVariant = variantItems[state.workbenchVariantIndex];
  const variantTabs = variantItems.map((item, index) => {
    const question = item.question || {};
    return `<button type="button" class="workbench-variant-tab ${index === state.workbenchVariantIndex ? "is-active" : ""}" data-workbench-variant="${index}" role="tab" aria-selected="${index === state.workbenchVariantIndex ? "true" : "false"}"><span>变式 ${index + 1}</span><small>${escapeHtml(question.year || "")} 年第 ${escapeHtml(question.number || "")} 题</small></button>`;
  }).join("");
  const variantViewer = activeVariant ? workbenchQuestionMarkup(activeVariant, `变式 ${state.workbenchVariantIndex + 1}`, true) : `<div class="loading-card">暂无可用变式题。</div>`;
  const sourceNote = template.example_source === "无直接题目"
    ? "当前题库没有找到可核验的该细分题型真题，不展示其他题型作为替代。"
    : "例题与变式只使用细分题型直接命中的真实题目。";
  const primaryActions = state.workbenchEditingTemplate ? "" : `<button type="button" class="secondary-button" id="copy-workbench-answer-template">复制六步骨架</button><button type="button" class="primary-button" id="start-workbench-practice">开始专项训练</button>`;
  card.innerHTML = `<header class="workbench-template-head"><div><span class="workbench-template-path">${escapeHtml(template.subject)} / ${escapeHtml(template.concept_name)}</span><h3>${escapeHtml(template.subtype_name)}</h3><div class="workbench-template-summary">${renderLearningText(template.subtype_summary || "")}<span>${escapeHtml(sourceNote)}</span></div></div><div class="template-head-actions">${template.customized ? `<span class="custom-template-mark">已自定义</span>` : ""}${primaryActions}<button type="button" class="secondary-button" id="refresh-workbench-variants">换一组题</button><button type="button" class="secondary-button" id="edit-workbench-template">${state.workbenchEditingTemplate ? "继续编辑" : "编辑模板"}</button>${state.workbenchEditingTemplate ? `<button type="button" class="quiet-button" id="cancel-workbench-template">取消</button><button type="button" class="primary-button" id="save-workbench-template">保存模板</button>` : ""}</div></header>${summaryMarkup}<section class="workbench-example-section" id="template-example">${workbenchSectionHeadingMarkup("先看一道完整例题", "题目在左，来源答案与解析在右，可以进入作答区独立完成。", "完整题面与来源解析")}${workbenchQuestionMarkup(template.example, "典型例题")}</section><section class="workbench-variants-section">${workbenchSectionHeadingMarkup("再做变式练习", "一次只展示一道，换题会优先避开当前例题和变式，避免来回重复。", `${template.variant_count || 0} 道真实题`)}<div class="workbench-variant-switcher" role="tablist" aria-label="选择变式题">${variantTabs}</div><div class="workbench-variant-viewer">${variantViewer}</div>${variantItems.length > 1 ? `<nav class="workbench-variant-nav" aria-label="切换变式题"><button type="button" class="quiet-button" id="workbench-variant-prev" ${state.workbenchVariantIndex === 0 ? "disabled" : ""}>上一道</button><span>${state.workbenchVariantIndex + 1} / ${variantItems.length}</span><button type="button" class="secondary-button" id="workbench-variant-next" ${state.workbenchVariantIndex === variantItems.length - 1 ? "disabled" : ""}>下一道</button></nav>` : ""}</section>`;
  bindQuestionOpeners(card);
  bindWorkbenchTemplateActions(card);
  if (state.workbenchEditingTemplate) bindTemplateEditor(card);
  $$('[data-workbench-variant]', card).forEach((button) => button.addEventListener("click", () => {
    state.workbenchVariantIndex = Number(button.dataset.workbenchVariant || 0);
    renderWorkbenchTemplate();
  }));
  $("workbench-variant-prev")?.addEventListener("click", () => { state.workbenchVariantIndex -= 1; renderWorkbenchTemplate(); });
  $("workbench-variant-next")?.addEventListener("click", () => { state.workbenchVariantIndex += 1; renderWorkbenchTemplate(); });
  $("refresh-workbench-variants")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      state.workbenchVariantIndex = 0;
      await loadWorkbenchTemplate(true);
      showToast("已换一组真实例题与变式题。", false);
    } catch (error) {
      showToast(`换题失败：${error.message}`, true);
      button.disabled = false;
    }
  });
  $("edit-workbench-template")?.addEventListener("click", () => { state.workbenchEditingTemplate = true; renderWorkbenchTemplate(); });
  $("cancel-workbench-template")?.addEventListener("click", () => { state.workbenchEditingTemplate = false; renderWorkbenchTemplate(); });
  $("save-workbench-template")?.addEventListener("click", saveWorkbenchTemplate);
}

function renderWorkbenchProgress() {
  const root = $("workbench-progress-grid");
  if (!root) return;
  const data = state.workbenchAnalytics || state.analytics || {};
  const overview = data.overview || {};
  const concept = (data.concepts || []).find((item) => item.id === state.workbenchConceptId) || {};
  const catalogConcept = state.workbenchCatalog.find((item) => item.id === state.workbenchConceptId) || {};
  const questionCount = Number(concept.question_count || catalogConcept.total_questions || 0);
  const attempted = Number(concept.attempted_question_count || 0);
  const coverage = questionCount ? Math.max(0, Math.min(100, attempted / questionCount * 100)) : 0;
  const metrics = [
    ["当前块覆盖", `${attempted} / ${questionCount}`, "已完成真实作答"],
    ["当前块掌握度", `${formatScore(concept.mastery ?? 22)}%`, concept.status || "等待作答证据"],
    ["全库覆盖", analyticsPercent(overview.coverage_rate, "0%"), `${overview.unique_questions || 0} / ${data.questions_available || 0} 道题`],
    ["工作台笔记", String(state.notes.length), "当前检索结果"],
  ];
  root.innerHTML = metrics.map(([label, value, note]) => `<div class="workbench-progress-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></div>`).join("");
  const bar = $("workbench-progress-bar");
  if (bar) bar.style.setProperty("--progress", (coverage / 100).toFixed(3));
}

function bindTemplateEditor(root) {
  $$('[data-template-add]', root).forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", () => {
    const list = root.querySelector(`[data-template-list="${button.dataset.templateAdd}"]`);
    if (!list) return;
    const key = button.dataset.templateAdd;
    const index = list.querySelectorAll("[data-template-list-item]").length + 1;
    button.insertAdjacentHTML("beforebegin", `<div class="template-edit-row"><span>${index}</span><input type="text" value="" data-template-list-item="${escapeAttr(key)}" /><button type="button" class="text-button" data-template-remove="${escapeAttr(key)}">删除</button></div>`);
    bindTemplateEditor(root);
    });
  });
  $$('[data-template-remove]', root).forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", () => {
    const rows = root.querySelectorAll(`[data-template-list="${button.dataset.templateRemove}"] .template-edit-row`);
    if (rows.length <= 1) return;
    button.closest(".template-edit-row")?.remove();
    });
  });
}

async function saveWorkbenchTemplate() {
  const card = $("workbench-template-card");
  const overview = card.querySelector('[data-template-field="overview"]')?.value || "";
  const memoryAid = card.querySelector('[data-template-field="memory_aid"]')?.value || "";
  const values = (key) => [...card.querySelectorAll(`[data-template-list-item="${key}"]`)].map((input) => input.value.trim()).filter(Boolean);
  const button = $("save-workbench-template");
  if (button) button.disabled = true;
  try {
    const payload = await fetchJSON(`/api/workbench/templates/${encodeURIComponent(state.workbenchConceptId)}/${encodeURIComponent(state.workbenchSubtypeId)}`, { ...jsonOptions({ user_id: state.userId, overview, framework: values("framework"), mistakes: values("mistakes"), memory_aid: memoryAid }), method: "PUT" });
    state.workbenchTemplate = payload.template;
    state.workbenchEditingTemplate = false;
    renderWorkbenchTemplate();
    showToast("答题模板已保存到本机。", false);
  } catch (error) {
    showToast(`模板保存失败：${error.message}`, true);
    if (button) button.disabled = false;
  }
}

async function selectWorkbenchConcept(conceptId) {
  if (!conceptId || conceptId === state.workbenchConceptId) return;
  state.workbenchConceptId = conceptId;
  state.workbenchSubtypeQuery = "";
  if ($("workbench-subtype-search")) $("workbench-subtype-search").value = "";
  state.workbenchEditingTemplate = false;
  state.workbenchVariantIndex = 0;
  renderWorkbenchConcepts();
  renderWorkbenchSubtypeTabs();
  renderWorkbenchProgress();
  await loadWorkbenchTemplate();
}

async function selectWorkbenchSubtype(subtypeId) {
  if (!subtypeId || subtypeId === state.workbenchSubtypeId) return;
  state.workbenchSubtypeId = subtypeId;
  state.workbenchEditingTemplate = false;
  state.workbenchVariantIndex = 0;
  renderWorkbenchSubtypeTabs();
  await loadWorkbenchTemplate();
}

async function loadWorkbenchTemplate(forceRefresh = false) {
  if (!state.workbenchConceptId || !state.workbenchSubtypeId) return;
  const card = $("workbench-template-card");
  card.innerHTML = `<div class="workbench-template-skeleton"><span></span><span></span><span></span></div>`;
  try {
    const params = new URLSearchParams({ concept_id: state.workbenchConceptId, subtype_id: state.workbenchSubtypeId, user_id: state.userId });
    if (forceRefresh) {
      params.set("refresh", "true");
      const currentIds = [state.workbenchTemplate?.example?.question?.id, ...(state.workbenchTemplate?.variants || []).map((item) => item.question?.id)].filter(Boolean);
      currentIds.forEach((id) => params.append("exclude_question_ids", id));
    }
    const payload = await fetchJSON(`/api/workbench?${params}`);
    state.workbenchTemplate = payload.template;
    renderWorkbenchTemplate();
  } catch (error) {
    card.innerHTML = `<div class="loading-card">模板读取失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderWorkbenchNotes() {
  const root = $("workbench-note-list");
  if (!root) return;
  root.innerHTML = state.notes.length
    ? state.notes.map((note) => `<button type="button" class="workbench-note-item ${state.currentNote?.id === note.id ? "is-active" : ""}" data-workbench-note="${escapeAttr(note.id)}"><span class="note-item-title">${note.favorite ? "收藏 · " : ""}${escapeHtml(note.title || "未命名笔记")}</span><small>${escapeHtml(conceptName(note.concept_id) || "未归类")} · ${escapeHtml(String(note.updated_at || "").slice(0, 10))}</small><span class="note-item-preview">${escapeHtml(notePreviewText(note).replace(/\s+/g, " ").slice(0, 54) || "暂无正文")}</span></button>`).join("")
    : `<div class="note-list-empty">${state.noteFavoriteOnly ? "还没有收藏笔记。" : "还没有笔记，先建立一条复盘。"}</div>`;
  $$('[data-workbench-note]', root).forEach((button) => button.addEventListener("click", () => openWorkbenchNote(button.dataset.workbenchNote)));
}

async function loadWorkbenchNotes() {
  const params = new URLSearchParams({ user_id: state.userId });
  const search = $("note-search")?.value.trim();
  if (search) params.set("search", search);
  if (state.noteFavoriteOnly) params.set("favorite", "true");
  try {
    const payload = await fetchJSON(`/api/workbench/notes?${params}`);
    state.notes = payload.items || [];
    renderWorkbenchNotes();
    renderWorkbenchProgress();
  } catch (error) {
    $("workbench-note-list").innerHTML = `<div class="note-list-empty">笔记读取失败：${escapeHtml(error.message)}</div>`;
  }
}

function populateNoteConcepts(selected = "") {
  const select = $("note-concept");
  if (!select) return;
  select.innerHTML = `<option value="">未归类</option>${(state.concepts || []).map((concept) => `<option value="${escapeAttr(concept.id)}">${escapeHtml(concept.name)}</option>`).join("")}`;
  select.value = selected || "";
}

function noteMarkdownToHtml(source) {
  const lines = String(source || "").replace(/\r/g, "").split("\n");
  const output = [];
  let paragraph = [];
  const flushParagraph = () => {
    if (!paragraph.length) return;
    output.push("<p>" + paragraph.map((line) => noteInlineMarkdownToHtml(line)).join("<br />") + "</p>");
    paragraph = [];
  };
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      flushParagraph();
      index += 1;
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      const level = Math.min(4, heading[1].length + 1);
      output.push("<h" + level + ">" + noteInlineMarkdownToHtml(heading[2]) + "</h" + level + ">");
      index += 1;
      continue;
    }
    if (/^>\s?/.test(line)) {
      flushParagraph();
      const quote = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(noteInlineMarkdownToHtml(lines[index].replace(/^>\s?/, "")));
        index += 1;
      }
      output.push("<blockquote>" + quote.join("<br />") + "</blockquote>");
      continue;
    }
    const listMatch = line.match(/^\s*([-*+])\s+(.+)$/) || line.match(/^\s*(\d+)[.、)]\s+(.+)$/);
    if (listMatch) {
      flushParagraph();
      const ordered = /^\s*\d+[.、)]\s+/.test(line);
      const tag = ordered ? "ol" : "ul";
      const items = [];
      while (index < lines.length) {
        const match = ordered
          ? lines[index].match(/^\s*\d+[.、)]\s+(.+)$/)
          : lines[index].match(/^\s*[-*+]\s+(.+)$/);
        if (!match) break;
        items.push("<li>" + noteInlineMarkdownToHtml(match[1]) + "</li>");
        index += 1;
      }
      output.push("<" + tag + ">" + items.join("") + "</" + tag + ">");
      continue;
    }
    paragraph.push(line);
    index += 1;
  }
  flushParagraph();
  return output.join("");
}

function noteHtmlToMarkdown(html) {
  const holder = document.createElement("div");
  holder.innerHTML = html || "";
  const inline = (node) => {
    if (node.nodeType === Node.TEXT_NODE) return node.nodeValue || "";
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const tag = node.tagName.toLowerCase();
    if (tag === "br") return "\n";
    if (tag === "img") {
      const src = safeNoteUrl(node.getAttribute("src"));
      return src ? "![" + (node.getAttribute("alt") || "图片") + "](" + src + ")" : "";
    }
    const content = Array.from(node.childNodes).map(inline).join("");
    if (tag === "strong" || tag === "b") return "**" + content + "**";
    if (tag === "em" || tag === "i") return "*" + content + "*";
    if (tag === "u") return "__" + content + "__";
    if (tag === "code") return "\x60" + content + "\x60";
    if (tag === "a") {
      const href = safeNoteUrl(node.getAttribute("href"));
      return href ? "[" + content + "](" + href + ")" : content;
    }
    return content;
  };
  const blocks = (parent) => Array.from(parent.childNodes).map((node) => {
    if (node.nodeType === Node.TEXT_NODE) return (node.nodeValue || "").trim() ? (node.nodeValue || "") + "\n\n" : "";
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const tag = node.tagName.toLowerCase();
    if (/^h[1-6]$/.test(tag)) return "#".repeat(Math.min(4, Number(tag.slice(1)))) + " " + inline(node) + "\n\n";
    if (tag === "blockquote") return inline(node).split("\n").map((line) => "> " + line).join("\n") + "\n\n";
    if (tag === "ul" || tag === "ol") {
      return Array.from(node.children).map((item, itemIndex) => (tag === "ol" ? String(itemIndex + 1) + ". " : "- ") + inline(item).trim()).join("\n") + "\n\n";
    }
    return inline(node).trim() + "\n\n";
  }).join("");
  return blocks(holder).replace(/\n{3,}/g, "\n\n").trim();
}

function safeNoteUrl(value) {
  const url = String(value || "").trim();
  return /^(?:https?:\/\/|\/(?!\/)|#|data:image\/)/i.test(url) && !/^javascript:/i.test(url) ? url : "";
}

function noteInlineMarkdownToHtml(value) {
  let html = escapeHtml(value);
  html = html.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g, (_match, alt, url, title) => {
    const safe = safeNoteUrl(url);
    return safe ? "<img src=\"" + escapeAttr(safe) + "\" alt=\"" + escapeAttr(alt) + "\"" + (title ? " title=\"" + escapeAttr(title) + "\"" : "") + " />" : _match;
  });
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, label, url) => {
    const safe = safeNoteUrl(url);
    return safe ? "<a href=\"" + escapeAttr(safe) + "\" target=\"_blank\" rel=\"noreferrer\">" + label + "</a>" : _match;
  });
  html = html.replace(/\x60([^\x60]+)\x60/g, "<code>$1</code>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+?)__/g, "<u>$1</u>");
  html = html.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");
  return html;
}

function renderNoteRichPreview() {
  const preview = $("note-rich-preview-body");
  const editor = $("note-rich-editor");
  if (!preview || !editor) return;
  const holder = document.createElement("div");
  holder.innerHTML = editor.innerHTML || "";
  $$("script, style, iframe, object, embed, form", holder).forEach((element) => element.remove());
  $$("*", holder).forEach((element) => {
    [...element.attributes].forEach((attribute) => {
      const name = attribute.name.toLowerCase();
      if (name.startsWith("on") || !["href", "src", "alt", "title"].includes(name)) element.removeAttribute(attribute.name);
    });
    if (element.hasAttribute("href")) {
      const safe = safeNoteUrl(element.getAttribute("href"));
      if (safe) element.setAttribute("href", safe);
      else element.removeAttribute("href");
    }
    if (element.hasAttribute("src")) {
      const safe = safeNoteUrl(element.getAttribute("src"));
      if (safe) element.setAttribute("src", safe);
      else element.removeAttribute("src");
    }
  });
  const walker = document.createTreeWalker(holder, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  let current;
  while ((current = walker.nextNode())) {
    const parent = current.parentElement;
    if (parent && !["CODE", "PRE", "SCRIPT", "STYLE"].includes(parent.tagName)) textNodes.push(current);
  }
  textNodes.forEach((node) => {
    const rendered = renderInlineFormulaText(node.nodeValue || "");
    const fragment = document.createRange().createContextualFragment(rendered);
    node.replaceWith(fragment);
  });
  preview.innerHTML = holder.innerHTML || '<p class="muted-copy">输入内容后，这里会显示预览。</p>';
}

function updateNoteEditorStats() {
  updateEditorCount($("note-rich-editor")?.parentElement, $("note-rich-editor")?.innerText || "");
  updateEditorCount($("note-markdown-editor")?.parentElement, $("note-markdown-editor")?.value || "");
}

function renderNoteMarkdownPreview() {
  const preview = $("note-markdown-preview-body");
  const source = $("note-markdown-editor")?.value || "";
  if (!preview) return;
  preview.innerHTML = source.trim()
    ? renderMarkdown(source)
    : '<p class="muted-copy">输入 Markdown 后，这里会显示排版结果。</p>';
}

function setNoteMode(mode) {
  const nextMode = mode === "markdown" ? "markdown" : "rich";
  if (nextMode === state.noteEditorMode) return;
  const rich = $("note-rich-editor");
  const markdown = $("note-markdown-editor");
  if (nextMode === "markdown" && rich && markdown) {
    markdown.value = noteHtmlToMarkdown(rich.innerHTML);
    resetTextEditorHistory(markdown);
  }
  if (nextMode === "rich" && rich && markdown) rich.innerHTML = noteMarkdownToHtml(markdown.value);
  state.noteEditorMode = nextMode;
  $("note-rich-pane").hidden = nextMode !== "rich";
  $("note-markdown-pane").hidden = nextMode !== "markdown";
  $$('[data-note-mode]').forEach((button) => { const active = button.dataset.noteMode === nextMode; button.classList.toggle("is-active", active); button.setAttribute("aria-selected", String(active)); });
  renderNoteMarkdownPreview();
  renderNoteRichPreview();
  updateNoteEditorStats();
}

function saveNoteSelection() {
  const editor = $("note-rich-editor");
  const selection = window.getSelection();
  if (!editor || !selection?.rangeCount || !editor.contains(selection.anchorNode)) return;
  state.noteSavedRange = selection.getRangeAt(0).cloneRange();
}

function restoreNoteSelection() {
  if (!state.noteSavedRange) return;
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(state.noteSavedRange);
}

function markNoteDirty() {
  rememberTextEditorChange($("note-markdown-editor"));
  $("note-save-state").textContent = "有未保存修改";
  renderNoteRichPreview();
  renderNoteMarkdownPreview();
  updateNoteEditorStats();
}

function insertNoteText(value) {
  const editor = $("note-rich-editor");
  if (!editor) return;
  editor.focus();
  restoreNoteSelection();
  document.execCommand("insertText", false, value);
  state.noteSavedRange = null;
  markNoteDirty();
}

function runNoteCommand(command, value = null) {
  const editor = $("note-rich-editor");
  if (!editor) return;
  editor.focus();
  const selection = window.getSelection();
  if (!selection?.rangeCount || !editor.contains(selection.anchorNode)) restoreNoteSelection();
  if (command === "createLink") {
    const input = window.prompt("输入链接地址", "https://");
    if (!input) return;
    const normalized = /^https?:\/\//i.test(input.trim()) ? input.trim() : "https://" + input.trim();
    const safe = safeNoteUrl(normalized);
    if (!safe) {
      showToast("链接地址不可用。", true);
      return;
    }
    document.execCommand("createLink", false, safe);
  } else {
    document.execCommand(command, false, value);
  }
  saveNoteSelection();
  markNoteDirty();
}

function handleNoteRichKeydown(event) {
  const editor = $("note-rich-editor");
  if (!editor || event.isComposing) return;
  const modifier = event.ctrlKey || event.metaKey;
  if (modifier && !event.altKey) {
    const key = event.key.toLowerCase();
    const command = { b: "bold", i: "italic", u: "underline", k: "createLink" }[key];
    if (command) {
      event.preventDefault();
      runNoteCommand(command);
      return;
    }
  }
  if (event.key === "Tab" && !modifier && !event.altKey) {
    event.preventDefault();
    runNoteCommand(event.shiftKey ? "outdent" : "indent");
  }
}

function renderNoteEditor() {
  const note = state.currentNote;
  const empty = $("workbench-note-empty");
  const editor = $("workbench-note-editor");
  if (!note) {
    empty.hidden = false;
    editor.hidden = true;
    $("note-save-state").textContent = "未选择笔记";
    return;
  }
  empty.hidden = true;
  editor.hidden = false;
  $("note-title").value = note.title || "";
  $("note-tags").value = (note.tags || []).join("，");
  populateNoteConcepts(note.concept_id || state.workbenchConceptId);
  $("note-rich-editor").innerHTML = note.content_html || noteMarkdownToHtml(note.content_markdown || "");
  $("note-markdown-editor").value = note.content_markdown || noteHtmlToMarkdown(note.content_html || "");
  resetTextEditorHistory($("note-markdown-editor"));
  renderNoteMarkdownPreview();
  renderNoteRichPreview();
  updateNoteEditorStats();
  $("note-favorite").textContent = note.favorite ? "已收藏" : "收藏";
  $("note-favorite").setAttribute("aria-pressed", String(Boolean(note.favorite)));
  $("note-version-label").textContent = note.id ? `版本记录 · ${String(note.updated_at || "").slice(0, 10)}` : "新笔记";
  $("note-save-state").textContent = note.id ? "已保存到本机" : "尚未保存";
  state.noteEditorMode = "rich";
  setNoteMode("rich");
  if (note.id) loadNoteVersions(note.id);
  else $("note-history-list").innerHTML = `<span class="note-history-empty">保存后可以回溯旧版本</span>`;
  renderWorkbenchNotes();
}

function newWorkbenchNote() {
  state.currentNote = { id: "", title: "", concept_id: state.workbenchConceptId, tags: [], content_html: "", content_markdown: "", favorite: false };
  renderNoteEditor();
  $("note-title")?.focus();
}

async function openWorkbenchNote(noteId) {
  try {
    const payload = await fetchJSON(`/api/workbench/notes/${encodeURIComponent(noteId)}?user_id=${encodeURIComponent(state.userId)}`);
    state.currentNote = payload.note;
    renderNoteEditor();
  } catch (error) {
    showToast(`笔记读取失败：${error.message}`, true);
  }
}

function collectNotePayload() {
  const rich = $("note-rich-editor");
  const markdown = $("note-markdown-editor");
  const contentHtml = state.noteEditorMode === "markdown" ? noteMarkdownToHtml(markdown.value) : rich.innerHTML;
  const contentMarkdown = state.noteEditorMode === "markdown" ? markdown.value : (markdown.value.trim() || noteHtmlToMarkdown(rich.innerHTML));
  const tags = $("note-tags").value.split(/[，,]/).map((item) => item.trim()).filter(Boolean);
  return {
    user_id: state.userId,
    title: $("note-title").value.trim() || "未命名笔记",
    concept_id: $("note-concept").value,
    tags,
    content_html: contentHtml,
    content_markdown: contentMarkdown,
    favorite: $("note-favorite").getAttribute("aria-pressed") === "true",
  };
}

async function saveWorkbenchNote() {
  if (!state.currentNote) newWorkbenchNote();
  const button = $("note-save");
  button.disabled = true;
  $("note-save-state").textContent = "正在保存……";
  try {
    const payload = collectNotePayload();
    const response = state.currentNote?.id ? await fetchJSON(`/api/workbench/notes/${encodeURIComponent(state.currentNote.id)}`, { ...jsonOptions(payload), method: "PUT" }) : await fetchJSON("/api/workbench/notes", jsonOptions(payload));
    state.currentNote = response.note;
    renderNoteEditor();
    await loadWorkbenchNotes();
    showToast("笔记已保存到本机。", false);
  } catch (error) {
    $("note-save-state").textContent = `保存失败：${error.message}`;
    showToast(`笔记保存失败：${error.message}`, true);
  } finally {
    button.disabled = false;
  }
}

async function deleteWorkbenchNote() {
  if (!state.currentNote?.id) { state.currentNote = null; renderNoteEditor(); return; }
  if (!window.confirm("确定删除这条笔记吗？删除后无法从版本记录恢复。")) return;
  try {
    await fetchJSON(`/api/workbench/notes/${encodeURIComponent(state.currentNote.id)}?user_id=${encodeURIComponent(state.userId)}`, { method: "DELETE" });
    state.currentNote = null;
    await loadWorkbenchNotes();
    renderNoteEditor();
    showToast("笔记已删除。", false);
  } catch (error) {
    showToast(`笔记删除失败：${error.message}`, true);
  }
}

async function loadNoteVersions(noteId) {
  try {
    const payload = await fetchJSON(`/api/workbench/notes/${encodeURIComponent(noteId)}/versions?user_id=${encodeURIComponent(state.userId)}`);
    const root = $("note-history-list");
    const items = payload.items || [];
    root.innerHTML = items.length ? items.slice(0, 8).map((item, index) => `<button type="button" class="note-history-item" data-note-restore="${item.id}"><span>${index === 0 ? "当前保存前" : "历史版本"}</span><small>${escapeHtml(String(item.created_at || "").replace("T", " ").slice(0, 16))}</small></button>`).join("") : `<span class="note-history-empty">还没有历史版本</span>`;
    $$('[data-note-restore]', root).forEach((button) => button.addEventListener("click", () => restoreWorkbenchNote(button.dataset.noteRestore)));
  } catch {
    $("note-history-list").innerHTML = `<span class="note-history-empty">版本记录暂时不可用</span>`;
  }
}

async function restoreWorkbenchNote(versionId) {
  if (!state.currentNote?.id || !window.confirm("恢复后当前内容会作为一个新版本保存，继续吗？")) return;
  try {
    const payload = await fetchJSON(`/api/workbench/notes/${encodeURIComponent(state.currentNote.id)}/restore/${encodeURIComponent(versionId)}?user_id=${encodeURIComponent(state.userId)}`, { method: "POST" });
    state.currentNote = payload.note;
    renderNoteEditor();
    await loadWorkbenchNotes();
    showToast("已恢复历史版本。", false);
  } catch (error) {
    showToast(`恢复失败：${error.message}`, true);
  }
}

function toggleNoteFavorite() {
  if (!state.currentNote) return;
  const button = $("note-favorite");
  const active = button.getAttribute("aria-pressed") === "true";
  button.setAttribute("aria-pressed", String(!active));
  button.textContent = active ? "收藏" : "已收藏";
  $("note-save-state").textContent = "有未保存修改";
}

async function exportWorkbenchData() {
  try {
    const payload = await fetchJSON(`/api/workbench/export?user_id=${encodeURIComponent(state.userId)}`);
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `ai-math-workbench-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    showToast("工作台数据已导出。", false);
  } catch (error) {
    showToast(`导出失败：${error.message}`, true);
  }
}

async function importWorkbenchData(file) {
  if (!file) return;
  try {
    const payload = JSON.parse(await file.text());
    const result = await fetchJSON("/api/workbench/import", jsonOptions({ user_id: state.userId, notes: payload.notes || [], template_overrides: payload.template_overrides || [] }));
    await loadWorkbenchNotes();
    await loadWorkbenchTemplate();
    showToast(`导入完成：${result.imported_notes} 条笔记，${result.imported_templates} 个模板。`, false);
  } catch (error) {
    showToast(`导入失败：${error.message}`, true);
  } finally {
    $("workbench-import-input").value = "";
  }
}

function applyWorkbenchTheme() {
  applyAccountTheme(state.user?.preferences?.theme || "system");
  const button = $("workbench-theme-toggle");
  if (button) button.textContent = document.body.classList.contains("theme-dark") ? "切换亮色" : "切换暗色";
}

function applyAccountTheme(theme = "system") {
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const dark = theme === "dark" || (theme === "system" && prefersDark);
  document.body.classList.toggle("theme-dark", dark);
}

function bindWorkbenchControls() {
  const search = $("workbench-subtype-search");
  search?.addEventListener("input", () => {
    state.workbenchSubtypeQuery = search.value;
    renderWorkbenchSubtypeTabs();
  });
  $("workbench-type-tabs")?.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const tabs = $$('[data-workbench-subtype]', $("workbench-type-tabs"));
    if (!tabs.length) return;
    event.preventDefault();
    const current = Math.max(0, tabs.indexOf(document.activeElement));
    const nextIndex = event.key === "Home" ? 0
      : event.key === "End" ? tabs.length - 1
        : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[nextIndex].focus();
    tabs[nextIndex].click();
  });
}

async function loadWorkbench() {
  applyWorkbenchTheme();
  try {
    if (!state.workbenchCatalog.length) {
      const payload = await fetchJSON(`/api/workbench?user_id=${encodeURIComponent(state.userId)}`);
      state.workbenchCatalog = payload.concepts || [];
    }
    if (!state.workbenchCatalog.some((item) => item.id === state.workbenchConceptId)) {
      state.workbenchConceptId = state.workbenchCatalog[0]?.id || "";
    }
    const activeConcept = workbenchConcept(state.workbenchConceptId);
    if (!activeConcept?.subtypes?.some((item) => item.id === state.workbenchSubtypeId)) {
      state.workbenchSubtypeId = activeConcept?.subtypes?.[0]?.id || "";
    }
    renderWorkbenchConcepts();
    renderWorkbenchSubtypeTabs();
    await Promise.all([loadWorkbenchTemplate(), loadWorkbenchNotes(), (async () => {
      try {
        state.workbenchAnalytics = await fetchJSON(`/api/analytics?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二`);
      } catch {
        state.workbenchAnalytics = state.analytics || null;
      }
      renderWorkbenchProgress();
    })()]);
  } catch (error) {
    $("workbench-template-card").innerHTML = `<div class="loading-card">工作台读取失败：${escapeHtml(error.message)}</div>`;
    showNotice(`无法读取学习工作台：${error.message}`);
  }
}

async function uploadWorkbenchNoteImage(file) {
  const error = validateImageFile(file);
  if (error) throw new Error(error);
  const formData = new FormData();
  formData.append("file", file);
  formData.append("user_id", state.userId);
  return fetchJSON("/api/workbench/notes/assets", { method: "POST", body: formData });
}

function bindNoteEditor() {
  const richFormulaToolbar = $("note-rich-formula-toolbar");
  const markdownFormulaToolbar = $("note-markdown-formula-toolbar");
  const sharedFormulaEditor = (editorId) => `<div class="formula-editor note-formula-editor" data-formula-editor="${escapeAttr(editorId)}">${formulaToolbarMarkup(editorId, false, "fill", false)}</div>`;
  if (richFormulaToolbar) richFormulaToolbar.innerHTML = sharedFormulaEditor("note-rich");
  if (markdownFormulaToolbar) markdownFormulaToolbar.innerHTML = sharedFormulaEditor("note-markdown");
  bindAnswerEditors(richFormulaToolbar || document);
  bindAnswerEditors(markdownFormulaToolbar || document);
  ensureTextEditorHistory($("note-markdown-editor"));
  $$('[data-note-mode]').forEach((button) => button.addEventListener("click", () => setNoteMode(button.dataset.noteMode)));
  $$('[data-note-command]').forEach((button) => button.addEventListener("mousedown", (event) => event.preventDefault()));
  $$('[data-note-command]').forEach((button) => button.addEventListener("click", () => runNoteCommand(button.dataset.noteCommand, button.dataset.noteValue || null)));
  $$('[data-note-insert]').forEach((button) => button.addEventListener("click", () => insertNoteText(button.dataset.noteInsert === "subquestion" ? "（1） " : "1. ")));
  $("note-rich-editor")?.addEventListener("keydown", handleNoteRichKeydown);
  $("note-rich-editor")?.addEventListener("keyup", saveNoteSelection);
  $("note-rich-editor")?.addEventListener("mouseup", saveNoteSelection);
  $("note-rich-editor")?.addEventListener("input", markNoteDirty);
  $("note-markdown-editor")?.addEventListener("keydown", (event) => handleStructuredTextKeydown($("note-markdown-editor"), event));
  $$('[data-markdown-insert]').forEach((button) => button.addEventListener("click", () => {
    const textarea = $("note-markdown-editor");
    const value = button.dataset.markdownInsert || "";
    const start = textarea.selectionStart || 0;
    textarea.value = `${textarea.value.slice(0, start)}${value}${textarea.value.slice(textarea.selectionEnd || start)}`;
    textarea.focus();
    textarea.selectionStart = textarea.selectionEnd = start + value.length;
    markNoteDirty();
  }));
  $("note-markdown-editor")?.addEventListener("input", markNoteDirty);
  $("note-image-button")?.addEventListener("click", () => { saveNoteSelection(); $("note-image-input").click(); });
  $("note-image-input")?.addEventListener("change", async () => {
    const input = $("note-image-input");
    const file = input.files?.[0];
    if (!file) return;
    try {
      $("note-save-state").textContent = "图片上传中……";
      const uploaded = await uploadWorkbenchNoteImage(file);
      const editor = $("note-rich-editor");
      editor.focus();
      restoreNoteSelection();
      document.execCommand("insertHTML", false, `<img src="${escapeAttr(uploaded.url)}" alt="${escapeAttr(uploaded.filename || "笔记图片")}" />`);
      markNoteDirty();
    } catch (error) {
      showToast(`图片插入失败：${error.message}`, true);
    } finally {
      input.value = "";
    }
  });
  $("note-save")?.addEventListener("click", saveWorkbenchNote);
  $("note-delete")?.addEventListener("click", deleteWorkbenchNote);
  $("note-favorite")?.addEventListener("click", toggleNoteFavorite);
  $("new-note-button")?.addEventListener("click", newWorkbenchNote);
  $("empty-new-note")?.addEventListener("click", newWorkbenchNote);
  $("note-search")?.addEventListener("input", () => {
    clearTimeout(state.noteSearchTimer);
    state.noteSearchTimer = setTimeout(loadWorkbenchNotes, 250);
  });
  $("note-favorite-filter")?.addEventListener("click", () => {
    state.noteFavoriteOnly = !state.noteFavoriteOnly;
    $("note-favorite-filter").classList.toggle("is-active", state.noteFavoriteOnly);
    $("note-favorite-filter").setAttribute("aria-pressed", String(state.noteFavoriteOnly));
    loadWorkbenchNotes();
  });
  $("workbench-theme-toggle")?.addEventListener("click", () => {
    const next = document.body.classList.contains("theme-dark") ? "light" : "dark";
    applyAccountTheme(next);
    const current = state.accountSettings?.preferences || {};
    fetchJSON("/api/settings/preferences", { ...jsonOptions({ ...current, theme: next }), method: "PATCH" })
      .then((payload) => { state.accountSettings = { ...(state.accountSettings || {}), preferences: payload.preferences }; state.user = { ...state.user, preferences: payload.preferences }; applyWorkbenchTheme(); })
      .catch((error) => showToast(`主题保存失败：${error.message}`, true));
  });
  $("workbench-export")?.addEventListener("click", exportWorkbenchData);
  $("workbench-import")?.addEventListener("click", () => $("workbench-import-input")?.click());
  $("workbench-import-input")?.addEventListener("change", () => importWorkbenchData($("workbench-import-input").files?.[0]));
  $("workbench-refresh-progress")?.addEventListener("click", async () => {
    const button = $("workbench-refresh-progress");
    if (button) button.disabled = true;
    try {
      state.workbenchAnalytics = await fetchJSON(`/api/analytics?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二`);
      renderWorkbenchProgress();
      showToast("工作台进度已刷新。", false);
    } catch (error) {
      showToast(`进度刷新失败：${error.message}`, true);
    } finally {
      if (button) button.disabled = false;
    }
  });
}

function analyticsPercent(value, fallback = "—") {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? fallback : `${formatScore(value)}%`;
}

function analyticsDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds)) || Number(seconds) <= 0) return "—";
  const value = Number(seconds);
  return value < 60 ? `${formatScore(value)} 秒` : `${formatScore(value / 60)} 分钟`;
}

function analyticsSignedPercent(value, fallback = "—") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback;
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${formatScore(numeric)}%`;
}

function analyticsDate(value, fallback = "暂无") {
  return value ? String(value).slice(0, 10) : fallback;
}

function analyticsStatusClass(status) {
  return {
    correct: "steady",
    incorrect: "needs-work",
    partial: "building",
    manual: "untrained",
    "需加强": "needs-work",
    "待训练": "untrained",
    "巩固中": "building",
    "稳定": "steady",
    "继续巩固": "building",
  }[status] || "neutral";
}

function renderAnalyticsRankRow(row, index) {
  const mastery = Math.max(0, Math.min(100, Number(row.mastery) || 0));
  const attempted = Number(row.attempted_question_count || 0);
  const total = Number(row.question_count || 0);
  return `<div class="analytics-rank-row">
    <span class="analytics-rank-index">${String(index + 1).padStart(2, "0")}</span>
    <div class="analytics-rank-main">
      <div class="analytics-rank-title"><strong>${escapeHtml(row.name || "未分类")}</strong><span class="analysis-status ${analyticsStatusClass(row.status)}">${escapeHtml(row.status || "待观察")}</span></div>
      <div class="analytics-rank-meta"><span>${escapeHtml(row.subject || row.scope_label || "知识块")}</span><span>${attempted} / ${total} 题已覆盖</span><span>正确率 ${analyticsPercent(row.accuracy)}</span><span>近期 ${analyticsPercent(row.recent_accuracy)}</span></div>
      <div class="analytics-bar"><span style="--progress:${(mastery / 100).toFixed(3)}"></span></div>
    </div>
    <strong class="analytics-rank-value">${formatScore(row.mastery)}%</strong>
  </div>`;
}

function renderAnalytics() {
  const data = state.analytics || {};
  const overview = data.overview || {};
  const profile = data.profile || {};
  const recommendations = data.recommendations || [];
  const setText = (id, value) => { if ($(id)) $(id).textContent = value; };
  setText("analytics-attempts", String(overview.attempts ?? data.attempts ?? 0));
  setText("analytics-coverage", analyticsPercent(overview.coverage_rate, "0%"));
  setText("analytics-coverage-note", `${overview.unique_questions || 0} / ${data.questions_available || 0} 道题`);
  setText("analytics-accuracy", analyticsPercent(overview.accuracy));
  setText("analytics-mastery", analyticsPercent(overview.mastery, "0%"));
  setText("analytics-score-rate", analyticsPercent(overview.score_rate));
  setText("analytics-avg-time", analyticsDuration(overview.avg_seconds));
  setText("analytics-recent-accuracy", analyticsPercent(profile.recent_accuracy));
  setText("analytics-active-days", `${profile.active_days_7d || 0} 天`);
  setText("analytics-active-days-note", `${profile.attempts_7d || 0} 次作答`);
  setText("analytics-repeat-gain", analyticsSignedPercent(profile.repeat_gain));
  setText("analytics-hint-rate", analyticsPercent(profile.hint_rate));
  setText("analytics-slow-rate", analyticsPercent(profile.slow_rate));
  setText("analytics-manual-rate", analyticsPercent(profile.manual_rate));

  const recommendationMarkup = recommendations.length
    ? recommendations.slice(0, 3).map((item, index) => `<span class="analytics-recommendation"><b>${String(index + 1).padStart(2, "0")}</b>${escapeHtml(item)}</span>`).join("")
    : `<span class="analytics-recommendation">完成真实作答后，这里会给出基于证据的下一步建议。</span>`;
  $("analytics-recommendations").innerHTML = `<span class="eyebrow">NEXT MOVES</span>${recommendationMarkup}`;

  const profileItems = [
    ["最近状态", `${analyticsPercent(profile.recent_accuracy)} 正确 · ${analyticsPercent(profile.recent_score_rate)} 得分`, `最近 ${profile.recent_attempts || 0} 题`],
    ["近 30 天", `${profile.active_days_30d || 0} 天活跃`, `${profile.attempts_30d || 0} 次作答`],
    ["首次 / 复做", `${analyticsPercent(profile.first_pass_score_rate)} → ${analyticsPercent(profile.repeat_score_rate)}`, `${profile.repeat_questions || 0} 道题有复做`],
    ["平均提示", `${formatScore(profile.avg_hints || 0)} 次`, `提示依赖率 ${analyticsPercent(profile.hint_rate)}`],
    ["有效计时", `${profile.timed_attempts || 0} 次`, `超时比例 ${analyticsPercent(profile.slow_rate)}`],
    ["数据可信度", profile.data_confidence || "暂无", `最后作答 ${analyticsDate(profile.last_attempt_at)}`],
  ];
  $("analytics-profile").innerHTML = profileItems.map(([label, value, note]) => `<div class="analytics-profile-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></div>`).join("");

  const yearRows = data.recent_year_breakdown || [];
  $("analytics-years").innerHTML = yearRows.length
    ? yearRows.map((row) => `<div class="analytics-year-row"><div><strong>${escapeHtml(row.year)} 年</strong><small>平均难度 ${formatScore(row.average_difficulty)}</small></div><span>${row.attempted_question_count || 0} / ${row.question_count || 0} 题</span><span>得分率 ${analyticsPercent(row.score_rate)}</span><em>${Object.entries(row.difficulty_distribution || {}).map(([level, count]) => `难${level}·${count}`).join(" / ")}</em></div>`).join("")
    : `<div class="analytics-empty">题库暂时没有最近三年的完整试卷。</div>`;

  const difficultyRows = data.difficulty_breakdown || [];
  $("analytics-difficulty").innerHTML = difficultyRows.length
    ? `<div class="analytics-difficulty-row analytics-difficulty-header"><span>难度</span><span>题库题数</span><span>覆盖</span><span>正确率</span><span>得分率</span><span>平均用时</span><span>提示</span></div>${difficultyRows.map((row) => `<div class="analytics-difficulty-row"><strong>${escapeHtml(row.label || `难度 ${row.difficulty}`)}</strong><span>${row.question_count || 0}</span><span>${row.attempted_question_count || 0} 题</span><span>${analyticsPercent(row.accuracy)}</span><span>${analyticsPercent(row.score_rate)}</span><span>${analyticsDuration(row.avg_seconds)}</span><span>${row.avg_hints == null ? "—" : `${formatScore(row.avg_hints)} 次`}</span></div>`).join("")}`
    : `<div class="analytics-empty">完成最近三年题目后，这里会显示不同难度的表现差异。</div>`;

  const weaknesses = data.weaknesses || [];
  const strengths = data.strengths || [];
  $("analytics-weaknesses").innerHTML = weaknesses.length
    ? weaknesses.map(renderAnalyticsRankRow).join("")
    : `<div class="analytics-empty">完成真实作答后，这里会显示掌握度低、正确率低或覆盖不足的知识块。</div>`;
  $("analytics-strengths").innerHTML = strengths.length
    ? strengths.map(renderAnalyticsRankRow).join("")
    : `<div class="analytics-empty">还没有足够的作答证据。系统不会把未训练的知识块误判为强项。</div>`;

  const questionTypeRows = data.question_types || [];
  $("analytics-type-breakdown").innerHTML = questionTypeRows.length
    ? questionTypeRows.map((row) => `<div class="analytics-type-row">
        <div class="analytics-type-title"><strong>${escapeHtml(typeLabel(row.question_type))}</strong><span class="analysis-status ${analyticsStatusClass(row.status)}">${escapeHtml(row.status || "待训练")}</span></div>
        <div class="analytics-type-stats"><span><b>${row.attempts || 0}</b> 次作答</span><span><b>${row.attempted_question_count || 0}</b> / ${row.question_count || 0} 题</span><span>正确率 <b>${analyticsPercent(row.accuracy)}</b></span><span>平均 ${analyticsDuration(row.avg_seconds)}</span></div>
        <div class="analytics-bar"><span style="--progress:${(Math.max(0, Math.min(100, Number(row.accuracy) || 0)) / 100).toFixed(3)}"></span></div>
      </div>`).join("")
    : `<div class="analytics-empty">题型数据读取中……</div>`;

  const subtypeRows = data.subtypes || [];
  $("analytics-subtypes").innerHTML = subtypeRows.length
    ? `<div class="analytics-subtype-row analytics-subtype-header"><span>具体考法</span><span>所属知识块</span><span>题库 / 已做</span><span>作答次数</span><span>正确次数</span><span>正确率</span></div>${subtypeRows.map((row) => `<div class="analytics-subtype-row"><span><strong>${escapeHtml(row.name || "未分类")}</strong>${renderLearningText(row.summary || "", "analytics-subtype-summary")}</span><span>${escapeHtml(conceptName(row.concept_id) || "数学二")}</span><span>${row.question_count || 0} / ${row.attempted_question_count || 0}</span><span>${row.attempts || 0}</span><span>${row.correct || 0}</span><span>${analyticsPercent(row.accuracy)}</span></div>`).join("")}`
    : `<div class="analytics-empty">完成具体题型训练后，这里会显示每个考法的作答次数和正确次数。</div>`;

  const concepts = data.concepts || [];
  $("analytics-concepts").innerHTML = concepts.length
    ? `<div class="analytics-concepts-row analytics-concepts-header"><span>知识块</span><span>掌握度</span><span>题库覆盖</span><span>正确率</span><span>得分率</span><span>平均用时</span></div>${concepts.map((row) => `<div class="analytics-concepts-row"><span class="analytics-concept-name"><strong>${escapeHtml(row.name || "未分类")}</strong><small>${escapeHtml(row.subject || row.scope_label || "")}${row.scope === "out-of-syllabus" ? " · 原题保留" : ""}</small></span><strong>${formatScore(row.mastery)}%</strong><span>${row.attempted_question_count || 0} / ${row.question_count || 0}</span><span>${analyticsPercent(row.accuracy)}</span><span>${analyticsPercent(row.score_rate)}</span><span>${analyticsDuration(row.avg_seconds)}</span></div>`).join("")}`
    : `<div class="analytics-empty">题库知识块读取中……</div>`;

  const errors = data.error_types || [];
  $("analytics-errors").innerHTML = errors.length
    ? errors.slice(0, 8).map((row) => `<div class="analytics-error-row"><span class="analytics-error-name">${escapeHtml(row.name)}</span><span class="analytics-error-bar"><i style="--progress:${(Math.max(0, Math.min(100, Number(row.share) || 0)) / 100).toFixed(3)}"></i></span><strong>${row.count} 次</strong><small>${analyticsPercent(row.share)}</small></div>`).join("")
    : `<div class="analytics-empty">暂无错因记录。选择题、填空题判错或解答题自评后，这里会逐步形成分布。</div>`;

  const trend = data.daily_trend || [];
  const maxDailyAttempts = Math.max(1, ...trend.map((row) => Number(row.attempts) || 0));
  $("analytics-trend").innerHTML = trend.length
    ? trend.map((row) => `<div class="analytics-trend-row"><span class="analytics-trend-date">${escapeHtml(String(row.date).slice(5))}</span><span class="analytics-trend-bar"><i style="--progress:${((Number(row.attempts) || 0) / maxDailyAttempts).toFixed(3)}"></i></span><span>${row.attempts} 次</span><span>正确率 ${analyticsPercent(row.accuracy)}</span></div>`).join("")
    : `<div class="analytics-empty">完成作答并提交后，这里会按日期显示训练频率和正确率趋势。</div>`;

  const recent = data.recent_attempts || [];
  $("analytics-recent").innerHTML = recent.length
    ? recent.map((row) => `<button type="button" class="analytics-recent-row" data-analytics-question="${escapeAttr(row.question_id)}"><span class="analytics-recent-ref">${escapeHtml(row.year || "—")} / Q${escapeHtml(row.number || "—")}</span><span class="analytics-recent-type">${escapeHtml(typeLabel(row.question_type))}</span><span class="analysis-status ${analyticsStatusClass(row.status)}">${escapeHtml(row.status_label)}</span><strong>${formatScore(row.score)} / ${formatScore(row.max_score)}</strong></button>`).join("")
    : `<div class="analytics-empty">暂无最近作答记录。</div>`;
  $$('[data-analytics-question]', $("analytics-recent")).forEach((button) => button.addEventListener("click", () => openQuestion(button.dataset.analyticsQuestion)));
}

async function loadAnalytics() {
  try {
    state.analytics = await fetchJSON(`/api/analytics?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二`);
    renderAnalytics();
    showNotice("");
  } catch (error) {
    $("analytics-recommendations").textContent = `无法读取学习分析：${error.message}`;
  }
}

function renderBlockPreview(block) {
  const concept = block.concept || {};
  const value = Math.max(2, Math.min(98, Number(concept.mastery ?? 22)));
  return `<article class="block-card" data-block-concept="${escapeAttr(concept.id || "")}">
    <span class="eyebrow">${escapeHtml(concept.subject || "知识块")}</span>
    <h3>${escapeHtml(concept.name || "未分类")}</h3>
    <p>${escapeHtml(block.reason || "根据作答轨迹安排")}</p>
    <div class="progress-line"><span style="--progress:${(value / 100).toFixed(3)}"></span></div>
    <div class="block-bottom"><span>掌握度 ${formatScore(concept.mastery ?? 22)}%</span><span>${concept.attempts || 0} 次练习</span></div>
  </article>`;
}

function questionDifficultyMarkup(question) {
  const year = Number(question.year) || 0;
  const band = question.difficulty_band || (year >= 2020 && year <= 2026 ? "advanced" : year >= 1987 && year <= 2019 ? "basic" : "other");
  const label = question.difficulty_label || (band === "advanced" ? "提高题" : band === "basic" ? "基础题" : "待分层");
  return `<span class="difficulty-pill ${escapeAttr(band)}">${escapeHtml(label)}</span>`;
}

function questionAttemptMarkup(question, compact = false) {
  const summary = question?.attempt_summary || {};
  const attempts = Number(summary.attempts || 0);
  const correct = Number(summary.correct || 0);
  if (!attempts) {
    return compact
      ? `<span class="attempt-status attempt-status-unseen">未做</span>`
      : `<div class="question-attempt-summary attempt-summary-unseen"><span class="attempt-status attempt-status-unseen">未做</span><span>还没有作答记录</span></div>`;
  }
  const lastLabel = summary.last_status_label || "已记录";
  const content = `<span class="attempt-status attempt-status-done">已做</span><span>作答 ${attempts} 次</span><span>正确 ${correct} 次</span><span>最近：${escapeHtml(lastLabel)}</span>`;
  return compact
    ? `<span class="question-attempt-summary compact-attempt-summary">${content}</span>`
    : `<div class="question-attempt-summary">${content}</div>`;
}

function renderQuestionMini(question) {
  return `<article class="question-mini" data-question-id="${escapeAttr(question.id)}">
    <div class="question-mini-ref"><span>${escapeHtml(question.year)} / Q${escapeHtml(question.number)}</span><span class="question-mini-meta">${questionDifficultyMarkup(question)}<span>${formatScore(question.points)}分</span></span></div>
    <div class="question-mini-preview markdown-body">${renderQuestionPreview(question.question_markdown, 300) || `<p class="muted-copy">完整题目</p>`}</div>
    <p class="question-concepts">${questionConceptMarkup(question)}</p>
    <div class="question-mini-foot"><span class="type-pill ${question.question_type === "solution" ? "solution" : ""}">${typeLabel(question.question_type)}</span>${questionAttemptMarkup(question, true)}<span>打开作答 →</span></div>
  </article>`;
}

function bindQuestionOpeners(root) {
  $$(`[data-question-id]`, root).forEach((element) => element.addEventListener("click", () => openQuestion(element.dataset.questionId)));
}

async function loadBaseData() {
  const results = await Promise.all([
    fetchJSON("/api/stats"),
    fetchJSON(`/api/progress?user_id=${encodeURIComponent(state.userId)}`),
    fetchJSON(`/api/forecast?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二`),
    fetchJSON(`/api/analytics?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二`),
    fetchJSON(`/api/study/blocks?user_id=${encodeURIComponent(state.userId)}&limit=6`),
    fetchJSON(`/api/practice/next?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二&limit=8`),
    fetchJSON("/api/concepts"),
    fetchJSON("/api/exams"),
    fetchJSON(`/api/workbench?user_id=${encodeURIComponent(state.userId)}`),
    fetchJSON("/api/llm/settings"),
    fetchJSON("/api/server/settings"),
  ]);
  [state.stats, state.progress, state.forecast, state.analytics] = results.slice(0, 4);
  state.blocks = results[4].blocks || [];
  state.nextQuestions = results[5].items || [];
  state.concepts = results[6] || [];
  state.exams = results[7] || [];
  state.workbenchCatalog = results[8]?.concepts || [];
  state.settings = results[9] || {};
  state.serverSettings = results[10] || {};
  populateFilters();
  renderModelStatus();
  renderOverview();
  renderAnalytics();
  renderSettingsValues();
  renderServerSettingsValues();
}

async function loadOverview() {
  try {
    await loadBaseData();
    showNotice("");
  } catch (error) {
    showNotice(`无法读取本地服务：${error.message}。请确认已按 README 启动 FastAPI。`);
  }
}

function populateFilters() {
  const years = [...new Set(state.exams.filter((item) => item.exam_type === "数学二").map((item) => item.year))].sort((a, b) => b - a);
  const yearSelect = $("filter-year");
  const currentYear = yearSelect.value;
  yearSelect.innerHTML = `<option value="">全部年份</option>${years.map((year) => `<option value="${year}">${year}</option>`).join("")}`;
  if (years.map(String).includes(currentYear)) yearSelect.value = currentYear;
  const simulationYear = $("simulation-year");
  const simulationCurrent = simulationYear.value;
  simulationYear.innerHTML = years.map((year) => `<option value="${year}">${year} 年真题</option>`).join("");
  simulationYear.value = years.map(String).includes(simulationCurrent) ? simulationCurrent : String(years[0] || "");
  const conceptOptions = state.concepts.map((concept) => `<option value="${escapeAttr(concept.id)}">${escapeHtml(concept.name)}</option>`).join("");
  const conceptSelect = $("filter-concept");
  const currentConcept = conceptSelect.value;
  conceptSelect.innerHTML = `<option value="">全部知识块</option>${conceptOptions}`;
  conceptSelect.value = currentConcept;
  populateSubtypeFilter();
}

async function loadLibrary() {
  if (!state.concepts.length || !state.exams.length) {
    try { await loadBaseData(); } catch (error) { showNotice(error.message); return; }
  }
  const params = new URLSearchParams({ exam_type: $("filter-exam").value || "数学二", limit: "60" });
  if ($("filter-year").value) params.set("year", $("filter-year").value);
  if ($("filter-type").value) params.set("question_type", $("filter-type").value);
  if ($("filter-concept").value) params.set("concept_id", $("filter-concept").value);
  if ($("filter-subtype").value) params.set("subtype_id", $("filter-subtype").value);
  if ($("filter-scope").value) params.set("scope", $("filter-scope").value);
  params.set("user_id", state.userId);
  $("question-list").innerHTML = `<div class="loading-card">正在加载真题……</div>`;
  try {
    const payload = await fetchJSON(`/api/questions?${params}`);
    $("archive-count").textContent = `${payload.total} 道真题`;
    $("question-list").innerHTML = payload.items.length ? payload.items.map(renderQuestionRow).join("") : `<div class="loading-card">没有匹配的题目。</div>`;
    bindQuestionOpeners($("question-list"));
    bindClassificationControls($("question-list"));
    state.libraryLoaded = true;
  } catch (error) {
    $("question-list").innerHTML = `<div class="loading-card">读取失败：${escapeHtml(error.message)}</div>`;
  }
}

function bindClassificationControls(root = document) {
  $$('[data-classification-question]', root).forEach((control) => {
    if (control.dataset.classificationBound === "true") return;
    control.dataset.classificationBound = "true";
    const panel = control.querySelector("[data-correction-panel]");
    const open = control.querySelector("[data-open-correction]");
    const cancel = control.querySelector("[data-cancel-correction]");
    const concept = control.querySelector("[data-correction-concept]");
    const subtype = control.querySelector("[data-correction-subtype]");
    const status = control.querySelector("[data-classification-status]");
    open?.addEventListener("click", (event) => {
      event.stopPropagation();
      if (panel) panel.hidden = false;
      open?.setAttribute("aria-expanded", "true");
    });
    cancel?.addEventListener("click", (event) => {
      event.stopPropagation();
      if (panel) panel.hidden = true;
      open?.setAttribute("aria-expanded", "false");
    });
    [concept, subtype].forEach((element) => element?.addEventListener("click", (event) => event.stopPropagation()));
    concept?.addEventListener("change", (event) => {
      event.stopPropagation();
      populateCorrectionSubtype(subtype, concept.value);
    });
    status?.addEventListener("click", (event) => event.stopPropagation());
    control.querySelector("[data-correction-note]")?.addEventListener("click", (event) => event.stopPropagation());
    control.querySelector("[data-save-classification]")?.addEventListener("click", async (event) => {
      event.stopPropagation();
      const button = event.currentTarget;
      if (!concept?.value || !subtype?.value) {
        if (status) status.textContent = "请先选择知识块和具体题型。";
        return;
      }
      button.disabled = true;
      if (status) status.textContent = "正在保存分类……";
      try {
        const questionId = control.dataset.classificationQuestion;
        const payload = await fetchJSON(`/api/questions/${encodeURIComponent(questionId)}/classification`, {
          ...jsonOptions({ user_id: state.userId, concept_id: concept.value, subtype_id: subtype.value, note: control.querySelector("[data-correction-note]")?.value || "" }),
          method: "PUT",
        });
        showToast("分类已保存，后续筛选和训练会使用新分类。", false);
        if (control.closest("#question-list")) await loadLibrary();
        else if (control.closest("#modal-classification") && state.currentQuestion?.id === questionId) await openQuestion(questionId);
        else if (control.closest("#blocks-container")) {
          const practiceCard = control.closest("[data-practice-question]");
          const updatedQuestion = payload.question;
          if (practiceCard && state.practiceSession && updatedQuestion) {
            const sessionQuestion = state.practiceSession.questions?.find((item) => item.id === questionId);
            if (sessionQuestion) Object.assign(sessionQuestion, updatedQuestion);
            const tags = practiceCard.querySelector(".practice-question-tags");
            if (tags) tags.innerHTML = questionSubtypeMarkup(updatedQuestion);
            const subtypeLabel = practiceCard.querySelector("[data-practice-subtype-label]");
            if (subtypeLabel) subtypeLabel.textContent = practiceQuestionSubtypeLine(updatedQuestion);
            const replacementTemplate = document.createElement("template");
            replacementTemplate.innerHTML = classificationEditorMarkup(updatedQuestion, "practice");
            const replacement = replacementTemplate.content.firstElementChild;
            if (replacement) {
              control.replaceWith(replacement);
              bindClassificationControls(replacement.parentElement || replacement);
            }
          } else {
            await loadBlocks();
          }
        }
      } catch (error) {
        if (status) status.textContent = `保存失败：${error.message}`;
        button.disabled = false;
      }
    });
  });
}

function renderQuestionRow(question) {
  return `<article class="question-row" data-question-id="${escapeAttr(question.id)}">
    <div class="question-row-ref">${escapeHtml(question.year)} 年<br />第 ${escapeHtml(question.number)} 题</div>
    <div class="question-row-content"><div class="question-preview markdown-body">${renderQuestionPreview(question.question_markdown, 460) || `<p class="muted-copy">完整题目</p>`}</div><p class="question-concepts">${questionConceptMarkup(question)}${questionSubtypeMarkup(question)}</p>${questionAttemptMarkup(question)}${classificationEditorMarkup(question)}</div>
    <div class="question-row-meta"><span class="type-pill ${question.question_type === "solution" ? "solution" : ""}">${typeLabel(question.question_type)}</span><small>${formatScore(question.points)} 分</small></div>
  </article>`;
}

async function loadBlocks() {
  $("blocks-container").classList.remove("practice-active");
  $("blocks-container").innerHTML = `<div class="loading-card">正在分析作答记录……</div>`;
  try {
    const payload = await fetchJSON(`/api/study/blocks?user_id=${encodeURIComponent(state.userId)}&limit=12`);
    state.blocks = payload.blocks || [];
    $("blocks-container").innerHTML = state.blocks.length ? state.blocks.map(renderFullBlock).join("") : `<div class="empty-state"><div class="empty-mark">∑</div><h3>完成第一道题后开始分析</h3><p>系统会从真实作答中识别薄弱知识块，并生成短练习。</p></div>`;
    bindBlockStack($("blocks-container"));
    bindQuestionOpeners($("blocks-container"));
    bindPracticeStarters($("blocks-container"));
    bindClassificationControls($("blocks-container"));
  } catch (error) {
    $("blocks-container").innerHTML = `<div class="loading-card">读取失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderFullBlock(block, blockIndex = 0) {
  const concept = block.concept || {};
  const value = Math.max(2, Math.min(98, Number(concept.mastery ?? 22)));
  const subtypeCards = (block.subtypes || []).map((item) => {
    const available = Number(item.question_count || 0);
    const attempted = Number(item.attempted_question_count || 0);
    const correct = Number(item.correct || 0);
    const sizeLabel = available >= 15 ? "15 题" : `全部 ${available} 题`;
    const accuracy = item.accuracy == null ? "暂无正确率" : `${formatScore(item.accuracy)}% 正确`;
    const formats = Object.entries(item.question_format_counts || {}).filter(([, count]) => count).map(([format, count]) => `${typeLabel(format)} ${count}`).join(" · ");
    return `<article class="block-type-card block-subtype-card">
      <div class="block-type-head"><div><span class="eyebrow">具体考法</span><h4>${escapeHtml(item.name)}</h4></div><span class="block-type-count">${available}题库</span></div>
      <div class="block-subtype-summary">${renderLearningText(item.summary || "按这个具体考法集中训练")}</div>
      <p class="block-subtype-stats"><strong>${attempted} / ${available} 题已做</strong> · ${item.attempts || 0} 次作答 · ${correct} 次正确 · ${escapeHtml(item.status || "待训练")}<br />${escapeHtml(accuracy)} · ${escapeHtml(formats || "题型待标注")}</p>
      <button class="secondary-button block-start-button" data-start-practice data-concept-id="${escapeAttr(concept.id || "")}" data-question-type="" data-subtype-id="${escapeAttr(item.id)}">开始${escapeHtml(sizeLabel)}训练 →</button>
    </article>`;
  }).join("");
  const typeCards = (block.question_types || []).map((item) => {
    const available = Number(item.question_count || 0);
    const sizeLabel = available >= 15 ? "15 题" : `全部 ${available} 题`;
    const accuracy = item.accuracy == null ? "暂无正确率" : `${formatScore(item.accuracy)}% 正确`;
    return `<article class="block-type-card">
      <div class="block-type-head"><div><span class="eyebrow">${escapeHtml(typeLabel(item.question_type))}题</span><h4>${escapeHtml(sizeLabel)}训练</h4></div><span class="block-type-count">${available}题库</span></div>
      <p>${escapeHtml(accuracy)} · ${item.attempts || 0} 次作答 · ${escapeHtml(item.status || "待训练")}</p>
      <button class="secondary-button block-start-button" data-start-practice data-concept-id="${escapeAttr(concept.id || "")}" data-question-type="${escapeAttr(item.question_type)}">开始${escapeHtml(sizeLabel)}训练 →</button>
    </article>`;
  }).join("");
  const samples = (block.questions || []).slice(0, 3).map((question, index) => `<div class="block-question" data-question-id="${escapeAttr(question.id)}"><span class="block-question-number">0${index + 1}</span><div class="block-question-main"><div class="block-question-preview markdown-body">${renderQuestionPreview(question.question_markdown, 260)}</div><p class="question-concepts">${questionConceptMarkup(question)}${questionSubtypeMarkup(question)}</p>${questionAttemptMarkup(question, true)}${classificationEditorMarkup(question, "block")}</div><small>${questionDifficultyMarkup(question)} ${formatScore(question.points)}分 · ${question.year}</small></div>`).join("");
  return `<details class="full-block-card block-stack-card" data-block-stack style="--stack-index:${blockIndex}" ${blockIndex === 0 ? "open" : ""}>
    <summary class="block-stack-summary"><div class="full-block-head"><div><span class="eyebrow">${escapeHtml(concept.subject || "知识块")}</span><h3>${escapeHtml(concept.name || "未分类")}</h3><p>${concept.attempts || 0} 次作答 · ${concept.accuracy == null ? "暂无正确率" : `${formatScore(concept.accuracy)}% 正确`} · ${(block.subtypes || []).length} 类具体考法</p></div><div class="block-stack-metrics"><div class="mastery-number">${formatScore(concept.mastery ?? 22)}%</div><span data-block-stack-state>${blockIndex === 0 ? "收起" : "展开"}</span></div></div><div class="block-stack-reason">${renderLearningText(block.reason || "根据当前掌握度安排训练")}</div></summary>
    <div class="block-stack-content">
      <div class="block-stack-content-inner">
        <div class="block-stack-content-body">
          <div class="progress-line"><span style="--progress:${(value / 100).toFixed(3)}"></span></div>
          <div class="block-type-grid">${subtypeCards || typeCards || `<p class="muted-copy">该知识块暂时没有可用的细分题型。</p>`}</div>
          <div class="block-sample-head"><span class="eyebrow">题目预览</span><span>点击题目可直接作答</span></div>
          <div class="block-question-list">${samples || `<p class="muted-copy">暂无推荐题目。</p>`}</div>
        </div>
      </div>
    </div>
  </details>`;
}

function bindBlockStack(root) {
  const stacks = $$('[data-block-stack]', root);
  stacks.forEach((stack) => stack.addEventListener("toggle", () => {
    if (stack.open) {
      stacks.forEach((other) => {
        if (other !== stack && other.open) other.open = false;
      });
    }
    const label = stack.querySelector("[data-block-stack-state]");
    if (label) label.textContent = stack.open ? "收起" : "展开";
  }));
}

function bindPracticeStarters(root) {
  $$('[data-start-practice]', root).forEach((button) => button.addEventListener("click", () => startPracticeSession(button.dataset.conceptId, button.dataset.questionType || "", button.dataset.subtypeId || "")));
}

function practiceGradeValue(value) {
  return value == null ? "" : String(value);
}

function renderPracticeAttachments(items = []) {
  return items.length
    ? `<div class="practice-existing-attachments"><span>已提交附件：</span>${items.map((item) => `<a href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.filename || "作答附件")}</a>`).join("、")}</div>`
    : "";
}

function renderAnswerImageUpload({ scope, questionId, status = "支持 PNG/JPG/WebP/GIF，单张不超过 8 MB" } = {}) {
  const safeQuestionId = escapeAttr(questionId);
  const prefix = scope === "simulation" ? "sim" : "practice";
  const rowClass = scope === "simulation" ? "sim-upload-row" : "practice-upload-row";
  return `<div class="answer-support-strip"><div class="answer-support-title"><strong>图片作答</strong><span>与手写作答一样，会随提交保存</span></div><div class="${rowClass} answer-upload-row"><label class="upload-button small-upload" for="${prefix}-image-${safeQuestionId}">＋ 上传作答图片</label><input id="${prefix}-image-${safeQuestionId}" type="file" data-${prefix}-image="${safeQuestionId}" accept="image/png,image/jpeg,image/webp,image/gif" /><span data-${prefix}-image-status="${safeQuestionId}">${escapeHtml(status)}</span></div></div>`;
}

function practiceQuestionIsAnswered(question) {
  const answerState = question?.answer_state || {};
  return Boolean((answerState.answer || "").trim() || answerState.self_grade != null || (answerState.attachments || []).length || handwritingHasDraft(answerHandwritingKey("practice", question?.id)));
}

function practiceCardHasDraft(card) {
  if (!card) return false;
  const answer = card.querySelector("[data-practice-answer]")?.value.trim() || "";
  const grade = card.querySelector("[data-practice-grade]");
  return Boolean(answer || (grade && grade.value !== "") || card.querySelector(".practice-existing-attachments") || handwritingPadHasContent(card.querySelector("[data-handwriting-pad]")));
}

function renderPracticeSession() {
  const session = state.practiceSession;
  if (!session) return;
  const finished = session.status === "finished";
  const questions = session.questions || [];
  state.practiceQuestionIndex = Math.max(0, Math.min(state.practiceQuestionIndex, Math.max(questions.length - 1, 0)));
  const activeIndex = state.practiceQuestionIndex;
  const countLabel = session.question_count >= session.requested_count ? `${session.question_count} 题` : `题库仅有 ${session.question_count} 题`;
  const sessionSubtypeName = session.subtype_id ? subtypeName(session.subtype_id) : (session.question_type ? `${typeLabel(session.question_type)}题` : "混合题型");
  const cards = questions.map((question, index) => {
    const answerState = question.answer_state || {};
    const answer = answerState.answer || "";
    const result = answerState.result || {};
    const selectedGrade = practiceGradeValue(answerState.self_grade);
    const gradeOptions = [
      ["", "暂不自评"], ["1", "完整正确（100%）"], ["0.7", "主要正确（70%）"], ["0.4", "部分得到（40%）"], ["0", "不会/错误（0%）"],
    ].map(([value, label]) => `<option value="${value}" ${selectedGrade === value ? "selected" : ""}>${label}</option>`).join("");
    const resultMarkup = finished ? `<div class="practice-answer-result ${escapeAttr(result.status || answerState.status || "manual")}"><span>${escapeHtml(resultLabel(result.status || answerState.status))}</span><b>${formatScore(answerState.score)} / ${formatScore(answerState.max_score || question.points)} 分</b>${question.answer_markdown ? `<h5>来源答案</h5><div class="markdown-body">${renderMarkdown(question.answer_markdown)}</div>` : ""}${question.solution_markdown ? `<h5>来源解析</h5><div class="markdown-body">${renderMarkdown(question.solution_markdown)}</div>` : ""}</div>` : "";
    const answerArea = renderAnswerEditor(question, { mode: "practice", value: answer, readonly: finished });
    const uploadArea = finished ? renderPracticeAttachments(answerState.attachments || []) : `${renderAnswerImageUpload({ scope: "practice", questionId: question.id })}${renderPracticeAttachments(answerState.attachments || [])}`;
    const selfGrade = question.question_type === "solution" ? `<label class="practice-grade-label">解答题自评<select data-practice-grade="${escapeAttr(question.id)}" ${finished ? "disabled" : ""}>${gradeOptions}</select></label>` : "";
    const answerBoard = `<div class="practice-answer-grid">${answerArea}${uploadArea}${selfGrade}</div>`;
    const subtypeLine = practiceQuestionSubtypeLine(question);
    const assistMarkup = `<div class="practice-assist-actions"><span class="practice-assist-label">卡住了？</span><button type="button" class="text-button" data-practice-hint="${escapeAttr(question.id)}">问问 AI</button><button type="button" class="text-button" data-practice-source="${escapeAttr(question.id)}">查看解析</button></div><div class="practice-assist-panel" data-practice-assist="${escapeAttr(question.id)}" hidden></div>`;
    return `<article class="practice-session-question" data-practice-question="${escapeAttr(question.id)}" data-practice-question-card="${index}" ${index === activeIndex ? "" : "hidden"}><div class="practice-question-head"><span>${String(index + 1).padStart(2, "0")} / <span data-practice-subtype-label="${escapeAttr(question.id)}">${escapeHtml(subtypeLine)}</span></span><span class="practice-question-history">${questionAttemptMarkup(question, true)}</span><b>${formatScore(question.points)} 分</b></div><div class="practice-question-body markdown-body">${renderMarkdown(question.question_markdown)}</div><div class="practice-question-tags">${questionConceptMarkup(question)}${questionSubtypeMarkup(question)}</div>${classificationEditorMarkup(question, "practice")}${answerBoard}${assistMarkup}${resultMarkup}</article>`;
  }).join("");
  const answeredCount = questions.filter(practiceQuestionIsAnswered).length;
  const statusLabel = finished ? `已提交 · 得分 ${formatScore(session.score)} / ${formatScore(session.max_score)} 分` : `已填写 ${answeredCount} / ${questions.length} 题 · 可随时暂存`;
  const navigator = `<nav class="practice-question-navigator" aria-label="专项训练题目导航"><div><strong>题目导航</strong><span>一次专注一道，答案会在切题时保留</span></div><div class="practice-question-tabs" role="tablist">${questions.map((question, index) => `<button type="button" data-practice-question-index="${index}" class="practice-question-tab ${index === activeIndex ? "is-active" : ""} ${practiceQuestionIsAnswered(question) ? "is-complete" : ""}" aria-selected="${index === activeIndex ? "true" : "false"}" aria-label="第 ${index + 1} 题${practiceQuestionIsAnswered(question) ? "，已填写" : ""}">${index + 1}</button>`).join("")}</div></nav>`;
  const cardNavigation = `<nav class="practice-card-navigation" aria-label="上一题或下一题"><button type="button" class="quiet-button" id="practice-question-prev" ${activeIndex === 0 ? "disabled" : ""}>上一题</button><span id="practice-question-position">第 ${activeIndex + 1} / ${questions.length} 题</span><button type="button" class="secondary-button" id="practice-question-next" ${activeIndex >= questions.length - 1 ? "disabled" : ""}>下一题</button></nav>`;
  $("blocks-container").classList.add("practice-active");
  $("blocks-container").innerHTML = `<section class="practice-session-shell"><header class="practice-session-header"><div><span class="eyebrow">TRAINING SESSION / ${escapeHtml(sessionSubtypeName)}</span><h3>${escapeHtml(conceptName(session.concept_id))} · ${escapeHtml(sessionSubtypeName)}训练</h3><p>随机抽取 ${escapeHtml(countLabel)} · 真实题库 · ${finished ? "本次已完成" : "提交后统一判题"}</p></div><div class="practice-session-actions"><button class="text-button" id="leave-practice-session">返回分块</button><button class="secondary-button" id="refresh-practice-session">换一组题</button>${finished ? "" : `<button class="secondary-button" id="save-practice-session">保存暂存</button><button class="primary-button" id="submit-practice-session">提交训练</button>`}</div></header><div class="practice-session-status"><span>${escapeHtml(statusLabel)}</span><span class="practice-session-id">${escapeHtml(session.id.slice(0, 8))}</span></div>${navigator}<div class="practice-session-list">${cards}</div>${cardNavigation}${finished ? `<footer class="practice-session-footer"><p>本次结果已经写入学习记录，可以返回分块继续训练。</p><button class="primary-button" id="back-after-practice">返回分块训练</button></footer>` : `<footer class="practice-session-footer"><p>未提交前，文字与手写内容仅暂存在本机；提交后会作为正式答案与图片附件保存。</p><button class="primary-button" id="submit-practice-session-bottom">提交 ${questions.length} 题训练</button></footer>`}</section>`;
  typeset($("blocks-container"));
  bindAnswerEditors($('blocks-container'));
  bindClassificationControls($("blocks-container"));
  bindPracticeSession();
  window.requestAnimationFrame?.(() => $("blocks-container").querySelectorAll("[data-handwriting-pad]").forEach(resizeHandwritingPad));
}

function updatePracticeSessionStatus() {
  const session = state.practiceSession;
  if (!session || session.status === "finished") return;
  const root = $("blocks-container");
  const answered = $$('[data-practice-question-card]', root).filter(practiceCardHasDraft).length;
  const status = root.querySelector(".practice-session-status span");
  if (status) status.textContent = `已填写 ${answered} / ${session.questions.length} 题 · 可随时暂存`;
  updatePracticeQuestionNavigator();
}

function updatePracticeQuestionNavigator() {
  const root = $("blocks-container");
  $$('[data-practice-question-card]', root).forEach((card, index) => {
    const complete = practiceCardHasDraft(card);
    const button = $$('[data-practice-question-index]', root)[index];
    button?.classList.toggle("is-complete", complete);
    button?.setAttribute("aria-label", `第 ${index + 1} 题${complete ? "，已填写" : ""}`);
  });
}

function selectPracticeQuestion(index, focusAnswer = false) {
  const root = $("blocks-container");
  const cards = $$('[data-practice-question-card]', root);
  if (!cards.length) return;
  state.practiceQuestionIndex = Math.max(0, Math.min(Number(index) || 0, cards.length - 1));
  cards.forEach((card, cardIndex) => { card.hidden = cardIndex !== state.practiceQuestionIndex; });
  $$('[data-practice-question-index]', root).forEach((button, buttonIndex) => {
    const active = buttonIndex === state.practiceQuestionIndex;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  const previous = $("practice-question-prev");
  const next = $("practice-question-next");
  if (previous) previous.disabled = state.practiceQuestionIndex === 0;
  if (next) next.disabled = state.practiceQuestionIndex === cards.length - 1;
  const position = $("practice-question-position");
  if (position) position.textContent = `第 ${state.practiceQuestionIndex + 1} / ${cards.length} 题`;
  cards[state.practiceQuestionIndex].scrollIntoView({ behavior: "smooth", block: "start" });
  window.requestAnimationFrame?.(() => cards[state.practiceQuestionIndex].querySelectorAll("[data-handwriting-pad]").forEach(resizeHandwritingPad));
  if (focusAnswer) cards[state.practiceQuestionIndex].querySelector('[data-formula-input], [data-choice-editor]')?.focus({ preventScroll: true });
}

function bindPracticeSession() {
  const root = $("blocks-container");
  $$('[data-practice-answer]', root).forEach((field) => field.addEventListener("input", updatePracticeSessionStatus));
  $$('[data-practice-grade]', root).forEach((field) => field.addEventListener("change", updatePracticeSessionStatus));
  if (root.dataset.practiceHandwritingBound !== "true") {
    root.dataset.practiceHandwritingBound = "true";
    root.addEventListener("handwritingchange", updatePracticeSessionStatus);
  }
  $$('[data-practice-image]', root).forEach((input) => input.addEventListener("change", () => {
    const status = $$('[data-practice-image-status]', root).find((item) => item.dataset.practiceImageStatus === input.dataset.practiceImage);
    const error = validateImageFile(input.files?.[0]);
    if (error) {
      input.value = "";
      if (status) status.textContent = error;
      return;
    }
    if (status) status.textContent = input.files?.[0] ? `已选择：${input.files[0].name}` : "支持图片，单张不超过 8 MB";
  }));
  $("leave-practice-session")?.addEventListener("click", () => { state.practiceSession = null; loadBlocks(); });
  $("back-after-practice")?.addEventListener("click", () => { state.practiceSession = null; loadBlocks(); });
  $("refresh-practice-session")?.addEventListener("click", refreshPracticeSession);
  $("save-practice-session")?.addEventListener("click", savePracticeSession);
  $("submit-practice-session")?.addEventListener("click", () => submitPracticeSession(false));
  $("submit-practice-session-bottom")?.addEventListener("click", () => submitPracticeSession(false));
  $$('[data-practice-question-index]', root).forEach((button) => button.addEventListener("click", () => selectPracticeQuestion(button.dataset.practiceQuestionIndex)));
  $("practice-question-prev")?.addEventListener("click", () => selectPracticeQuestion(state.practiceQuestionIndex - 1, true));
  $("practice-question-next")?.addEventListener("click", () => selectPracticeQuestion(state.practiceQuestionIndex + 1, true));
  $$('[data-practice-hint]', root).forEach((button) => button.addEventListener("click", () => requestPracticeHint(button.dataset.practiceHint, root)));
  $$('[data-practice-source]', root).forEach((button) => button.addEventListener("click", () => revealPracticeSource(button.dataset.practiceSource, root)));
}

function practiceAssistPanel(questionId, root) {
  return $$('[data-practice-assist]', root).find((panel) => panel.dataset.practiceAssist === questionId);
}

function practiceAnswerValue(questionId, root) {
  return $$('[data-practice-answer]', root).find((field) => field.dataset.practiceAnswer === questionId)?.value || "";
}

async function requestPracticeHint(questionId, root = document) {
  const button = $$('[data-practice-hint]', root).find((item) => item.dataset.practiceHint === questionId);
  const panel = practiceAssistPanel(questionId, root);
  if (!button || !panel) return;
  button.disabled = true;
  panel.hidden = false;
  panel.innerHTML = '<p class="muted-copy">AI 正在根据题面和你的当前作答整理第一步思路……</p>';
  try {
    const payload = await fetchJSON(`/api/questions/${encodeURIComponent(questionId)}/hint`, jsonOptions({
      user_id: state.userId,
      answer: practiceAnswerValue(questionId, root),
      request: "请先给我解题方向和第一步，最多给三层递进提示，不要直接给最终答案；如果来源没有解析，请明确说明。",
    }));
    panel.innerHTML = `<div class="practice-assist-head"><strong>解题思路提示</strong><span>${escapeHtml(payload.model || "已配置模型")}</span></div><div class="markdown-body">${renderMarkdown(payload.content || "模型没有返回提示。")}</div>`;
    typeset(panel);
  } catch (error) {
    panel.innerHTML = `<p class="error-copy">AI 提示失败：${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
  }
}

async function revealPracticeSource(questionId, root = document) {
  const button = $$('[data-practice-source]', root).find((item) => item.dataset.practiceSource === questionId);
  const panel = practiceAssistPanel(questionId, root);
  if (!button || !panel) return;
  button.disabled = true;
  panel.hidden = false;
  panel.innerHTML = '<p class="muted-copy">正在读取来源答案与解析……</p>';
  try {
    const question = await fetchJSON(`/api/questions/${encodeURIComponent(questionId)}?reveal=true&user_id=${encodeURIComponent(state.userId)}`);
    const answer = question.answer_markdown ? `<h4>来源答案</h4><div class="markdown-body">${renderMarkdown(question.answer_markdown)}</div>` : '<p class="muted-copy">当前来源没有提供标准答案。</p>';
    const solution = question.solution_markdown ? `<h4>来源解析</h4><div class="markdown-body">${renderMarkdown(question.solution_markdown)}</div>` : '<p class="muted-copy">当前来源文件没有提供该题解析。</p>';
    panel.innerHTML = `<div class="practice-assist-head"><strong>来源解析</strong><span>${escapeHtml(question.source_path || "本地题库")}</span></div>${answer}${solution}`;
    typeset(panel);
  } catch (error) {
    panel.innerHTML = `<p class="error-copy">解析读取失败：${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
  }
}

async function collectPracticeSessionPayload({ includeHandwriting = false } = {}) {
  const answers = {};
  const selfGrades = {};
  const attachmentIds = {};
  $$('[data-practice-answer]').forEach((field) => { answers[field.dataset.practiceAnswer] = field.value; });
  $$('[data-practice-grade]').forEach((field) => { if (field.value !== "") selfGrades[field.dataset.practiceGrade] = Number(field.value); });
  (state.practiceSession?.questions || []).forEach((question) => {
    const existing = (question.answer_state?.attachments || []).map((item) => item.id).filter(Boolean);
    if (existing.length) attachmentIds[question.id] = existing;
  });
  for (const input of $$('[data-practice-image]')) {
    const file = input.files?.[0];
    if (!file) continue;
    const status = $$('[data-practice-image-status]').find((item) => item.dataset.practiceImageStatus === input.dataset.practiceImage);
    if (status) status.textContent = "正在上传图片……";
    const uploaded = await uploadAnswerImage(file, input.dataset.practiceImage);
    attachmentIds[input.dataset.practiceImage] = [...(attachmentIds[input.dataset.practiceImage] || []), uploaded.attachment_id];
    input.value = "";
    if (status) status.textContent = "图片已保存到本次训练";
  }
  if (includeHandwriting) await collectHandwritingAttachments($("blocks-container"), attachmentIds);
  return { user_id: state.userId, answers, self_grades: selfGrades, attachment_ids: attachmentIds };
}

async function refreshPracticeSession() {
  const session = state.practiceSession;
  const button = $("refresh-practice-session");
  if (!session) return;
  const hasDraft = $$('[data-practice-answer]').some((field) => field.value.trim()) || $$('[data-practice-grade]').some((field) => field.value !== "") || $$('[data-handwriting-pad]').some(handwritingPadHasContent) || $$('[data-practice-image]').some((input) => input.files?.length);
  if (hasDraft && !window.confirm("换一组题会丢弃当前未提交的草稿，已提交的历史记录不会丢失。确定换题吗？")) return;
  const currentIds = (session.questions || []).map((question) => question.id).filter(Boolean);
  await startPracticeSession(session.concept_id, session.question_type || "", session.subtype_id || "", currentIds, button);
}

async function startPracticeSession(conceptId, questionType = "", subtypeId = "", excludeQuestionIds = [], triggerButton = null) {
  const button = triggerButton || $$('[data-start-practice]').find((item) => item.dataset.conceptId === conceptId && (item.dataset.subtypeId || "") === subtypeId && (item.dataset.questionType || "") === questionType);
  if (button) button.disabled = true;
  try {
    state.practiceSession = await fetchJSON("/api/practice/sessions", jsonOptions({ user_id: state.userId, exam_type: "数学二", concept_id: conceptId, question_type: questionType, subtype_id: subtypeId, count: 15, exclude_question_ids: excludeQuestionIds }));
    state.practiceQuestionIndex = 0;
    renderPracticeSession();
    if (excludeQuestionIds.length) showToast("已优先避开上一组题；题库较小时会保留少量旧题。", false);
    $("blocks-container").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showToast(`生成训练失败：${error.message}`, true);
    if (button) button.disabled = false;
  }
}

async function savePracticeSession() {
  const session = state.practiceSession;
  const button = $("save-practice-session");
  if (!session || !button) return;
  button.disabled = true;
  try {
    const payload = await collectPracticeSessionPayload();
    state.practiceSession = await fetchJSON(`/api/practice/sessions/${encodeURIComponent(session.id)}`, { ...jsonOptions(payload), method: "PUT" });
    renderPracticeSession();
    showToast("暂存已保存到本机。继续编辑后可以再次保存。", false);
  } catch (error) {
    showToast(`保存暂存失败：${error.message}`, true);
    button.disabled = false;
  }
}

async function submitPracticeSession(confirmSubmit = false) {
  const session = state.practiceSession;
  if (!session || session.status === "finished") return;
  if (!confirmSubmit && !window.confirm("提交后将统一判题并计入掌握度，确定提交这套训练吗？")) return;
  const buttons = [$("submit-practice-session"), $("submit-practice-session-bottom")].filter(Boolean);
  buttons.forEach((button) => { button.disabled = true; });
  try {
    const payload = await collectPracticeSessionPayload({ includeHandwriting: true });
    state.practiceSession = await fetchJSON(`/api/practice/sessions/${encodeURIComponent(session.id)}/submit`, jsonOptions(payload));
    clearHandwritingDrafts($("blocks-container"));
    renderPracticeSession();
    await refreshLearningData();
    showToast(`训练已提交：${formatScore(state.practiceSession.score)} / ${formatScore(state.practiceSession.max_score)} 分。`);
  } catch (error) {
    showToast(`提交训练失败：${error.message}`, true);
    buttons.forEach((button) => { button.disabled = false; });
  }
}

async function openQuestion(questionId) {
  try {
    const question = await fetchJSON(`/api/questions/${encodeURIComponent(questionId)}?user_id=${encodeURIComponent(state.userId)}`);
    state.currentQuestion = question;
    $("modal-question-ref").textContent = `${question.exam_type} · ${question.year} 年 · 第 ${question.number} 题`;
    $("modal-question-type").textContent = `${typeLabel(question.question_type)}题 · ${formatScore(question.points)} 分`;
    $("question-modal-title").textContent = `${question.year} 年真题 / Q${question.number}`;
    $("modal-question-tags").innerHTML = questionConceptLabels(question).map((concept) => `<span class="tag ${concept.scope === "out-of-syllabus" ? "out-of-syllabus" : ""}">${escapeHtml(concept.scope === "out-of-syllabus" ? `${concept.scope_label} · ${concept.name}` : concept.name)}</span>`).join("") + questionSubtypeLabels(question).map((item) => `<span class="tag subtype-tag">${escapeHtml(item.name || subtypeName(item.id))}</span>`).join("");
    $("modal-question-attempts").innerHTML = questionAttemptMarkup(question);
    $("modal-classification").innerHTML = classificationEditorMarkup(question, "modal");
    bindClassificationControls($("modal-classification"));
    $("modal-question-body").innerHTML = renderMarkdown(question.question_markdown);
    typeset($("modal-question-body"));
    $("modal-answer-editor").innerHTML = renderAnswerEditor(question, { mode: "modal" });
    bindAnswerEditors($("modal-answer-editor"));
    $("answer-image-input").value = "";
    clearImagePreview($("answer-image-preview"));
    $("answer-image-status").textContent = "支持 PNG/JPG/WebP/GIF，单张不超过 8 MB";
    $("answer-duration").value = "0";
    $("self-grade").value = "";
    $("self-grade-wrap").style.display = question.question_type === "solution" ? "grid" : "none";
    $("answer-hint").textContent = question.question_type === "choice"
      ? "点击选项，也可以直接手写或上传图片"
      : question.question_type === "fill"
        ? "文字、公式、手写和图片都可以作为正式答案"
        : "先写步骤，或直接手写；图片会和答案一起保存";
    $("question-result").hidden = true;
    $("tutor-box").hidden = true;
    $("modal-source").textContent = `SOURCE · ${question.source_path || "本地题库"}`;
    $("question-modal").classList.add("open");
    $("question-modal").setAttribute("aria-hidden", "false");
    window.requestAnimationFrame?.(() => $("modal-answer-editor").querySelectorAll("[data-handwriting-pad]").forEach(resizeHandwritingPad));
    window.setTimeout(() => $("answer-input")?.focus(), 120);
  } catch (error) {
    showToast(`打开题目失败：${error.message}`, true);
  }
}

function closeQuestion() {
  const fullscreenPad = $("modal-answer-editor")?.querySelector("[data-handwriting-pad]");
  if (fullscreenPad?.classList.contains("is-fullscreen-fallback")) setHandwritingFullscreen(fullscreenPad, false);
  if (document.fullscreenElement === fullscreenPad) document.exitFullscreen?.();
  $("question-modal").classList.remove("open");
  $("question-modal").setAttribute("aria-hidden", "true");
  state.currentQuestion = null;
}

function resultLabel(status) {
  return { correct: "判定正确", incorrect: "需要订正", partial: "部分得分", manual: "等待自评" }[status] || status;
}

function renderAnswerAttachmentGallery(items = [], heading = "") {
  if (!items.length) return "";
  const title = heading ? `<h4>${escapeHtml(heading)}</h4>` : "";
  return `<div class="result-attachments">${title}${items.map((item) => `<a href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer"><img src="${escapeAttr(item.url)}" alt="${escapeAttr(item.filename || "作答附件")}" /><span>${escapeHtml(item.filename || "作答附件")}</span></a>`).join("")}</div>`;
}

function renderQuestionResult(payload) {
  const result = payload.result || {};
  const box = $("question-result");
  box.className = `result-box ${result.status || "manual"}`;
  box.hidden = false;
  const expected = result.expected_answer || payload.answer_markdown || "";
  const solution = payload.solution_markdown || "";
  const attachments = payload.attachments || [];
  const attachmentMarkup = renderAnswerAttachmentGallery(attachments, "已提交的作答附件");
  box.innerHTML = `<div class="result-head"><span class="result-status">${resultLabel(result.status)}</span><span class="result-score">${formatScore(result.score)} / ${formatScore(result.max_score)} 分</span></div>
    <div class="result-detail"><h4>${result.error_type ? `记录：${escapeHtml(result.error_type)}` : "本次判定"}</h4><p class="muted-copy">${result.status === "manual" ? "来源没有可自动比对的完整标准答案，请根据步骤选择自评分数，或使用下方 AI 复核。" : result.status === "correct" ? "这次作答已计入掌握度。继续做一题同知识块的变式题。" : "这次作答已计入薄弱项分析，建议查看来源解析后再做一题相近题。"}</p>${attachmentMarkup}${expected ? `<h4>来源答案</h4><div class="markdown-body">${renderMarkdown(expected)}</div>` : ""}${solution ? `<h4>来源解析</h4><div class="markdown-body">${renderMarkdown(solution)}</div>` : `<h4>来源解析</h4><p class="muted-copy">当前来源文件没有提供该题解析。</p>`}</div>`;
  typeset(box);
  $("tutor-box").hidden = false;
  $("tutor-content").textContent = "提交后可让已配置的模型根据题面、作答和来源解析进行复核。";
}

async function submitAnswer() {
  const question = state.currentQuestion;
  if (!question) return;
  const button = $("submit-answer");
  button.disabled = true;
  const selfGradeValue = $("self-grade").value;
  const imageInput = $("answer-image-input");
  try {
    const attachmentIds = [];
    if (imageInput.files?.[0]) {
      $("answer-image-status").textContent = "正在上传图片……";
      const uploaded = await uploadAnswerImage(imageInput.files[0], question.id);
      attachmentIds.push(uploaded.attachment_id);
    }
    await collectHandwritingAttachments($("modal-answer-editor"), attachmentIds, { questionId: question.id });
    const payload = await fetchJSON(`/api/questions/${encodeURIComponent(question.id)}/attempts`, jsonOptions({
      user_id: state.userId,
      answer: $("answer-input").value,
      self_grade: selfGradeValue === "" ? null : Number(selfGradeValue),
      duration_seconds: Math.max(0, Number($("answer-duration").value || 0) * 60),
      mode: "practice",
      attachment_ids: attachmentIds,
    }));
    clearHandwritingDrafts($("modal-answer-editor"));
    renderQuestionResult(payload);
    showToast("作答已保存，掌握度会在总览中更新。");
    await refreshLearningData();
  } catch (error) {
    showToast(`提交失败：${error.message}`, true);
  } finally {
    button.disabled = false;
  }
}

async function askTutor() {
  if (!state.currentQuestion) return;
  const button = $("ask-tutor");
  button.disabled = true;
  $("tutor-content").textContent = "模型正在分析，请稍候……";
  try {
    const payload = await fetchJSON(`/api/questions/${encodeURIComponent(state.currentQuestion.id)}/tutor`, jsonOptions({
      user_id: state.userId,
      answer: $("answer-input").value,
      request: "分析我的错误，指出最关键的思路断点，并给出下一步训练建议",
    }));
    const content = String(payload.content || "");
    let html = renderMarkdown(content);
    try {
      const parsed = JSON.parse(content);
      html = Object.entries(parsed).map(([key, value]) => `<p><strong>${escapeHtml(key)}：</strong>${renderMarkdown(String(value))}</p>`).join("");
    } catch { /* model may return ordinary text; it is still shown safely */ }
    $("tutor-content").innerHTML = html || "模型没有返回可显示的内容。";
  } catch (error) {
    $("tutor-content").textContent = `模型复核失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
}

async function refreshLearningData() {
  try {
    const [progress, forecast, analytics, blocks, next] = await Promise.all([
      fetchJSON(`/api/progress?user_id=${encodeURIComponent(state.userId)}`),
      fetchJSON(`/api/forecast?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二`),
      fetchJSON(`/api/analytics?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二`),
      fetchJSON(`/api/study/blocks?user_id=${encodeURIComponent(state.userId)}&limit=12`),
      fetchJSON(`/api/practice/next?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二&limit=8`),
    ]);
    state.progress = progress;
    state.forecast = forecast;
    state.analytics = analytics;
    state.blocks = blocks.blocks || [];
    state.nextQuestions = next.items || [];
    renderOverview();
    renderAnalytics();
    if (state.view === "blocks") loadBlocks();
    if (state.view === "analytics") await loadAnalytics();
  } catch (error) {
    console.warn("learning refresh failed", error);
  }
}

async function loadSimulationCatalog() {
  if (!state.exams.length) {
    try { await loadBaseData(); } catch (error) { showNotice(error.message); return; }
  }
  const savedId = readSavedSimulationId();
  if (savedId && !state.currentSimulation) {
    try {
      state.currentSimulation = await fetchJSON(`/api/simulations/${encodeURIComponent(savedId)}`);
      saveSimulationPointer(state.currentSimulation.id);
      renderSimulation();
      if (state.currentSimulation.status !== "finished") startSimulationClock();
      return;
    } catch {
      localStorage.removeItem(simulationPointerKey());
      localStorage.removeItem("ai-math-simulation");
    }
  }
  if (!state.currentSimulation) renderSimulationEmpty();
}

function renderSimulationEmpty() {
  const container = $("simulation-container");
  if (!container) return;
  container.innerHTML = `<div class="empty-state"><div class="empty-mark">⌁</div><h3>还没有进行中的模拟考</h3><p>选择年份并生成一套完整试卷，提交后结果会回流到你的掌握度和分数预估。</p></div>`;
}

async function createSimulation() {
  const button = $("create-simulation");
  button.disabled = true;
  try {
    const payload = await fetchJSON("/api/simulations", jsonOptions({
      user_id: state.userId,
      exam_type: "数学二",
      year: Number($("simulation-year").value) || null,
      duration_minutes: Number($("simulation-duration").value || 180),
    }));
    state.currentSimulation = payload;
    state.simulationCurrentIndex = 0;
    state.simulationCardFilter = "all";
    saveSimulationPointer(payload.id);
    renderSimulation();
    startSimulationClock();
    showToast(`已生成 ${payload.year} 年完整试卷，共 ${payload.questions.length} 题。`);
  } catch (error) {
    showToast(`生成模拟考失败：${error.message}`, true);
  } finally {
    button.disabled = false;
  }
}

async function cancelSimulation() {
  const simulation = state.currentSimulation;
  if (!simulation || simulation.status === "finished") return;
  if (!window.confirm("取消后将删除这套进行中的试卷、答题草稿和答题卡状态，确定取消吗？")) return;
  const button = $("cancel-simulation");
  if (button) button.disabled = true;
  try {
    await fetchJSON(`/api/simulations/${encodeURIComponent(simulation.id)}?user_id=${encodeURIComponent(state.userId)}`, { method: "DELETE" });
    window.clearInterval(state.simulationTimer);
    localStorage.removeItem(simulationPointerKey());
    localStorage.removeItem("ai-math-simulation");
    localStorage.removeItem(simulationDraftKey(simulation.id));
    state.currentSimulation = null;
    state.simulationDeadline = null;
    state.simulationCurrentIndex = 0;
    state.simulationCardFilter = "all";
    renderSimulationEmpty();
    showToast("模拟考已取消，答题草稿已清理。", false);
  } catch (error) {
    showToast(`取消模拟考失败：${error.message}`, true);
    if (button) button.disabled = false;
  }
}

function renderSimulation() {
  const simulation = state.currentSimulation;
  if (!simulation) return;
  const container = $("simulation-container");
  if (!container) return;
  delete container.dataset.simPlatformBound;
  const finished = simulation.status === "finished";
  const questions = simulation.questions || [];
  if (finished) {
    const score = formatScore(simulation.score);
    container.innerHTML = `<div class="simulation-result"><div class="simulation-result-score">${score}<span> / ${formatScore(simulation.max_score)} 分</span></div><div><h3>${simulation.year} 年模拟考已完成</h3><p>本次成绩已计入学习记录。你可以回到分块训练查看哪些知识块拉低了得分，并继续做针对性练习。</p></div></div>${renderSimulationPaper(simulation, true)}`;
    typeset(container);
    bindSimulationPlatform(container);
    refreshSimulationAnswerCard(container);
    return;
  }
  container.innerHTML = renderSimulationPaper(simulation, false);
  typeset(container);
  bindAnswerEditors(container);
  bindSimulationUploads(container);
  bindSimulationPlatform(container);
  window.requestAnimationFrame?.(() => container.querySelectorAll("[data-handwriting-pad]").forEach(resizeHandwritingPad));
}

function renderSimulationPaper(simulation, finished) {
  const questions = simulation.questions || [];
  const draft = readSimulationDraft(simulation);
  const renderSubmittedAnswer = (question) => {
    const attempt = question.attempt || {};
    const answer = String(attempt.answer || "").trim();
    const attachments = attempt.attachments || [];
    if (!answer && !attachments.length) return `<div class="sim-submitted-answer"><span>本题未记录文字、手写或图片答案。</span></div>`;
    return `<section class="sim-submitted-answer"><div class="sim-submitted-answer-head"><strong>已提交作答</strong><span>${attachments.length ? `${attachments.length} 个附件` : "文字答案"}</span></div>${answer ? `<div class="markdown-body sim-submitted-answer-text">${renderMarkdown(answer)}</div>` : ""}${renderAnswerAttachmentGallery(attachments)}</section>`;
  };
  const questionMarkup = questions.map((question, index) => {
    const draftValue = simulationDraftForQuestion(simulation, question, draft);
    const gradeMarkup = question.question_type === "solution" ? `<div class="sim-self-grade"><span>解答题自评</span><select data-sim-grade="${escapeAttr(question.id)}"><option value="" ${draftValue.selfGrade === "" ? "selected" : ""}>暂不自评</option><option value="1" ${String(draftValue.selfGrade) === "1" ? "selected" : ""}>完整正确（100%）</option><option value="0.7" ${String(draftValue.selfGrade) === "0.7" ? "selected" : ""}>主要正确（70%）</option><option value="0.4" ${String(draftValue.selfGrade) === "0.4" ? "selected" : ""}>部分得到（40%）</option><option value="0" ${String(draftValue.selfGrade) === "0" ? "selected" : ""}>不会/错误（0%）</option></select></div>` : "";
    const answerMarkup = finished ? renderSubmittedAnswer(question) : `<div class="sim-answer">${renderAnswerEditor(question, { mode: "simulation", value: draftValue.answer, contextId: simulation.id })}${renderAnswerImageUpload({ scope: "simulation", questionId: question.id, status: "可选，单张不超过 8 MB" })}${gradeMarkup}</div>`;
    return `<article class="simulation-question" data-sim-index="${index}"><div class="sim-q-head"><span class="sim-q-ref">${String(index + 1).padStart(2, "0")} / 第 ${question.number} 题 · ${typeLabel(question.question_type)}</span><span class="sim-q-points">${formatScore(question.points)} 分</span></div><div class="markdown-body">${renderMarkdown(question.question_markdown)}</div>${answerMarkup}</article>`;
  }).join("");
  const simulationHeaderAction = finished ? "" : `<div class="simulation-header-actions"><button type="button" class="secondary-button simulation-cancel-button" id="cancel-simulation">取消模拟考</button><div class="simulation-clock" id="simulation-clock">180:00</div></div>`;
  return `<div class="simulation-workspace"><div class="simulation-shell"><div class="simulation-header"><div><h3>${simulation.year} 年数学二 · 全真模拟</h3><p>${questions.length} 道题 · 满分 ${formatScore(simulation.max_score)} · ${finished ? "答案与解析已开放" : "答案不会自动显示，提交后统一判定"}</p></div>${finished ? `<div class="simulation-clock" id="simulation-clock">已完成</div>` : simulationHeaderAction}</div><div class="simulation-progress"><span id="simulation-progress-bar" style="--progress:0"></span></div><div class="simulation-question-list">${questionMarkup}</div>${finished ? "" : `<div class="simulation-footer"><p>解答题若暂不自评，将被诚实记录为“待自评”，不自动猜分。</p><button class="primary-button" id="submit-simulation">提交整卷</button></div>`}</div><aside class="simulation-rail" aria-label="模拟考答题辅助栏"><div class="simulation-sticky-timer ${finished ? "finished" : ""}"><span>剩余时间</span><strong id="simulation-sticky-clock">${finished ? "已完成" : "180:00"}</strong><small>${finished ? "本套试卷已提交" : "计时不会因离开页面而暂停"}</small></div>${renderSimulationAnswerCard(simulation, finished)}</aside></div>`;
}

function bindSimulationUploads(root) {
  $$('[data-sim-image]', root).forEach((input) => input.addEventListener("change", () => {
    const status = $$('[data-sim-image-status]', root).find((item) => item.dataset.simImageStatus === input.dataset.simImage);
    const file = input.files?.[0];
    const error = validateImageFile(file);
    if (error) {
      input.value = "";
      if (status) status.textContent = error;
      return;
    }
    if (status) status.textContent = file ? `已选择：${file.name}` : "可选，单张不超过 8 MB";
  }));
}

function startSimulationClock() {
  window.clearInterval(state.simulationTimer);
  const simulation = state.currentSimulation;
  if (!simulation || simulation.status === "finished") return;
  const startedAt = new Date(simulation.started_at || Date.now()).getTime();
  state.simulationDeadline = startedAt + Number(simulation.duration_seconds || 10800) * 1000;
  const tick = () => {
    const remaining = Math.max(0, state.simulationDeadline - Date.now());
    const seconds = Math.floor(remaining / 1000);
    const minutes = Math.floor(seconds / 60);
    const display = `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    const clock = $("simulation-clock");
    if (clock) clock.textContent = display;
    const stickyClock = $("simulation-sticky-clock");
    if (stickyClock) stickyClock.textContent = display;
    const answered = simulationAnsweredCount(simulation, $("simulation-container") || document);
    const total = (simulation.questions || []).length || 1;
    const bar = $("simulation-progress-bar");
    if (bar) bar.style.setProperty("--progress", String(answered / total));
    refreshSimulationAnswerCard($("simulation-container") || document);
    $("simulation-sticky-clock")?.closest(".simulation-sticky-timer")?.classList.toggle("warning", remaining <= 5 * 60 * 1000);
    if (remaining <= 0) {
      window.clearInterval(state.simulationTimer);
      showToast("模拟考时间到，正在自动提交。", true);
      submitSimulation(true);
    }
  };
  tick();
  state.simulationTimer = window.setInterval(tick, 1000);
}

async function submitSimulation(autoSubmit = false) {
  const simulation = state.currentSimulation;
  if (!simulation || simulation.status === "finished") return;
  if (!autoSubmit && !window.confirm("提交后将结束本套模拟考，并把结果写入学习记录。确定提交吗？")) return;
  const answers = {};
  const selfGrades = {};
  const attachmentIds = {};
  $$('[data-sim-answer]').forEach((field) => { answers[field.dataset.simAnswer] = field.value; });
  $$('[data-sim-grade]').forEach((field) => { if (field.value !== "") selfGrades[field.dataset.simGrade] = Number(field.value); });
  const button = $("submit-simulation");
  if (button) button.disabled = true;
  try {
    for (const input of $$('[data-sim-image]')) {
      const file = input.files?.[0];
      if (!file) continue;
      const status = $$('[data-sim-image-status]').find((item) => item.dataset.simImageStatus === input.dataset.simImage);
      if (status) status.textContent = "正在上传图片……";
      const uploaded = await uploadAnswerImage(file, input.dataset.simImage);
      attachmentIds[input.dataset.simImage] = [uploaded.attachment_id];
    }
    await collectHandwritingAttachments($("simulation-container"), attachmentIds);
    state.currentSimulation = await fetchJSON(`/api/simulations/${encodeURIComponent(simulation.id)}/submit`, jsonOptions({ user_id: state.userId, answers, self_grades: selfGrades, attachment_ids: attachmentIds }));
    saveSimulationPointer(state.currentSimulation.id);
    localStorage.removeItem(simulationDraftKey(simulation.id));
    clearHandwritingDrafts($("simulation-container"));
    window.clearInterval(state.simulationTimer);
    renderSimulation();
    await refreshLearningData();
    showToast(`模拟考完成：${formatScore(state.currentSimulation.score)} / ${formatScore(state.currentSimulation.max_score)} 分。`);
  } catch (error) {
    showToast(`提交模拟考失败：${error.message}`, true);
    if (button) button.disabled = false;
  }
}

async function loadSettings() {
  try {
    const [accountSettings, modelSettings, serverSettings] = await Promise.all([
      fetchJSON("/api/settings"),
      fetchJSON("/api/llm/settings"),
      fetchJSON("/api/server/settings"),
    ]);
    state.accountSettings = accountSettings;
    state.settings = modelSettings;
    state.serverSettings = serverSettings;
    renderAccountSettings();
    renderSettingsValues();
    renderServerSettingsValues();
    renderModelStatus();
  } catch (error) {
    $("profile-settings-status").textContent = `读取账户设置失败：${error.message}`;
    $("settings-status").textContent = `读取模型配置失败：${error.message}`;
    $("settings-status").classList.add("error");
    $("server-settings-status").textContent = `读取服务配置失败：${error.message}`;
    $("server-settings-status").classList.add("error");
  }
}

function renderSettingsValues() {
  if (!state.settings) return;
  $("base-url").value = state.settings.base_url || "";
  $("api-key").value = "";
  const model = state.settings.model || "";
  const select = $("model-select");
  if (model && ![...select.options].some((option) => option.value === model)) select.insertAdjacentHTML("beforeend", `<option value="${escapeAttr(model)}">${escapeHtml(model)}（已保存）</option>`);
  select.value = model;
  $("model-manual").value = model;
}

function renderModelStatus() {
  const configured = Boolean(state.settings?.base_url && state.settings?.model);
  const dot = $("model-status-dot");
  dot.classList.toggle("connected", configured);
  const badge = $("connection-badge");
  if (!badge) return;
  badge.classList.toggle("connected", configured);
  badge.innerHTML = `<span></span>${configured ? `已保存 · ${escapeHtml(state.settings.model)}` : "未配置"}`;
}

function renderServerSettingsValues() {
  const settings = state.serverSettings;
  if (!settings) return;
  $("server-host").value = settings.host || "127.0.0.1";
  $("server-port").value = settings.port || 8000;
  $("server-public-url").value = settings.public_url || "";
  $("server-binding-mode").textContent = `⌁ ${settings.binding_mode || "服务"}`;
  $("server-launch-command").textContent = settings.launch_command || "python scripts/run_server.py";
  const access = settings.public_url || settings.browser_url || settings.access_url || `http://${settings.host}:${settings.port}`;
  const bindNote = settings.network_exposure_warning
    ? "当前监听地址允许网络设备连接。局域网使用本机 IP；公网请先配置防火墙、HTTPS 和认证。"
    : "当前只监听本机，其他设备无法访问。保存后请用启动脚本重启服务。";
  $("server-access-note").innerHTML = `<strong>访问提示：</strong>${escapeHtml(bindNote)}<br /><span>展示地址：${escapeHtml(access)}</span>`;
  const canEdit = state.user?.role === "admin";
  const form = $("server-settings-form");
  form?.classList.toggle("is-readonly", !canEdit);
  form?.querySelectorAll("input, button[type=submit]").forEach((control) => { control.disabled = !canEdit; });
  const permission = $("server-settings-permission");
  if (permission) permission.textContent = canEdit ? "管理员可修改监听配置；保存后需要重启服务。" : "当前账户只能查看服务配置，修改权限属于管理员。";
}

async function fetchModelsFromForm() {
  const button = $("fetch-models");
  const status = $("fetch-model-status");
  button.disabled = true;
  status.textContent = "正在连接……";
  try {
    const payload = await fetchJSON("/api/llm/models", jsonOptions({ base_url: $("base-url").value || null, api_key: $("api-key").value || null }));
    const models = payload.models || [];
    const select = $("model-select");
    const current = $("model-manual").value || select.value;
    select.innerHTML = models.length ? models.map((model) => `<option value="${escapeAttr(model.id)}">${escapeHtml(model.id)}</option>`).join("") : `<option value="">接口返回 0 个模型</option>`;
    if (current && models.some((model) => model.id === current)) select.value = current;
    $("model-manual").value = select.value || current || "";
    status.textContent = `已拉取 ${models.length} 个模型`;
    showToast(models.length ? `模型列表已更新，共 ${models.length} 个。` : "接口可连接，但没有返回模型。", !models.length);
  } catch (error) {
    status.textContent = `拉取失败：${error.message}`;
    showToast(`拉取模型失败：${error.message}`, true);
  } finally {
    button.disabled = false;
  }
}

async function saveModelSettings(event) {
  event.preventDefault();
  const status = $("settings-status");
  status.classList.remove("error");
  status.textContent = "正在保存……";
  try {
    state.settings = await fetchJSON("/api/llm/settings", jsonOptions({
      base_url: $("base-url").value,
      model: $("model-manual").value || $("model-select").value,
      api_key: $("api-key").value || null,
      clear_api_key: false,
    }));
    $("api-key").value = "";
    status.textContent = `已保存。${state.settings.api_key_set ? `密钥 ${state.settings.api_key_masked}` : "当前未设置 API Key（本地服务可用）"}`;
    renderModelStatus();
    showToast("模型配置已保存到本机。");
  } catch (error) {
    status.textContent = `保存失败：${error.message}`;
    status.classList.add("error");
  }
}

async function clearApiKey() {
  try {
    state.settings = await fetchJSON("/api/llm/settings", jsonOptions({ base_url: $("base-url").value, model: $("model-manual").value || $("model-select").value, api_key: null, clear_api_key: true }));
    $("api-key").value = "";
    $("settings-status").textContent = "本机保存的 API Key 已清除。";
    renderModelStatus();
    showToast("API Key 已从本机配置中清除。");
  } catch (error) {
    $("settings-status").textContent = `清除失败：${error.message}`;
    $("settings-status").classList.add("error");
  }
}

async function saveServerSettings(event) {
  event.preventDefault();
  const status = $("server-settings-status");
  status.classList.remove("error");
  status.textContent = "正在保存……";
  try {
    state.serverSettings = await fetchJSON("/api/server/settings", jsonOptions({
      host: $("server-host").value,
      port: Number($("server-port").value),
      public_url: $("server-public-url").value,
    }));
    renderServerSettingsValues();
    status.textContent = "已保存。请停止当前服务，再用上方启动命令重启后生效。";
    showToast("后端服务设置已保存，重启后生效。");
  } catch (error) {
    status.textContent = `保存失败：${error.message}`;
    status.classList.add("error");
  }
}

async function copyServerCommand() {
  const command = $("server-launch-command").textContent.trim();
  try {
    await navigator.clipboard.writeText(command);
    showToast("启动命令已复制。", false);
  } catch {
    showToast(`无法自动复制，请手动复制：${command}`, true);
  }
}

function renderAccountSettings() {
  const account = state.accountSettings || {};
  const profile = account.profile || state.user || {};
  const preferences = account.preferences || {};
  $("account-username") && ($("account-username").value = profile.username || "");
  $("account-email") && ($("account-email").value = profile.email || "");
  $("account-display-name") && ($("account-display-name").value = profile.display_name || profile.username || "");
  $("account-theme") && ($("account-theme").value = preferences.theme || "system");
  $("account-daily-goal") && ($("account-daily-goal").value = preferences.daily_goal ?? 30);
  $("account-practice-count") && ($("account-practice-count").value = preferences.practice_count ?? 15);
  $("account-exam-type") && ($("account-exam-type").value = preferences.default_exam_type || "数学二");
  $("account-sound-enabled") && ($("account-sound-enabled").checked = Boolean(preferences.sound_enabled));
  const sessions = account.sessions || [];
  const sessionRoot = $("account-sessions-list");
  if (sessionRoot) sessionRoot.innerHTML = sessions.length
    ? `<div class="sessions-heading"><strong>登录设备</strong><span>${sessions.length} 个有效会话</span></div>${sessions.map((session) => `<div class="account-session-row ${session.current ? "current" : ""}"><span class="session-device">${escapeHtml(session.user_agent || "未知设备")}</span><span>${escapeHtml(session.ip_address || "本机")} · ${escapeHtml(formatDateTime(session.last_seen_at))}</span>${session.current ? `<b>当前设备</b>` : ""}</div>`).join("")}`
    : `<span class="muted-copy">暂无有效登录设备。</span>`;
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

async function saveProfileSettings(event) {
  event.preventDefault();
  const status = $("profile-settings-status");
  status.textContent = "正在保存……";
  status.classList.remove("error");
  try {
    const payload = await fetchJSON("/api/settings/profile", { ...jsonOptions({ display_name: $("account-display-name").value, email: $("account-email").value }), method: "PATCH" });
    state.user = { ...state.user, ...payload.profile };
    state.accountSettings = { ...(state.accountSettings || {}), profile: state.user };
    renderAuthenticatedUser();
    status.textContent = "已保存";
    showToast("账户资料已保存。");
  } catch (error) {
    status.textContent = `保存失败：${error.message}`;
    status.classList.add("error");
  }
}

async function savePreferencesSettings(event) {
  event.preventDefault();
  const status = $("preferences-settings-status");
  status.textContent = "正在保存……";
  status.classList.remove("error");
  try {
    const preferences = {
      theme: $("account-theme").value,
      default_exam_type: $("account-exam-type").value,
      daily_goal: Number($("account-daily-goal").value),
      practice_count: Number($("account-practice-count").value),
      sound_enabled: $("account-sound-enabled").checked,
    };
    const payload = await fetchJSON("/api/settings/preferences", { ...jsonOptions(preferences), method: "PATCH" });
    state.accountSettings = { ...(state.accountSettings || {}), preferences: payload.preferences };
    state.user = { ...state.user, preferences: payload.preferences };
    applyAccountTheme(payload.preferences.theme);
    status.textContent = "已保存";
    showToast("学习偏好已保存。");
  } catch (error) {
    status.textContent = `保存失败：${error.message}`;
    status.classList.add("error");
  }
}

async function savePasswordSettings(event) {
  event.preventDefault();
  const status = $("password-settings-status");
  status.textContent = "正在更新……";
  status.classList.remove("error");
  try {
    await fetchJSON("/api/auth/change-password", jsonOptions({ current_password: $("current-password").value, new_password: $("new-password").value }));
    $("current-password").value = "";
    $("new-password").value = "";
    status.textContent = "密码已更新，请重新登录。";
    showAuthScreen("密码已更新，请使用新密码登录。");
  } catch (error) {
    status.textContent = `更新失败：${error.message}`;
    status.classList.add("error");
  }
}

async function revokeOtherSessions() {
  const status = $("password-settings-status");
  try {
    const result = await fetchJSON("/api/auth/sessions/revoke-others", jsonOptions({}));
    status.textContent = `已退出 ${result.revoked || 0} 个其他设备。`;
    await loadSettings();
  } catch (error) {
    status.textContent = `操作失败：${error.message}`;
    status.classList.add("error");
  }
}

const authActionLabels = {
  register: "注册账户",
  login: "登录成功",
  "login-failed": "登录失败",
  logout: "退出登录",
  "password-changed": "修改密码",
  "admin-user-updated": "管理员更新账户",
  "admin-sessions-revoked": "管理员撤销会话",
  "legacy-data-migrated": "迁移旧数据",
};

function applyAdminFilters() {
  const userFilters = state.adminUserFilters || {};
  const userSearch = String(userFilters.search || "").trim().toLocaleLowerCase();
  state.adminUsers = (state.adminUsersAll || []).filter((user) => {
    const haystack = [user.username, user.email, user.display_name].join(" ").toLocaleLowerCase();
    const matchesSearch = !userSearch || haystack.includes(userSearch);
    const matchesRole = !userFilters.role || user.role === userFilters.role;
    const matchesStatus = !userFilters.status || (userFilters.status === "active" ? user.is_active : !user.is_active);
    return matchesSearch && matchesRole && matchesStatus;
  });

  const auditFilters = state.adminAuditFilters || {};
  const auditSearch = String(auditFilters.search || "").trim().toLocaleLowerCase();
  state.adminAudit = (state.adminAuditAll || []).filter((event) => {
    const matchesAction = !auditFilters.action || event.action === auditFilters.action;
    const haystack = [event.action, event.actor_username, event.user_username, event.target_username, event.ip_address, event.detail]
      .join(" ")
      .toLocaleLowerCase();
    return matchesAction && (!auditSearch || haystack.includes(auditSearch));
  });
  renderAdminUsers();
  renderAdminAudit();
}

function syncAdminAuditActions() {
  const select = $("admin-audit-action");
  if (!select) return;
  const current = state.adminAuditFilters?.action || "";
  const actions = [...new Set((state.adminAuditAll || []).map((event) => event.action).filter(Boolean))].sort();
  select.innerHTML = `<option value="">全部事件</option>${actions.map((action) => `<option value="${escapeAttr(action)}">${escapeHtml(authActionLabels[action] || action)}</option>`).join("")}`;
  select.value = actions.includes(current) ? current : "";
  if (!actions.includes(current)) state.adminAuditFilters.action = "";
}

function renderAdminUsers() {
  const root = $("admin-users-table");
  if (!root) return;
  const users = state.adminUsers || [];
  const total = (state.adminUsersAll || []).length;
  const resultCount = $("admin-user-result-count");
  if (resultCount) resultCount.textContent = `${users.length} / ${total} 个账户`;
  root.innerHTML = users.length
    ? `<div class="admin-user-head"><span>账户</span><span>角色与状态</span><span>操作</span></div>${users.map((user) => { const sessionCount = Number(user.active_session_count || 0); const isCurrent = user.id === state.userId; return `<article class="admin-user-row" data-admin-user="${escapeAttr(user.id)}"><div class="admin-user-identity"><div class="admin-user-name-line"><strong>${escapeHtml(user.display_name || user.username)}</strong><span class="admin-state-chip ${user.is_active ? "is-active" : "is-inactive"}">${user.is_active ? "已启用" : "已停用"}</span></div><span>@${escapeHtml(user.username)}${user.email ? ` · ${escapeHtml(user.email)}` : ""}</span><small>注册于 ${escapeHtml(formatDateTime(user.created_at))}${user.last_login_at ? ` · 最近登录 ${escapeHtml(formatDateTime(user.last_login_at))}` : ""}</small><small>${Number(user.attempt_count || 0)} 次作答 · ${Number(user.note_count || 0)} 条笔记 · ${sessionCount} 个活跃会话</small></div><div class="admin-user-controls"><label>角色<select data-admin-role ${isCurrent ? "disabled" : ""}><option value="user" ${user.role === "user" ? "selected" : ""}>普通用户</option><option value="admin" ${user.role === "admin" ? "selected" : ""}>管理员</option></select></label><label class="admin-active-toggle"><input type="checkbox" data-admin-active ${user.is_active ? "checked" : ""} ${isCurrent ? "disabled" : ""} />启用</label></div><div class="admin-user-actions"><input type="text" data-admin-display value="${escapeAttr(user.display_name || user.username)}" maxlength="80" aria-label="${escapeAttr(user.username)} 显示名称" /><div class="admin-user-action-buttons"><button type="button" class="secondary-button" data-admin-save>保存</button><button type="button" class="secondary-button admin-revoke-button" data-admin-revoke-sessions ${isCurrent || sessionCount === 0 ? "disabled" : ""} title="${isCurrent ? "不能撤销当前管理员会话" : sessionCount ? `撤销 ${sessionCount} 个活跃会话` : "没有可撤销的会话"}">撤销会话</button></div><span class="form-status" data-admin-status></span></div></article>`; }).join("")}`
    : `<div class="empty-state compact-empty"><h3>${total ? "没有匹配账户" : "暂无账户"}</h3><p>${total ? "调整搜索条件或筛选器后重试。" : "注册后账户会显示在这里。"}</p></div>`;
}

function renderAdminAudit() {
  const root = $("admin-audit-list");
  if (!root) return;
  const events = state.adminAudit || [];
  const resultCount = $("admin-audit-result-count");
  if (resultCount) resultCount.textContent = `${events.length} / ${(state.adminAuditAll || []).length} 条事件`;
  root.innerHTML = events.length
    ? events.map((event) => `<article class="admin-audit-row"><div><strong>${escapeHtml(authActionLabels[event.action] || event.action)}</strong><span>${escapeHtml(event.actor_username || event.user_username || "系统")}${event.target_username ? ` → ${escapeHtml(event.target_username)}` : ""}</span></div><time>${escapeHtml(formatDateTime(event.created_at))}</time><small>${escapeHtml(event.detail || event.ip_address || "")}</small></article>`).join("")
    : `<div class="empty-state compact-empty"><h3>${(state.adminAuditAll || []).length ? "没有匹配事件" : "暂无安全事件"}</h3><p>${(state.adminAuditAll || []).length ? "调整事件类型或搜索词后重试。" : "登录、注册和权限变更会记录在这里。"}</p></div>`;
}

async function loadAdmin() {
  if (state.user?.role !== "admin") return;
  try {
    const [overview, users, audit] = await Promise.all([
      fetchJSON("/api/admin/overview"),
      fetchJSON("/api/admin/users"),
      fetchJSON("/api/admin/audit?limit=200"),
    ]);
    $("admin-users-count").textContent = overview.users ?? "—";
    $("admin-active-users-count").textContent = overview.active_users ?? "—";
    $("admin-admins-count").textContent = overview.admins ?? "—";
    $("admin-sessions-count").textContent = overview.active_sessions ?? "—";
    $("admin-attempts-count").textContent = overview.attempts ?? "—";
    $("admin-audit-count").textContent = overview.audit_events ?? audit.items?.length ?? "—";
    state.adminUsersAll = users.items || [];
    state.adminAuditAll = audit.items || [];
    syncAdminAuditActions();
    applyAdminFilters();
  } catch (error) {
    $("admin-users-table").innerHTML = `<div class="loading-card">读取管理数据失败：${escapeHtml(error.message)}</div>`;
    $("admin-audit-list").innerHTML = `<div class="loading-card">读取安全事件失败：${escapeHtml(error.message)}</div>`;
  }
}

async function updateAdminUser(row) {
  const target = row?.dataset.adminUser;
  if (!target) return;
  const button = row.querySelector("[data-admin-save]");
  const status = row.querySelector("[data-admin-status]");
  if (button) { button.disabled = true; button.setAttribute("aria-busy", "true"); }
  if (status) { status.textContent = "保存中……"; status.classList.remove("error"); }
  try {
    const payload = {
      role: row.querySelector("[data-admin-role]")?.value || "user",
      is_active: Boolean(row.querySelector("[data-admin-active]")?.checked),
      display_name: row.querySelector("[data-admin-display]")?.value || "",
    };
    await fetchJSON(`/api/admin/users/${encodeURIComponent(target)}`, { ...jsonOptions(payload), method: "PATCH" });
    if (status) status.textContent = "已保存";
    await loadAdmin();
  } catch (error) {
    if (status) { status.textContent = `失败：${error.message}`; status.classList.add("error"); }
  } finally {
    if (button) { button.disabled = false; button.removeAttribute("aria-busy"); }
  }
}

async function revokeAdminUserSessions(row) {
  const target = row?.dataset.adminUser;
  if (!target) return;
  const user = (state.adminUsersAll || []).find((item) => item.id === target);
  if (!user || user.id === state.userId) return;
  const sessionCount = Number(user.active_session_count || 0);
  if (!sessionCount || !window.confirm(`确定撤销 ${user.display_name || user.username} 的 ${sessionCount} 个活跃会话吗？该账户需要重新登录。`)) return;
  const button = row.querySelector("[data-admin-revoke-sessions]");
  const status = row.querySelector("[data-admin-status]");
  if (button) { button.disabled = true; button.setAttribute("aria-busy", "true"); }
  if (status) { status.textContent = "撤销中……"; status.classList.remove("error"); }
  try {
    const result = await fetchJSON(`/api/admin/users/${encodeURIComponent(target)}/sessions/revoke`, { ...jsonOptions({}), method: "POST" });
    showToast(`已撤销 ${result.revoked || 0} 个会话。`);
    await loadAdmin();
  } catch (error) {
    if (status) { status.textContent = `失败：${error.message}`; status.classList.add("error"); }
  } finally {
    if (button) { button.disabled = false; button.removeAttribute("aria-busy"); }
  }
}

function exportAdminAudit() {
  const events = state.adminAudit || [];
  if (!events.length) { showToast("当前筛选没有可导出的安全事件。", true); return; }
  const csvCell = (value) => {
    let text = String(value ?? "").replace(/\r?\n/g, " ");
    if (/^[-=+@]/.test(text)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  };
  const header = ["时间", "事件", "操作者", "目标账户", "IP", "详情"];
  const rows = events.map((event) => [event.created_at, authActionLabels[event.action] || event.action, event.actor_username || event.user_username || "系统", event.target_username || "", event.ip_address || "", event.detail || ""]);
  const csv = "\ufeff" + [header, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `ai-math-security-log-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  showToast(`已导出 ${events.length} 条安全事件。`);
}

function bindAdminControls() {
  $("admin-users-table")?.addEventListener("click", (event) => {
    const row = event.target.closest?.("[data-admin-user]");
    const saveButton = event.target.closest?.("[data-admin-save]");
    const revokeButton = event.target.closest?.("[data-admin-revoke-sessions]");
    if (saveButton && row) updateAdminUser(row);
    if (revokeButton && row) revokeAdminUserSessions(row);
  });
  $("admin-user-search")?.addEventListener("input", (event) => { state.adminUserFilters.search = event.target.value; applyAdminFilters(); });
  $("admin-user-role-filter")?.addEventListener("change", (event) => { state.adminUserFilters.role = event.target.value; applyAdminFilters(); });
  $("admin-user-status-filter")?.addEventListener("change", (event) => { state.adminUserFilters.status = event.target.value; applyAdminFilters(); });
  $("admin-audit-search")?.addEventListener("input", (event) => { state.adminAuditFilters.search = event.target.value; applyAdminFilters(); });
  $("admin-audit-action")?.addEventListener("change", (event) => { state.adminAuditFilters.action = event.target.value; applyAdminFilters(); });
  $("admin-audit-export")?.addEventListener("click", exportAdminAudit);
}

function bindAuthControls() {
  $("auth-switch")?.addEventListener("click", () => setAuthMode(state.authMode === "login" ? "register" : "login"));
  $("auth-retry")?.addEventListener("click", retryAuthConnection);
  $$('[data-password-toggle]').forEach((button) => button.addEventListener("click", () => {
    const input = $(button.dataset.target || "");
    if (!input) return;
    const visible = input.type === "text";
    input.type = visible ? "password" : "text";
    const secretName = button.dataset.secretName || "密码";
    const nextLabel = `${visible ? "显示" : "隐藏"}${secretName}`;
    button.setAttribute("aria-pressed", String(!visible));
    button.setAttribute("aria-label", nextLabel);
    button.setAttribute("title", nextLabel);
    const srLabel = button.querySelector(".sr-only");
    if (srLabel) srLabel.textContent = nextLabel;
    input.focus({ preventScroll: true });
  }));
  $("login-form")?.addEventListener("submit", submitAuthForm);
  $("register-form")?.addEventListener("submit", submitAuthForm);
  setAuthMode("login");
}

function bindAccountSettingsControls() {
  $("profile-settings-form")?.addEventListener("submit", saveProfileSettings);
  $("preferences-settings-form")?.addEventListener("submit", savePreferencesSettings);
  $("password-settings-form")?.addEventListener("submit", savePasswordSettings);
  $("revoke-other-sessions")?.addEventListener("click", revokeOtherSessions);
}

function handleClientBootFailure(error) {
  // A missing favicon or a slow optional font should not turn into an auth
  // error. Only handle script/runtime failures; resource error events have a
  // DOM target but no Error object.
  if (error?.target && error.target !== window && !error.error) return;
  const message = String(error?.reason?.message || error?.error?.message || error?.message || "");
  console.error("AI Math client error", error?.reason || error?.error || error);
  if (!state.authenticated && $("auth-screen")?.hasAttribute("hidden")) {
    showAuthScreen("界面加载失败，请刷新页面或重新启动本地服务。", { connection: true });
    if ($("auth-connection-copy")) $("auth-connection-copy").textContent = "页面脚本未能完成初始化，请重试。";
    return;
  }
  const notice = $("app-notice");
  if (notice) {
    notice.textContent = "页面遇到一个可恢复的问题，请刷新当前页面后重试。";
    notice.classList.add("show");
  }
}

async function init() {
  $("today-date").textContent = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(new Date());
  bindAuthControls();
  bindNoteEditor();
  bindWorkbenchControls();
  $$(".nav-item[data-view]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.view)));
  $$('[data-view-target]').forEach((button) => button.addEventListener("click", () => navigate(button.dataset.viewTarget)));
  $("refresh-button").addEventListener("click", refreshCurrentView);
  $("start-recommended").addEventListener("click", () => state.nextQuestions[0] ? openQuestion(state.nextQuestions[0].id) : navigate("library"));
  $("apply-filters").addEventListener("click", loadLibrary);
  $("filter-concept")?.addEventListener("change", populateSubtypeFilter);
  $("create-simulation").addEventListener("click", createSimulation);
  $("submit-answer").addEventListener("click", submitAnswer);
  $("answer-image-input").addEventListener("change", () => showImagePreview($("answer-image-input").files?.[0], $("answer-image-preview"), $("answer-image-status")));
  $("ask-tutor").addEventListener("click", askTutor);
  $("close-question-modal").addEventListener("click", closeQuestion);
  $("question-modal").addEventListener("click", (event) => { if (event.target === $("question-modal")) closeQuestion(); });
  $("fetch-models").addEventListener("click", fetchModelsFromForm);
  $("model-settings-form").addEventListener("submit", saveModelSettings);
  $("server-settings-form").addEventListener("submit", saveServerSettings);
  $("copy-server-command").addEventListener("click", copyServerCommand);
  $("clear-key").addEventListener("click", clearApiKey);
  $("logout-button")?.addEventListener("click", logout);
  bindAccountSettingsControls();
  bindAdminControls();
  $("model-select").addEventListener("change", () => { $("model-manual").value = $("model-select").value; });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeQuestion(); });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s" && state.view === "workbench" && state.currentNote) {
      event.preventDefault();
      saveWorkbenchNote();
    }
  });
  document.addEventListener("click", (event) => {
    if (event.target.id === "submit-simulation") submitSimulation(false);
    if (event.target.id === "cancel-simulation") cancelSimulation();
  });
  if (!(await bootstrapAuth())) return;
  applyWorkbenchTheme();
  await loadOverview();
}

window.addEventListener("beforeunload", handleSimulationBeforeUnload);
window.addEventListener("error", handleClientBootFailure);
window.addEventListener("unhandledrejection", handleClientBootFailure);
window.addEventListener("DOMContentLoaded", init);

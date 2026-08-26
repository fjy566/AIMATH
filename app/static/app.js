const state = {
  view: "overview",
  userId: "local-user",
  stats: null,
  progress: null,
  forecast: null,
  blocks: [],
  nextQuestions: [],
  concepts: [],
  exams: [],
  settings: null,
  currentQuestion: null,
  practiceSession: null,
  currentSimulation: null,
  simulationTimer: null,
  simulationDeadline: null,
  libraryLoaded: false,
};

const viewMeta = {
  overview: ["STUDY DESK / OVERVIEW", "今天，把薄弱处练成得分点"],
  library: ["ARCHIVE / REAL QUESTIONS", "真题库"],
  blocks: ["ADAPTIVE PRACTICE / BLOC TRAINING", "分块训练"],
  simulation: ["FULL PAPER / TIMED PRACTICE", "模拟考"],
  settings: ["MODEL GATEWAY / OPENAI COMPATIBLE", "模型设置"],
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

function renderMarkdown(source) {
  let text = String(source || "").replace(/\r/g, "");
  const formulas = [];
  const formulaPattern = /\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^$\n]+\$/g;
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
    }
    const token = `MATHTOKEN${formulas.length}END`;
    formulas.push({ token, display, tex });
    return token;
  });

  const inline = (line) => {
    let html = escapeHtml(line);
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    for (const formula of formulas) {
      const math = renderFormula(formula.tex, formula.display);
      html = html.replaceAll(formula.token, math);
    }
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
  const source = String(tex || "").trim();
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
      { label: "根号", symbol: "√x", tex: "\\sqrt{x}", select: "x", title: "插入根号" },
      { label: "次方", symbol: "xⁿ", tex: "x^{n}", select: "n", title: "插入次方" },
      { label: "下标", symbol: "xᵢ", tex: "x_{i}", select: "i", title: "插入下标" },
      { label: "括号", symbol: "( )", tex: "\\left( x \\right)", select: "x", title: "插入括号" },
      { label: "矩阵", symbol: "▦", tex: "\\begin{pmatrix}a&b\\\\c&d\\end{pmatrix}", select: "a", wrap: "display", title: "插入二阶矩阵" },
    ],
  },
  {
    label: "微积分",
    items: [
      { label: "导数", symbol: "dy/dx", tex: "\\frac{dy}{dx}", select: "dy", title: "插入一阶导数" },
      { label: "偏导", symbol: "∂f/∂x", tex: "\\frac{\\partial f}{\\partial x}", select: "f", title: "插入偏导数" },
      { label: "积分", symbol: "∫", tex: "\\int_{a}^{b} f(x)\\,dx", select: "a", wrap: "display", title: "插入定积分" },
      { label: "二重积分", symbol: "∬", tex: "\\iint_{D} f(x,y)\\,dA", select: "D", wrap: "display", title: "插入二重积分" },
      { label: "极限", symbol: "lim", tex: "\\lim_{x\\to a} f(x)", select: "x\\to a", wrap: "display", title: "插入极限" },
      { label: "求和", symbol: "Σ", tex: "\\sum_{i=1}^{n} a_i", select: "i=1", wrap: "display", title: "插入求和" },
    ],
  },
  {
    label: "常用函数和符号",
    items: [
      { label: "正弦", symbol: "sin", tex: "\\sin x", select: "x", title: "插入正弦函数" },
      { label: "余弦", symbol: "cos", tex: "\\cos x", select: "x", title: "插入余弦函数" },
      { label: "自然对数", symbol: "ln", tex: "\\ln x", select: "x", title: "插入自然对数" },
      { label: "指数", symbol: "eˣ", tex: "e^{x}", select: "x", title: "插入指数函数" },
      { label: "绝对值", symbol: "|x|", tex: "\\left|x\\right|", select: "x", title: "插入绝对值" },
      { label: "无穷大", symbol: "∞", tex: "\\infty", title: "插入无穷大" },
      { label: "趋于", symbol: "→", tex: "\\to", title: "插入趋于符号" },
      { label: "不等式", symbol: "≤ ≥", tex: "a \\le b", select: "a", title: "插入小于等于不等式" },
    ],
  },
];

const FORMULA_TOOL_GROUPS = [
  {
    label: "结构",
    items: [
      { label: "分数", tex: "\\frac{a}{b}", select: "a", title: "插入分数" },
      { label: "根式", tex: "\\sqrt{x}", select: "x", title: "插入平方根" },
      { label: "幂", tex: "x^{n}", select: "n", title: "插入幂" },
      { label: "下标", tex: "x_{i}", select: "i", title: "插入下标" },
      { label: "绝对值", tex: "\\left|x\\right|", select: "x", title: "插入绝对值" },
      { label: "矩阵", tex: "\\begin{pmatrix}a&b\\\\c&d\\end{pmatrix}", select: "a", wrap: "display", title: "插入二阶矩阵" },
    ],
  },
  {
    label: "微积分",
    items: [
      { label: "积分", tex: "\\int_{a}^{b} f(x)\\,dx", select: "a", wrap: "display", title: "插入定积分" },
      { label: "二重积分", tex: "\\iint_{D} f(x,y)\\,dA", select: "D", wrap: "display", title: "插入二重积分" },
      { label: "求和", tex: "\\sum_{i=1}^{n} a_i", select: "i=1", wrap: "display", title: "插入求和" },
      { label: "极限", tex: "\\lim_{x\\to a} f(x)", select: "x\\to a", wrap: "display", title: "插入极限" },
      { label: "导数", tex: "\\frac{dy}{dx}", select: "dy", title: "插入一阶导数" },
      { label: "偏导", tex: "\\frac{\\partial f}{\\partial x}", select: "f", title: "插入偏导数" },
    ],
  },
  {
    label: "常用符号",
    items: [
      { label: "α", tex: "\\alpha", title: "希腊字母 alpha" },
      { label: "β", tex: "\\beta", title: "希腊字母 beta" },
      { label: "γ", tex: "\\gamma", title: "希腊字母 gamma" },
      { label: "λ", tex: "\\lambda", title: "希腊字母 lambda" },
      { label: "∞", tex: "\\infty", title: "无穷大" },
      { label: "→", tex: "\\to", title: "趋于" },
      { label: "≤", tex: "\\le", title: "小于等于" },
      { label: "≥", tex: "\\ge", title: "大于等于" },
      { label: "≠", tex: "\\ne", title: "不等于" },
      { label: "±", tex: "\\pm", title: "正负号" },
      { label: "·", tex: "\\cdot", title: "乘号" },
      { label: "∈", tex: "\\in", title: "属于" },
    ],
  },
  {
    label: "函数",
    items: [
      { label: "sin", tex: "\\sin x", select: "x", title: "正弦函数" },
      { label: "cos", tex: "\\cos x", select: "x", title: "余弦函数" },
      { label: "ln", tex: "\\ln x", select: "x", title: "自然对数" },
      { label: "eˣ", tex: "e^{x}", select: "x", title: "指数函数" },
      { label: "f′", tex: "f'(x)", select: "f", title: "函数导数" },
      { label: "向量", tex: "\\vec{a}", select: "a", title: "向量记号" },
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

function formulaToolMarkup(item, className = "formula-tool", beginner = false) {
  const content = beginner
    ? `<span class="formula-tool-glyph">${escapeHtml(item.symbol || item.label)}</span><span class="formula-tool-caption">${escapeHtml(item.label)}</span>`
    : `<span>${escapeHtml(item.label)}</span>`;
  return `<button type="button" class="${className}" data-formula-tool data-formula-tex="${escapeAttr(item.tex)}" data-formula-select="${escapeAttr(item.select || "")}" data-formula-wrap="${escapeAttr(item.wrap || "inline")}" title="${escapeAttr(item.title || item.label)}">${content}</button>`;
}

function formulaGroupsMarkup(groups, beginner = false) {
  const groupClass = beginner ? "formula-beginner-group" : "formula-tool-group";
  const listClass = beginner ? "formula-beginner-list" : "formula-tool-list";
  const buttonClass = beginner ? "formula-tool beginner-formula-tool" : "formula-tool";
  return groups.map((group) => `<div class="${groupClass}"><span class="formula-group-label">${escapeHtml(group.label)}</span><div class="${listClass}">${group.items.map((item) => formulaToolMarkup(item, buttonClass, beginner)).join("")}</div></div>`).join("");
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

function formulaToolbarMarkup(editorId, readonly = false, questionType = "fill") {
  if (readonly) return `<p class="formula-readonly-note">本题已提交。可查看公式，但不能修改。</p>`;
  return `<div class="answer-toolbox">
    <div class="answer-tool-row">
      <span class="answer-tool-prompt">不懂 LaTeX 也没关系，直接点你想要的公式</span>
      <div class="answer-tool-actions">
        <button type="button" class="answer-tool-toggle" data-formula-toggle aria-expanded="false" aria-controls="${escapeAttr(editorId)}-formula-tools"><span>Σ</span> 公式工具</button>
        ${questionType === "solution" ? `<button type="button" class="answer-tool-toggle" data-answer-structure-toggle aria-expanded="false" aria-controls="${escapeAttr(editorId)}-answer-structure"><span>☷</span> 作答结构</button>` : ""}
      </div>
    </div>
    <div class="formula-tools-panel" id="${escapeAttr(editorId)}-formula-tools" data-formula-tools-panel hidden>
      <div class="formula-beginner-head"><strong>直接插入常用公式</strong><span>插入后可以继续修改字母和数字</span></div>
      <div class="formula-beginner-groups">${formulaGroupsMarkup(BEGINNER_FORMULA_GROUPS, true)}</div>
      <div class="formula-advanced-toggle-row"><button type="button" class="formula-advanced-toggle" data-formula-advanced-toggle aria-expanded="false">显示高级 LaTeX 工具 <span>适合熟悉公式写法后使用</span></button></div>
      <div class="formula-advanced-panel" data-formula-advanced-panel hidden><div class="formula-toolbar" data-formula-toolbar="${escapeAttr(editorId)}" role="toolbar" aria-label="高级 LaTeX 公式工具">${formulaGroupsMarkup(FORMULA_TOOL_GROUPS)}</div><p class="formula-helper"><span>高级工具仍然插入模板，不会覆盖你已有的文字</span><span><kbd>$</kbd> 行内 · <kbd>$$</kbd> 行间 · <kbd>Ctrl</kbd> + <kbd>Enter</kbd> 提交</span></p></div>
    </div>
    ${answerStructureMarkup(editorId, questionType)}
  </div>`;
}

function renderFormulaEditor({ id, value = "", readonly = false, answerAttribute = "", label = "LaTeX 作答", placeholder = "先写文字，再用工具插入公式，例如：函数在区间上连续。", questionType = "fill" }) {
  const editorId = domId(id);
  const inputId = editorId === "modal-answer" ? "answer-input" : `${editorId}-input`;
  return `<div class="formula-editor" data-formula-editor="${escapeAttr(editorId)}">
    <div class="formula-editor-layout">
      <div class="formula-source-pane">
        <div class="formula-pane-head"><label for="${escapeAttr(inputId)}">${escapeHtml(label)}</label><span>文字和公式混合</span></div>
        <textarea id="${escapeAttr(inputId)}" ${answerAttribute} data-formula-input="${escapeAttr(editorId)}" rows="5" spellcheck="false" ${readonly ? "readonly" : ""} placeholder="${escapeAttr(placeholder)}">${escapeHtml(value)}</textarea>
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

function renderAnswerEditor(question, { mode = "modal", value = "", readonly = false } = {}) {
  const answerAttribute = mode === "practice"
    ? `data-practice-answer="${escapeAttr(question.id)}"`
    : mode === "simulation"
      ? `data-sim-answer="${escapeAttr(question.id)}"`
      : "";
  if (question.question_type === "choice") {
    return renderChoiceEditor({ question, value, readonly, answerAttribute, id: mode === "modal" ? "modal-choice" : `${mode}-choice-${question.id}` });
  }
  return renderFormulaEditor({
    id: mode === "modal" ? "modal-answer" : `${mode}-answer-${question.id}`,
    value,
    readonly,
    answerAttribute,
    label: question.question_type === "fill" ? "填写答案" : "我的解题过程",
    placeholder: question.question_type === "fill" ? "输入最终结果，点击工具插入分数、根式、积分等公式。" : "先写解题步骤，公式直接点工具插入，需要时再修改字母或数字。",
    questionType: question.question_type,
  });
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

function setDisclosure(button, panel, open) {
  if (!button || !panel) return;
  panel.hidden = !open;
  button.setAttribute("aria-expanded", String(open));
  button.classList.toggle("is-open", open);
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
    const field = editor.querySelector("[data-formula-input]");
    const preview = editor.querySelector("[data-formula-preview]");
    const update = () => {
      if (preview) preview.innerHTML = renderAnswerPreview(field.value);
      if (state.practiceSession) updatePracticeSessionStatus();
    };
    field?.addEventListener("input", update);
    $$('[data-formula-tool]', editor).forEach((button) => button.addEventListener("click", () => insertFormulaSnippet(field, button)));
    field?.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && editor.closest(".practice-session-shell")) {
        event.preventDefault();
        $("submit-practice-session")?.click();
      }
    });
    $$('[data-formula-toggle]', editor).forEach((button) => button.addEventListener("click", () => {
      setDisclosure(button, editor.querySelector("[data-formula-tools-panel]"), button.getAttribute("aria-expanded") !== "true");
    }));
    $$('[data-formula-advanced-toggle]', editor).forEach((button) => button.addEventListener("click", () => {
      setDisclosure(button, editor.querySelector("[data-formula-advanced-panel]"), button.getAttribute("aria-expanded") !== "true");
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
}

function typeLabel(type) {
  return { choice: "选择", fill: "填空", solution: "解答" }[type] || type || "题目";
}

function conceptName(id) {
  return state.concepts.find((concept) => concept.id === id)?.name || id;
}

function questionConceptLabels(question) {
  if (Array.isArray(question?.concept_labels) && question.concept_labels.length) return question.concept_labels;
  return (question?.concept_ids || []).map((id) => ({ id, name: conceptName(id), scope: "unknown", scope_label: "未标注范围" }));
}

function questionConceptMarkup(question) {
  return questionConceptLabels(question).map((concept) => `<span class="concept-label ${concept.scope === "out-of-syllabus" ? "out-of-syllabus" : ""}">${escapeHtml(concept.scope === "out-of-syllabus" ? `${concept.scope_label} · ${concept.name}` : concept.name)}</span>`).join("");
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

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) {
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

function navigate(view) {
  if (!viewMeta[view]) return;
  state.view = view;
  $$(".view").forEach((element) => element.classList.toggle("active", element.id === `view-${view}`));
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("view-kicker").textContent = viewMeta[view][0];
  $("view-title").textContent = viewMeta[view][1];
  if (view === "overview") loadOverview();
  if (view === "library") loadLibrary();
  if (view === "blocks") loadBlocks();
  if (view === "simulation") loadSimulationCatalog();
  if (view === "settings") loadSettings();
}

function renderOverview() {
  const stats = state.stats || {};
  const progress = state.progress || {};
  const forecast = state.forecast || {};
  $("metric-questions").textContent = stats.total_questions ?? "读取中";
  $("metric-attempts").textContent = progress.attempts ?? 0;
  $("metric-mastery").textContent = progress.overall_mastery == null ? "0%" : `${formatScore(progress.overall_mastery)}%`;
  $("metric-focus").textContent = state.blocks[0]?.concept?.name || "暂无";
  $("forecast-p50").innerHTML = forecast.available ? `${formatScore(forecast.p50)}<span> / ${formatScore(forecast.max_score)}</span>` : "0<span> / 150</span>";
  $("forecast-p10").textContent = forecast.available ? formatScore(forecast.p10) : "0";
  $("forecast-p90").textContent = forecast.available ? formatScore(forecast.p90) : "0";
  $("forecast-meta").textContent = forecast.available ? `置信度 ${forecast.confidence} · 已使用 ${forecast.attempts_used} 次作答` : (forecast.reason || "等待题库数据");
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

function renderQuestionMini(question) {
  return `<article class="question-mini" data-question-id="${escapeAttr(question.id)}">
    <div class="question-mini-ref"><span>${escapeHtml(question.year)} / Q${escapeHtml(question.number)}</span><span>${formatScore(question.points)}分</span></div>
    <div class="question-mini-preview markdown-body">${renderQuestionPreview(question.question_markdown, 300) || `<p class="muted-copy">完整题目</p>`}</div>
    <p class="question-concepts">${questionConceptMarkup(question)}</p>
    <div class="question-mini-foot"><span class="type-pill ${question.question_type === "solution" ? "solution" : ""}">${typeLabel(question.question_type)}</span><span>打开作答 →</span></div>
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
    fetchJSON(`/api/study/blocks?user_id=${encodeURIComponent(state.userId)}&limit=6`),
    fetchJSON(`/api/practice/next?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二&limit=8`),
    fetchJSON("/api/concepts"),
    fetchJSON("/api/exams"),
    fetchJSON("/api/llm/settings"),
  ]);
  [state.stats, state.progress, state.forecast] = results.slice(0, 3);
  state.blocks = results[3].blocks || [];
  state.nextQuestions = results[4].items || [];
  state.concepts = results[5] || [];
  state.exams = results[6] || [];
  state.settings = results[7] || {};
  populateFilters();
  renderModelStatus();
  renderOverview();
  renderSettingsValues();
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
}

async function loadLibrary() {
  if (!state.concepts.length || !state.exams.length) {
    try { await loadBaseData(); } catch (error) { showNotice(error.message); return; }
  }
  const params = new URLSearchParams({ exam_type: $("filter-exam").value || "数学二", limit: "60" });
  if ($("filter-year").value) params.set("year", $("filter-year").value);
  if ($("filter-type").value) params.set("question_type", $("filter-type").value);
  if ($("filter-concept").value) params.set("concept_id", $("filter-concept").value);
  if ($("filter-scope").value) params.set("scope", $("filter-scope").value);
  $("question-list").innerHTML = `<div class="loading-card">正在加载真题……</div>`;
  try {
    const payload = await fetchJSON(`/api/questions?${params}`);
    $("archive-count").textContent = payload.total;
    $("question-list").innerHTML = payload.items.length ? payload.items.map(renderQuestionRow).join("") : `<div class="loading-card">没有匹配的题目。</div>`;
    bindQuestionOpeners($("question-list"));
    state.libraryLoaded = true;
  } catch (error) {
    $("question-list").innerHTML = `<div class="loading-card">读取失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderQuestionRow(question) {
  return `<article class="question-row" data-question-id="${escapeAttr(question.id)}">
    <div class="question-row-ref">${escapeHtml(question.year)} 年<br />第 ${escapeHtml(question.number)} 题</div>
    <div class="question-row-content"><div class="question-preview markdown-body">${renderQuestionPreview(question.question_markdown, 460) || `<p class="muted-copy">完整题目</p>`}</div><p class="question-concepts">${questionConceptMarkup(question)}</p></div>
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
    bindQuestionOpeners($("blocks-container"));
    bindPracticeStarters($("blocks-container"));
  } catch (error) {
    $("blocks-container").innerHTML = `<div class="loading-card">读取失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderFullBlock(block) {
  const concept = block.concept || {};
  const value = Math.max(2, Math.min(98, Number(concept.mastery ?? 22)));
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
  const samples = (block.questions || []).slice(0, 3).map((question, index) => `<div class="block-question" data-question-id="${escapeAttr(question.id)}"><span class="block-question-number">0${index + 1}</span><div class="block-question-preview markdown-body">${renderQuestionPreview(question.question_markdown, 260)}</div><small>${formatScore(question.points)}分 · ${question.year}</small></div>`).join("");
  return `<article class="full-block-card">
    <div class="full-block-head"><div><span class="eyebrow">${escapeHtml(concept.subject || "知识块")}</span><h3>${escapeHtml(concept.name || "未分类")}</h3><p>${concept.attempts || 0} 次作答 · ${concept.accuracy == null ? "暂无正确率" : `${formatScore(concept.accuracy)}% 正确`}</p></div><div class="mastery-number">${formatScore(concept.mastery ?? 22)}%</div></div>
    <div class="progress-line"><span style="--progress:${(value / 100).toFixed(3)}"></span></div>
    <div class="block-reason">${escapeHtml(block.reason || "根据当前掌握度安排训练")}</div>
    <div class="block-type-grid">${typeCards || `<p class="muted-copy">该知识块暂时没有可用的题型子块。</p>`}</div>
    <div class="block-sample-head"><span class="eyebrow">题目预览</span><span>点击题目可直接作答</span></div>
    <div class="block-question-list">${samples || `<p class="muted-copy">暂无推荐题目。</p>`}</div>
  </article>`;
}

function bindPracticeStarters(root) {
  $$('[data-start-practice]', root).forEach((button) => button.addEventListener("click", () => startPracticeSession(button.dataset.conceptId, button.dataset.questionType)));
}

function practiceGradeValue(value) {
  return value == null ? "" : String(value);
}

function renderPracticeAttachments(items = []) {
  return items.length
    ? `<div class="practice-existing-attachments">已保存：${items.map((item) => `<a href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.filename || "作答图片")}</a>`).join("、")}</div>`
    : "";
}

function renderPracticeSession() {
  const session = state.practiceSession;
  if (!session) return;
  const finished = session.status === "finished";
  const questions = session.questions || [];
  const countLabel = session.question_count >= session.requested_count ? `${session.question_count} 题` : `题库仅有 ${session.question_count} 题`;
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
    const uploadArea = finished ? renderPracticeAttachments(answerState.attachments || []) : `<div class="practice-upload-row"><label class="upload-button small-upload" for="practice-image-${escapeAttr(question.id)}">＋ 上传过程图</label><input id="practice-image-${escapeAttr(question.id)}" type="file" data-practice-image="${escapeAttr(question.id)}" accept="image/png,image/jpeg,image/webp,image/gif" /><span data-practice-image-status="${escapeAttr(question.id)}">支持图片，单张不超过 8 MB</span></div>${renderPracticeAttachments(answerState.attachments || [])}`;
    const selfGrade = question.question_type === "solution" ? `<label class="practice-grade-label">解答题自评<select data-practice-grade="${escapeAttr(question.id)}" ${finished ? "disabled" : ""}>${gradeOptions}</select></label>` : "";
    return `<article class="practice-session-question" data-practice-question="${escapeAttr(question.id)}"><div class="practice-question-head"><span>${String(index + 1).padStart(2, "0")} / ${typeLabel(question.question_type)}</span><b>${formatScore(question.points)} 分</b></div><div class="practice-question-body markdown-body">${renderMarkdown(question.question_markdown)}</div><div class="practice-answer-grid">${answerArea}</div>${uploadArea}${selfGrade}${resultMarkup}</article>`;
  }).join("");
  const answeredCount = questions.filter((question) => {
    const state = question.answer_state || {};
    return (state.answer || "").trim() || state.self_grade != null;
  }).length;
  const statusLabel = finished ? `已提交 · 得分 ${formatScore(session.score)} / ${formatScore(session.max_score)} 分` : `已填写 ${answeredCount} / ${questions.length} 题 · 可随时保存草稿`;
  $("blocks-container").classList.add("practice-active");
  $("blocks-container").innerHTML = `<section class="practice-session-shell"><header class="practice-session-header"><div><span class="eyebrow">TRAINING SESSION / ${escapeHtml(typeLabel(session.question_type))}</span><h3>${escapeHtml(conceptName(session.concept_id))} · ${escapeHtml(typeLabel(session.question_type))}题训练</h3><p>随机抽取 ${escapeHtml(countLabel)} · 真实题库 · ${finished ? "本次已完成" : "提交后统一判题"}</p></div><div class="practice-session-actions"><button class="text-button" id="leave-practice-session">返回分块</button>${finished ? "" : `<button class="secondary-button" id="save-practice-session">保存草稿</button><button class="primary-button" id="submit-practice-session">提交训练</button>`}</div></header><div class="practice-session-status"><span>${escapeHtml(statusLabel)}</span><span class="practice-session-id">${escapeHtml(session.id.slice(0, 8))}</span></div><div class="practice-session-list">${cards}</div>${finished ? `<footer class="practice-session-footer"><p>本次结果已经写入学习记录，可以返回分块继续训练。</p><button class="primary-button" id="back-after-practice">返回分块训练</button></footer>` : `<footer class="practice-session-footer"><p>草稿只保存到本机，不会改变掌握度；点击提交后才会计入统计。</p><button class="primary-button" id="submit-practice-session-bottom">提交 15 题训练</button></footer>`}</section>`;
  typeset($("blocks-container"));
  bindAnswerEditors($('blocks-container'));
  bindPracticeSession();
}

function updatePracticeSessionStatus() {
  const session = state.practiceSession;
  if (!session || session.status === "finished") return;
  const answered = $$('[data-practice-answer]').filter((field) => field.value.trim()).length + $$('[data-practice-grade]').filter((field) => field.value !== "").length;
  const status = $("blocks-container").querySelector(".practice-session-status span");
  if (status) status.textContent = `已填写 ${answered} / ${session.questions.length} 题 · 可随时保存草稿`;
}

function bindPracticeSession() {
  const root = $("blocks-container");
  $$('[data-practice-answer]', root).forEach((field) => field.addEventListener("input", updatePracticeSessionStatus));
  $$('[data-practice-grade]', root).forEach((field) => field.addEventListener("change", updatePracticeSessionStatus));
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
  $("save-practice-session")?.addEventListener("click", savePracticeSession);
  $("submit-practice-session")?.addEventListener("click", () => submitPracticeSession(false));
  $("submit-practice-session-bottom")?.addEventListener("click", () => submitPracticeSession(false));
}

async function collectPracticeSessionPayload() {
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
  return { user_id: state.userId, answers, self_grades: selfGrades, attachment_ids: attachmentIds };
}

async function startPracticeSession(conceptId, questionType) {
  const button = $$('[data-start-practice]').find((item) => item.dataset.conceptId === conceptId && item.dataset.questionType === questionType);
  if (button) button.disabled = true;
  try {
    state.practiceSession = await fetchJSON("/api/practice/sessions", jsonOptions({ user_id: state.userId, exam_type: "数学二", concept_id: conceptId, question_type: questionType, count: 15 }));
    renderPracticeSession();
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
    showToast("草稿已保存到本机。继续编辑后可以再次保存。", false);
  } catch (error) {
    showToast(`保存草稿失败：${error.message}`, true);
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
    const payload = await collectPracticeSessionPayload();
    state.practiceSession = await fetchJSON(`/api/practice/sessions/${encodeURIComponent(session.id)}/submit`, jsonOptions(payload));
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
    const question = await fetchJSON(`/api/questions/${encodeURIComponent(questionId)}`);
    state.currentQuestion = question;
    $("modal-question-ref").textContent = `${question.exam_type} · ${question.year} 年 · 第 ${question.number} 题`;
    $("modal-question-type").textContent = `${typeLabel(question.question_type)}题 · ${formatScore(question.points)} 分`;
    $("question-modal-title").textContent = `${question.year} 年真题 / Q${question.number}`;
    $("modal-question-tags").innerHTML = questionConceptLabels(question).map((concept) => `<span class="tag ${concept.scope === "out-of-syllabus" ? "out-of-syllabus" : ""}">${escapeHtml(concept.scope === "out-of-syllabus" ? `${concept.scope_label} · ${concept.name}` : concept.name)}</span>`).join("");
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
      ? "点击选项，或使用键盘 A-D / 1-4"
      : question.question_type === "fill"
        ? "点击公式工具插入模板，源码与预览同步"
        : "先写步骤，再用公式工具补充关键表达式";
    $("question-result").hidden = true;
    $("tutor-box").hidden = true;
    $("modal-source").textContent = `SOURCE · ${question.source_path || "本地题库"}`;
    $("question-modal").classList.add("open");
    $("question-modal").setAttribute("aria-hidden", "false");
    window.setTimeout(() => $("answer-input")?.focus(), 120);
  } catch (error) {
    showToast(`打开题目失败：${error.message}`, true);
  }
}

function closeQuestion() {
  $("question-modal").classList.remove("open");
  $("question-modal").setAttribute("aria-hidden", "true");
  state.currentQuestion = null;
}

function resultLabel(status) {
  return { correct: "判定正确", incorrect: "需要订正", partial: "部分得分", manual: "等待自评" }[status] || status;
}

function renderQuestionResult(payload) {
  const result = payload.result || {};
  const box = $("question-result");
  box.className = `result-box ${result.status || "manual"}`;
  box.hidden = false;
  const expected = result.expected_answer || payload.answer_markdown || "";
  const solution = payload.solution_markdown || "";
  const attachments = payload.attachments || [];
  const attachmentMarkup = attachments.length ? `<div class="result-attachments"><h4>已保存的作答图片</h4>${attachments.map((item) => `<a href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer"><img src="${escapeAttr(item.url)}" alt="${escapeAttr(item.filename || "作答图片")}" /></a>`).join("")}</div>` : "";
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
    const payload = await fetchJSON(`/api/questions/${encodeURIComponent(question.id)}/attempts`, jsonOptions({
      user_id: state.userId,
      answer: $("answer-input").value,
      self_grade: selfGradeValue === "" ? null : Number(selfGradeValue),
      duration_seconds: Math.max(0, Number($("answer-duration").value || 0) * 60),
      mode: "practice",
      attachment_ids: attachmentIds,
    }));
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
    let html = escapeHtml(content).replace(/\n/g, "<br />");
    try {
      const parsed = JSON.parse(content);
      html = Object.entries(parsed).map(([key, value]) => `<p><strong>${escapeHtml(key)}：</strong>${escapeHtml(value)}</p>`).join("");
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
    const [progress, forecast, blocks, next] = await Promise.all([
      fetchJSON(`/api/progress?user_id=${encodeURIComponent(state.userId)}`),
      fetchJSON(`/api/forecast?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二`),
      fetchJSON(`/api/study/blocks?user_id=${encodeURIComponent(state.userId)}&limit=12`),
      fetchJSON(`/api/practice/next?user_id=${encodeURIComponent(state.userId)}&exam_type=数学二&limit=8`),
    ]);
    state.progress = progress;
    state.forecast = forecast;
    state.blocks = blocks.blocks || [];
    state.nextQuestions = next.items || [];
    renderOverview();
    if (state.view === "blocks") loadBlocks();
  } catch (error) {
    console.warn("learning refresh failed", error);
  }
}

async function loadSimulationCatalog() {
  if (!state.exams.length) {
    try { await loadBaseData(); } catch (error) { showNotice(error.message); return; }
  }
  const savedId = localStorage.getItem("ai-math-simulation");
  if (savedId && !state.currentSimulation) {
    try {
      state.currentSimulation = await fetchJSON(`/api/simulations/${encodeURIComponent(savedId)}`);
      renderSimulation();
      if (state.currentSimulation.status !== "finished") startSimulationClock();
      return;
    } catch {
      localStorage.removeItem("ai-math-simulation");
    }
  }
  if (!state.currentSimulation) $("simulation-container").innerHTML = `<div class="empty-state"><div class="empty-mark">⌁</div><h3>还没有进行中的模拟考</h3><p>选择年份并生成一套完整试卷，提交后结果会回流到你的掌握度和分数预估。</p></div>`;
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
    localStorage.setItem("ai-math-simulation", payload.id);
    renderSimulation();
    startSimulationClock();
    showToast(`已生成 ${payload.year} 年完整试卷，共 ${payload.questions.length} 题。`);
  } catch (error) {
    showToast(`生成模拟考失败：${error.message}`, true);
  } finally {
    button.disabled = false;
  }
}

function renderSimulation() {
  const simulation = state.currentSimulation;
  if (!simulation) return;
  const finished = simulation.status === "finished";
  const questions = simulation.questions || [];
  if (finished) {
    const score = formatScore(simulation.score);
    $("simulation-container").innerHTML = `<div class="simulation-result"><div class="simulation-result-score">${score}<span> / ${formatScore(simulation.max_score)} 分</span></div><div><h3>${simulation.year} 年模拟考已完成</h3><p>本次成绩已计入学习记录。你可以回到分块训练查看哪些知识块拉低了得分，并继续做针对性练习。</p></div></div>${renderSimulationPaper(simulation, true)}`;
    typeset($("simulation-container"));
    return;
  }
  $("simulation-container").innerHTML = renderSimulationPaper(simulation, false);
  typeset($("simulation-container"));
  bindAnswerEditors($("simulation-container"));
  bindSimulationUploads($("simulation-container"));
}

function renderSimulationPaper(simulation, finished) {
  const questions = simulation.questions || [];
  const questionMarkup = questions.map((question, index) => {
    const gradeMarkup = question.question_type === "solution" ? `<div class="sim-self-grade"><span>解答题自评</span><select data-sim-grade="${escapeAttr(question.id)}"><option value="">暂不自评</option><option value="1">完整正确（100%）</option><option value="0.7">主要正确（70%）</option><option value="0.4">部分得到（40%）</option><option value="0">不会/错误（0%）</option></select></div>` : "";
    const answerMarkup = finished ? "" : `<div class="sim-answer">${renderAnswerEditor(question, { mode: "simulation" })}<div class="sim-upload-row"><label class="upload-button small-upload" for="sim-image-${escapeAttr(question.id)}">＋ 上传过程图</label><input id="sim-image-${escapeAttr(question.id)}" type="file" data-sim-image="${escapeAttr(question.id)}" accept="image/png,image/jpeg,image/webp,image/gif" /><span class="sim-image-status" data-sim-image-status="${escapeAttr(question.id)}">可选，单张不超过 8 MB</span></div>${gradeMarkup}</div>`;
    return `<article class="simulation-question"><div class="sim-q-head"><span class="sim-q-ref">${String(index + 1).padStart(2, "0")} / 第 ${question.number} 题 · ${typeLabel(question.question_type)}</span><span class="sim-q-points">${formatScore(question.points)} 分</span></div><div class="markdown-body">${renderMarkdown(question.question_markdown)}</div>${answerMarkup}</article>`;
  }).join("");
  return `<div class="simulation-shell"><div class="simulation-header"><div><h3>${simulation.year} 年数学二 · 全真模拟</h3><p>${questions.length} 道题 · 满分 ${formatScore(simulation.max_score)} · ${finished ? "已交卷" : "答案不会自动显示，提交后统一判定"}</p></div><div class="simulation-clock" id="simulation-clock">${finished ? "已完成" : "180:00"}</div></div><div class="simulation-progress"><span id="simulation-progress-bar" style="--progress:0"></span></div><div class="simulation-question-list">${questionMarkup}</div>${finished ? "" : `<div class="simulation-footer"><p>解答题若暂不自评，将被诚实记录为“待自评”，不自动猜分。</p><button class="primary-button" id="submit-simulation">提交整卷</button></div>`}</div>`;
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
    const answered = $$('[data-sim-answer]').filter((field) => field.value.trim()).length;
    const total = (simulation.questions || []).length || 1;
    const bar = $("simulation-progress-bar");
    if (bar) bar.style.setProperty("--progress", String(answered / total));
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
    state.currentSimulation = await fetchJSON(`/api/simulations/${encodeURIComponent(simulation.id)}/submit`, jsonOptions({ user_id: state.userId, answers, self_grades: selfGrades, attachment_ids: attachmentIds }));
    localStorage.setItem("ai-math-simulation", state.currentSimulation.id);
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
    state.settings = await fetchJSON("/api/llm/settings");
    renderSettingsValues();
    renderModelStatus();
  } catch (error) {
    $("settings-status").textContent = `读取配置失败：${error.message}`;
    $("settings-status").classList.add("error");
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

async function init() {
  $("today-date").textContent = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(new Date());
  $$(".nav-item[data-view]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.view)));
  $$('[data-view-target]').forEach((button) => button.addEventListener("click", () => navigate(button.dataset.viewTarget)));
  $("refresh-button").addEventListener("click", () => loadOverview());
  $("start-recommended").addEventListener("click", () => state.nextQuestions[0] ? openQuestion(state.nextQuestions[0].id) : navigate("library"));
  $("apply-filters").addEventListener("click", loadLibrary);
  $("reload-blocks").addEventListener("click", loadBlocks);
  $("create-simulation").addEventListener("click", createSimulation);
  $("submit-answer").addEventListener("click", submitAnswer);
  $("answer-image-input").addEventListener("change", () => showImagePreview($("answer-image-input").files?.[0], $("answer-image-preview"), $("answer-image-status")));
  $("ask-tutor").addEventListener("click", askTutor);
  $("close-question-modal").addEventListener("click", closeQuestion);
  $("question-modal").addEventListener("click", (event) => { if (event.target === $("question-modal")) closeQuestion(); });
  $("fetch-models").addEventListener("click", fetchModelsFromForm);
  $("model-settings-form").addEventListener("submit", saveModelSettings);
  $("clear-key").addEventListener("click", clearApiKey);
  $("model-select").addEventListener("change", () => { $("model-manual").value = $("model-select").value; });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeQuestion(); });
  document.addEventListener("click", (event) => { if (event.target.id === "submit-simulation") submitSimulation(false); });
  await loadOverview();
}

window.addEventListener("DOMContentLoaded", init);

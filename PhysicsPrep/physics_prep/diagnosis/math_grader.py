"""确定性数学判分。

安全模型（不使用 eval、不使用 parse_expr、不使用 multiprocessing）：

1. 输入先经过长度、节点数与嵌套深度上限；
2. 用 AST 白名单把文本构造成 SymPy 对象，只允许白名单符号、函数与四则运算；
3. 幂指数必须是绝对值不超过 20 的实常量，避免 `2**100000` 这类膨胀；
4. 每个可能昂贵的步骤前后都检查墙钟截止时间，超时返回 `uncertain`；
5. 判定顺序：精确相等 → 数值容差 → 受控边界抽样反例。抽样只能证明“不等价”，
   绝不用于证明“等价”；无法证明等价时返回 `uncertain`，不强行判错。

早期版本依赖 `multiprocessing` 子进程加超时；在受限环境（命名管道不可用）下会直接失败，
并使全部判分不可用。现在改为纯进程内实现，判分在 Mock 与在线模式下均可离线运行。
"""
import ast
import re
import time

MIN_GRADING_BUDGET_SECONDS = 0.005
DEFAULT_GRADING_TIMEOUT = 5.0

FUNCTION_NAMES = frozenset({'sqrt', 'sin', 'cos', 'tan', 'exp', 'log', 'abs'})
CONSTANT_NAMES = frozenset({'pi', 'E', 'I'})
RESERVED_NAMES = FUNCTION_NAMES | CONSTANT_NAMES


class InputError(ValueError):
    """受控解析失败：输入越界、含非白名单语法或数学上无定义。"""


def _check_deadline(deadline):
    if deadline is not None and time.monotonic() > deadline:
        raise TimeoutError('数学判分超时')


def controlled_parse(text, symbols):
    """把受信表达式解析为 SymPy 对象。`symbols` = {'names': [...], 'positive': [...]}"""
    import sympy as sp
    _check_deadline(symbols.get('deadline'))
    if isinstance(text, bool) or not isinstance(text, (str, int, float)):
        raise InputError('仅支持文本或数值答案')
    if isinstance(text, str):
        if len(text) > 300:
            raise InputError('输入长度限制为300字符')
        text = text.strip()
        if not text:
            raise InputError('请输入答案')
        text = text.replace('^', '**').replace('×', '*').replace('÷', '/').replace('−', '-')
    else:
        if text != text:  # NaN
            raise InputError('表达式无定义')
        text = repr(text)

    try:
        tree = ast.parse(text, mode='eval')
    except SyntaxError as exc:
        raise InputError('表达式语法有误，请检查括号与显式乘号 *') from exc
    if len(list(ast.walk(tree))) > 100:
        raise InputError('表达式过于复杂')

    positive = set(symbols.get('positive') or [])
    names = {}
    for name in symbols.get('names') or []:
        names[name] = sp.Symbol(name, positive=True) if name in positive else sp.Symbol(name, real=True)
    names.update({'pi': sp.pi, 'E': sp.E, 'I': sp.I})
    functions = {'sqrt': sp.sqrt, 'sin': sp.sin, 'cos': sp.cos, 'tan': sp.tan,
                 'exp': sp.exp, 'log': sp.log, 'abs': sp.Abs}
    deadline = symbols.get('deadline')

    def walk(node, depth=0):
        if depth > 15:
            raise InputError('表达式嵌套过深')
        if depth % 4 == 0:
            _check_deadline(deadline)
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InputError('仅支持数值常量、白名单符号与四则运算')
            if abs(value) > 1e12:
                raise InputError('数值过大')
            return sp.Rational(str(value))
        if isinstance(node, ast.Name):
            if node.id in names:
                return names[node.id]
            raise InputError(f'未允许的符号或函数：{node.id}')
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand = walk(node.operand, depth + 1)
            return operand if isinstance(node.op, ast.UAdd) else -operand
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left, right = walk(node.left, depth + 1), walk(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right.is_zero:
                    raise InputError('除数不能为零')
                return left / right
            if right.free_symbols or not right.is_real or abs(complex(sp.N(right))) > 20:
                raise InputError('幂指数必须是绝对值不超过20的实数常量')
            return left ** right
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in functions and len(node.args) == 1 and not node.keywords):
            return functions[node.func.id](walk(node.args[0], depth + 1))
        raise InputError('仅支持白名单符号、函数与四则运算，请使用显式乘号 *')

    result = walk(tree.body)
    if result.has(sp.zoo, sp.nan, sp.oo, -sp.oo) or result is sp.nan:
        raise InputError('表达式无定义')
    _check_deadline(deadline)
    return result


def _sample_points(expression):
    """构造受控代入点：只使用正有理数，避免把定义域外取值当成反例。"""
    import sympy as sp
    symbols = sorted(expression.free_symbols, key=str)
    for offset in (1, 2, 3, 5):
        yield {symbol: sp.Rational(index + offset + 1, offset + 1) for index, symbol in enumerate(symbols)}


def _finite_number(expression):
    import sympy as sp
    try:
        value = complex(sp.N(expression, 12))
    except Exception:
        return None
    if value != value or value in (complex('inf'), complex('-inf')):
        return None
    return value


def compare_expressions(left, right, numeric=False, tolerance=1e-6, deadline=None):
    """在符号或数值意义上比较两个表达式，返回 (status, explanation)。"""
    import sympy as sp
    if left == right:
        return 'correct', '表达式与标准答案在结构上一致。'

    difference = left - right
    if difference.is_zero is True:
        return 'correct', '在题目约定的符号条件下，两式解析等价。'

    _check_deadline(deadline)
    # 只要存在浮点数就按数值容差比较，避免 1.00000001 被当作“不等价”。
    if numeric or difference.atoms(sp.Float):
        if not difference.free_symbols:
            value = _finite_number(difference)
            if value is None:
                return 'uncertain', '无法在数值上比较该表达式，请人工确认。'
            _check_deadline(deadline)
            scale = max(1.0, abs(_finite_number(right) or 0.0))
            if abs(value) <= tolerance * scale:
                return 'correct', '按题目给定的数值容差比较，结果一致。'
            return ('incorrect' if numeric else 'uncertain'), (
                '数值上与标准答案不一致。' if numeric else '数值上与标准答案不一致，请核对精确表达式。')

    for transform in (lambda e: sp.together(e), lambda e: sp.cancel(e), lambda e: sp.simplify(e)):
        _check_deadline(deadline)
        try:
            candidate = transform(difference)
        except Exception:
            continue
        if candidate == 0 or candidate.is_zero is True:
            return 'correct', '在题目约定的符号条件下，两式解析等价。'

    _check_deadline(deadline)
    if not difference.free_symbols:
        return 'incorrect', '两式结果不同。'

    for sample in _sample_points(difference):
        _check_deadline(deadline)
        value = _finite_number(difference.subs(sample))
        if value is None:
            continue
        if abs(value) > 1e-8:
            return 'incorrect', '在题目允许的正实数范围内可找到不等价的反例。'
    return 'uncertain', '无法证明两式等价，需要人工确认。'


def _resolve_symbols(expected, opts):
    names = opts.get('allowed_symbols')
    if names is None:
        names = sorted(set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', str(expected))) - RESERVED_NAMES)
    names = list(names)
    if len(names) > 20 or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,20}', name) for name in names):
        return None
    positive = [name for name in (opts.get('positive_symbols') or []) if name in names]
    return {'names': names, 'positive': positive}


def _objective_grade(answer, expected, question_type, opts, deadline):
    from .units import detect_units
    text = answer if isinstance(answer, (int, float)) and not isinstance(answer, bool) else str('' if answer is None else answer)
    if isinstance(text, str):
        text = text.strip()
    if text == '' or text is None:
        return {'status': 'uncertain', 'explanation': '请先输入答案。'}

    expected_unit = opts.get('expected_unit')
    _, unit_notice = detect_units(text, expected_unit, opts.get('allowed_symbols'))
    if expected_unit and unit_notice and isinstance(text, str):
        # 单位书写与题目要求不一致时先提示核对，不直接判错。
        return {'status': 'uncertain', 'explanation': unit_notice}

    symbols = _resolve_symbols(expected, opts)
    if symbols is None:
        return {'status': 'uncertain', 'explanation': '题目符号配置无效，需要人工确认。'}
    symbols['deadline'] = deadline

    numeric = question_type.startswith('numeric')
    tolerance = float(opts.get('numeric_tolerance', 1e-6))
    try:
        left = controlled_parse(text, symbols)
        right = controlled_parse(str(expected), symbols)
    except InputError as exc:
        # 把本题实际可用的符号列出来，避免只报“未允许的符号”让用户无从下手。
        allowed = '、'.join(symbols.get('names') or [])
        hint = f'本题可用符号：{allowed}；' if allowed else ''
        return {'status': 'uncertain', 'explanation': f'{exc}；{hint}如不确定请请求人工确认。'}
    except TimeoutError:
        return {'status': 'uncertain', 'explanation': '数学判分超时，请简化输入或请求人工确认。'}

    if numeric and (left.free_symbols or right.free_symbols):
        return {'status': 'uncertain', 'explanation': '本题要求数值结果，请代入具体数值后作答。'}

    try:
        status, explanation = compare_expressions(left, right, numeric, tolerance, deadline)
    except TimeoutError:
        return {'status': 'uncertain', 'explanation': '数学判分超时，请简化输入或请求人工确认。'}
    except Exception:
        return {'status': 'uncertain', 'explanation': '无法安全判定该表达式，请检查显式乘号与符号白名单。'}
    if status == 'correct' and unit_notice:
        explanation += f'（{unit_notice}）'
    return {'status': status, 'explanation': explanation}


def grade(answer, expected, question_type, options=None, **kwargs):
    """对一道题作答判分，返回 {'status', 'explanation'}。

    status ∈ {'correct', 'incorrect', 'uncertain'}。判分是确定性的：
    大模型输出不得覆盖这里的结果。
    """
    opts = {**(options or {}), **kwargs}
    try:
        timeout = float(opts.get('grading_timeout', DEFAULT_GRADING_TIMEOUT))
    except (TypeError, ValueError):
        timeout = DEFAULT_GRADING_TIMEOUT
    timeout = max(0.0, min(60.0, timeout))

    if question_type == 'single_choice':
        chosen = str(answer or '').strip()
        if not chosen:
            return {'status': 'uncertain', 'explanation': '请选择一个选项。'}
        return {'status': 'correct' if chosen == str(expected).strip() else 'incorrect',
                'explanation': '按标准选项确定性判分，不涉及模型推断。'}

    if question_type == 'multiple_choice':
        if not isinstance(answer, (list, tuple, set)):
            return {'status': 'uncertain', 'explanation': '请提交选项列表。'}
        if not answer:
            return {'status': 'uncertain', 'explanation': '请至少选择一个选项。'}
        expected_set = set(expected) if isinstance(expected, (list, tuple, set)) else {str(expected)}
        return {'status': 'correct' if set(answer) == expected_set else 'incorrect',
                'explanation': '全部正确选项一致才算正确，不设置部分分。'}

    if question_type not in ('numeric', 'symbolic', 'numeric_calculation', 'symbolic_expression'):
        return {'status': 'uncertain',
                'explanation': '推导或简答题需要人工确认；模型意见仅供参考，不自动更新掌握度。'}

    if timeout < MIN_GRADING_BUDGET_SECONDS:
        return {'status': 'uncertain', 'explanation': '数学判分时间预算过小，未执行判定。'}
    deadline = time.monotonic() + timeout
    try:
        return _objective_grade(answer, expected, question_type, opts, deadline)
    except Exception:
        return {'status': 'uncertain', 'explanation': '数学判分未完成，请检查输入或请求人工确认。'}

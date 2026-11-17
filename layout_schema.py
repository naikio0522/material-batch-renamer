"""Validation and defaults for published end-user layout settings."""
import copy

GROUPS = {
    'basic1': ('基本信息 · 第一行', ['剪辑', '平台']),
    'basic2': ('基本信息 · 第二行', ['产品', '日期']),
    'basic3': ('基本信息 · 第三行', ['运营（多选）']),
    'basic4': ('基本信息 · 序号', ['序号标识']),
    'category': ('素材分类', ['一级分类', '二级分类', '三级分类']),
    'fourth': ('四级分类', ['达人', '专场', '活动', '痛点', '品牌事件', '其他']),
    'tags': ('其他标签', ['AI剧情', 'AI非剧情', '打假', '测评', '矩阵号', '声明', '内部AI', '数字人AI']),
    'title': ('素材名称', ['自定义素材名']),
    'creative': ('创意人员', ['AI组创意人员', 'AI组创意类型', '编导创意']),
}
FIELDS = ['剪辑', '平台', '产品', '日期', '序号标识', '一级分类', '二级分类',
          '达人', '专场', '活动', '痛点', '品牌事件', '其他',
          '自定义素材名', 'AI组创意人员', 'AI组创意类型', '编导创意']
DEFAULT_LAYOUT = {
    'widths': dict(zip(FIELDS, [20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 11, 11, 11])),
    'columns': {'basic1': 2, 'basic2': 2, 'basic3': 1, 'basic4': 1, 'category': 1, 'fourth': 4, 'title': 1, 'tags': 8, 'creative': 3},
    'window': {'width': 1240, 'height': 860, 'maximized': True, 'list_height': 220},
}

FIELD_ALIASES = {
    '剪辑简称+全名': '剪辑',
    '官媒专场': '专场',
    '大促活动': '活动',
    '品牌活动事件': '品牌事件',
    '品牌事件活动': '品牌事件',
}
FIXED_WIDTHS = {'剪辑', '平台', '产品', '日期'}
MINIMUM_20_FIELDS = {'达人', '专场', '活动', '痛点', '品牌事件', '其他'}
FIXED_COLUMNS = {'basic1': 2, 'basic2': 2, 'basic3': 1, 'basic4': 1, 'fourth': 4, 'title': 1}


def width_limits(name):
    if name in FIXED_WIDTHS: return 20, 20
    return (20, 40) if name in MINIMUM_20_FIELDS else (6, 40)


def column_limits(key):
    if key in FIXED_COLUMNS:
        return FIXED_COLUMNS[key], FIXED_COLUMNS[key]
    return (7, 8) if key == 'tags' else (1, len(GROUPS[key][1]))


def _number(value, fallback, low, high):
    try:
        if isinstance(value, bool): return fallback
        return min(high, max(low, int(value)))
    except (TypeError, ValueError, OverflowError):
        return fallback


def sanitize_layout(config):
    result = copy.deepcopy(DEFAULT_LAYOUT)
    if not isinstance(config, dict): return result
    widths = config.get('widths')
    if isinstance(widths, dict):
        widths = dict(widths)
        for old, new in FIELD_ALIASES.items():
            if new not in widths and old in widths: widths[new] = widths[old]
        for name, default in result['widths'].items():
            result['widths'][name] = _number(widths.get(name), default, *width_limits(name))
    columns = config.get('columns')
    if isinstance(columns, dict):
        for key, default in result['columns'].items():
            result['columns'][key] = _number(columns.get(key), default, *column_limits(key))
    window = config.get('window')
    if isinstance(window, dict):
        for key, low, high in [('width', 680, 2560), ('height', 500, 1600), ('list_height', 110, 1000)]:
            result['window'][key] = _number(window.get(key), result['window'][key], low, high)
        if isinstance(window.get('maximized'), bool): result['window']['maximized'] = window['maximized']
    return result

"""Pure filename rules and read-only batch planning for material renames.

The planner keeps original row indices and only validates checked rows. It never
renames or writes a file; the GUI executes the reviewed operations separately.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Callable, Mapping, Sequence


PRODUCTS = {'修护牙膏': '修', '色修牙膏': '色修', '釉龈双护牙膏': '双护', '口干口臭专健牙膏': '专健', '儿童牙膏': '儿童'}
PLATFORMS = {'抖音': '抖', '抖音图文': '抖', '快手': '快', '视频号': '视'}
OPERATORS = {
    ('抖音', '修护牙膏'): ['李好', '阿鑫', '浩轩'],
    ('抖音', '口干口臭专健牙膏'): ['亚军'],
    ('抖音', '釉龈双护牙膏'): ['征宇'],
    ('抖音', '色修牙膏'): ['晓曦', '泽耀', '家宝'],
    ('抖音', '儿童牙膏'): ['楚楚', '靖海'],
    ('抖音图文', '口干口臭专健牙膏'): ['三朝'],
    ('抖音图文', '修护牙膏'): ['田田'],
    ('抖音图文', '色修牙膏'): ['依婷'],
    ('抖音图文', '儿童牙膏'): ['楚楚'],
    ('抖音图文', '釉龈双护牙膏'): ['楚楚'],
}
AI_PEOPLE = ['QQ王芊芊', 'XZ徐学志', 'JN陈嘉楠', 'YZ张瑶', 'ZY张语嫣', 'XL雷枭']
DIRECTORS = ['ZW赵婉君', 'TY唐玉', 'JL刘家龙', 'ZP张屏', 'ZJ周佳丽', 'LY李盈']
AI_TEXT_FIELDS = ('内部AI', '矩阵号')
FIXED_TAGS = ('AI剧情', 'AI非剧情', '打假', '测评', '声明')
INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$', re.I)


def validate_part(value, label, required=False):
    if not value:
        if required:
            raise ValueError(f'请填写{label}。')
        return
    if INVALID.search(value) or value[-1] in '. ':
        raise ValueError(f'{label}含 Windows 不允许的字符，或以空格/点结尾。')


def format_fourth(name, value):
    """Complete a category once; blank categories do not enter the filename."""
    value = value.strip()
    if not value:
        return ''
    prefix = {'达人': '达人', '痛点': '痛点'}.get(name, '')
    suffix = {'官媒专场': '专场', '专场': '专场', '大促活动': '活动',
              '活动': '活动', '品牌活动事件': '品牌事件', '品牌事件': '品牌事件',
              '内部AI': '内部AI', '矩阵号': '矩阵号'}.get(name, '')
    if prefix and not value.startswith(prefix):
        value = prefix + value
    if suffix and not value.endswith(suffix):
        value += suffix
    return value


def format_serial(value, index):
    """# is a dense automatic index; an explicit number remains unchanged."""
    if not isinstance(value, str):
        raise ValueError('序号标识请填写 # 或数字。')
    value = value.strip()
    if value == '#':
        if not isinstance(index, int) or isinstance(index, bool) or index < 1:
            raise ValueError('自动序号必须从 1 开始。')
        return str(index)
    if not re.fullmatch(r'[0-9]+', value):
        raise ValueError('序号标识请填写 # 或数字。')
    return value


def make_name(fields, original, index, total):
    """Return a validated filename; index is one-based among checked files."""
    original = Path(original)
    editor = fields['editor'].strip()
    validate_part(editor, '剪辑', True)
    try:
        date = datetime.strptime(fields['date'].strip(), '%Y-%m-%d').strftime('%m%d')
    except ValueError:
        raise ValueError('日期请用有效的 YYYY-MM-DD 格式，例如 2026-11-17。') from None
    platform, product = fields['platform'], fields['product']
    if platform not in PLATFORMS or product not in PRODUCTS:
        raise ValueError('请选择平台和产品。')
    if fields['first'] not in ('功效', '背书', '活动'):
        raise ValueError('请选择一级分类。')
    if fields['second'] not in ('口播', '混剪', '直播切片', '清水素材'):
        raise ValueError('请选择二级分类。')
    if len(fields['third']) != 1 or fields['third'][0] not in ('复刻', '迭代', '创新'):
        raise ValueError('请选择一个三级分类。')
    serial = format_serial(fields.get('serial', '#'), index)
    editor_segment = ('（Q）' if platform == '抖音图文' else '') + editor
    parts = [editor_segment, PLATFORMS[platform] + PRODUCTS[product], date, serial,
             fields['first'], fields['second'], *fields['third'], *fields['fourth_text']]
    title = fields['title'].strip() or original.stem
    validate_part(title, '素材名称', True)
    if fields.get('sequence') is not None:
        title += '_' + str(fields['sequence']).zfill(fields.get('sequence_width', 2))
    parts.append(title)
    parts.extend(fields['fourth_fixed'])
    if platform in ('抖音', '抖音图文'):
        if fields['operator'] not in OPERATORS.get((platform, product), []) + ['李想']:
            raise ValueError('请选择当前平台和产品对应的运营。')
        parts.append(fields['operator'])
    if fields['ai_type'] or fields['ai_person']:
        if fields['ai_type'] not in ('输出创意AI', '承接创意AI') or fields['ai_person'] not in AI_PEOPLE:
            raise ValueError('AI 创意须同时选择人员和类型。')
        parts.append(fields['ai_person'] + fields['ai_type'])
    if fields['director']:
        if fields['director'] not in DIRECTORS:
            raise ValueError('请选择有效的编导创意人员。')
        parts.append(fields['director'] + '创意')
    for part in parts:
        validate_part(part, '命名字段', True)
    result = '-'.join(parts) + original.suffix
    if len(result.encode('utf-16-le')) // 2 > 255 or RESERVED.match(result):
        raise ValueError('生成的文件名过长或是 Windows 保留名称。')
    return result


@dataclass(frozen=True)
class RenameItem:
    row_index: int
    source: Path
    target: Path | None
    filename: str
    status: str
    operator: str = ''
    checked: bool = True


@dataclass(frozen=True)
class RenamePlan:
    items: tuple[RenameItem, ...]

    @property
    def selected(self):
        return tuple(item for item in self.items if item.checked)

    @property
    def errors(self):
        return tuple(item for item in self.selected if item.target is None)

    @property
    def operations(self):
        return tuple(item for item in self.selected if item.target is not None)


@dataclass(frozen=True)
class _Draft:
    row_index: int
    source: Path
    fields: dict
    dense_index: int
    title_group: str
    filename: str


def _path_key(path):
    return str(path.resolve()).casefold()


def build_rename_plan(files: Sequence[Mapping], fields_for: Callable, check_sources=True):
    """Build one result per original row, with operations only for checked rows.

    fields_for(file, dense_index) is called once per checked row. The same dense
    index drives automatic serials and the GUI's round-robin operator choice.
    With check_sources=False, virtual examples are allowed and disk collisions
    are ignored; batch collisions are still resolved without writing anything.
    """
    if not files:
        raise ValueError('请先添加文件。')
    selected_count = sum(bool(file.get('checked', True)) for file in files)
    if not selected_count:
        raise ValueError('请至少勾选一个素材。')
    items, drafts = {}, []
    dense_index = 0
    for row_index, file in enumerate(files):
        source = Path(file['path'])
        if not file.get('checked', True):
            items[row_index] = RenameItem(row_index, source, None, '', '未勾选', checked=False)
            continue
        current_index = dense_index
        dense_index += 1
        operator = ''
        try:
            if check_sources and not source.is_file():
                raise ValueError('源文件不存在或不是文件。')
            fields = dict(fields_for(file, current_index))
            operator = fields.get('operator', '') if fields.get('platform') in ('抖音', '抖音图文') else ''
            filename = make_name(fields, source, current_index + 1, selected_count)
            title_group = (fields['title'].strip() or source.stem).casefold()
            drafts.append(_Draft(row_index, source, fields, current_index, title_group, filename))
        except (ValueError, OSError) as exc:
            items[row_index] = RenameItem(row_index, source, None, '', str(exc), operator)

    counts = Counter(draft.title_group for draft in drafts)
    reserved = {_path_key(d.source.with_name(d.filename)) for d in drafts if counts[d.title_group] == 1}
    claimed, next_suffix = set(), {}
    for draft in drafts:
        operator = draft.fields.get('operator', '') if draft.fields['platform'] in ('抖音', '抖音图文') else ''
        try:
            filename = draft.filename
            if counts[draft.title_group] > 1:
                number = next_suffix.get(draft.title_group, 1)
                while True:
                    if number > 999999:
                        raise ValueError('可用序号不足，请调整素材名。')
                    fields = dict(draft.fields, sequence=number, sequence_width=max(2, len(str(counts[draft.title_group]))))
                    filename = make_name(fields, draft.source, draft.dense_index + 1, selected_count)
                    target = draft.source.with_name(filename)
                    key = _path_key(target)
                    number += 1
                    if key not in reserved and key not in claimed and (not check_sources or not target.exists()):
                        break
                next_suffix[draft.title_group] = number
            else:
                target = draft.source.with_name(filename)
                key = _path_key(target)
                if key in claimed:
                    raise ValueError('与列表中的其他目标重名，请调整素材名。')
                if check_sources and target.exists():
                    if key == _path_key(draft.source):
                        raise ValueError('目标名称与原名称相同。')
                    raise ValueError('目标文件已存在，不会覆盖。')
            claimed.add(key)
            status = '可执行' if check_sources else '仅预览'
            items[draft.row_index] = RenameItem(draft.row_index, draft.source, target, filename, status, operator)
        except (ValueError, OSError) as exc:
            items[draft.row_index] = RenameItem(draft.row_index, draft.source, None, '', str(exc), operator)
    return RenamePlan(tuple(items[index] for index in range(len(files))))

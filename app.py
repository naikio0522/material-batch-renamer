import datetime as dt
import os
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
from updater import CURRENT_VERSION, startup_update_check
import settings


PRODUCTS = {'修护牙膏': '修', '色修牙膏': '色修', '釉龈双护牙膏': '双护', '口干口臭专健牙膏': '专健', '儿童牙膏': '儿童'}
UPDATE_REPOSITORY = 'naikio0522/material-batch-renamer'
UPDATE_MANIFEST_URL = 'https://raw.githubusercontent.com/naikio0522/material-batch-renamer/main/update.json'
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
    """Add the category wording once, leaving empty and free-form items alone."""
    value = value.strip()
    if not value:
        return ''
    prefixes = {'达人': '达人', '痛点': '痛点'}
    suffixes = {'官媒专场': '专场', '大促活动': '活动', '品牌活动事件': '品牌事件'}
    prefix = prefixes.get(name, '')
    suffix = suffixes.get(name, '')
    if prefix and not value.startswith(prefix):
        value = prefix + value
    if suffix and not value.endswith(suffix):
        value += suffix
    return value


def make_name(fields, original, index, total):
    """Build a filename without touching files. Raises ValueError for invalid fields."""
    editor = fields['editor'].strip()
    validate_part(editor, '剪辑简称和全名', True)
    if not re.fullmatch(r'[A-Za-z]+[\u3400-\u9fff·]+', editor):
        raise ValueError('剪辑请填写英文简称加中文全名，例如 XZ徐学志。')
    try:
        date = dt.datetime.strptime(fields['date'].strip(), '%Y-%m-%d').strftime('%m%d')
    except ValueError:
        raise ValueError('日期请用有效的 YYYY-MM-DD 格式，例如 2026-11-17。')
    platform, product = fields['platform'], fields['product']
    if platform not in PLATFORMS or product not in PRODUCTS:
        raise ValueError('请选择平台和产品。')
    if fields['first'] not in ('功效', '背书', '活动'):
        raise ValueError('请选择一级分类。')
    if fields['second'] not in ('口播', '混剪', '直播切片', '清水素材'):
        raise ValueError('请选择二级分类。')
    if len(fields['third']) != 1 or fields['third'][0] not in ('复刻', '迭代', '创新'):
        raise ValueError('请选择一个三级分类。')
    name = (('（Q）' if platform == '抖音图文' else '') + editor + ('自剪' if fields['leader'] else ''))
    parts = [name, PLATFORMS[platform] + PRODUCTS[product], date,
             fields['first'], fields['second'], *fields['third'], *fields['fourth_text']]
    title = fields['title'].strip() or original.stem
    validate_part(title, '素材名称', True)
    if fields.get('sequence') is not None:
        title += '_' + str(fields['sequence']).zfill(fields.get('sequence_width', 2))
    parts.append(title)
    parts.extend(fields['fourth_fixed'])
    if platform in ('抖音', '抖音图文'):
        allowed = OPERATORS.get((platform, product), []) + ['李想']
        if fields['operator'] not in allowed:
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
    if len(result) > 255 or RESERVED.match(result):
        raise ValueError('生成的文件名过长或是 Windows 保留名称。')
    return result


class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self._saved_settings = settings.load_settings()
        self._settings_ready = False
        self._settings_timer = None
        self._normal_geometry = None
        self.title('素材批量重命名工具 v' + CURRENT_VERSION)
        self.geometry('1240x860')
        self.minsize(680, 500)
        self.files = []
        self.editor = tk.StringVar()
        self.leader = tk.BooleanVar()
        self.platform = tk.StringVar(value='抖音')
        self.product = tk.StringVar(value='修护牙膏')
        self.date = tk.StringVar(value=dt.date.today().isoformat())
        self.first = tk.StringVar(value='功效')
        self.second = tk.StringVar(value='混剪')
        self.third = tk.StringVar()
        self.fourth_fixed = {k: tk.BooleanVar() for k in ('AI剧情', 'AI非剧情', '打假', '测评', '矩阵号', '声明', '内部AI', '数字人AI')}
        self.fourth_text = {k: tk.StringVar() for k in ('达人', '官媒专场', '大促活动', '痛点', '品牌活动事件', '其他')}
        self.title_text = tk.StringVar()
        self.operator_vars = {}
        self.ai_type = tk.StringVar()
        self.ai_person = tk.StringVar()
        self.director = tk.StringVar()
        self.status = tk.StringVar(value='请选择文件，填写规则后点击“生成预览”。')
        self.build_ui()
        self.platform.trace_add('write', self.update_operators)
        self.product.trace_add('write', self.update_operators)
        self.update_operators()
        self.restore_settings()
        self.setup_autosave()
        self.protocol('WM_DELETE_WINDOW', self.close_app)
        for widget in (self, self.tree):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<Drop>>', self.drop_files)

    def build_ui(self):
        outer = ttk.Frame(self, padding=6)
        outer.pack(fill='both', expand=True)
        header = ttk.Frame(outer)
        header.pack(fill='x')
        ttk.Label(header, text='素材批量重命名', font=('Microsoft YaHei UI', 12, 'bold')).pack(side='left')
        ttk.Button(header, text='检查更新', command=self.check_updates).pack(side='right')

        # A visibly raised divider can be dragged to change the height of the file area.
        pane = tk.PanedWindow(outer, orient='vertical', sashwidth=9, sashrelief='raised',
                              sashcursor='sb_v_double_arrow', borderwidth=0, opaqueresize=True)
        self.pane = pane
        pane.pack(fill='both', expand=True, pady=(3, 0))
        top = ttk.Frame(pane)
        pane.add(top, minsize=120, stretch='always')
        canvas = tk.Canvas(top, highlightthickness=0)
        bar = ttk.Scrollbar(top, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        form = ttk.Frame(canvas, padding=(2, 0, 4, 0))
        win = canvas.create_window((0, 0), window=form, anchor='nw')
        form.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(win, width=e.width))

        def scroll_form(event):
            widget = self.winfo_containing(event.x_root, event.y_root)
            while widget is not None:
                if widget is canvas or widget is form:
                    canvas.yview_scroll(-int(event.delta / 120), 'units')
                    return 'break'
                widget = widget.master
        self.bind_all('<MouseWheel>', scroll_form, add='+')

        def heading(text):
            ttk.Label(form, text=text, font=('Microsoft YaHei UI', 9, 'bold'), foreground='black').pack(anchor='w', pady=(3, 0))

        def flow(items, max_cols, min_cell, weights=None):
            container = ttk.Frame(form)
            container.pack(fill='x')
            widgets = [make(container) for make in items]
            state = {'cols': None}
            def layout(event):
                cols = max(1, min(max_cols, event.width // min_cell))
                if cols == state['cols']:
                    return
                state['cols'] = cols
                for i in range(max_cols):
                    weight = (weights[i] if weights and cols == max_cols else 1) if i < cols else 0
                    container.columnconfigure(i, weight=weight, uniform='flow' if i < cols else '')
                for i, widget in enumerate(widgets):
                    widget.grid(row=i // cols, column=i % cols, sticky='ew', padx=(0, 6), pady=1)
            container.bind('<Configure>', layout)
            return container

        def field(text, variable, kind='entry', values=None, width=12, bold=False, expand=True):
            def build(parent):
                item = ttk.Frame(parent)
                options = {'font': ('Microsoft YaHei UI', 9, 'bold'), 'foreground': 'black'} if bold else {}
                ttk.Label(item, text=text, **options).pack(side='left', padx=(0, 4))
                if kind == 'combo':
                    w = ttk.Combobox(item, textvariable=variable, values=values, state='readonly', width=width)
                else:
                    w = ttk.Entry(item, textvariable=variable, width=width)
                w.pack(side='left', fill='x' if expand else None, expand=expand)
                return item
            return build

        heading('基本信息')
        def editor_field(parent):
            item = ttk.Frame(parent)
            ttk.Label(item, text='剪辑简称+全名 *', font=('Microsoft YaHei UI', 9, 'bold'), foreground='black').pack(side='left', padx=(0, 4))
            ttk.Entry(item, textvariable=self.editor, width=13).pack(side='left', fill='x', expand=True)
            return item
        def leader_field(parent):
            item = ttk.Frame(parent)
            ttk.Checkbutton(item, text='组长自剪', variable=self.leader).pack(side='left')
            return item
        def operators_field(parent):
            item = ttk.Frame(parent)
            self.operator_label = ttk.Label(item, text='运营（多选） *', font=('Microsoft YaHei UI', 9, 'bold'), foreground='black')
            self.operator_label.pack(side='left', padx=(0, 4))
            self.operator_frame = ttk.Frame(item)
            self.operator_frame.pack(side='left')
            return item

        # Keep the two requested rows independent so reflow never moves the
        # product/date/operator group into the first row on narrow windows.
        flow([editor_field, leader_field,
              field('平台 *', self.platform, 'combo', list(PLATFORMS), 9, bold=True)], 3, 280)
        flow([field('产品 *', self.product, 'combo', list(PRODUCTS), 11, bold=True),
              field('日期 *', self.date, width=11, bold=True), operators_field], 3, 285, weights=(3, 3, 4))

        heading('素材分类')
        def third_field(parent):
            item = ttk.Frame(parent)
            ttk.Label(item, text='三级分类 *', font=('Microsoft YaHei UI', 9, 'bold'), foreground='black').pack(side='left', padx=(0, 4))
            for k in ('复刻', '迭代', '创新'):
                ttk.Radiobutton(item, text=k, variable=self.third, value=k).pack(side='left')
            return item
        flow([field('一级分类 *', self.first, 'combo', ['功效', '背书', '活动'], 20, bold=True, expand=False),
              field('二级分类 *', self.second, 'combo', ['口播', '混剪', '直播切片', '清水素材'], 20, bold=True, expand=False),
              third_field], 1, 1)
        heading('四级分类（按需填写）')
        items = [field(key, var, width=10) for key, var in self.fourth_text.items()]
        flow(items, 4, 205)
        flow([field('自定义素材名', self.title_text, width=20, expand=False)], 1, 1)
        def checkbox(key, var):
            def build(parent):
                item = ttk.Frame(parent)
                ttk.Checkbutton(item, text=key, variable=var).pack(side='left')
                return item
            return build
        ttk.Label(form, text='其他标签（可多选）').pack(anchor='w', pady=(1, 0))
        flow([checkbox(k, v) for k, v in self.fourth_fixed.items()], 8, 100)
        heading('创意人员（没有可留空）')
        flow([field('AI组创意人员', self.ai_person, 'combo', [''] + AI_PEOPLE, 11),
              field('AI组创意类型', self.ai_type, 'combo', ['', '输出创意AI', '承接创意AI'], 11),
              field('编导创意', self.director, 'combo', [''] + DIRECTORS, 11)], 3, 230)
        ttk.Label(form, text='带*为必选项，点击“生成预览”可查看当前素材的命名结果', foreground='#555').pack(anchor='w', pady=(1, 1))

        bottom = ttk.Frame(pane)
        pane.add(bottom, minsize=110, stretch='always')
        controls = ttk.Frame(bottom)
        controls.pack(fill='x', pady=2)
        for text, fn in [('添加文件', self.add_files), ('移除选中', self.remove_files), ('清空列表', self.clear_files), ('生成预览', self.preview), ('执行重命名', self.execute)]:
            ttk.Button(controls, text=text, command=fn).pack(side='left', padx=(0, 5))
        ttk.Label(controls, text='↑ 拖动分隔条调整列表高度').pack(side='left', padx=4)
        self.tree = ttk.Treeview(bottom, columns=('old', 'title', 'operator', 'new', 'status'), show='headings', selectmode='extended')
        for col, title, width in [('old', '原文件（含路径）', 290), ('title', '单独素材名', 120), ('operator', '分配运营', 85), ('new', '预览文件名', 480), ('status', '状态', 180)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, minwidth=80)
        vs = ttk.Scrollbar(bottom, orient='vertical', command=self.tree.yview)
        hs = ttk.Scrollbar(bottom, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        hs.pack(side='bottom', fill='x')
        vs.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<Double-1>', self.edit_title)
        ttk.Label(outer, textvariable=self.status, foreground='#314e6b').pack(fill='x', pady=(3, 0))
        def initial_split():
            # Fit the whole form where possible while leaving a usable file list.
            self.update_idletasks()
            bbox = canvas.bbox('all')
            if bbox:
                position = min(bbox[3] + 4, max(120, pane.winfo_height() - 125))
                pane.sash_place(0, 0, position)
        self._initial_split = initial_split
        # Prefer a full-screen workspace so both the form and file list are visible.
        try:
            self.state('zoomed')
        except tk.TclError:
            self.geometry(f'{min(1360, self.winfo_screenwidth())}x{min(760, self.winfo_screenheight())}')

    def check_updates(self):
        if not startup_update_check(self, UPDATE_MANIFEST_URL, UPDATE_REPOSITORY, manual=True):
            self.close_app()

    def restore_settings(self):
        data = self._saved_settings
        def assign(var, key, valid=None):
            value = data.get(key)
            if isinstance(value, str) and (valid is None or value in valid):
                var.set(value)

        assign(self.editor, 'editor')
        if isinstance(data.get('leader'), bool): self.leader.set(data['leader'])
        assign(self.platform, 'platform', PLATFORMS)
        assign(self.product, 'product', PRODUCTS)
        self.date.set(settings.restored_date(data))
        assign(self.first, 'first', ('功效', '背书', '活动'))
        assign(self.second, 'second', ('口播', '混剪', '直播切片', '清水素材'))
        assign(self.third, 'third', ('', '复刻', '迭代', '创新'))
        assign(self.title_text, 'title_text')
        assign(self.ai_person, 'ai_person', [''] + AI_PEOPLE)
        assign(self.ai_type, 'ai_type', ('', '输出创意AI', '承接创意AI'))
        assign(self.director, 'director', [''] + DIRECTORS)
        fourth_text = data.get('fourth_text')
        if isinstance(fourth_text, dict):
            for key, var in self.fourth_text.items():
                value = fourth_text.get(key)
                if isinstance(value, str): var.set(value)
        fourth_fixed = data.get('fourth_fixed')
        if isinstance(fourth_fixed, dict):
            for key, var in self.fourth_fixed.items():
                value = fourth_fixed.get(key)
                if isinstance(value, bool): var.set(value)
        chosen = data.get('operators')
        if isinstance(chosen, list):
            for key, var in self.operator_vars.items(): var.set(key in chosen)

        files = data.get('files')
        missing = 0
        if isinstance(files, list):
            seen = set()
            for item in files:
                if not isinstance(item, dict) or not isinstance(item.get('path'), str):
                    continue
                path = Path(item['path'])
                try:
                    key = os.path.normcase(str(path.resolve()))
                    if not path.is_file():
                        missing += 1
                    elif key not in seen:
                        title = item.get('title', '')
                        self.files.append({'path': path, 'title': title if isinstance(title, str) else ''})
                        seen.add(key)
                except (OSError, ValueError):
                    missing += 1
            self.draw()
        if missing:
            self.status.set(f'已恢复上次内容；{missing} 个文件已不存在，已从列表移除。')
        elif self.files:
            self.status.set(f'已恢复上次内容和 {len(self.files)} 个文件，请重新生成预览。')

        geometry = data.get('geometry')
        match = re.fullmatch(r'(\d+)x(\d+)([+-]\d+)([+-]\d+)', geometry or '') if isinstance(geometry, str) else None
        if match:
            width, height, x, y = map(int, match.groups())
            screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
            width = max(680, min(width, screen_w))
            height = max(500, min(height, screen_h))
            x = max(0, min(x, max(0, screen_w - width)))
            y = max(0, min(y, max(0, screen_h - height)))
            self.state('normal')
            self.geometry(f'{width}x{height}+{x}+{y}')
            self._normal_geometry = f'{width}x{height}+{x}+{y}'
        if data.get('maximized') is True:
            try: self.state('zoomed')
            except tk.TclError: pass
        elif match:
            self.state('normal')

        def restore_split():
            self.update_idletasks()
            sash = data.get('sash')
            if isinstance(sash, int) and not isinstance(sash, bool) and 120 <= sash <= self.pane.winfo_height() - 110:
                self.pane.sash_place(0, 0, sash)
            else:
                self._initial_split()
        self.after(150, restore_split)

    def setup_autosave(self):
        variables = [self.editor, self.leader, self.platform, self.product, self.date,
                     self.first, self.second, self.third, self.title_text,
                     self.ai_person, self.ai_type, self.director]
        variables += list(self.fourth_text.values()) + list(self.fourth_fixed.values())
        for var in variables: var.trace_add('write', self.schedule_save)
        self.bind('<Configure>', self.window_changed, add='+')
        self.pane.bind('<ButtonRelease-1>', self.schedule_save, add='+')
        self._settings_ready = True

    def window_changed(self, event):
        if event.widget is not self: return
        if self.state() == 'normal':
            self._normal_geometry = self.geometry()
        self.schedule_save()

    def schedule_save(self, *_):
        if not self._settings_ready: return
        if self._settings_timer is not None:
            try: self.after_cancel(self._settings_timer)
            except tk.TclError: pass
        self._settings_timer = self.after(500, self.save_current_settings)

    def save_current_settings(self):
        self._settings_timer = None
        state = self.state()
        if state == 'normal': self._normal_geometry = self.geometry()
        try: sash = self.pane.sash_coord(0)[1]
        except tk.TclError: sash = None
        data = {'editor': self.editor.get(), 'leader': self.leader.get(),
                'platform': self.platform.get(), 'product': self.product.get(),
                'date': self.date.get(), '_saved_on': dt.date.today().isoformat(),
                'first': self.first.get(), 'second': self.second.get(), 'third': self.third.get(),
                'title_text': self.title_text.get(), 'ai_person': self.ai_person.get(),
                'ai_type': self.ai_type.get(), 'director': self.director.get(),
                'fourth_text': {k: v.get() for k, v in self.fourth_text.items()},
                'fourth_fixed': {k: v.get() for k, v in self.fourth_fixed.items()},
                'operators': self.selected_operators(),
                'files': [{'path': str(f['path']), 'title': f['title']} for f in self.files],
                'geometry': self._normal_geometry, 'maximized': state == 'zoomed', 'sash': sash}
        settings.save_settings(data)

    def close_app(self):
        if self._settings_timer is not None:
            try: self.after_cancel(self._settings_timer)
            except tk.TclError: pass
            self._settings_timer = None
        self.save_current_settings()
        self.destroy()

    def update_operators(self, *_):
        p, product = self.platform.get(), self.product.get()
        self.operator_label.configure(text='运营（多选） *' if p in ('抖音', '抖音图文') else '运营（多选）')
        for widget in self.operator_frame.winfo_children(): widget.destroy()
        self.operator_vars = {}
        if p in ('抖音', '抖音图文'):
            values = OPERATORS.get((p, product), []) + ['李想']
            for value in values:
                var = tk.BooleanVar(value=value != '李想')
                var.trace_add('write', self.schedule_save)
                self.operator_vars[value] = var
                ttk.Checkbutton(self.operator_frame, text=value, variable=var).pack(side='left', padx=2)
        else:
            ttk.Label(self.operator_frame, text='无需运营', foreground='#666').pack(side='left')

    def selected_operators(self):
        return [k for k, var in self.operator_vars.items() if var.get()]

    def operator_for(self, index):
        selected = self.selected_operators()
        return selected[index % len(selected)] if selected else ''

    def add_paths(self, selected):
        existing = {os.path.normcase(str(x['path'].resolve())) for x in self.files}
        skipped = 0
        for value in selected:
            path = Path(value)
            if not path.is_file():
                skipped += 1
                continue
            key = os.path.normcase(str(path.resolve()))
            if key not in existing:
                self.files.append({'path': path, 'title': ''}); existing.add(key)
        self.draw()
        notice = f'；已忽略 {skipped} 个文件夹或无效路径' if skipped else ''
        self.status.set(f'已选择 {len(self.files)} 个文件{notice}。修改规则后请重新预览。')

    def add_files(self):
        self.add_paths(filedialog.askopenfilenames(title='选择需要重命名的文件'))

    def drop_files(self, event):
        self.add_paths(self.tk.splitlist(event.data))
        return 'copy'

    def remove_files(self):
        selected = {int(i) for i in self.tree.selection()}
        self.files = [f for i, f in enumerate(self.files) if i not in selected]
        self.draw()

    def clear_files(self):
        self.files.clear(); self.draw()

    def edit_title(self, event):
        row = self.tree.identify_row(event.y)
        if not row: return
        file = self.files[int(row)]
        new = simpledialog.askstring('单独设置素材名', '输入素材名；留空则使用自定义素材名或原文件名：', initialvalue=file['title'], parent=self)
        if new is not None:
            file['title'] = new; self.draw()
            self.status.set('素材名已修改，请重新生成预览。')

    def draw(self, preview=None):
        self.tree.delete(*self.tree.get_children())
        for i, f in enumerate(self.files):
            result, status = preview[i] if preview is not None else ('', '')
            self.tree.insert('', 'end', iid=str(i), values=(str(f['path']), f['title'], self.operator_for(i) if preview is not None else '', result, status))
        self.schedule_save()

    def fields(self, f, index=0):
        fourth_text = [format_fourth(k, v.get()) for k, v in self.fourth_text.items() if v.get().strip()]
        fourth_fixed = [k for k, v in self.fourth_fixed.items() if v.get()]
        return {'editor': self.editor.get(), 'leader': self.leader.get(), 'platform': self.platform.get(),
                'product': self.product.get(), 'date': self.date.get(), 'first': self.first.get(),
                'second': self.second.get(), 'third': [self.third.get()] if self.third.get() else [],
                'fourth_text': fourth_text, 'fourth_fixed': fourth_fixed,
                'title': f['title'] or self.title_text.get(),
                'operator': self.operator_for(index), 'ai_person': self.ai_person.get(), 'ai_type': self.ai_type.get(),
                'director': self.director.get()}

    def prepare(self):
        if not self.files: raise ValueError('请先添加文件。')
        # Plan the whole batch before allocating suffixes. Duplicate material names
        # across the batch get a sequence even when their operators differ.
        drafts, counts = [], {}
        for i, f in enumerate(self.files, 1):
            source = f['path']
            try:
                if not source.is_file(): raise ValueError('源文件不存在或不是文件。')
                fields = self.fields(f, i - 1)
                name = make_name(fields, source, i, len(self.files))
                title = fields['title'].strip() or source.stem
                group = title.casefold()
                counts[group] = counts.get(group, 0) + 1
                drafts.append((source, fields, group, name, None))
            except (ValueError, OSError) as exc:
                drafts.append((source, None, None, None, str(exc)))

        # Preserve unique names even if another group happens to generate the same
        # name with a suffix, e.g. "示例_01" versus the first "示例".
        reserved = set()
        for source, fields, group, name, error in drafts:
            if error is None and counts[group] == 1:
                reserved.add(str(source.with_name(name).resolve()).casefold())

        previews, targets, next_number = [], [], {}
        for i, (source, fields, group, name, error) in enumerate(drafts, 1):
            try:
                if error is not None: raise ValueError(error)
                if counts[group] > 1:
                    number = next_number.get(group, 1)
                    while True:
                        if number > 999999: raise ValueError('可用序号不足，请调整素材名。')
                        fields['sequence'] = number
                        fields['sequence_width'] = max(2, len(str(counts[group])))
                        name = make_name(fields, source, i, len(self.files))
                        target = source.with_name(name)
                        key = str(target.resolve()).casefold()
                        number += 1
                        if key not in reserved and not target.exists(): break
                    next_number[group] = number
                    reserved.add(key)
                else:
                    target = source.with_name(name)
                    if target.exists():
                        if str(target.resolve()).casefold() == str(source.resolve()).casefold():
                            raise ValueError('目标名称与原名称相同。')
                        raise ValueError('目标文件已存在，不会覆盖。')
                previews.append((name, '可执行')); targets.append(target)
            except (ValueError, OSError) as exc:
                previews.append(('', str(exc))); targets.append(None)
        return previews, targets

    def preview(self):
        try:
            previews, targets = self.prepare()
            self.draw(previews)
            errors = sum(x is None for x in targets)
            self.status.set(f'共 {len(targets)} 个文件，{len(targets)-errors} 个可执行，{errors} 个需处理。执行前会再次校验。')
        except ValueError as exc: messagebox.showwarning('无法预览', str(exc), parent=self)

    def execute(self):
        try: previews, targets = self.prepare()
        except ValueError as exc:
            messagebox.showwarning('无法执行', str(exc), parent=self); return
        self.draw(previews)
        if any(t is None for t in targets):
            messagebox.showwarning('无法执行', '预览存在错误，处理所有错误后再执行。', parent=self); return
        if not messagebox.askyesno('确认重命名', f'将按当前预览重命名 {len(targets)} 个文件。确认执行？', parent=self): return
        completed = 0
        for i, (f, target) in enumerate(zip(self.files, targets)):
            try:
                if target.exists(): raise FileExistsError('目标文件已出现，已停止以防覆盖。')
                # On Windows os.rename refuses to replace an existing destination.
                os.rename(f['path'], target)
                f['path'] = target
                previews[i] = (target.name, '已完成')
                completed += 1
            except OSError as exc:
                previews[i] = (target.name, '失败：' + str(exc))
                for j in range(i + 1, len(previews)): previews[j] = (previews[j][0], '未执行')
                self.draw(previews)
                self.status.set(f'已完成 {completed} 个；发生错误，后续未执行。请查看列表。')
                messagebox.showerror('执行中止', f'已完成 {completed} 个，后续未执行。\n{exc}', parent=self)
                return
        self.draw(previews)
        self.status.set(f'重命名完成，共 {completed} 个文件。')
        messagebox.showinfo('完成', f'已成功重命名 {completed} 个文件。', parent=self)


if __name__ == '__main__':
    update_root = tk.Tk()
    update_root.withdraw()
    try:
        continue_to_app = startup_update_check(update_root, UPDATE_MANIFEST_URL, UPDATE_REPOSITORY)
    finally:
        update_root.destroy()
    if continue_to_app:
        App().mainloop()

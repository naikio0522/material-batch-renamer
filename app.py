import datetime as dt
import os
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
from updater import CURRENT_VERSION, startup_update_check, is_newer
import settings
import layout_schema


from dataclasses import replace
from rename_core import (
    PRODUCTS, PLATFORMS, OPERATORS, AI_PEOPLE, DIRECTORS,
    RenamePlan, build_rename_plan, make_name, format_fourth,
)

UPDATE_REPOSITORY = 'naikio0522/material-batch-renamer'
UPDATE_MANIFEST_URL = 'https://github.com/naikio0522/material-batch-renamer/raw/refs/heads/main/update.json'
UI_LAYOUT_REVISION = '1.3-serial-and-file-checkboxes'
TABLE_COLUMNS = ('checked', 'old', 'title', 'operator', 'new', 'status')
FILE_PANE_MIN_HEIGHT = 80

class App(TkinterDnD.Tk):
    def __init__(self, shared_manifest=None, initial_settings=None):
        super().__init__()
        self._saved_settings = settings.load_settings() if initial_settings is None else initial_settings
        self._settings_ready = False
        self._settings_timer = None
        self._restore_job = None
        self._layout_job = None
        self._refresh_job = None
        self._normal_geometry = None
        self._heading_drag = None
        self._sash_manual = self._saved_settings.get('ui_layout_revision') == UI_LAYOUT_REVISION and self._saved_settings.get('sash_manual') is True
        self._layout_fields = {}
        self._layout_flows = {}
        self._layout_revision = self._saved_settings.get('layout_revision', '')
        shared = shared_manifest or {}
        remote_revision = shared.get('layout_revision', '')
        try:
            newer_layout = bool(shared.get('layout') and (not self._layout_revision or is_newer(remote_revision, self._layout_revision)))
        except (ValueError, TypeError):
            newer_layout = False
        self.layout_config = layout_schema.sanitize_layout(shared.get('layout') if newer_layout else self._saved_settings.get('layout'))
        self._apply_shared_window = newer_layout
        if newer_layout: self._layout_revision = remote_revision
        self.title('素材批量重命名工具 v' + CURRENT_VERSION)
        self.geometry('1240x860')
        self.minsize(680, 500)
        self.files = []
        self.editor = tk.StringVar()
        self.platform = tk.StringVar(value='抖音')
        self.product = tk.StringVar(value='修护牙膏')
        self.date = tk.StringVar(value=dt.date.today().isoformat())
        self.serial = tk.StringVar(value='#')
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
        self.title_label = ttk.Label(header, text='素材批量重命名', font=('Microsoft YaHei UI', 12, 'bold'))
        self.title_label.pack(side='left')
        self.update_button = ttk.Button(header, text='检查更新', command=self.check_updates)
        self.update_button.pack(side='left', padx=(20, 0))

        # A visibly raised divider can be dragged to change the height of the file area.
        pane = tk.PanedWindow(outer, orient='vertical', sashwidth=9, sashrelief='raised',
                              sashcursor='sb_v_double_arrow', borderwidth=0, opaqueresize=True)
        self.pane = pane
        pane.pack(fill='both', expand=True, pady=(3, 0))
        top = ttk.Frame(pane)
        pane.add(top, minsize=120, stretch='always')
        canvas = tk.Canvas(top, highlightthickness=0)
        self._form_canvas = canvas
        bar = ttk.Scrollbar(top, orient='vertical', command=canvas.yview)
        horizontal = ttk.Scrollbar(top, orient='horizontal', command=canvas.xview)
        canvas.configure(yscrollcommand=bar.set, xscrollcommand=horizontal.set)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        form = ttk.Frame(canvas, padding=(2, 0, 4, 0))
        self._form_frame = form
        win = canvas.create_window((0, 0), window=form, anchor='nw')
        form.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        def size_form(event=None):
            available = event.width if event else canvas.winfo_width()
            minimum = max([340] + [widget.master.winfo_reqwidth() + 12 for name, widget in self._layout_fields.items() if name != '自定义素材名'])
            if hasattr(self, 'operator_frame'):
                minimum = max(minimum, self.operator_frame.master.winfo_reqwidth() + 12)
            if hasattr(self, '_material_name_label'):
                minimum = max(minimum, self._material_name_label.winfo_reqwidth() + self._layout_fields['自定义素材名'].winfo_reqwidth() + 22)
                self._material_name_row.configure(width=max(300, available - 6))
            if hasattr(self, '_hint_label'):
                minimum = max(minimum, self._hint_label.winfo_reqwidth() + 12)
            content_width = max(available, minimum)
            canvas.itemconfigure(win, width=content_width)
            if minimum > available:
                if not horizontal.winfo_manager(): horizontal.pack(side='top', fill='x', before=canvas)
            elif horizontal.winfo_manager():
                horizontal.pack_forget()
                canvas.xview_moveto(0)
        self._size_form = size_form
        canvas.bind('<Configure>', size_form)

        def scroll_form(event):
            widget = self.winfo_containing(event.x_root, event.y_root)
            while widget is not None:
                if widget is canvas or widget is form:
                    canvas.yview_scroll(-int(event.delta / 120), 'units')
                    return 'break'
                widget = widget.master
        self.bind_all('<MouseWheel>', scroll_form, add='+')

        self._section_headings = {}
        def heading(text, major=False):
            label = ttk.Label(form, text=text, font=('Microsoft YaHei UI', 12 if major else 9, 'bold'), foreground='black')
            label.pack(anchor='w', pady=(8 if major else 3, 3 if major else 0))
            self._section_headings[text] = label

        def flow(items, max_cols, min_cell, key=None):
            container = ttk.Frame(form)
            container.pack(fill='x')
            widgets = [make(container) for make in items]
            state = {'cols': None}
            def layout(event=None):
                available = event.width if event else container.winfo_width()
                configured = self.layout_config['columns'].get(key, max_cols)
                minimum = max([min_cell] + [w.winfo_reqwidth() + 8 for w in widgets])
                cols = max(7 if key == 'tags' else 1, min(configured, available // minimum))
                if cols == state['cols']:
                    return
                state['cols'] = cols
                for i in range(max_cols):
                    weight = 1 if i < cols else 0
                    container.columnconfigure(i, weight=weight, uniform='flow' if i < cols else '')
                for i, widget in enumerate(widgets):
                    widget.grid(row=i // cols, column=i % cols, sticky='ew', padx=(0, 6), pady=1)
            container.bind('<Configure>', layout)
            if key: self._layout_flows[key] = (state, layout)
            return container

        def field(text, variable, kind='entry', values=None, width=12, bold=False):
            def build(parent):
                item = ttk.Frame(parent)
                options = {'font': ('Microsoft YaHei UI', 9, 'bold'), 'foreground': 'black'} if bold else {}
                ttk.Label(item, text=text, **options).pack(side='left', padx=(0, 4))
                if kind == 'combo':
                    w = ttk.Combobox(item, textvariable=variable, values=values, state='readonly', width=width)
                else:
                    w = ttk.Entry(item, textvariable=variable, width=width)
                field_name = text.replace(' *', '')
                self._layout_fields[field_name] = w
                w.configure(width=self.layout_config['widths'].get(field_name, width))
                w.pack(side='left')
                return item
            return build

        heading('基本信息', major=True)
        basic = ttk.Frame(form)
        basic.pack(fill='x', pady=(0, 2))
        self._basic_grid = basic
        self._basic_labels = {}
        basic.columnconfigure(1, uniform='basic-input')
        basic.columnconfigure(3, uniform='basic-input')
        basic.columnconfigure(4, weight=1)
        for row, items in enumerate(((('剪辑', self.editor, None), ('平台', self.platform, list(PLATFORMS))),
                                     (('产品', self.product, list(PRODUCTS)), ('日期', self.date, None)))):
            for position, (name, variable, choices) in enumerate(items):
                column = position * 2
                label = ttk.Label(basic, text=name + ' *', font=('Microsoft YaHei UI', 9, 'bold'), foreground='black')
                label.grid(row=row, column=column, sticky='w', padx=(50 if position else 0, 0), pady=3)
                self._basic_labels[name] = label
                widget = ttk.Combobox(basic, textvariable=variable, values=choices, state='readonly', width=20) if choices is not None else ttk.Entry(basic, textvariable=variable, width=20)
                widget.grid(row=row, column=column + 1, sticky='ew', padx=(10, 0), pady=3)
                self._layout_fields[name] = widget
        operator_row = ttk.Frame(form)
        operator_row.pack(fill='x', pady=3)
        self.operator_label = ttk.Label(operator_row, text='运营（多选） *', font=('Microsoft YaHei UI', 9, 'bold'), foreground='black')
        self.operator_label.pack(side='left', padx=(0, 10))
        self.operator_frame = ttk.Frame(operator_row)
        self.operator_frame.pack(side='left')
        serial_row = ttk.Frame(form)
        serial_row.pack(fill='x', pady=3)
        ttk.Label(serial_row, text='序号标识 *', font=('Microsoft YaHei UI', 9, 'bold'), foreground='black').pack(side='left', padx=(0, 10))
        serial_entry = ttk.Entry(serial_row, textvariable=self.serial, width=20)
        serial_entry.pack(side='left')
        self._layout_fields['序号标识'] = serial_entry
        ttk.Label(serial_row, text='  # 自动编号；填数字则使用固定序号').pack(side='left')

        heading('素材分类', major=True)
        def third_field(parent):
            item = ttk.Frame(parent)
            ttk.Label(item, text='三级分类 *', font=('Microsoft YaHei UI', 9, 'bold'), foreground='black').pack(side='left', padx=(0, 4))
            for k in ('复刻', '迭代', '创新'):
                ttk.Radiobutton(item, text=k, variable=self.third, value=k).pack(side='left')
            return item
        flow([field('一级分类 *', self.first, 'combo', ['功效', '背书', '活动'], 20, bold=True),
              field('二级分类 *', self.second, 'combo', ['口播', '混剪', '直播切片', '清水素材'], 20, bold=True),
              third_field], 3, 200, key='category')
        heading('四级分类（按需填写）')
        fourth = ttk.Frame(form)
        fourth.pack(fill='x', pady=2)
        self._fourth_grid = fourth
        self._fourth_labels = {}
        display_names = {'官媒专场': '专场', '大促活动': '活动', '品牌活动事件': '品牌事件'}
        for pair in range(4):
            fourth.columnconfigure(pair * 2, uniform='fourth-label')
            fourth.columnconfigure(pair * 2 + 1, weight=1, uniform='fourth-input')
        for index, (key, variable) in enumerate(self.fourth_text.items()):
            row, pair = divmod(index, 4)
            name = display_names.get(key, key)
            label = ttk.Label(fourth, text=name, anchor='center')
            label.grid(row=row, column=pair * 2, sticky='ew', pady=3)
            widget = ttk.Entry(fourth, textvariable=variable, width=max(20, self.layout_config['widths'].get(name, 20)), justify='center' if row else 'left')
            widget.grid(row=row, column=pair * 2 + 1, sticky='ew', padx=(10, 14), pady=3)
            self._layout_fields[name] = widget
            self._fourth_labels[name] = label
        def checkbox(key, var):
            def build(parent):
                item = ttk.Frame(parent)
                ttk.Checkbutton(item, text=key, variable=var).pack(side='left')
                return item
            return build
        ttk.Label(form, text='其他标签（可多选）').pack(anchor='w', pady=(1, 0))
        flow([checkbox(k, v) for k, v in self.fourth_fixed.items()], 8, 80, key='tags')
        title_row = ttk.Frame(form)
        title_row.pack(anchor='w', pady=(4, 3))
        title_row.pack_propagate(False)
        self._material_name_row = title_row
        self._material_name_label = ttk.Label(title_row, text='自定义素材名', font=('Microsoft YaHei UI', 12, 'bold'), foreground='#c00000')
        self._material_name_label.pack(side='left', padx=(0, 10))
        material_entry = ttk.Entry(title_row, textvariable=self.title_text, width=20)
        material_entry.pack(side='left', fill='x', expand=True)
        self._layout_fields['自定义素材名'] = material_entry
        title_row.configure(height=max(self._material_name_label.winfo_reqheight(), material_entry.winfo_reqheight()))
        heading('创意人员', major=True)
        flow([field('AI组创意人员', self.ai_person, 'combo', [''] + AI_PEOPLE, 11),
              field('AI组创意类型', self.ai_type, 'combo', ['', '输出创意AI', '承接创意AI'], 11),
              field('编导创意', self.director, 'combo', [''] + DIRECTORS, 11)], 3, 200, key='creative')
        hint = ttk.Label(form, text='带*为必选项，点击“生成预览”可查看当前素材的命名结果', foreground='#555', wraplength=0)
        hint.pack(anchor='w', pady=(1, 0))
        self._hint_label = hint

        bottom = ttk.Frame(pane)
        pane.add(bottom, minsize=FILE_PANE_MIN_HEIGHT, stretch='always')
        controls = ttk.Frame(bottom)
        controls.pack(fill='x', pady=2)
        actions = [ttk.Button(controls, text=text, command=fn) for text, fn in [('添加文件', self.add_files), ('移除选中', self.remove_files), ('清空列表', self.clear_files), ('全选', lambda: self.set_all_checked(True)), ('全不选', lambda: self.set_all_checked(False)), ('生成预览', self.preview), ('执行重命名', self.execute)]]
        actions.append(ttk.Label(controls, text='↑ 拖动分隔条调整列表高度'))
        def layout_actions(event):
            row, column, occupied = 0, 0, 0
            for widget in actions:
                width = widget.winfo_reqwidth() + 6
                if column and occupied + width > event.width:
                    row, column, occupied = row + 1, 0, 0
                widget.grid(row=row, column=column, sticky='w', padx=(0, 6), pady=2)
                column, occupied = column + 1, occupied + width
        controls.bind('<Configure>', layout_actions)
        self.tree = ttk.Treeview(bottom, columns=TABLE_COLUMNS, displaycolumns=TABLE_COLUMNS, show='headings', selectmode='extended')
        for col, title, width in [('checked', '☑', 48), ('old', '原文件（含路径）', 290), ('title', '单独素材名', 120), ('operator', '分配运营', 85), ('new', '预览文件名', 480), ('status', '状态', 180)]:
            centered = col in ('checked', 'operator', 'status')
            self.tree.heading(col, text=title, anchor='center' if centered else 'w')
            self.tree.column(col, width=width, minwidth=48 if col == 'checked' else 80, stretch=col != 'checked', anchor='center' if centered else 'w')
        self.tree.heading('checked', command=self.toggle_all_checked)
        vs = ttk.Scrollbar(bottom, orient='vertical', command=self.tree.yview)
        hs = ttk.Scrollbar(bottom, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        hs.pack(side='bottom', fill='x')
        vs.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<Double-1>', self.edit_title)
        self.tree.bind('<Button-1>', self.on_tree_click)
        self.tree.bind('<B1-Motion>', self.drag_heading)
        self.tree.bind('<ButtonRelease-1>', self.finish_heading_drag)
        self.tree.bind('<space>', self.toggle_highlighted)
        status_label = ttk.Label(outer, textvariable=self.status, foreground='#314e6b', wraplength=1000)
        status_label.pack(fill='x', pady=(3, 0))
        status_label.bind('<Configure>', lambda event: status_label.configure(wraplength=max(280, event.width)))
        def initial_split(fit_window=False):
            # Default to exactly 10px below the single-line hint where space allows.
            self.update_idletasks()
            position = hint.winfo_rooty() + hint.winfo_height() + 10 - pane.winfo_rooty()
            maximum = max(120, pane.winfo_height() - FILE_PANE_MIN_HEIGHT - int(pane.cget('sashwidth')))
            if fit_window and position > maximum and self.state() != 'zoomed':
                self.state('zoomed')
                if self._layout_job is not None:
                    try: self.after_cancel(self._layout_job)
                    except tk.TclError: pass
                def fit_after_maximize():
                    self._layout_job = None
                    initial_split()
                    self.schedule_save()
                self._layout_job = self.after(100, fit_after_maximize)
                return
            position = min(max(120, position), maximum)
            pane.sash_place(0, 0, position)
        self._initial_split = initial_split
        # Prefer a full-screen workspace so both the form and file list are visible.
        try:
            self.state('zoomed')
        except tk.TclError:
            self.geometry(f'{min(1360, self.winfo_screenwidth())}x{min(760, self.winfo_screenheight())}')

    def check_updates(self):
        if not startup_update_check(self, UPDATE_MANIFEST_URL, UPDATE_REPOSITORY, manual=True, on_manifest=self._receive_shared_layout):
            self.close_app()

    def _receive_shared_layout(self, manifest):
        revision = manifest.get('layout_revision', '')
        try:
            newer = bool(manifest.get('layout') and (not self._layout_revision or is_newer(revision, self._layout_revision)))
        except (ValueError, TypeError):
            newer = False
        if newer and not is_newer(manifest['version']):
            self._layout_revision = revision
            self.apply_layout(manifest['layout'])

    def _refresh_layout(self):
        self.update_idletasks()
        self._size_form()
        for state, layout in self._layout_flows.values():
            state['cols'] = None
            layout()

    def _queued_refresh(self):
        self._refresh_job = None
        self._refresh_layout()

    def apply_layout(self, config, change_window=True):
        self.layout_config = layout_schema.sanitize_layout(config)
        for name, widget in self._layout_fields.items():
            if name in self.layout_config['widths']:
                widget.configure(width=self.layout_config['widths'][name])
        self._refresh_layout()
        if change_window:
            saved_position = self.pane.sash_coord(0)[1]
            if self._layout_job is not None:
                try: self.after_cancel(self._layout_job)
                except tk.TclError: pass
                self._layout_job = None
            window = self.layout_config['window']
            self.state('normal')
            self.geometry(f"{window['width']}x{window['height']}")
            if window['maximized']:
                try: self.state('zoomed')
                except tk.TclError: pass
            def set_split():
                self._layout_job = None
                if self._sash_manual:
                    height = self.pane.winfo_height()
                    self.pane.sash_place(0, 0, min(max(120, saved_position), max(120, height - FILE_PANE_MIN_HEIGHT - 9)))
                else:
                    self._initial_split(fit_window=True)
                self.schedule_save()
            self._layout_job = self.after(150, set_split)
        self.schedule_save()

    def restore_settings(self):
        data = self._saved_settings
        def assign(var, key, valid=None):
            value = data.get(key)
            if isinstance(value, str) and (valid is None or value in valid):
                var.set(value)

        assign(self.editor, 'editor')
        assign(self.platform, 'platform', PLATFORMS)
        assign(self.product, 'product', PRODUCTS)
        self.date.set(settings.restored_date(data))
        assign(self.first, 'first', ('功效', '背书', '活动'))
        assign(self.second, 'second', ('口播', '混剪', '直播切片', '清水素材'))
        assign(self.third, 'third', ('', '复刻', '迭代', '创新'))
        assign(self.title_text, 'title_text')
        assign(self.serial, 'serial')
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
                        self.files.append({'path': path, 'title': title if isinstance(title, str) else '', 'checked': item.get('checked', True) is not False})
                        seen.add(key)
                except (OSError, ValueError):
                    missing += 1
            self.draw()
        if missing:
            self.status.set(f'已恢复上次内容；{missing} 个文件已不存在，已从列表移除。')
        elif self.files:
            self.status.set(f'已恢复上次内容和 {len(self.files)} 个文件，请重新生成预览。')

        column_order = data.get('column_order')
        if isinstance(column_order, list) and len(column_order) == len(TABLE_COLUMNS) and set(column_order) == set(TABLE_COLUMNS):
            self.tree.configure(displaycolumns=('checked', *(key for key in column_order if key != 'checked')))
        column_widths = data.get('column_widths')
        if isinstance(column_widths, dict):
            for key in TABLE_COLUMNS[1:]:
                value = column_widths.get(key)
                if isinstance(value, int) and not isinstance(value, bool): self.tree.column(key, width=max(80, min(3000, value)))

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
            self._restore_job = None
            self.update_idletasks()
            sash = data.get('sash')
            if self._sash_manual and isinstance(sash, int) and not isinstance(sash, bool) and 120 <= sash <= self.pane.winfo_height() - FILE_PANE_MIN_HEIGHT:
                self.pane.sash_place(0, 0, sash)
            else:
                self._initial_split(fit_window=True)
        self._restore_job = self.after(150, restore_split)
        if self._apply_shared_window:
            self._layout_job = self.after(250, lambda: self.apply_layout(self.layout_config))

    def setup_autosave(self):
        variables = [self.editor, self.platform, self.product, self.date,
                     self.first, self.second, self.third, self.title_text, self.serial,
                     self.ai_person, self.ai_type, self.director]
        variables += list(self.fourth_text.values()) + list(self.fourth_fixed.values())
        for var in variables: var.trace_add('write', self.schedule_save)
        self.bind('<Configure>', self.window_changed, add='+')
        self.pane.bind('<ButtonRelease-1>', self.sash_dragged, add='+')
        self._settings_ready = True

    def window_changed(self, event):
        if event.widget is not self: return
        if self.state() == 'normal':
            self._normal_geometry = self.geometry()
        self.schedule_save()

    def sash_dragged(self, _event=None):
        self._sash_manual = True
        self.schedule_save()

    def schedule_save(self, *_):
        if not self._settings_ready: return
        if self._settings_timer is not None:
            try: self.after_cancel(self._settings_timer)
            except tk.TclError: pass
        self._settings_timer = self.after(500, self.save_current_settings)

    def save_current_settings(self):
        if self._settings_timer is not None:
            try: self.after_cancel(self._settings_timer)
            except tk.TclError: pass
        self._settings_timer = None
        state = self.state()
        if state == 'normal': self._normal_geometry = self.geometry()
        try: sash = self.pane.sash_coord(0)[1]
        except tk.TclError: sash = None
        data = {'editor': self.editor.get(),
                'platform': self.platform.get(), 'product': self.product.get(),
                'date': self.date.get(), '_saved_on': dt.date.today().isoformat(),
                'serial': self.serial.get(),
                'first': self.first.get(), 'second': self.second.get(), 'third': self.third.get(),
                'title_text': self.title_text.get(), 'ai_person': self.ai_person.get(),
                'ai_type': self.ai_type.get(), 'director': self.director.get(),
                'fourth_text': {k: v.get() for k, v in self.fourth_text.items()},
                'fourth_fixed': {k: v.get() for k, v in self.fourth_fixed.items()},
                'operators': self.selected_operators(),
                'files': [{'path': str(f['path']), 'title': f['title'], 'checked': f.get('checked', True)} for f in self.files],
                'column_order': list(self.tree.cget('displaycolumns')),
                'column_widths': {key: self.tree.column(key, 'width') for key in TABLE_COLUMNS[1:]},
                'geometry': self._normal_geometry, 'maximized': state == 'zoomed', 'sash': sash,
                'layout': self.layout_config, 'layout_revision': self._layout_revision,
                'ui_layout_revision': UI_LAYOUT_REVISION, 'sash_manual': self._sash_manual}
        settings.save_settings(data)

    def close_app(self):
        if self._refresh_job is not None:
            try: self.after_cancel(self._refresh_job)
            except tk.TclError: pass
            self._refresh_job = None
        if self._layout_job is not None:
            try: self.after_cancel(self._layout_job)
            except tk.TclError: pass
            self._layout_job = None
        if self._restore_job is not None:
            try: self.after_cancel(self._restore_job)
            except tk.TclError: pass
            self._restore_job = None
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
        if self._refresh_job is not None:
            try: self.after_cancel(self._refresh_job)
            except tk.TclError: pass
        self._refresh_job = self.after_idle(self._queued_refresh)

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
                self.files.append({'path': path, 'title': '', 'checked': True}); existing.add(key)
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
        self.draw(preserve_view=False)

    def clear_files(self):
        self.files.clear(); self.draw()

    def edit_title(self, event):
        if self.tree.identify_region(event.x, event.y) != 'cell' or self.column_at(event.x) == 'checked': return 'break'
        row = self.tree.identify_row(event.y)
        if not row: return
        file = self.files[int(row)]
        new = simpledialog.askstring('单独设置素材名', '输入素材名；留空则使用自定义素材名或原文件名：', initialvalue=file['title'], parent=self)
        if new is not None:
            file['title'] = new; self.draw()
            self.status.set('素材名已修改，请重新生成预览。')

    def column_at(self, x):
        column = self.tree.identify_column(x)
        order = tuple(self.tree.cget('displaycolumns'))
        index = int(column[1:]) - 1 if column else -1
        return order[index] if 0 <= index < len(order) else None

    def on_tree_click(self, event):
        self._heading_drag = None
        region = self.tree.identify_region(event.x, event.y)
        column = self.column_at(event.x)
        if region == 'heading' and column != 'checked':
            self._heading_drag = (column, event.x)
        elif region == 'cell' and column == 'checked':
            row = self.tree.identify_row(event.y)
            if row:
                file = self.files[int(row)]
                file['checked'] = not file.get('checked', True)
                self.tree.focus(row)
                self.selection_changed()
            return 'break'

    def drag_heading(self, event):
        if self._heading_drag and abs(event.x - self._heading_drag[1]) > 5:
            self.tree.configure(cursor='fleur')
            return 'break'

    def finish_heading_drag(self, event):
        drag = self._heading_drag
        self._heading_drag = None
        self.tree.configure(cursor='')
        if drag and abs(event.x - drag[1]) > 5:
            target = self.column_at(event.x)
            order = list(self.tree.cget('displaycolumns'))
            if target in order and drag[0] in order:
                destination = max(1, order.index(target))
                order.remove(drag[0])
                order.insert(min(destination, len(order)), drag[0])
                self.tree.configure(displaycolumns=order)
        self.schedule_save()

    def set_all_checked(self, checked):
        for file in self.files: file['checked'] = checked
        self.selection_changed()

    def toggle_all_checked(self):
        self.set_all_checked(not (self.files and all(file.get('checked', True) for file in self.files)))

    def toggle_highlighted(self, _event=None):
        rows = self.tree.selection() or ((self.tree.focus(),) if self.tree.focus() else ())
        for row in rows:
            file = self.files[int(row)]
            file['checked'] = not file.get('checked', True)
        self.selection_changed()
        return 'break'

    def selection_changed(self):
        self.draw()
        count = sum(file.get('checked', True) for file in self.files)
        self.status.set(f'已勾选 {count} / {len(self.files)} 个素材，请生成预览。')

    def draw(self, plan=None, preserve_view=True):
        selected = self.tree.selection() if preserve_view else ()
        focus = self.tree.focus() if preserve_view else ''
        yview, xview = self.tree.yview(), self.tree.xview()
        self.tree.delete(*self.tree.get_children())
        for i, f in enumerate(self.files):
            checked = f.get('checked', True)
            item = plan.items[i] if plan is not None else None
            filename, status, operator = (item.filename, item.status, item.operator) if item else ('', '' if checked else '未勾选', '')
            self.tree.insert('', 'end', iid=str(i), values=('☑' if checked else '☐', str(f['path']), f['title'], operator, filename, status))
        valid = self.tree.get_children()
        self.tree.selection_set([row for row in selected if row in valid])
        if focus in valid: self.tree.focus(focus)
        if yview: self.tree.yview_moveto(yview[0])
        if xview: self.tree.xview_moveto(xview[0])
        self.tree.heading('checked', text='☑' if self.files and all(f.get('checked', True) for f in self.files) else '☐')
        self.schedule_save()

    def fields(self, f, index=0):
        fourth_text = [format_fourth(k, v.get()) for k, v in self.fourth_text.items() if v.get().strip()]
        fourth_fixed = [k for k, v in self.fourth_fixed.items() if v.get()]
        return {'editor': self.editor.get(), 'platform': self.platform.get(),
                'product': self.product.get(), 'date': self.date.get(), 'serial': self.serial.get(), 'first': self.first.get(),
                'second': self.second.get(), 'third': [self.third.get()] if self.third.get() else [],
                'fourth_text': fourth_text, 'fourth_fixed': fourth_fixed,
                'title': f['title'] or self.title_text.get(),
                'operator': self.operator_for(index), 'ai_person': self.ai_person.get(), 'ai_type': self.ai_type.get(),
                'director': self.director.get()}

    def prepare(self):
        return build_rename_plan(self.files, self.fields)

    def preview(self):
        try:
            plan = self.prepare()
        except ValueError as exc:
            messagebox.showwarning('无法预览', str(exc), parent=self)
            return
        self.draw(plan)
        self.status.set(f'已勾选 {len(plan.selected)} 个素材，{len(plan.operations)} 个可执行，{len(plan.errors)} 个需处理。')

    def execute(self):
        try:
            plan = self.prepare()
        except ValueError as exc:
            messagebox.showwarning('无法执行', str(exc), parent=self)
            return
        self.draw(plan)
        if plan.errors:
            messagebox.showwarning('无法执行', '勾选素材的预览存在错误，处理后再执行。', parent=self)
            return
        if not messagebox.askyesno('确认重命名', f'将按当前预览重命名勾选的 {len(plan.operations)} 个素材。确认执行？', parent=self):
            return
        results = list(plan.items)
        completed = 0
        for operation_index, item in enumerate(plan.operations):
            try:
                if item.target.exists():
                    raise FileExistsError('目标文件已出现，已停止以防覆盖。')
                # Windows os.rename refuses an existing destination.
                os.rename(item.source, item.target)
                self.files[item.row_index]['path'] = item.target
                results[item.row_index] = replace(item, status='已完成')
                completed += 1
            except OSError as exc:
                results[item.row_index] = replace(item, status='失败：' + str(exc))
                for remaining in plan.operations[operation_index + 1:]:
                    results[remaining.row_index] = replace(remaining, status='未执行')
                self.draw(RenamePlan(tuple(results)))
                self.status.set(f'已完成 {completed} 个；发生错误，后续未执行。')
                messagebox.showerror('执行中止', f'已完成 {completed} 个，后续未执行。\n{exc}', parent=self)
                return
        self.draw(RenamePlan(tuple(results)))
        self.status.set(f'重命名完成，共 {completed} 个素材。未勾选的素材保持原名。')
        messagebox.showinfo('完成', f'已成功重命名 {completed} 个素材。', parent=self)


if __name__ == '__main__':
    application = App()
    def startup_check():
        if not startup_update_check(application, UPDATE_MANIFEST_URL, UPDATE_REPOSITORY, on_manifest=application._receive_shared_layout):
            application.close_app()
    application.after(250, startup_check)
    application.mainloop()

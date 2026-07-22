import os
import sqlite3
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

import ttkbootstrap as ttk
from ttkbootstrap.dialogs import Messagebox


DB_NAME = "notes.db"
APP_VERSION = "1.4.0"
PAGE_SIZE = 25  # сколько заметок на странице
APP_NAME = "ZeeroNotes"  # для папки в APPDATA


# ---------- Работа с PIN в APPDATA ----------

def get_pin_path() -> Path:
    """
    Возвращает путь к файлу PIN в пользовательской папке.
    На Windows: %APPDATA%\ZeeroNotes\pin.cfg
    На других ОС: ~/ZeeroNotes/pin.cfg (fallback).
    """
    appdata = os.getenv("APPDATA")
    if appdata:
        base = Path(appdata)
    else:
        base = Path.home()
    app_dir = base / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / "pin.cfg"


def read_pin() -> str:
    """
    Читает PIN из APPDATA. Если файла нет или нет доступа, создаёт "1234" по умолчанию.
    """
    pin_path = get_pin_path()

    if not pin_path.exists():
        try:
            pin_path.write_text("1234", encoding="utf-8")
            return "1234"
        except OSError:
            # если вообще нет прав на запись — просто вернём дефолтный PIN
            return "1234"

    try:
        return pin_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "1234"


def show_pin_dialog(root: ttk.Window) -> bool:
    """Модальное окно ввода PIN. True — доступ разрешён, False — выход."""
    pin_correct = read_pin()

    dialog = ttk.Toplevel(root)
    dialog.title("Авторизация Zeero заметки")
    dialog.geometry("340x190")
    dialog.transient(root)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=16)
    frame.pack(fill=tk.BOTH, expand=tk.YES)

    ttk.Label(
        frame,
        text="Введите PIN для доступа к Zeero заметки",
        bootstyle="secondary",
        font=("Segoe UI", 10, "bold"),
        wraplength=280,
    ).pack(pady=(0, 12))

    pin_var = tk.StringVar()
    pin_entry = ttk.Entry(frame, textvariable=pin_var, show="*")
    pin_entry.pack(fill=tk.X)
    pin_entry.focus()

    status_label = ttk.Label(frame, text="", bootstyle="danger")
    status_label.pack(pady=(8, 12))

    allowed = {"value": False}

    def on_ok():
        if pin_var.get().strip() == pin_correct:
            allowed["value"] = True
            dialog.destroy()
        else:
            status_label.config(text="Неверный PIN")

    def on_cancel():
        allowed["value"] = False
        dialog.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X)

    ttk.Button(
        buttons,
        text="Войти",
        command=on_ok,
        bootstyle="success",
        icon="box-arrow-in-right",
        compound=tk.LEFT,
        width=10,
    ).pack(side=tk.LEFT, padx=4)

    ttk.Button(
        buttons,
        text="Отмена",
        command=on_cancel,
        bootstyle="secondary",
        icon="x-lg",
        compound=tk.LEFT,
        width=10,
    ).pack(side=tk.RIGHT, padx=4)

    dialog.wait_window()
    return allowed["value"]


# ---------- Tooltip / улучшенное превью ----------

class NotePreviewTooltip:
    """Превью заметки при наведении: заголовок, категория, первые строки текста."""

    def __init__(self, parent, fetch_preview_callback):
        self.parent = parent
        self.fetch_preview_callback = fetch_preview_callback
        self.tipwindow = None

    def show(self, title, category, text_lines, x, y):
        if self.tipwindow or not text_lines:
            return

        self.tipwindow = tw = tk.Toplevel(self.parent)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.wm_geometry(f"+{x+20}+{y+10}")

        frame = ttk.Frame(tw, padding=8, bootstyle="secondary")
        frame.pack(fill=tk.BOTH, expand=tk.YES)

        header_text = title
        if category:
            header_text += f" [{category}]"

        header = ttk.Label(
            frame,
            text=header_text,
            bootstyle="inverse-primary",
            font=("Segoe UI", 9, "bold"),
            wraplength=360,
            justify=tk.LEFT,
        )
        header.pack(anchor=tk.W, pady=(0, 4))

        label = ttk.Label(
            frame,
            text="\n".join(text_lines),
            bootstyle="secondary",
            justify=tk.LEFT,
            wraplength=360,
        )
        label.pack(fill=tk.BOTH, expand=tk.YES)

    def hide(self):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


# ---------- Приложение Zeero заметки ----------

class NotesApp:
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title("Zeero заметки")
        self.root.geometry("1200x700")

        self.root.style.theme_use("minty")
        self.current_theme_mode = "light"

        # состояние
        self.current_note_id = None
        self.current_sort = "updated_desc"
        self.notes = []      # текущая страница: список (id, title, category)
        self.total_notes = 0
        self.current_page = 1
        self.total_pages = 1
        self.preview_tooltip = None

        # БД
        self.conn = sqlite3.connect(DB_NAME)
        self.cursor = self.conn.cursor()
        self.create_tables()

        self.set_window_icon()
        self.create_menu()
        self.create_layout()

        self.preview_tooltip = NotePreviewTooltip(self.root, self.fetch_note_preview)
        self.notes_listbox.bind("<Motion>", self.on_listbox_motion)
        self.notes_listbox.bind("<Leave>", lambda e: self.preview_tooltip.hide())

        self.update_pagination_info()
        self.load_notes()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- таблицы, FTS5, теги ----------

    def create_tables(self):
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT,
                created_at TEXT NOT NULL DEFAULT current_timestamp,
                updated_at TEXT NOT NULL DEFAULT current_timestamp
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS note_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT,
                created_at TEXT NOT NULL DEFAULT current_timestamp
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS note_tags (
                note_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (note_id, tag_id),
                FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
            """
        )

        fts_available = True
        try:
            self.cursor.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
                USING fts5(
                    title,
                    content,
                    category,
                    content='notes',
                    content_rowid='id'
                )
                """
            )
        except sqlite3.OperationalError as e:
            print("FTS5 недоступен:", e)
            fts_available = False

        if fts_available:
            self.cursor.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS notes_fts_ai
                AFTER INSERT ON notes
                BEGIN
                    INSERT INTO notes_fts(rowid, title, content, category)
                    VALUES (new.id, new.title, new.content, new.category);
                END;

                CREATE TRIGGER IF NOT EXISTS notes_fts_ad
                AFTER DELETE ON notes
                BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, title, content, category)
                    VALUES ('delete', old.id, old.title, old.content, old.category);
                END;

                CREATE TRIGGER IF NOT EXISTS notes_fts_au
                AFTER UPDATE ON notes
                BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, title, content, category)
                    VALUES ('delete', old.id, old.title, old.content, old.category);
                    INSERT INTO notes_fts(rowid, title, content, category)
                    VALUES (new.id, new.title, new.content, new.category);
                END;
                """
            )

        self.conn.commit()

    # ---------- меню ----------

    def create_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Новая заметка", command=self.new_note)
        file_menu.add_command(label="Сохранить", command=self.save_note)
        file_menu.add_separator()
        file_menu.add_command(label="Экспорт БД...", command=self.export_db)
        file_menu.add_command(label="Экспорт заметки в .txt...", command=self.export_note_txt)
        file_menu.add_command(label="Экспорт заметки в .md...", command=self.export_note_md)
        file_menu.add_command(label="Экспорт всех заметок в HTML...", command=self.export_all_to_html)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Светлая тема (minty)", command=self.set_light_theme)
        view_menu.add_command(label="Тёмная тема (darkly)", command=self.set_dark_theme)
        menubar.add_cascade(label="View", menu=view_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="История версий заметки", command=self.show_versions_dialog)
        tools_menu.add_command(label="Массовое удаление по тегам", command=self.bulk_delete_by_tags)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О Zeero заметки", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    # ---------- layout ----------

    def create_layout(self):
        top_bar = ttk.Frame(self.root, padding=16)
        top_bar.pack(side=tk.TOP, fill=tk.X)

        title_label = ttk.Label(
            top_bar,
            text="Zeero заметки (поиск, пагинация, теги)",
            bootstyle="inverse-primary",
            font=("Segoe UI", 13, "bold"),
        )
        title_label.pack(side=tk.LEFT)

        self.theme_var = tk.IntVar(value=0)
        theme_switch = ttk.Checkbutton(
            top_bar,
            text="Тёмная тема",
            variable=self.theme_var,
            command=self.toggle_theme,
            bootstyle="round-toggle",
        )
        theme_switch.pack(side=tk.RIGHT)

        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=tk.YES)

        # левая колонка
        left_frame = ttk.Frame(main_frame, padding=(0, 0, 12, 0))
        left_frame.pack(side=tk.LEFT, fill=tk.Y)

        search_card = ttk.LabelFrame(
            left_frame,
            text="Поиск и фильтр",
            bootstyle="secondary",
            padding=8,
        )
        search_card.pack(fill=tk.X, pady=(0, 10))

        search_row = ttk.Frame(search_card)
        search_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(
            search_row,
            text="FTS-поиск:",
            bootstyle="secondary",
        ).pack(side=tk.LEFT)

        self.search_entry = ttk.Entry(search_row, width=22)
        self.search_entry.pack(side=tk.LEFT, padx=(6, 6))

        ttk.Button(
            search_row,
            text="Найти",
            command=self.search_notes_fts,
            bootstyle="info",
            icon="search",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT)

        ttk.Button(
            search_row,
            text="Сброс",
            command=self.clear_search,
            bootstyle="secondary",
            icon="arrow-counterclockwise",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT, padx=(6, 0))

        # поиск по тегам
        tag_search_row = ttk.Frame(search_card)
        tag_search_row.pack(fill=tk.X, pady=(4, 0))

        ttk.Label(
            tag_search_row,
            text="Поиск по тегам:",
            bootstyle="secondary",
        ).pack(side=tk.LEFT)

        self.tag_search_entry = ttk.Entry(tag_search_row, width=22)
        self.tag_search_entry.pack(side=tk.LEFT, padx=(6, 6))

        ttk.Button(
            tag_search_row,
            text="Фильтр по тегам",
            command=self.search_by_tags,
            bootstyle="info",
            icon="tags",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT)

        filter_row = ttk.Frame(search_card)
        filter_row.pack(fill=tk.X, pady=(6, 0))

        ttk.Label(
            filter_row,
            text="Категория:",
            bootstyle="secondary",
        ).pack(side=tk.LEFT)

        self.category_filter = ttk.Combobox(
            filter_row,
            bootstyle="info",
            values=["Все", "Математика", "История", "Программирование", "TO-DO"],
            state="readonly",
            width=20,
        )
        self.category_filter.current(0)
        self.category_filter.pack(side=tk.LEFT, padx=(6, 6))
        self.category_filter.bind("<<ComboboxSelected>>", self.on_category_filter_change)

        ttk.Button(
            filter_row,
            text="Создано",
            command=lambda: self.set_sort("created_desc"),
            bootstyle="secondary",
            icon="clock-history",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            filter_row,
            text="Изменено",
            command=lambda: self.set_sort("updated_desc"),
            bootstyle="secondary",
            icon="arrow-repeat",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            filter_row,
            text="Заголовок",
            command=lambda: self.set_sort("title_asc"),
            bootstyle="secondary",
            icon="sort-alpha-down",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT, padx=2)

        # список + пагинация
        list_card = ttk.LabelFrame(
            left_frame,
            text="Заметки Zeero",
            bootstyle="secondary",
            padding=8,
        )
        list_card.pack(fill=tk.BOTH, expand=tk.YES)

        self.notes_listbox = tk.Listbox(
            list_card,
            width=42,
            activestyle="none",
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            bg="#f8fafc",
            fg="#0f172a",
            selectbackground="#0d6efd",
            selectforeground="white",
            highlightthickness=0,
        )
        self.notes_listbox.pack(fill=tk.BOTH, expand=tk.YES)
        self.notes_listbox.bind("<<ListboxSelect>>", self.on_note_select)

        list_controls = ttk.Frame(left_frame, padding=(0, 10, 0, 0))
        list_controls.pack(fill=tk.X)

        ttk.Button(
            list_controls,
            text="Новая",
            command=self.new_note,
            bootstyle="primary",
            icon="file-earmark-plus",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            list_controls,
            text="Сохранить",
            command=self.save_note,
            bootstyle="success",
            icon="save",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            list_controls,
            text="Удалить",
            command=self.delete_note,
            bootstyle="danger outline",
            icon="trash",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT, padx=4)

        pagination_frame = ttk.Frame(left_frame, padding=(0, 4, 0, 0))
        pagination_frame.pack(fill=tk.X)

        self.prev_button = ttk.Button(
            pagination_frame,
            text="◀ Предыдущая",
            command=self.prev_page,
            bootstyle="secondary",
            icon="chevron-left",
            compound=tk.LEFT,
        )
        self.prev_button.pack(side=tk.LEFT, padx=4)

        self.next_button = ttk.Button(
            pagination_frame,
            text="Следующая ▶",
            command=self.next_page,
            bootstyle="secondary",
            icon="chevron-right",
            compound=tk.LEFT,
        )
        self.next_button.pack(side=tk.LEFT, padx=4)

        self.page_label = ttk.Label(
            pagination_frame,
            text="Страница 1 из 1",
            bootstyle="secondary",
        )
        self.page_label.pack(side=tk.RIGHT, padx=4)

        # правая колонка — заметка
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.YES)

        header_frame = ttk.Frame(right_frame)
        header_frame.pack(fill=tk.X)

        left_header = ttk.Frame(header_frame)
        left_header.pack(side=tk.LEFT, fill=tk.X, expand=tk.YES)

        ttk.Label(
            left_header,
            text="Заголовок заметки Zeero",
            bootstyle="secondary",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W)

        self.title_entry = ttk.Entry(left_header)
        self.title_entry.pack(fill=tk.X, pady=(2, 8))

        right_header = ttk.Frame(header_frame)
        right_header.pack(side=tk.RIGHT)

        ttk.Label(
            right_header,
            text="Категория",
            bootstyle="secondary",
        ).pack(anchor=tk.W)

        self.category_entry = ttk.Combobox(
            right_header,
            bootstyle="info",
            values=["", "Математика", "История", "Программирование", "TO-DO"],
            state="readonly",
            width=20,
        )
        self.category_entry.current(0)
        self.category_entry.pack(pady=(2, 8))

        tags_frame = ttk.Frame(right_frame)
        tags_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(
            tags_frame,
            text="Теги (через запятую):",
            bootstyle="secondary",
        ).pack(side=tk.LEFT)

        self.tags_entry = ttk.Entry(tags_frame)
        self.tags_entry.pack(side=tk.LEFT, fill=tk.X, expand=tk.YES, padx=(6, 0))

        text_card = ttk.LabelFrame(
            right_frame,
            text="Текст заметки Zeero",
            bootstyle="secondary",
            padding=8,
        )
        text_card.pack(fill=tk.BOTH, expand=tk.YES, pady=(4, 8))

        self.text_area = tk.Text(
            text_card,
            wrap="word",
            font=("Segoe UI", 11),
            relief=tk.FLAT,
            bg="#ffffff",
            fg="#0f172a",
            insertbackground="#0f172a",
        )
        self.text_area.pack(fill=tk.BOTH, expand=tk.YES)

        dates_frame = ttk.Frame(right_frame)
        dates_frame.pack(fill=tk.X)

        self.created_label = ttk.Label(
            dates_frame,
            text="Создано: —",
            bootstyle="secondary",
            font=("Segoe UI", 9),
        )
        self.created_label.pack(anchor=tk.W)

        self.updated_label = ttk.Label(
            dates_frame,
            text="Изменено: —",
            bootstyle="secondary",
            font=("Segoe UI", 9),
        )
        self.updated_label.pack(anchor=tk.W)

        status_frame = ttk.Frame(self.root, padding=8)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_label = ttk.Label(
            status_frame,
            text=f"Готово | Zeero заметки v{APP_VERSION}",
            bootstyle="secondary",
            anchor=tk.W,
        )
        self.status_label.pack(fill=tk.X)

    # ---------- темы ----------

    def set_light_theme(self):
        self.root.style.theme_use("minty")
        self.theme_var.set(0)
        self.apply_theme_colors(light=True)
        self.set_status("Светлая тема (minty)")

    def set_dark_theme(self):
        self.root.style.theme_use("darkly")
        self.theme_var.set(1)
        self.apply_theme_colors(light=False)
        self.set_status("Тёмная тема (darkly)")

    def toggle_theme(self):
        if self.theme_var.get() == 1:
            self.set_dark_theme()
        else:
            self.set_light_theme()

    def apply_theme_colors(self, light=True):
        if light:
            self.notes_listbox.configure(
                bg="#f8fafc",
                fg="#0f172a",
                selectbackground="#0d6efd",
                selectforeground="#ffffff",
            )
            self.text_area.configure(
                bg="#ffffff",
                fg="#0f172a",
                insertbackground="#0f172a",
            )
        else:
            self.notes_listbox.configure(
                bg="#0b1021",
                fg="#e5e7eb",
                selectbackground="#0d6efd",
                selectforeground="#ffffff",
            )
            self.text_area.configure(
                bg="#111827",
                fg="#e5e7eb",
                insertbackground="#e5e7eb",
            )

    # ---------- иконка окна ----------

    def set_window_icon(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ico_path = os.path.join(base_dir, "icon.ico")
        png_path = os.path.join(base_dir, "icon.png")

        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
                return
            except Exception:
                pass

        if os.path.exists(png_path):
            try:
                icon_image = tk.PhotoImage(file=png_path)
                self.root.iconphoto(True, icon_image)
                self.icon_image = icon_image
                return
            except Exception:
                pass

    # ---------- пагинация ----------

    def update_pagination_info(self):
        self.cursor.execute("SELECT COUNT(*) FROM notes")
        self.total_notes = self.cursor.fetchone()[0]
        self.total_pages = max(1, (self.total_notes + PAGE_SIZE - 1) // PAGE_SIZE)
        self.current_page = min(self.current_page, self.total_pages)
        self.page_label.config(text=f"Страница {self.current_page} из {self.total_pages}")

        self.prev_button.configure(state=tk.NORMAL if self.current_page > 1 else tk.DISABLED)
        self.next_button.configure(
            state=tk.NORMAL if self.current_page < self.total_pages else tk.DISABLED
        )

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_notes(category_filter=self.category_filter.get())
            self.update_pagination_info()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_notes(category_filter=self.category_filter.get())
            self.update_pagination_info()

    # ---------- загрузка списка ----------

    def load_notes(self, category_filter=None):
        self.notes_listbox.delete(0, tk.END)
        self.notes = []

        base_query = "FROM notes"
        params = []
        conditions = []

        if category_filter and category_filter != "Все":
            conditions.append("category = ?")
            params.append(category_filter)

        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)

        if self.current_sort == "created_desc":
            order_clause = " ORDER BY created_at DESC"
        elif self.current_sort == "updated_desc":
            order_clause = " ORDER BY updated_at DESC"
        elif self.current_sort == "title_asc":
            order_clause = " ORDER BY title ASC"
        else:
            order_clause = " ORDER BY updated_at DESC"

        offset = (self.current_page - 1) * PAGE_SIZE
        limit_clause = " LIMIT ? OFFSET ?"
        params_with_limit = params + [PAGE_SIZE, offset]

        query = "SELECT id, title, category " + base_query + where_clause + order_clause + limit_clause

        self.cursor.execute(query, params_with_limit)
        self.notes = self.cursor.fetchall()

        for note in self.notes:
            title = note[1]
            category = note[2] or ""
            display_text = title if not category else f"{title} [{category}]"
            self.notes_listbox.insert(tk.END, display_text)

        self.update_pagination_info()

    # ---------- FTS-поиск ----------

    def search_notes_fts(self):
        text = self.search_entry.get().strip()
        if not text:
            Messagebox.show_warning("Введите текст для поиска", "FTS-поиск")
            return

        try:
            self.cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='notes_fts'"
            )
            if self.cursor.fetchone() is None:
                Messagebox.show_warning(
                    "FTS5 недоступен или таблица не создана. Можно использовать обычный LIKE-поиск.",
                    "FTS-поиск",
                )
                return
        except sqlite3.Error as e:
            Messagebox.show_error(f"Ошибка проверки FTS5:\n{e}", "FTS-поиск")
            return

        category = self.category_filter.get()
        self.notes_listbox.delete(0, tk.END)
        self.notes = []

        query = """
            SELECT n.id, n.title, n.category
            FROM notes_fts f
            JOIN notes n ON n.id = f.rowid
            WHERE notes_fts MATCH ?
        """
        params = [text]

        if category and category != "Все":
            query += " AND n.category = ?"
            params.append(category)

        try:
            self.cursor.execute(query, params)
            self.notes = self.cursor.fetchall()
        except sqlite3.OperationalError as e:
            Messagebox.show_error(f"Ошибка FTS-поиска:\n{e}", "FTS5")
            return

        for note in self.notes:
            title = note[1]
            category_value = note[2] or ""
            display_text = title if not category_value else f"{title} [{category_value}]"
            self.notes_listbox.insert(tk.END, display_text)

        self.page_label.config(text=f"Результаты FTS-поиска ({len(self.notes)} заметок)")
        self.prev_button.configure(state=tk.DISABLED)
        self.next_button.configure(state=tk.DISABLED)

        self.set_status(f"FTS-поиск: «{text}»")

    # ---------- поиск по тегам ----------

    def search_by_tags(self):
        tags_text = self.tag_search_entry.get().strip()
        if not tags_text:
            Messagebox.show_warning("Введите хотя бы один тег", "Поиск по тегам")
            return

        tags = [t.strip() for t in tags_text.split(",") if t.strip()]
        if not tags:
            Messagebox.show_warning("Введите хотя бы один тег", "Поиск по тегам")
            return

        self.notes_listbox.delete(0, tk.END)
        self.notes = []

        placeholders = ", ".join("?" for _ in tags)
        query = f"""
            SELECT DISTINCT n.id, n.title, n.category
            FROM notes n
            JOIN note_tags nt ON nt.note_id = n.id
            JOIN tags t ON t.id = nt.tag_id
            WHERE t.name IN ({placeholders})
        """
        params = tags

        category = self.category_filter.get()
        if category and category != "Все":
            query += " AND n.category = ?"
            params.append(category)

        try:
            self.cursor.execute(query, params)
            self.notes = self.cursor.fetchall()
        except sqlite3.Error as e:
            Messagebox.show_error(f"Ошибка поиска по тегам:\n{e}", "Поиск по тегам")
            return

        for note in self.notes:
            title = note[1]
            category_value = note[2] or ""
            display_text = title if not category_value else f"{title} [{category_value}]"
            self.notes_listbox.insert(tk.END, display_text)

        self.page_label.config(text=f"Результаты по тегам ({len(self.notes)} заметок)")
        self.prev_button.configure(state=tk.DISABLED)
        self.next_button.configure(state=tk.DISABLED)

        self.set_status(f"Поиск по тегам: {', '.join(tags)}")

    def clear_search(self):
        self.search_entry.delete(0, tk.END)
        self.tag_search_entry.delete(0, tk.END)
        self.update_pagination_info()
        self.load_notes(category_filter=self.category_filter.get())
        self.set_status("Поиск сброшен")

    def on_category_filter_change(self, event=None):
        self.current_page = 1
        self.update_pagination_info()
        category = self.category_filter.get()
        self.load_notes(category_filter=category)
        self.set_status(f"Фильтр по категории: {category}")

    def set_sort(self, sort_mode):
        self.current_sort = sort_mode
        self.current_page = 1
        self.update_pagination_info()
        category = self.category_filter.get()
        self.load_notes(category_filter=category)
        self.set_status(f"Сортировка изменена: {sort_mode}")

    # ---------- превью заметки ----------

    def fetch_note_preview(self, note_id, max_lines=5):
        try:
            self.cursor.execute(
                "SELECT title, content, category FROM notes WHERE id = ?",
                (note_id,),
            )
            row = self.cursor.fetchone()
            if not row:
                return None, None, []
            title, content, category = row
            lines = content.splitlines()
            return title, category, lines[:max_lines]
        except sqlite3.Error:
            return None, None, []

    def on_listbox_motion(self, event):
        index = self.notes_listbox.nearest(event.y)
        if not self.notes or index < 0 or index >= len(self.notes):
            self.preview_tooltip.hide()
            return

        note_id = self.notes[index][0]
        title, category, preview_lines = self.fetch_note_preview(note_id)

        if preview_lines and title is not None:
            x_root = self.root.winfo_pointerx()
            y_root = self.root.winfo_pointery()
            self.preview_tooltip.show(title, category, preview_lines, x_root, y_root)
        else:
            self.preview_tooltip.hide()

    # ---------- теги ----------

    def load_tags_for_note(self, note_id):
        self.cursor.execute(
            """
            SELECT t.name
            FROM tags t
            JOIN note_tags nt ON nt.tag_id = t.id
            WHERE nt.note_id = ?
            """,
            (note_id,),
        )
        rows = self.cursor.fetchall()
        return [r[0] for r in rows]

    def save_tags_for_note(self, note_id, tags_text):
        tags = [t.strip() for t in tags_text.split(",") if t.strip()]
        self.cursor.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
        for tag_name in tags:
            self.cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
            self.cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_id = self.cursor.fetchone()[0]
            self.cursor.execute(
                "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                (note_id, tag_id),
            )
        self.conn.commit()

    # ---------- массовое удаление по тегам ----------

    def bulk_delete_by_tags(self):
        self.cursor.execute("SELECT id, name FROM tags ORDER BY name ASC")
        tags = self.cursor.fetchall()
        if not tags:
            Messagebox.show_info("Тегов пока нет, удалять нечего", "Массовое удаление")
            return

        dialog = ttk.Toplevel(self.root)
        dialog.title("Массовое удаление заметок Zeero по тегам")
        dialog.geometry("420x380")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=tk.YES)

        ttk.Label(
            frame,
            text="Выберите теги для массового удаления заметок Zeero:",
            bootstyle="secondary",
            wraplength=380,
        ).pack(anchor=tk.W, pady=(0, 8))

        tags_listbox = tk.Listbox(
            frame,
            selectmode=tk.MULTIPLE,
            activestyle="none",
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            bg="#f8fafc",
            fg="#0f172a",
            highlightthickness=0,
        )
        tags_listbox.pack(fill=tk.BOTH, expand=tk.YES)

        for t in tags:
            tags_listbox.insert(tk.END, t[1])

        info_label = ttk.Label(
            frame,
            text="Внимание: удаление заметок необратимо!",
            bootstyle="danger",
        )
        info_label.pack(anchor=tk.W, pady=(8, 8))

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X)

        def on_delete():
            selection = tags_listbox.curselection()
            if not selection:
                Messagebox.show_warning("Сначала выберите хотя бы один тег", "Массовое удаление")
                return

            selected_tag_names = [tags[i][1] for i in selection]

            confirm = Messagebox.yesno(
                f"Удалить все заметки Zeero с тегами:\n{', '.join(selected_tag_names)}?",
                "Подтверждение",
                alert=True,
            )
            if confirm != "Yes":
                return

            placeholders = ", ".join("?" for _ in selected_tag_names)
            delete_query = f"""
                DELETE FROM notes
                WHERE id IN (
                    SELECT DISTINCT n.id
                    FROM notes n
                    JOIN note_tags nt ON nt.note_id = n.id
                    JOIN tags t ON t.id = nt.tag_id
                    WHERE t.name IN ({placeholders})
                )
            """
            try:
                self.cursor.execute(delete_query, selected_tag_names)
                self.conn.commit()
                Messagebox.show_info("Заметки Zeero удалены по выбранным тегам", "Массовое удаление")
                dialog.destroy()
                self.current_note_id = None
                self.new_note()
                self.update_pagination_info()
                self.load_notes(category_filter=self.category_filter.get())
                self.set_status(f"Массовое удаление по тегам: {', '.join(selected_tag_names)}")
            except sqlite3.Error as e:
                Messagebox.show_error(f"Ошибка массового удаления:\n{e}", "Ошибка")

        def on_cancel():
            dialog.destroy()

        ttk.Button(
            buttons,
            text="Удалить",
            command=on_delete,
            bootstyle="danger",
            icon="trash",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            buttons,
            text="Закрыть",
            command=on_cancel,
            bootstyle="secondary",
            icon="x-lg",
            compound=tk.LEFT,
        ).pack(side=tk.RIGHT, padx=4)

        dialog.wait_window()

    # ---------- логика заметок ----------

    def on_note_select(self, event):
        selection = self.notes_listbox.curselection()
        if not selection or not self.notes:
            return
        index = selection[0]
        if index >= len(self.notes):
            return
        note_id = self.notes[index][0]

        self.cursor.execute(
            """
            SELECT id, title, content, category, created_at, updated_at
            FROM notes
            WHERE id = ?
            """,
            (note_id,),
        )
        row = self.cursor.fetchone()
        if row:
            self.current_note_id = row[0]
            self.title_entry.delete(0, tk.END)
            self.title_entry.insert(0, row[1])

            self.text_area.delete("1.0", tk.END)
            self.text_area.insert(tk.END, row[2])

            category = row[3] or ""
            values = list(self.category_entry["values"])
            if category in values:
                self.category_entry.set(category)
            else:
                self.category_entry.set("")

            created_at = row[4]
            updated_at = row[5]
            self.created_label.config(text=f"Создано: {created_at}")
            self.updated_label.config(text=f"Изменено: {updated_at}")

            tags = self.load_tags_for_note(self.current_note_id)
            self.tags_entry.delete(0, tk.END)
            self.tags_entry.insert(0, ", ".join(tags))

    def new_note(self):
        self.current_note_id = None
        self.title_entry.delete(0, tk.END)
        self.text_area.delete("1.0", tk.END)
        self.category_entry.set("")
        self.tags_entry.delete(0, tk.END)
        self.created_label.config(text="Создано: —")
        self.updated_label.config(text="Изменено: —")
        self.set_status("Новая заметка Zeero")

    def save_note(self):
        title = self.title_entry.get().strip()
        content = self.text_area.get("1.0", tk.END).strip()
        category = self.category_entry.get().strip() or None
        tags_text = self.tags_entry.get().strip()

        if not title:
            Messagebox.show_warning("Введите заголовок заметки", "Внимание")
            return
        if not content:
            Messagebox.show_warning("Введите текст заметки", "Внимание")
            return

        if self.current_note_id is None:
            self.cursor.execute(
                "INSERT INTO notes (title, content, category) VALUES (?, ?, ?)",
                (title, content, category),
            )
            self.conn.commit()
            self.current_note_id = self.cursor.lastrowid
        else:
            self.cursor.execute(
                """
                INSERT INTO note_versions (note_id, title, content, category)
                SELECT id, title, content, category
                FROM notes
                WHERE id = ?
                """,
                (self.current_note_id,),
            )
            self.cursor.execute(
                """
                UPDATE notes
                SET title = ?,
                    content = ?,
                    category = ?,
                    updated_at = current_timestamp
                WHERE id = ?
                """,
                (title, content, category, self.current_note_id),
            )
            self.conn.commit()

        self.save_tags_for_note(self.current_note_id, tags_text)

        self.cursor.execute(
            """
            SELECT created_at, updated_at
            FROM notes
            WHERE id = ?
            """,
            (self.current_note_id,),
        )
        row = self.cursor.fetchone()
        if row:
            self.created_label.config(text=f"Создано: {row[0]}")
            self.updated_label.config(text=f"Изменено: {row[1]}")

        self.update_pagination_info()
        category_filter = self.category_filter.get()
        self.load_notes(category_filter=category_filter)

        self.set_status("Заметка Zeero сохранена")
        self.show_toast("Заметка Zeero сохранена")

    def delete_note(self):
        if self.current_note_id is None:
            Messagebox.show_warning("Сначала выберите заметку", "Внимание")
            return

        answer = Messagebox.yesno(
            "Удалить выбранную заметку Zeero?",
            "Подтверждение",
            alert=True,
        )
        if answer == "Yes":
            self.cursor.execute("DELETE FROM notes WHERE id = ?", (self.current_note_id,))
            self.conn.commit()
            self.current_note_id = None
            self.title_entry.delete(0, tk.END)
            self.text_area.delete("1.0", tk.END)
            self.category_entry.set("")
            self.tags_entry.delete(0, tk.END)
            self.created_label.config(text="Создано: —")
            self.updated_label.config(text="Изменено: —")

            self.update_pagination_info()
            category_filter = self.category_filter.get()
            self.load_notes(category_filter=category_filter)

            self.set_status("Заметка Zeero удалена")
            self.show_toast("Заметка Zeero удалена")

    # ---------- история версий ----------

    def show_versions_dialog(self):
        if self.current_note_id is None:
            Messagebox.show_warning("Сначала выберите заметку", "История версий")
            return

        dialog = ttk.Toplevel(self.root)
        dialog.title("История версий заметки Zeero")
        dialog.geometry("640x420")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=tk.YES)

        ttk.Label(
            frame,
            text="Версии заметки Zeero (по датам сохранения):",
            bootstyle="secondary",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W)

        listbox = tk.Listbox(
            frame,
            activestyle="none",
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            bg="#f8fafc",
            fg="#0f172a",
            selectbackground="#0d6efd",
            selectforeground="white",
            height=14,
        )
        listbox.pack(fill=tk.BOTH, expand=tk.YES, pady=(4, 10))

        self.cursor.execute(
            """
            SELECT id, created_at, title, category
            FROM note_versions
            WHERE note_id = ?
            ORDER BY created_at DESC
            """,
            (self.current_note_id,),
        )
        versions = self.cursor.fetchall()

        for v in versions:
            v_id, created_at, title, category = v
            cat_text = f"[{category}]" if category else ""
            listbox.insert(tk.END, f"{created_at} | {title} {cat_text}")

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X)

        def on_view():
            sel = listbox.curselection()
            if not sel or not versions:
                return
            idx = sel[0]
            if idx >= len(versions):
                return
            v_id = versions[idx][0]
            self.cursor.execute(
                """
                SELECT title, content, category, created_at
                FROM note_versions
                WHERE id = ?
                """,
                (v_id,),
            )
            row = self.cursor.fetchone()
            if row:
                title, content, category, created_at = row
                self.title_entry.delete(0, tk.END)
                self.title_entry.insert(0, title)
                self.text_area.delete("1.0", tk.END)
                self.text_area.insert(tk.END, content)
                self.category_entry.set(category or "")
                self.set_status(f"Просмотр версии Zeero от {created_at}")

        def on_close():
            dialog.destroy()

        ttk.Button(
            buttons,
            text="Открыть версию",
            command=on_view,
            bootstyle="primary",
            icon="eye",
            compound=tk.LEFT,
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            buttons,
            text="Закрыть",
            command=on_close,
            bootstyle="secondary",
            icon="x-lg",
            compound=tk.LEFT,
        ).pack(side=tk.RIGHT, padx=4)

        dialog.wait_window()

    # ---------- экспорт ----------

    def export_db(self):
        path = filedialog.asksaveasfilename(
            title="Экспорт базы данных Zeero",
            defaultextension=".db",
            filetypes=[("SQLite DB", "*.db"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            self.conn.commit()
            with open(DB_NAME, "rb") as f_src, open(path, "wb") as f_dst:
                f_dst.write(f_src.read())
            Messagebox.show_info("База данных Zeero экспортирована", "Экспорт")
            self.set_status(f"БД экспортирована: {path}")
        except Exception as e:
            Messagebox.show_error(f"Ошибка экспорта БД:\n{e}", "Ошибка")

    def export_note_txt(self):
        if self.current_note_id is None:
            Messagebox.show_warning("Сначала выберите заметку", "Экспорт")
            return
        path = filedialog.asksaveasfilename(
            title="Экспорт заметки Zeero в .txt",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All Files", "*.*")],
        )
        if not path:
            return
        title = self.title_entry.get().strip()
        content = self.text_area.get("1.0", tk.END).strip()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(title + "\n\n" + content)
            Messagebox.show_info("Заметка Zeero экспортирована в .txt", "Экспорт")
            self.set_status(f"Заметка экспортирована: {path}")
        except Exception as e:
            Messagebox.show_error(f"Ошибка экспорта:\n{e}", "Ошибка")

    def export_note_md(self):
        if self.current_note_id is None:
            Messagebox.show_warning("Сначала выберите заметку", "Экспорт")
            return
        path = filedialog.asksaveasfilename(
            title="Экспорт заметки Zeero в .md",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("All Files", "*.*")],
        )
        if not path:
            return
        title = self.title_entry.get().strip()
        content = self.text_area.get("1.0", tk.END).strip()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("# " + title + "\n\n" + content)
            Messagebox.show_info("Заметка Zeero экспортирована в .md", "Экспорт")
            self.set_status(f"Заметка экспортирована: {path}")
        except Exception as e:
            Messagebox.show_error(f"Ошибка экспорта:\n{e}", "Ошибка")

    def export_all_to_html(self):
        path = filedialog.asksaveasfilename(
            title="Экспорт всех заметок Zeero в HTML",
            defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("All Files", "*.*")],
        )
        if not path:
            return

        try:
            self.cursor.execute(
                """
                SELECT id, title, content, category, created_at, updated_at
                FROM notes
                ORDER BY category, title
                """
            )
            notes = self.cursor.fetchall()

            html_parts = [
                "<!DOCTYPE html>",
                "<html lang='ru'>",
                "<head>",
                "<meta charset='UTF-8'>",
                "<title>Zeero заметки (экспорт)</title>",
                "<style>",
                "body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 40px; background: #f9fafb; }",
                "h1 { color: #0f172a; }",
                "h2 { margin-top: 32px; color: #0f172a; }",
                ".note { background: #ffffff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(15,23,42,0.1); }",
                ".meta { font-size: 12px; color: #6b7280; margin-bottom: 8px; }",
                ".tags { font-size: 12px; color: #0d9488; margin-top: 8px; }",
                "</style>",
                "</head>",
                "<body>",
                "<h1>Все заметки Zeero</h1>",
                f"<p>Всего заметок: {len(notes)}</p>",
            ]

            for n in notes:
                note_id, title, content, category, created_at, updated_at = n
                tags = self.load_tags_for_note(note_id)
                tags_html = ""
                if tags:
                    tags_html = "<div class='tags'>Теги: " + ", ".join(tags) + "</div>"

                category_text = category or "Без категории"
                meta = f"Категория: {category_text} | Создано: {created_at} | Изменено: {updated_at}"

                html_parts.append("<div class='note'>")
                html_parts.append(f"<h2>{title}</h2>")
                html_parts.append(f"<div class='meta'>{meta}</div>")
                safe_content = (
                    content.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\n", "<br>")
                )
                html_parts.append(f"<p>{safe_content}</p>")
                if tags_html:
                    html_parts.append(tags_html)
                html_parts.append("</div>")

            html_parts.append("</body></html>")

            html = "\n".join(html_parts)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)

            Messagebox.show_info("Все заметки Zeero экспортированы в HTML", "Экспорт")
            self.set_status(f"Все заметки экспортированы: {path}")
        except Exception as e:
            Messagebox.show_error(f"Ошибка экспорта HTML:\n{e}", "Ошибка")

    # ---------- статус / тост / about / закрытие ----------

    def set_status(self, text):
        self.status_label.config(text=f"{text} | Zeero заметки v{APP_VERSION}")

    def show_toast(self, message, duration=2000):
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)

        self.root.update_idletasks()
        x = self.root.winfo_rootx() + self.root.winfo_width() - 260
        y = self.root.winfo_rooty() + self.root.winfo_height() - 100
        toast.geometry(f"240x60+{x}+{y}")

        frame = ttk.Frame(toast, padding=5, bootstyle="secondary")
        frame.pack(fill=tk.BOTH, expand=tk.YES)

        label = ttk.Label(
            frame,
            text=message,
            bootstyle="inverse-success",
            anchor=tk.CENTER,
        )
        label.pack(fill=tk.BOTH, expand=tk.YES, padx=4, pady=4)

        toast.after(duration, toast.destroy)

    def show_about(self):
        Messagebox.show_info(
            f"Zeero заметки\nВерсия: {APP_VERSION}\n\nПагинация, поиск по тегам и FTS5,\nмассовое удаление по тегам и экспорт.\nСоздано на Python, Tkinter, ttkbootstrap и SQLite.",
            "О Zeero заметки",
        )

    def on_close(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self.root.destroy()


# ---------- запуск приложения ----------

if __name__ == "__main__":
    root = ttk.Window(themename="minty", title="Zeero заметки")

    if show_pin_dialog(root):
        app = NotesApp(root)
        root.mainloop()
    else:
        root.destroy()

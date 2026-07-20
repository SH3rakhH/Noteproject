import os
import sqlite3
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox  # стилизованные диалоги[web:147][web:151]


DB_NAME = "notes.db"
APP_VERSION = "1.3.0 (SQLite + ttk + dates + icon)"


class NotesApp:
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title("Заметки (Tkinter + SQLite + ttkbootstrap)")
        self.root.geometry("840x520")

            # начальная тема (светлая)
        # Window уже создан с themename="flatly" ниже в __main__, но на всякий случай синхронизируем.[web:140]
        self.root.style.theme_use("flatly")
        self.current_theme_mode = "light"

        # Иконка окна
        self.set_window_icon()

        # Подключение к БД и создание таблицы
        self.conn = sqlite3.connect(DB_NAME)
        self.cursor = self.conn.cursor()
        self.create_table()

        # ---------- Layout ----------

        # Верхняя панель: заголовок + переключатель темы
        top_bar = ttk.Frame(self.root, padding=10)
        top_bar.pack(side=TOP, fill=X)

        title_label = ttk.Label(
            top_bar,
            text="Приложение для заметок",
            bootstyle="inverse-primary",
            font=("Segoe UI", 12, "bold"),
        )
        title_label.pack(side=LEFT)

        # Переключатель темы (Checkbutton)
        self.theme_var = tk.IntVar(value=0)  # 0 — светлая, 1 — тёмная
        theme_switch = ttk.Checkbutton(
            top_bar,
            text="Тёмная тема",
            variable=self.theme_var,
            command=self.toggle_theme,
            bootstyle="round-toggle",
        )
        theme_switch.pack(side=RIGHT)

        # Основная область
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(side=TOP, fill=BOTH, expand=YES)

        # Левый фрейм (список заметок)
        left_frame = ttk.Frame(main_frame, padding=(0, 0, 10, 0))
        left_frame.pack(side=LEFT, fill=Y)

        side_title = ttk.Label(
            left_frame,
            text="Список заметок",
            bootstyle="secondary",
            font=("Segoe UI", 10, "bold"),
        )
        side_title.pack(pady=(0, 6), anchor=W)

        # Listbox — используем цвета, согласованные с темой (для light/dark придется обновлять).[web:157]
        self.notes_listbox = tk.Listbox(
            left_frame,
            width=28,
            activestyle="none",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            highlightthickness=0,
        )
        self.notes_listbox.pack(fill=Y, expand=YES)
        self.notes_listbox.bind("<<ListboxSelect>>", self.on_note_select)

        # начальные цвета для светлой темы
        self.apply_listbox_colors(light=True)

        buttons_frame = ttk.Frame(left_frame, padding=(0, 8, 0, 0))
        buttons_frame.pack(fill=X)

        self.new_button = ttk.Button(
            buttons_frame,
            text="Новая",
            command=self.new_note,
            bootstyle="primary-outline",
        )
        self.new_button.pack(side=LEFT, padx=2)

        self.save_button = ttk.Button(
            buttons_frame,
            text="Сохранить",
            command=self.save_note,
            bootstyle="success",
        )
        self.save_button.pack(side=LEFT, padx=2)

        self.delete_button = ttk.Button(
            buttons_frame,
            text="Удалить",
            command=self.delete_note,
            bootstyle="danger-outline",
        )
        self.delete_button.pack(side=LEFT, padx=2)

        # Правый фрейм (заголовок + текст + даты)
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=LEFT, fill=BOTH, expand=YES)

        # Заголовок
        title_label_right = ttk.Label(
            right_frame,
            text="Заголовок",
            bootstyle="secondary",
            font=("Segoe UI", 10, "bold"),
        )
        title_label_right.pack(anchor=W)

        self.title_entry = ttk.Entry(right_frame)
        self.title_entry.pack(fill=X, pady=(2, 8))

        # Текст заметки
        content_label = ttk.Label(
            right_frame,
            text="Текст заметки",
            bootstyle="secondary",
            font=("Segoe UI", 10, "bold"),
        )
        content_label.pack(anchor=W)

        text_card = ttk.Frame(
            right_frame,
            bootstyle="secondary",
            padding=5,
        )
        text_card.pack(fill=BOTH, expand=YES, pady=(2, 8))

        self.text_area = tk.Text(
            text_card,
            wrap="word",
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            highlightthickness=0,
        )
        self.text_area.pack(fill=BOTH, expand=YES)

        # начальные цвета Text для светлой темы
        self.apply_text_colors(light=True)

        # Блок с датами
        dates_frame = ttk.Frame(right_frame)
        dates_frame.pack(fill=X)

        self.created_label = ttk.Label(
            dates_frame,
            text="Создано: —",
            bootstyle="secondary",
            font=("Segoe UI", 9),
        )
        self.created_label.pack(anchor=W)

        self.updated_label = ttk.Label(
            dates_frame,
            text="Изменено: —",
            bootstyle="secondary",
            font=("Segoe UI", 9),
        )
        self.updated_label.pack(anchor=W)

        # ID текущей заметки
        self.current_note_id = None

        # Загрузка списка заметок
        self.load_notes()

        # Статус-бар / версия
        status_frame = ttk.Frame(self.root, padding=6)
        status_frame.pack(side=BOTTOM, fill=X)

        self.status_label = ttk.Label(
            status_frame,
            text=f"Версия: {APP_VERSION}",
            bootstyle="secondary",
            anchor=W,
        )
        self.status_label.pack(fill=X)

        # Закрытие (освобождение БД)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- Цвета для light/dark ----------

    def apply_listbox_colors(self, light: bool):
        """Применить цвета к Listbox в зависимости от темы."""
        if light:
            self.notes_listbox.configure(
                bg="#f8fafc",
                fg="#0f172a",
                selectbackground="#0d6efd",
                selectforeground="#ffffff",
            )
        else:
            self.notes_listbox.configure(
                bg="#0b1021",
                fg="#e5e7eb",
                selectbackground="#0d6efd",
                selectforeground="#ffffff",
            )

    def apply_text_colors(self, light: bool):
        """Применить цвета к текстовому полю в зависимости от темы."""
        if light:
            self.text_area.configure(
                bg="#ffffff",
                fg="#0f172a",
                insertbackground="#0f172a",
            )
        else:
            self.text_area.configure(
                bg="#111827",
                fg="#e5e7eb",
                insertbackground="#e5e7eb",
            )

    # ---------- Переключение темы ----------

    def toggle_theme(self):
        """
        Переключатель между светлой и тёмной темой.
        Используем встроенные темы ttkbootstrap (flatly / darkly).[web:140][web:157]
        """
        style = self.root.style
        if self.theme_var.get() == 1:
            style.theme_use("darkly")
            self.current_theme_mode = "dark"
            self.set_status("Включена тёмная тема")
            self.apply_listbox_colors(light=False)
            self.apply_text_colors(light=False)
        else:
            style.theme_use("flatly")
            self.current_theme_mode = "light"
            self.set_status("Включена светлая тема")
            self.apply_listbox_colors(light=True)
            self.apply_text_colors(light=True)

    # ---------- Иконка окна ----------

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

    # ---------- БД ----------

    def create_table(self):
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT current_timestamp,
                updated_at TEXT NOT NULL DEFAULT current_timestamp
            )
            """
        )
        self.conn.commit()

    def load_notes(self):
        """Загрузить все заметки в Listbox."""
        self.notes_listbox.delete(0, tk.END)
        self.cursor.execute("SELECT id, title FROM notes ORDER BY id DESC")
        self.notes = self.cursor.fetchall()
        for note in self.notes:
            self.notes_listbox.insert(tk.END, note[1])

    # ---------- Логика заметок ----------

    def on_note_select(self, event):
        """Загрузка выбранной заметки в поля."""
        selection = self.notes_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        note_id = self.notes[index][0]

        self.cursor.execute(
            """
            SELECT id, title, content, created_at, updated_at
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

            created_at = row[3]
            updated_at = row[4]
            self.created_label.config(text=f"Создано: {created_at}")
            self.updated_label.config(text=f"Изменено: {updated_at}")

    def new_note(self):
        """Очистить поля для создания новой заметки."""
        self.current_note_id = None
        self.title_entry.delete(0, tk.END)
        self.text_area.delete("1.0", tk.END)
        self.created_label.config(text="Создано: —")
        self.updated_label.config(text="Изменено: —")
        self.set_status("Новая заметка")

    def save_note(self):
        """Создать новую или обновить существующую заметку."""
        title = self.title_entry.get().strip()
        content = self.text_area.get("1.0", tk.END).strip()

        if not title:
            Messagebox.show_warning("Введите заголовок заметки", "Внимание")
            return
        if not content:
            Messagebox.show_warning("Введите текст заметки", "Внимание")
            return

        if self.current_note_id is None:
            # Новая заметка
            self.cursor.execute(
                "INSERT INTO notes (title, content) VALUES (?, ?)",
                (title, content),
            )
            self.conn.commit()

            new_id = self.cursor.lastrowid
            self.current_note_id = new_id

            self.cursor.execute(
                """
                SELECT created_at, updated_at
                FROM notes
                WHERE id = ?
                """,
                (new_id,),
            )
            row = self.cursor.fetchone()
            if row:
                self.created_label.config(text=f"Создано: {row[0]}")
                self.updated_label.config(text=f"Изменено: {row[1]}")

            self.set_status("Заметка создана")
            self.show_toast("Заметка сохранена")
        else:
            # Обновление существующей заметки
            self.cursor.execute(
                """
                UPDATE notes
                SET title = ?,
                    content = ?,
                    updated_at = current_timestamp
                WHERE id = ?
                """,
                (title, content, self.current_note_id),
            )
            self.conn.commit()

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

            self.set_status("Заметка обновлена")
            self.show_toast("Заметка обновлена")

        self.load_notes()

    def delete_note(self):
        """Удалить выбранную заметку."""
        if self.current_note_id is None:
            Messagebox.show_warning("Сначала выберите заметку", "Внимание")
            return

        answer = Messagebox.yesno(
            "Удалить выбранную заметку?",
            "Подтверждение",
            alert=True,
        )
        if answer == "Yes":
            self.cursor.execute(
                "DELETE FROM notes WHERE id = ?", (self.current_note_id,)
            )
            self.conn.commit()
            self.current_note_id = None
            self.title_entry.delete(0, tk.END)
            self.text_area.delete("1.0", tk.END)
            self.created_label.config(text="Создано: —")
            self.updated_label.config(text="Изменено: —")
            self.load_notes()
            self.set_status("Заметка удалена")
            self.show_toast("Заметка удалена")

    # ---------- Статус и toast ----------

    def set_status(self, text):
        """Обновить строку статуса (внизу)."""
        self.status_label.config(text=f"{text} | Версия: {APP_VERSION}")

    def show_toast(self, message, duration=2000):
        """Небольшое всплывающее окно (toast), не блокирует интерфейс.[web:147][web:151]"""
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)

        self.root.update_idletasks()
        x = self.root.winfo_rootx() + self.root.winfo_width() - 230
        y = self.root.winfo_rooty() + self.root.winfo_height() - 90
        toast.geometry(f"220x50+{x}+{y}")

        frame = ttk.Frame(toast, padding=5, bootstyle="secondary")
        frame.pack(fill=BOTH, expand=YES)

        label = ttk.Label(
            frame,
            text=message,
            bootstyle="inverse-success",
            anchor=CENTER,
        )
        label.pack(fill=BOTH, expand=YES, padx=4, pady=4)

        toast.after(duration, toast.destroy)

    # ---------- Закрытие ----------

    def on_close(self):
        self.conn.close()
        self.root.destroy()


if __name__ == "__main__":
    # Создаём окно сразу с светлой темой flatly.[web:140]
    app_window = ttk.Window(themename="flatly")
    app = NotesApp(app_window)
    app_window.mainloop()

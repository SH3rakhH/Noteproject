import os
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
import sqlite3


DB_NAME = "notes.db"
APP_VERSION = "1.3.0 (SQLite + ttk + dates + icon)"


class NotesApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Заметки (Tkinter + SQLite + ttk)")
        self.root.geometry("820x500")

        # Устанавливаем иконку приложения
        self.set_window_icon()

        # Используем тему ttk
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Стили
        self.style.configure("Main.TFrame", background="#f4f4f4")
        self.style.configure("Side.TFrame", background="#e0e0e0")
        self.style.configure(
            "Title.TLabel",
            font=("Segoe UI", 10, "bold"),
            background="#f4f4f4",
        )
        self.style.configure(
            "SideTitle.TLabel",
            font=("Segoe UI", 10, "bold"),
            background="#e0e0e0",
        )
        self.style.configure("TButton", font=("Segoe UI", 9), padding=6)
        self.style.configure(
            "Status.TLabel",
            background="#d0d0d0",
            font=("Segoe UI", 9),
        )

        # Подключение к БД и создание таблицы
        self.conn = sqlite3.connect(DB_NAME)
        self.cursor = self.conn.cursor()
        self.create_table()

        # Основной фрейм
        main_frame = ttk.Frame(self.root, style="Main.TFrame")
        main_frame.pack(side="top", fill="both", expand=True)

        # Левый фрейм (список заметок + кнопки)
        left_frame = ttk.Frame(main_frame, style="Side.TFrame", width=260)
        left_frame.pack(side="left", fill="y")

        side_title = ttk.Label(
            left_frame,
            text="Список заметок",
            style="SideTitle.TLabel",
        )
        side_title.pack(pady=(8, 4), padx=8, anchor="w")

        self.notes_listbox = tk.Listbox(
            left_frame,
            width=30,
            activestyle="none",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
        )
        self.notes_listbox.pack(fill="y", expand=True, padx=8, pady=(0, 8))
        self.notes_listbox.bind("<<ListboxSelect>>", self.on_note_select)

        buttons_frame = ttk.Frame(left_frame, style="Side.TFrame")
        buttons_frame.pack(fill="x", pady=(0, 8))

        self.new_button = ttk.Button(
            buttons_frame, text="Новая", command=self.new_note
        )
        self.new_button.pack(side="left", padx=5)

        self.save_button = ttk.Button(
            buttons_frame, text="Сохранить", command=self.save_note
        )
        self.save_button.pack(side="left", padx=5)

        self.delete_button = ttk.Button(
            buttons_frame, text="Удалить", command=self.delete_note
        )
        self.delete_button.pack(side="left", padx=5)

        # Правый фрейм (заголовок + текст + даты)
        right_frame = ttk.Frame(main_frame, style="Main.TFrame")
        right_frame.pack(side="right", fill="both", expand=True)

        title_label = ttk.Label(
            right_frame,
            text="Заголовок",
            style="Title.TLabel",
        )
        title_label.pack(anchor="w", padx=10, pady=(10, 2))

        self.title_entry = ttk.Entry(right_frame)
        self.title_entry.pack(fill="x", padx=10, pady=(0, 8))

        content_label = ttk.Label(
            right_frame,
            text="Текст заметки",
            style="Title.TLabel",
        )
        content_label.pack(anchor="w", padx=10, pady=(0, 2))

        text_frame = ttk.Frame(right_frame, style="Main.TFrame")
        text_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        self.text_area = tk.Text(
            text_frame,
            wrap="word",
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            borderwidth=1,
        )
        self.text_area.pack(fill="both", expand=True)

        # Блок с датами
        dates_frame = ttk.Frame(right_frame, style="Main.TFrame")
        dates_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.created_label = ttk.Label(
            dates_frame,
            text="Создано: —",
            style="Title.TLabel",
        )
        self.created_label.pack(anchor="w")

        self.updated_label = ttk.Label(
            dates_frame,
            text="Изменено: —",
            style="Title.TLabel",
        )
        self.updated_label.pack(anchor="w")

        # ID текущей заметки
        self.current_note_id = None

        # Загрузка списка заметок
        self.load_notes()

        # Статус-бар / версия
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_label = ttk.Label(
            status_frame,
            text=f"Версия: {APP_VERSION}",
            style="Status.TLabel",
            anchor="w",
        )
        self.status_label.pack(fill=tk.X, padx=8, pady=2)

        # Закрытие (освобождение БД)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- Иконка окна ----------

    def set_window_icon(self):
        """
        Устанавливаем иконку окна.
        Ищем файлы icon.ico и icon.png в той же папке, что и скрипт.[web:66][web:68][web:72]
        """
        base_dir = os.path.dirname(os.path.abspath(__file__))

        ico_path = os.path.join(base_dir, "icon.ico")
        png_path = os.path.join(base_dir, "icon.png")

        # Сначала пробуем .ico (под Windows это стандартный вариант).[web:66][web:72]
        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
                return
            except Exception:
                pass

        # Если .ico нет или не получилось, пробуем .png через iconphoto.[web:68][web:72]
        if os.path.exists(png_path):
            try:
                icon_image = tk.PhotoImage(file=png_path)
                self.root.iconphoto(True, icon_image)
                # Чтобы изображение не было уничтожено сборщиком мусора, сохраняем ссылку
                self.icon_image = icon_image
                return
            except Exception:
                pass

        # Если ничего не нашли, просто оставляем стандартную иконку

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
            messagebox.showwarning("Внимание", "Введите заголовок заметки")
            return
        if not content:
            messagebox.showwarning("Внимание", "Введите текст заметки")
            return

        if self.current_note_id is None:
            # Новая заметка
            self.cursor.execute(
                "INSERT INTO notes (title, content) VALUES (?, ?)",
                (title, content),
            )
            self.conn.commit()

            # Получаем id добавленной строки через cursor.lastrowid.[web:58][web:59][web:64]
            new_id = self.cursor.lastrowid
            self.current_note_id = new_id

            # Читаем созданную строку, чтобы отобразить даты
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
            # Обновление: updated_at = текущий момент
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

            # Читаем актуальные даты
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
            messagebox.showwarning("Внимание", "Сначала выберите заметку")
            return

        if messagebox.askyesno("Подтверждение", "Удалить эту заметку?"):
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
        """
        Небольшое всплывающее окно (toast), не блокирует интерфейс.[web:44]
        """
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)

        self.root.update_idletasks()
        x = self.root.winfo_rootx() + self.root.winfo_width() - 230
        y = self.root.winfo_rooty() + self.root.winfo_height() - 90
        toast.geometry(f"220x50+{x}+{y}")

        frame = ttk.Frame(toast, style="Main.TFrame")
        frame.pack(fill="both", expand=True)

        label = ttk.Label(
            frame,
            text=message,
            font=("Segoe UI", 9),
            anchor="center",
        )
        label.pack(fill="both", expand=True, padx=5, pady=5)

        toast.after(duration, toast.destroy)

    # ---------- Закрытие ----------

    def on_close(self):
        self.conn.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = NotesApp(root)
    root.mainloop()
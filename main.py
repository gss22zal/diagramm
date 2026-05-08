import tkinter as tk
from tkinter import ttk, messagebox
import pyodbc
from datetime import datetime
import threading
import subprocess
import sys
import os
from dotenv import load_dotenv
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

# Загрузка переменных из .env
load_dotenv()

class HealthReportApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Отчёт по результатам тестирования")
        self.root.geometry("1200x800")
        
        # Настройки подключения к БД из .env
        self.db_config = {
            'server': os.getenv('DB_SERVER', 'localhost'),
            'database': os.getenv('DB_NAME', 'health_db'),
            'username': os.getenv('DB_USER', ''),
            'password': os.getenv('DB_PASSWORD', ''),
            'driver': os.getenv('DB_DRIVER', '{ODBC Driver 17 for SQL Server}')
        }
        
        self.conn = None
        self.connect_to_db()
        
        self.create_widgets()
        self.load_persons()
        
    def connect_to_db(self):
        """Подключение к базе данных"""
        try:
            conn_str = (
                f"DRIVER={self.db_config['driver']};"
                f"SERVER={self.db_config['server']};"
                f"DATABASE={self.db_config['database']};"
                f"UID={self.db_config['username']};"
                f"PWD={self.db_config['password']};"
            )
            self.conn = pyodbc.connect(conn_str)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось подключиться к БД:\n{e}")
            self.root.destroy()
    
    def parse_number(self, value):
        """Преобразование строки в число с учетом русского формата (запятая)"""
        if value is None:
            return None
        try:
            cleaned = str(value).replace(',', '.').strip()
            # Убираем нечисловые символы, кроме точки и минуса
            cleaned = ''.join(c for c in cleaned if c.isdigit() or c in '.-')
            return float(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None
    
    def create_widgets(self):
        """Создание виджетов интерфейса"""
        # Панель фильтров
        filter_frame = ttk.LabelFrame(self.root, text="Фильтры")
        filter_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Выбор человека
        ttk.Label(filter_frame, text="Пациент:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.E)
        self.person_var = tk.StringVar()
        self.person_combo = ttk.Combobox(filter_frame, textvariable=self.person_var, state="readonly", width=25)
        self.person_combo.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        self.person_combo.bind('<<ComboboxSelected>>', self.on_person_selected)
        
        # Выбор даты
        ttk.Label(filter_frame, text="Дата тестирования:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.E)
        self.date_var = tk.StringVar()
        self.date_combo = ttk.Combobox(filter_frame, textvariable=self.date_var, state="readonly", width=20)
        self.date_combo.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)
        self.date_combo.bind('<<ComboboxSelected>>', self.on_date_selected)
         # --- КНОПКА УДАЛЕНИЯ ---
        ttk.Button(filter_frame, text="🗑 Удалить", command=self.delete_selected_records).grid(row=0, column=4, padx=6, pady=5)
        #  КНОПКА Импорт PDF
        self.import_btn = ttk.Button(filter_frame, text="📥 Импорт PDF", command=self.start_pdf_import)
        self.import_btn.grid(row=0, column=5, padx=4, pady=5)


        # Выбор системы организма
        ttk.Label(filter_frame, text="Система организма:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.E)
        self.system_var = tk.StringVar()
        self.system_combo = ttk.Combobox(filter_frame, textvariable=self.system_var, state="readonly", width=25)
        self.system_combo.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        self.system_combo.bind('<<ComboboxSelected>>', self.on_system_selected)
        
        # Кнопка обновления
        ttk.Button(filter_frame, text="Обновить", command=self.load_report).grid(row=1, column=3, padx=5, pady=5)
        # Кнопка диаграмм
        ttk.Button(filter_frame, text="📊 Диаграммы", command=self.open_chart_window).grid(row=1, column=2, padx=5, pady=5)
       
       
        
        self.import_status = ttk.Label(filter_frame, text="", foreground="blue")
        self.import_status.grid(row=1, column=5, padx=5, pady=5, sticky=tk.W)

        # Информация о пациенте
        info_frame = ttk.LabelFrame(self.root, text="Информация о пациенте")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.info_label = ttk.Label(info_frame, text="", font=("Arial", 10))
        self.info_label.pack(anchor=tk.W)
        
        # Таблица результатов
        table_frame = ttk.LabelFrame(self.root, text="Результаты измерений")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Создаем Canvas и Scrollbars для прокрутки
        self.canvas = tk.Canvas(table_frame)
        scrollbar_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.canvas.yview)
        scrollbar_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.canvas.xview)
        
        self.scrollable_frame = tk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        # Статусная строка
        self.status_label = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM)
    
    def load_persons(self):
        """Загрузка списка пациентов"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT DISTINCT person_name FROM health_results ORDER BY person_name")
            persons = [row[0] for row in cursor.fetchall()]
            self.person_combo['values'] = persons
            if persons:
                self.person_combo.current(0)
                self.on_person_selected(None)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить список пациентов:\n{e}")
    
    def on_person_selected(self, event):
        """Обработка выбора пациента"""
        person = self.person_var.get()
        if not person: return
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT DISTINCT test_date FROM health_results 
                WHERE person_name = ? ORDER BY test_date DESC
            """, (person,))
            dates = [row[0].strftime("%d.%m.%Y %H:%M") for row in cursor.fetchall()]
            self.date_combo['values'] = dates
            if dates:
                self.date_combo.current(0)
                self.on_date_selected(None)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить даты:\n{e}")
    
    def on_date_selected(self, event):
        # Обработка выбора даты БЕЗ сброса фильтра системы организма
        person = self.person_var.get()
        date_str = self.date_var.get()
        if not person or not date_str:
            return

        # 1. Запоминаем текущий выбор системы ДО обновления списка
        old_system = self.system_var.get()

        try:
            date = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT DISTINCT system_name 
                FROM health_results 
                WHERE person_name = ? AND test_date = ?
                ORDER BY system_name
            """, (person, date))
            
            systems = [row[0] for row in cursor.fetchall()]
            self.system_combo['values'] = systems
            
            # 2. Пытаемся восстановить предыдущий выбор
            if old_system in systems:
                self.system_combo.set(old_system)
            elif systems:
                self.system_combo.current(0)
            else:
                self.system_var.set('')
                
            # 3. Загружаем отчёт
            self.load_report()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить системы:\n{e}")
    
    def on_system_selected(self, event):
        """Обработка выбора системы"""
        self.load_report()
    
    def load_report(self):
        """Загрузка и отображение отчёта"""
        person = self.person_var.get()
        date_str = self.date_var.get()
        system = self.system_var.get()
        if not all([person, date_str, system]): return
        
        try:
            date = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
            for widget in self.scrollable_frame.winfo_children(): widget.destroy()
            
            headers = ["Измеряемый параметр", "Диапазон нормальных значений", "Результат", "Интерпретация результата"]
            for i, header in enumerate(headers):
                tk.Label(self.scrollable_frame, text=header, font=("Arial", 10, "bold"), 
                         borderwidth=1, relief="solid", padx=5, pady=5, width=33, anchor="w").grid(row=0, column=i, sticky="nsew")
            
            self.scrollable_frame.grid_columnconfigure(0, weight=1, minsize=300)
            for i in range(1, 4): self.scrollable_frame.grid_columnconfigure(i, weight=0, minsize=150)
            
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT parameter_name, parameter_value FROM health_results
                WHERE person_name = ? AND test_date = ? AND system_name = ? ORDER BY parameter_name
            """, (person, date, system))
            results = cursor.fetchall()
            
            cursor.execute("""
                SELECT parameter_name, norm_min, norm_max,
                       minor_high_min, minor_high_max, significant_high_min, significant_high_max, severe_high_min,
                       minor_low_min, minor_low_max, significant_low_min, significant_low_max, severe_low_max
                FROM reference_values WHERE system_name = ?
            """, (system,))
            ref_values = {row[0]: row[1:] for row in cursor.fetchall()}
            
            for idx, (param_name, param_value) in enumerate(results, start=1):
                result_value = self.parse_number(param_value)
                if result_value is None:
                    tk.Label(self.scrollable_frame, text=param_name, borderwidth=1, relief="solid", padx=5, pady=5, anchor="w").grid(row=idx, column=0, sticky="nsew")
                    for c in range(1, 4):
                        tk.Label(self.scrollable_frame, text="Нет данных" if c==1 else "-", borderwidth=1, relief="solid", padx=5, pady=5, anchor="center").grid(row=idx, column=c, sticky="nsew")
                    continue
                
                if param_name in ref_values:
                    ref = ref_values[param_name]
                    norm_min, norm_max = self.parse_number(ref[0]), self.parse_number(ref[1])
                    interpretation, bg_color = self.get_interpretation(result_value, ref)
                    norm_range = f"{norm_min:g} - {norm_max:g}"
                else:
                    interpretation, bg_color = "Нет референса", "#FFFFFF"
                    norm_range = "Нет данных"
                
                tk.Label(self.scrollable_frame, text=param_name, borderwidth=1, relief="solid", padx=5, pady=5, anchor="w").grid(row=idx, column=0, sticky="nsew")
                tk.Label(self.scrollable_frame, text=norm_range, borderwidth=1, relief="solid", padx=5, pady=5, anchor="center").grid(row=idx, column=1, sticky="nsew")
                tk.Label(self.scrollable_frame, text=f"{result_value:g}".replace('.', ','), borderwidth=1, relief="solid", padx=5, pady=5, anchor="center").grid(row=idx, column=2, sticky="nsew")
                
                fg = "white" if bg_color == "#DC143C" else "black"
                tk.Label(self.scrollable_frame, text=interpretation, bg=bg_color, fg=fg, borderwidth=1, relief="solid", padx=5, pady=5, anchor="center").grid(row=idx, column=3, sticky="nsew")
            
            self.update_patient_info(person, date, system)
            self.status_label.config(text=f"Загружено параметров: {len(results)}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить отчёт:\n{e}")
    
    def get_interpretation(self, value, ref):
        """Определение интерпретации результата и цвета"""
        norm_min = self.parse_number(ref[0])
        norm_max = self.parse_number(ref[1])
        
        if norm_min is not None and norm_max is not None and norm_min <= value <= norm_max:
            return "нормально", "#90EE90"
        
        # Проверка высоких значений (используем полные диапазоны как на диаграммах)
        if value > norm_max:
            # Серьезные нарушения (+++) - выше severe_high_min
            if ref[6] is not None and value >= self.parse_number(ref[6]):
                return "серьезные нарушения (+++)", "#DC143C"
            
            # Значительные изменения (++) - от significant_high_min до significant_high_max
            if ref[4] is not None and ref[5] is not None:
                significant_min = self.parse_number(ref[4])
                significant_max = self.parse_number(ref[5])
                if significant_min is not None and significant_max is not None:
                    if significant_min <= value <= significant_max:
                        return "значительные изменения (++)", "#FFD700"
                elif significant_min is not None and value >= significant_min:
                    return "значительные изменения (++)", "#FFD700"
            
            # Незначительные изменения (+) - от minor_high_min до minor_high_max
            if ref[2] is not None and ref[3] is not None:
                minor_min = self.parse_number(ref[2])
                minor_max = self.parse_number(ref[3])
                if minor_min is not None and minor_max is not None:
                    if minor_min <= value <= minor_max:
                        return "незначительные изменения (+)", "#87CEEB"
                elif minor_min is not None and value >= minor_min:
                    return "незначительные изменения (+)", "#87CEEB"
        
        # Проверка низких значений (используем полные диапазоны как на диаграммах)
        if value < norm_min:
            # Серьезные нарушения (---) - ниже severe_low_max
            if ref[11] is not None and value <= self.parse_number(ref[11]):
                return "серьезные нарушения (---)", "#DC143C"
            
            # Значительные изменения (--) - от significant_low_min до significant_low_max
            if ref[9] is not None and ref[10] is not None:
                significant_min = self.parse_number(ref[9])
                significant_max = self.parse_number(ref[10])
                if significant_min is not None and significant_max is not None:
                    if significant_min <= value <= significant_max:
                        return "значительные изменения (--)", "#FFD700"
                elif significant_max is not None and value <= significant_max:
                    return "значительные изменения (--)", "#FFD700"
            
            # Незначительные изменения (-) - от minor_low_min до minor_low_max
            if ref[7] is not None and ref[8] is not None:
                minor_min = self.parse_number(ref[7])
                minor_max = self.parse_number(ref[8])
                if minor_min is not None and minor_max is not None:
                    if minor_min <= value <= minor_max:
                        return "незначительные изменения (-)", "#87CEEB"
                elif minor_max is not None and value <= minor_max:
                    return "незначительные изменения (-)", "#87CEEB"
        
        return "нормально", "#90EE90"
    
    def update_patient_info(self, person, date, system):
        try:
            info_text = f"Имя: {person}  |  Время тестирования: {date.strftime('%d.%m.%Y %H:%M')}  |  Система: {system}"
            self.info_label.config(text=info_text)
        except: pass

    # ───────────── ФУНКЦИЯ: ДИАГРАММЫ ─────────────
    def open_chart_window(self):
        person = self.person_var.get()
        system = self.system_var.get()
        if not person or not system:
            messagebox.showwarning("Внимание", "Сначала выберите пациента и систему организма.")
            return

        chart_win = tk.Toplevel(self.root)
        chart_win.title(f"Динамика параметров: {system}")
        chart_win.geometry("950x650")
        chart_win.transient(self.root)

        # Панель управления графиком
        ctrl_frame = ttk.Frame(chart_win)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(ctrl_frame, text="Параметр:").pack(side=tk.LEFT, padx=5)
        param_var = tk.StringVar()
        param_combo = ttk.Combobox(ctrl_frame, textvariable=param_var, state="readonly", width=40)
        param_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Получаем список параметров для текущей системы
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT parameter_name FROM health_results 
            WHERE person_name = ? AND system_name = ? ORDER BY parameter_name
        """, (person, system))
        params = [row[0] for row in cursor.fetchall()]
        param_combo['values'] = params
        if params: param_combo.current(0)

        # Matplotlib Figure
        plt.style.use('default')
        fig = plt.Figure(figsize=(9, 5.5), dpi=100)
        ax = fig.add_subplot(111)
        canvas = FigureCanvasTkAgg(fig, master=chart_win)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        def update_plot(event=None):
            ax.clear()
            selected = param_var.get()
            if not selected: return

            # Загрузка данных по датам
            cursor.execute("""
                SELECT test_date, parameter_value FROM health_results 
                WHERE person_name = ? AND system_name = ? AND parameter_name = ? 
                ORDER BY test_date
            """, (person, system, selected))
            rows = cursor.fetchall()

            valid_data = []
            for dt, val in rows:
                v = self.parse_number(val)
                if v is not None: valid_data.append((dt, v))

            if not valid_data:
                ax.text(0.5, 0.5, "Нет числовых данных для построения графика", ha='center', va='center', transform=ax.transAxes, fontsize=12)
                canvas.draw()
                return

            dates, values = zip(*valid_data)
                    
            # Определяем диапазон дат для расчета 1-х чисел
            min_date = min(dates)
            max_date = max(dates)

            # Загрузка референсов
            cursor.execute("""
                SELECT norm_min, norm_max, minor_high_min, minor_high_max, 
                    significant_high_min, significant_high_max, severe_high_min,
                    minor_low_min, minor_low_max, significant_low_min, significant_low_max, severe_low_max
                FROM reference_values WHERE parameter_name = ? AND system_name = ?
            """, (selected, system))
            ref = cursor.fetchone()

            # Определение границ Y для зон
            y_data_min, y_data_max = min(values), max(values)
            y_margin = (y_data_max - y_data_min) * 0.2 if y_data_max != y_data_min else 1.0
            plot_min, plot_max = y_data_min - y_margin, y_data_max + y_margin

            # Парсим референсные значения
            ref_vals = [self.parse_number(x) for x in ref] if ref else [None]*12
            
            # Корректируем границы графика, чтобы включить референсные значения
            if ref:
                ref_valid = [v for v in ref_vals if v is not None]
                if ref_valid:
                    plot_min = min(plot_min, min(ref_valid) - y_margin)
                    plot_max = max(plot_max, max(ref_valid) + y_margin)

            # Отрисовка цветных зон (ИСПРАВЛЕННАЯ ЛОГИКА)
            zones = []
            
            # 1. Низкие отклонения (используем конкретные min/max колонки)
            if ref_vals[7] is not None and ref_vals[8] is not None:
                zones.append((ref_vals[7], ref_vals[8], '#64adfa', 'Незначительные отклонения (-)'))
            if ref_vals[9] is not None and ref_vals[10] is not None:
                zones.append((ref_vals[9], ref_vals[10], '#f8d76a', 'Значительные отклонения (--)'))
            if ref_vals[11] is not None:
                zones.append((plot_min, ref_vals[11], '#f76666', 'Серьезные отклонения (---)'))
            
            # 2. Норма
            if ref_vals[0] is not None and ref_vals[1] is not None:
                zones.append((ref_vals[0], ref_vals[1], "#86f6a0", 'Норма'))
                
            # 3. Высокие отклонения (используем конкретные min/max колонки)
            if ref_vals[2] is not None and ref_vals[3] is not None:
                zones.append((ref_vals[2], ref_vals[3], "#64adfa", 'Незначительные отклонения (+)'))
            if ref_vals[4] is not None and ref_vals[5] is not None:
                zones.append((ref_vals[4], ref_vals[5], "#f8d76a", 'Значительные отклонения (++)'))
            if ref_vals[6] is not None:
                zones.append((ref_vals[6], plot_max, "#f76666", 'Серьезные отклонения (+++)'))

            # Рисуем зоны
            drawn_labels = set()
            for start, end, color, label in zones:
                # Проверка на корректный диапазон (start < end)
                if start < end:
                    ax.axhspan(start, end, color=color, alpha=0.4, label=label if label not in drawn_labels else "")
                    drawn_labels.add(label)

            # Генерируем даты 1-го числа для каждого месяца в диапазоне
            current_date = min_date.replace(day=1)
            while current_date <= max_date:
                ax.axvline(x=current_date, color='black', linestyle='-', linewidth=1.5, alpha=1, zorder=2)
                
                # Переход к следующему месяцу
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)

            # Линия графика
            ax.plot(dates, values, marker='o', linestyle='-', color='#0056b3', linewidth=2, markersize=6, label='Результат')

            ax.set_title(f"Динамика: {selected}", fontsize=14, pad=10)
            ax.set_xlabel("Дата тестирования", fontsize=11)
            ax.set_ylabel("Значение параметра", fontsize=11)
            ax.grid(True, linestyle='--', alpha=0.5)
            ax.set_ylim(plot_min, plot_max)
            
            # Форматирование дат на оси X
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
            fig.autofmt_xdate(rotation=45)

            ax.legend(loc='upper right', fontsize=9)
            canvas.draw()
        
            
        param_combo.bind('<<ComboboxSelected>>', update_plot)
        update_plot()

    def start_pdf_import(self):
        """Запускает импорт PDF в отдельном потоке"""
        self.import_btn.config(state=tk.DISABLED)
        self.import_status.config(text="⏳ Чтение и сохранение PDF...")
        self.root.config(cursor="watch")
        
        # Запускаем тяжёлую операцию в фоне
        thread = threading.Thread(target=self._run_import_thread, daemon=True)
        thread.start()

    def _run_import_thread(self):
        """Фоновая задача: запускает save_health_data.py"""
        try:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "save_health_data.py")
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                encoding='utf-8', 
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            self.root.after(0, self._on_import_finished, result)
        except Exception as e:
            self.root.after(0, self._on_import_error, str(e))

    def _on_import_finished(self, result):
        """Вызывается после завершения импорта"""
        self.root.config(cursor="")
        self.import_btn.config(state=tk.NORMAL)
        self.import_status.config(text="")
        
        # Безопасное получение вывода (защита от None)
        output = (result.stdout or "").strip()
        success_line = [line for line in output.split('\n') if 'УСПЕШНО' in line]
        msg = success_line[0] if success_line else "PDF файлы успешно обработаны!"
        
        if result.returncode == 0:
            messagebox.showinfo("Импорт завершён", msg)
            self.load_persons()  # Обновляем списки
        else:
            error_msg = (result.stderr or "Неизвестная ошибка")[:300]
            messagebox.showerror("Ошибка импорта", f"Не удалось обработать PDF:\n{error_msg}")

    def _on_import_error(self, error_msg):
        """Обработка ошибок запуска потока"""
        self.root.config(cursor="")
        self.import_btn.config(state=tk.NORMAL)
        self.import_status.config(text="")
        messagebox.showerror("Ошибка запуска", f"Не удалось запустить парсер:\n{error_msg}")

    def delete_selected_records(self):
        """Удаление всех записей выбранного пациента за выбранную дату"""
        person = self.person_var.get()
        date_str = self.date_var.get()

        # Проверка, выбраны ли данные
        if not person or not date_str:
            messagebox.showwarning("Внимание", "Для удаления необходимо выбрать Пациента и Дату.")
            return

        # Запрос подтверждения
        confirmation = messagebox.askyesno(
            "Подтверждение удаления",
            f"Вы действительно хотите удалить все результаты\n"
            f"для пациента '{person}' за {date_str}?\n"
            "Это действие нельзя отменить.",
            icon='warning'
        )

        if confirmation:
            try:
                cursor = self.conn.cursor()
                
                # Преобразуем строку даты обратно в объект datetime
                date_obj = datetime.strptime(date_str, "%d.%m.%Y %H:%M")

                # Выполняем удаление
                delete_query = """
                    DELETE FROM health_results 
                    WHERE person_name = ? AND test_date = ?
                """
                cursor.execute(delete_query, (person, date_obj))
                self.conn.commit()

                # Уведомление об успехе
                messagebox.showinfo("Успех", f"Данные для {person} за {date_str} успешно удалены.")

                # Обновляем списки, так как дата могла быть единственной для пациента
                self.load_persons()

            except Exception as e:
                messagebox.showerror("Ошибка БД", f"Не удалось удалить данные:\n{e}")

def main():
    root = tk.Tk()
    app = HealthReportApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
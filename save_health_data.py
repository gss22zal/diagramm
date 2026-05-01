# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
import re
import glob
import pdfplumber
import pyodbc
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ───────────── НАСТРОЙКИ ПОДКЛЮЧЕНИЯ ─────────────
DB_CONFIG = {
    "server": os.getenv("DB_SERVER", "localhost"),
    "database": os.getenv("DB_NAME", "health_db"),
    "username": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "driver": os.getenv("DB_DRIVER", "{ODBC Driver 17 for SQL Server}")
}

PDF_FOLDER = os.getenv("PDF_FOLDER", "pdf_files")

def get_db_connection():
    """Устанавливает соединение с SQL Server"""
    required = ["server", "database", "username", "password", "driver"]
    missing = [k for k in required if not DB_CONFIG.get(k)]
    if missing:
        print(f"Отсутствуют параметры в .env: {', '.join(missing)}")
        return None

    conn_str = (
        f"DRIVER={DB_CONFIG['driver']};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['username']};"
        f"PWD={DB_CONFIG['password']};"
    )
    try:
        return pyodbc.connect(conn_str)
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        return None

def extract_date_time(raw_text):
    """Надежное извлечение даты и времени с нормализацией текста"""
    # Заменяем все переносы строк, табуляцию и спецпробелы на один обычный пробел
    normalized = re.sub(r'[\s\xa0\r\n]+', ' ', raw_text)
    
    # Ищем: "Время тестирования: ДД.ММ.ГГГГ ЧЧ:ММ"
    match = re.search(r'Время\s+тестирования:\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})', normalized)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    
    # Альтернативный поиск, если формат немного отличается
    date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', normalized)
    time_match = re.search(r'(\d{2}:\d{2})', normalized)
    if date_match and time_match:
        return f"{date_match.group(1)} {time_match.group(1)}"
    
    return None

def parse_pdf(pdf_path):
    """Извлекает данные из одного PDF файла"""
    if not os.path.exists(pdf_path):
        return None, None, []

    records = []
    name = None
    date_str = None
    
    # Заголовки таблиц, которые нужно ИГНОРИРОВАТЬ
    skip_headers = {
        "измеряемый параметр", "диапазон нормальных значений", "результат",
        "интерпретация результата", "классификация состава", "величина",
        "содержание воды в организме", "мышечная масса", "обезжиренный вес",
        "вес тела", "свойство", "недостаток", "стандарт", "превышение",
        "определение питания", "общая оценка", "контроль веса", "расчетный вес",
        "оценка телосложения", "вероятность появления проблем", "система",
        "типы мышц", "состояние питания", "верхний и нижний баланс", "симметрия",
        "общий отчет", "---", "||", "напитков"
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Собираем весь текст для метаданных
            full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            
            # ── Имя ──
            name_match = re.search(r'Имя:\s*(\S+)', full_text)
            name = name_match.group(1) if name_match else "Unknown"

            # ── Дата ──
            date_str = extract_date_time(full_text)
            if not date_str:
                date_str = datetime.now().strftime("%d.%m.%Y %H:%M")

            # ── Парсинг по страницам ──
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text() or ""
                
                # Ищем заголовок системы (например, "Сердечно-сосудистая система")
                system_match = re.search(r'Отчёт по результатам тестирования\s*\((.*?)\)', page_text)
                system_name = system_match.group(1).strip() if system_match else "Общий отчет"
                
                # Пропускаем страницы с общим отчетом (там только рекомендации)
                if system_name == "Общий отчет":
                    continue

                tables = page.extract_tables()
                if not tables:
                    continue
                    
                for table in tables:
                    for row in table:
                        if not row or len(row) < 3:
                            continue
                        
                        # Нормализуем текст ячейки (убираем \n, \t)
                        param_name = re.sub(r'\s+', ' ', str(row[0])).strip() if row[0] else ""
                        param_value = re.sub(r'\s+', ' ', str(row[2])).strip() if row[2] else ""
                        
                        # 1. Пропускаем точные заголовки таблиц
                        if param_name.lower() in skip_headers:
                            continue
                            
                        # 2. Пропускаем мусор
                        if any(kw in param_name.lower() for kw in ["рекомендации", "отчет", "страница", "объяснение", "формула"]):
                            continue
                            
                        if not param_name or not param_value:
                            continue
                        if param_value.lower() in ["+", "-", "++", "#", "none", ""]:
                            continue
                        if not any(c.isalpha() for c in param_name):
                            continue
                        if len(param_name) < 3:
                            continue
                        
                        records.append((name, date_str, system_name, param_name, param_value))
            
    except Exception as e:
        print(f"  Ошибка чтения файла {os.path.basename(pdf_path)}: {e}")
        return None, None, []
    
    return name, date_str, records

def insert_records(conn, records):
    """Сохраняет все данные в SQL Server"""
    if not records:
        return 0, 0
    
    cursor = conn.cursor()
    success = 0
    errors = 0
    
    insert_query = """
        INSERT INTO health_results (person_name, test_date, system_name, parameter_name, parameter_value)
        VALUES (?, ?, ?, ?, ?)
    """
    
    for name, date_str, system_name, param, val in records:
        try:
            dt_obj = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
            cursor.execute(insert_query, name, dt_obj, system_name, param, val)
            success += 1
        except Exception as e:
            print(f"     Ошибка вставки ({param[:20]}): {str(e)[:60]}")
            errors += 1
    
    conn.commit()
    cursor.close()
    return success, errors

def main():
    print("=" * 60)
    print("ПАКЕТНАЯ ОБРАБОТКА PDF В SQL SERVER")
    print("=" * 60)
    
    # 1. Проверяем папку
    if not os.path.exists(PDF_FOLDER):
        print(f"Папка '{PDF_FOLDER}' не найдена. Создайте её и положите туда PDF файлы.")
        return

    # 2. Ищем все PDF файлы
    pdf_files = glob.glob(os.path.join(PDF_FOLDER, "*.pdf"))
    
    if not pdf_files:
        print(f"В папке '{PDF_FOLDER}' не найдено PDF файлов.")
        return
        
    print(f"Найдено файлов: {len(pdf_files)}\n")
    
    all_records = []
    file_count = 0
    
    # 3. Обрабатываем каждый файл
    for file_path in pdf_files:
        file_name = os.path.basename(file_path)
        print(f" Обработка: {file_name}...")
        
        name, date_str, records = parse_pdf(file_path)
        
        if records:
            # Добавляем источник файла для отладки (необязательно, но полезно)
            # В БД у нас есть name и date, этого обычно достаточно для связки
            all_records.extend(records)
            file_count += 1
            print(f"    Извлечено записей: {len(records)}")
        else:
            print(f"    Данных не найдено.")

    print(f"\n{'='*60}")
    print(f"ИТОГО найдено записей: {len(all_records)} из {file_count} файлов")
    print(f"{'='*60}")
    
    if not all_records:
        print("Нет данных для сохранения.")
        return

    # 4. Сохраняем в БД
    conn = get_db_connection()
    if not conn:
        print("Нет подключения к БД.")
        return
    
    print("\nСохранение в базу данных...")
    success, errors = insert_records(conn, all_records)
    
    print(f"\n{'='*60}")
    print(f"УСПЕШНО СОХРАНЕНО: {success} записей")
    print(f"ОШИБОК ПРИ ВСТАВКЕ: {errors}")
    print(f"{'='*60}")
    
    conn.close()
    print("Соединение с БД закрыто.")

if __name__ == "__main__":
    main()
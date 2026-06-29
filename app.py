import streamlit as st
import pandas as pd
import numpy as np
import io
import calendar

# === КОНФИГУРАЦИЯ СТРАНИЦЫ ===
st.set_page_config(page_title="Komfort Analytics", page_icon="🏠", layout="wide")

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def clean_name(val):
    if pd.isna(val): return ''
    return str(val).strip().replace('\xa0', ' ').rstrip(',. ')

def clean_group(val):
    if pd.isna(val): return ''
    return str(val).replace(',', '').replace(' ', '').strip()

def safe_to_date(val):
    try:
        return pd.to_datetime(val, format='%d.%m.%Y')
    except:
        return pd.NaT

# === ЗАГОЛОВОК ===
st.title("🏠 Komfort Analytics")
st.markdown("**Цифровой финдиректор для гостиничного бизнеса**")

# === САЙДБАР ===
with st.sidebar:
    st.header("📂 Загрузка данных")
    uploaded_act = st.file_uploader("1️⃣ Акт реализации", type=['csv', 'xlsx', 'xls'])
    uploaded_cottages = st.file_uploader("2️⃣ Номерной фонд", type=['xlsx', 'xls'])
    
    if uploaded_act and uploaded_cottages:
        st.success("✅ Файлы загружены!")
    else:
        st.info("💡 Загрузите оба файла для анализа")

# === ГЛАВНАЯ ОБЛАСТЬ ===
if uploaded_act is None or uploaded_cottages is None:
    st.warning("⚠️ Загрузите оба файла, чтобы начать анализ")
else:
    try:
        with st.spinner("📖 Читаем и обрабатываем файлы..."):
            # 1. Читаем файл акта
            if uploaded_act.name.lower().endswith('.csv'):
                df_act = pd.read_csv(uploaded_act)
            else:
                df_act = pd.read_excel(uploaded_act)
                
            if 'Unnamed: 0' in df_act.columns:
                df_act.drop(columns=['Unnamed: 0'], inplace=True)
            
            # Удаляем строку "Итого" если есть
            df_act = df_act[~df_act['Дата акта'].astype(str).str.contains('Итого', na=False)]
            
            # Чистим данные
            df_act['Группа'] = df_act['Группа'].apply(clean_group)
            df_act['Коттедж'] = df_act['Коттедж'].apply(clean_name)
            df_act['Сумма с НДС'] = pd.to_numeric(df_act['Сумма с НДС'], errors='coerce').fillna(0)
            df_act['Количество'] = pd.to_numeric(df_act['Количество'], errors='coerce').fillna(0)
            df_act['НДС 5%'] = pd.to_numeric(df_act['НДС 5%'], errors='coerce').fillna(0)
            
            # Определяем целевой месяц
            df_act['Месяц акта'] = pd.to_datetime(df_act['Дата акта'], format='%d.%m.%Y', errors='coerce').dt.month
            target_month = df_act['Месяц акта'].mode()[0] if not df_act['Месяц акта'].mode().empty else 4
            target_year = 2026 
            days_in_month = calendar.monthrange(target_year, target_month)[1]

            # 2. Читаем номерной фонд
            df_cottages = pd.read_excel(uploaded_cottages, skiprows=1)
            df_cottages.columns = ['Тип', 'Коттедж', 'Площадь', 'Вместимость']
            df_cottages['Коттедж'] = df_cottages['Коттедж'].apply(clean_name)
            cottage_ref = dict(zip(df_cottages['Коттедж'], df_cottages['Вместимость']))
            
            for c in df_act['Коттедж'].unique():
                if c and c not in cottage_ref:
                    cottage_ref[c] = 4
            all_cottages = sorted(list(cottage_ref.keys()))

            # 3. Агрегация по фолио
            folio_services = {}
            for _, row in df_act.iterrows():
                folio = row.get('Фолио')
                service = str(row.get('Услуга/товар', '')).lower()
                amount = row.get('Сумма с НДС', 0)
                
                if pd.isna(folio) or not folio: continue
                
                if folio not in folio_services:
                    folio_services[folio] = {
                        'cottage': row.get('Коттедж', ''), 'group': row.get('Группа', ''),
                        'fio': row.get('ФИО', ''), 'check_in': row.get('Дата заезда', ''),
                        'check_out': row.get('Дата выезда', ''),
                        'accommodation_sum': 0, 'extra_bed_sum': 0, 'other_sum': 0
                    }
                
                if 'прожив' in service and 'домашн' not in service and 'животн' not in service:
                    folio_services[folio]['accommodation_sum'] += amount
                elif 'дополнит' in service or ('доп' in service and 'мест' in service):
                    folio_services[folio]['extra_bed_sum'] += amount
                else:
                    folio_services[folio]['other_sum'] += amount

            # 4. Расчет Коттедж-дней
            daily_bookings = []
            for folio, info in folio_services.items():
                d_in = safe_to_date(info['check_in'])
                d_out = safe_to_date(info['check_out'])
                if pd.isna(d_in) or pd.isna(d_out): continue
                
                actual_nights = (d_out - d_in).days
                if actual_nights <= 0: continue
                
                avg_price = info['accommodation_sum'] / actual_nights
                current = d_in
                while current < d_out:
                    if current.month == target_month and current.year == target_year:
                        daily_bookings.append({
                            'Дата': current.strftime('%d.%m.%Y'), 'Коттедж': info['cottage'], 
                            'Группа': info['group'], 'Фолио': folio, 'ФИО': info['fio'],
                            'Тип дня': 'Выходные' if current.dayofweek >= 5 else 'Будни',
                            'Цена за сутки': round(avg_price, 2)
                        })
                    current += pd.Timedelta(days=1)
            
            df_bookings = pd.DataFrame(daily_bookings)
            
            all_dates_list = pd.date_range(f'{target_year}-{target_month:02d}-01', f'{target_year}-{target_month:02d}-{days_in_month:02d}', freq='D')
            frame_data = [{'Дата': d.strftime('%d.%m.%Y'), 'Коттедж': c, 'Вместимость': cottage_ref.get(c, 4)} for d in all_dates_list for c in all_cottages]
            df_frame = pd.DataFrame(frame_data)
            
            df_occupancy = df_frame.merge(df_bookings, on=['Дата', 'Коттедж'], how='left')
            df_occupancy['Статус'] = df_occupancy['Фолио'].apply(lambda x: 'Занят' if pd.notna(x) else 'Свободен')
            df_occupancy = df_occupancy.fillna({'Группа': '', 'Фолио': '', 'ФИО': '', 'Тип дня': '', 'Цена за сутки': 0})
            df_occupancy = df_occupancy[['Дата', 'Коттедж', 'Группа', 'Вместимость', 'Статус', 'Тип дня', 'Цена за сутки', 'Фолио', 'ФИО']]

            # 5. Сводная загрузка
            df_summary_occ = df_occupancy.groupby('Коттедж', as_index=False).agg({
                'Вместимость': 'first',
                'Статус': lambda x: (x == 'Занят').sum(),
                'Цена за сутки': lambda x: x[x>0].mean() if (x>0).any() else 0
            }).rename(columns={'Статус': 'Занято дней', 'Цена за сутки': 'Средняя цена/ночь'})
            
            df_summary_occ['Всего дней'] = days_in_month
            df_summary_occ['Свободно дней'] = days_in_month - df_summary_occ['Занято дней']
            df_summary_occ['Загрузка, %'] = round(df_summary_occ['Занято дней'] / days_in_month * 100, 1)
            df_summary_occ = df_summary_occ.sort_values('Загрузка, %', ascending=False)
            
            # Добавляем строку ИТОГО для сводной загрузки
            total_row_occ = pd.Series({
                'Коттедж': 'ИТОГО',
                'Вместимость': df_summary_occ['Вместимость'].sum(),
                'Занято дней': df_summary_occ['Занято дней'].sum(),
                'Средняя цена/ночь': df_summary_occ[df_summary_occ['Коттедж']!='ИТОГО']['Средняя цена/ночь'].mean(),
                'Всего дней': df_summary_occ['Всего дней'].sum(),
                'Свободно дней': df_summary_occ['Свободно дней'].sum(),
                'Загрузка, %': round(df_summary_occ['Занято дней'].sum() / df_summary_occ['Всего дней'].sum() * 100, 1)
            })
            df_summary_occ = pd.concat([df_summary_occ, total_row_occ.to_frame().T], ignore_index=True)

            # 6. Детализация выручки
            revenue_data = []
            for folio, info in folio_services.items():
                total_rev = info['accommodation_sum'] + info['extra_bed_sum'] + info['other_sum']
                revenue_data.append({
                    'Дата выезда': info['check_out'], 'Коттедж': info['cottage'], 'Группа': info['group'],
                    'Фолио': folio, 'ФИО': info['fio'],
                    'Проживание': round(info['accommodation_sum'], 2),
                    'Доп. место': round(info['extra_bed_sum'], 2),
                    'Доп. услуги': round(info['other_sum'], 2),
                    'Итого выручка': round(total_rev, 2)
                })
            df_revenue = pd.DataFrame(revenue_data).sort_values('Дата выезда')
            
            # Добавляем строку ИТОГО для детализации выручки
            total_row_rev = pd.Series({
                'Дата выезда': 'ИТОГО',
                'Коттедж': '',
                'Группа': '',
                'Фолио': '',
                'ФИО': '',
                'Проживание': df_revenue['Проживание'].sum(),
                'Доп. место': df_revenue['Доп. место'].sum(),
                'Доп. услуги': df_revenue['Доп. услуги'].sum(),
                'Итого выручка': df_revenue['Итого выручка'].sum()
            })
            df_revenue = pd.concat([df_revenue, total_row_rev.to_frame().T], ignore_index=True)
            
            # Добавляем строку ИТОГО для "Все данные"
            total_row_all = pd.Series({
                'Дата акта': 'ИТОГО',
                'Контрагент': '',
                'Группа': '',
                'Коттедж': '',
                'Фолио': '',
                'ФИО': '',
                'Дата заезда': '',
                'Дата выезда': '',
                'Услуга/товар': '',
                'Количество': df_act['Количество'].sum(),
                'Сумма с НДС': df_act['Сумма с НДС'].sum(),
                'НДС 5%': df_act['НДС 5%'].sum()
            })
            df_act_with_total = pd.concat([df_act, total_row_all.to_frame().T], ignore_index=True)

        # === ИНТЕРФЕЙС ===
        real_sum = df_act['Сумма с НДС'].sum()
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("📊 Всего услуг", len(df_act))
        with col2: st.metric("💰 Выручка", f"{real_sum:,.2f} ₽")
        with col3: st.metric("🏠 Уникальных фолио", df_act['Фолио'].nunique())
        with col4: st.metric("📅 Период анализа", f"{target_month:02d}.{target_year} ({days_in_month} дн.)")

        st.markdown("---")
        
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Все данные", "📊 Коттедж-дни", "📈 Сводная загрузка", "💰 Детализация выручки"])
        
        with tab1:
            st.header("Все услуги из акта")
            st.dataframe(df_act_with_total, use_container_width=True, height=400)
            
        with tab2:
            st.header(f"Загрузка коттеджей ({target_month:02d}.{target_year})")
            st.info(f"Всего строк: {len(df_occupancy)} | Занято: {len(df_occupancy[df_occupancy['Статус']=='Занят'])} | Свободно: {len(df_occupancy[df_occupancy['Статус']=='Свободен'])}")
            
            # Функция для подсветки
            def highlight_status(val):
                if val == 'Занят':
                    return 'background-color: #FFC7CE'  # Красный
                elif val == 'Свободен':
                    return 'background-color: #C6EFCE'  # Зеленый
                return ''
            
            # Применяем стилизацию
            styled_df = df_occupancy.style.applymap(highlight_status, subset=['Статус'])
            st.dataframe(styled_df, use_container_width=True, height=500)
            
        with tab3:
            st.header("Сводная загрузка по коттеджам")
            st.dataframe(df_summary_occ, use_container_width=True, height=400)
            
        with tab4:
            st.header("Финансовая детализация по фолио")
            st.dataframe(df_revenue, use_container_width=True, height=400)
            
                # Кнопка скачивания
                # Кнопка скачивания
        st.markdown("---")
        if st.button("💾 Скачать все отчеты в Excel"):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                workbook = writer.book
                
                # === СОЗДАЕМ ФОРМАТЫ ===
                header_format = workbook.add_format({
                    'bold': True, 'bg_color': '#4472C4', 'font_color': 'white', 
                    'border': 1, 'align': 'center', 'valign': 'vcenter'
                })
                
                # Обычные форматы
                money_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
                percent_format = workbook.add_format({'num_format': '0.0"%"', 'border': 1})
                integer_format = workbook.add_format({'num_format': '0', 'border': 1})
                
                busy_format = workbook.add_format({'bg_color': '#FFC7CE', 'border': 1})
                free_format = workbook.add_format({'bg_color': '#C6EFCE', 'border': 1})
                
                # Форматы для строки ИТОГО (желтый фон + формат числа)
                total_format = workbook.add_format({'bold': True, 'bg_color': '#FFFF99', 'border': 1})
                total_money_format = workbook.add_format({'bold': True, 'bg_color': '#FFFF99', 'border': 1, 'num_format': '#,##0.00'})
                total_percent_format = workbook.add_format({'bold': True, 'bg_color': '#FFFF99', 'border': 1, 'num_format': '0.0"%"'})
                total_integer_format = workbook.add_format({'bold': True, 'bg_color': '#FFFF99', 'border': 1, 'num_format': '0'})

                # === ЛИСТ 1: ВСЕ ДАННЫЕ ===
                df_act_with_total.to_excel(writer, sheet_name='Все данные', index=False)
                ws1 = writer.sheets['Все данные']
                for col_num, value in enumerate(df_act_with_total.columns):
                    ws1.write(0, col_num, value, header_format)
                
                for row_num in range(len(df_act_with_total)):
                    is_total = (df_act_with_total.iloc[row_num]['Дата акта'] == 'ИТОГО')
                    for col_num, col in enumerate(df_act_with_total.columns):
                        val = df_act_with_total.iloc[row_num, col_num]
                        
                        # Сначала проверяем ИТОГО, чтобы вся строка была желтой
                        if is_total:
                            if col in ['Сумма с НДС', 'НДС 5%']: fmt = total_money_format
                            elif col == 'Количество': fmt = total_integer_format
                            else: fmt = total_format
                        else:
                            if col in ['Сумма с НДС', 'НДС 5%']: fmt = money_format
                            else: fmt = None
                        
                        if pd.isna(val) or val is None: ws1.write(row_num + 1, col_num, "", fmt)
                        else: ws1.write(row_num + 1, col_num, val, fmt)
                
                for i, col in enumerate(df_act_with_total.columns):
                    max_len = max(df_act_with_total[col].astype(str).map(len).max(), len(str(col))) + 2
                    ws1.set_column(i, i, max_len)

                # === ЛИСТ 2: КОТТЕДЖ-ДНИ ===
                df_occupancy.to_excel(writer, sheet_name='Коттедж-дни', index=False)
                ws2 = writer.sheets['Коттедж-дни']
                for col_num, value in enumerate(df_occupancy.columns):
                    ws2.write(0, col_num, value, header_format)
                
                for row_num in range(len(df_occupancy)):
                    status = df_occupancy.iloc[row_num]['Статус']
                    for col_num, col in enumerate(df_occupancy.columns):
                        val = df_occupancy.iloc[row_num, col_num]
                        
                        if col == 'Статус':
                            fmt = busy_format if val == 'Занят' else free_format
                        elif col == 'Цена за сутки':
                            fmt = money_format
                        else:
                            fmt = None
                        
                        if pd.isna(val) or val is None: ws2.write(row_num + 1, col_num, "", fmt)
                        else: ws2.write(row_num + 1, col_num, val, fmt)
                
                for i, col in enumerate(df_occupancy.columns):
                    max_len = max(df_occupancy[col].astype(str).map(len).max(), len(str(col))) + 2
                    ws2.set_column(i, i, max_len)

                # === ЛИСТ 3: СВОДНАЯ ЗАГРУЗКА ===
                df_summary_occ.to_excel(writer, sheet_name='Сводная загрузка', index=False)
                ws3 = writer.sheets['Сводная загрузка']
                for col_num, value in enumerate(df_summary_occ.columns):
                    ws3.write(0, col_num, value, header_format)
                
                for row_num in range(len(df_summary_occ)):
                    is_total = (df_summary_occ.iloc[row_num]['Коттедж'] == 'ИТОГО')
                    for col_num, col in enumerate(df_summary_occ.columns):
                        val = df_summary_occ.iloc[row_num, col_num]
                        
                        # Сначала проверяем ИТОГО, чтобы вся строка была желтой
                        if is_total:
                            if col == 'Загрузка, %': fmt = total_percent_format
                            elif col == 'Средняя цена/ночь': fmt = total_money_format
                            elif col in ['Вместимость', 'Занято дней', 'Свободно дней', 'Всего дней']: fmt = total_integer_format
                            else: fmt = total_format
                        else:
                            if col == 'Загрузка, %': fmt = percent_format
                            elif col == 'Средняя цена/ночь': fmt = money_format
                            elif col in ['Вместимость', 'Занято дней', 'Свободно дней', 'Всего дней']: fmt = integer_format
                            else: fmt = None
                        
                        if pd.isna(val) or val is None: ws3.write(row_num + 1, col_num, "", fmt)
                        else: ws3.write(row_num + 1, col_num, val, fmt)
                
                for i, col in enumerate(df_summary_occ.columns):
                    max_len = max(df_summary_occ[col].astype(str).map(len).max(), len(str(col))) + 2
                    ws3.set_column(i, i, max_len)

                # === ЛИСТ 4: ДЕТАЛИЗАЦИЯ ВЫРУЧКИ ===
                df_revenue.to_excel(writer, sheet_name='Детализация выручки', index=False)
                ws4 = writer.sheets['Детализация выручки']
                for col_num, value in enumerate(df_revenue.columns):
                    ws4.write(0, col_num, value, header_format)
                
                for row_num in range(len(df_revenue)):
                    is_total = (df_revenue.iloc[row_num]['Дата выезда'] == 'ИТОГО')
                    for col_num, col in enumerate(df_revenue.columns):
                        val = df_revenue.iloc[row_num, col_num]
                        
                        # Сначала проверяем ИТОГО
                        if is_total:
                            if col in ['Проживание', 'Доп. место', 'Доп. услуги', 'Итого выручка']: fmt = total_money_format
                            else: fmt = total_format
                        else:
                            if col in ['Проживание', 'Доп. место', 'Доп. услуги', 'Итого выручка']: fmt = money_format
                            else: fmt = None
                        
                        if pd.isna(val) or val is None: ws4.write(row_num + 1, col_num, "", fmt)
                        else: ws4.write(row_num + 1, col_num, val, fmt)
                
                for i, col in enumerate(df_revenue.columns):
                    max_len = max(df_revenue[col].astype(str).map(len).max(), len(str(col))) + 2
                    ws4.set_column(i, i, max_len)

            st.download_button("📥 Скачать Excel", data=output.getvalue(), file_name="Komfort_Analytics.xlsx", mime="application/vnd.ms-excel")
            st.success("✅ Файл Excel сформирован с полным форматированием!")
    except Exception as e:
        st.error(f"❌ Ошибка: {e}")
        import traceback
        st.code(traceback.format_exc())
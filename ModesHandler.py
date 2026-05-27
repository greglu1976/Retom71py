import json
import os
import re
from Logger import logger
from Mode import Mode
from tkinter import messagebox
import openpyxl

class ModesHandler:

    def __init__(self, path_to_dir):
        self.inputs = 'inputs.json'
        self.outputs = 'outputs.json'
        self.path_to_dir = path_to_dir
        self.modes = []  # Список для хранения загруженных режимов
        self.status_var = None  # Будет установлен извне
        
        # Загружаем режимы из папки
        self._load_modes_from_folder()
        
        # Сортируем режимы человеческим способом
        self._sort_modes_natural()
        
        # Загружаем JSON файлы (если они есть в path_to_dir)
        self._load_json_files()
    
    def _natural_sort_key(self, text):
        """
        Создает ключ для человеческой сортировки строк с числами.
        Например: "Режим 2" < "Режим 10", а не наоборот
        """
        def convert(text_part):
            return int(text_part) if text_part.isdigit() else text_part.lower()
        
        return [convert(c) for c in re.split(r'(\d+)', text)]
    
    def _sort_modes_natural(self):
        """Сортирует режимы по имени в человеческом порядке (1, 2, 3... 10, 11)"""
        if not self.modes:
            return
        
        # Получаем имена всех режимов
        mode_names = []
        for mode in self.modes:
            if hasattr(mode, 'get_name'):
                name = mode.get_name()
            elif hasattr(mode, 'mode_name'):
                name = mode.mode_name
            elif hasattr(mode, 'file_path'):
                name = os.path.basename(mode.file_path)
            else:
                name = f"Mode_{len(mode_names)}"
            mode_names.append(name)
        
        # Сортируем режимы вместе с их именами
        sorted_pairs = sorted(zip(mode_names, self.modes), key=lambda x: self._natural_sort_key(x[0]))
        
        # Обновляем список режимов
        self.modes = [mode for _, mode in sorted_pairs]
        
        #logger.info("Modes", f"Sorted {len(self.modes)} modes naturally")
    
    def _load_modes_from_folder(self):
        """Загрузка режимов из Excel файлов в папке"""
        # Получаем список всех .xlsx и .xls файлов в папке
        excel_files = []
        for file in os.listdir(self.path_to_dir):
            if file.lower().endswith(('.xlsx', '.xls')):
                excel_files.append(os.path.join(self.path_to_dir, file))
        
        if not excel_files:
            logger.warning("Modes", f"No Excel files found in {self.path_to_dir}")
            return
        
        logger.info("Modes", f"Found {len(excel_files)} Excel files in folder")
        
        # Загружаем все режимы
        loaded_count = 0
        failed_files = []

        for filepath in excel_files:
            try:
                # Быстрая проверка валидности Excel файла
                try:
                    # Открываем workbook только для чтения
                    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
                    
                    # Проверяем наличие листа 'SGF_Parameters'
                    if 'SGF_Parameters' not in wb.sheetnames:
                        logger.warning("Modes", f"Skipping {os.path.basename(filepath)}: 'SGF_Parameters' sheet not found")
                        failed_files.append(os.path.basename(filepath))
                        wb.close()
                        continue
                    
                    wb.close()
                    
                except Exception as e:
                    logger.warning("Modes", f"Skipping {os.path.basename(filepath)}: Cannot open Excel file - {e}")
                    failed_files.append(os.path.basename(filepath))
                    continue
                
                # Если проверка пройдена, создаем объект Mode
                mode = Mode(filepath)
                
                # Если у Mode есть метод load, вызываем его
                if hasattr(mode, 'load'):
                    if mode.load():
                        self.modes.append(mode)
                        loaded_count += 1
                        #logger.info("Modes", f"Loaded mode: {mode.get_name() if hasattr(mode, 'get_name') else os.path.basename(filepath)}")
                    else:
                        failed_files.append(os.path.basename(filepath))
                else:
                    # Если нет метода load, просто добавляем
                    self.modes.append(mode)
                    loaded_count += 1
                    #logger.info("Modes", f"Added mode: {mode.get_name() if hasattr(mode, 'get_name') else os.path.basename(filepath)}")
                
            except Exception as e:
                logger.error("Modes", f"Failed to load {os.path.basename(filepath)}: {e}")
                failed_files.append(os.path.basename(filepath))
        
        # Выводим результат
        if loaded_count > 0:
            logger.info("Modes", f"Successfully loaded {loaded_count} modes")
        
        if failed_files:
            logger.warning("Modes", f"Failed to load: {', '.join(failed_files)}")



    def filter_io_data(self, data_dict):
        """
        Исключает из словаря ключи с аналоговыми сигналами (токи, напряжения)
        
        Args:
            data_dict: исходный словарь с данными inputs/outputs
        
        Returns:
            dict: отфильтрованный словарь только с дискретными сигналами
        """
        # Ключи для исключения (аналоговые сигналы)
        exclude_keys = [
            'IA', 'IB', 'IC', 'dIA', 'dIB', 'dIC',
            'IA1', 'IB1', 'IC1', 'dIA1', 'dIB1', 'dIC1',
            'UA1', 'dUA1', 'UB1', 'dUB1', 'UC1', 'dUC1',
            'UA2', 'dUA2', 'UB2', 'dUB2', 'UC2', 'dUC2',
            'IA2harm', 'IB2harm', 'IC2harm', 
            'IA5harm', 'IB5harm', 'IC5harm'            
        ]
        
        # Создаем новый словарь без исключенных ключей
        filtered_dict = {
            key: value for key, value in data_dict.items() 
            if key not in exclude_keys
        }
        
        return filtered_dict


    def _load_json_files(self):
        """Загрузка JSON файлов inputs.json и outputs.json"""
        # Загрузка inputs.json
        inputs_path = os.path.join(self.path_to_dir, self.inputs)
        if os.path.exists(inputs_path):
            try:
                with open(inputs_path, 'r', encoding='utf-8') as f:
                    self.inputs_data = json.load(f)
                #logger.info("Modes", f"Loaded inputs from {inputs_path}")
            except Exception as e:
                logger.error("Modes", f"Failed to load {inputs_path}: {e}")
                self.inputs_data = {}
        else:
            logger.warning("Modes", f"File not found: {inputs_path}")
            self.inputs_data = {}

        self.inputs_data = self.filter_io_data(self.inputs_data)

        # Загрузка outputs.json
        outputs_path = os.path.join(self.path_to_dir, self.outputs)
        if os.path.exists(outputs_path):
            try:
                with open(outputs_path, 'r', encoding='utf-8') as f:
                    self.outputs_data = json.load(f)
                #logger.info("Modes", f"Loaded outputs from {outputs_path}")
            except Exception as e:
                logger.error("Modes", f"Failed to load {outputs_path}: {e}")
                self.outputs_data = {}
        else:
            logger.warning("Modes", f"File not found: {outputs_path}")
            self.outputs_data = {}
    
    def get_modes_count(self):
        """Возвращает количество загруженных режимов"""
        return len(self.modes)
    
    def get_mode(self, index):
        """Возвращает режим по индексу"""
        if 0 <= index < len(self.modes):
            return self.modes[index]
        return None
    
    def get_all_modes(self):
        """Возвращает список всех режимов"""
        return self.modes.copy()
    
    def get_mode_names(self):
        """Возвращает список имен всех режимов (уже отсортированный)"""
        names = []
        for mode in self.modes:
            if hasattr(mode, 'get_name'):
                names.append(mode.get_name())
            elif hasattr(mode, 'mode_name'):
                names.append(mode.mode_name)
            elif hasattr(mode, 'file_path'):
                names.append(os.path.basename(mode.file_path))
            else:
                names.append(f"Mode_{len(names)+1}")
        return names
    
    def get_inputs_data(self):
        """Возвращает данные из inputs.json"""
        return self.inputs_data.copy() if hasattr(self, 'inputs_data') else {}
    
    def get_outputs_data(self):
        """Возвращает данные из outputs.json"""
        return self.outputs_data.copy() if hasattr(self, 'outputs_data') else {}
    
    def get_mode_by_name(self, name):
        """Возвращает режим по имени"""
        for mode in self.modes:
            mode_name = mode.get_name() if hasattr(mode, 'get_name') else mode.mode_name if hasattr(mode, 'mode_name') else None
            if mode_name == name:
                return mode
        return None
    
    def get_sorted_mode_names_with_index(self):
        """Возвращает список кортежей (индекс, имя) для ComboBox"""
        return [(i, name) for i, name in enumerate(self.get_mode_names())]
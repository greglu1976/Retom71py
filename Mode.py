import pandas as pd
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Mode:
    """Класс для работы с режимом выдачи и проверки устройства из Excel файла"""
    
    file_path: str
    mode_name: str = field(default="")  # Добавляем поле для имени режима
    sgf_parameters: Dict[str, Any] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """После инициализации загружаем данные из Excel"""
        # Устанавливаем имя режима из имени файла, если не задано
        if not self.mode_name:
            self.mode_name = Path(self.file_path).stem  # Имя файла без расширения
        self.load_from_excel()
    
    def load_from_excel(self) -> None:
        """
        Загружает данные из Excel файла.
        Ожидается структура: первая строка - наименования параметров,
        вторая строка - значения параметров.
        Листы: SGF_Parameters, Settings, Inputs, Outputs  
        """
        try:
            # Проверяем существование файла
            if not Path(self.file_path).exists():
                raise FileNotFoundError(f"Файл {self.file_path} не найден")
            
            # Загружаем все необходимые листы
            sheet_names = ['SGF_Parameters', 'Settings', 'Inputs', 'Outputs']
            
            for sheet in sheet_names:
                try:
                    # Читаем лист, берем только первые две строки
                    df = pd.read_excel(self.file_path, sheet_name=sheet, header=None, nrows=2)
                    
                    if df.shape[1] == 0:
                        print(f"Предупреждение: Лист '{sheet}' пуст")
                        setattr(self, self._get_attribute_name(sheet), {})
                        continue
                    
                    # Первая строка - наименования параметров
                    # Вторая строка - значения параметров
                    param_names = df.iloc[0].dropna().tolist()
                    param_values = df.iloc[1].dropna().tolist() if df.shape[0] > 1 else []
                    
                    # Создаем словарь параметров
                    params_dict = {}
                    for i, name in enumerate(param_names):
                        if i < len(param_values):
                            value = param_values[i]
                            # Пытаемся преобразовать значение в соответствующий тип
                            params_dict[name] = self._convert_value(value)
                        else:
                            params_dict[name] = None
                    
                    # Сохраняем в соответствующий атрибут
                    setattr(self, self._get_attribute_name(sheet), params_dict)
                    
                except Exception as e:
                    print(f"Ошибка при загрузке листа '{sheet}': {e}")
                    setattr(self, self._get_attribute_name(sheet), {})
            
        except Exception as e:
            raise Exception(f"Ошибка при загрузке Excel файла: {e}")
    
    def _get_attribute_name(self, sheet_name: str) -> str:
        """Преобразует имя листа в имя атрибута (snake_case)"""
        mapping = {
            'SGF_Parameters': 'sgf_parameters',
            'Settings': 'settings',
            'Inputs': 'inputs',
            'Outputs': 'outputs'
        }
        return mapping.get(sheet_name, sheet_name.lower())
    
    def _convert_value(self, value: Any) -> Any:
        """
        Преобразует значение в соответствующий тип данных
        (числа, булевы значения, строки и т.д.)
        """
        if pd.isna(value):
            return None
        
        # Если это строка
        if isinstance(value, str):
            # Пробуем преобразовать в булево значение
            if value.lower() in ('true', 'yes', '1', 'on'):
                return True
            elif value.lower() in ('false', 'no', '0', 'off'):
                return False
            
            # Пробуем преобразовать в число
            try:
                if '.' in value:
                    return float(value)
                else:
                    return int(value)
            except ValueError:
                pass
        
        # Если это уже числа или другие типы
        if isinstance(value, (int, float, bool)):
            return value
        
        # Возвращаем как есть (строка или другой тип)
        return value
    
    def get_parameter(self, sheet: str, param_name: str) -> Optional[Any]:
        """
        Получает значение параметра по имени листа и имени параметра
        
        Args:
            sheet: имя листа ('SGF_Parameters', 'Settings', 'Inputs', 'Outputs')
            param_name: имя параметра
        
        Returns:
            значение параметра или None, если не найден
        """
        attr_name = self._get_attribute_name(sheet)
        params_dict = getattr(self, attr_name, {})
        return params_dict.get(param_name)
    
    def set_parameter(self, sheet: str, param_name: str, value: Any) -> None:
        """
        Устанавливает значение параметра
        
        Args:
            sheet: имя листа ('SGF_Parameters', 'Settings', 'Inputs', 'Outputs')
            param_name: имя параметра
            value: новое значение
        """
        attr_name = self._get_attribute_name(sheet)
        params_dict = getattr(self, attr_name, {})
        params_dict[param_name] = value
        setattr(self, attr_name, params_dict)
    
    def get_all_parameters(self, sheet: str) -> Dict[str, Any]:
        """Возвращает все параметры указанного листа"""
        attr_name = self._get_attribute_name(sheet)
        return getattr(self, attr_name, {}).copy()
    
    def get_outputs_labels(self) -> List[str]:
        """
        Возвращает список названий для выходов из листа Outputs
        
        Returns:
            список из 16 названий (недостающие заполняются "Не назначено")
        """
        labels = ["Не назначено"] * 16
        
        if self.outputs:
            # Предполагаем, что в Outputs есть колонки Output1...Output16
            for i in range(1, 17):
                label_key = f"Output{i}"
                if label_key in self.outputs:
                    labels[i-1] = str(self.outputs[label_key])
                # Альтернативный вариант: колонка Label
                elif f"Label{i}" in self.outputs:
                    labels[i-1] = str(self.outputs[f"Label{i}"])
        
        return labels
    
    def get_inputs_labels(self) -> List[str]:
        """
        Возвращает список названий для входов из листа Inputs
        
        Returns:
            список из 16 названий (недостающие заполняются "Не назначено")
        """
        labels = ["Не назначено"] * 16
        
        if self.inputs:
            # Предполагаем, что в Inputs есть колонки Input1...Input16
            for i in range(1, 17):
                label_key = f"Input{i}"
                if label_key in self.inputs:
                    labels[i-1] = str(self.inputs[label_key])
                # Альтернативный вариант: колонка Label
                elif f"Label{i}" in self.inputs:
                    labels[i-1] = str(self.inputs[f"Label{i}"])
        
        return labels
    
    def get_expected_outputs_mask(self) -> int:
        """
        Возвращает маску ожидаемых выходов из листа Outputs
        
        Returns:
            16-битная маска состояния выходов
        """
        mask = 0
        
        if self.outputs:
            for i in range(1, 17):
                # Ищем колонки Expected1...Expected16 или State1...State16
                state_key = f"Expected{i}"
                if state_key in self.outputs:
                    if self.outputs[state_key] in (True, 1, "1", "ON", "on", "True", "true"):
                        mask |= (1 << (i-1))
                elif f"State{i}" in self.outputs:
                    if self.outputs[f"State{i}"] in (True, 1, "1", "ON", "on", "True", "true"):
                        mask |= (1 << (i-1))
        
        return mask
    
    def get_name(self) -> str:
        """Возвращает имя режима"""
        return self.mode_name
    
    def set_name(self, name: str) -> None:
        """Устанавливает имя режима"""
        self.mode_name = name
    
    def save_to_excel(self, output_path: Optional[str] = None) -> None:
        """
        Сохраняет текущее состояние режима в Excel файл
        
        Args:
            output_path: путь для сохранения (если не указан, используется исходный)
        """
        save_path = output_path or self.file_path
        
        with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
            sheets_data = {
                'SGF_Parameters': self.sgf_parameters,
                'Settings': self.settings,
                'Inputs': self.inputs,
                'Outputs': self.outputs
            }
            
            for sheet_name, params_dict in sheets_data.items():
                if params_dict:
                    # Создаем DataFrame с двумя строками
                    df = pd.DataFrame([list(params_dict.keys()), list(params_dict.values())])
                    df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)
                else:
                    # Пустой лист
                    pd.DataFrame().to_excel(writer, sheet_name=sheet_name, index=False)
    
    def validate(self) -> List[str]:
        """
        Проверяет корректность загруженных данных
        
        Returns:
            список ошибок (пустой, если все корректно)
        """
        errors = []
        
        # Проверяем, что все необходимые листы загружены
        required_sheets = ['sgf_parameters', 'settings', 'inputs', 'outputs']
        for sheet in required_sheets:
            if not getattr(self, sheet, None):
                errors.append(f"Лист {sheet} пуст или не загружен")
        
        # Проверяем, что в листах есть параметры
        if self.sgf_parameters and len(self.sgf_parameters) == 0:
            errors.append("SGF_Parameters не содержит параметров")
        
        if self.settings and len(self.settings) == 0:
            errors.append("Settings не содержит параметров")
        
        if self.inputs and len(self.inputs) == 0:
            errors.append("Inputs не содержит параметров")
        
        if self.outputs and len(self.outputs) == 0:
            errors.append("Outputs не содержит параметров")
        
        return errors
    
    def __repr__(self) -> str:
        return f"Mode(name='{self.mode_name}', file='{self.file_path}', sgf_params={len(self.sgf_parameters)}, settings={len(self.settings)}, inputs={len(self.inputs)}, outputs={len(self.outputs)})"
    
    def display_summary(self) -> None:
        """Выводит краткую информацию о загруженном режиме"""
        print(f"Режим: {self.mode_name}")
        print(f"Файл: {self.file_path}")
        print(f"SGF_Parameters: {len(self.sgf_parameters)} параметров")
        print(f"Settings: {len(self.settings)} параметров")
        print(f"Inputs: {len(self.inputs)} параметров")
        print(f"Outputs: {len(self.outputs)} параметров")
        
        if self.sgf_parameters:
            print("\nПример SGF параметров:")
            for i, (key, value) in enumerate(list(self.sgf_parameters.items())[:5]):
                print(f"  {key}: {value}")


# Пример использования
if __name__ == "__main__":
    # Создание и загрузка режима (имя автоматически будет "1")
    mode = Mode("1.xlsx")
    
    # Вывод информации
    mode.display_summary()
    
    # Получение имени режима
    print(f"\nИмя режима: {mode.get_name()}")
    
    # Получение названий выходов
    output_labels = mode.get_outputs_labels()
    print(f"\nНазвания выходов: {output_labels[:5]}...")
    
    # Получение маски ожидаемых выходов
    expected_mask = mode.get_expected_outputs_mask()
    print(f"Маска ожидаемых выходов: 0x{expected_mask:04X}")
    
    # Получение конкретного параметра
    param_value = mode.get_parameter("Settings", "some_parameter")
    print(f"\nЗначение параметра: {param_value}")
    
    # Установка нового значения
    mode.set_parameter("Inputs", "new_input", 100)
    
    # Проверка корректности
    errors = mode.validate()
    if errors:
        print("Найдены ошибки:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\nРежим загружен корректно")
    
    # Сохранение изменений в новый файл
    # mode.save_to_excel("modified_mode.xlsx")
from dataclasses import dataclass

@dataclass
class ExpData:
    """
        Модель файла, в котором хранятся испытания.
    """

    exp_id: str = ""
    product_name: str = ""
    executor_name: str = ""
    exp_date: str = ""
    description: str = ""
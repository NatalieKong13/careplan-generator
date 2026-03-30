from abc import ABC, abstractmethod
from .schemas import InternalOrder


class BaseIntakeAdapter(ABC):
    """
    所有外部数据源 Adapter 的抽象基类。
    每个 Adapter 负责把一种外部格式转换成 InternalOrder。

    使用方式：
        adapter = ClinicJsonAdapter(raw_data)
        order = adapter.run()  # 依次调用 parse → validate → transform
    """

    def __init__(self, raw_data):
        self.raw_data = raw_data      # 原始数据（JSON dict / XML bytes / Form dict）
        self._parsed = None           # parse() 的中间结果

    @abstractmethod
    def parse(self):
        """
        解析原始数据，提取出需要的字段。
        结果存到 self._parsed，供 transform() 使用。
        """
        ...

    @abstractmethod
    def transform(self) -> InternalOrder:
        """
        把 self._parsed 转换成 InternalOrder。
        必须返回一个 InternalOrder 实例。
        """
        ...

    @abstractmethod
    def validate(self) -> None:
        """
        验证 self._parsed 的数据是否合法。
        发现问题时抛出异常，不返回任何值。

        例如：
        - 必填字段是否存在
        - NPI 格式是否正确
        - 日期是否能被解析
        """
        ...

    def run(self) -> InternalOrder:
        """
        标准执行流程，子类不需要重写这个方法。
        parse → validate → transform
        """
        self.parse()
        self.validate()
        return self.transform()

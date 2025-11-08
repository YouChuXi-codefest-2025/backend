# backend/models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, Text, Double
from geoalchemy2 import Geometry

class Base(DeclarativeBase):
    pass

class TaipeiDistrict(Base):
    __tablename__ = "taipei_districts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_name: Mapped[str] = mapped_column(Text, default="臺北市")
    district_name: Mapped[str] = mapped_column(Text, nullable=False)
    geom: Mapped[str] = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=4326))

class CoolingSite(Base):
    __tablename__ = "cooling_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_type: Mapped[str] = mapped_column(Text)                 # 設施地點（戶外或室內）
    name: Mapped[str] = mapped_column(Text)                          # 名稱
    district_name: Mapped[str] = mapped_column(Text)                 # 行政區
    address: Mapped[str] = mapped_column(Text)                       # 地址
    lon: Mapped[float] = mapped_column(Double)                       # 經度
    lat: Mapped[float] = mapped_column(Double)                       # 緯度
    phone: Mapped[str] = mapped_column(Text)                         # 市話
    ext: Mapped[str] = mapped_column(Text)                           # 分機
    mobile: Mapped[str] = mapped_column(Text)                        # 手機
    other_contact: Mapped[str] = mapped_column(Text)                 # 其他聯絡方式
    open_hours: Mapped[str] = mapped_column(Text)                    # 開放時間
    fan: Mapped[bool] = mapped_column()                              # 電風扇
    ac: Mapped[bool] = mapped_column()                               # 冷氣
    toilet: Mapped[bool] = mapped_column()                           # 廁所
    seating: Mapped[bool] = mapped_column()                          # 座位
    drinking: Mapped[bool] = mapped_column()                         # 飲水設施
    accessible_seat: Mapped[bool] = mapped_column()                  # 無障礙座位
    features: Mapped[str] = mapped_column(Text)                      # 其他特色及亮點
    notes: Mapped[str] = mapped_column(Text)                         # 備註
    geom: Mapped[str] = mapped_column(Geometry(geometry_type="POINT", srid=4326))  # 由 lon/lat 建

# Standard library imports
import ctypes
import datetime
import gc
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
import logging
import logging.handlers
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import Process, Queue, cpu_count, freeze_support


from pathlib import Path
import platform

# Third-party imports
import numpy as np
import piexif
import psutil
import rawpy
from PIL import Image, ImageQt



# PySide6 - Qt framework imports
from PySide6.QtCore import (Qt, QEvent, QMetaObject, QObject, QPoint, 
                           QThread, QTimer, QUrl, Signal, Q_ARG)
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QGuiApplication, 
                          QImage, QKeyEvent, QMouseEvent, QPainter, QPalette, 
                          QPen, QPixmap, QWheelEvent, QFontMetrics)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox,
                              QDialog, QFileDialog, QFrame, QGridLayout, 
                              QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                              QMainWindow, QMessageBox, QPushButton, QRadioButton,
                              QScrollArea, QSizePolicy, QSplitter, QTextBrowser,
                              QVBoxLayout, QWidget, QToolTip)
# QRLinkLabel 클래스 정의 (툴팁을 위한 예시)
class QRLinkLabel(QLabel):
    def __init__(self, text, qr_path=None, size=100, parent=None):
        super().__init__(text, parent)
        # Store QR path and size for tooltip
        self._qr_path = qr_path
        self._qr_size = size

    def enterEvent(self, event):
        """Mac용: 마우스 오버 시 이미지 툴팁 표시"""
        if platform.system() == "Darwin" and self._qr_path:
            # HTML 툴팁으로 이미지 표시
            html = f'<img src="{self._qr_path}" width="{self._qr_size}">'
            QToolTip.showText(event.globalPos(), html)
        else:
            super().enterEvent(event)

    def leaveEvent(self, event):
        """툴팁 사라지도록 처리"""
        if platform.system() == "Darwin":
            QToolTip.hideText()
        else:
            super().leaveEvent(event)



# 로깅 시스템 설정
def setup_logger():
    # 로그 디렉터리 생성 (실행 파일과 동일한 위치에 logs 폴더 생성)
    if getattr(sys, 'frozen', False):
        # PyInstaller로 패키징된 경우
        app_dir = Path(sys.executable).parent
    else:
        # 일반 스크립트로 실행된 경우
        app_dir = Path(__file__).parent
        
    # 실행 파일과 같은 위치에 logs 폴더 생성
    log_dir = app_dir / "logs"
    os.makedirs(log_dir, exist_ok=True)

    # 현재 날짜로 로그 파일명 생성
    log_filename = datetime.now().strftime("photosort_%Y%m%d.log")
    log_path = log_dir / log_filename
    
    # 로그 형식 설정
    log_format = "%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # 루트 로거 설정
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # 개발 환경에서는 DEBUG, 배포 환경에서는 INFO 또는 WARNING
    
    # 파일 핸들러 설정 (로테이션 적용)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    logger.addHandler(file_handler)
    
    # 콘솔 핸들러 설정 (디버깅용)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)  # 콘솔에는 중요한 메시지만 표시
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    logger.addHandler(console_handler)
    
    # 버전 및 시작 메시지 로깅
    logging.info("PhotoSort 시작 (버전: 25.04.26)")
    
    return logger

# 로거 초기화
logger = setup_logger()

# UI 공통 색상 - 디폴트
UI_COLORS_DEFAULT = {
    "accent" : "#848484",
    "accent_hover" : "#555555",  # 강조색 호버 상태(밝음)
    "accent_pressed": "#222222",# 강조색 눌림 상태(어두움)
    "text": "#D8D8D8",          # 일반 텍스트 색상
    "text_disabled": "#595959", # 비활성화된 텍스트 색상
    "bg_primary": "#333333",    # 기본 배경색
    "bg_secondary": "#444444",  # 버튼 등 배경색
    "bg_hover": "#555555",      # 호버 시 배경색
    "bg_pressed": "#222222",    # 눌림 시 배경색
    "bg_disabled": "#222222",   # 비활성화 배경색
    "border": "#555555",        # 테두리 색상
}
# UI 공통 색상 - 소니
UI_COLORS_SONY = {
    "accent": "#E2570D",        # 강조색
    "accent_hover": "#E2570D",  # 강조색 호버 상태(밝음)
    "accent_pressed": "#C83E00",# 강조색 눌림 상태(어두움)
    "text": "#D8D8D8",          # 일반 텍스트 색상
    "text_disabled": "#595959", # 비활성화된 텍스트 색상
    "bg_primary": "#333333",    # 기본 배경색
    "bg_secondary": "#444444",  # 버튼 등 배경색
    "bg_hover": "#555555",      # 호버 시 배경색
    "bg_pressed": "#222222",    # 눌림 시 배경색
    "bg_disabled": "#222222",   # 비활성화 배경색
    "border": "#555555",        # 테두리 색상
}
# UI 공통 색상 - 니콘
UI_COLORS_NIKON = {
    "accent": "#E0CB00",        # 강조색
    "accent_hover": "#E0CB00",  # 강조색 호버 상태(밝음)
    "accent_pressed": "#C6B200",# 강조색 눌림 상태(어두움)
    "text": "#D8D8D8",          # 일반 텍스트 색상
    "text_disabled": "#595959", # 비활성화된 텍스트 색상
    "bg_primary": "#333333",    # 기본 배경색
    "bg_secondary": "#444444",  # 버튼 등 배경색
    "bg_hover": "#555555",      # 호버 시 배경색
    "bg_pressed": "#222222",    # 눌림 시 배경색
    "bg_disabled": "#222222",   # 비활성화 배경색
    "border": "#555555",        # 테두리 색상
}
# UI 공통 색상 - 캐논
UI_COLORS_CANON = {
    "accent": "#D71215",        # 강조색
    "accent_hover": "#D71215",  # 강조색 호버 상태(밝음)
    "accent_pressed": "#BE0000",# 강조색 눌림 상태(어두움)
    "text": "#D8D8D8",          # 일반 텍스트 색상
    "text_disabled": "#595959", # 비활성화된 텍스트 색상
    "bg_primary": "#333333",    # 기본 배경색
    "bg_secondary": "#444444",  # 버튼 등 배경색
    "bg_hover": "#555555",      # 호버 시 배경색
    "bg_pressed": "#222222",    # 눌림 시 배경색
    "bg_disabled": "#222222",   # 비활성화 배경색
    "border": "#555555",        # 테두리 색상
}
# UI 공통 색상 - 후지
UI_COLORS_FUJIFILM = {
    "accent": "#2AA58F",        # 강조색
    "accent_hover": "#2AA58F",  # 강조색 호버 상태(밝음)
    "accent_pressed": "#108C76",# 강조색 눌림 상태(어두움)
    "text": "#D8D8D8",          # 일반 텍스트 색상
    "text_disabled": "#595959", # 비활성화된 텍스트 색상
    "bg_primary": "#333333",    # 기본 배경색
    "bg_secondary": "#444444",  # 버튼 등 배경색
    "bg_hover": "#555555",      # 호버 시 배경색
    "bg_pressed": "#222222",    # 눌림 시 배경색
    "bg_disabled": "#222222",   # 비활성화 배경색
    "border": "#555555",        # 테두리 색상
}
# UI 공통 색상 - 파나소닉
UI_COLORS_PANASONIC = {
    "accent": "#0041C0",        # 강조색
    "accent_hover": "#0041C0",  # 강조색 호버 상태(밝음)
    "accent_pressed": "#0027A6",# 강조색 눌림 상태(어두움)
    "text": "#D8D8D8",          # 일반 텍스트 색상
    "text_disabled": "#595959", # 비활성화된 텍스트 색상
    "bg_primary": "#333333",    # 기본 배경색
    "bg_secondary": "#444444",  # 버튼 등 배경색
    "bg_hover": "#555555",      # 호버 시 배경색
    "bg_pressed": "#222222",    # 눌림 시 배경색
    "bg_disabled": "#222222",   # 비활성화 배경색
    "border": "#555555",        # 테두리 색상
}
# UI 공통 색상 - 라이카
UI_COLORS_LEICA = {
    "accent": "#DD171A",        # 강조색
    "accent_hover": "#DD171A",  # 강조색 호버 상태(밝음)
    "accent_pressed": "#C40000",# 강조색 눌림 상태(어두움)
    "text": "#D8D8D8",          # 일반 텍스트 색상
    "text_disabled": "#595959", # 비활성화된 텍스트 색상
    "bg_primary": "#333333",    # 기본 배경색
    "bg_secondary": "#444444",  # 버튼 등 배경색
    "bg_hover": "#555555",      # 호버 시 배경색
    "bg_pressed": "#222222",    # 눌림 시 배경색
    "bg_disabled": "#222222",   # 비활성화 배경색
    "border": "#555555",        # 테두리 색상
}



class ExifWorker(QObject):
    """백그라운드 스레드에서 EXIF 데이터를 처리하는 워커 클래스"""
    # 시그널 정의
    finished = Signal(dict, str)  # (EXIF 결과 딕셔너리, 이미지 경로)
    error = Signal(str, str)      # (오류 메시지, 이미지 경로)
    request_process = Signal(str)
    
    def __init__(self, raw_extensions, exiftool_path, exiftool_available):
        super().__init__()
        self.raw_extensions = raw_extensions
        self.exiftool_path = exiftool_path
        self.exiftool_available = exiftool_available
        self._running = True  # 작업 중단 플래그

        # 자신의 시그널을 슬롯에 연결
        self.request_process.connect(self.process_image)
    
    def stop(self):
        """워커의 실행을 중지"""
        self._running = False
    
    def get_exif_with_exiftool(self, image_path):
        """ExifTool을 사용하여 이미지 메타데이터 추출"""
        if not self.exiftool_available or not self._running:
            return {}
            
        try:
            # 중요: -g1 옵션 제거하고 일반 태그로 변경
            cmd = [self.exiftool_path, "-json", "-a", "-u", str(image_path)]
            # Windows에서 콘솔창 숨기기 위한 플래그 추가
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", 
                                    errors="replace", check=False, creationflags=creationflags)
            
            if process.returncode == 0 and process.stdout:
                try:
                    exif_data = json.loads(process.stdout)
                    # ExifTool은 결과를 항상 리스트로 반환
                    if exif_data and isinstance(exif_data, list):
                        return exif_data[0]
                    return {}
                except json.JSONDecodeError:
                    return {}
            else:
                return {}
        except Exception:
            return {}

    def process_image(self, image_path):
        """백그라운드에서 이미지의 EXIF 데이터 처리"""
        try:
            if not self._running:
                return
                
            file_path_obj = Path(image_path)
            is_raw = file_path_obj.suffix.lower() in self.raw_extensions
            
            # 결과를 저장할 딕셔너리 초기화
            result = {
                "exif_resolution": None,
                "exif_make": "",
                "exif_model": "",
                "exif_datetime": None,
                "exif_focal_mm": None,
                "exif_focal_35mm": None,
                "exif_orientation": None,
                "image_path": image_path
            }
            
            # PHASE 0: RAW 파일인 경우 rawpy로 정보 추출
            if is_raw and self._running:
                try:
                    with rawpy.imread(image_path) as raw:
                        result["exif_resolution"] = (raw.sizes.raw_width, raw.sizes.raw_height)
                        if hasattr(raw, 'camera_manufacturer'):
                            result["exif_make"] = raw.camera_manufacturer.strip() if raw.camera_manufacturer else ""
                        if hasattr(raw, 'model'):
                            result["exif_model"] = raw.model.strip() if raw.model else ""
                        if hasattr(raw, 'timestamp') and raw.timestamp:
                            dt_obj = datetime.datetime.fromtimestamp(raw.timestamp)
                            result["exif_datetime"] = dt_obj.strftime('%Y:%m:%d %H:%M:%S')
                except Exception:
                    pass

            # PHASE 1: Piexif로 EXIF 정보 추출 시도
            piexif_success = False
            if self._running:
                try:
                    # JPG 이미지 크기 (RAW는 위에서 추출)
                    if not is_raw and not result["exif_resolution"]:
                        try:
                            with Image.open(image_path) as img:
                                result["exif_resolution"] = img.size
                        except Exception:
                            pass
                    
                    exif_dict = piexif.load(image_path)
                    ifd0 = exif_dict.get("0th", {})
                    exif_ifd = exif_dict.get("Exif", {})

                    # Orientation
                    if piexif.ImageIFD.Orientation in ifd0:
                        try:
                            result["exif_orientation"] = int(ifd0.get(piexif.ImageIFD.Orientation))
                        except (ValueError, TypeError):
                            pass

                    # 카메라 정보
                    if not result["exif_make"] and piexif.ImageIFD.Make in ifd0:
                        result["exif_make"] = ifd0.get(piexif.ImageIFD.Make, b'').decode('utf-8', errors='ignore').strip()
                    if not result["exif_model"] and piexif.ImageIFD.Model in ifd0:
                        result["exif_model"] = ifd0.get(piexif.ImageIFD.Model, b'').decode('utf-8', errors='ignore').strip()

                    # 날짜 정보
                    if not result["exif_datetime"]:
                        if piexif.ExifIFD.DateTimeOriginal in exif_ifd:
                            result["exif_datetime"] = exif_ifd.get(piexif.ExifIFD.DateTimeOriginal, b'').decode('utf-8', errors='ignore')
                        elif piexif.ImageIFD.DateTime in ifd0:
                            result["exif_datetime"] = ifd0.get(piexif.ImageIFD.DateTime, b'').decode('utf-8', errors='ignore')

                    # 초점 거리
                    if result["exif_focal_mm"] is None and piexif.ExifIFD.FocalLength in exif_ifd:
                        val = exif_ifd.get(piexif.ExifIFD.FocalLength)
                        if isinstance(val, tuple) and len(val) == 2 and val[1] != 0:
                            result["exif_focal_mm"] = val[0] / val[1]
                    if result["exif_focal_35mm"] is None and piexif.ExifIFD.FocalLengthIn35mmFilm in exif_ifd:
                        result["exif_focal_35mm"] = exif_ifd.get(piexif.ExifIFD.FocalLengthIn35mmFilm)

                    # 필수 정보 확인
                    required_info_count = sum([
                        result["exif_resolution"] is not None,
                        bool(result["exif_make"] or result["exif_model"]),
                        result["exif_datetime"] is not None
                    ])
                    piexif_success = required_info_count >= 2
                except Exception:
                    piexif_success = False

            # PHASE 2: ExifTool 필요 여부 확인 및 실행
            if not self._running:
                return
                
            needs_exiftool = False
            if self.exiftool_available:
                if is_raw and result["exif_orientation"] is None:
                    needs_exiftool = True
                elif not result["exif_resolution"]:
                    needs_exiftool = True
                elif not piexif_success:
                    needs_exiftool = True

            if needs_exiftool and self._running:
                exif_data_tool = self.get_exif_with_exiftool(image_path)
                if exif_data_tool:
                    # 해상도 정보
                    if not result["exif_resolution"]:
                        width = exif_data_tool.get("ImageWidth") or exif_data_tool.get("ExifImageWidth")
                        height = exif_data_tool.get("ImageHeight") or exif_data_tool.get("ExifImageHeight")
                        if width and height:
                            try:
                                result["exif_resolution"] = (int(width), int(height))
                            except (ValueError, TypeError):
                                pass
                    
                    # Orientation
                    if result["exif_orientation"] is None:
                        orientation_val = exif_data_tool.get("Orientation")
                        if orientation_val:
                            try:
                                result["exif_orientation"] = int(orientation_val)
                            except (ValueError, TypeError):
                                pass
                    
                    # 카메라 정보
                    if not (result["exif_make"] or result["exif_model"]):
                        result["exif_make"] = exif_data_tool.get("Make", "")
                        result["exif_model"] = exif_data_tool.get("Model", "")
                    
                    # 날짜 정보
                    if not result["exif_datetime"]:
                        date_str = (exif_data_tool.get("DateTimeOriginal") or
                                exif_data_tool.get("CreateDate") or
                                exif_data_tool.get("FileModifyDate"))
                        if date_str:
                            result["exif_datetime"] = date_str
                    
                    # 초점 거리
                    if result["exif_focal_mm"] is None:
                        focal_val = exif_data_tool.get("FocalLength")
                        if focal_val:
                            try:
                                result["exif_focal_mm"] = float(str(focal_val).lower().replace(" mm", ""))
                            except (ValueError, TypeError):
                                result["exif_focal_mm"] = str(focal_val)
                    
                    if result["exif_focal_35mm"] is None:
                        focal_35_val = exif_data_tool.get("FocalLengthIn35mmFormat")
                        if focal_35_val:
                            try:
                                result["exif_focal_35mm"] = float(str(focal_35_val).lower().replace(" mm", ""))
                            except (ValueError, TypeError):
                                result["exif_focal_35mm"] = str(focal_35_val)

            # 작업 완료, 결과 전송
            if self._running:
                self.finished.emit(result, image_path)
            
        except Exception as e:
            # 오류 발생, 오류 메시지 전송
            if self._running:
                self.error.emit(str(e), image_path)


class UIScaleManager:
    """해상도에 따른 UI 크기를 관리하는 클래스"""

    # 기본 UI 크기 설정
    NORMAL_SETTINGS = {
        "control_panel_margins": (10, 0, 10, 0), # 컨트롤 패널 내부 여백 (좌, 상, 우, 하 순서 확인 필요)
        "control_layout_spacing": 8,          # 컨트롤 레이아웃 위젯 간 기본 간격
        "button_min_height": 30,               # 일반 버튼 최소 높이
        "button_padding": 8,                   # 일반 버튼 내부 패딩
        "delete_button_width": 45,             # 삭제(X) 버튼 너비
        "JPG_RAW_spacing": 15,
        "section_spacing": 20,                 # 구분선(HorizontalLine) 주변 간격
        "group_box_spacing": 15,               # 라디오 버튼 등 그룹 내 간격
        "title_spacing": 10,                   # Zoom, Grid 등 섹션 제목 아래 간격
        "settings_button_size": 35,            # 설정(톱니바퀴) 버튼 크기
        "filename_label_padding": 40,          # 파일명 레이블 상하 패딩
        "info_label_padding": 5,               # 파일 정보 레이블 좌측 패딩
        "font_size": 10,                       # 기본 폰트 크기
        "filename_font_size": 12,              # 파일명 폰트 크기
        "folder_container_spacing": 6,         # 버튼 - 레이블 - X버튼 간격
        "folder_label_padding": 13,            # 폴더 경로 레이블 높이 계산용 패딩
        "category_folder_vertical_spacing": 7,
        # 설정 창 관련 키 추가
        "settings_popup_width": 785,
        "settings_popup_height": 1080,
        "settings_layout_vspace": 10,
        "viewshortcuts_seperator": 15,
        "infotext_licensebutton": 40,
        "donation_between_tworows": 30,
        "bottom_space": 30,
        # 정보 텍스트 여백 관련 키 추가
        "info_version_margin": 40,
        "info_paragraph_margin": 40,
        "info_bottom_margin": 40,
        "info_donation_spacing": 50,
        
        
    }

    # 컴팩트 모드 UI 크기 설정
    COMPACT_SETTINGS = {
        "control_panel_margins": (10, 0, 10, 0),
        "control_layout_spacing": 6,
        "button_min_height": 26,
        "button_padding": 6,
        "delete_button_width": 42,
        "JPG_RAW_spacing": 10,
        "section_spacing": 15,
        "group_box_spacing": 15,
        "title_spacing": 7,
        "settings_button_size": 30,
        "filename_label_padding": 30,
        "info_label_padding": 5,
        "font_size": 9,
        "filename_font_size": 10,
        "folder_container_spacing": 5,
        "folder_label_padding": 12,
        "category_folder_vertical_spacing": 7,
        # 설정 창 관련 키 추가 (컴팩트 모드에서는 더 작게)
        "settings_popup_width": 750,
        "settings_popup_height": 835,  # 크게 줄임
        "settings_layout_vspace": 7,
        "viewshortcuts_seperator": 10,
        "infotext_licensebutton": 25,
        "donation_between_tworows": 20,
        "bottom_space": 20,
        # 정보 텍스트 여백 관련 키 추가 (컴팩트 모드에서는 여백 축소)
        "info_version_margin": 30,
        "info_paragraph_margin": 30,
        "info_bottom_margin": 30,
        "info_donation_spacing": 30,
    }

    _current_settings = NORMAL_SETTINGS # 초기값은 Normal로 설정

    @classmethod
    def initialize(cls):
        """애플리케이션 시작 시 호출되어 화면 해상도 확인 및 모드 설정"""
        try:
            screen = QGuiApplication.primaryScreen()
            if not screen:
                logging.warning("Warning: Primary screen not found. Using default UI scale.")
                cls._current_settings = cls.NORMAL_SETTINGS
                return

            screen_geometry = screen.geometry()
            vertical_resolution = screen_geometry.height()
            is_compact = vertical_resolution < 1201 

            if is_compact:
                cls._current_settings = cls.COMPACT_SETTINGS
                logging.info(f"세로 해상도: {vertical_resolution}px / Compact UI 모드 활성")
            else:
                cls._current_settings = cls.NORMAL_SETTINGS
                logging.info(f"세로 해상도: {vertical_resolution}px / Normal UI 모드 활성")

        except Exception as e:
            logging.error(f"Error initializing UIScaleManager: {e}. Using default UI scale.")
            cls._current_settings = cls.NORMAL_SETTINGS

    @classmethod
    def is_compact_mode(cls):
        """현재 컴팩트 모드 여부 반환"""
        # _current_settings가 COMPACT_SETTINGS와 같은 객체인지 비교하여 확인
        return cls._current_settings is cls.COMPACT_SETTINGS

    @classmethod
    def get(cls, key, default=None):
        """현재 모드에 맞는 UI 크기 값 반환"""
        # cls._current_settings에서 직접 값을 가져옴
        return cls._current_settings.get(key, default)

    @classmethod
    def get_margins(cls):
        """현재 모드에 맞는 마진 튜플 반환"""
        # 마진 값은 튜플이므로 직접 반환
        return cls._current_settings.get("control_panel_margins")


class ThemeManager:
    # 모든 테마 저장
    THEMES = {
        "default": UI_COLORS_DEFAULT,
        "sony": UI_COLORS_SONY,
        "nikon": UI_COLORS_NIKON,
        "canon": UI_COLORS_CANON,
        "fujifilm": UI_COLORS_FUJIFILM,
        "panasonic": UI_COLORS_PANASONIC,
        "leica": UI_COLORS_LEICA
    }
    
    _current_theme = "default"  # 현재 테마
    _theme_change_callbacks = []  # 테마 변경 시 호출할 콜백 함수 목록
    
    @classmethod
    def get_color(cls, color_key):
        """현재 테마에서 색상 코드 가져오기"""
        return cls.THEMES[cls._current_theme][color_key]
    
    @classmethod
    def set_theme(cls, theme_name):
        """테마 변경하고 모든 콜백 함수 호출"""
        if theme_name in cls.THEMES:
            cls._current_theme = theme_name
            # 모든 콜백 함수 호출
            for callback in cls._theme_change_callbacks:
                callback()
            return True
        return False
    
    @classmethod
    def register_theme_change_callback(cls, callback):
        """테마 변경 시 호출될 콜백 함수 등록"""
        if callable(callback) and callback not in cls._theme_change_callbacks:
            cls._theme_change_callbacks.append(callback)
    
    @classmethod
    def get_current_theme_name(cls):
        """현재 테마 이름 반환"""
        return cls._current_theme
    
    @classmethod
    def get_available_themes(cls):
        """사용 가능한 모든 테마 이름 목록 반환"""
        return list(cls.THEMES.keys())

class LanguageManager:
    """언어 설정 및 번역을 관리하는 클래스"""
    
    # 사용 가능한 언어
    LANGUAGES = {
        "en": "English",
        "ko": "한국어"
    }
    
    # 번역 데이터
    _translations = {
        "en": {},  # 영어 번역 데이터는 아래에서 초기화
        "ko": {}   # 한국어는 기본값이므로 필요 없음
    }
    
    _current_language = "en"  # 기본 언어
    _language_change_callbacks = []  # 언어 변경 시 호출할 콜백 함수 목록
    
    @classmethod
    def initialize_translations(cls, translations_data):
        """번역 데이터 초기화"""
        # 영어는 key-value 반대로 저장 (한국어->영어 매핑)
        for ko_text, en_text in translations_data.items():
            cls._translations["en"][ko_text] = en_text
    
    @classmethod
    def translate(cls, text_id):
        """텍스트 ID에 해당하는 번역 반환"""
        if cls._current_language == "ko":
            return text_id  # 한국어는 원래 ID 그대로 사용
        
        translations = cls._translations.get(cls._current_language, {})
        return translations.get(text_id, text_id)  # 번역 없으면 원본 반환
    
    @classmethod
    def set_language(cls, language_code):
        """언어 설정 변경"""
        if language_code in cls.LANGUAGES:
            cls._current_language = language_code
            # 언어 변경 시 콜백 함수 호출
            for callback in cls._language_change_callbacks:
                callback()
            return True
        return False
    
    @classmethod
    def register_language_change_callback(cls, callback):
        """언어 변경 시 호출될 콜백 함수 등록"""
        if callable(callback) and callback not in cls._language_change_callbacks:
            cls._language_change_callbacks.append(callback)
    
    @classmethod
    def get_current_language(cls):
        """현재 언어 코드 반환"""
        return cls._current_language
    
    @classmethod
    def get_available_languages(cls):
        """사용 가능한 언어 목록 반환"""
        return list(cls.LANGUAGES.keys())
    
    @classmethod
    def get_language_name(cls, language_code):
        """언어 코드에 해당하는 언어 이름 반환"""
        return cls.LANGUAGES.get(language_code, language_code)

class RawProcessingStrategyManager:
    """RAW 파일 처리 전략을 관리하는 클래스"""
    
    # 사용 가능한 전략
    STRATEGIES = {
        "ultra_fast": "매우 빠름",
        "fast": "빠름",
        "high_quality": "고품질",
        "ultra_quality": "최고 품질"
    }
    
    # 영문 번역
    STRATEGIES_EN = {
        "ultra_fast": "Ultra Fast",
        "fast": "Fast",
        "high_quality": "High Quality",
        "ultra_quality": "Ultra Quality"
    }
    
    _current_strategy = "fast"  # 기본값: 빠름
    _strategy_change_callbacks = []  # 전략 변경 시 호출할 콜백 함수 목록
    
    @classmethod
    def set_strategy(cls, strategy_code):
        """전략 설정 변경"""
        if strategy_code in cls.STRATEGIES:
            cls._current_strategy = strategy_code
            # 전략 변경 시 콜백 함수 호출
            for callback in cls._strategy_change_callbacks:
                callback()
            return True
        return False
    
    @classmethod
    def register_strategy_change_callback(cls, callback):
        """전략 변경 시 호출될 콜백 함수 등록"""
        if callable(callback) and callback not in cls._strategy_change_callbacks:
            cls._strategy_change_callbacks.append(callback)
    
    @classmethod
    def get_current_strategy(cls):
        """현재 전략 코드 반환"""
        return cls._current_strategy
    
    @classmethod
    def get_current_strategy_name(cls, language="ko"):
        """현재 전략 이름 반환 (언어 지원)"""
        strategy_code = cls._current_strategy
        if language == "en":
            return cls.STRATEGIES_EN.get(strategy_code, "")
        else:
            return cls.STRATEGIES.get(strategy_code, "")
    
    @classmethod
    def get_available_strategies(cls):
        """사용 가능한 전략 목록 반환"""
        return list(cls.STRATEGIES.keys())
    
    @classmethod
    def get_strategy_name(cls, strategy_code, language="ko"):
        """전략 코드에 해당하는 이름 반환 (언어 지원)"""
        if language == "en":
            return cls.STRATEGIES_EN.get(strategy_code, strategy_code)
        else:
            return cls.STRATEGIES.get(strategy_code, strategy_code)

class DateFormatManager:
    """날짜 형식 설정을 관리하는 클래스"""
    
    # 날짜 형식 정보
    DATE_FORMATS = {
        "yyyy-mm-dd": "YYYY-MM-DD",
        "mm/dd/yyyy": "MM/DD/YYYY",
        "dd/mm/yyyy": "DD/MM/YYYY"
    }
    
    # 형식별 실제 변환 패턴
    _format_patterns = {
        "yyyy-mm-dd": "%Y-%m-%d",
        "mm/dd/yyyy": "%m/%d/%Y",
        "dd/mm/yyyy": "%d/%m/%Y"
    }
    
    _current_format = "yyyy-mm-dd"  # 기본 형식
    _format_change_callbacks = []  # 형식 변경 시 호출할 콜백 함수
    
    @classmethod
    def format_date(cls, date_str):
        """날짜 문자열을 현재 설정된 형식으로 변환"""
        if not date_str:
            return "▪ -"
        
        # 기존 형식(YYYY:MM:DD HH:MM:SS)에서 datetime 객체로 변환
        try:
            # EXIF 날짜 형식 파싱 (콜론 포함)
            if ":" in date_str:
                dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
            else:
                # 콜론 없는 형식 시도 (다른 포맷의 가능성)
                dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            
            # 현재 설정된 형식으로 변환하여 반환
            pattern = cls._format_patterns.get(cls._current_format, "%Y-%m-%d")
            # 시간 정보 추가
            return f"▪ {dt.strftime(pattern)} {dt.strftime('%H:%M:%S')}"
        except (ValueError, TypeError) as e:
            # 다른 형식 시도 (날짜만 있는 경우)
            try:
                if ":" in date_str:
                    dt = datetime.strptime(date_str.split()[0], "%Y:%m:%d")
                else:
                    dt = datetime.strptime(date_str.split()[0], "%Y-%m-%d")
                pattern = cls._format_patterns.get(cls._current_format, "%Y-%m-%d")
                return f"▪ {dt.strftime(pattern)}"
            except (ValueError, TypeError):
                # 형식이 맞지 않으면 원본 반환
                return f"▪ {date_str}"
    
    @classmethod
    def set_date_format(cls, format_code):
        """날짜 형식 설정 변경"""
        if format_code in cls.DATE_FORMATS:
            cls._current_format = format_code
            # 형식 변경 시 콜백 함수 호출
            for callback in cls._format_change_callbacks:
                callback()
            return True
        return False
    
    @classmethod
    def register_format_change_callback(cls, callback):
        """날짜 형식 변경 시 호출될 콜백 함수 등록"""
        if callable(callback) and callback not in cls._format_change_callbacks:
            cls._format_change_callbacks.append(callback)
    
    @classmethod
    def get_current_format(cls):
        """현재 날짜 형식 코드 반환"""
        return cls._current_format
    
    @classmethod
    def get_available_formats(cls):
        """사용 가능한 날짜 형식 목록 반환"""
        return list(cls.DATE_FORMATS.keys())
    
    @classmethod
    def get_format_display_name(cls, format_code):
        """날짜 형식 코드에 해당하는 표시 이름 반환"""
        return cls.DATE_FORMATS.get(format_code, format_code)

class FolderPathLabel(QLabel):
    """폴더 경로를 보여주는 레이블 클래스, 더블클릭 시 탐색기 열기"""
    doubleClicked = Signal(str)
    
    def __init__(self, text="", fixed_height_padding=10, parent=None):
        super().__init__(parent=parent)
        self.full_path = ""
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("더블클릭하면 해당 폴더가 열립니다 (전체 경로 표시)")

        font = QFont("Arial", UIScaleManager.get("font_size"))
        self.setFont(font)

        # 폰트 메트릭스를 이용해 2줄 높이 계산
        fm = QFontMetrics(font)
        line_height = fm.height()
        fixed_height = (line_height * 2) + fixed_height_padding # ========== UIScaleManager 적용 - 인자 사용 ==========
        self.setFixedHeight(fixed_height)

        self.setWordWrap(True)
        self.setStyleSheet(f"""
            QLabel {{
                color: #AAAAAA;
                padding: 5px;
                background-color: {ThemeManager.get_color('bg_primary')};
                border-radius: 1px;
            }}
        """)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setText(text)

    def setText(self, text: str, max_length=38, prefix_length=17, suffix_length=17):
        """
        라벨 텍스트 설정 및 긴 경로 생략 처리
        max_length: 이 길이를 초과하면 경로를 생략함
        prefix_length: 생략 시 앞에서 표시할 글자 수
        suffix_length: 생략 시 뒤에서 표시할 글자 수
        """
        self.full_path = text  # 원본 경로 저장
        self.setToolTip(text)  # 툴팁으로 전체 경로 표시
        
        # 경로가 너무 길면 중간을 '...'로 표시
        if len(text) > max_length:
            display_text = text[:prefix_length] + " ... " + text[-suffix_length:]
        else:
            display_text = text
        super().setText(display_text)

    def text(self) -> str:
        return super().text()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.full_path and self.full_path != "폴더 경로":
            self.doubleClicked.emit(self.full_path)

class HorizontalLine(QFrame):
    """구분선을 나타내는 수평선 위젯"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        self.setStyleSheet(f"background-color: {ThemeManager.get_color('border')};")
        self.setFixedHeight(1)


def decode_raw_in_process(input_queue, output_queue):
    """별도 프로세스에서 RAW 디코딩 처리"""
    logging.info(f"RAW 디코더 프로세스 시작됨 (PID: {os.getpid()})")
    try:
        import rawpy
        import numpy as np
    except ImportError as e:
        logging.error(f"RAW 디코더 프로세스 초기화 오류 (모듈 로드 실패): {e}")
        return
    
    memory_warning_shown = False
    last_memory_log_time = 0  # 마지막 메모리 경고 로그 시간
    memory_log_cooldown = 60  # 메모리 경고 로그 출력 간격 (초)
    
    while True:
        try:
            task = input_queue.get()
            if task is None:  # 종료 신호
                logging.info(f"RAW 디코더 프로세스 종료 신호 수신 (PID: {os.getpid()})")
                break
                
            file_path, task_id = task
            
            # 작업 시작 전 메모리 확인
            try:
                memory_percent = psutil.virtual_memory().percent
                current_time = time.time()
                
                # 메모리 경고 로그는 일정 간격으로만 출력
                if memory_percent > 85 and not memory_warning_shown and current_time - last_memory_log_time > memory_log_cooldown:
                    logging.warning(f"경고: 높은 메모리 사용량 ({memory_percent}%) 상태에서 RAW 디코딩 작업 시작")
                    memory_warning_shown = True
                    last_memory_log_time = current_time
                elif memory_percent <= 75:
                    memory_warning_shown = False
                    
                # 메모리가 매우 부족하면 작업 연기 (95% 이상)
                if memory_percent > 95:
                    logging.warning(f"심각한 메모리 부족 ({memory_percent}%): RAW 디코딩 작업 {os.path.basename(file_path)} 연기")
                    # 작업을 큐에 다시 넣고 잠시 대기
                    input_queue.put((file_path, task_id))
                    time.sleep(5)  # 조금 더 길게 대기
                    continue
            except:
                pass  # psutil 사용 불가 시 무시
            
            try:
                with rawpy.imread(file_path) as raw:
                    # 이미지 처리 전 가비지 컬렉션 실행
                    try:
                        import gc
                        gc.collect()
                    except:
                        pass
                        
                    # 이미지 처리
                    rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
                    
                    # 결과 메타데이터 준비
                    result = {
                        'task_id': task_id,
                        'width': rgb.shape[1],
                        'height': rgb.shape[0],
                        'success': True,
                        'file_path': file_path
                    }
                    
                    # 데이터 형태 확인하고 전송 준비
                    if rgb.dtype == np.uint8 and rgb.ndim == 3:
                        # 메모리 공유를 위해 numpy 배열을 바이트로 직렬화
                        result['data'] = rgb.tobytes()
                        result['shape'] = rgb.shape
                        result['dtype'] = str(rgb.dtype)
                        
                        # 큰 데이터는 로그에 출력하지 않음
                        data_size_mb = len(result['data']) / (1024*1024)
                        logging.info(f"RAW 디코딩 완료: {os.path.basename(file_path)} - {rgb.shape}, {data_size_mb:.2f}MB")
                    else:
                        # 예상치 못한 데이터 형식인 경우
                        logging.warning(f"디코딩된 데이터 형식 문제: {rgb.dtype}, shape={rgb.shape}")
                        result['success'] = False
                        result['error'] = f"Unexpected data format: {rgb.dtype}, shape={rgb.shape}"
                    
                    # 처리 결과 전송 전 메모리에서 큰 객체 제거
                    rgb = None
                    
                    # 명시적 가비지 컬렉션
                    try:
                        import gc
                        gc.collect()
                    except:
                        pass
                    
                    output_queue.put(result)
                    
            except Exception as e:
                logging.error(f"RAW 디코딩 중 오류: {os.path.basename(file_path)} - {e}")
                import traceback
                traceback.print_exc()
                output_queue.put({
                    'task_id': task_id, 
                    'success': False, 
                    'file_path': file_path,
                    'error': str(e)
                })
                
        except Exception as main_error:
            logging.error(f"RAW 디코더 프로세스 주 루프 오류: {main_error}")
            import traceback
            traceback.print_exc()
            # 루프 계속 실행: 한 작업이 실패해도 프로세스는 계속 실행

    logging.info(f"RAW 디코더 프로세스 종료 (PID: {os.getpid()})")


class RawDecoderPool:
    """RAW 디코더 프로세스 풀"""
    def __init__(self, num_processes=None):
        if num_processes is None:
        # 코어 수에 비례하되 상한선 설정
            available_cores = cpu_count()
            num_processes = min(2, max(1, available_cores // 4))
            # 8코어: 2개, 16코어: 4개, 32코어: 8개로 제한
            
        logging.info(f"RawDecoderPool 초기화: {num_processes}개 프로세스")
        self.input_queue = Queue()
        self.output_queue = Queue()
        self.processes = []
        
        # 디코더 프로세스 시작
        for i in range(num_processes):
            p = Process(
                target=decode_raw_in_process, 
                args=(self.input_queue, self.output_queue),
                daemon=True  # 메인 프로세스가 종료하면 함께 종료
            )
            p.start()
            logging.info(f"RAW 디코더 프로세스 #{i+1} 시작됨 (PID: {p.pid})")
            self.processes.append(p)
        
        self.next_task_id = 0
        self.tasks = {}  # task_id -> callback
        self._running = True
    
    def decode_raw(self, file_path, callback):
        """RAW 디코딩 요청 (비동기)"""
        if not self._running:
            print("RawDecoderPool이 이미 종료됨")
            return None
        
        task_id = self.next_task_id
        self.next_task_id += 1
        self.tasks[task_id] = callback
        
        print(f"RAW 디코딩 요청: {os.path.basename(file_path)} (task_id: {task_id})")
        self.input_queue.put((file_path, task_id))
        return task_id
    
    def process_results(self, max_results=5):
        """완료된 결과 처리 (메인 스레드에서 주기적으로 호출)"""
        if not self._running:
            return 0
            
        processed = 0
        while processed < max_results:
            try:
                # non-blocking 확인
                if self.output_queue.empty():
                    break
                    
                result = self.output_queue.get_nowait()
                task_id = result['task_id']
                
                if task_id in self.tasks:
                    callback = self.tasks.pop(task_id)
                    # 성공 여부와 관계없이 콜백 호출
                    callback(result)
                else:
                    logging.warning(f"경고: task_id {task_id}에 대한 콜백을 찾을 수 없음")
                
                processed += 1
                
            except Exception as e:
                logging.error(f"결과 처리 중 오류: {e}")
                break
                
        return processed
    
    def shutdown(self):
        """프로세스 풀 종료"""
        if not self._running:
            print("RawDecoderPool이 이미 종료됨")
            return
            
        print("RawDecoderPool 종료 중...")
        self._running = False
        
        # 모든 프로세스에 종료 신호 전송
        for _ in range(len(self.processes)):
            self.input_queue.put(None)
        
        # 프로세스 종료 대기
        for i, p in enumerate(self.processes):
            p.join(0.5)  # 각 프로세스별로 최대 0.5초 대기
            if p.is_alive():
                logging.info(f"프로세스 #{i+1} (PID: {p.pid})이 응답하지 않아 강제 종료")
                p.terminate()
                
        self.processes.clear()
        self.tasks.clear()
        logging.info("RawDecoderPool 종료 완료")

class ResourceManager:
    """스레드 풀과 프로세스 풀을 통합 관리하는 싱글톤 클래스"""
    _instance = None
    
    @classmethod
    def instance(cls):
        """싱글톤 인스턴스 반환"""
        if cls._instance is None:
            cls._instance = ResourceManager()
        return cls._instance
    
    def __init__(self):
        """리소스 매니저 초기화"""
        if ResourceManager._instance is not None:
            raise RuntimeError("ResourceManager는 싱글톤입니다. instance() 메서드를 사용하세요.")
        
        # 시스템 사양 확인
        self.available_cores = cpu_count()
        self.system_memory_gb = self.get_system_memory_gb()
        
        # 시스템 사양에 맞게 스레드/프로세스 수 최적화
        max_imaging_threads = self.calculate_optimal_threads()
        raw_processes = self.calculate_optimal_raw_processes()
        
        # 통합 이미징 스레드 풀 (이미지 로딩/처리에 사용)
        self.imaging_thread_pool = PriorityThreadPoolExecutor(
            max_workers=max_imaging_threads,
            thread_name_prefix="Imaging"
        )
        
        # RAW 디코더 프로세스 풀
        self.raw_decoder_pool = RawDecoderPool(num_processes=raw_processes)
        
        # 작업 추적
        self.active_tasks = set()
        self.pending_tasks = {}  # 우선순위별 대기 중인 작업
        self._running = True
        
        logging.info(f"ResourceManager 초기화: 이미징 스레드 {max_imaging_threads}개, RAW 디코더 프로세스 {raw_processes}개")
        
        # 작업 모니터링 타이머
        self.monitor_timer = QTimer()
        self.monitor_timer.setInterval(5000)  # 5초마다 확인
        self.monitor_timer.timeout.connect(self.monitor_resources)
        self.monitor_timer.start()

    def get_system_memory_gb(self):
        """시스템 메모리 크기 확인 (GB)"""
        try:
            import psutil
            return psutil.virtual_memory().total / (1024 * 1024 * 1024)
        except:
            return 8.0  # 기본값 8GB
        

    def calculate_optimal_threads(self):
        """시스템 사양에 맞는 최적의 스레드 수 계산"""
        # 저사양: 2스레드, 중간사양: 3스레드, 고사양: 4스레드. 구체적인 숫자는 조율 필요.
        if self.system_memory_gb >= 24 and self.available_cores >= 8:
            return 4  # 고사양
        elif self.system_memory_gb >= 12 and self.available_cores >= 6:
            return 3  # 중간사양
        else:
            return 2  # 저사양 (8GB RAM, 4코어)
        
    def calculate_optimal_raw_processes(self):
        """시스템 사양에 맞는 최적의 RAW 프로세스 수 계산"""
        # RAW 처리는 메모리 집약적이므로 메모리 우선 고려
        if self.system_memory_gb >= 15: # 32gb, 24gb, 16gb 중 구체적인 숫자는 조율 필요.
            return min(2, max(1, self.available_cores // 4))
        else:
            return 1  # 8GB-15GB 시스템에서는 1개로 제한
        
    def monitor_resources(self):
        """시스템 리소스 사용량 모니터링 및 필요시 조치"""
        if not self._running:
            return
            
        try:
            # 현재 메모리 사용량 확인
            memory_percent = psutil.virtual_memory().percent
            
            # 메모리 사용량이 95%를 초과할 경우만 긴급 정리 (기존 90%에서 상향)
            if memory_percent > 95:
                print(f"심각한 메모리 부족 감지 ({memory_percent}%): 긴급 조치 수행")
                # 우선순위 낮은 작업 취소
                self.cancel_low_priority_tasks()
                
                # 가비지 컬렉션 명시적 호출
                gc.collect()
        except:
            pass  # psutil 사용 불가 등의 예외 상황 무시

    def cancel_low_priority_tasks(self):
        """우선순위가 낮은 작업 취소"""
        # low 우선순위 작업 전체 취소
        if 'low' in self.pending_tasks:
            for task in list(self.pending_tasks['low']):
                task.cancel()
            self.pending_tasks['low'] = []
            
        # 필요시 medium 우선순위 작업 일부 취소 (최대 절반)
        if 'medium' in self.pending_tasks and len(self.pending_tasks['medium']) > 4:
            # 절반만 유지
            keep = len(self.pending_tasks['medium']) // 2
            to_cancel = self.pending_tasks['medium'][keep:]
            self.pending_tasks['medium'] = self.pending_tasks['medium'][:keep]
            
            for task in to_cancel:
                task.cancel()

    
    def submit_imaging_task_with_priority(self, priority, fn, *args, **kwargs):
        """이미지 처리 작업을 우선순위와 함께 제출"""
        if not self._running:
            return None
            
        # 우선순위 스레드 풀에 작업 제출
        if isinstance(self.imaging_thread_pool, PriorityThreadPoolExecutor):
            self.imaging_thread_pool.submit_with_priority(priority, fn, *args, **kwargs)
        else:
            # 우선순위 지원하지 않으면 일반 제출
            self.submit_imaging_task(fn, *args, **kwargs)



    def submit_imaging_task(self, fn, *args, **kwargs):
        """이미지 처리 작업 제출 (일반)"""
        if not self._running:
            return None
            
        future = self.imaging_thread_pool.submit(fn, *args, **kwargs)
        self.active_tasks.add(future)
        future.add_done_callback(lambda f: self.active_tasks.discard(f))
        return future
    
    def submit_raw_decoding(self, file_path, callback):
        """RAW 디코딩 작업 제출"""
        if not self._running:
            return None
        return self.raw_decoder_pool.decode_raw(file_path, callback)
    
    def process_raw_results(self, max_results=5):
        """RAW 디코딩 결과 처리"""
        if not self._running:
            return 0
        return self.raw_decoder_pool.process_results(max_results)
    
    def cancel_all_tasks(self):
        """모든 활성 작업 취소"""
        print("ResourceManager: 모든 작업 취소 중...")
        
        # 1. 활성 스레드 풀 작업 취소
        for future in list(self.active_tasks):
            future.cancel()
        self.active_tasks.clear()
        
        # 2. RAW 디코더 풀 작업 취소 (input_queue 비우기 추가)
        if hasattr(self, 'raw_decoder_pool') and self.raw_decoder_pool:
            try:
                # 입력 큐 비우기 시도 (가능한 경우)
                while not self.raw_decoder_pool.input_queue.empty():
                    try:
                        self.raw_decoder_pool.input_queue.get_nowait()
                    except:
                        break
                
                # 출력 큐 비우기 시도 (가능한 경우)
                while not self.raw_decoder_pool.output_queue.empty():
                    try:
                        self.raw_decoder_pool.output_queue.get_nowait()
                    except:
                        break
                        
                # 작업 추적 정보 비우기
                self.raw_decoder_pool.tasks.clear()
                print("RAW 디코더 작업 큐 및 작업 추적 정보 초기화됨")
            except Exception as e:
                logging.error(f"RAW 디코더 풀 작업 취소 중 오류: {e}")
        
        print("ResourceManager: 모든 작업 취소 완료")
    
    def shutdown(self):
        """모든 리소스 종료"""
        if not self._running:
            return
            
        print("ResourceManager: 리소스 종료 중...")
        self._running = False
        
        # 활성 작업 취소
        self.cancel_all_tasks()
        
        # 스레드 풀 종료
        self.imaging_thread_pool.shutdown(wait=False, cancel_futures=True)
        
        # RAW 디코더 풀 종료
        self.raw_decoder_pool.shutdown()
        
        print("ResourceManager: 리소스 종료 완료")

class PriorityThreadPoolExecutor(ThreadPoolExecutor):
    """우선순위를 지원하는 스레드 풀"""
    
    def __init__(self, max_workers=None, thread_name_prefix=''):
        super().__init__(max_workers=max_workers, thread_name_prefix=thread_name_prefix)
        
        # 우선순위별 작업 큐
        self.task_queues = {
            'high': queue.Queue(),    # 현재 보는 이미지
            'medium': queue.Queue(),  # 다음/인접 이미지
            'low': queue.Queue()      # 나머지 이미지
        }
        
        self.shutdown_flag = False
        self.queue_processor_thread = threading.Thread(
            target=self._process_priority_queues,
            daemon=True,
            name=f"{thread_name_prefix}-QueueProcessor"
        )
        self.queue_processor_thread.start()
    
    def _process_priority_queues(self):
        """우선순위 큐를 처리하는 스레드 함수"""
        while not self.shutdown_flag:
            # 높은 우선순위부터 처리
            processed = False
            
            # 높은 우선순위 작업 처리
            try:
                task = self.task_queues['high'].get_nowait()
                super().submit(task[0], *task[1], **task[2])
                processed = True
            except queue.Empty:
                # 높은 우선순위 큐가 비어있으면 다음으로
                pass
            
            # 중간 우선순위 작업 처리
            if not processed:
                try:
                    task = self.task_queues['medium'].get_nowait()
                    super().submit(task[0], *task[1], **task[2])
                    processed = True
                except queue.Empty:
                    # 중간 우선순위 큐가 비어있으면 다음으로
                    pass
            
            # 낮은 우선순위 작업 처리
            if not processed:
                try:
                    task = self.task_queues['low'].get_nowait()
                    super().submit(task[0], *task[1], **task[2])
                    processed = True
                except queue.Empty:
                    # 모든 큐가 비어있으면 잠시 대기
                    time.sleep(0.05)
    
    def submit_with_priority(self, priority, fn, *args, **kwargs):
        """우선순위와 함께 작업 제출"""
        if priority not in self.task_queues:
            priority = 'low'  # 기본값
        
        # 큐에 작업 추가
        self.task_queues[priority].put((fn, args, kwargs))
    
    def shutdown(self, wait=True, cancel_futures=False):
        """스레드 풀 종료"""
        self.shutdown_flag = True
        super().shutdown(wait=wait, cancel_futures=cancel_futures)

class ImageLoader(QObject):
    """이미지 로딩 및 캐싱을 관리하는 클래스"""
    imageLoaded = Signal(int, QPixmap, str)  # 인덱스, 픽스맵, 이미지 경로
    loadCompleted = Signal(QPixmap, str, int)  # pixmap, image_path, requested_index
    loadFailed = Signal(str, str, int)  # error_message, image_path, requested_index

     # 클래스 변수로 전역 전략 설정 (스레드 간 공유)
    _global_raw_strategy = "undetermined"
    _strategy_initialized = False  # 전략 초기화 여부 플래그 추가
    
    def __init__(self, parent=None, raw_extensions=None):
        super().__init__(parent)
        self.raw_extensions = raw_extensions or set()
        
        # 시스템 메모리 기반 캐시 크기 조정
        self.system_memory_gb = self.get_system_memory_gb()
        self.cache_limit = self.calculate_adaptive_cache_size()
        self.cache = self.create_lru_cache(self.cache_limit)

        # 디코딩 이력 추적 (중복 디코딩 방지용)
        self.recently_decoded = {}  # 파일명 -> 마지막 디코딩 시간
        self.decoding_cooldown = 30  # 초 단위 (이 시간 내 중복 디코딩 방지)

        # 주기적 캐시 건전성 확인 타이머 추가
        self.cache_health_timer = QTimer()
        self.cache_health_timer.setInterval(30000)  # 30초마다 캐시 건전성 확인
        self.cache_health_timer.timeout.connect(self.check_cache_health)
        self.cache_health_timer.start()
        
        # 마지막 캐시 동적 조정 시간 저장
        self.last_cache_adjustment = time.time()

        self.resource_manager = ResourceManager.instance()
        self.active_futures = []  # 현재 활성화된 로딩 작업 추적
        self.last_requested_page = -1  # 마지막으로 요청된 페이지
        self._raw_load_strategy = "undetermined" # "undetermined", "preview", "decode" - 첫 RAW 파일 처리 방식 결정
        self.load_executor = self.resource_manager.imaging_thread_pool

        # 디코더 결과 처리 타이머 설정
        self.decoder_timer = QTimer()
        self.decoder_timer.setInterval(100)  # 100ms 마다 결과 확인
        self.decoder_timer.timeout.connect(self.check_decoder_results)
        self.decoder_timer.start()
        
        # RAW 디코딩 보류 중인 파일 추적 
        self.pending_raw_decoding = set()

        # 전략 결정을 위한 락 추가
        self._strategy_lock = threading.Lock()

        # 스레드 안전성을 위한 lock
        if not hasattr(ImageLoader, '_strategy_lock'):
            ImageLoader._strategy_lock = threading.RLock()  # 재진입 가능한 lock 사용

    def get_system_memory_gb(self):
        """시스템 메모리 크기 확인 (GB)"""
        try:
            import psutil
            return psutil.virtual_memory().total / (1024 * 1024 * 1024)
        except:
            return 8.0  # 기본값 8GB
        

    def calculate_adaptive_cache_size(self):
        """시스템 메모리 기반으로 캐시 크기 계산"""
        # 메모리 사용량에 따라 캐시 크기를 동적으로 조정하는 상세 로직
        # 8GB 시스템: 기본 25개 이미지 (기존 30개에서 줄임)
        # 16GB 시스템: 약 50개 이미지
        # 32GB 시스템: 약 100개 이미지
        base_cache_size = 25
        
        if self.system_memory_gb >= 31:
            return base_cache_size * 4
        elif self.system_memory_gb >= 23:
            return base_cache_size * 3
        elif self.system_memory_gb >= 15:
            return base_cache_size * 2
        else:
            return base_cache_size
    
    def create_lru_cache(self, max_size):
        """LRU 캐시 생성 (OrderedDict 기반)"""
        from collections import OrderedDict
        return OrderedDict()
    
    def check_cache_health(self):
        """캐시 상태 확인 및 필요시 축소"""
        try:
            # 현재 메모리 사용량 확인
            memory_percent = psutil.virtual_memory().percent
            
            # 메모리 사용량에 따른 단계적 캐시 정리 (임계치 상향 조정)
            current_time = time.time()
            
            # 위험 단계 (95% 이상): 대규모 정리
            if memory_percent > 95 and current_time - self.last_cache_adjustment > 5:
                # 캐시 크기 50% 축소 - 심각한 메모리 부족 상황
                reduction = max(1, int(len(self.cache) * 0.5))
                self._remove_oldest_items_from_cache(reduction)
                logging.warning(f"심각한 메모리 부족 감지 ({memory_percent}%): 캐시 50% 정리 ({reduction}개 항목)")
                self.last_cache_adjustment = current_time
                gc.collect()
                
            # 경고 단계 (90% 이상): 중간 정리
            elif memory_percent > 90 and current_time - self.last_cache_adjustment > 10:
                # 캐시 크기 30% 축소 - 경고 수준
                reduction = max(1, int(len(self.cache) * 0.3))
                self._remove_oldest_items_from_cache(reduction)
                logging.warning(f"높은 메모리 사용량 감지 ({memory_percent}%): 캐시 30% 정리 ({reduction}개 항목)")
                self.last_cache_adjustment = current_time
                gc.collect()
                
            # 주의 단계 (85% 이상): 소규모 정리
            elif memory_percent > 85 and current_time - self.last_cache_adjustment > 30:
                # 캐시 크기 15% 축소 - 예방적 조치
                reduction = max(1, int(len(self.cache) * 0.15))
                self._remove_oldest_items_from_cache(reduction)
                logging.warning(f"메모리 주의 수준 감지 ({memory_percent}%): 캐시 15% 정리 ({reduction}개 항목)")
                self.last_cache_adjustment = current_time
                gc.collect()
        except:
            pass  # psutil 사용 불가 등의 예외 상황 무시

    def _remove_oldest_items_from_cache(self, count):
        """캐시에서 가장 오래된 항목 제거하되, 현재 이미지와 인접 이미지는 보존"""
        if not self.cache or count <= 0:
            return 0
            
        # 현재 이미지 경로 및 인접 이미지 경로 확인 (보존 대상)
        preserved_paths = set()
        
        # 1. 현재 표시 중인 이미지나 그리드에 표시 중인 이미지 보존
        if hasattr(self, 'current_image_index') and self.current_image_index >= 0:
            if hasattr(self, 'image_files') and 0 <= self.current_image_index < len(self.image_files):
                current_path = str(self.image_files[self.current_image_index])
                preserved_paths.add(current_path)
                
                # 현재 이미지 주변 이미지도 보존 (앞뒤 3개씩)
                for offset in range(-3, 4):
                    if offset == 0:
                        continue
                    idx = self.current_image_index + offset
                    if 0 <= idx < len(self.image_files):
                        preserved_paths.add(str(self.image_files[idx]))
        
        # 2. 가장 오래된 항목부터 제거하되, 보존 대상은 제외
        items_to_remove = []
        items_removed = 0
        
        for key in list(self.cache.keys()):
            if items_removed >= count:
                break
                
            if key not in preserved_paths:
                items_to_remove.append(key)
                items_removed += 1
        
        # 3. 실제 캐시에서 제거
        for key in items_to_remove:
            del self.cache[key]
            
        return items_removed  # 실제 제거된 항목 수 반환

    def determine_raw_strategy(self, file_path):
        """명시적으로 주어진 파일로 RAW 로딩 전략 결정"""
        file_path_obj = Path(file_path)
        
        # 클래스 수준의 락 사용
        with ImageLoader._strategy_lock:
            # 이미 전역 전략이 초기화되었는지 확인
            if ImageLoader._strategy_initialized:
                logging.debug(f"전역 전략이 이미 초기화됨: {ImageLoader._global_raw_strategy}, 결정 과정 건너뜀 ({file_path_obj.name})")
                # 이미 초기화되었어도 인스턴스의 전략은 업데이트
                self._raw_load_strategy = ImageLoader._global_raw_strategy
                return
                
            # 전략 결정 로직 실행
            current_strategy = RawProcessingStrategyManager.get_current_strategy()
            logging.info(f"RAW 처리 전략 결정 시작: {current_strategy} ({file_path_obj.name})")
            
            # 미리보기 추출 시도
            preview_pixmap_for_check, preview_width, preview_height = self._load_raw_preview_with_orientation(file_path)
            
            # 원본 RAW 크기 확인 시도
            raw_width, raw_height = None, None
            try:
                with rawpy.imread(file_path) as raw:
                    raw_width = raw.sizes.raw_width
                    raw_height = raw.sizes.raw_height
            except Exception as e_raw_size:
                logging.warning(f"RAW 원본 크기 읽기 실패 ({file_path_obj.name}): {e_raw_size}")
            
            # 전략에 따라 처리 방식 결정
            if current_strategy == "ultra_fast":
                # "매우 빠름" - 무조건 미리보기 사용
                determined_strategy = "preview"
                logging.info(f"전략 '{current_strategy}': 무조건 미리보기 사용")
                
                # 미리보기 추출 실패 시 오류 메시지
                if not preview_pixmap_for_check or preview_pixmap_for_check.isNull():
                    # 기존 QEvent 발송 코드 제거하고 메시지 함수 직접 호출
                    self.show_preview_failure_message()
                    
                    logging.warning(f"미리보기 이미지 추출 실패 ({file_path_obj.name}). 설정 변경 필요.")
            
            elif current_strategy == "fast":
                # "빠름" - 미리보기 크기 기준으로 결정
                if preview_pixmap_for_check and not preview_pixmap_for_check.isNull() and preview_width and preview_height:
                    preview_long_edge = max(preview_width, preview_height)
                    if preview_long_edge >= 2900:
                        determined_strategy = "preview"
                        logging.info(f"전략 '{current_strategy}': 미리보기 크기 충분함 ({preview_long_edge}px >= 2900px)")
                    else:
                        determined_strategy = "decode"
                        logging.info(f"전략 '{current_strategy}': 미리보기 크기 작음 ({preview_long_edge}px < 2900px)")
                        # 디코딩 시도
                        try:
                            with rawpy.imread(file_path) as raw:
                                rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
                                # 디코딩 성공 시 decode 전략 유지
                                logging.warning(f"전략 확인: 디코딩 성공")
                        except Exception as e_decode_check:
                            # 디코딩 실패 시 preview 전략으로 변경
                            logging.warning(f"전략 변경: 디코딩 실패 ({e_decode_check}), preview로 전환")
                            determined_strategy = "preview"
                            # 호환성 문제 메시지 표시
                            self.show_compatibility_message()
                else:
                    # 미리보기 추출 실패시 디코딩 시도
                    determined_strategy = "decode"
                    logging.warning(f"전략 '{current_strategy}': 미리보기 추출 실패, 디코딩 시도")
            
            elif current_strategy == "high_quality":
                # "고품질" - 원본 대비 미리보기 품질 or 절대 기준
                if preview_pixmap_for_check and not preview_pixmap_for_check.isNull() and preview_width and preview_height:
                    preview_long_edge = max(preview_width, preview_height)
                    
                    if raw_width and raw_height:
                        # 원본 크기를 알 수 있는 경우: 비율 기준
                        raw_long_edge = max(raw_width, raw_height)
                        preview_ratio = preview_long_edge / raw_long_edge if raw_long_edge > 0 else 0
                        
                        if preview_ratio >= 0.75:  # 75% 이상
                            determined_strategy = "preview"
                            logging.info(f"전략 '{current_strategy}': 미리보기/원본 비율 충분함 ({preview_ratio:.2f} >= 0.75)")
                        else:
                            determined_strategy = "decode"
                            logging.info(f"전략 '{current_strategy}': 미리보기/원본 비율 낮음 ({preview_ratio:.2f} < 0.75)")
                    else:
                        # 원본 크기를 모르는 경우: 절대 크기 기준
                        if preview_long_edge >= 5900:
                            determined_strategy = "preview"
                            logging.info(f"전략 '{current_strategy}': 미리보기 절대 크기 충분함 ({preview_long_edge}px >= 5900px)")
                        else:
                            determined_strategy = "decode"
                            logging.info(f"전략 '{current_strategy}': 미리보기 절대 크기 작음 ({preview_long_edge}px < 5900px)")
                else:
                    # 미리보기 추출 실패시 디코딩 시도
                    determined_strategy = "decode"
                    logging.warning(f"전략 '{current_strategy}': 미리보기 추출 실패, 디코딩 시도")
                
                # 디코딩 전략 선택 시 실제 디코딩 가능 여부 확인
                if determined_strategy == "decode":
                    try:
                        with rawpy.imread(file_path) as raw:
                            rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
                            # 디코딩 성공 시 decode 전략 유지
                            logging.warning(f"전략 확인: 디코딩 성공")
                    except Exception as e_decode_check:
                        # 디코딩 실패 시 preview 전략으로 변경
                        logging.warning(f"전략 변경: 디코딩 실패 ({e_decode_check}), preview로 전환")
                        determined_strategy = "preview"
                        # 호환성 문제 메시지 표시
                        self.show_compatibility_message()
            
            elif current_strategy == "ultra_quality":
                # "최고 품질" - 원본 대비 미리보기 품질 or 절대 기준 (더 높은 기준)
                if preview_pixmap_for_check and not preview_pixmap_for_check.isNull() and preview_width and preview_height:
                    preview_long_edge = max(preview_width, preview_height)
                    
                    if raw_width and raw_height:
                        # 원본 크기를 알 수 있는 경우: 비율 기준
                        raw_long_edge = max(raw_width, raw_height)
                        preview_ratio = preview_long_edge / raw_long_edge if raw_long_edge > 0 else 0
                        
                        if preview_ratio >= 0.90:  # 90% 이상
                            determined_strategy = "preview"
                            logging.info(f"전략 '{current_strategy}': 미리보기/원본 비율 충분함 ({preview_ratio:.2f} >= 0.90)")
                        else:
                            determined_strategy = "decode"
                            logging.info(f"전략 '{current_strategy}': 미리보기/원본 비율 낮음 ({preview_ratio:.2f} < 0.90)")
                    else:
                        # 원본 크기를 모르는 경우: 절대 크기 기준
                        if preview_long_edge >= 9000:
                            determined_strategy = "preview"
                            logging.info(f"전략 '{current_strategy}': 미리보기 절대 크기 충분함 ({preview_long_edge}px >= 9000px)")
                        else:
                            determined_strategy = "decode"
                            logging.info(f"전략 '{current_strategy}': 미리보기 절대 크기 작음 ({preview_long_edge}px < 9000px)")
                else:
                    # 미리보기 추출 실패시 디코딩 시도
                    determined_strategy = "decode"
                    logging.warning(f"전략 '{current_strategy}': 미리보기 추출 실패, 디코딩 시도")
                
                # 디코딩 전략 선택 시 실제 디코딩 가능 여부 확인
                if determined_strategy == "decode":
                    try:
                        with rawpy.imread(file_path) as raw:
                            rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
                            # 디코딩 성공 시 decode 전략 유지
                            logging.info(f"전략 확인: 디코딩 성공")
                    except Exception as e_decode_check:
                        # 디코딩 실패 시 preview 전략으로 변경
                        logging.warning(f"전략 변경: 디코딩 실패 ({e_decode_check}), preview로 전환")
                        determined_strategy = "preview"
                        # 호환성 문제 메시지 표시
                        self.show_compatibility_message()
            else:
                # 기본 전략: 프리뷰
                determined_strategy = "preview"  # Default to decode initially
                logging.warning(f"알 수 없는 전략 '{current_strategy}': 기본값 'preview' 사용")
            
            # --- 최종 결정된 전략 저장 ---
            self._raw_load_strategy = determined_strategy
            
            # 전역 전략 변수 설정 강화 - 클래스 변수 직접 수정
            with ImageLoader._strategy_lock:
                ImageLoader._global_raw_strategy = determined_strategy
                ImageLoader._strategy_initialized = True  # 초기화 플래그 설정
                logging.info(f"전역 RAW 로딩 전략 결정 및 초기화 완료: {determined_strategy}")
                
            logging.info(f"최종 RAW 로딩 전략 결정됨: {self._raw_load_strategy}")

    def cancel_all_raw_decoding(self):
        """진행 중인 모든 RAW 디코딩 작업 취소"""
        # 보류 중인 RAW 디코딩 작업 목록 초기화
        self.pending_raw_decoding.clear()
        
        # 캐시와 전략 초기화
        self._raw_load_strategy = "undetermined"
        logging.info("모든 RAW 디코딩 작업 취소됨, 인스턴스 전략 초기화됨")

    def check_decoder_results(self):
        """멀티프로세스 RAW 디코더의 결과를 주기적으로 확인"""
        # 리소스 매니저를 통한 접근으로 변경
        self.resource_manager.process_raw_results(10)

    def _add_to_cache(self, file_path, pixmap):
        """PixMap을 LRU 방식으로 캐시에 추가"""
        if pixmap and not pixmap.isNull():
            # 캐시 크기 제한 확인
            while len(self.cache) >= self.cache_limit:
                # 가장 오래전에 사용된 항목 제거 (OrderedDict의 첫 번째 항목)
                try:
                    self.cache.popitem(last=False)
                except:
                    break  # 캐시가 비어있는 경우 예외 처리
                    
            # 새 항목 추가 또는 기존 항목 갱신 (최근 사용됨으로 표시)
            self.cache[file_path] = pixmap
            # 항목을 맨 뒤로 이동 (최근 사용)
            self.cache.move_to_end(file_path)
      
    def _load_raw_preview_with_orientation(self, file_path):
        try:
            with rawpy.imread(file_path) as raw:
                try:
                    thumb = raw.extract_thumb()
                    thumb_image = None
                    preview_width, preview_height = None, None
                    orientation = 1  # 기본 방향

                    if thumb.format == rawpy.ThumbFormat.JPEG:
                        # JPEG 썸네일 처리
                        thumb_data = thumb.data
                        thumb_image = Image.open(io.BytesIO(thumb_data))
                        preview_width, preview_height = thumb_image.size

                        # EXIF 방향 정보 추출 시도
                        try:
                            exif_data = thumb_image._getexif()
                            if exif_data and 274 in exif_data:  # 274는 Orientation 태그
                                orientation = exif_data[274]
                        except:
                            orientation = 1  # 실패 시 기본값

                    elif thumb.format == rawpy.ThumbFormat.BITMAP:
                        # 비트맵 썸네일 처리
                        thumb_image = Image.fromarray(thumb.data)
                        preview_width, preview_height = thumb_image.size
                    
                    if thumb_image:
                        # 방향에 따라 이미지 회전
                        if orientation > 1:
                            rotation_methods = {
                                2: Image.FLIP_LEFT_RIGHT,
                                3: Image.ROTATE_180,
                                4: Image.FLIP_TOP_BOTTOM,
                                5: Image.TRANSPOSE,
                                6: Image.ROTATE_270,
                                7: Image.TRANSVERSE,
                                8: Image.ROTATE_90
                            }
                            if orientation in rotation_methods:
                                thumb_image = thumb_image.transpose(rotation_methods[orientation])
                        
                        # PIL Image를 QImage로 수동 변환 (ImageQt 사용하지 않음)
                        if thumb_image.mode == 'P' or thumb_image.mode == 'RGBA':
                            thumb_image = thumb_image.convert('RGBA')
                            img_format = QImage.Format_RGBA8888
                            bytes_per_pixel = 4
                        elif thumb_image.mode != 'RGB':
                            thumb_image = thumb_image.convert('RGB')
                            img_format = QImage.Format_RGB888
                            bytes_per_pixel = 3
                        else:
                            img_format = QImage.Format_RGB888
                            bytes_per_pixel = 3
                        
                        data = thumb_image.tobytes('raw', thumb_image.mode)
                        qimage = QImage(
                            data,
                            thumb_image.width,
                            thumb_image.height,
                            thumb_image.width * bytes_per_pixel,
                            img_format
                        )
                        
                        pixmap = QPixmap.fromImage(qimage)
                        
                        if pixmap and not pixmap.isNull():
                            logging.info(f"내장 미리보기 로드 성공 ({Path(file_path).name})")
                            return pixmap, preview_width, preview_height  # Return pixmap and dimensions
                        else:
                            raise ValueError("미리보기 QPixmap 변환 실패")
                    else:
                        raise rawpy.LibRawUnsupportedThumbnailError(f"지원하지 않는 미리보기 형식: {thumb.format}")

                except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError) as e_thumb:
                    logging.error(f"내장 미리보기 없음/지원안함 ({Path(file_path).name}): {e_thumb}")
                    return None, None, None  # Return None for all on failure
                except Exception as e_inner:
                    logging.error(f"미리보기 처리 중 오류 ({Path(file_path).name}): {e_inner}")
                    return None, None, None  # Return None for all on failure

        except (rawpy.LibRawIOError, rawpy.LibRawFileUnsupportedError, Exception) as e:
            logging.error(f"RAW 파일 읽기 오류 (미리보기 시도 중) ({Path(file_path).name}): {e}")
            return None, None, None  # Return None for all on failure

        # Should not be reached, but as fallback
        return None, None, None
    
    def load_image_with_orientation(self, file_path):
        """EXIF 방향 정보를 고려하여 이미지를 올바른 방향으로 로드 (RAW 로딩 전략 포함)"""
        # 캐시 확인
        if file_path in self.cache:
            # 최근 사용 표시 (LRU 캐시 업데이트)
            self.cache.move_to_end(file_path)
            return self.cache[file_path]

        file_path_obj = Path(file_path)
        is_raw = file_path_obj.suffix.lower() in self.raw_extensions
        pixmap = None # 결과 Pixmap 변수 초기화

        # --- RAW 파일 처리 로직 ---
        if is_raw:
            # --- 이미지가 아직 설정되지 않은 경우 전략 적용 ---
            if pixmap is None:
                # 무조건 클래스 변수 확인 후 인스턴스 변수에 동기화
                with ImageLoader._strategy_lock:
                    if ImageLoader._strategy_initialized:
                        # 전역 전략이 설정되어 있으면 인스턴스 변수에 동기화
                        if self._raw_load_strategy != ImageLoader._global_raw_strategy:
                            self._raw_load_strategy = ImageLoader._global_raw_strategy
                            logging.debug(f"인스턴스 전략 동기화: {self._raw_load_strategy} ({file_path_obj.name})")

                if self._raw_load_strategy == "preview":
                    logging.info(f"전략 적용 'preview': ({file_path_obj.name})")
                    # Only try loading the preview. Do not fall back to decode.
                    preview_pixmap_result, _, _ = self._load_raw_preview_with_orientation(file_path)
                    if preview_pixmap_result and not preview_pixmap_result.isNull():
                        pixmap = preview_pixmap_result
                    else:
                        logging.warning(f"'preview' 전략 실패, 미리보기 로드 불가 ({file_path_obj.name})")
                        pixmap = QPixmap() # Return empty pixmap on failure

                elif self._raw_load_strategy == "decode":
                    logging.info(f"전략 적용 'decode': ({file_path_obj.name})")
                    
                    # 이미 디코딩 중이거나 캐시에 있는지 확인
                    if file_path in self.pending_raw_decoding:
                        logging.debug(f"이미 디코딩 중: {file_path_obj.name}")
                        # 임시 플레이스홀더 이미지 반환
                        placeholder = QPixmap(100, 100)
                        placeholder.fill(QColor(40, 40, 40))
                        return placeholder
                    
                    # 최근에 이미 디코딩했는지 확인 (중복 디코딩 방지) - 새 로직
                    current_time = time.time()
                    if file_path_obj.name in self.recently_decoded:
                        last_decode_time = self.recently_decoded[file_path_obj.name]
                        if current_time - last_decode_time < self.decoding_cooldown:
                            logging.debug(f"최근에 이미 디코딩한 파일: {file_path_obj.name}, 플레이스홀더 반환")
                            # 플레이스홀더 반환 (로딩 표시용)
                            placeholder = QPixmap(100, 100)
                            placeholder.fill(QColor(40, 40, 40))
                            return placeholder


                    try:
                        with rawpy.imread(file_path) as raw:
                            try:
                                # --- user_flip=1 제거: rawpy가 방향 자동 처리하도록 함 ---
                                rgb = raw.postprocess(use_camera_wb=True, output_bps=8) # <- user_flip 제거
                                # --- QImage 생성 시 rawpy 결과 직접 사용 ---
                                height, width, _ = rgb.shape # <- rotated_rgb 대신 rgb 사용
                                # Ensure data is contiguous
                                rgb_contiguous = np.ascontiguousarray(rgb) # <- rotated_rgb_contiguous 대신 rgb_contiguous 사용
                                qimage = QImage(rgb_contiguous.data, width, height, rgb_contiguous.strides[0], QImage.Format_RGB888)

                                pixmap_result = QPixmap.fromImage(qimage)
                                if pixmap_result and not pixmap_result.isNull():
                                    pixmap = pixmap_result
                                    logging.info(f"RAW 디코딩 (rawpy 자동 방향 처리) 성공 ({file_path_obj.name})")
                                else:
                                    logging.warning(f"RAW 디코딩 후 QPixmap 변환 실패 ({file_path_obj.name})")
                                    pixmap = QPixmap()

                            except rawpy.LibRawDecodingError as e_decoding:
                                logging.error(f"'decode' 전략 실패, postprocess 오류 ({file_path_obj.name}): {e_decoding}")
                                pixmap = QPixmap() # Return empty on decoding error

                    except (rawpy.LibRawIOError, rawpy.LibRawFileUnsupportedError, Exception) as e_raw_read:
                        logging.error(f"'decode' 전략 실패, 파일 읽기 오류 ({file_path_obj.name}): {e_raw_read}")
                        pixmap = QPixmap() # Return empty on read error

                    # 최근 디코딩 기록 정리 (메모리 관리) - 새 로직
                    self._clean_old_decoding_history(current_time)

                elif self._raw_load_strategy == "undetermined":
                    # 전략이 아직 결정되지 않은 경우 기본값 사용
                    # 스레드 안전성을 위해 락 획득
                    with self._strategy_lock:
                        # 현재 설정된 전역 전략 확인 (다른 스레드에서 설정됐을 수 있음)
                        if hasattr(ImageLoader, '_global_raw_strategy') and ImageLoader._global_raw_strategy != "undetermined":
                            # 전역 전략이 이미 설정되었다면 사용
                            self._raw_load_strategy = ImageLoader._global_raw_strategy
                            logging.info(f"전역 전략 적용: {self._raw_load_strategy} ({file_path_obj.name})")
                        else:
                            # 아직 전략이 결정되지 않은 경우
                            logging.warning(f"전략이 결정되지 않음, 기본 'preview' 사용: ({file_path_obj.name})")
                            # 기본 preview 전략으로 설정 후 전역 초기화
                            self._raw_load_strategy = "preview"
                            ImageLoader._global_raw_strategy = "preview"
                            ImageLoader._strategy_initialized = True
                            try:
                                parent = self.parent()
                                if hasattr(parent, 'save_state'):
                                    parent.save_state()
                            except Exception as e:
                                logging.error(f"설정 저장 중 오류: {e}")
                    # 전략에 따른 처리 (이 부분은 기존 코드 유지)
                    preview_pixmap_result, _, _ = self._load_raw_preview_with_orientation(file_path)
                    if preview_pixmap_result and not preview_pixmap_result.isNull():
                        pixmap = preview_pixmap_result
                    else:
                        logging.warning(f"미리보기 로드 실패, 빈 픽스맵 반환: ({file_path_obj.name})")
                        pixmap = QPixmap()

            # --- Caching and Return (Common for RAW) ---
            if pixmap and not pixmap.isNull():
                self._add_to_cache(file_path, pixmap)
                return pixmap
            else:
                # If strategy execution failed, return an empty QPixmap
                logging.error(f"RAW 처리 최종 실패 ({file_path_obj.name}), 빈 QPixmap 반환")
                return QPixmap()
        # --- RAW 파일 처리 로직 끝 ---

        # --- JPG 파일 처리 로직 (수정) ---
        else: # Not RAW
            try:
                # Use context manager for file opening
                with open(file_path, 'rb') as f:
                    # Load with PIL
                    image = Image.open(f)
                    # Ensure image data is loaded to access EXIF before closing file
                    image.load()

                orientation = 1
                # Check EXIF using Pillow's method
                if hasattr(image, 'getexif'): # Use getexif() for modern Pillow
                    exif = image.getexif()
                    if exif and 0x0112 in exif:
                        orientation = exif[0x0112]

                # Apply orientation using Pillow
                if orientation > 1:
                    if orientation == 2: 
                        image = image.transpose(Image.FLIP_LEFT_RIGHT)
                    elif orientation == 3: 
                        image = image.transpose(Image.ROTATE_180)
                    elif orientation == 4: 
                        image = image.transpose(Image.FLIP_TOP_BOTTOM)
                    elif orientation == 5: 
                        image = image.transpose(Image.TRANSPOSE)
                    elif orientation == 6: 
                        image = image.transpose(Image.ROTATE_270)
                    elif orientation == 7: 
                        image = image.transpose(Image.TRANSVERSE)
                    elif orientation == 8: 
                        image = image.transpose(Image.ROTATE_90)
                    
                # 이미지 모드 확인 및 변환 (필요시)
                if image.mode == 'P' or image.mode == 'RGBA':
                    image = image.convert('RGBA')
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                    
                # PIL Image를 QImage로 수동 변환 (ImageQt 사용하지 않음)
                img_format = QImage.Format_RGBA8888 if image.mode == 'RGBA' else QImage.Format_RGB888
                bytes_per_pixel = 4 if image.mode == 'RGBA' else 3
                
                data = image.tobytes('raw', image.mode)
                qimage = QImage(
                    data, 
                    image.width, 
                    image.height,
                    image.width * bytes_per_pixel,
                    img_format
                )
                
                # QImage에서 QPixmap 생성
                pixmap = QPixmap.fromImage(qimage)

                if pixmap and not pixmap.isNull():
                    self._add_to_cache(file_path, pixmap)
                    return pixmap
                else:
                    logging.warning(f"JPG QPixmap 변환 실패 ({file_path_obj.name})")
                    return QPixmap() # Return empty if conversion fails

            except Exception as e:
                logging.error(f"JPG 이미지 처리 오류 ({file_path_obj.name}): {e}")
                # Fallback: Try loading directly with QPixmap
                try:
                    pixmap = QPixmap(file_path)
                    if not pixmap.isNull():
                        self._add_to_cache(file_path, pixmap)
                        return pixmap
                    else:
                        logging.warning(f"기본 QPixmap 로드 실패 (JPG) ({file_path_obj.name})")
                        return QPixmap() # Return empty if fallback fails
                except Exception as e2:
                    logging.exception(f"기본 QPixmap 로드 중 예외 (JPG) ({file_path_obj.name}): {e2}")
                    return QPixmap() # Return empty on exception

        # Should not be reached if logic is correct, but as a final fallback
        logging.error(f"모든 이미지 로드 시도 실패 ({file_path_obj.name})")
        return QPixmap()
    
    def _clean_old_decoding_history(self, current_time, max_entries=50):
        """오래된 디코딩 이력 정리 (메모리 관리)"""
        if len(self.recently_decoded) <= max_entries:
            return
            
        # 현재 시간으로부터 일정 시간이 지난 항목 제거
        old_threshold = current_time - (self.decoding_cooldown * 2)
        keys_to_remove = []
        
        for file_name, decode_time in self.recently_decoded.items():
            if decode_time < old_threshold:
                keys_to_remove.append(file_name)
        
        # 실제 항목 제거
        for key in keys_to_remove:
            del self.recently_decoded[key]
            
        # 여전히 너무 많은 항목이 있으면 가장 오래된 것부터 제거
        if len(self.recently_decoded) > max_entries:
            items = sorted(self.recently_decoded.items(), key=lambda x: x[1])
            to_remove = items[:len(items) - max_entries]
            for file_name, _ in to_remove:
                del self.recently_decoded[file_name]

    # def show_compatibility_message(self):
    #     """호환성 문제 메시지를 표시 (디코딩 실패 시)"""
        
    #     # 메인 스레드에서 실행되는 슬롯 함수로 만들기 
    #     def show_message_box_on_main_thread():
    #         msg_box = QMessageBox()
    #         msg_box.setWindowTitle(LanguageManager.translate("호환성 문제"))
    #         msg_box.setText(LanguageManager.translate("RAW 디코딩 실패. 미리보기를 대신 사용합니다."))
    #         msg_box.setIcon(QMessageBox.Warning)
    #         msg_box.exec_()
        
    #     # 올바르게 메인 스레드에서 메시지 박스 표시 함수 호출
    #     QMetaObject.invokeMethod(
    #         self, 
    #         "show_message_box_on_main_thread",  # 실제 호출할 함수명
    #         Qt.QueuedConnection
    # )

    def show_compatibility_message(self):
        """호환성 문제 메시지를 표시 (디코딩 실패 시)"""
        
        def show_message():
            msg_box = QMessageBox()
            msg_box.setWindowTitle(LanguageManager.translate("호환성 문제"))
            msg_box.setText(LanguageManager.translate("RAW 디코딩 실패. 미리보기를 대신 사용합니다."))
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.exec_()
        
        # QTimer를 사용하면 메타 객체 시스템을 거치지 않고도 메인 스레드에서 실행 가능
        QTimer.singleShot(0, show_message)

        
    def show_preview_failure_message(self):
        """'매우 빠름' 모드에서 미리보기 추출 실패 시 메시지 표시"""
        
        def show_message():
            msg_box = QMessageBox()
            msg_box.setWindowTitle(LanguageManager.translate("미리보기 추출 실패"))
            msg_box.setText(LanguageManager.translate("미리보기 이미지 추출 실패. RAW 파일 처리 설정을 바꿔보세요"))
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.exec_()
        
        # QTimer를 사용하면 메타 객체 시스템을 거치지 않고도 메인 스레드에서 실행 가능
        QTimer.singleShot(0, show_message)
    


    def preload_page(self, image_files, page_start_index, cells_per_page):
        """특정 페이지의 이미지를 미리 로딩"""
        self.last_requested_page = page_start_index // cells_per_page
        
        # 이전 작업 취소
        for future in self.active_futures:
            future.cancel()
        self.active_futures.clear()
        
        # 현재 페이지 이미지 로드
        end_idx = min(page_start_index + cells_per_page, len(image_files))
        futures = []
        
        for i in range(page_start_index, end_idx):
            if i < 0 or i >= len(image_files):
                continue
                
            img_path = str(image_files[i])
            if img_path in self.cache:
                # 이미 캐시에 있으면 시그널 발생
                pixmap = self.cache[img_path]
                self.imageLoaded.emit(i - page_start_index, pixmap, img_path)
            else:
                # 캐시에 없으면 비동기 로딩
                future = self.load_executor.submit(self._load_and_signal, i - page_start_index, img_path)
                futures.append(future)
                
        self.active_futures = futures
        
        # 다음 페이지도 미리 로드 (UI 블로킹 없이)
        next_page_start = page_start_index + cells_per_page
        if next_page_start < len(image_files):
            next_end = min(next_page_start + cells_per_page, len(image_files))
            for i in range(next_page_start, next_end):
                if i >= len(image_files):
                    break
                    
                img_path = str(image_files[i])
                if img_path not in self.cache:
                    future = self.load_executor.submit(self._preload_image, img_path)
                    self.active_futures.append(future)
    
    def _load_and_signal(self, cell_index, img_path):
        """이미지 로드 후 시그널 발생"""
        try:
            pixmap = self.load_image_with_orientation(img_path)
            self.imageLoaded.emit(cell_index, pixmap, img_path)
            return True
        except Exception as e:
            logging.error(f"이미지 로드 오류 (인덱스 {cell_index}): {e}")
            return False
    
    def _preload_image(self, img_path):
        """이미지 미리 로드 (시그널 없음)"""
        try:
            self.load_image_with_orientation(img_path)
            return True
        except:
            return False
    
    def clear_cache(self):
        """캐시 초기화"""
        self.cache.clear()
        self._raw_load_strategy = "undetermined" # RAW 로딩 전략 초기화
        print("Image cache cleared and RAW load strategy reset for this instance.")
        
        # 이전 작업 취소
        for future in self.active_futures:
            future.cancel()
        self.active_futures.clear()




# ZoomScrollArea 클래스 정의 추가
class ZoomScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 부모 참조 저장 (PhotoSortApp 인스턴스)
        self.app_parent = parent

    def wheelEvent(self, event: QWheelEvent):
        # 부모 위젯 (PhotoSortApp)의 zoom_mode 확인
        if self.app_parent and hasattr(self.app_parent, 'zoom_mode') and self.app_parent.zoom_mode in ["100%", "200%"]:
            # 100% 또는 200% 줌 모드에서는 휠 이벤트를 무시
            event.accept()
            return
        else:
            # 그 외의 경우 (Fit 모드 등) 기본 스크롤 동작 수행
            super().wheelEvent(event)

# FilenameLabel 클래스 정의 추가
class FilenameLabel(QLabel):
    """파일명을 표시하는 레이블 클래스, 더블클릭 시 파일 열기"""
    doubleClicked = Signal(str) # 시그널에 파일명(str) 전달

    def __init__(self, text="", fixed_height_padding=40, parent=None):
        super().__init__(parent=parent)
        self.full_filename = "" # 전체 파일명 저장
        self.setCursor(Qt.PointingHandCursor)
        self.setAlignment(Qt.AlignCenter) # 가운데 정렬

        # 폰트 설정 (Arial, 12pt, Bold)
        font = QFont("Arial", UIScaleManager.get("filename_font_size"))
        font.setBold(True) # Bold 설정 추가
        self.setFont(font)

        # 폰트 메트릭스를 이용해 2줄 높이 계산(현재는 1줄)
        fm = QFontMetrics(font)
        line_height = fm.height()
        fixed_height = line_height + fixed_height_padding
        self.setFixedHeight(fixed_height)
        self.setFixedHeight(fixed_height)

        self.setWordWrap(True) # 자동 줄바꿈 활성화
        self.setStyleSheet(f"color: {ThemeManager.get_color('text')};") # 기본 텍스트 색상
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed) # 크기 정책
        self.setText(text) # 초기 텍스트 설정 (setText 오버라이드 사용)

    def setText(self, text: str):
        """텍스트 설정 메서드 오버라이드 (파일명 생략 기능 추가)"""
        self.full_filename = text # 전체 파일명 저장
        self.setToolTip(text) # 툴팁에 전체 파일명 설정

        if len(text) > 17:
            # "앞A자...뒤B자" 형식으로 생략
            display_text = text[:6] + " ... " + text[-10:]
        else:
            display_text = text

        super().setText(display_text) # 화면 표시 업데이트

    def text(self) -> str:
        return super().text()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """더블클릭 시 full_filename으로 시그널 발생"""
        if self.full_filename:
            self.doubleClicked.emit(self.full_filename)


class QRLinkLabel(QLabel):
    """마우스 오버 시 QR 코드를 보여주고, 클릭 시 URL을 여는 범용 라벨"""
    def __init__(self, text, url, qr_path=None, parent=None, color="#D8D8D8", size=400):
        super().__init__(text, parent)
        self.url = url
        self.qr_popup = None
        self.qr_path = qr_path
        self.normal_color = color  # 링크 느낌의 파란색 계열 사용
        self.hover_color = "#FFFFFF"  # 밝은 색상 (마우스 오버 시)
        
        # 기본 스타일 적용
        self.setStyleSheet(f"""
            color: {self.normal_color};
            text-decoration: none;
            font-weight: normal;
        """)
        self.setCursor(Qt.PointingHandCursor)  # 손가락 커서로 변경
        
        # QR 팝업 생성
        self.create_qr_popup(size)
    
    def enterEvent(self, event):
        """마우스가 위젯에 들어왔을 때 스타일 변경 및 QR 코드 표시"""
        self.setStyleSheet(f"""
            color: {self.hover_color};
            text-decoration: none;
            font-weight: bold;
        """)
        
        # QR 팝업 표시 로직 (기존 코드)
        if self.qr_popup.property("has_qr_content"):
            global_pos = self.mapToGlobal(QPoint(0, 0))
            popup_x = global_pos.x() + (self.width() - self.qr_popup.width()) // 2
            popup_y = global_pos.y() - self.qr_popup.height() - 5
            self.qr_popup.move(popup_x, popup_y)
            self.qr_popup.show()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        """마우스가 위젯을 벗어났을 때 스타일 복원 및 QR 코드 숨김"""
        # 원래 스타일로 복원
        self.setStyleSheet(f"""
            color: {self.normal_color};
            text-decoration: none;
            font-weight: normal;
        """)
        self.qr_popup.hide()
        super().leaveEvent(event)
    
    def create_qr_popup(self, size=400):
        """QR 코드 팝업 생성"""
        self.qr_popup = QLabel(self.parent())
        self.qr_popup.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.qr_popup.setAttribute(Qt.WA_TranslucentBackground)
        self.qr_popup.setStyleSheet("background-color: white; border-radius: 5px; padding: 5px;")
        self.qr_popup.hide()
        
        # QR 코드 이미지 설정 (파일이 있는 경우에만 처리)
        if self.qr_path and Path(self.qr_path).exists():
            qr_pixmap = QPixmap(self.qr_path)
            if not qr_pixmap.isNull():
                # QR 코드 크기 조정
                qr_pixmap = qr_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.qr_popup.setPixmap(qr_pixmap)
                self.qr_popup.adjustSize()
                # QR 이미지가 있는 경우에만 표시 여부 속성 설정
                self.qr_popup.setProperty("has_qr_content", True)
        else:
            # 경로가 없거나 파일이 없으면 표시 안 함 속성 설정
            self.qr_popup.setProperty("has_qr_content", False)
    
    def mouseReleaseEvent(self, event):
        """마우스 클릭 시 URL 열기"""
        if event.button() == Qt.LeftButton:
            QDesktopServices.openUrl(QUrl(self.url))
        super().mouseReleaseEvent(event)


class PhotoSortApp(QMainWindow):
    STATE_FILE = "photosort_data.json" # 상태 저장 파일 이름 정의

    def __init__(self):
        super().__init__()
        
        # 앱 제목 설정
        self.setWindowTitle("PhotoSort")
        
        # 내부 변수 초기화
        self.current_folder = ""
        self.raw_folder = ""
        self.image_files = []
        self.raw_files = {}  # 키: 기본 파일명, 값: RAW 파일 경로
        self.is_raw_only_mode = False # RAW 단독 로드 모드인지 나타내는 플래그
        self.raw_extensions = {'.arw', '.crw', '.dng', '.cr2', '.cr3', '.nef', 
                             '.nrw', '.raf', '.srw', '.srf', '.sr2', '.rw2', 
                             '.rwl', '.x3f', '.gpr', '.orf', '.pef', '.ptx', 
                             '.3fr', '.fff', '.mef', '.iiq', '.braw', '.ari', '.r3d'}
        self.current_image_index = -1
        self.move_raw_files = True  # RAW 파일 이동 여부 (기본값: True)
        self.target_folders = ["", "", ""]  # 분류 대상 폴더 경로 (최대 3개)
        self.folder_count = 1  # 기본 폴더 개수
        self.zoom_mode = "Fit"  # 기본 확대 모드: "Fit", "100%", "200%"
        self.original_pixmap = None  # 원본 이미지 pixmap
        self.panning = False  # 패닝 모드 여부
        self.pan_start_pos = QPoint(0, 0)  # 패닝 시작 위치
        self.scroll_pos = QPoint(0, 0)  # 스크롤 위치 

        self.control_panel_on_right = False # 기본값: 왼쪽 (False)

        # 메모리 모니터링 및 자동 조정을 위한 타이머
        self.memory_monitor_timer = QTimer(self)
        self.memory_monitor_timer.setInterval(10000)  # 10초마다 확인
        self.memory_monitor_timer.timeout.connect(self.check_memory_usage)
        self.memory_monitor_timer.start()
        
        # 시스템 사양 검사
        self.system_memory_gb = self.get_system_memory_gb()
        self.system_cores = cpu_count()


        # 파일 이동 기록 (Undo/Redo 용)
        self.move_history = [] # 이동 기록을 저장할 리스트
        self.history_pointer = -1 # 현재 히스토리 위치 (-1은 기록 없음)
        self.max_history = 10 # 최대 저장할 히스토리 개수

        # Grid 관련 변수 추가
        self.grid_mode = "Off" # 'Off', '2x2', '3x3'
        self.current_grid_index = 0 # 현재 선택된 그리드 셀 인덱스 (0부터 시작)
        self.grid_page_start_index = 0 # 현재 그리드 페이지의 시작 이미지 인덱스
        self.grid_layout = None # 그리드 레이아웃 객체
        self.grid_labels = []   # 그리드 셀 QLabel 목록

        # 리소스 매니저 초기화
        self.resource_manager = ResourceManager.instance()

        # --- 그리드 썸네일 사전 생성을 위한 변수 추가 ---
        self.grid_thumbnail_cache_2x2 = {} # 2x2 그리드 썸네일 캐시 (key: image_path, value: QPixmap)
        self.grid_thumbnail_cache_3x3 = {} # 3x3 그리드 썸네일 캐시 (key: image_path, value: QPixmap)
        self.active_thumbnail_futures = [] # 현재 실행 중인 백그라운드 썸네일 작업 추적
        self.grid_thumbnail_executor = ThreadPoolExecutor(
        max_workers=2, 
        thread_name_prefix="GridThumbnail")

        # 이미지 방향 추적을 위한 변수 추가
        self.current_image_orientation = None  # "landscape" 또는 "portrait"
        self.previous_image_orientation = None
        

        # 미니맵 관련 변수
        self.minimap_visible = False  # 미니맵 표시 여부
        self.minimap_base_size = 230  # 미니맵 기본 크기 (배율 적용 전)
        self.minimap_max_size = self.get_scaled_size(self.minimap_base_size)  # UI 배율 적용한 최대 크기
        self.minimap_width = self.minimap_max_size
        self.minimap_height = int(self.minimap_max_size / 1.5)  # 3:2 비율 기준
        self.minimap_pixmap = None     # 미니맵용 축소 이미지
        self.minimap_viewbox = None    # 미니맵 뷰박스 정보
        self.minimap_dragging = False  # 미니맵 드래그 중 여부
        self.minimap_viewbox_dragging = False  # 미니맵 뷰박스 드래그 중 여부
        self.minimap_drag_start = QPoint(0, 0)  # 미니맵 드래그 시작 위치
        self.last_event_time = 0  # 이벤트 스로틀링을 위한 타임스탬프
        
        # 미니맵 뷰박스 캐싱 변수
        self.cached_viewbox_params = {
            "zoom": None, 
            "img_pos": None, 
            "canvas_size": None
        }
        
        # 이미지 캐싱 관련 변수 추가
        self.fit_pixmap_cache = {}  # 크기별로 Fit 이미지 캐싱
        self.last_fit_size = (0, 0)
        
        # 이미지 로더/캐시 추가
        self.image_loader = ImageLoader(raw_extensions=self.raw_extensions)
        self.image_loader.imageLoaded.connect(self.on_image_loaded)
        self.image_loader.loadCompleted.connect(self._on_image_loaded_for_display)  # 새 시그널 연결
        self.image_loader.loadFailed.connect(self._on_image_load_failed)  # 새 시그널 연결

        # 시스템 사양에 따른 설정 조정
        self.adjust_settings_for_system()
        
        # 그리드 로딩 시 빠른 표시를 위한 플레이스홀더 이미지
        self.placeholder_pixmap = QPixmap(100, 100)
        self.placeholder_pixmap.fill(QColor("#222222"))
        
        # 다크 테마 적용
        self.setup_dark_theme()
        
        # 제목 표시줄 다크 테마 적용
        self.setup_dark_titlebar()
        
        # 중앙 위젯 설정
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 메인 레이아웃 설정
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 수평 분할기 생성
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(0)  # 분할기 핸들 너비를 0픽셀로 설정
        self.main_layout.addWidget(self.splitter)
        
        # 좌측 컨트롤 영역 생성
        self.control_panel = QWidget()
        self.control_layout = QVBoxLayout(self.control_panel)
        self.control_layout.setContentsMargins(*UIScaleManager.get_margins())
        self.control_layout.setSpacing(UIScaleManager.get("control_layout_spacing"))
        
        # 우측 이미지 영역 생성 (검은색 배경으로 설정)
        self.image_panel = QFrame()
        self.image_panel.setFrameShape(QFrame.NoFrame)
        self.image_panel.setAutoFillBackground(True)
        
        # 이미지 패널에 검은색 배경 설정
        image_palette = self.image_panel.palette()
        image_palette.setColor(QPalette.Window, QColor(0, 0, 0))
        self.image_panel.setPalette(image_palette)
        
        # 이미지 레이아웃 설정 - 초기에는 단일 이미지 레이아웃
        self.image_layout = QVBoxLayout(self.image_panel) # 기본 이미지 표시용 레이아웃
        self.image_layout.setContentsMargins(0, 0, 0, 0)
        
        # 패닝을 위한 컨테이너 위젯
        self.image_container = QWidget()
        self.image_container.setStyleSheet("background-color: black;")
        
        # 이미지 레이블 생성 (단일 이미지 표시용)
        self.image_label = QLabel(self.image_container)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: transparent;")
        
        # 스크롤 영역 설정 - ZoomScrollArea 사용
        self.scroll_area = ZoomScrollArea(self) # ZoomScrollArea 인스턴스 생성 (self 전달)
        self.scroll_area.setWidget(self.image_container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: black; border: none;")
        
        # 스크롤바 숨기기
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 마우스 이벤트 처리를 위한 설정 (단일 이미지 모드용)
        self.image_container.setMouseTracking(True)
        self.image_container.mousePressEvent = self.image_mouse_press_event
        self.image_container.mouseMoveEvent = self.image_mouse_move_event
        self.image_container.mouseReleaseEvent = self.image_mouse_release_event
        
        # 더블클릭 이벤트 연결
        self.image_container.mouseDoubleClickEvent = self.image_mouse_double_click_event
        
        # 미니맵 위젯 생성
        self.minimap_widget = QWidget(self.image_panel)
        self.minimap_widget.setStyleSheet("background-color: rgba(20, 20, 20, 200); border: 1px solid #666666;")
        self.minimap_widget.setFixedSize(self.minimap_width, self.minimap_height)
        self.minimap_widget.hide()  # 초기에는 숨김
        
        # 미니맵 레이블 생성
        self.minimap_label = QLabel(self.minimap_widget)
        self.minimap_label.setAlignment(Qt.AlignCenter)
        self.minimap_layout = QVBoxLayout(self.minimap_widget)
        self.minimap_layout.setContentsMargins(0, 0, 0, 0)
        self.minimap_layout.addWidget(self.minimap_label)
        
        # 미니맵 마우스 이벤트 설정
        self.minimap_widget.setMouseTracking(True)
        self.minimap_widget.mousePressEvent = self.minimap_mouse_press_event
        self.minimap_widget.mouseMoveEvent = self.minimap_mouse_move_event
        self.minimap_widget.mouseReleaseEvent = self.minimap_mouse_release_event
        
        self.image_layout.addWidget(self.scroll_area)
        
        # 세로 가운데 정렬을 위한 상단 Stretch
        self.control_layout.addStretch(1)

        # --- JPG 폴더 섹션 ---
        self.load_button = QPushButton(LanguageManager.translate("JPG 불러오기")) # 버튼 먼저 추가
        self.load_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                padding: {UIScaleManager.get("button_padding")}px;
                border-radius: 1px;
                min-height: {UIScaleManager.get("button_min_height")}px;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.get_color('accent_hover')};
            }}
            QPushButton:pressed {{
                background-color: {ThemeManager.get_color('accent_pressed')};
            }}
            QPushButton:disabled {{
                background-color: {ThemeManager.get_color('bg_disabled')};
                color: {ThemeManager.get_color('text_disabled')};
                opacity: 0.7;
            }}
        """)
        self.load_button.clicked.connect(self.load_jpg_folder)
        self.control_layout.addWidget(self.load_button) # 컨트롤 레이아웃에 직접 추가

        # JPG 폴더 경로/클리어 컨테이너
        jpg_folder_container = QWidget()
        jpg_folder_layout = QHBoxLayout(jpg_folder_container)
        jpg_folder_layout.setContentsMargins(0, 3, 0, 3) # 상하 여백 추가
        jpg_folder_layout.setSpacing(UIScaleManager.get("folder_container_spacing", 5))

        # JPG 폴더 경로 표시 레이블 추가
        folder_label_padding = UIScaleManager.get("folder_label_padding")
        self.folder_path_label = FolderPathLabel(LanguageManager.translate("폴더 경로"), fixed_height_padding=folder_label_padding)
        self.folder_path_label.setWordWrap(True)
        self.folder_path_label.doubleClicked.connect(self.open_folder_in_explorer)

        # JPG 폴더 클리어 버튼 (X) 추가
        self.jpg_clear_button = QPushButton("X")
        delete_button_style = f"""
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                padding: 4px;
                border-radius: 1px;
                min-height: {UIScaleManager.get("button_min_height")}px;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.get_color('accent_hover')};
                color: white;
            }}
            QPushButton:pressed {{
                background-color: {ThemeManager.get_color('accent_pressed')};
                color: white;
            }}
            QPushButton:disabled {{
                background-color: {ThemeManager.get_color('bg_disabled')};
                color: {ThemeManager.get_color('text_disabled')};
            }}
        """
        self.jpg_clear_button.setStyleSheet(delete_button_style)
        fm_label = QFontMetrics(self.folder_path_label.font()) # FolderPathLabel의 폰트 기준
        label_line_height = fm_label.height()
        label_fixed_height = (label_line_height * 2) + UIScaleManager.get("folder_label_padding")
        self.jpg_clear_button.setFixedHeight(label_fixed_height)
        self.jpg_clear_button.setFixedWidth(UIScaleManager.get("delete_button_width"))
        self.jpg_clear_button.setEnabled(False)
        self.jpg_clear_button.clicked.connect(self.clear_jpg_folder)

        # JPG 폴더 레이아웃에 레이블과 버튼 추가
        jpg_folder_layout.addWidget(self.folder_path_label, 1) # 레이블 확장
        jpg_folder_layout.addWidget(self.jpg_clear_button)
        self.control_layout.addWidget(jpg_folder_container) # 메인 레이아웃에 컨테이너 추가

        self.control_layout.addSpacing(UIScaleManager.get("JPG_RAW_spacing", 15))

        # --- RAW 폴더 섹션 ---
        self.match_raw_button = QPushButton(LanguageManager.translate("JPG - RAW 연결")) # 버튼 먼저 추가
        self.match_raw_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                padding: {UIScaleManager.get("button_padding")}px; 
                border-radius: 1px;
                min-height: {UIScaleManager.get("button_min_height")}px; 
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.get_color('accent_hover')};
            }}
            QPushButton:pressed {{
                background-color: {ThemeManager.get_color('accent_pressed')};
            }}
            QPushButton:disabled {{
                background-color: {ThemeManager.get_color('bg_disabled')};
                color: {ThemeManager.get_color('text_disabled')};
                opacity: 0.7;
            }}
""")
        self.match_raw_button.clicked.connect(self.on_match_raw_button_clicked)
        self.control_layout.addWidget(self.match_raw_button) # 컨트롤 레이아웃에 직접 추가

        # RAW 폴더 경로/클리어 컨테이너
        raw_folder_container = QWidget()
        raw_folder_layout = QHBoxLayout(raw_folder_container)
        raw_folder_layout.setContentsMargins(0, 3, 0, 3) # 상하 여백 추가
        raw_folder_layout.setSpacing(UIScaleManager.get("folder_container_spacing", 5))

        # RAW 폴더 경로 표시 레이블 추가
        folder_label_padding = UIScaleManager.get("folder_label_padding")
        self.raw_folder_path_label = FolderPathLabel(LanguageManager.translate("폴더 경로"), fixed_height_padding=folder_label_padding)
        self.raw_folder_path_label.setWordWrap(True)
        self.raw_folder_path_label.doubleClicked.connect(self.open_raw_folder_in_explorer)

        # RAW 폴더 클리어 버튼 (X) 추가
        self.raw_clear_button = QPushButton("X")
        self.raw_clear_button.setStyleSheet(delete_button_style) # JPG 클리어 버튼과 동일 스타일
        fm_label = QFontMetrics(self.raw_folder_path_label.font()) # raw 폴더 레이블 폰트 기준
        label_line_height = fm_label.height()
        label_fixed_height = (label_line_height * 2) + UIScaleManager.get("folder_label_padding")
        self.raw_clear_button.setFixedHeight(label_fixed_height)
        self.raw_clear_button.setFixedWidth(UIScaleManager.get("delete_button_width"))
        self.raw_clear_button.setEnabled(False) # 초기 비활성화
        self.raw_clear_button.clicked.connect(self.clear_raw_folder) # 시그널 연결

        # RAW 폴더 레이아웃에 레이블과 버튼 추가
        raw_folder_layout.addWidget(self.raw_folder_path_label, 1) # 레이블 확장
        raw_folder_layout.addWidget(self.raw_clear_button)
        self.control_layout.addWidget(raw_folder_container) # 메인 레이아웃에 컨테이너 추가

        # RAW 이동 토글 버튼을 위한 컨테이너 위젯 및 레이아웃
        self.toggle_container = QWidget()
        self.toggle_layout = QHBoxLayout(self.toggle_container)
        self.toggle_layout.setContentsMargins(0, 10, 0, 0)
        
        # RAW 이동 토글 버튼
        self.raw_toggle_button = QCheckBox(LanguageManager.translate("JPG + RAW 이동"))
        self.raw_toggle_button.setChecked(True)  # 기본적으로 활성화 상태로 시작
        self.raw_toggle_button.toggled.connect(self.on_raw_toggle_changed) # 자동 상태 관리로 변경
        self.raw_toggle_button.setStyleSheet(f"""
            QCheckBox {{
                color: {ThemeManager.get_color('text')};
                padding: 2px;
            }}
            QCheckBox:disabled {{
                color: {ThemeManager.get_color('text_disabled')};
            }}
            QCheckBox::indicator {{
                width: 11px;
                height: 11px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {ThemeManager.get_color('accent')};
                border: 2px solid {ThemeManager.get_color('accent')};
                border-radius: 1px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: 2px solid {ThemeManager.get_color('border')};
                border-radius: 1px;
            }}
            QCheckBox::indicator:unchecked:hover {{
                border: 2px solid {ThemeManager.get_color('text_disabled')};
            }}
        """)
        
        # 토글 버튼을 레이아웃에 가운데 정렬로 추가
        self.toggle_layout.addStretch()
        self.toggle_layout.addWidget(self.raw_toggle_button)
        self.toggle_layout.addStretch()
        
        # 컨트롤 패널에 토글 컨테이너 추가
        self.control_layout.addWidget(self.toggle_container)
        
        # 구분선 추가
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        self.control_layout.addWidget(HorizontalLine())
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        
        # 분류 폴더 설정 영역
        self.setup_folder_selection_ui()
        
        # 구분선 추가
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20) - UIScaleManager.get("category_folder_vertical_spacing"))
        self.control_layout.addWidget(HorizontalLine())
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        
        # 이미지 줌 설정 UI 구성
        self.setup_zoom_ui()

        # 구분선 추가
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        self.control_layout.addWidget(HorizontalLine())
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        
        # Grid 설정 UI 구성 (Zoom UI 아래 추가)
        self.setup_grid_ui() # <<< 새로운 UI 설정 메서드 호출

        # 구분선 추가
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        self.control_layout.addWidget(HorizontalLine())
        
        # 파일 정보 UI 구성 (Grid UI 아래 추가)
        self.setup_file_info_ui()

        # 구분선 추가 (파일 정보 아래)
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        self.control_layout.addWidget(HorizontalLine())
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))

        # 이미지 카운터와 설정 버튼을 담을 컨테이너
        self.counter_settings_container = QWidget() # 컨테이너 생성만 하고 레이아웃은 별도 메서드에서 설정

        # 설정 버튼 초기화
        self.settings_button = QPushButton("⚙")
        settings_button_size = UIScaleManager.get("settings_button_size")
        self.settings_button.setFixedSize(settings_button_size, settings_button_size)
        self.settings_button.setCursor(Qt.PointingHandCursor)
        settings_font_size_style = settings_button_size - 15 # 폰트 크기는 UIScaleManager에 별도 정의하거나 버튼 크기에 비례하여 조정 가능
        self.settings_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                border-radius: 3px;
                font-size: {settings_font_size_style}px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.get_color('accent_hover')};
            }}
            QPushButton:pressed {{
                background-color: {ThemeManager.get_color('accent_pressed')};
            }}
        """)
        self.settings_button.clicked.connect(self.show_settings_popup)

        # 이미지/페이지 카운트 레이블 추가
        self.image_count_label = QLabel("- / -")
        self.image_count_label.setStyleSheet(f"color: {ThemeManager.get_color('text')};")

        # 초기 레이아웃 설정 (현재 grid_mode에 맞게)
        self.update_counter_layout()

        # 컨트롤 레이아웃에 컨테이너 추가
        self.control_layout.addWidget(self.counter_settings_container)

        # 세로 가운데 정렬을 위한 하단 Stretch
        self.control_layout.addStretch(1)

        logging.info(f"__init__: 컨트롤 패널 오른쪽 배치 = {getattr(self, 'control_panel_on_right', False)}") # 초기 상태 확인용

        if getattr(self, 'control_panel_on_right', False): # 로드된 값 확인 (없으면 False)
            self.splitter.addWidget(self.image_panel)   # 인덱스 0
            self.splitter.addWidget(self.control_panel) # 인덱스 1
        else:
            self.splitter.addWidget(self.control_panel) # 인덱스 0
            self.splitter.addWidget(self.image_panel)   # 인덱스 1
        
        # 화면 크기가 변경되면 레이아웃 다시 조정
        QGuiApplication.instance().primaryScreen().geometryChanged.connect(self.adjust_layout)

        # --- 초기 UI 상태 설정 추가 ---
        self.update_raw_toggle_state() # RAW 토글 초기 상태 설정
        self.update_folder_label_style(self.folder_path_label, self.current_folder) # JPG 폴더 레이블 초기 스타일
        self.update_folder_label_style(self.raw_folder_path_label, self.raw_folder) # RAW 폴더 레이블 초기 스타일
        self.update_match_raw_button_state() # <--- 추가: RAW 관련 버튼 초기 상태 업데이트      
        
        self.showMaximized()

        # 초기 레이아웃 설정
        QApplication.processEvents()
        self.adjust_layout()
        
        # 키보드 포커스 설정
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        
        # 이전 그리드 모드 저장 변수 추가 (ESC 키로 돌아가기 위함)
        self.previous_grid_mode = None
        
        # 더블클릭 줌 관련 변수 추가
        self.center_image = False  # 이미지를 가운데로 이동할지 여부 플래그
        self.center_on_click = False  # 클릭한 지점을 중심으로 줌할지 여부 플래그
        self.double_click_pos = QPoint(0, 0)  # 더블클릭 위치 저장

        # 스페이스바 처리를 위한 플래그 추가
        self.space_pressed = False

        # 애플리케이션 레벨 이벤트 필터 설치
        QApplication.instance().installEventFilter(self)

        # --- 프로그램 시작 시 상태 불러오기 (UI 로드 후 실행) ---
        # QTimer.singleShot(100, self.load_state)

        # --- 파일 목록 다이얼로그 인스턴스 변수 추가 ---
        self.file_list_dialog = None

        # 테마 관리자 초기화 및 콜백 등록
        ThemeManager.register_theme_change_callback(self.update_ui_colors)
        
        # 언어 및 날짜 형식 관련 콜백 등록
        LanguageManager.register_language_change_callback(self.update_ui_texts)
        DateFormatManager.register_format_change_callback(self.update_date_formats)

        # --- 초기 UI 상태 설정 추가 ---
        self.update_raw_toggle_state() # RAW 토글 초기 상태 설정
        self.update_folder_label_style(self.folder_path_label, self.current_folder) # JPG 폴더 레이블 초기 스타일
        self.update_folder_label_style(self.raw_folder_path_label, self.raw_folder) # RAW 폴더 레이블 초기 스타일

        # ExifTool 가용성 확인
        self.exiftool_available = False
        #self.exiftool_path = self.get_bundled_exiftool_path()  # 인스턴스 변수로 저장 
        self.exiftool_path = self.get_exiftool_path()  #수정 추가
        try:
            if Path(self.exiftool_path).exists():
                result = subprocess.run([self.exiftool_path, "-ver"], capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    version = result.stdout.strip()
                    logging.info(f"ExifTool 버전 {version} 사용 가능")
                    self.exiftool_available = True
                else:
                    logging.warning("ExifTool을 찾았지만 실행할 수 없습니다. 제한된 메타데이터 추출만 사용됩니다.")
            else:
                logging.warning(f"ExifTool을 찾을 수 없습니다: {self.exiftool_path}")
        except Exception as e:
            logging.error(f"ExifTool 확인 중 오류: {e}")

        # === EXIF 병렬 처리를 위한 스레드 및 워커 설정 ===
        self.exif_thread = QThread(self)
        self.exif_worker = ExifWorker(self.raw_extensions, self.exiftool_path, self.exiftool_available)
        self.exif_worker.moveToThread(self.exif_thread)

        # 시그널-슬롯 연결
        self.exif_worker.finished.connect(self.on_exif_info_ready)
        self.exif_worker.error.connect(self.on_exif_info_error)

        # 스레드 시작
        self.exif_thread.start()

        # EXIF 캐시
        self.exif_cache = {}  # 파일 경로 -> EXIF 데이터 딕셔너리
        self.current_exif_path = None  # 현재 처리 중인 EXIF 경로
        # === 병렬 처리 설정 끝 ===

    def get_system_memory_gb(self):
        """시스템 메모리 크기 확인 (GB)"""
        try:
            import psutil
            return psutil.virtual_memory().total / (1024 * 1024 * 1024)
        except:
            return 8.0  # 기본값 8GB
        
    def adjust_settings_for_system(self):
        """시스템 사양에 맞게 설정 조정"""
        # 메모리 크기에 따라 기능 조정
        if self.system_memory_gb < 12:
            # 8GB-12GB RAM: 최소 기능만 유지
            self.image_loader.cache_limit = 20  # 캐시 크기 제한
            self.reduce_background_tasks = True  # 백그라운드 작업 축소
        elif self.system_memory_gb < 24:
            # 12GB-24GB RAM: 적절한 균형
            self.image_loader.cache_limit = 40  # 캐시 크기 제한
            self.reduce_background_tasks = False  # 백그라운드 작업 정상 실행
        else:
            # 24GB 이상: 최대 성능
            self.image_loader.cache_limit = 80  # 캐시 크기 확장
            self.reduce_background_tasks = False  # 백그라운드 작업 정상 실행

    def check_memory_usage(self):
        """메모리 사용량 모니터링 및 필요시 최적화 조치"""
        try:
            import psutil
            memory_percent = psutil.virtual_memory().percent
            
            # 메모리 사용량이 위험 수준일 경우 (85% 이상)
            if memory_percent > 85:
                logging.warning(f"높은 메모리 사용량 감지 ({memory_percent}%): 캐시 정리 수행")
                self.perform_emergency_cleanup()
            
            # 메모리 사용량이 경고 수준일 경우 (75% 이상)
            elif memory_percent > 75:
                logging.warning(f"경고: 높은 메모리 사용량 ({memory_percent}%)")
                self.reduce_cache_size()
        except:
            pass  # psutil 사용 불가 등의 예외 상황 무시

    def perform_emergency_cleanup(self):
        """메모리 사용량이 위험 수준일 때 수행할 긴급 정리 작업"""
        # 1. 이미지 캐시 대폭 축소
        if hasattr(self.image_loader, 'cache'):
            cache_size = len(self.image_loader.cache)
            items_to_keep = min(10, cache_size)  # 최대 10개만 유지
            
            # 현재 표시 중인 이미지는 유지
            current_path = None
            if self.current_image_index >= 0 and self.current_image_index < len(self.image_files):
                current_path = str(self.image_files[self.current_image_index])
            
            # 불필요한 캐시 항목 제거
            keys_to_remove = []
            keep_count = 0
            
            for key in list(self.image_loader.cache.keys()):
                # 현재 표시 중인 이미지는 유지
                if key == current_path:
                    continue
                    
                keys_to_remove.append(key)
                keep_count += 1
                
                if keep_count >= cache_size - items_to_keep:
                    break
            
            # 실제 항목 제거
            for key in keys_to_remove:
                del self.image_loader.cache[key]
            
            logging.info(f"메모리 확보: 이미지 캐시에서 {len(keys_to_remove)}개 항목 제거")
        
        # 2. Fit 모드 캐시 초기화
        self.fit_pixmap_cache.clear()
        self.last_fit_size = (0, 0)
        
        # 3. 그리드 썸네일 캐시 정리
        self.grid_thumbnail_cache_2x2.clear()
        self.grid_thumbnail_cache_3x3.clear()
        
        # 4. 백그라운드 작업 일부 취소
        for future in self.active_thumbnail_futures:
            future.cancel()
        self.active_thumbnail_futures.clear()
        
        # 5. 가비지 컬렉션 강제 실행
        import gc
        gc.collect()

    def reduce_cache_size(self):
        """메모리 사용량이 경고 수준일 때 캐시 크기 축소"""
        # 이미지 캐시 일부 축소
        if hasattr(self.image_loader, 'cache'):
            cache_size = len(self.image_loader.cache)
            if cache_size > 20:  # 최소 크기 이상일 때만 축소
                items_to_remove = max(5, int(cache_size * 0.15))  # 약 15% 축소
                
                # 최근 사용된 항목 제외하고 제거
                keys_to_remove = list(self.image_loader.cache.keys())[:items_to_remove]
                
                for key in keys_to_remove:
                    del self.image_loader.cache[key]
                
                logging.info(f"메모리 관리: 이미지 캐시에서 {len(keys_to_remove)}개 항목 제거")


    def show_first_run_settings_popup(self):
        """프로그램 최초 실행 시 설정 팝업을 표시(좌우 패널 구조조)"""
        # 설정 팝업창 생성
        self.settings_popup = QDialog(self)
        self.settings_popup.setWindowTitle(LanguageManager.translate("초기 설정"))
        # ========== 좌우 패널 고려하여 최소 크기 조정 ==========
        self.settings_popup.setMinimumSize(550, 740) 
        
        # 제목 표시줄 다크 테마 적용 (Windows용)
        if sys.platform == "win32":
            try:
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                dwmapi = ctypes.WinDLL("dwmapi")
                dwmapi.DwmSetWindowAttribute.argtypes = [
                    ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int), ctypes.c_uint
                ]
                hwnd = int(self.settings_popup.winId())
                value = ctypes.c_int(1)
                dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
            except Exception as e:
                logging.error(f"설정 팝업창 제목 표시줄 다크 테마 적용 실패: {e}")
        
        # 다크 테마 배경 설정
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(ThemeManager.get_color('bg_primary')))
        self.settings_popup.setPalette(palette)
        self.settings_popup.setAutoFillBackground(True)
        
        # ========== 메인 레이아웃 변경: QVBoxLayout (전체) ==========
        # 전체 구조: 세로 (환영 메시지 - 가로(설정|단축키) - 확인 버튼)
        main_layout = QVBoxLayout(self.settings_popup)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        # =========================================================
        
        # 환영 메시지 추가
        self.settings_popup.welcome_label = QLabel(LanguageManager.translate("기본 설정을 선택해주세요."))
        self.settings_popup.welcome_label.setObjectName("first_run_welcome_label")
        self.settings_popup.welcome_label.setStyleSheet(f"color: {ThemeManager.get_color('text')}; font-size: 11pt;")
        self.settings_popup.welcome_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.settings_popup.welcome_label)
        main_layout.addSpacing(10)
        
        # ========== 상하 패널을 담을 QVBoxLayout 생성 ==========
        # QHBoxLayout 대신 QVBoxLayout 사용
        content_widget = QWidget()
        content_vbox_layout = QVBoxLayout(content_widget) # 이름 변경 및 타입 변경
        content_vbox_layout.setContentsMargins(0, 0, 0, 0)
        content_vbox_layout.setSpacing(15) # 상하 패널 사이 간격
        # =====================================================

        # ========== 상단 패널: 기존 설정 UI ==========
        settings_panel = QWidget()
        settings_panel_layout = QVBoxLayout(settings_panel)
        settings_panel_layout.setContentsMargins(0, 0, 0, 0)
        settings_panel_layout.setSpacing(0)

        settings_ui_widget = self.setup_settings_ui()
        settings_panel_layout.addWidget(settings_ui_widget)

        # 상단 패널을 content_vbox_layout에 추가
        content_vbox_layout.addWidget(settings_panel)
        # =============================================

        # ========== 상하 구분선 추가 ==========
        # VLine 대신 HLine 사용
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine) # 가로선으로 변경
        separator.setFrameShadow(QFrame.Sunken)
        # max-width 대신 max-height 사용
        separator.setStyleSheet(f"background-color: {ThemeManager.get_color('border')}; max-height: 1px;")
        content_vbox_layout.addWidget(separator) # 설정 패널 다음에 추가
        # =====================================

        # ========== 하단 패널: 단축키 안내 ==========
        shortcuts_panel = QWidget()
        shortcuts_panel_layout = QVBoxLayout(shortcuts_panel)
        shortcuts_panel_layout.setContentsMargins(0, 10, 0, 10) # 상하 약간의 여백
        shortcuts_panel_layout.setSpacing(10)

        # 단축키 제목
        shortcuts_title = QLabel(LanguageManager.translate("단축키 안내"))
        shortcuts_title.setStyleSheet(f"color: {ThemeManager.get_color('text')}; font-size: 11pt;")
        shortcuts_title.setAlignment(Qt.AlignCenter)
        shortcuts_title.setObjectName("shortcuts_title_label")
        shortcuts_panel_layout.addWidget(shortcuts_title)
        shortcuts_panel_layout.setSpacing(35)

        
        # 단축키 내용 레이블
        shortcuts_label = QLabel()
        shortcuts_label.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        shortcuts_label.setTextFormat(Qt.RichText) # HTML 형식 사용 가능
        shortcuts_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        shortcuts_label.setWordWrap(True) # 자동 줄바꿈
        shortcuts_label.setObjectName("shortcuts_content_label")

        # 단축키 텍스트 구성 함수 호출 (아래 2번 단계에서 정의)
        self._update_shortcut_label_text(shortcuts_label) # 초기 텍스트 설정
        shortcuts_panel_layout.addWidget(shortcuts_label)
        # shortcuts_panel_layout.addStretch(1) # 하단 여백 제거 또는 유지 (선택)

        # 하단 패널을 content_vbox_layout에 추가 (구분선 다음)
        content_vbox_layout.addWidget(shortcuts_panel)
        # =============================================

        # 메인 레이아웃에 상하 패널 영역 추가
        main_layout.addWidget(content_widget)
        main_layout.addStretch(1)  # 설정/단축키 영역과 확인 버튼 사이 여백
        
        # 확인 버튼 추가
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 10, 0, 0)
        
        self.settings_popup.confirm_button = QPushButton(LanguageManager.translate("확인"))
        
        if platform.system() == "Darwin":
            self.settings_popup.confirm_button.setStyleSheet("""
                QPushButton {
                    background-color: #444444;
                    color: #D8D8D8;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    min-width: 100px;
                }
                QPushButton:hover {
                    background-color: #555555;
                }
                QPushButton:pressed {
                    background-color: #222222;
                }
            """)
        else:
            # Windows/Linux 등
            self.settings_popup.confirm_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ThemeManager.get_color('bg_secondary')};
                    color: {ThemeManager.get_color('text')};
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    min-width: 100px;
                }}
                QPushButton:hover {{
                    background-color: {ThemeManager.get_color('accent_hover')};
                }}
                QPushButton:pressed {{
                    background-color: {ThemeManager.get_color('accent_pressed')};
                }}
            """)

        self.settings_popup.confirm_button.clicked.connect(self.settings_popup.accept)
        
        button_layout.addStretch(1)
        button_layout.addWidget(self.settings_popup.confirm_button)
        button_layout.addStretch(1)
        
        main_layout.addWidget(button_container)
        
        # 모달 팝업창으로 표시
        self.settings_popup.exec_()
        
        # 설정 적용 후 상태 저장 (첫 실행 시 기본 상태만 저장)
        self.save_state()

    def _build_shortcut_html_text(self):
        """현재 언어 설정에 맞춰 단축키 안내 HTML 텍스트 생성 (개별 p 태그와 margin 사용)"""
        shortcut_items = [
            "▪ WASD 또는 방향키: 사진 넘기기",
            "▪ Shift+WASD 또는 Shift+방향키: 그리드 페이지 넘기기",
            "▪ 1, 2, 3: 지정한 폴더로 이동",
            "▪ F1, F2, F3: 그리드 옵션 변경",
            "▪ Ctrl + Z: 파일 이동 취소",
            "▪ Ctrl + Y 또는 Ctrl + Shift + Z: 파일 이동 다시 실행",
            "▪ Delete: 프로그램 초기화"
        ]
        translated_items = [LanguageManager.translate(item) for item in shortcut_items]

        # ========== 각 항목을 <p> 태그로 감싸고 margin-bottom 추가 ==========
        # margin_value를 조절하여 원하는 줄 간격(픽셀 단위)을 만듭니다.
        margin_value = 5 # 예시: 8px 간격
        line_spacing_style = f"margin-bottom: {margin_value}px;"

        # 각 번역된 항목에 대해 <p> 태그와 스타일 적용
        translated_items_html = [f"<p style='{line_spacing_style}'>{item_text}</p>" for item_text in translated_items]

        # <p> 태그들을 하나로 합침 (별도의 <br> 없음)
        shortcuts_html = "".join(translated_items_html)
        # =================================================================

        return shortcuts_html

    def _build_shortcut_tooltip_text(self):
        """현재 언어 설정에 맞춰 단축키 확인 툴팁 문자열 생성 (줄바꿈: \\n)"""
        shortcut_items = [
            "▪ WASD 또는 방향키: 사진 넘기기",
            "▪ Shift+WASD 또는 Shift+방향키: 그리드 페이지 넘기기",
            "▪ 1, 2, 3: 지정한 폴더로 이동",
            "▪ F1, F2, F3: 그리드 옵션 변경",
            "▪ Ctrl + Z: 파일 이동 취소",
            "▪ Ctrl + Y 또는 Ctrl + Shift + Z: 파일 이동 다시 실행",
            "▪ Delete: 프로그램 초기화"
        ]
        # LanguageManager를 사용하여 각 항목 번역
        translated_items = [LanguageManager.translate(item) for item in shortcut_items]
        # '\n' 문자를 사용하여 각 항목을 연결
        tooltip_text = "\n".join(translated_items)
        return tooltip_text

    def _update_shortcut_label_text(self, label_widget):
        """주어진 라벨 위젯의 텍스트를 현재 언어의 단축키 안내로 업데이트"""
        if label_widget:
            label_widget.setText(self._build_shortcut_html_text())

    def update_counter_layout(self):
        """Grid 모드에 따라 카운터 레이블과 설정 버튼의 레이아웃을 업데이트"""
        # 기존 컨테이너 제거 (있을 경우)
        if hasattr(self, 'counter_settings_container'):
            # 컨트롤 레이아웃에서 컨테이너 제거
            self.control_layout.removeWidget(self.counter_settings_container)
            # 컨테이너 삭제 예약
            self.counter_settings_container.deleteLater()
        
        # 새 컨테이너 생성
        self.counter_settings_container = QWidget()
        
        # Grid Off 모드일 때는 중앙 정렬 (QGridLayout)
        if self.grid_mode == "Off":
            counter_settings_layout = QGridLayout(self.counter_settings_container)
            counter_settings_layout.setContentsMargins(0, 0, 0, 0)
            
            # 버튼: (0, 0) 위치, 왼쪽 정렬
            counter_settings_layout.addWidget(self.settings_button, 0, 0, Qt.AlignLeft)
            # 레이블: (0, 0) 위치에서 시작하여 1행, 모든 열(-1)에 걸쳐 중앙 정렬
            counter_settings_layout.addWidget(self.image_count_label, 0, 0, 1, -1, Qt.AlignCenter)
            # 버튼이 레이블 위에 보이도록 설정
            self.settings_button.raise_()
        
        # Grid 2x2 또는 3x3 모드일 때는 가로 정렬 (QHBoxLayout)
        else:
            counter_settings_layout = QHBoxLayout(self.counter_settings_container)
            counter_settings_layout.setContentsMargins(0, 0, 0, 0)
            counter_settings_layout.setSpacing(10)  # 버튼과 레이블 사이 간격
            
            # 순서대로 추가: 버튼 - 왼쪽 여백 - 레이블 - 오른쪽 여백
            counter_settings_layout.addWidget(self.settings_button)  # 1. 설정 버튼
            counter_settings_layout.addStretch(1)                   # 2. 왼쪽 Stretch
            counter_settings_layout.addWidget(self.image_count_label)  # 3. 카운트 레이블
            counter_settings_layout.addStretch(1)                   # 4. 오른쪽 Stretch
        
        # 파일 정보 UI 이후의 마지막 HorizontalLine을 찾아 그 아래에 삽입
        last_horizontal_line_index = -1
        for i in range(self.control_layout.count()):
            item = self.control_layout.itemAt(i)
            if item and isinstance(item.widget(), HorizontalLine):
                last_horizontal_line_index = i
        
        # 마지막 HorizontalLine 이후에 위젯 삽입
        if last_horizontal_line_index >= 0:
            insertion_index = last_horizontal_line_index + 2  # HorizontalLine + Spacing 다음
            self.control_layout.insertWidget(insertion_index, self.counter_settings_container)
        else:
            # HorizontalLine을 찾지 못한 경우 기본적으로 끝에 추가
            self.control_layout.addWidget(self.counter_settings_container)
        
        # 현재 카운트 정보 업데이트
        self.update_image_count_label()

    def start_background_image_preloading(self):
        """Grid Off 상태일 때 2x2 및 3x3 썸네일 백그라운드 생성을 시작합니다."""
        if self.grid_mode != "Off" or not self.image_files:
            return  # Grid 모드이거나 이미지 파일이 없으면 실행 안 함

        logging.info("백그라운드 그리드 썸네일 생성 시작...")

        # 이전 백그라운드 작업 취소
        for future in self.active_thumbnail_futures:
            future.cancel()
        self.active_thumbnail_futures.clear()

        # 현재 화면에 표시된 이미지와 그 주변 이미지만 우선적으로 처리
        current_index = self.current_image_index
        if current_index < 0:
            return
        
        # 시스템 메모리에 따라 프리로드 범위 조정
        preload_range = self.calculate_adaptive_preload_range()
        
        # 인접 이미지 우선 처리 (현재 이미지 ± preload_range)
        futures = []
        
        # 최대 프리로드 개수 제한
        max_preload = min(30, len(self.image_files))
        
        # 우선순위 이미지 (현재 이미지 주변)
        priority_indices = []
        for offset in range(-preload_range, preload_range + 1):
            idx = (current_index + offset) % len(self.image_files)
            if idx not in priority_indices:
                priority_indices.append(idx)
        
        # 우선순위 이미지 로드
        for i, idx in enumerate(priority_indices):
            if i >= max_preload:
                break
                
            img_path = str(self.image_files[idx])
            
            # 우선순위로 이미지 사전 로드 작업 제출
            future = self.grid_thumbnail_executor.submit(
                self._preload_image_for_grid, img_path
            )
            futures.append(future)

        # 나머지 이미지는 별도 작업으로 제출 (필요할 때만)
        if len(self.image_files) > max_preload and self.system_memory_gb >= 16:
            def delayed_preload():
                time.sleep(3)  # 3초 후에 시작
                remaining = [i for i in range(len(self.image_files)) if i not in priority_indices]
                # 메모리 상황에 따라 작업 추가
                for i in remaining[:20]:  # 최대 20개만 추가 프리로드
                    if getattr(self, '_running', True):  # 앱이 아직 실행 중인지 확인
                        try:
                            img_path = str(self.image_files[i])
                            self._preload_image_for_grid(img_path)
                        except:
                            pass
            
            # 낮은 우선순위로 지연 로드 작업 제출
            if self.system_memory_gb >= 16:  # 16GB 이상 시스템에서만 활성화
                delayed_future = self.grid_thumbnail_executor.submit(delayed_preload)
                futures.append(delayed_future)

        self.active_thumbnail_futures = futures
        logging.info(f"총 {len(futures)}개의 이미지 사전 로딩 작업 제출됨.")

    def calculate_adaptive_preload_range(self):
        """시스템 메모리에 따라 프리로딩 범위 결정"""
        try:
            import psutil
            system_memory_gb = psutil.virtual_memory().total / (1024 * 1024 * 1024)
            
            if system_memory_gb >= 32:
                return 5  # 앞뒤 각각 5개 이미지 (총 11개)
            elif system_memory_gb >= 16:
                return 3  # 앞뒤 각각 3개 이미지 (총 7개)
            else:
                return 2  # 앞뒤 각각 2개 이미지 (총 5개)
        except:
            return 2  # 기본값

    def _preload_image_for_grid(self, image_path):
        """
        주어진 이미지 경로의 원본 이미지를 ImageLoader 캐시에 미리 로드합니다.
        백그라운드 스레드에서 실행됩니다.
        """
        try:
            # ImageLoader를 사용하여 원본 이미지 로드 (EXIF 방향 처리 포함)
            # 반환값을 사용하지 않고, 로드 행위 자체로 ImageLoader 캐시에 저장되도록 함
            loaded = self.image_loader.load_image_with_orientation(image_path)
            if loaded and not loaded.isNull():
                # print(f"이미지 사전 로드 완료: {Path(image_path).name}") # 디버깅 로그
                return True
            else:
                # print(f"이미지 사전 로드 실패: {Path(image_path).name}")
                return False
        except Exception as e:
            logging.error(f"백그라운드 이미지 사전 로드 오류 ({Path(image_path).name}): {e}")
            return False

    def setup_settings_ui(self):
        """설정 UI 구성 (언어, 날짜 형식, 테마 설정)"""
        settings_container = QWidget()
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setSpacing(15)
        
        # === 언어 설정 (가로 배치) ===
        language_container = QWidget()
        language_layout = QHBoxLayout(language_container)
        language_layout.setContentsMargins(0, 5, 0, 5)
        
        language_title = QLabel(LanguageManager.translate("언어"))
        language_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        language_title.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        font = QFont(self.font())
        font.setPointSize(10)
        language_title.setFont(font)
        language_title.setMinimumWidth(200) # 좌측 텍스트라벨과 우측 설정UI 사이 간격  # 레이블 최소 너비 설정
        language_title.setObjectName("language_title_label")
        
        # 라디오 버튼 컨테이너
        radio_container = QWidget()
        radio_layout = QHBoxLayout(radio_container)
        radio_layout.setContentsMargins(0, 0, 0, 0)
        radio_layout.setSpacing(20)  # 버튼 사이 간격
        
        # 언어 라디오 버튼 그룹 생성
        self.language_group = QButtonGroup(self)
        
        # English 라디오 버튼 (왼쪽)
        self.english_radio = QRadioButton("English")
        
        # 한국어 라디오 버튼 (오른쪽)
        self.korean_radio = QRadioButton("한국어")
        
        # 버튼 그룹에 추가
        self.language_group.addButton(self.english_radio, 0)  # 영어 = 0
        self.language_group.addButton(self.korean_radio, 1)   # 한국어 = 1
        
        # 현재 언어 상태에 따라 선택
        current_lang = LanguageManager.get_current_language()
        if current_lang == "en":
            self.english_radio.setChecked(True)
        else:  # "ko"
            self.korean_radio.setChecked(True)
        
        # 라디오 버튼 스타일 설정
        radio_style = f"""
            QRadioButton {{
                color: {ThemeManager.get_color('text')};
                padding: 2px;
            }}
            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
            }}
            QRadioButton::indicator:checked {{
                background-color: #848484;
                border: 2px solid #848484;
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: 2px solid {ThemeManager.get_color('border')};
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked:hover {{
                border: 2px solid {ThemeManager.get_color('text_disabled')};
            }}
        """
        self.english_radio.setStyleSheet(radio_style)
        self.korean_radio.setStyleSheet(radio_style)
        
        # 이벤트 연결
        self.language_group.buttonClicked.connect(self.on_language_radio_changed)
        
        # 라디오 버튼을 컨테이너에 추가
        radio_layout.addWidget(self.english_radio)
        radio_layout.addWidget(self.korean_radio)
        radio_layout.addStretch(1)  # 우측 여백
        
        # 레이아웃에 위젯 추가 (가로 정렬)
        language_layout.addWidget(language_title)
        language_layout.addWidget(radio_container, 1)  # 1=stretch factor
        
        settings_layout.addWidget(language_container)
        
        # ========== 컨트롤 패널 위치 설정 추가 (시작) ==========
        panel_pos_container = QWidget()
        panel_pos_layout = QHBoxLayout(panel_pos_container)
        panel_pos_layout.setContentsMargins(0, 5, 0, 5)

        panel_pos_title = QLabel(LanguageManager.translate("컨트롤 패널"))
        panel_pos_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        panel_pos_title.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        # 기본 폰트 크기 사용 (main에서 설정됨)
        font = QFont(self.font()) # 현재 적용된 폰트 가져오기
        font.setPointSize(UIScaleManager.get("font_size")) # 명시적으로 설정
        panel_pos_title.setFont(font)
        panel_pos_title.setMinimumWidth(200) # 좌측 텍스트라벨과 우측 설정UI 사이 간격  # 다른 라벨과 너비 맞춤
        panel_pos_title.setObjectName("panel_pos_title_label")

        # 라디오 버튼 컨테이너
        panel_radio_container = QWidget()
        panel_radio_layout = QHBoxLayout(panel_radio_container)
        panel_radio_layout.setContentsMargins(0, 0, 0, 0)
        panel_radio_layout.setSpacing(20)

        # 라디오 버튼 그룹 생성
        self.panel_position_group = QButtonGroup(self) # 그룹 객체 저장

        # 라디오 버튼 생성
        self.panel_pos_left_radio = QRadioButton(LanguageManager.translate("좌측")) # 새 번역 키
        self.panel_pos_left_radio.setFont(self.font()) # 애플리케이션 폰트 사용
        self.panel_pos_right_radio = QRadioButton(LanguageManager.translate("우측")) # 새 번역 키
        self.panel_pos_right_radio.setFont(self.font()) # 애플리케이션 폰트 사용

        # 버튼 그룹에 추가 (좌측=0, 우측=1)
        self.panel_position_group.addButton(self.panel_pos_left_radio, 0)
        self.panel_position_group.addButton(self.panel_pos_right_radio, 1)

        # 현재 상태에 따라 초기 선택 설정
        if getattr(self, 'control_panel_on_right', False):
            self.panel_pos_right_radio.setChecked(True)
        else:
            self.panel_pos_left_radio.setChecked(True)

        # 라디오 버튼 스타일 설정 (기존 스타일 재사용)
        radio_style = f"""
            QRadioButton {{
                color: {ThemeManager.get_color('text')};
                padding: 2px;
            }}
            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
            }}
            QRadioButton::indicator:checked {{
                background-color: #848484;
                border: 2px solid #848484;
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: 2px solid {ThemeManager.get_color('border')};
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked:hover {{
                border: 2px solid {ThemeManager.get_color('text_disabled')};
            }}
        """
        self.panel_pos_left_radio.setStyleSheet(radio_style)
        self.panel_pos_right_radio.setStyleSheet(radio_style)

        # 이벤트 연결 (새로운 슬롯 _on_panel_position_changed 연결)
        self.panel_position_group.buttonClicked.connect(self._on_panel_position_changed)

        # 라디오 버튼을 컨테이너에 추가
        panel_radio_layout.addWidget(self.panel_pos_left_radio)
        panel_radio_layout.addWidget(self.panel_pos_right_radio)
        panel_radio_layout.addStretch(1)

        # 레이아웃에 위젯 추가
        panel_pos_layout.addWidget(panel_pos_title)
        panel_pos_layout.addWidget(panel_radio_container, 1)

        settings_layout.addWidget(panel_pos_container)
        # ========== 컨트롤 패널 위치 설정 추가 (끝) ==========



        # === 날짜 형식 설정 (가로 배치) ===
        date_format_container = QWidget()
        date_format_layout = QHBoxLayout(date_format_container)
        date_format_layout.setContentsMargins(0, 5, 0, 5)
        
        date_format_title = QLabel(LanguageManager.translate("날짜 형식"))
        date_format_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        date_format_title.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        date_format_title.setFont(font)
        date_format_title.setMinimumWidth(200) # 좌측 텍스트라벨과 우측 설정UI 사이 간격  # 레이블 최소 너비 설정
        date_format_title.setObjectName("date_format_title_label")
        
        self.date_format_combo = QComboBox()
        for format_code in DateFormatManager.get_available_formats():
            self.date_format_combo.addItem(DateFormatManager.get_format_display_name(format_code), format_code)
        
        # 현재 날짜 형식 선택
        current_format = DateFormatManager.get_current_format()
        index = self.date_format_combo.findData(current_format)
        if index >= 0:
            self.date_format_combo.setCurrentIndex(index)
        
        self.date_format_combo.setStyleSheet(self.generate_combobox_style())
        self.date_format_combo.currentIndexChanged.connect(self.on_date_format_changed)
        
        date_format_layout.addWidget(date_format_title)
        date_format_layout.addWidget(self.date_format_combo, 1)  # 1=stretch factor
        
        settings_layout.addWidget(date_format_container)
        
        # === 테마 설정 (가로 배치) ===
        theme_container = QWidget()
        theme_layout = QHBoxLayout(theme_container)
        theme_layout.setContentsMargins(0, 5, 0, 5)
        
        theme_title = QLabel(LanguageManager.translate("테마"))
        theme_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        theme_title.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        theme_title.setFont(font)
        theme_title.setMinimumWidth(200) # 좌측 텍스트라벨과 우측 설정UI 사이 간격  # 레이블 최소 너비 설정
        theme_title.setObjectName("theme_title_label")
        
        self.theme_combo = QComboBox()
        for theme_name in ThemeManager.get_available_themes():
            self.theme_combo.addItem(theme_name.capitalize())
        
        # 현재 테마 선택
        current_theme = ThemeManager.get_current_theme_name()
        index = self.theme_combo.findText(current_theme.capitalize())
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        
        self.theme_combo.setStyleSheet(self.generate_combobox_style())
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        
        theme_layout.addWidget(theme_title)
        theme_layout.addWidget(self.theme_combo, 1)  # 1=stretch factor
        
        settings_layout.addWidget(theme_container)
        # === 테마 설정 끝 ===
        # === RAW 처리 전략 설정 (가로 배치 + 라디오버튼) ===
        strategy_container = QWidget()
        strategy_layout = QHBoxLayout(strategy_container)
        strategy_layout.setContentsMargins(0, 5, 0, 5)

        strategy_title = QLabel(LanguageManager.translate("RAW 처리 방식 ⓘ"))
        strategy_title.setObjectName("strategy_title_label")
        strategy_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        strategy_title.setCursor(Qt.WhatsThisCursor)
        strategy_title.setToolTip(self._build_raw_strategy_tooltip_text())
        strategy_title.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        strategy_title.setFont(font)
        strategy_title.setMinimumWidth(200) # 좌측 텍스트라벨과 우측 설정UI 사이 간격  # 레이블 최소 너비 설정

        # 라디오 버튼 컨테이너
        strategy_options_container = QWidget()
        strategy_options_layout = QHBoxLayout(strategy_options_container)
        strategy_options_layout.setContentsMargins(0, 0, 0, 0)
        strategy_options_layout.setSpacing(15)  # 버튼 사이 간격

        # 전략 라디오 버튼 그룹 생성
        self.strategy_group = QButtonGroup(self)

        # 사용 가능한 전략 가져오기
        strategies = RawProcessingStrategyManager.get_available_strategies()
        self.strategy_radio_buttons = {}

        # 현재 선택된 전략 가져오기
        current_strategy = RawProcessingStrategyManager.get_current_strategy()

        # 라디오 버튼 생성 및 스타일 설정
        radio_style = f"""
            QRadioButton {{
                color: {ThemeManager.get_color('text')};
                padding: 2px;
            }}
            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
            }}
            QRadioButton::indicator:checked {{
                background-color: #848484;
                border: 2px solid #848484;
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: 2px solid {ThemeManager.get_color('border')};
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked:hover {{
                border: 2px solid {ThemeManager.get_color('text_disabled')};
            }}
        """

        for i, strategy in enumerate(strategies):
            strategy_name = RawProcessingStrategyManager.get_strategy_name(
                strategy, 
                LanguageManager.get_current_language()
            )
            radio_button = QRadioButton(strategy_name)
            radio_button.setStyleSheet(radio_style)
            
            # 버튼에 전략 코드 저장
            radio_button.setProperty("strategy_code", strategy)
            
            # 그룹에 추가
            self.strategy_group.addButton(radio_button, i)
            
            # 현재 전략과 일치하면 선택
            if strategy == current_strategy:
                radio_button.setChecked(True)
            
            # 딕셔너리에 저장 (나중에 접근하기 쉽게)
            self.strategy_radio_buttons[strategy] = radio_button
            
            # 레이아웃에 추가
            strategy_options_layout.addWidget(radio_button)

        # 이벤트 연결
        self.strategy_group.buttonClicked.connect(self.on_strategy_radio_changed)

        # 레이아웃에 위젯 추가
        strategy_layout.addWidget(strategy_title)
        strategy_layout.addWidget(strategy_options_container, 1)  # 1=stretch factor

        settings_layout.addWidget(strategy_container)
        # === RAW 처리 전략 설정 끝 ===


        # 하단 여백
        # settings_layout.addStretch(1)
        
        return settings_container

    def _build_raw_strategy_tooltip_text(self):
        """RAW 처리 전략에 대한 툴팁 텍스트 생성"""
        current_lang = LanguageManager.get_current_language()
        
        if current_lang == "en":
            return (
                "RAW files contain embedded JPG previews.\n"
                "Using these previews is faster, but they may have lower resolution than the original image.\n"
                "(Preview resolution varies by camera model.)\n"
                "This setting determines how aggressively to use preview images.\n"
                "Not using previews requires decoding RAW files, which is slower and may have compatibility issues with some cameras.\n\n"
                "▪ Ultra Fast: Always uses embedded preview for maximum speed regardless of resolution.\n"
                "▪ Fast (Recommended): Uses preview unless its resolution is very low.\n"
                "▪ High Quality (Recommended): Uses preview only when its resolution is sufficient. Otherwise decodes RAW.\n"
                "▪ Ultra Quality: Uses preview only when its resolution is nearly identical to the original. Otherwise decodes RAW."
            )
        else:  # Korean
            return (
                "RAW 파일에는 미리보기를 위한 JPG 이미지가 내장되어 있습니다.\n"
                "미리보기 이미지를 사용하면 작업 속도가 빠르지만 해상도가 원본보다 낮을 수 있습니다.\n"
                "(미리보기의 해상도는 카메라마다 다릅니다.)\n"
                "이 옵션은 얼마나 적극적으로 미리보기 이미지를 사용할 것인지를 결정합니다.\n"
                "미리보기를 사용하지 않으면 RAW 파일을 디코딩해야 하는데, 속도가 느리고 일부 카메라의 경우 호환성 문제가 있을 수 있습니다.\n\n"
                "▪ 매우 빠름: 해상도와 관계없이 내장 미리보기를 사용하여 최대 속도 제공.\n"
                "▪ 빠름(추천): 해상도가 아주 낮지 않은 한 미리보기 사용.\n"
                "▪ 고품질(추천): 미리보기 해상도가 충분할 때만 사용. 그렇지 않으면 RAW 디코딩.\n"
                "▪ 최고품질: 미리보기 해상도가 원본과 거의 같을 때만 사용. 그렇지 않으면 RAW 디코딩."
            )

    def on_strategy_radio_changed(self, button):
        """전략 라디오 버튼 변경 처리"""
        strategy_code = button.property("strategy_code")
        if strategy_code:
            RawProcessingStrategyManager.set_strategy(strategy_code)


    def on_theme_changed(self, theme_name):
        """테마 변경 시 호출되는 함수"""
        # 소문자로 변환 (ThemeManager에서는 소문자 키 사용)
        theme_name = theme_name.lower()
        ThemeManager.set_theme(theme_name)
        # 모든 UI가 update_ui_colors()를 통해 자동으로 업데이트됨

    def update_ui_colors(self):
        """테마 변경 시 모든 UI 요소의 색상을 업데이트"""
        # 모든 UI 요소의 스타일시트를 다시 설정
        self.update_button_styles()
        self.update_label_styles()
        self.update_folder_styles()
        
        # 설정 버튼 스타일 업데이트
        self.settings_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                border-radius: 3px;
                font-size: 20px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.get_color('accent_hover')};
            }}
            QPushButton:pressed {{
                background-color: {ThemeManager.get_color('accent_pressed')};
            }}
        """)
        
        # ... 기타 UI 요소 업데이트
        # 메시지 표시
        print(f"테마가 변경되었습니다: {ThemeManager.get_current_theme_name()}")
    
    def update_button_styles(self):
        """버튼 스타일을 현재 테마에 맞게 업데이트"""
        # 기본 버튼 스타일
        button_style = f"""
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                padding: 8px;
                border-radius: 1px;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.get_color('accent_hover')};
            }}
            QPushButton:pressed {{
                background-color: {ThemeManager.get_color('accent_pressed')};
            }}
            QPushButton:disabled {{
                background-color: {ThemeManager.get_color('bg_disabled')};
                color: {ThemeManager.get_color('text_disabled')};
                opacity: 0.7;
            }}
        """
            
        # 삭제 버튼 스타일
        delete_button_style = f"""
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                padding: 4px;
                border-radius: 1px;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.get_color('accent_hover')};
                color: white;
            }}
            QPushButton:pressed {{
                background-color: {ThemeManager.get_color('accent_pressed')};
                color: white;
            }}
            QPushButton:disabled {{
                background-color: {ThemeManager.get_color('bg_disabled')};
                color: {ThemeManager.get_color('text_disabled')};
            }}
        """
        
        # 라디오 버튼 스타일
        radio_style = f"""
            QRadioButton {{
                color: {ThemeManager.get_color('text')};
                padding: 2px;
            }}
            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
            }}
            QRadioButton::indicator:checked {{
                background-color: {ThemeManager.get_color('accent')};
                border: 2px solid {ThemeManager.get_color('accent')};
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: 2px solid {ThemeManager.get_color('border')};
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked:hover {{
                border: 2px solid {ThemeManager.get_color('text_disabled')};
            }}
        """
        
        # 메인 버튼들 스타일 적용
        if hasattr(self, 'load_button'):
            self.load_button.setStyleSheet(button_style)
        if hasattr(self, 'match_raw_button'):
            self.match_raw_button.setStyleSheet(button_style)
        
        # 삭제 버튼 스타일 적용
        if hasattr(self, 'jpg_clear_button'):
            self.jpg_clear_button.setStyleSheet(delete_button_style)
        if hasattr(self, 'raw_clear_button'):
            self.raw_clear_button.setStyleSheet(delete_button_style)
        
        # 폴더 버튼과 삭제 버튼 스타일 적용
        if hasattr(self, 'folder_buttons'):
            for button in self.folder_buttons:
                button.setStyleSheet(button_style)
        if hasattr(self, 'folder_delete_buttons'):
            for button in self.folder_delete_buttons:
                button.setStyleSheet(delete_button_style)
        
        # 줌 및 그리드 라디오 버튼 스타일 적용
        if hasattr(self, 'zoom_group'):
            for button in self.zoom_group.buttons():
                button.setStyleSheet(radio_style)
        if hasattr(self, 'grid_group'):
            for button in self.grid_group.buttons():
                button.setStyleSheet(radio_style)
                
    def resource_path(self, relative_path: str) -> str:
        """개발 환경과 PyInstaller 번들 환경 모두에서 리소스 경로 반환"""
        try:
            base = Path(sys._MEIPASS)
        except Exception:
            base = Path(__file__).parent
        return str(base / relative_path)

    def update_label_styles(self):
        """라벨 스타일을 현재 테마에 맞게 업데이트"""
        # 기본 라벨 스타일
        label_style = f"color: {ThemeManager.get_color('text')};"
        
        # 카운트 라벨 스타일 적용
        if hasattr(self, 'image_count_label'):
            self.image_count_label.setStyleSheet(label_style)
            
        # 파일 정보 라벨들 스타일 적용
        if hasattr(self, 'file_info_labels'):
            for label in self.file_info_labels:
                label.setStyleSheet(label_style)

        # 체크박스 스타일 적용
        checkbox_style = f"""
            QCheckBox {{
                color: {ThemeManager.get_color('text')};
                padding: 2px;
            }}
            QCheckBox:disabled {{
                color: {ThemeManager.get_color('text_disabled')};
            }}
            QCheckBox::indicator {{
                width: 11px;
                height: 11px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {ThemeManager.get_color('accent')};
                border: 2px solid {ThemeManager.get_color('accent')};
                border-radius: 1px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: 2px solid {ThemeManager.get_color('border')};
                border-radius: 1px;
            }}
            QCheckBox::indicator:unchecked:hover {{
                border: 2px solid {ThemeManager.get_color('text_disabled')};
            }}
            QCheckBox::indicator:disabled {{
                background-color: {ThemeManager.get_color('bg_disabled')};
                border: 2px solid {ThemeManager.get_color('text_disabled')};
            }}
        """
        
        # 미니맵 토글 및 RAW 토글 체크박스 스타일 업데이트
        if hasattr(self, 'minimap_toggle'):
            self.minimap_toggle.setStyleSheet(checkbox_style)
        if hasattr(self, 'raw_toggle_button'):
            self.raw_toggle_button.setStyleSheet(checkbox_style)
    
    def update_folder_styles(self):
        """폴더 관련 UI 요소의 스타일을 업데이트"""
        # 폴더 경로 레이블 스타일 업데이트
        if hasattr(self, 'folder_path_label'):
            self.update_jpg_folder_ui_state()
        if hasattr(self, 'raw_folder_path_label'):
            self.update_raw_folder_ui_state()
        
        # 카테고리 폴더 경로 레이블 스타일 업데이트
        if hasattr(self, 'folder_path_labels'):
            for i, label in enumerate(self.folder_path_labels):
                self.update_folder_label_style(label, self.target_folders[i] if hasattr(self, 'target_folders') else None)
    
    def show_settings_popup(self):
            """설정 버튼 클릭 시 호출되는 메서드, 설정 팝업을 표시 (상하 구조)"""
            # ──────────────────────────────
            # [0] 이미 팝업창이 열려있다면 앞으로 가져오기
            # ──────────────────────────────
            if hasattr(self, 'settings_popup') and self.settings_popup.isVisible():
                self.settings_popup.activateWindow()
                return

            # ──────────────────────────────
            # [1] 팝업창 생성 및 기본 속성 설정
            # ──────────────────────────────
            self.settings_popup = QDialog(self)
            self.settings_popup.setWindowTitle(LanguageManager.translate("설정 및 정보"))
            # UIScaleManager에서 설정 창 크기 가져오기
            popup_width = UIScaleManager.get("settings_popup_width", 785)
            popup_height = UIScaleManager.get("settings_popup_height", 910)
            self.settings_popup.setMinimumSize(popup_width, popup_height)

            # ── Windows용 다크 테마 제목 표시줄 설정
            if sys.platform == "win32":
                try:
                    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                    dwmapi = ctypes.WinDLL("dwmapi")
                    dwmapi.DwmSetWindowAttribute.argtypes = [
                        ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int), ctypes.c_uint
                    ]
                    hwnd = int(self.settings_popup.winId())
                    value = ctypes.c_int(1)
                    dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                                                ctypes.byref(value), ctypes.sizeof(value))
                except Exception as e:
                    logging.error(f"설정 팝업창 제목 표시줄 다크 테마 적용 실패: {e}")

            # ── 다크 테마 배경 색상 적용
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(ThemeManager.get_color('bg_primary')))
            self.settings_popup.setPalette(palette)
            self.settings_popup.setAutoFillBackground(True)

            # ──────────────────────────────
            # [2] 메인 레이아웃 설정 (수직)
            # ──────────────────────────────
            main_layout = QVBoxLayout(self.settings_popup)
            main_layout.setContentsMargins(15, 15, 15, 15)  # 바깥 여백
            info_donation_spacing = UIScaleManager.get("info_donation_spacing", 50)
            main_layout.setSpacing(info_donation_spacing)  # 각 패널 간 간격

            # ──────────────────────────────
            # [3] 상단 설정 패널 (설정 항목 + 단축키 안내)
            # ──────────────────────────────
            settings_section = QWidget()
            settings_layout = QVBoxLayout(settings_section)
            settings_layout.setContentsMargins(0, 0, 0, 0)
            settings_layout.setSpacing(UIScaleManager.get("settings_layout_vspace", 10))  # 설정 항목 간 간격

            settings_layout.addWidget(self.setup_settings_ui())
            
            # ── [3-1] 단축키 안내 수평 박스
            shortcut_info_container = QWidget()
            shortcut_info_hbox = QHBoxLayout(shortcut_info_container)
            shortcut_info_hbox.setContentsMargins(0, 0, 0, 0)
            shortcut_info_hbox.setSpacing(5)  # 라벨과 아이콘 사이 간격

            # 텍스트 라벨
            shortcut_info_label = QLabel(LanguageManager.translate("∗ 단축키 확인 ⓘ"))
            shortcut_info_label.setObjectName("shortcut_info_label")
            shortcut_info_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            shortcut_info_label.setCursor(Qt.WhatsThisCursor)
            shortcut_info_label.setToolTip(self._build_shortcut_tooltip_text())
            shortcut_info_label.setStyleSheet(
                f"color: {ThemeManager.get_color('text')}; padding-left: 8px;"
            )

            # 수평 레이아웃에 추가
            shortcut_info_hbox.addWidget(shortcut_info_label)
            #  shortcut_info_hbox.addStretch(1) # ⓘ 아이콘을 우측에서부터 밀어서 텍스트에 붙게 하는 역할

            # 상단 설정 레이아웃에 추가
            settings_layout.addWidget(shortcut_info_container)
            settings_layout.addSpacing(UIScaleManager.get("viewshortcuts_seperator", 15)) # 단축키 확인과 중간 구분선 사이 간격 조절
            settings_layout.addStretch(1)  # 설정 항목과 안내 사이 공간 확보

            # ──────────────────────────────
            # [4] 첫 번째 구분선 (상단과 중단 사이)
            # ──────────────────────────────
            separator1 = QFrame()
            separator1.setFrameShape(QFrame.HLine)
            separator1.setFrameShadow(QFrame.Sunken)
            separator1.setStyleSheet(
                f"background-color: {ThemeManager.get_color('border')}; max-height: 1px;"
            )

            # ──────────────────────────────
            # [5] 중단 정보 섹션
            # ──────────────────────────────
            info_section = QWidget()
            info_layout = QVBoxLayout(info_section)
            info_layout.setContentsMargins(0, 0, 0, 0)
            info_layout.setSpacing(0)

            # 앱 정보 텍스트
            info_text = self.create_translated_info_text()
            info_label = QLabel(info_text)
            info_label.setAlignment(Qt.AlignCenter)
            info_label.setStyleSheet(f"color: {ThemeManager.get_color('text')};")

            # 링크 활성화 설정 추가
            info_label.setOpenExternalLinks(True)
            info_label.setTextInteractionFlags(Qt.TextBrowserInteraction)

            info_layout.addWidget(info_label)
            info_layout.addSpacing(UIScaleManager.get("infotext_licensebutton", 40))  # 정보 텍스트와 버튼 사이 간격 추가

            # 오픈소스 라이선스 버튼 추가 (가운데 정렬을 위한 컨테이너 사용)
            license_button_container = QWidget()
            license_button_layout = QHBoxLayout(license_button_container)
            license_button_layout.setContentsMargins(0, 0, 0, 0)

            # 버튼 생성 및 스타일 설정
            licenses_button = QPushButton("Open Source Licenses")
            licenses_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ThemeManager.get_color('bg_secondary')};
                    color: {ThemeManager.get_color('text')};
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    min-width: 180px;
                }}
                QPushButton:hover {{
                    background-color: {ThemeManager.get_color('bg_hover')};
                }}
                QPushButton:pressed {{
                    background-color: {ThemeManager.get_color('bg_pressed')};
                }}
            """)
            licenses_button.setCursor(Qt.PointingHandCursor)  # 손가락 커서로 변경
            licenses_button.clicked.connect(self.show_licenses_popup)

            # 가운데 정렬을 위한 스트레치 추가
            license_button_layout.addStretch(1)
            license_button_layout.addWidget(licenses_button)
            license_button_layout.addStretch(1)

            # 레이아웃에 버튼 컨테이너 추가
            info_layout.addWidget(license_button_container)
            info_layout.addStretch(1)  # 정보 섹션 하단 여백 (기존 코드)
            

            # ──────────────────────────────
            # [6] 두 번째 구분선 (중단과 하단 사이)
            # ──────────────────────────────
            separator2 = QFrame()
            separator2.setFrameShape(QFrame.HLine)
            separator2.setFrameShadow(QFrame.Sunken)
            separator2.setStyleSheet(
                f"background-color: {ThemeManager.get_color('border')}; max-height: 1px;"
            )

            # ──────────────────────────────
            # [7] 하단 후원 섹션
            # ──────────────────────────────
            donation_section = QWidget()
            donation_layout = QVBoxLayout(donation_section)
            donation_layout.setContentsMargins(0, 0, 0, 0)  # 상단만 여백 10px
            
            # 현재 언어 설정 확인 
            current_language = LanguageManager.get_current_language()

            # 영어 설정일 때 결제 링크 표시
            if current_language == "en":
                # 커피 이모지를 후원 섹션 전체의 왼쪽에 배치하기 위한 컨테이너
                donation_content_container = QWidget()
                donation_content_layout = QHBoxLayout(donation_content_container)
                donation_content_layout.setContentsMargins(0, 0, 0, 0)
                
                # 커피 이모지 레이블 (세로로 중앙에 배치) - 이미지로 변경
                coffee_icon_path = self.resource_path("resources/coffee_icon.png")  # 이미지 파일 경로 지정
                coffee_icon = QPixmap(coffee_icon_path)
                coffee_emoji = QLabel()
                if not coffee_icon.isNull():
                    # 이미지 크기 조정 (적절한 크기로 조정)
                    coffee_icon = coffee_icon.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    coffee_emoji.setPixmap(coffee_icon)
                else:
                    # 이미지 로드 실패 시 텍스트로 대체
                    coffee_emoji.setText("☕")
                coffee_emoji.setFixedWidth(60)  # 이미지에 적절한 너비 설정
                coffee_emoji.setStyleSheet("padding-left: 10px;")  # 왼쪽에 10px 패딩 추가
                coffee_emoji.setAlignment(Qt.AlignCenter)  # 중앙 정렬

                # 결제 링크 컨테이너 (세로 레이아웃)
                links_container = QWidget()
                links_layout = QVBoxLayout(links_container)
                links_layout.setContentsMargins(0, 0, 0, 0)
                links_layout.setSpacing(UIScaleManager.get("donation_between_tworows", 30))  # 두 행 사이 간격
                
                # 첫 번째 행: 바이미어커피와 페이팔
                row1_container = QWidget()
                row1_layout = QHBoxLayout(row1_container)
                row1_layout.setContentsMargins(0, 0, 0, 0)  # 여백 제거
                
                # 바이미어커피 링크
                bmc_url = "https://buymeacoffee.com/ffamilist"
                qr_path = self.resource_path("resources/bmc_qr.png")
                bmc_label = QRLinkLabel("Buy Me a Coffee", bmc_url, qr_path, size=250)
                bmc_label.setAlignment(Qt.AlignCenter)
                
                # 페이팔 링크
                paypal_url = "https://paypal.me/ffamilist"
                qr_path = ""
                paypal_label = QRLinkLabel("PayPal", paypal_url, qr_path, size=250)
                paypal_label.setAlignment(Qt.AlignCenter)
                paypal_label.setToolTip("Click to go to PayPal")  # 툴팁 추가
                
                # 첫 번째 행에 링크 추가
                row1_layout.addWidget(bmc_label)
                row1_layout.addWidget(paypal_label)
                
                # 두 번째 행: 카카오페이와 네이버페이
                row2_container = QWidget()
                row2_layout = QHBoxLayout(row2_container)
                row2_layout.setContentsMargins(0, 0, 0, 0)  # 여백 제거
                
                # 카카오페이 링크
                kakaopay_url = ""
                qr_path = str(Path(__file__).parent / "resources" / "kakaopay_qr.png")
                kakaopay_label = QRLinkLabel("KakaoPay 🇰🇷", kakaopay_url, qr_path)
                kakaopay_label.setAlignment(Qt.AlignCenter)
                
                # 네이버페이 링크
                naverpay_url = ""
                qr_path = str(Path(__file__).parent / "resources" / "naverpay_qr.png")
                naverpay_label = QRLinkLabel("NaverPay 🇰🇷", naverpay_url, qr_path, size=250)
                naverpay_label.setAlignment(Qt.AlignCenter)
                
                # 두 번째 행에 링크 추가
                row2_layout.addWidget(kakaopay_label)
                row2_layout.addWidget(naverpay_label)
                
                # 링크 컨테이너에 두 행 추가
                links_layout.addWidget(row1_container)
                links_layout.addWidget(row2_container)
                
                # 최종 컨테이너에 커피 이모지와 링크 컨테이너 추가
                donation_content_layout.addWidget(coffee_emoji, 0, Qt.AlignVCenter)  # 수직 중앙 정렬
                donation_content_layout.addWidget(links_container, 1)  # 나머지 공간 차지
                
                # 후원 레이아웃에 최종 컨테이너 추가
                donation_layout.addWidget(donation_content_container)
            else:  # "ko"
                # 결제 링크를 담을 컨테이너 생성
                ko_payment_container = QWidget()
                ko_payment_layout = QHBoxLayout(ko_payment_container)
                ko_payment_layout.setContentsMargins(0, 0, 0, 0)  # 여백 제거
                
                # 커피 이모지 레이블 (세로로 중앙에 배치) - 이미지로 변경
                coffee_icon_path = str(Path(__file__).parent / "resources" / "coffee_icon.png")
                coffee_icon = QPixmap(coffee_icon_path)
                coffee_emoji = QLabel()
                if not coffee_icon.isNull():
                    coffee_icon = coffee_icon.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    coffee_emoji.setPixmap(coffee_icon)
                else:
                    coffee_emoji.setText("☕")
                coffee_emoji.setFixedWidth(60)
                coffee_emoji.setStyleSheet("padding-left: 10px;")  # 왼쪽에 10px 패딩 추가
                coffee_emoji.setAlignment(Qt.AlignCenter)
                
                # 결제 링크 컨테이너 (세로 레이아웃)
                links_container = QWidget()
                links_layout = QVBoxLayout(links_container)
                links_layout.setContentsMargins(0, 0, 0, 0)
                links_layout.setSpacing(UIScaleManager.get("donation_between_tworows", 30))  # 두 행 사이 간격
                
                # 첫 번째 행: 카카오페이와 네이버페이
                row1_container = QWidget()
                row1_layout = QHBoxLayout(row1_container)
                row1_layout.setContentsMargins(0, 0, 0, 0)  # 여백 제거
                
                # 카카오페이 링크
                kakaopay_url = ""
                qr_path = str(Path(__file__).parent / "resources" / "kakaopay_qr.png")
                kakaopay_label = QRLinkLabel(LanguageManager.translate("카카오페이"), kakaopay_url, qr_path)
                kakaopay_label.setAlignment(Qt.AlignCenter)
                
                # 네이버페이 링크
                naverpay_url = ""
                qr_path = str(Path(__file__).parent / "resources" / "naverpay_qr.png")
                naverpay_label = QRLinkLabel(LanguageManager.translate("네이버페이"), naverpay_url, qr_path, size=250)
                naverpay_label.setAlignment(Qt.AlignCenter)
                
                # 첫 번째 행에 링크 추가
                row1_layout.addWidget(kakaopay_label)
                row1_layout.addWidget(naverpay_label)
                
                # 두 번째 행: Buy Me a Coffee와 PayPal
                row2_container = QWidget()
                row2_layout = QHBoxLayout(row2_container)
                row2_layout.setContentsMargins(0, 0, 0, 0)  # 여백 제거
                
                # Buy Me a Coffee 링크
                bmc_url = "https://buymeacoffee.com/ffamilist"
                qr_path = str(Path(__file__).parent / "resources" / "bmc_qr.png")
                bmc_label = QRLinkLabel("Buy Me a Coffee", bmc_url, qr_path, size=250)
                bmc_label.setAlignment(Qt.AlignCenter)
                
                # PayPal 링크
                paypal_url = "https://paypal.me/ffamilist"
                qr_path = ""
                paypal_label = QRLinkLabel("PayPal", paypal_url, qr_path, size=250)
                paypal_label.setAlignment(Qt.AlignCenter)
                paypal_label.setToolTip("Click to go to PayPal")  # 툴팁 추가
                
                # 두 번째 행에 링크 추가
                row2_layout.addWidget(bmc_label)
                row2_layout.addWidget(paypal_label)
                
                # 링크 컨테이너에 두 행 추가
                links_layout.addWidget(row1_container)
                links_layout.addWidget(row2_container)
                
                # 최종 컨테이너에 커피 이모지와 링크 컨테이너 추가
                ko_payment_layout.addWidget(coffee_emoji, 0, Qt.AlignVCenter)  # 수직 중앙 정렬
                ko_payment_layout.addWidget(links_container, 1)  # 나머지 공간 차지
                
                # 후원 레이아웃에 최종 컨테이너 추가
                donation_layout.addWidget(ko_payment_container)

            donation_layout.addStretch(1)  # 하단 여백 확보

            # ──────────────────────────────
            # [8] 메인 레이아웃에 구성요소 순서대로 추가
            # ──────────────────────────────
            main_layout.addWidget(settings_section)  # 상단 설정 패널
            main_layout.addWidget(separator1)        # 첫 번째 구분선
            main_layout.addWidget(info_section)      # 중단 정보 패널
            main_layout.addWidget(separator2)        # 두 번째 구분선
            main_layout.addWidget(donation_section)  # 하단 후원 패널
            main_layout.addSpacing(UIScaleManager.get("bottom_space", 30))       # 하단 여백 확보

            # ──────────────────────────────
            # [9] 팝업 실행
            # ──────────────────────────────
            self.settings_popup.exec_()

    def create_translated_info_text(self):
        """현재 언어에 맞게 번역된 정보 텍스트를 생성하여 반환"""
        # UIScaleManager에서 여백 값 가져오기
        version_margin = UIScaleManager.get("info_version_margin", 40)
        paragraph_margin = UIScaleManager.get("info_paragraph_margin", 30) 
        bottom_margin = UIScaleManager.get("info_bottom_margin", 30)

        info_text = f"""
        <h2>PhotoSort</h2>
        <p style="margin-bottom: {version_margin}px;">Version: 25.04.26</p>
        <p>{LanguageManager.translate("조건 없이 자유롭게 사용할 수 있는 무료 소프트웨어입니다.")}</p>
        <p>{LanguageManager.translate("제작자 정보를 바꿔서 배포하지만 말아주세요.")}</p>
        <p style="margin-bottom: {paragraph_margin}px;">{LanguageManager.translate("이 프로그램이 마음에 드신다면, 커피 한 잔으로 응원해 주세요.")}</p>
        <p style="margin-bottom: {bottom_margin}px;">Copyright © 2025 ffamilist</p>
        <p>{LanguageManager.translate("피드백 및 업데이트 확인:")} <a href="https://medium.com/@ffamilist/photosort-simple-sorting-for-busy-dads-e9a4f45b03dc" style="color: #E2570D; text-decoration: none;">[EN]</a>&nbsp;&nbsp;<a href="https://blog.naver.com/ffamilist/223844618813" style="color: #E2570D; text-decoration: none;">[KR]</a></p>
        """
        return info_text

    def show_licenses_popup(self):
        """오픈소스 라이선스 정보를 표시하는 팝업"""
        # 다이얼로그 생성
        licenses_popup = QDialog(self)
        licenses_popup.setWindowTitle("Open Source Licenses Info")
        licenses_popup.setMinimumSize(950, 950)
        
        # Windows용 다크 테마 제목 표시줄 설정
        if sys.platform == "win32":
            try:
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                dwmapi = ctypes.WinDLL("dwmapi")
                dwmapi.DwmSetWindowAttribute.argtypes = [
                    ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int), ctypes.c_uint
                ]
                hwnd = int(licenses_popup.winId())
                value = ctypes.c_int(1)
                dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                                            ctypes.byref(value), ctypes.sizeof(value))
            except Exception as e:
                logging.error(f"라이선스 팝업창 제목 표시줄 다크 테마 적용 실패: {e}")
        
        # 다크 테마 배경 설정
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(ThemeManager.get_color('bg_primary')))
        licenses_popup.setPalette(palette)
        licenses_popup.setAutoFillBackground(True)
        
        # 메인 레이아웃 설정
        main_layout = QVBoxLayout(licenses_popup)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # QTextBrowser로 변경 - 마크다운 지원 및 텍스트 선택 가능
        scroll_content = QTextBrowser()
        scroll_content.setOpenExternalLinks(True)  # 외부 링크 열기 허용
        scroll_content.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {ThemeManager.get_color('bg_primary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                selection-background-color: #505050;
                selection-color: white;
            }}
        """)
        
        # HTML 스타일 추가 (마크다운 스타일 에뮬레이션)
        html_style = """
        <style>
            body { color: #D8D8D8; font-family: Arial, sans-serif; }
            h1 { font-size: 18px; margin-top: 20px; margin-bottom: 15px; color: #FFFFFF; }
            h2 { font-size: 16px; margin-top: 15px; margin-bottom: 10px; color: #FFFFFF; }
            p { margin: 8px 0; }
            ul { margin-left: 20px; }
            li { margin: 5px 0; }
            a { color: #42A5F5; text-decoration: none; }
            a:hover { text-decoration: underline; }
            hr { border: 0; height: 1px; background-color: #555555; margin: 20px 0; }
        </style>
        """
        
        # 라이선스 정보 HTML 변환
        licenses_html = f"""
        {html_style}
        <h1>Open Source Libraries and Licenses</h1>
        <p>This application uses the following open source libraries:</p>

        <h2>PySide6 (Qt for Python)</h2>
        <ul>
        <li><strong>License</strong>: LGPL-3.0</li>
        <li><strong>Website</strong>: <a href="https://www.qt.io/qt-for-python">https://www.qt.io/qt-for-python</a></li>
        <li>Qt for Python is the official Python bindings for Qt, providing access to the complete Qt framework.</li>
        </ul>

        <h2>Pillow (PIL Fork)</h2>
        <ul>
        <li><strong>License</strong>: HPND License (Historical Permission Notice and Disclaimer)</li>
        <li><strong>Website</strong>: <a href="https://pypi.org/project/pillow/">https://pypi.org/project/pillow/</a></li>
        <li>Pillow is the friendly PIL fork. PIL is the Python Imaging Library that adds image processing capabilities to your Python interpreter.</li>
        </ul>

        <h2>piexif</h2>
        <ul>
        <li><strong>License</strong>: MIT License</li>
        <li><strong>Website</strong>: <a href="https://github.com/hMatoba/Piexif">https://github.com/hMatoba/Piexif</a></li>
        <li>Piexif is a pure Python library for reading and writing EXIF data in JPEG and TIFF files.</li>
        </ul>

        <h2>rawpy</h2>
        <ul>
        <li><strong>License</strong>: MIT License</li>
        <li><strong>Website</strong>: <a href="https://github.com/letmaik/rawpy">https://github.com/letmaik/rawpy</a></li>
        <li>Rawpy provides Python bindings to LibRaw, allowing you to read and process camera RAW files.</li>
        </ul>

        <h2>LibRaw (used by rawpy)</h2>
        <ul>
        <li><strong>License</strong>: LGPL-2.1 or CDDL-1.0</li>
        <li><strong>Website</strong>: <a href="https://www.libraw.org/">https://www.libraw.org/</a></li>
        <li>LibRaw is a library for reading RAW files obtained from digital photo cameras.</li>
        </ul>

        <h2>ExifTool</h2>
        <ul>
        <li><strong>License</strong>: Perl's Artistic License / GNU GPL</li>
        <li><strong>Website</strong>: <a href="https://exiftool.org/">https://exiftool.org/</a></li>
        <li>ExifTool is a platform-independent Perl library and command-line application for reading, writing and editing meta information in a wide variety of files.</li>
        </ul>

        <h2>UIW Icon Kit</h2>
        <ul>
        <li><strong>License</strong>: MIT License</li>
        <li><strong>Website</strong>: <a href="https://iconduck.com/sets/uiw-icon-kit">https://iconduck.com/sets/uiw-icon-kit</a></li>
        <li>UIW Icon Kit is an Icon Set of 214 solid icons that can be used for both personal and commercial purposes.</li>
        </ul>

        <hr>

        <p>Each of these libraries is subject to its own license terms. Full license texts are available at the respective project websites. This software is not affiliated with or endorsed by any of these projects or their authors.</p>
        """
        
        # HTML 형식으로 내용 설정
        scroll_content.setHtml(licenses_html)
        
        # 확인 버튼 생성
        close_button = QPushButton(LanguageManager.translate("닫기"))
        close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.get_color('bg_hover')};
            }}
            QPushButton:pressed {{
                background-color: {ThemeManager.get_color('bg_pressed')};
            }}
        """)
        close_button.clicked.connect(licenses_popup.accept)
        
        # 버튼 컨테이너 (가운데 정렬)
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addStretch(1)
        button_layout.addWidget(close_button)
        button_layout.addStretch(1)
        
        # 메인 레이아웃에 위젯 추가
        main_layout.addWidget(scroll_content, 1)  # 스크롤 영역에 확장성 부여
        main_layout.addWidget(button_container)
        
        # 팝업 표시
        licenses_popup.exec_()

    def generate_combobox_style(self):
        """현재 테마에 맞는 콤보박스 스타일 생성"""
        return f"""
            QComboBox {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                padding: 5px;
                border-radius: 3px;
            }}
            QComboBox:hover {{
                background-color: #555555;
            }}
            QComboBox QAbstractItemView {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                selection-background-color: #505050;
                selection-color: {ThemeManager.get_color('text')};
            }}
        """

    def setup_dark_theme(self):
        """다크 테마 설정"""
        app = QApplication.instance()
        
        # 다크 팔레트 생성
        dark_palette = QPalette()
        
        # 다크 테마 색상 설정
        dark_palette.setColor(QPalette.Window, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Text, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        
        # 어두운 비활성화 색상
        dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(150, 150, 150))
        dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(150, 150, 150))
        
        # 팔레트 적용
        app.setPalette(dark_palette)
        
        # 스타일시트 추가 설정
        app.setStyleSheet(f"""
            QToolTip {{
                color: {ThemeManager.get_color('text')};
                background-color: {ThemeManager.get_color('bg_secondary')};
                border: 1px solid {ThemeManager.get_color('border')};
            }}
            QSplitter::handle {{
                background-color: {ThemeManager.get_color('bg_primary')};
            }}
            QSplitter::handle:horizontal {{
                width: 1px;
            }}
        """)
    
    def setup_dark_titlebar(self):
        """제목 표시줄에 다크 테마 적용 (Windows용)"""
        # Windows 환경에서만 작동
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes.wintypes import DWORD, BOOL, HKEY
                
                # Windows 10/11의 다크 모드를 위한 설정
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                
                # DwmSetWindowAttribute 함수 설정
                dwmapi = ctypes.WinDLL("dwmapi")
                dwmapi.DwmSetWindowAttribute.argtypes = [
                    ctypes.c_void_p,  # hwnd
                    ctypes.c_uint,    # dwAttribute
                    ctypes.POINTER(ctypes.c_int),  # pvAttribute
                    ctypes.c_uint     # cbAttribute
                ]
                
                # 다크 모드 활성화
                hwnd = int(self.winId())
                value = ctypes.c_int(1)
                dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    DWMWA_USE_IMMERSIVE_DARK_MODE,
                    ctypes.byref(value),
                    ctypes.sizeof(value)
                )
            except Exception as e:
                logging.error(f"제목 표시줄 다크 테마 적용 실패: {e}")
    
    def adjust_layout(self):
        """이미지 영역이 3:2 비율을 유지하면서 최대 크기를 갖도록 레이아웃 조정"""
        # 현재 창의 크기
        window_width = self.width()
        window_height = self.height()
        
        # 3:2 비율로 이미지 영역의 최대 크기 계산
        if window_width / window_height > 3/2:
            # 창이 더 넓은 경우: 높이 기준으로 너비 계산
            image_height = window_height
            image_width = int(image_height * 3/2)
        else:
            # 창이 더 좁은 경우: 너비 기준으로 높이 계산
            image_width = window_width
            image_height = int(image_width * 2/3)
        
        # 컨트롤 패널의 너비 계산
        control_width = window_width - image_width
        
        control_on_right = getattr(self, 'control_panel_on_right', False)

        if control_width > 0:
            if control_on_right:
                self.splitter.setSizes([image_width, control_width]) # 우측 배치 시 순서 변경
            else:
                self.splitter.setSizes([control_width, image_width]) # 좌측 배치 시 기존 순서
        else:
            # Fallback 처리도 순서 고려
            fallback_control_width = 200
            fallback_image_width = self.width() - fallback_control_width
            if fallback_image_width < 0: fallback_image_width = 0

            if control_on_right:
                self.splitter.setSizes([fallback_image_width, fallback_control_width])
            else:
                self.splitter.setSizes([fallback_control_width, fallback_image_width])
        
        # 이미지가 로드된 경우 이미지 크기도 조정
        if hasattr(self, 'current_image_index') and self.current_image_index >= 0:
            self.display_current_image()
    
    def resizeEvent(self, event):
        """창 크기 변경 이벤트 처리"""
        super().resizeEvent(event)
        self.adjust_layout()
        
        # 미니맵 위치도 업데이트
        self.update_minimap_position()
    
    def load_jpg_folder(self):
        """JPG 파일이 있는 폴더 선택 및 로드"""
        folder_path = QFileDialog.getExistingDirectory(
            self, LanguageManager.translate("JPG 파일이 있는 폴더 선택"), "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if folder_path:
            logging.info(f"JPG 폴더 선택: {folder_path}")
            self.clear_raw_folder()  # 새 JPG 폴더 지정 시 RAW 폴더 초기화

            if self.load_images_from_folder(folder_path):
                self.current_folder = folder_path
                self.folder_path_label.setText(folder_path)
                self.update_jpg_folder_ui_state() # UI 상태 업데이트
            else:
                # 로드 실패 시 상태 초기화 반영
                self.current_folder = ""
                # 실패 시 load_images_from_folder 내부에서도 호출하지만 여기서도 명시적으로 호출
                self.update_jpg_folder_ui_state()

    def on_match_raw_button_clicked(self):
        """ "JPG - RAW 연결" 또는 "RAW 불러오기" 버튼 클릭 시 호출 """
        if self.is_raw_only_mode:
            # 현재 RAW 모드이면 이 버튼은 동작하지 않아야 하지만, 안전 차원에서 추가
            print("RAW 전용 모드에서는 이 버튼이 비활성화되어야 합니다.")
            return
        elif self.image_files: # JPG가 로드된 상태 -> 기존 RAW 연결 로직
            self.load_raw_folder()
        else: # JPG가 로드되지 않은 상태 -> RAW 단독 로드 로직
            self.load_raw_only_folder()

    def load_images_from_folder(self, folder_path):
        """폴더에서 JPG 이미지 파일 목록 로드 및 유효성 검사"""
        if not folder_path:
            return False # 유효하지 않은 경로면 실패

        # 임시 이미지 목록 생성
        temp_image_files = []

        # JPG 파일 검색 - 대소문자 구분 없이 중복 방지
        target_path = Path(folder_path)

        # 하나의 패턴으로 통합하여 검색 (대소문자 구분 없이)
        all_jpg_files = list(target_path.glob("*.jpg")) + list(target_path.glob("*.jpeg"))

        # 파일명을 소문자로 변환하여 set으로 중복 제거 후 원본 경로 유지
        seen_files = set()
        for file_path in all_jpg_files:
            lower_name = file_path.name.lower()
            if lower_name not in seen_files:
                seen_files.add(lower_name)
                temp_image_files.append(file_path)

        # --- JPG 파일 유무 검사 추가 ---
        if not temp_image_files:
            logging.warning(f"선택한 폴더에 JPG 파일이 없습니다: {folder_path}")
            self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("경고"), LanguageManager.translate("선택한 폴더에 JPG 파일이 없습니다."))
            # UI 초기화
            self.image_files = [] # 내부 목록도 비움
            self.current_image_index = -1
            self.is_raw_only_mode = False # <--- 모드 해제
            self.image_label.clear() # 캔버스 비우기
            self.image_label.setStyleSheet("background-color: black;") # 검은 배경 유지
            self.setWindowTitle("PhotoSort") # 창 제목 초기화
            self.update_counters() # 카운터 업데이트
            self.update_file_info_display(None) # 파일 정보 초기화
            self.update_jpg_folder_ui_state() # 실패 시 X 버튼 비활성화
            self.update_match_raw_button_state() # <--- RAW 버튼 상태 업데이트
            self.load_button.setEnabled(True) # <--- JPG 버튼 활성화 (실패 시)
            self.update_raw_folder_ui_state() # <--- RAW 토글 상태 업데이트
            return False # 파일 로드 실패 반환
        # --- 검사 끝 ---

        # 파일이 있으면 내부 목록 업데이트 및 정렬
        self.image_files = sorted(temp_image_files)
        self.is_raw_only_mode = False # <--- JPG 로드 성공 시 RAW 전용 모드 해제

        # 그리드 상태 초기화
        self.grid_page_start_index = 0
        self.current_grid_index = 0

        # 이미지 캐시 초기화
        self.image_loader.clear_cache()

        # === Zoom과 Grid 모드 초기화 ===
        self.zoom_mode = "Fit"
        self.fit_radio.setChecked(True)
        
        self.grid_mode = "Off"
        self.grid_off_radio.setChecked(True)
        self.update_zoom_radio_buttons_state()

        # 이전 폴더의 백그라운드 작업이 있다면 취소
        for future in self.active_thumbnail_futures:
            future.cancel()
        self.active_thumbnail_futures.clear()

        # 로드된 이미지 수 출력 (디버깅용)
        logging.info(f"로드된 이미지 파일 수: {len(self.image_files)}")

        # 첫 번째 이미지 표시
        self.current_image_index = 0

        # 그리드 모드일 경우 일정 시간 후 강제 업데이트
        if self.grid_mode != "Off":
           QTimer.singleShot(100, self.force_grid_refresh)

        self.display_current_image() # 내부에서 카운터 및 정보 업데이트 호출됨

        self.update_jpg_folder_ui_state() # 성공 시 X 버튼 활성화
        self.update_match_raw_button_state() # <--- RAW 버튼 상태 업데이트 ("JPG - RAW 연결"로)
        self.update_raw_folder_ui_state() # <--- RAW 토글 상태 업데이트

        # --- Grid Off 상태이면 백그라운드 썸네일 생성 시작 ---
        if self.grid_mode == "Off":
            self.start_background_image_preloading()

        return True # 파일 로드 성공 반환
    
    def force_grid_refresh(self):
        """그리드 뷰를 강제로 리프레시"""
        if self.grid_mode != "Off":
            # 이미지 로더의 활성 작업 취소
            for future in self.image_loader.active_futures:
                future.cancel()
            self.image_loader.active_futures.clear()
            
            # 페이지 다시 로드 요청
            cells_per_page = 4 if self.grid_mode == "2x2" else 9
            self.image_loader.preload_page(self.image_files, self.grid_page_start_index, cells_per_page)
            
            # 그리드 UI 업데이트
            self.update_grid_view()    

    def load_image_with_orientation(self, file_path):
        """EXIF 방향 정보를 고려하여 이미지를 올바른 방향으로 로드 (캐시 활용)"""
        return self.image_loader.load_image_with_orientation(file_path)

    def apply_zoom_to_image(self):
        """현재 이미지에 확대 모드 적용 (Grid Off 모드에서만 사용)"""
        if self.grid_mode != "Off": return # Grid 모드에서는 이 함수 사용 안 함

        if not self.original_pixmap:
            return

        # 패닝 위치 초기화 여부 결정 (방향이 다를 때만)
        reset_panning = False
        if self.zoom_mode in ["100%", "200%"]:
            # 방향이 바뀌었는지 확인 (둘 다 None이 아니고 서로 다를 때)
            if (self.previous_image_orientation and self.current_image_orientation and 
                self.previous_image_orientation != self.current_image_orientation):
                reset_panning = True
                print(f"이미지 방향 변경 감지: {self.previous_image_orientation} -> {self.current_image_orientation}, 뷰포트 중앙 이동")

        # 방향이 다르거나 처음 로드되는 경우 패닝 위치 초기화
        if reset_panning or not self.previous_image_orientation:
            self.scroll_pos = QPoint(0, 0)
        
        # 이미지 표시 전에 캔버스 초기화 (중요)
        # 이 코드를 추가하여 이미지 갱신 문제 해결
        self.image_label.clear()
        self.image_label.setPixmap(QPixmap())  # 빈 픽스맵 설정으로 이전 이미지 완전히 제거

        if self.zoom_mode == "Fit":
            scaled_pixmap = self.high_quality_resize_to_fit(self.original_pixmap)
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setGeometry(
                (self.scroll_area.width() - scaled_pixmap.width()) // 2,
                (self.scroll_area.height() - scaled_pixmap.height()) // 2,
                scaled_pixmap.width(),
                scaled_pixmap.height()
            )
            self.image_container.setMinimumSize(1, 1) # Fit 모드에서는 컨테이너 크기 고정 안 함
        else:  # 100% or 200%
            # 확대 비율 계산
            zoom_percent = 1.0 if self.zoom_mode == "100%" else 2.0
            
            # 이미지와 뷰 크기 계산
            img_width = self.original_pixmap.width()
            img_height = self.original_pixmap.height()
            view_width = self.scroll_area.width()
            view_height = self.scroll_area.height()
            
            # 확대된 크기 계산
            zoomed_width = int(img_width * zoom_percent)
            zoomed_height = int(img_height * zoom_percent)
            
            # 100% <-> 200% 전환 시 화면 위치 유지를 위한 비율 계산
            maintain_position = False
            rel_x, rel_y = 0.5, 0.5  # 기본값은 중앙

            # 현재 이미지 위치 및 이전 줌 배율
            current_pos = self.image_label.pos()
            old_zoom = 1.0 if hasattr(self, 'last_zoom_mode') and self.last_zoom_mode == "100%" else 2.0

            # 이미지 위치 계산 로직
            if reset_panning or self.center_image or not hasattr(self, 'last_zoom_mode'):
                # 가운데 정렬 (Fit에서 전환 시 또는 방향 변경 시)
                new_x = (view_width - zoomed_width) // 2
                new_y = (view_height - zoomed_height) // 2
                
                # 이미지가 뷰보다 클 경우 조정 (항상 일부가 표시되게)
                if zoomed_width > view_width:
                    new_x = (view_width - zoomed_width) // 2
                if zoomed_height > view_height:
                    new_y = (view_height - zoomed_height) // 2
            elif self.center_on_click:
                # 더블클릭한 지점을 중심으로 (Fit에서 더블클릭으로 100% 전환 시)
                # Fit 모드에서의 이미지 크기 및 위치 계산
                scaled_pixmap = self.high_quality_resize_to_fit(self.original_pixmap)
                fit_width = scaled_pixmap.width()
                fit_height = scaled_pixmap.height()
                
                # 이미지 좌상단 위치 계산 (Fit 모드에서는 중앙 정렬)
                img_x = (view_width - fit_width) // 2
                img_y = (view_height - fit_height) // 2
                
                # 더블클릭 위치에서 이미지 내 상대 위치 계산
                click_x = self.double_click_pos.x() - img_x
                click_y = self.double_click_pos.y() - img_y
                
                if fit_width > 0 and fit_height > 0:
                    rel_x = click_x / fit_width
                    rel_y = click_y / fit_height
                    
                    # 클릭 위치가 이미지 외부일 경우 조정
                    rel_x = max(0, min(1, rel_x))
                    rel_y = max(0, min(1, rel_y))
                
                # 확대된 이미지에서 클릭 위치 계산
                target_x = int(rel_x * zoomed_width)
                target_y = int(rel_y * zoomed_height)
                
                # 클릭 위치가 화면 중앙에 오도록 이미지 위치 계산
                new_x = (view_width // 2) - target_x
                new_y = (view_height // 2) - target_y
                
                # 이미지 경계 보정
                if zoomed_width <= view_width:
                    new_x = (view_width - zoomed_width) // 2
                else:
                    new_x = min(0, max(view_width - zoomed_width, new_x))
                    
                if zoomed_height <= view_height:
                    new_y = (view_height - zoomed_height) // 2
                else:
                    new_y = min(0, max(view_height - zoomed_height, new_y))
            else:
                # 100% <-> 200% 전환 시 위치 유지
                if hasattr(self, 'last_zoom_mode') and self.last_zoom_mode in ["100%", "200%"]:
                    maintain_position = True
                    
                    # 현재 보고 있는 이미지 영역의 중심 계산
                    old_zoomed_width = int(img_width * old_zoom)
                    old_zoomed_height = int(img_height * old_zoom)
                    
                    # 현재 뷰포트에 보이는 이미지의 중심 상대 위치 구하기
                    view_center_x = view_width / 2 - current_pos.x()
                    view_center_y = view_height / 2 - current_pos.y()
                    
                    # 이미지 내의 상대 위치 계산 (0~1 범위)
                    rel_x = view_center_x / old_zoomed_width if old_zoomed_width > 0 else 0.5
                    rel_y = view_center_y / old_zoomed_height if old_zoomed_height > 0 else 0.5
                    
                    # 새 확대 비율에서의 위치 계산
                    target_x = int(rel_x * zoomed_width)
                    target_y = int(rel_y * zoomed_height)
                    
                    # 해당 위치가 화면 중앙에 오도록 계산
                    new_x = (view_width // 2) - target_x
                    new_y = (view_height // 2) - target_y
                    
                    # 위치 제한 (이미지가 화면 밖으로 나가지 않도록)
                    if zoomed_width > view_width:
                        new_x = min(0, max(view_width - zoomed_width, new_x))
                    else:
                        new_x = (view_width - zoomed_width) // 2
                        
                    if zoomed_height > view_height:
                        new_y = min(0, max(view_height - zoomed_height, new_y))
                    else:
                        new_y = (view_height - zoomed_height) // 2
                else:
                    # 기본 위치 (가운데)
                    new_x = (view_width - zoomed_width) // 2
                    new_y = (view_height - zoomed_height) // 2
                    
                    # 이미지가 뷰포트보다 크면 좌상단 표시
                    if zoomed_width > view_width:
                        new_x = 0
                    if zoomed_height > view_height:
                        new_y = 0
            
            # 확대 모드에 따른 이미지 설정
            if self.zoom_mode == "100%":
                self.image_label.setPixmap(self.original_pixmap)
            else:  # 200%
                scaled_pixmap = self.original_pixmap.scaled(
                    zoomed_width, zoomed_height, 
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
            
            # 이미지 위치 및 크기 설정
            self.image_label.setGeometry(new_x, new_y, zoomed_width, zoomed_height)
            self.image_container.setMinimumSize(zoomed_width, zoomed_height)

        # 현재 줌 모드 저장 (다음 전환 시 위치 유지 위해)
        self.last_zoom_mode = self.zoom_mode
        
        # 플래그 초기화
        self.center_image = False
        self.center_on_click = False

        # 미니맵 업데이트 (Grid Off이고 미니맵 활성화 시)
        if self.minimap_toggle.isChecked():
            self.toggle_minimap(True)

    def high_quality_resize_to_fit(self, pixmap):
        """고품질 이미지 리사이징 (Fit 모드용) - 메모리 최적화"""
        if not pixmap:
            return pixmap
                
        # 이미지 패널 크기 가져오기
        panel_width = self.image_panel.width()
        panel_height = self.image_panel.height()
        
        if panel_width <= 0 or panel_height <= 0:
            return pixmap
        
        # 크기가 같다면 캐시 확인
        current_size = (panel_width, panel_height)
        if self.last_fit_size == current_size and current_size in self.fit_pixmap_cache:
            return self.fit_pixmap_cache[current_size]
        
        # 이미지 크기
        img_width = pixmap.width()
        img_height = pixmap.height()
        
        # 이미지가 패널보다 크면 Qt의 네이티브 하드웨어 가속 렌더링을 사용한 리사이징
        if img_width > panel_width or img_height > panel_height:
            # 비율 계산
            ratio_w = panel_width / img_width
            ratio_h = panel_height / img_height
            ratio = min(ratio_w, ratio_h)
            
            # 새 크기 계산
            new_width = int(img_width * ratio)
            new_height = int(img_height * ratio)
            
            # 메모리 사용량 확인 (가능한 경우)
            large_image_threshold = 20000000  # 약 20MB (원본 크기가 큰 이미지)
            estimated_size = new_width * new_height * 4  # 4 바이트/픽셀 (RGBA)
            
            if img_width * img_height > large_image_threshold:
                # 대형 이미지는 메모리 최적화를 위해 단계적 축소
                try:
                    # 단계적으로 줄이는 방법 (품질 유지하면서 메모리 사용량 감소)
                    if ratio < 0.3:  # 크게 축소해야 하는 경우
                        # 중간 크기로 먼저 축소
                        temp_ratio = ratio * 2 if ratio * 2 < 0.8 else 0.8
                        temp_width = int(img_width * temp_ratio)
                        temp_height = int(img_height * temp_ratio)
                        
                        # 중간 크기로 먼저 변환
                        temp_pixmap = pixmap.scaled(
                            temp_width, 
                            temp_height,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                        
                        # 최종 크기로 변환
                        result_pixmap = temp_pixmap.scaled(
                            new_width,
                            new_height,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                        
                        # 중간 결과 명시적 해제
                        temp_pixmap = None
                    else:
                        # 한 번에 최종 크기로 변환
                        result_pixmap = pixmap.scaled(
                            new_width,
                            new_height,
                            Qt.KeepAspectRatio, 
                            Qt.SmoothTransformation
                        )
                except:
                    # 오류 발생 시 기본 방식으로 축소
                    result_pixmap = pixmap.scaled(
                        new_width,
                        new_height,
                        Qt.KeepAspectRatio, 
                        Qt.FastTransformation  # 메모리 부족 시 빠른 변환 사용
                    )
            else:
                # 일반 크기 이미지는 고품질 변환 사용
                result_pixmap = pixmap.scaled(
                    new_width, 
                    new_height, 
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                )
                
            # 캐시 업데이트
            self.fit_pixmap_cache[current_size] = result_pixmap
            self.last_fit_size = current_size
            
            return result_pixmap
        
        # 이미지가 패널보다 작으면 원본 사용
        return pixmap
    
    def image_mouse_press_event(self, event):
        """이미지 영역 마우스 클릭 이벤트 처리"""
        # 100% 또는 200% 모드에서만 패닝 활성화
        if self.zoom_mode in ["100%", "200%"]:
            if event.button() == Qt.LeftButton:
                # 패닝 상태 활성화
                self.panning = True
                self.pan_start_pos = event.position().toPoint()
                self.image_start_pos = self.image_label.pos()
                self.setCursor(Qt.ClosedHandCursor)
                
    
    def image_mouse_move_event(self, event):
        """이미지 영역 마우스 이동 이벤트 처리"""
        # 패닝 중이 아니면 이벤트 무시
        if not self.panning:
            return
            
        if self.original_pixmap:
            # 현재 시간 확인 (스로틀링)
            current_time = int(time.time() * 1000)
            if current_time - self.last_event_time < 8:  # ~120fps 제한 (8ms)
                return
            self.last_event_time = current_time
            
            # 마우스 이동 거리 계산 - 패닝 감도 2배 향상
            delta = (event.position().toPoint() - self.pan_start_pos) * 2
            
            # 새로운 이미지 위치 계산 (시작 위치 기준 - 절대 위치 기반)
            new_pos = self.image_start_pos + delta
            
            # 이미지 크기 가져오기
            if self.zoom_mode == "100%":
                img_width = self.original_pixmap.width()
                img_height = self.original_pixmap.height()
            else:  # 200%
                img_width = self.original_pixmap.width() * 2
                img_height = self.original_pixmap.height() * 2
            
            # 뷰포트 크기
            view_width = self.scroll_area.width()
            view_height = self.scroll_area.height()
            
            # 패닝 범위 계산 (이미지가 화면을 벗어나지 않도록)
            if img_width <= view_width:
                # 이미지가 뷰포트보다 작으면 가운데 정렬
                x_min = (view_width - img_width) // 2
                x_max = x_min
            else:
                # 이미지가 뷰포트보다 크면 자유롭게 패닝
                x_min = min(0, view_width - img_width)
                x_max = 0
            
            if img_height <= view_height:
                y_min = (view_height - img_height) // 2
                y_max = y_min
            else:
                y_min = min(0, view_height - img_height)
                y_max = 0
            
            # 범위 내로 제한
            new_x = max(x_min, min(x_max, new_pos.x()))
            new_y = max(y_min, min(y_max, new_pos.y()))
            
            # 이미지 위치 업데이트 - 실제 이동만 여기서 진행
            self.image_label.move(int(new_x), int(new_y))
            
            # 미니맵 뷰박스 업데이트 - 패닝 중에는 미니맵 업데이트 빈도 낮추기
            if current_time - getattr(self, 'last_minimap_update_time', 0) > 50:  # 20fps로 제한
                self.last_minimap_update_time = current_time
                if self.minimap_visible and self.minimap_widget.isVisible():
                    self.update_minimap()
    
    def image_mouse_release_event(self, event):
        """이미지 영역 마우스 릴리스 이벤트 처리"""
        if event.button() == Qt.LeftButton and self.panning:
            # 패닝 상태 해제
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
            
            # 미니맵 최종 업데이트
            if self.minimap_visible and self.minimap_widget.isVisible():
                self.update_minimap()
    
    def open_folder_in_explorer(self, folder_path):
        """폴더 경로를 윈도우 탐색기에서 열기"""
        if not folder_path or folder_path == LanguageManager.translate("폴더를 선택하세요"):
            return
        
        try:
            if sys.platform == 'win32':
                os.startfile(folder_path)
            elif sys.platform == 'darwin':  # macOS
                subprocess.run(['open', folder_path])
            else:  # Linux
                subprocess.run(['xdg-open', folder_path])
        except Exception as e:
            logging.error(f"폴더 열기 실패: {e}")
    
    def load_raw_folder(self):
        """RAW 파일이 있는 폴더 선택 및 매칭 (JPG 로드 상태에서만 호출됨)"""
        # JPG 파일이 로드되었는지 확인 (이 함수는 JPG 로드 상태에서만 호출되어야 함)
        if not self.image_files or self.is_raw_only_mode:
             # is_raw_only_mode 체크 추가
            self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("경고"), LanguageManager.translate("먼저 JPG 파일을 불러와야 합니다."))
            return

        folder_path = QFileDialog.getExistingDirectory(
            self, LanguageManager.translate("RAW 파일이 있는 폴더 선택"), "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if folder_path:
            # RAW 폴더 경로 업데이트는 match_raw_files 내부에서 매칭 성공 시 수행
            self.match_raw_files(folder_path)

    def load_raw_only_folder(self):
        """ RAW 파일만 로드하는 기능 """
        folder_path = QFileDialog.getExistingDirectory(
            self, LanguageManager.translate("RAW 파일이 있는 폴더 선택"), "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if folder_path:
            target_path = Path(folder_path)
            temp_raw_file_list = []

            # RAW 파일 검색
            for ext in self.raw_extensions:
                temp_raw_file_list.extend(target_path.glob(f'*{ext}'))
                temp_raw_file_list.extend(target_path.glob(f'*{ext.upper()}')) # 대문자 확장자도 고려

            # 중복 제거 및 정렬
            unique_raw_files = sorted(list(set(temp_raw_file_list)))

            if not unique_raw_files:
                self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("경고"), LanguageManager.translate("선택한 폴더에 RAW 파일이 없습니다."))
                # UI 초기화 (기존 JPG 로드 실패와 유사하게)
                self.image_files = []
                self.current_image_index = -1
                self.image_label.clear()
                self.image_label.setStyleSheet("background-color: black;")
                self.setWindowTitle("PhotoSort")
                self.update_counters()
                self.update_file_info_display(None)
                # RAW 관련 UI 업데이트
                self.raw_folder = ""
                self.is_raw_only_mode = False # 실패 시 모드 해제
                self.update_raw_folder_ui_state() # raw_folder_path_label 포함
                self.update_match_raw_button_state() # 버튼 텍스트 원복
                # JPG 버튼 활성화
                self.load_button.setEnabled(True)
                return

            # --- RAW 로드 성공 시 ---
            print(f"로드된 RAW 파일 수: {len(unique_raw_files)}")
            self.image_files = unique_raw_files # 메인 리스트를 RAW 파일로 교체
            
            # 명시적으로 첫 번째 RAW 파일로 전략 결정 - 개선
        
            
            if self.image_files:
                first_raw_file = str(self.image_files[0])
                
                # 전략 재설정을 위해 초기화 플래그 리셋
                with ImageLoader._strategy_lock:
                    ImageLoader._strategy_initialized = False
                    ImageLoader._global_raw_strategy = "undetermined"
                    logging.info("새 RAW 폴더 로드: 전역 전략 초기화됨")
                
                # 이제 전략 결정 로직 호출
                logging.warning(f"json 경로! {first_raw_file}")
                logging.warning(f"json 경로! {first_raw_file}")
                logging.warning(f"json 경로! {first_raw_file}")

                self.image_loader.determine_raw_strategy(first_raw_file)
                logging.warning(f"첫 번째 RAW 파일 ({Path(first_raw_file).name})로 전략 결정 완료")
            
            self.raw_folder = folder_path # RAW 폴더 경로 저장
            self.is_raw_only_mode = True # RAW 전용 모드 활성화

            # 기존 JPG/RAW 연결 정보 초기화
            self.current_folder = ""
            self.raw_files = {}
            self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))
            self.update_jpg_folder_ui_state() # JPG UI 초기화

            # RAW UI 업데이트
            self.raw_folder_path_label.setText(folder_path)
            self.update_raw_folder_ui_state() # X버튼 활성화, 토글 버튼 On+비활성화 처리
            self.update_match_raw_button_state()

            # JPG 불러오기 버튼 비활성화
            self.load_button.setEnabled(False)

            # 그리드 상태 초기화
            self.grid_page_start_index = 0
            self.current_grid_index = 0

            # 이미지 캐시 초기화
            self.image_loader.clear_cache()

            # === Zoom과 Grid 모드 초기화 ===
            self.zoom_mode = "Fit"
            self.fit_radio.setChecked(True)
            
            self.grid_mode = "Off"
            self.grid_off_radio.setChecked(True)
            self.update_zoom_radio_buttons_state()

            # 첫 번째 RAW 이미지 표시
            self.current_image_index = 0
            self.display_current_image() # 내부에서 카운터, 정보, 제목 업데이트 호출

            # Grid Off 상태이면 백그라운드 썸네일 생성 시작
            if self.grid_mode == "Off":
                self.start_background_image_preloading()

    def match_raw_files(self, folder_path): # folder_path 인자 받도록 수정
        """JPG 파일과 RAW 파일 매칭 및 결과 처리"""
        if not folder_path or not self.image_files:
            return

        # RAW 파일 딕셔너리 초기화
        temp_raw_files = {} # 임시 딕셔너리 사용

        # 현재 로드된 모든 JPG 파일의 기본 이름(확장자 제외) 획득
        jpg_filenames = {jpg_path.stem: jpg_path for jpg_path in self.image_files}
        # RAW 폴더의 모든 파일 검사
        matched_count = 0
        raw_folder_path = Path(folder_path)

        # 모든 파일 검사
        for file_path in raw_folder_path.iterdir():
            if not file_path.is_file():
                continue

            # 확장자가 RAW 확장자인지 확인
            if file_path.suffix.lower() in self.raw_extensions:
                base_name = file_path.stem

                # 동일한 이름의 JPG 파일이 있는지 확인
                if base_name in jpg_filenames:
                    temp_raw_files[base_name] = file_path
                    matched_count += 1

        # --- 매칭 결과 검사 추가 ---
        if matched_count == 0:
            self.show_themed_message_box(QMessageBox.Information, LanguageManager.translate("정보"), LanguageManager.translate("선택한 RAW 폴더에서 매칭되는 파일을 찾을 수 없습니다."))
            # 매칭 실패 시 UI 상태 업데이트
            self.raw_folder = "" # 내부 경로도 클리어
            self.raw_files = {}
            self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로")) # 레이블 리셋
            self.update_raw_folder_ui_state() # X 버튼, 레이블 스타일, 토글 업데이트
            return
        # --- 검사 끝 ---

        # 매칭 성공 시 실제 변수 업데이트
        self.raw_folder = folder_path
        self.raw_files = temp_raw_files
        self.raw_folder_path_label.setText(folder_path)

        # --- RAW 파일 매칭 시 자동으로 이동 체크박스 ON 설정 ---
        self.move_raw_files = True

        # --- RAW 폴더 레이블 스타일 및 X 버튼/토글 상태 업데이트 추가 ---
        self.update_raw_folder_ui_state() # 성공 시 X 버튼, 레이블 스타일, 토글 업데이트
        self.update_match_raw_button_state()

        # 매칭 결과 팝업 표시 (매칭된 경우에만)
        self.show_themed_message_box(QMessageBox.Information, LanguageManager.translate("RAW 파일 매칭 결과"), f"{LanguageManager.translate('RAW 파일이 매칭되었습니다.')}\n{matched_count} / {len(self.image_files)}")
    
    def get_bundled_exiftool_path(self):
        """애플리케이션 폴더 구조에서 ExifTool 경로 찾기"""
        # 애플리케이션 기본 디렉토리 확인
        if getattr(sys, 'frozen', False):
            # PyInstaller로 패키징된 경우
            app_dir = Path(sys.executable).parent
        else:
            # 일반 스크립트로 실행된 경우
            app_dir = Path(__file__).parent
        
        # 1. 먼저 새 구조의 exiftool 폴더 내에서 확인
        exiftool_path = app_dir / "exiftool" / "exiftool.exe"
        if exiftool_path.exists():
            # print(f"ExifTool 발견: {exiftool_path}")
            logging.info(f"ExifTool 발견: {exiftool_path}")
            return str(exiftool_path)
        
        # 2. 이전 구조의 resources 폴더에서 확인 (호환성 유지)
        exiftool_path = app_dir / "resources" / "exiftool.exe"
        if exiftool_path.exists():
            print(f"ExifTool 발견(레거시 경로): {exiftool_path}")
            logging.info(f"ExifTool 발견(레거시 경로): {exiftool_path}")
            return str(exiftool_path)
        
        # 3. 애플리케이션 기본 폴더 내에서 직접 확인
        exiftool_path = app_dir / "exiftool.exe" 
        if exiftool_path.exists():
            # print(f"ExifTool 발견(기본 폴더): {exiftool_path}")
            logging.info(f"ExifTool 발견: {exiftool_path}")
            return str(exiftool_path)
        
        # 4. PATH 환경변수에서 검색 가능하도록 이름만 반환 (선택적)
        logging.warning("ExifTool을 찾을 수 없습니다. PATH에 있다면 기본 이름으로 시도합니다.")
        return "exiftool.exe"

    #추가 수정
    def get_exiftool_path(self) -> str:
        """운영체제별로 exiftool 경로를 반환합니다."""
        system = platform.system()
        if system == "Darwin":
            # macOS 번들 내부 exiftool 사용
            logging.info(f"맥 전용 exiftool사용")
            bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.argv[0]))
            return os.path.join(bundle_dir, "exiftool")
        elif system == "Windows":
            # Windows: 기존 get_bundled_exiftool_path 로 경로 확인
            return self.get_bundled_exiftool_path()
        else:
            # 기타 OS: 시스템 PATH에서 exiftool 호출
            return "exiftool"

    def show_themed_message_box(self, icon, title, text, buttons=QMessageBox.Ok, default_button=QMessageBox.NoButton):
        """스타일 및 제목 표시줄 다크 테마가 적용된 QMessageBox 표시"""
        message_box = QMessageBox(self)
        message_box.setWindowTitle(title)
        message_box.setText(text)
        message_box.setIcon(icon)
        message_box.setStandardButtons(buttons)
        message_box.setDefaultButton(default_button)

        # 메시지 박스 내용 다크 테마 스타일 적용
        message_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {ThemeManager.get_color('bg_primary')};
                color: {ThemeManager.get_color('text')};
            }}
            QLabel {{
                color: {ThemeManager.get_color('text')};
            }}
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: none;
                padding: 8px;
                border-radius: 4px;
                min-width: 60px;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.get_color('accent_hover')};
            }}
            QPushButton:pressed {{
                background-color: {ThemeManager.get_color('accent_pressed')};
            }}
        """)

        # 제목 표시줄 다크 테마 적용 (Windows용)
        if ctypes and sys.platform == "win32":
            try:
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                dwmapi = ctypes.WinDLL("dwmapi")
                dwmapi.DwmSetWindowAttribute.argtypes = [
                    ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int), ctypes.c_uint
                ]
                hwnd = int(message_box.winId()) # message_box의 winId 사용
                value = ctypes.c_int(1)
                dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
            except Exception as e:
                logging.error(f"MessageBox 제목 표시줄 다크 테마 적용 실패: {e}")

        return message_box.exec_() # 실행하고 결과 반환
    
    def open_raw_folder_in_explorer(self, folder_path):
        """RAW 폴더 경로를 윈도우 탐색기에서 열기"""
        if not folder_path or folder_path == LanguageManager.translate("RAW 폴더를 선택하세요"):
            return
        
        try:
            if sys.platform == 'win32':
                os.startfile(folder_path)
            elif sys.platform == 'darwin':  # macOS
                subprocess.run(['open', folder_path])
            else:  # Linux
                subprocess.run(['xdg-open', folder_path])
        except Exception as e:
            logging.error(f"폴더 열기 실패: {e}")

    def on_raw_toggle_changed(self, checked):
        """RAW 이동 토글 상태 변경 처리"""
        self.move_raw_files = checked
        print(f"RAW 파일 이동 설정: {'활성화' if checked else '비활성화'}")
    
    def setup_folder_selection_ui(self):
        """분류 폴더 설정 UI 구성"""
        self.folder_buttons = []
        self.folder_path_labels = []
        self.folder_delete_buttons = []

        # ========== UIScaleManager 값 가져오기 ==========
        button_padding = UIScaleManager.get("button_padding")
        button_min_height = UIScaleManager.get("button_min_height")
        folder_label_padding = UIScaleManager.get("folder_label_padding")
        delete_button_width = UIScaleManager.get("delete_button_width")
        folder_container_spacing = UIScaleManager.get("folder_container_spacing", 5)

        # FolderPathLabel 높이 계산 (한 번만 계산)
        # FolderPathLabel에 설정될 폰트 기준 (여기서는 기본값 Arial 10 사용 가정)
        # 만약 FolderPathLabel의 폰트가 다르다면 해당 폰트로 QFontMetrics 생성해야 함
        temp_label_font = QFont("Arial", 10) # FolderPathLabel의 폰트와 동일해야 함
        fm_label = QFontMetrics(temp_label_font)
        label_line_height = fm_label.height()
        label_fixed_height = (label_line_height * 2) + folder_label_padding

        for i in range(3):
            folder_container = QWidget()
            folder_layout = QHBoxLayout(folder_container)
            folder_layout.setContentsMargins(0, 0, 0, 0)
            # ========== UIScaleManager 적용 ==========
            folder_layout.setSpacing(folder_container_spacing)

            folder_button = QPushButton(f"{i+1}")
            folder_button.setFont(self.font()) # 애플리케이션 기본 폰트 사용
            # ========== UIScaleManager 적용 ==========
            folder_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ThemeManager.get_color('bg_secondary')};
                    color: {ThemeManager.get_color('text')};
                    border: none;
                    padding: {button_padding}px;
                    border-radius: 1px;
                    min-height: {button_min_height}px;
                }}
                QPushButton:hover {{ background-color: {ThemeManager.get_color('accent_hover')}; }}
                QPushButton:pressed {{ background-color: {ThemeManager.get_color('accent_pressed')}; }}
            """)
            folder_button.clicked.connect(lambda checked=False, idx=i: self.select_category_folder(idx))
            # ========== UIScaleManager 적용 ==========
            # 너비는 delete 버튼과 맞추거나, 필요시 별도 키 정의
            folder_button.setFixedWidth(delete_button_width)
            folder_button.setFixedHeight(label_fixed_height) # 레이블 높이와 동일하게

            delete_button = QPushButton("X")
            delete_button.setFont(self.font()) # 애플리케이션 기본 폰트 사용
            # ========== UIScaleManager 적용 ==========
            delete_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ThemeManager.get_color('bg_secondary')};
                    color: {ThemeManager.get_color('text')};
                    border: none;
                    padding: 4px;
                    border-radius: 1px;
                    min-height: {button_min_height}px;
                }}
                QPushButton:hover {{ background-color: {ThemeManager.get_color('accent_hover')}; color: white; }}
                QPushButton:pressed {{ background-color: {ThemeManager.get_color('accent_pressed')}; color: white; }}
                QPushButton:disabled {{ background-color: {ThemeManager.get_color('bg_disabled')}; color: {ThemeManager.get_color('text_disabled')}; }}
            """)
            delete_button.clicked.connect(lambda checked=False, idx=i: self.clear_category_folder(idx))
            # ========== UIScaleManager 적용 ==========
            delete_button.setFixedWidth(delete_button_width)
            delete_button.setFixedHeight(label_fixed_height) # 레이블 높이와 동일하게

            # ========== UIScaleManager 적용 ==========
            folder_path_label = FolderPathLabel(LanguageManager.translate("폴더 경로"), fixed_height_padding=folder_label_padding)
            folder_path_label.setWordWrap(True)
            folder_path_label.setEnabled(False)
            folder_path_label.doubleClicked.connect(lambda full_path_emitted, idx=i: self.open_category_folder(idx, full_path_emitted))

            folder_layout.addWidget(folder_button)
            folder_layout.addWidget(folder_path_label, 1)
            folder_layout.addWidget(delete_button)

            self.control_layout.addWidget(folder_container)
            # ========== UIScaleManager 적용 ==========
            # 각 폴더 컨테이너 사이의 간격
            self.control_layout.addSpacing(UIScaleManager.get("category_folder_vertical_spacing"))

            self.folder_buttons.append(folder_button)
            self.folder_path_labels.append(folder_path_label)
            self.folder_delete_buttons.append(delete_button)

        self.folder_count = 3
        self.update_folder_buttons()
    
    def update_folder_buttons(self):
        """폴더 설정 상태에 따라 UI 업데이트"""
        # 모든 폴더 버튼은 항상 활성화
        for i in range(3):
            # 폴더 버튼 항상 활성화
            self.folder_buttons[i].setEnabled(True)
            
            # 폴더 경로 레이블 및 X 버튼 상태 설정
            has_folder = bool(self.target_folders[i] and os.path.isdir(self.target_folders[i]))
            
            # 폴더 경로 레이블 상태 설정
            self.folder_path_labels[i].setEnabled(has_folder)
            if has_folder:
                # 폴더가 지정된 경우 - 활성화 및 경로 표시
                self.folder_path_labels[i].setStyleSheet(f"""
                    QLabel {{
                        color: #AAAAAA;
                        padding: 5px;
                        background-color: {ThemeManager.get_color('bg_primary')};
                        border-radius: 1px;
                    }}
                """)
            else:
                # 폴더가 지정되지 않은 경우 - 비활성화 스타일
                self.folder_path_labels[i].setStyleSheet(f"""
                    QLabel {{
                        color: {ThemeManager.get_color('text_disabled')};
                        padding: 5px;
                        background-color: {ThemeManager.get_color('bg_disabled')};
                        border-radius: 1px;
                    }}
                """)
                
            # X 버튼 상태 설정
            self.folder_delete_buttons[i].setEnabled(has_folder)
    
    def select_category_folder(self, index):
        """분류 폴더 선택"""
        folder_path = QFileDialog.getExistingDirectory(
            self, f"{LanguageManager.translate('폴더 선택')} {index+1}", "", 
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if folder_path:
            self.target_folders[index] = folder_path
            self.folder_path_labels[index].setText(folder_path, max_length=28, prefix_length=15, suffix_length=12) # 분류폴더 경로 레이블 글자수 설정
            # 폴더 설정 후 UI 업데이트
            self.update_folder_buttons()
    
    def clear_category_folder(self, index):
        """분류 폴더 지정 취소"""
        self.target_folders[index] = ""
        self.folder_path_labels[index].setText(LanguageManager.translate("폴더 경로"))
        # 폴더 설정 취소 후 UI 업데이트
        self.update_folder_buttons()
    
    def open_category_folder(self, index, folder_path): # folder_path 인자 추가
        """선택된 분류 폴더를 탐색기에서 열기 (full_path 사용)"""
        # folder_path = self.folder_path_labels[index].text() # 이 줄 제거

        # 전달받은 folder_path(전체 경로) 직접 사용
        if not folder_path or folder_path == LanguageManager.translate("폴더를 선택하세요"):
            return

        try:
            if sys.platform == 'win32':
                os.startfile(folder_path) # folder_path 는 이제 전체 경로임
            elif sys.platform == 'darwin':  # macOS
                subprocess.run(['open', folder_path])
            else:  # Linux
                subprocess.run(['xdg-open', folder_path])
        except Exception as e:
            logging.error(f"폴더 열기 실패: {e}")
    
    def keyPressEvent(self, event: QKeyEvent):
        """키보드 이벤트 처리 (Grid 모드 추가)"""
        key = event.key()
        modifiers = event.modifiers()
        
        # --- Enter 키 처리 추가 ---
        if key == Qt.Key_Return or key == Qt.Key_Enter:
            if self.image_files: # 로드된 이미지가 있을 때만 실행
                # 현재 선택된 이미지의 인덱스 결정
                current_selected_index = -1
                if self.grid_mode == "Off":
                    current_selected_index = self.current_image_index
                else: # Grid 모드일 때
                    potential_index = self.grid_page_start_index + self.current_grid_index
                    if 0 <= potential_index < len(self.image_files):
                        current_selected_index = potential_index

                # 유효한 인덱스가 있을 때만 대화상자 표시
                if current_selected_index != -1:
                    dialog = FileListDialog(self.image_files, current_selected_index, self.image_loader, self)
                    dialog.exec_() # 모달 대화상자로 실행
                else:
                    logging.debug("Enter 키: 유효한 선택된 이미지가 없습니다.") # 디버깅용
            else:
                logging.debug("Enter 키: 로드된 이미지가 없습니다.") # 디버깅용
            return # Enter 키 이벤트 처리 완료
        # --- Enter 키 처리 끝 ---

        # 새로운 단축키 처리 (F1, F2, F3, Delete)
        if key == Qt.Key_F1:
            # F1: Grid Off
            self.force_refresh = True # 강제 새로고침 플래그 설정 추가
            self.grid_off_radio.setChecked(True)
            self.on_grid_changed(self.grid_off_radio)
            return True
        elif key == Qt.Key_F2:
            # F2: Grid 2x2
            self.force_refresh = True # 강제 새로고침 플래그 설정 추가
            self.grid_2x2_radio.setChecked(True)
            self.on_grid_changed(self.grid_2x2_radio)
            return True
        elif key == Qt.Key_F3:
            # F3: Grid 3x3
            self.force_refresh = True # 강제 새로고침 플래그 설정 추가
            self.grid_3x3_radio.setChecked(True)
            self.on_grid_changed(self.grid_3x3_radio)
            return True
        
        # ESC 키 처리: 확대 모드에서는 Fit 모드로 우선 돌아가고, Grid Off 모드에서만 이전 그리드로 복원
        if key == Qt.Key_Escape:
            # 우선순위 1: 100% 또는 200% 확대 모드에서는 항상 Fit 모드로 돌아가기
            if self.zoom_mode != "Fit":
                self.fit_radio.setChecked(True)
                self.on_zoom_changed(self.fit_radio)
                return
            # 우선순위 2: Grid Off 모드에서만 이전 그리드 모드로 복원 (이미 Fit 모드일 때)
            elif self.grid_mode == "Off" and self.previous_grid_mode and self.previous_grid_mode != "Off":
                if self.previous_grid_mode == "2x2":
                    self.grid_2x2_radio.setChecked(True)
                    # 강제 새로고침 플래그 설정 추가
                    self.force_refresh = True
                    self.on_grid_changed(self.grid_2x2_radio)
                elif self.previous_grid_mode == "3x3":
                    self.grid_3x3_radio.setChecked(True)
                    # 강제 새로고침 플래그 설정 추가
                    self.force_refresh = True
                    self.on_grid_changed(self.grid_3x3_radio)
                return
        
        # 스페이스바 처리: 그리드 모드에서 Grid Off로 전환
        if key == Qt.Key_Space and self.grid_mode != "Off":
            # 이전 그리드 모드 저장
            self.previous_grid_mode = self.grid_mode
            # Grid Off로 전환 (직접 모드 설정 방식으로 변경)
            self.grid_mode = "Off"
            self.grid_off_radio.setChecked(True)
            
            # 스페이스바로 전환 시 이전 모드 유지를 위한 플래그 설정
            self.space_pressed = True
            
            # 그리드 뷰 업데이트
            self.update_grid_view()
            
            # 줌 라디오 버튼 상태 업데이트
            self.update_zoom_radio_buttons_state()
            return
        
        if self.grid_mode != "Off":
            # --- Grid 모드 키 처리 ---
            # Shift+A/D 또는 Shift+Left/Right 처리
            if modifiers & Qt.ShiftModifier:
                if key == Qt.Key_A or key == Qt.Key_Left: # Shift+A 또는 Shift+Left
                    self.navigate_to_adjacent_page(-1)  # 이전 페이지
                    return
                elif key == Qt.Key_D or key == Qt.Key_Right: # Shift+D 또는 Shift+Right
                    self.navigate_to_adjacent_page(1)   # 다음 페이지
                    return

            # --- 기존 WASD/Arrow 키 네비게이션 로직 수정 ---
            rows, cols = (2, 2) if self.grid_mode == '2x2' else (3, 3)

            if key == Qt.Key_A or key == Qt.Key_Left:
                self.navigate_grid(-1) # 좌측/이전
            elif key == Qt.Key_D or key == Qt.Key_Right:
                self.navigate_grid(1)  # 우측/다음
            elif key == Qt.Key_W or key == Qt.Key_Up:
                self.navigate_grid(-cols) # 위
            elif key == Qt.Key_S or key == Qt.Key_Down:
                self.navigate_grid(cols)  # 아래
            # --- 수정 끝 ---

            # 폴더 이동 (1, 2, 3 키)
            elif Qt.Key_1 <= key <= Qt.Key_3:
                folder_index = key - Qt.Key_1
                self.move_grid_image(folder_index)
            else:
                 pass # Grid 모드에서 처리 안 된 키는 무시
        else:
            # --- Grid Off 모드 키 처리 (기존 로직 유지) ---
            if key == Qt.Key_A or key == Qt.Key_Left: # 여기는 원래 or 조건으로 잘 되어 있음
                self.show_previous_image()
            elif key == Qt.Key_D or key == Qt.Key_Right: # 여기도 원래 or 조건으로 잘 되어 있음
                self.show_next_image()
            elif Qt.Key_1 <= key <= Qt.Key_3:
                folder_index = key - Qt.Key_1
                self.move_current_image_to_folder(folder_index)
            else:
                super().keyPressEvent(event)
    
    def navigate_to_adjacent_page(self, direction):
        """그리드 모드에서 페이지 단위 이동 처리 (순환 기능 추가)"""
        if self.grid_mode == "Off" or not self.image_files:
            return

        rows, cols = (2, 2) if self.grid_mode == '2x2' else (3, 3)
        num_cells = rows * cols
        total_images = len(self.image_files)
        if total_images == 0: return # 이미지가 없으면 중단

        total_pages = (total_images + num_cells - 1) // num_cells
        if total_pages <= 1: return # 페이지가 1개뿐이면 순환 의미 없음

        current_page = self.grid_page_start_index // num_cells

        # 새 페이지 계산 (모듈러 연산으로 순환)
        new_page = (current_page + direction + total_pages) % total_pages

        # 페이지 이동
        self.grid_page_start_index = new_page * num_cells
        self.current_grid_index = 0  # 새 페이지의 첫 셀 선택

        # 그리드 뷰 업데이트
        self.update_grid_view()
    
    def show_previous_image(self):
        """이전 이미지 표시 (순환 기능 추가)"""
        if not self.image_files: # 이미지가 없으면 아무것도 안 함
            return

        if self.current_image_index <= 0: # 첫 이미지에서 이전으로 가면
            self.current_image_index = len(self.image_files) - 1 # 마지막 이미지로
        else:
            self.current_image_index -= 1
        
        # 이미지 캐시는 유지하되, 강제 새로고침 플래그 설정
        if self.zoom_mode == "Fit" and self.grid_mode == "Off":
            self.force_refresh = True
        else:
            self.force_refresh = False
        
        self.display_current_image()

    
    def show_next_image(self):
        """다음 이미지 표시 (순환 기능 추가)"""
        if not self.image_files: # 이미지가 없으면 아무것도 안 함
            return

        if self.current_image_index >= len(self.image_files) - 1: # 마지막 이미지에서 다음으로 가면
            self.current_image_index = 0 # 첫 이미지로
        else:
            self.current_image_index += 1
        
        # 이미지 캐시는 유지하되, 강제 새로고침 플래그 설정
        if self.zoom_mode == "Fit" and self.grid_mode == "Off":
            self.force_refresh = True
        else:
            self.force_refresh = False
        
        self.display_current_image()
    
    def move_current_image_to_folder(self, folder_index):
        """현재 이미지를 지정된 폴더로 이동 (Grid Off 모드 전용)"""
        if self.grid_mode != "Off": # Grid 모드에서는 move_grid_image 사용
             return

        if not self.image_files or self.current_image_index < 0 or self.current_image_index >= len(self.image_files):
            return

        target_folder = self.target_folders[folder_index]
        if not target_folder or not os.path.isdir(target_folder):
            return

        current_image_path = self.image_files[self.current_image_index]
        current_index = self.current_image_index # 이동 전 인덱스 저장

        # ======================================================================== #
        # ========== UNDO/REDO VARIABLES START ==========
        moved_jpg_path = None # 이동된 JPG 경로 저장 변수
        moved_raw_path = None # 이동된 RAW 경로 저장 변수
        raw_path_before_move = None # 이동 전 RAW 경로 저장 변수
        # ========== UNDO/REDO VARIABLES END ==========
        # ======================================================================== #

        try:
            # --- JPG 파일 이동 ---
            moved_jpg_path = self.move_file(current_image_path, target_folder) # <<< 반환값 저장

            # --- 이동 실패 시 처리 ---
            if moved_jpg_path is None:
                self.show_themed_message_box(QMessageBox.Critical, LanguageManager.translate("에러"), f"{LanguageManager.translate('파일 이동 중 오류 발생')}: {current_image_path.name}")
                return # 이동 실패 시 여기서 함수 종료

            # --- RAW 파일 이동 (토글 활성화 및 파일 존재 시) ---
            raw_moved_successfully = True # RAW 이동 성공 플래그
            if self.move_raw_files:
                base_name = current_image_path.stem
                if base_name in self.raw_files:
                    raw_path_before_move = self.raw_files[base_name] # 이동 전 경로 저장
                    moved_raw_path = self.move_file(raw_path_before_move, target_folder) # <<< 반환값 저장
                    if moved_raw_path is None:
                        # RAW 이동 실패 시 사용자에게 알리고 계속 진행할지, 아니면 JPG 이동을 취소할지 결정해야 함
                        # 여기서는 RAW 이동 실패 메시지만 보여주고 계속 진행 (JPG는 이미 이동됨)
                        self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("경고"), f"RAW 파일 이동 실패: {raw_path_before_move.name}")
                        raw_moved_successfully = False # 실패 플래그 설정
                    else:
                        del self.raw_files[base_name] # 성공 시에만 raw_files 딕셔너리에서 제거

            # --- 이미지 목록에서 제거 ---
            self.image_files.pop(current_index)

            # ======================================================================== #
            # ========== UNDO/REDO HISTORY ADDITION START ==========
            if moved_jpg_path: # JPG 이동이 성공했을 경우에만 히스토리 추가
                history_entry = {
                    "jpg_source": str(current_image_path),
                    "jpg_target": str(moved_jpg_path),
                    "raw_source": str(raw_path_before_move) if raw_path_before_move else None,
                    "raw_target": str(moved_raw_path) if moved_raw_path and raw_moved_successfully else None, # RAW 이동 성공 시에만 target 저장
                    "index_before_move": current_index,
                    "mode": "Off" # 이동 당시 모드 기록
                }
                self.add_move_history(history_entry)
            # ========== UNDO/REDO HISTORY ADDITION END ==========
            # ======================================================================== #


            if self.image_files:
                # 인덱스 조정 후 이미지 표시 명시적으로 호출
                # 주의: 현재 코드는 바로 다음 이미지를 보여주지 않고 현재 인덱스를 유지함
                # 이동 후에도 현재 인덱스를 유지하므로 자동으로 다음 이미지가 표시됨
                # 다만, 마지막 이미지인 경우 인덱스 조정 필요
                
                # 현재 인덱스가 이미 다음 이미지를 가리키므로 그대로 유지
                # 단, 마지막 이미지였던 경우 새 배열의 끝으로 조정
                # 현재 인덱스가 배열 범위를 벗어나면 마지막 이미지로 조정
                if current_index >= len(self.image_files):
                    self.current_image_index = len(self.image_files) - 1
                else:
                    self.current_image_index = current_index

                # 디버깅을 위해 로그 추가
                logging.debug(f"이미지 이동 후: current_index={current_index}, new current_image_index={self.current_image_index}, 이미지 총 개수={len(self.image_files)}")

                # 강제 이미지 새로고침 플래그 설정 (필요한 경우)
                self.force_refresh = True

                # 이미지 표시 함수 호출
                self.display_current_image()

                # 디버깅용 로그 추가
                logging.debug(f"display_current_image 호출 완료, 현재 인덱스: {self.current_image_index}")
                
            else:
                self.current_image_index = -1
                self.display_current_image() # 빈 화면 표시
                # 미니맵 숨기기 추가
                if self.minimap_visible:
                    self.minimap_widget.hide()
                    self.minimap_visible = False
                self.show_themed_message_box(QMessageBox.Information, LanguageManager.translate("완료"), LanguageManager.translate("모든 이미지가 분류되었습니다."))

        except Exception as e:
            # move_file 에서 예외 처리하지만, pop 등 다른 로직에서 발생할 수 있으므로 유지
            self.show_themed_message_box(QMessageBox.Critical, LanguageManager.translate("에러"), f"{LanguageManager.translate('파일 이동 중 오류 발생')}: {str(e)}")
            # 만약 파일 이동 중 예외 발생 시, 히스토리 추가는 되지 않음

    def move_file(self, source_path, target_folder):
        """파일을 대상 폴더로 이동하고, 이동된 최종 경로를 반환"""
        if not source_path or not target_folder:
            return None # <<< 실패 시 None 반환

        # 대상 폴더 존재 확인
        target_dir = Path(target_folder)
        if not target_dir.exists():
            try: # <<< 폴더 생성 시 오류 처리 추가
                target_dir.mkdir(parents=True)
                logging.info(f"대상 폴더 생성됨: {target_dir}")
            except Exception as e:
                logging.error(f"대상 폴더 생성 실패: {target_dir}, 오류: {e}")
                return None # <<< 폴더 생성 실패 시 None 반환

        # 대상 경로 생성
        target_path = target_dir / source_path.name

        # 이미 같은 이름의 파일이 있는지 확인
        if target_path.exists():
            # 파일명 중복 처리
            counter = 1
            while target_path.exists():
                # 새 파일명 형식: 원본파일명_1.확장자
                new_name = f"{source_path.stem}_{counter}{source_path.suffix}"
                target_path = target_dir / new_name
                counter += 1
            logging.info(f"파일명 중복 처리: {source_path.name} -> {target_path.name}")

        # 파일 이동
        try: # <<< 파일 이동 시 오류 처리 추가
            shutil.move(str(source_path), str(target_path))
            logging.info(f"파일 이동: {source_path} -> {target_path}")
            return target_path # <<< 이동 성공 시 최종 target_path 반환
        except Exception as e:
            logging.error(f"파일 이동 실패: {source_path} -> {target_path}, 오류: {e}")
            return None # <<< 이동 실패 시 None 반환
    
    def setup_zoom_ui(self):
        """줌 UI 설정"""
        # 확대/축소 섹션 제목
        zoom_label = QLabel("Zoom")
        zoom_label.setAlignment(Qt.AlignCenter) # --- 가운데 정렬 추가 ---
        zoom_label.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        # --- 폰트 수정 시작 (새 QFont 객체 생성) ---
        font = QFont(self.font()) # <<< 현재 위젯(PhotoSortApp)의 폰트를 가져와서 복사
        # font.setBold(True) # 이 새 폰트 객체에만 볼드 적용
        font.setPointSize(UIScaleManager.get("font_size")) # 이 새 폰트 객체에만 크기 적용
        zoom_label.setFont(font) # 수정된 새 폰트를 레이블에 적용
        # --- 폰트 수정 끝 ---
        self.control_layout.addWidget(zoom_label)
        self.control_layout.addSpacing(UIScaleManager.get("title_spacing"))

        # 확대 옵션 컨테이너 (가로 배치)
        zoom_container = QWidget()
        zoom_layout = QHBoxLayout(zoom_container)
        zoom_layout.setContentsMargins(0, 5, 0, 5)
        zoom_layout.setSpacing(UIScaleManager.get("group_box_spacing"))
        
        # 라디오 버튼 생성
        self.fit_radio = QRadioButton("Fit")
        self.zoom_100_radio = QRadioButton("100%")
        self.zoom_200_radio = QRadioButton("200%")
        
        # 버튼 그룹에 추가
        self.zoom_group = QButtonGroup(self)
        self.zoom_group.addButton(self.fit_radio, 0)
        self.zoom_group.addButton(self.zoom_100_radio, 1)
        self.zoom_group.addButton(self.zoom_200_radio, 2)
        
        # 기본값: Fit
        self.fit_radio.setChecked(True)
        
        # 버튼 스타일 설정 (기존 코드 재사용)
        radio_style = f"""
            QRadioButton {{
                color: {ThemeManager.get_color('text')};
                padding: 2px;
            }}
            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
            }}
            QRadioButton::indicator:checked {{
                background-color: {ThemeManager.get_color('accent')};
                border: 2px solid {ThemeManager.get_color('accent')};
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: 2px solid {ThemeManager.get_color('border')};
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked:hover {{
                border: 2px solid {ThemeManager.get_color('text_disabled')};
            }}
        """
        self.fit_radio.setStyleSheet(radio_style)
        self.zoom_100_radio.setStyleSheet(radio_style)
        self.zoom_200_radio.setStyleSheet(radio_style)
        
        # 이벤트 연결
        self.zoom_group.buttonClicked.connect(self.on_zoom_changed)
        
        # 레이아웃에 위젯 추가 (가운데 정렬)
        zoom_layout.addStretch()
        zoom_layout.addWidget(self.fit_radio)
        zoom_layout.addWidget(self.zoom_100_radio)
        zoom_layout.addWidget(self.zoom_200_radio)
        zoom_layout.addStretch()
        
        self.control_layout.addWidget(zoom_container)
        
        # 미니맵 토글 체크박스 추가
        self.minimap_toggle = QCheckBox(LanguageManager.translate("미니맵"))
        self.minimap_toggle.setChecked(True)  # 기본값 체크(ON)
        self.minimap_toggle.toggled.connect(self.toggle_minimap)
        self.minimap_toggle.setStyleSheet(f"""
            QCheckBox {{
                color: {ThemeManager.get_color('text')};
                padding: 2px;
            }}
            QCheckBox::indicator {{
                width: 11px;
                height: 11px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {ThemeManager.get_color('accent')};
                border: 2px solid {ThemeManager.get_color('accent')};
                border-radius: 1px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: 2px solid {ThemeManager.get_color('border')};
                border-radius: 1px;
            }}
            QCheckBox::indicator:unchecked:hover {{
                border: 2px solid {ThemeManager.get_color('text_disabled')};
            }}
        """)
        
        # 미니맵 토글을 중앙에 배치
        minimap_container = QWidget()
        minimap_layout = QHBoxLayout(minimap_container)
        minimap_layout.setContentsMargins(0, 5, 0, 5)
        minimap_layout.addStretch()
        minimap_layout.addWidget(self.minimap_toggle)
        minimap_layout.addStretch()
        
        self.control_layout.addWidget(minimap_container)

    def on_zoom_changed(self, button):
            """확대 모드 변경 처리"""
            old_zoom_mode = self.zoom_mode
            
            if button == self.fit_radio:
                self.zoom_mode = "Fit"
                
                # Fit 모드로 전환 시 현재 이미지가 실제로 표시 중인 이미지와 일치하는지 확인
                if self.grid_mode == "Off" and self.image_files and 0 <= self.current_image_index < len(self.image_files):
                    current_image_path = str(self.image_files[self.current_image_index])
                    
                    # 1. 캐시 초기화하여 강제 리로드
                    self.last_fit_size = (0, 0)
                    self.fit_pixmap_cache.clear()
                    
                    # 2. 캐시에서 현재 이미지 다시 가져오기
                    cached_pixmap = self.image_loader.cache.get(current_image_path)
                    if cached_pixmap and not cached_pixmap.isNull():
                        # 캐시된 이미지가 있으면 현재 표시 중인 이미지와 다른지 확인
                        if self.original_pixmap != cached_pixmap:
                            # 이미지가 다르면 현재 올바른 이미지로 강제 업데이트
                            self.original_pixmap = cached_pixmap
                            # 이미지 방향 정보도 업데이트
                            if cached_pixmap.width() >= cached_pixmap.height():
                                self.current_image_orientation = "landscape"
                            else:
                                self.current_image_orientation = "portrait"
                            
                            print(f"Fit 모드 전환: 이미지 불일치 감지, '{Path(current_image_path).name}'으로 강제 업데이트")
                    else:
                        # 캐시에 없으면 강제 리로드 플래그 설정
                        self.force_refresh = True
                        self.display_current_image()
                        return # 리로드 중이므로 여기서 종료

            elif button == self.zoom_100_radio:
                self.zoom_mode = "100%"
                # 100% 또는 200% Zoom 시 Grid는 Off로 변경
                if self.grid_mode != "Off":
                    self.grid_mode = "Off"
                    self.grid_off_radio.setChecked(True)
                    self.update_grid_view() # 그리드 뷰 끄기
                    self.update_counter_layout() # 레이아웃 업데이트 호출

            elif button == self.zoom_200_radio:
                self.zoom_mode = "200%"
                # 100% 또는 200% Zoom 시 Grid는 Off로 변경
                if self.grid_mode != "Off":
                    self.grid_mode = "Off"
                    self.grid_off_radio.setChecked(True)
                    self.update_grid_view() # 그리드 뷰 끄기
                    self.update_counter_layout() # 레이아웃 업데이트 호출


            # Fit에서 100% 또는 200%로 바뀔 때는 가운데로, 
            # 100%와 200% 사이에는 위치 유지
            # center_on_click 플래그가 설정된 경우 그것을 우선 적용하지 않음
            if old_zoom_mode != self.zoom_mode and self.original_pixmap and not self.center_on_click:
                if old_zoom_mode == "Fit" and self.zoom_mode in ["100%", "200%"]:
                    # Fit에서 다른 모드로 변경 시 가운데로
                    self.center_image = True
                elif old_zoom_mode in ["100%", "200%"] and self.zoom_mode in ["100%", "200%"]:
                    # 100% <-> 200% 변경 시 위치 유지
                    self.center_image = False

            # 현재 이미지 다시 표시 (확대/Grid 모드 적용)
            if self.original_pixmap and self.grid_mode == "Off":
                self.apply_zoom_to_image()
            elif self.grid_mode != "Off":
                self.update_grid_view() # Zoom 변경 시 그리드 뷰도 업데이트

            # 미니맵 상태 업데이트
            self.toggle_minimap(self.minimap_toggle.isChecked())

    def toggle_minimap(self, show=None):
        """미니맵 표시 여부 토글"""
        # 파라미터가 없으면 현재 상태에서 토글
        if show is None:
            show = not self.minimap_visible
        
        self.minimap_visible = show and self.minimap_toggle.isChecked()
        
        # Fit 모드이거나 이미지가 없는 경우 미니맵 숨김
        if self.zoom_mode == "Fit" or not self.image_files or self.current_image_index < 0:
            self.minimap_widget.hide()
            return
        
        if self.minimap_visible:
            # 미니맵 크기 계산
            self.calculate_minimap_size()
            
            # 미니맵 위치 업데이트
            self.update_minimap_position()
            
            # 미니맵 이미지 업데이트
            self.update_minimap()
            
            # 미니맵 표시
            self.minimap_widget.show()
            self.minimap_widget.raise_()  # 위젯을 다른 위젯들 위로 올림
        else:
            self.minimap_widget.hide()
    
    def calculate_minimap_size(self):
        """현재 이미지 비율에 맞게 미니맵 크기 계산"""
        if not self.original_pixmap:
            # 기본 3:2 비율 사용
            self.minimap_width = self.minimap_max_size
            self.minimap_height = int(self.minimap_max_size / 1.5)
            return
        
        try:
            # 원본 이미지의 비율 확인
            img_width = self.original_pixmap.width()
            img_height = self.original_pixmap.height()
            img_ratio = img_width / img_height if img_height > 0 else 1.5  # 안전 처리
            
            # 이미지 비율에 맞게 미니맵 크기 설정 (최대 크기 제한)
            if img_ratio > 1:  # 가로가 더 긴 이미지
                self.minimap_width = self.minimap_max_size
                self.minimap_height = int(self.minimap_max_size / img_ratio)
            else:  # 세로가 더 길거나 정사각형 이미지
                self.minimap_height = self.minimap_max_size
                self.minimap_width = int(self.minimap_max_size * img_ratio)
            
            # 미니맵 위젯 크기 업데이트
            self.minimap_widget.setFixedSize(self.minimap_width, self.minimap_height)
            
        except Exception as e:
            # 오류 발생 시 기본 크기 사용
            self.minimap_width = self.minimap_max_size
            self.minimap_height = int(self.minimap_max_size / 1.5)
            logging.error(f"미니맵 크기 계산 오류: {e}")
    
    def update_minimap_position(self):
        """미니맵 위치 업데이트"""
        if not self.minimap_visible:
            return
        
        # 패딩 설정
        padding = 10
        
        # 이미지 패널의 크기 가져오기
        panel_width = self.image_panel.width()
        panel_height = self.image_panel.height()
        
        # 미니맵 위치 계산 (우측 하단)
        minimap_x = panel_width - self.minimap_width - padding
        minimap_y = panel_height - self.minimap_height - padding
        
        # 미니맵 위치 설정
        self.minimap_widget.move(minimap_x, minimap_y)
    
    def update_minimap(self):
        """미니맵 이미지 및 뷰박스 업데이트"""
        if not self.minimap_visible or not self.original_pixmap:
            return
        
        try:
            # 미니맵 이미지 생성 (원본 이미지 축소)
            scaled_pixmap = self.original_pixmap.scaled(
                self.minimap_width, 
                self.minimap_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # 미니맵 크기에 맞게 배경 이미지 조정
            background_pixmap = QPixmap(self.minimap_width, self.minimap_height)
            background_pixmap.fill(Qt.black)
            
            # 배경에 이미지 그리기
            painter = QPainter(background_pixmap)
            # 이미지 중앙 정렬
            x = (self.minimap_width - scaled_pixmap.width()) // 2
            y = (self.minimap_height - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)
            
            # 뷰박스 그리기
            if self.zoom_mode != "Fit":
                self.draw_minimap_viewbox(painter, scaled_pixmap, x, y)
            
            painter.end()
            
            # 미니맵 이미지 설정
            self.minimap_pixmap = background_pixmap
            self.minimap_label.setPixmap(background_pixmap)
            
        except Exception as e:
            logging.error(f"미니맵 업데이트 오류: {e}")
    
    def draw_minimap_viewbox(self, painter, scaled_pixmap, offset_x, offset_y):
        """미니맵에 현재 보이는 영역을 표시하는 뷰박스 그리기"""
        try:
            # 현재 상태 정보
            zoom_level = self.zoom_mode
            
            # 캔버스 크기
            view_width = self.scroll_area.width()
            view_height = self.scroll_area.height()
            
            # 원본 이미지 크기
            img_width = self.original_pixmap.width()
            img_height = self.original_pixmap.height()
            
            # 스케일 계산
            minimap_img_width = scaled_pixmap.width()
            minimap_img_height = scaled_pixmap.height()
            
            # 확대 비율
            if zoom_level == "100%":
                zoom_percent = 1.0
            elif zoom_level == "200%":
                zoom_percent = 2.0
            else:
                return
            
            # 확대된 이미지 크기
            zoomed_width = img_width * zoom_percent
            zoomed_height = img_height * zoom_percent
            
            # 현재 이미지 위치
            img_pos = self.image_label.pos()
            
            # 뷰포트가 보이는 이미지 영역의 비율 계산 (0~1 사이 값)
            if zoomed_width <= view_width:
                # 이미지가 더 작으면 전체가 보임
                view_x_ratio = 0
                view_width_ratio = 1.0
            else:
                # 이미지가 더 크면 일부만 보임
                view_x_ratio = -img_pos.x() / zoomed_width if img_pos.x() < 0 else 0
                view_width_ratio = min(1.0, view_width / zoomed_width)
            
            if zoomed_height <= view_height:
                y_min = (view_height - img_height) // 2
                y_max = y_min
            else:
                y_min = min(0, view_height - img_height)
                y_max = 0
            
            if img_height <= view_height:
                view_y_ratio = 0
                view_height_ratio = 1.0
            else:
                view_y_ratio = -img_pos.y() / zoomed_height if img_pos.y() < 0 else 0
                view_height_ratio = min(1.0, view_height / zoomed_height)
            
            # 범위 제한
            view_x_ratio = min(1.0 - view_width_ratio, max(0, view_x_ratio))
            view_y_ratio = min(1.0 - view_height_ratio, max(0, view_y_ratio))
            
            # 뷰박스 좌표 계산
            box_x1 = offset_x + (view_x_ratio * minimap_img_width)
            box_y1 = offset_y + (view_y_ratio * minimap_img_height)
            box_x2 = box_x1 + (view_width_ratio * minimap_img_width)
            box_y2 = box_y1 + (view_height_ratio * minimap_img_height)
            
            # 뷰박스 그리기
            painter.setPen(QPen(QColor(255, 255, 0), 2))  # 노란색, 2px 두께
            painter.drawRect(int(box_x1), int(box_y1), int(box_x2 - box_x1), int(box_y2 - box_y1))
            
            # 뷰박스 정보 저장
            self.minimap_viewbox = {
                "x1": box_x1,
                "y1": box_y1,
                "x2": box_x2,
                "y2": box_y2,
                "offset_x": offset_x,
                "offset_y": offset_y,
                "width": minimap_img_width,
                "height": minimap_img_height
            }
            
        except Exception as e:
            logging.error(f"뷰박스 그리기 오류: {e}")
    
    def minimap_mouse_press_event(self, event):
        """미니맵 마우스 클릭 이벤트 처리"""
        if not self.minimap_visible or self.zoom_mode == "Fit":
            return
        
        # 패닝 진행 중이면 중단
        if self.panning:
            self.panning = False
            
        # 이벤트 발생 위치
        pos = event.position().toPoint()
        
        # 뷰박스 클릭 체크
        if self.minimap_viewbox and self.is_point_in_viewbox(pos):
            # 뷰박스 내부 클릭 - 드래그 시작
            self.minimap_viewbox_dragging = True
            self.minimap_drag_start = pos
        else:
            # 뷰박스 외부 클릭 - 위치 이동
            self.move_view_to_minimap_point(pos)
    
    def minimap_mouse_move_event(self, event):
        """미니맵 마우스 이동 이벤트 처리"""
        if not self.minimap_visible or self.zoom_mode == "Fit":
            return
            
        # 패닝 중이라면 중단
        if self.panning:
            self.panning = False
            
        pos = event.position().toPoint()
        
        # 뷰박스 드래그 처리
        if self.minimap_viewbox_dragging:
            self.drag_minimap_viewbox(pos)
        
        # 뷰박스 위에 있을 때 커서 모양 변경
        if self.is_point_in_viewbox(pos):
            self.minimap_widget.setCursor(Qt.PointingHandCursor)
        else:
            self.minimap_widget.setCursor(Qt.ArrowCursor)
    
    def minimap_mouse_release_event(self, event):
        """미니맵 마우스 릴리스 이벤트 처리"""
        if event.button() == Qt.LeftButton:
            # 드래그 상태 해제
            self.minimap_viewbox_dragging = False
            self.minimap_widget.setCursor(Qt.ArrowCursor)
    
    def is_point_in_viewbox(self, point):
        """포인트가 뷰박스 내에 있는지 확인"""
        if not self.minimap_viewbox:
            return False
        
        vb = self.minimap_viewbox
        return (vb["x1"] <= point.x() <= vb["x2"] and
                vb["y1"] <= point.y() <= vb["y2"])
    
    def move_view_to_minimap_point(self, point):
        """미니맵의 특정 지점으로 뷰 이동"""
        if not self.minimap_viewbox or not self.original_pixmap:
            return
        
        # 이벤트 스로틀링
        current_time = int(time.time() * 1000)
        if current_time - self.last_event_time < 50:  # 50ms 지연
            return
        
        self.last_event_time = current_time
        
        vb = self.minimap_viewbox
        
        # 미니맵 이미지 내 클릭 위치의 상대적 비율 계산
        x_ratio = (point.x() - vb["offset_x"]) / vb["width"]
        y_ratio = (point.y() - vb["offset_y"]) / vb["height"]
        
        # 비율 제한
        x_ratio = max(0, min(1, x_ratio))
        y_ratio = max(0, min(1, y_ratio))
        
        # 원본 이미지 크기
        img_width = self.original_pixmap.width()
        img_height = self.original_pixmap.height()
        
        # 확대 비율
        zoom_percent = 1.0 if self.zoom_mode == "100%" else 2.0
        
        # 확대된 이미지 크기
        zoomed_width = img_width * zoom_percent
        zoomed_height = img_height * zoom_percent
        
        # 뷰포트 크기
        view_width = self.scroll_area.width()
        view_height = self.scroll_area.height()
        
        # 새 이미지 위치 계산
        new_x = -x_ratio * (zoomed_width - view_width) if zoomed_width > view_width else (view_width - zoomed_width) / 2
        new_y = -y_ratio * (zoomed_height - view_height) if zoomed_height > view_height else (view_height - zoomed_height) / 2
        
        # 이미지 위치 업데이트
        self.image_label.move(int(new_x), int(new_y))
        
        # 미니맵 업데이트
        self.update_minimap()
    
    def drag_minimap_viewbox(self, point):
        """미니맵 뷰박스 드래그 처리 - 부드럽게 개선"""
        if not self.minimap_viewbox or not self.minimap_viewbox_dragging:
            return
        
        # 스로틀링 시간 감소하여 부드러움 향상 
        current_time = int(time.time() * 1000)
        if current_time - self.last_event_time < 16:  # 약 60fps를 목표로 (~16ms)
            return
        
        self.last_event_time = current_time
        
        # 마우스 이동 거리 계산
        dx = point.x() - self.minimap_drag_start.x()
        dy = point.y() - self.minimap_drag_start.y()
        
        # 현재 위치 업데이트
        self.minimap_drag_start = point
        
        # 미니맵 내에서의 이동 비율
        vb = self.minimap_viewbox
        x_ratio = dx / vb["width"] if vb["width"] > 0 else 0
        y_ratio = dy / vb["height"] if vb["height"] > 0 else 0
        
        # 원본 이미지 크기
        img_width = self.original_pixmap.width()
        img_height = self.original_pixmap.height()
        
        # 확대 비율
        zoom_percent = 1.0 if self.zoom_mode == "100%" else 2.0
        
        # 확대된 이미지 크기
        zoomed_width = img_width * zoom_percent
        zoomed_height = img_height * zoom_percent
        
        # 현재 이미지 위치
        img_pos = self.image_label.pos()
        
        # 이미지가 이동할 거리 계산
        img_dx = x_ratio * zoomed_width
        img_dy = y_ratio * zoomed_height
        
        # 뷰포트 크기
        view_width = self.scroll_area.width()
        view_height = self.scroll_area.height()
        
        # 새 위치 계산
        new_x = img_pos.x() - img_dx
        new_y = img_pos.y() - img_dy
        
        # 위치 제한
        if zoomed_width > view_width:
            new_x = min(0, max(view_width - zoomed_width, new_x))
        else:
            new_x = (view_width - zoomed_width) / 2
            
        if zoomed_height > view_height:
            new_y = min(0, max(view_height - zoomed_height, new_y))
        else:
            new_y = (view_height - zoomed_height) / 2
        
        # 이미지 위치 업데이트
        self.image_label.move(int(new_x), int(new_y))
        
        # 미니맵 업데이트
        self.update_minimap()
    
    def get_scaled_size(self, base_size):
        """UI 배율을 고려한 크기 계산"""
        # 화면의 물리적 DPI와 논리적 DPI를 사용하여 스케일 계산
        screen = QGuiApplication.primaryScreen()
        if screen:
            dpi_ratio = screen.devicePixelRatio()
            # Qt의 devicePixelRatio를 사용하여 실제 UI 배율 계산
            # Windows에서 150% 배율일 경우 dpi_ratio는 1.5가 됨
            return int(base_size / dpi_ratio)  # 배율을 고려하여 크기 조정
        return base_size  # 스케일 정보를 얻을 수 없으면 기본값 사용

    def setup_grid_ui(self):
        """Grid 설정 UI 구성"""

        # Grid 제목 레이블
        grid_title = QLabel("Grid")
        grid_title.setAlignment(Qt.AlignCenter) # --- 가운데 정렬 ---
        grid_title.setStyleSheet(f"color: {ThemeManager.get_color('text')};") # --- 스타일 시트에서 마진 제거 ---
        # --- 폰트 설정 시작 (Zoom과 동일하게) ---
        font = QFont(self.font()) # 기본 폰트 속성 복사
        # font.setBold(True) # 볼드 적용
        font.setPointSize(UIScaleManager.get("font_size")) # 크기 적용
        grid_title.setFont(font) # 새 폰트 적용
        # --- 폰트 설정 끝 ---
        self.control_layout.addWidget(grid_title)
        self.control_layout.addSpacing(UIScaleManager.get("title_spacing"))

        # Grid 옵션 컨테이너 (가로 배치)
        grid_container = QWidget()
        grid_layout_h = QHBoxLayout(grid_container)
        grid_layout_h.setContentsMargins(0, 5, 0, 5)
        grid_layout_h.setSpacing(UIScaleManager.get("group_box_spacing")) 

        # 라디오 버튼 생성
        self.grid_off_radio = QRadioButton("Off")
        self.grid_2x2_radio = QRadioButton("2 x 2")
        self.grid_3x3_radio = QRadioButton("3 x 3")

        # 버튼 그룹에 추가
        self.grid_group = QButtonGroup(self)
        self.grid_group.addButton(self.grid_off_radio, 0)
        self.grid_group.addButton(self.grid_2x2_radio, 1)
        self.grid_group.addButton(self.grid_3x3_radio, 2)

        # 기본값: Off
        self.grid_off_radio.setChecked(True)

        # 버튼 스타일 설정 (Zoom 스타일 재사용)
        radio_style = f"""
            QRadioButton {{
                color: {ThemeManager.get_color('text')};
                padding: 2px;
            }}
            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
            }}
            QRadioButton::indicator:checked {{
                background-color: {ThemeManager.get_color('accent')};
                border: 2px solid {ThemeManager.get_color('accent')};
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: 2px solid {ThemeManager.get_color('border')};
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked:hover {{
                border: 2px solid {ThemeManager.get_color('text_disabled')};
            }}
        """
        self.grid_off_radio.setStyleSheet(radio_style)
        self.grid_2x2_radio.setStyleSheet(radio_style)
        self.grid_3x3_radio.setStyleSheet(radio_style)

        # 이벤트 연결
        self.grid_group.buttonClicked.connect(self.on_grid_changed)

        # 레이아웃에 위젯 추가 (가운데 정렬)
        grid_layout_h.addStretch()
        grid_layout_h.addWidget(self.grid_off_radio)
        grid_layout_h.addWidget(self.grid_2x2_radio)
        grid_layout_h.addWidget(self.grid_3x3_radio)
        grid_layout_h.addStretch()

        self.control_layout.addWidget(grid_container)

    def on_grid_changed(self, button):
        """Grid 모드 변경 처리"""
        previous_grid_mode = self.grid_mode
        new_grid_mode = "Off" # 기본값

        # 이전 그리드 모드에서의 선택 인덱스 저장 (Off로 갈 때 사용)
        last_selected_image_index = -1
        if previous_grid_mode != "Off":
            global_index = self.grid_page_start_index + self.current_grid_index
            # global_index가 실제 이미지 리스트 범위 내에 있는지 확인
            if 0 <= global_index < len(self.image_files):
                last_selected_image_index = global_index
            elif self.image_files: # 유효한 선택이 없었지만 이미지가 있다면 첫번째 이미지로
                last_selected_image_index = 0

        if button == self.grid_off_radio:
            new_grid_mode = "Off"
            # 스페이스바로 전환된 경우가 아닐 때만 previous_grid_mode 초기화
            if not self.space_pressed:
                self.previous_grid_mode = None
            else:
                # 스페이스바 플래그 초기화
                self.space_pressed = False
            
            # Off 모드로 전환 시, 이전 선택 이미지 인덱스를 current_image_index로 설정
            if last_selected_image_index != -1:
                self.current_image_index = last_selected_image_index
                
                # 이미지 변경 시 강제 새로고침 플래그 설정 추가
                self.force_refresh = True
                
                # Fit 모드인 경우 기존 캐시 무효화 추가
                if self.zoom_mode == "Fit":
                    self.last_fit_size = (0, 0)
                    self.fit_pixmap_cache.clear()
                    
            elif self.image_files: # 이미지 파일이 있는데 선택 정보가 없으면 첫 이미지
                self.current_image_index = 0
                
                # 이미지 변경 시 강제 새로고침 플래그 설정 추가
                self.force_refresh = True
                
                # Fit 모드인 경우 기존 캐시 무효화 추가
                if self.zoom_mode == "Fit":
                    self.last_fit_size = (0, 0)
                    self.fit_pixmap_cache.clear()
                    
            else: # 이미지 파일이 아예 없으면
                self.current_image_index = -1

        elif button == self.grid_2x2_radio:
            new_grid_mode = "2x2"
            if self.zoom_mode != "Fit":
                self.zoom_mode = "Fit"
                self.fit_radio.setChecked(True)
        elif button == self.grid_3x3_radio:
            new_grid_mode = "3x3"
            if self.zoom_mode != "Fit":
                self.zoom_mode = "Fit"
                self.fit_radio.setChecked(True)

        # Grid 모드가 실제로 변경되었는지 확인
        if previous_grid_mode != new_grid_mode:
            # Grid Off에서 다른 모드로 전환 시, 이전 모드 저장은 하지 않음
            
            self.grid_mode = new_grid_mode # 새 모드 적용

            # 모드 변경 시 그리드 관련 상태 초기화 또는 조정
            if new_grid_mode != "Off":
                # Off -> Grid 전환 시, 현재 단일 이미지 인덱스를 기준으로 페이지 및 셀 결정
                if previous_grid_mode == "Off" and self.current_image_index != -1:
                      rows, cols = (2, 2) if new_grid_mode == '2x2' else (3, 3)
                      num_cells = rows * cols
                      self.grid_page_start_index = (self.current_image_index // num_cells) * num_cells
                      self.current_grid_index = self.current_image_index % num_cells
                else: # Grid -> Grid 전환 (또는 초기 상태)
                      pass # Grid -> Grid 전환 시 상태 유지

            # 뷰 업데이트
            self.update_grid_view()
            
            # 줌 라디오 버튼 상태 업데이트
            self.update_zoom_radio_buttons_state()

            # 카운터 레이아웃 업데이트 (Grid 모드 변경에 따라)
            self.update_counter_layout()

        # 미니맵 활성화/비활성화 및 상태 업데이트
        if self.grid_mode != "Off":
            self.toggle_minimap(False) # 그리드 모드에서는 미니맵 숨김
        else:
            self.toggle_minimap(self.minimap_toggle.isChecked())

    def update_zoom_radio_buttons_state(self):
        """그리드 모드에 따라 줌 라디오 버튼 활성화/비활성화"""
        if self.grid_mode != "Off":
            # 그리드 모드에서 100%, 200% 비활성화
            self.zoom_100_radio.setEnabled(False)
            self.zoom_200_radio.setEnabled(False)
            # 비활성화 스타일 적용
            disabled_radio_style = f"""
                QRadioButton {{
                    color: {ThemeManager.get_color('text_disabled')};
                    padding: 2px;
                }}
                QRadioButton::indicator {{
                    width: 14px;
                    height: 14px;
                }}
                QRadioButton::indicator:checked {{
                    background-color: {ThemeManager.get_color('accent')};
                    border: 2px solid {ThemeManager.get_color('accent')};
                    border-radius: 9px;
                }}
                QRadioButton::indicator:unchecked {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border: 2px solid {ThemeManager.get_color('border')};
                    border-radius: 9px;
                }}
            """
            self.zoom_100_radio.setStyleSheet(disabled_radio_style)
            self.zoom_200_radio.setStyleSheet(disabled_radio_style)
        else:
            # 그리드 모드가 아닐 때 모든 버튼 활성화
            self.zoom_100_radio.setEnabled(True)
            self.zoom_200_radio.setEnabled(True)
            # 활성화 스타일 복원
            radio_style = f"""
                QRadioButton {{
                    color: {ThemeManager.get_color('text')};
                    padding: 2px;
                }}
                QRadioButton::indicator {{
                    width: 14px;
                    height: 14px;
                }}
                QRadioButton::indicator:checked {{
                    background-color: {ThemeManager.get_color('accent')};
                    border: 2px solid {ThemeManager.get_color('accent')};
                    border-radius: 9px;
                }}
                QRadioButton::indicator:unchecked {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border: 2px solid {ThemeManager.get_color('border')};
                    border-radius: 9px;
                }}
                QRadioButton::indicator:unchecked:hover {{
                    border: 2px solid {ThemeManager.get_color('text_disabled')};
                }}
            """
            self.zoom_100_radio.setStyleSheet(radio_style)
            self.zoom_200_radio.setStyleSheet(radio_style)
    
    def update_grid_view(self):
        """Grid 모드에 따라 이미지 뷰 업데이트"""

        # 현재 스크롤 영역에 있는 위젯 가져오기
        current_widget = self.scroll_area.widget()

        if self.grid_mode == "Off":
            # === Grid Off 모드로 전환 또는 유지 ===
            if current_widget is not self.image_container:
                # 이전 위젯(아마도 그리드 컨테이너) 제거 및 삭제 예약
                old_widget = self.scroll_area.takeWidget()
                if old_widget and old_widget is not self.image_container: # image_container는 삭제하면 안됨
                    old_widget.deleteLater()
                # 레이아웃과 레이블 리스트 정리 (참조만 제거)
                self.grid_layout = None
                self.grid_labels.clear()

            # 스크롤 영역에 단일 이미지 컨테이너 설정 (이미 설정되어 있어도 호출)
            if current_widget is not self.image_container:
                self.scroll_area.setWidget(self.image_container)

            # 현재 선택된 이미지 표시 (current_image_index는 on_grid_changed에서 설정됨)
            # 그리드 모드에서 전환된 경우 강제 새로고침이 필요할 수 있음
            if getattr(self, 'force_refresh', False):
                # 이미 force_refresh 플래그가 설정되어 있으면 적용
                # display_current_image()가 이를 처리
                pass
            else:
                # 그리드에서 Off로 전환될 때 명시적으로 설정
                self.force_refresh = True
                
            self.display_current_image()
            return # Off 모드 처리는 여기서 종료

        # === Grid On 모드로 전환 또는 유지 ('2x2' 또는 '3x3') ===

        # 이전 위젯 처리
        if current_widget is self.image_container:
            # 단일 이미지 컨테이너였으면 그냥 제거 (삭제는 안 함)
            self.scroll_area.takeWidget()
        elif current_widget is not None:
             # 이전 그리드 컨테이너였으면 제거하고 삭제 예약
             old_widget = self.scroll_area.takeWidget()
             old_widget.deleteLater()

        # --- 새 Grid 생성 시작 ---
        # 레이아웃과 레이블 리스트 초기화 (항상 새로 만듦)
        self.grid_layout = None
        self.grid_labels.clear()

        # 새 Grid 레이아웃 및 컨테이너 위젯 생성
        rows, cols = (2, 2) if self.grid_mode == '2x2' else (3, 3)
        num_cells = rows * cols

        self.grid_layout = QGridLayout() # 새 레이아웃 객체
        self.grid_layout.setSpacing(0)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)

        grid_container_widget = QWidget() # 새 컨테이너 위젯
        grid_container_widget.setLayout(self.grid_layout)
        grid_container_widget.setStyleSheet("background-color: black;")

        # 스크롤 영역에 새 그리드 컨테이너 설정
        self.scroll_area.setWidget(grid_container_widget)
        self.scroll_area.setWidgetResizable(True) # 리사이즈 가능 설정 유지

        # 이미지 로드 및 레이블 생성/추가
        start_idx = self.grid_page_start_index
        end_idx = min(start_idx + num_cells, len(self.image_files))
        images_to_display = self.image_files[start_idx:end_idx]

        # current_grid_index가 새 페이지의 유효 범위를 벗어나는 경우 조정
        if self.current_grid_index >= len(images_to_display) and len(images_to_display) > 0:
             self.current_grid_index = len(images_to_display) - 1
        elif len(images_to_display) == 0:
             self.current_grid_index = 0

        for i in range(num_cells):
            row, col = divmod(i, cols)

            cell_label = QLabel() # 항상 새 레이블 생성
            cell_label.setAlignment(Qt.AlignCenter)
            cell_label.setStyleSheet("border: 1px solid #555555;") # 기본 테두리
            cell_label.setMinimumSize(1, 1)
            
            # 클릭 이벤트와 더블클릭 이벤트 처리
            cell_label.mousePressEvent = lambda event, label=cell_label, index=i: self.on_grid_cell_clicked(label, index) # 인덱스 전달
            cell_label.mouseDoubleClickEvent = lambda event, label=cell_label, index=i: self.on_grid_cell_double_clicked(label, index) # 더블클릭 처리 추가

            if i < len(images_to_display):
                current_image_path = str(images_to_display[i])
                cell_label.setProperty("image_path", current_image_path)
                cell_label.setProperty("loaded", False) # 초기 상태는 로드 안됨

                # --- ImageLoader 캐시 확인 및 이미지 설정 (원래 방식과 유사하게) ---
                # ImageLoader의 캐시를 직접 접근하기보다, preload_page가 처리하도록 유도
                # 여기서는 우선 플레이스홀더를 설정
                cell_label.setPixmap(self.placeholder_pixmap)

                # ***********************************************************************
                # 중요: ImageLoader 캐시 확인 로직 추가 (선택적이지만 성능 향상에 도움)
                # ImageLoader 내부에 캐시가 있다면 즉시 가져와서 표시 시도
                cached_original = self.image_loader.cache.get(current_image_path) # 직접 캐시 접근 (주의)
                if cached_original and not cached_original.isNull():
                    try:
                        cell_label.setProperty("original_pixmap", cached_original)
                        # 캐시된 원본을 현재 셀 크기에 맞게 리사이즈 (Smooth 사용)
                        if cell_label.width() > 10 and cell_label.height() > 10:
                            scaled_pixmap = cached_original.scaled(
                                cell_label.size(),
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation # 여기서 Smooth 사용
                            )
                            cell_label.setPixmap(scaled_pixmap)
                            cell_label.setProperty("loaded", True)
                            # print(f"ImageLoader 캐시 사용 및 리사이즈: {Path(current_image_path).name}")
                        else: # 레이블 크기가 아직 유효하지 않으면 플레이스홀더 유지
                            pass
                    except Exception as e:
                        logging.error(f"그리드 뷰에서 캐시 이미지 리사이즈 오류: {e}")
                # ***********************************************************************

            else:
                cell_label.setText("") # 빈 셀
            self.grid_layout.addWidget(cell_label, row, col)
            self.grid_labels.append(cell_label) # 새 레이블 리스트에 추가

        # 선택 상태 및 제목 업데이트
        self.update_grid_selection_border() # 테두리 업데이트 (새 레이블에 적용됨)
        self.update_window_title_with_selection()

        # 비동기 이미지 로딩 시작 (페이지당 셀 수)
        self.image_loader.preload_page(self.image_files, self.grid_page_start_index, num_cells)

        # Grid 이미지 리사이즈 예약 (UI가 그려진 후 실행되도록)
        QTimer.singleShot(0, self.resize_grid_images)

        # --- 파일 정보 UI 업데이트 추가 (update_grid_view 끝) ---
        selected_image_list_index_gw = self.grid_page_start_index + self.current_grid_index
        if 0 <= selected_image_list_index_gw < len(self.image_files):
            self.update_file_info_display(str(self.image_files[selected_image_list_index_gw]))
        else:
            self.update_file_info_display(None) # 유효하지 않으면 초기화
        # --- 업데이트 끝 ---

        self.update_counters() # 카운터 업데이트

    def on_image_loaded(self, cell_index, pixmap, img_path):
        """비동기 이미지 로딩 완료 시 호출되는 슬롯"""
        if self.grid_mode == "Off" or not self.grid_labels:
            return
            
        if 0 <= cell_index < len(self.grid_labels):
            cell_label = self.grid_labels[cell_index]
            if cell_label.property("image_path") == img_path:
                # --- "original_pixmap" 속성 설정 추가/복원 ---
                cell_label.setProperty("original_pixmap", pixmap)
                # --- 추가/복원 끝 ---
                cell_label.setProperty("loaded", True) # 로드됨 상태 설정

                # 현재 표시 크기에 맞게 스케일링 (SmoothTransformation 사용)
                if cell_label.width() > 10 and cell_label.height() > 10:
                    scaled_pixmap = pixmap.scaled(
                        cell_label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    cell_label.setPixmap(scaled_pixmap)
                else:
                    cell_label.setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.FastTransformation))

    def resize_grid_images(self):
        """그리드 셀 크기에 맞춰 이미지 리사이징 (고품질)"""
        if not self.grid_labels or self.grid_mode == "Off": # source:457
            return # source:457

        for label in self.grid_labels: # source:457
            image_path = label.property("image_path")
            # if label.property("loaded") and image_path: # 로드된 상태이고 경로가 있을 때만
            if image_path: # 경로가 있으면 무조건 시도 (캐시에 있을 수 있으므로)
                # ImageLoader 캐시에서 원본 이미지를 가져옴
                original_pixmap = self.image_loader.cache.get(image_path)

                if original_pixmap and isinstance(original_pixmap, QPixmap) and not original_pixmap.isNull(): # source:458
                    # QLabel의 현재 크기에 맞춰 고품질 스케일링 (SmoothTransformation)
                    try:
                        scaled_pixmap = original_pixmap.scaled(
                            label.size(), # 현재 QLabel 크기 사용 (source:458)
                            Qt.KeepAspectRatio, # source:459
                            Qt.SmoothTransformation # 고품질 스케일링 (source:459)
                        )
                        # 현재 표시된 것과 다를 경우에만 업데이트 (선택적 최적화)
                        # if label.pixmap() is None or label.pixmap().size() != scaled_pixmap.size():
                        label.setPixmap(scaled_pixmap) # source:459
                    except Exception as e:
                        logging.error(f"resize_grid_images 오류 ({Path(image_path).name}): {e}")
                # else: 캐시에 없거나 로드 실패한 경우 그대로 둠

    def update_grid_selection_border(self):
        """현재 선택된 그리드 셀의 테두리 업데이트"""
        if not self.grid_labels or self.grid_mode == "Off":
            return

        for i, label in enumerate(self.grid_labels):
            # 셀에 이미지가 없어도 테두리는 업데이트 (이동 가능하게)
            if i == self.current_grid_index:
                # 선택된 셀 테두리 두께 1px로 변경
                label.setStyleSheet("border: 1px solid white;")
            else:
                # 기본 셀 테두리 두께 1px로 변경
                label.setStyleSheet("border: 1px solid #555555;")

    def update_window_title_with_selection(self):
        """Grid 모드에서 창 제목 업데이트 ("PhotoSort - 파일명" 형식)"""
        if self.grid_mode == "Off":
             # Grid Off 모드에서는 display_current_image에서 처리
             return

        total_images = len(self.image_files)
        selected_filename = ""
        selected_image_list_index = self.grid_page_start_index + self.current_grid_index

        if 0 <= selected_image_list_index < total_images:
            selected_filename = self.image_files[selected_image_list_index].name
            title = f"PhotoSort - {selected_filename}" # 새 형식 적용
        else:
            # 이미지가 없거나 유효한 선택이 아닐 때
            title = "PhotoSort"

        self.setWindowTitle(title)

    def navigate_grid(self, delta):
        """Grid 셀 간 이동 및 페이지 전환 처리 (좌우 끝에서만 순환, 상하 페이지 이동 없음)"""
        if not self.image_files or self.grid_mode == "Off":
            return

        total_images = len(self.image_files)
        if total_images <= 0: return # 이미지가 없으면 중단

        rows, cols = (2, 2) if self.grid_mode == '2x2' else (3, 3)
        num_cells = rows * cols

        # 현재 페이지의 셀 개수 계산 (마지막 페이지는 다를 수 있음)
        current_page_first_image_index = self.grid_page_start_index
        # 현재 페이지에 실제로 표시될 수 있는 이미지의 마지막 인덱스
        current_page_last_possible_image_index = min(current_page_first_image_index + num_cells - 1, total_images - 1)
        # 현재 페이지에 실제로 존재하는 셀(이미지)의 개수
        current_page_cell_count = current_page_last_possible_image_index - current_page_first_image_index + 1

        # 현재 선택된 셀의 전체 목록에서의 인덱스
        current_global_index = self.grid_page_start_index + self.current_grid_index

        page_changed = False
        new_grid_index = self.current_grid_index # 페이지 내 이동 기본값

        # 1. 좌/우 이동 처리 (Left/A 또는 Right/D)
        if delta == -1: # 왼쪽
            if current_global_index == 0: # <<< 전체 첫 이미지에서 왼쪽: 마지막 이미지로 순환
                self.grid_page_start_index = ((total_images - 1) // num_cells) * num_cells
                self.current_grid_index = (total_images - 1) % num_cells
                page_changed = True
                logging.debug("Navigating grid: Wrap around to last image") # 디버깅 로그
            elif self.current_grid_index == 0 and self.grid_page_start_index > 0: # 페이지 첫 셀에서 왼쪽: 이전 페이지 마지막 셀
                self.grid_page_start_index = max(0, self.grid_page_start_index - num_cells)
                # 이전 페이지의 셀 개수 계산
                prev_page_cell_count = min(num_cells, total_images - self.grid_page_start_index)
                self.current_grid_index = prev_page_cell_count - 1 # 이전 페이지의 마지막 유효 셀로 이동
                page_changed = True
                logging.debug(f"Navigating grid: To previous page, index {self.current_grid_index}") # 디버깅 로그
            elif self.current_grid_index > 0: # 페이지 내 왼쪽 이동
                new_grid_index = self.current_grid_index - 1
                logging.debug(f"Navigating grid: Move left within page to {new_grid_index}") # 디버깅 로그

        elif delta == 1: # 오른쪽
            if current_global_index == total_images - 1: # <<< 전체 마지막 이미지에서 오른쪽: 첫 이미지로 순환
                self.grid_page_start_index = 0
                self.current_grid_index = 0
                page_changed = True
                logging.debug("Navigating grid: Wrap around to first image") # 디버깅 로그
            elif self.current_grid_index == current_page_cell_count - 1 and self.grid_page_start_index + num_cells < total_images: # 페이지 마지막 셀에서 오른쪽: 다음 페이지 첫 셀
                self.grid_page_start_index += num_cells
                self.current_grid_index = 0
                page_changed = True
                logging.debug("Navigating grid: To next page, index 0") # 디버깅 로그
            elif self.current_grid_index < current_page_cell_count - 1: # 페이지 내 오른쪽 이동
                new_grid_index = self.current_grid_index + 1
                logging.debug(f"Navigating grid: Move right within page to {new_grid_index}") # 디버깅 로그

        # 2. 상/하 이동 처리 (Up/W 또는 Down/S) - 페이지 이동 없음
        elif delta == -cols: # 위
            if self.current_grid_index >= cols: # 첫 줄이 아니면 위로 이동
                new_grid_index = self.current_grid_index - cols
                logging.debug(f"Navigating grid: Move up within page to {new_grid_index}") # 디버깅 로그
            # 첫 줄이면 이동 안 함

        elif delta == cols: # 아래
            potential_new_index = self.current_grid_index + cols
            # 이동하려는 위치가 현재 페이지의 유효한 셀 범위 내에 있는지 확인
            if potential_new_index < current_page_cell_count:
                new_grid_index = potential_new_index
                logging.debug(f"Navigating grid: Move down within page to {new_grid_index}") # 디버깅 로그
            # 마지막 줄이거나 다음 줄에 해당하는 셀이 현재 페이지에 없으면 이동 안 함

        # 3. 페이지 내 이동 결과 적용 (페이지 변경이나 순환이 아닐 경우)
        if not page_changed and new_grid_index != self.current_grid_index:
            self.current_grid_index = new_grid_index
            # 페이지 내 이동 시 UI 업데이트
            self.update_grid_selection_border()
            self.update_window_title_with_selection()
            image_list_index_ng = self.grid_page_start_index + self.current_grid_index
            # 페이지 내 이동 시에도 전역 인덱스 유효성 검사 (안전 장치)
            if 0 <= image_list_index_ng < total_images:
                self.update_file_info_display(str(self.image_files[image_list_index_ng]))
            else:
                # 이 경우는 발생하면 안되지만, 방어적으로 처리
                self.update_file_info_display(None)
                logging.warning(f"Warning: Invalid global index {image_list_index_ng} after intra-page navigation.")
            self.update_counters()

        # 4. 페이지 변경 또는 순환 발생 시 UI 업데이트
        elif page_changed:
            # 페이지 변경/순환 시에는 update_grid_view가 모든 UI 업데이트를 처리
            self.update_grid_view()
            logging.debug(f"Navigating grid: Page changed to start index {self.grid_page_start_index}, grid index {self.current_grid_index}") # 디버깅 로그

    def move_grid_image(self, folder_index):
        """Grid 모드에서 현재 선택된 이미지를 지정된 폴더로 이동"""
        if self.grid_mode == "Off" or not self.grid_labels:
            return

        rows, cols = (2, 2) if self.grid_mode == '2x2' else (3, 3)
        num_cells = rows * cols

        image_list_index = self.grid_page_start_index + self.current_grid_index # 이동 전 인덱스

        if not (0 <= image_list_index < len(self.image_files)):
            logging.warning("선택된 셀에 이동할 이미지가 없습니다.")
            return

        target_folder = self.target_folders[folder_index]
        if not target_folder or not os.path.isdir(target_folder):
            return

        current_image_path = self.image_files[image_list_index]

        # ======================================================================== #
        # ========== UNDO/REDO VARIABLES START ==========
        moved_jpg_path = None
        moved_raw_path = None
        raw_path_before_move = None
        # ========== UNDO/REDO VARIABLES END ==========
        # ======================================================================== #

        try:
            # --- JPG 파일 이동 ---
            moved_jpg_path = self.move_file(current_image_path, target_folder) # <<< 반환값 저장

            # --- 이동 실패 시 처리 ---
            if moved_jpg_path is None:
                self.show_themed_message_box(QMessageBox.Critical, LanguageManager.translate("에러"), f"{LanguageManager.translate('파일 이동 중 오류 발생')}: {current_image_path.name}")
                return

            # --- RAW 파일 이동 ---
            raw_moved_successfully = True
            if self.move_raw_files:
                base_name = current_image_path.stem
                if base_name in self.raw_files:
                    raw_path_before_move = self.raw_files[base_name]
                    moved_raw_path = self.move_file(raw_path_before_move, target_folder) # <<< 반환값 저장
                    if moved_raw_path is None:
                        self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("경고"), f"RAW 파일 이동 실패: {raw_path_before_move.name}")
                        raw_moved_successfully = False
                    else:
                        del self.raw_files[base_name]

            # --- 이미지 목록에서 제거 ---
            self.image_files.pop(image_list_index)

            # ======================================================================== #
            # ========== UNDO/REDO HISTORY ADDITION START ==========
            if moved_jpg_path:
                history_entry = {
                    "jpg_source": str(current_image_path),
                    "jpg_target": str(moved_jpg_path),
                    "raw_source": str(raw_path_before_move) if raw_path_before_move else None,
                    "raw_target": str(moved_raw_path) if moved_raw_path and raw_moved_successfully else None,
                    "index_before_move": image_list_index,
                    "mode": self.grid_mode # 이동 당시 모드 기록
                }
                self.add_move_history(history_entry)
            # ========== UNDO/REDO HISTORY ADDITION END ==========
            # ======================================================================== #


            # --- 그리드 뷰 업데이트 로직 (기존 코드 유지) ---
            current_page_image_count = min(num_cells, len(self.image_files) - self.grid_page_start_index)
            if self.current_grid_index >= current_page_image_count and current_page_image_count > 0:
                self.current_grid_index = current_page_image_count - 1

            if current_page_image_count == 0 and len(self.image_files) > 0:
                 self.grid_page_start_index = max(0, self.grid_page_start_index - num_cells)
                 self.current_grid_index = 0

            self.update_grid_view()

            if not self.image_files:
                self.grid_mode = "Off"
                self.grid_off_radio.setChecked(True)
                self.update_grid_view()
                # 미니맵 숨기기 추가
                if self.minimap_visible:
                    self.minimap_widget.hide()
                    self.minimap_visible = False
                self.show_themed_message_box(QMessageBox.Information, LanguageManager.translate("완료"), LanguageManager.translate("모든 이미지가 분류되었습니다."))

            self.update_counters()

        except Exception as e:
            self.show_themed_message_box(QMessageBox.Critical, LanguageManager.translate("에러"), f"{LanguageManager.translate('파일 이동 중 오류 발생')}: {str(e)}")
    
    def on_grid_cell_double_clicked(self, clicked_label, clicked_index):
        """그리드 셀 더블클릭 시 Grid Off 모드로 전환"""
        if self.grid_mode == "Off" or not self.grid_labels:
            return
        
        try:
            # 유효한 이미지가 있는 셀인지 확인
            current_page_image_count = min(len(self.grid_labels), len(self.image_files) - self.grid_page_start_index)
            
            if 0 <= clicked_index < current_page_image_count:
                # 해당 셀에 이미지가 있는지 확인
                if clicked_label.property("original_pixmap"):
                    # 현재 인덱스 저장 (Grid Off 모드로 전환 시 사용)
                    self.current_image_index = self.grid_page_start_index + clicked_index
                    
                    # 이미지 변경 시 강제 새로고침 플래그 설정
                    self.force_refresh = True
                    
                    # Fit 모드인 경우 기존 캐시 무효화
                    if self.zoom_mode == "Fit":
                        self.last_fit_size = (0, 0)
                        self.fit_pixmap_cache.clear()
                    
                    # 이전 그리드 모드 저장 (ESC로 돌아올 수 있게)
                    self.previous_grid_mode = self.grid_mode
                    
                    # Grid Off 모드로 변경
                    self.grid_mode = "Off"
                    self.grid_off_radio.setChecked(True)
                    
                    # Grid Off 모드로 변경 및 이미지 표시
                    self.update_grid_view()
                    
                    # 이미지 로더의 캐시 확인하여 이미 메모리에 있으면 즉시 적용을 시도
                    image_path = str(self.image_files[self.current_image_index])
                    if image_path in self.image_loader.cache:
                        cached_pixmap = self.image_loader.cache[image_path]
                        if cached_pixmap and not cached_pixmap.isNull():
                            # 캐시된 이미지가 있으면 즉시 적용 시도
                            self.original_pixmap = cached_pixmap
                            if self.zoom_mode == "Fit":
                                self.apply_zoom_to_image()
                    
                    # 줌 라디오 버튼 상태 업데이트 (활성화)
                    self.update_zoom_radio_buttons_state()
                    self.update_counter_layout() # 레이아웃 업데이트 호출
                    
                    # 이중 이벤트 방지를 위해 클릭 이벤트 상태 초기화
                    self.click_timer = None
        except Exception as e:
            logging.error(f"그리드 셀 더블클릭 처리 중 오류 발생: {e}")
        finally:
            self.update_counters()

    def image_mouse_double_click_event(self, event):
        """이미지 컨테이너 더블클릭 이벤트"""
        # Grid Off & Zoom Fit 모드에서 더블클릭 시 100% 확대
        if self.grid_mode == "Off" and self.zoom_mode == "Fit" and self.original_pixmap:
            # 더블클릭 위치 저장
            self.double_click_pos = event.position().toPoint()
            
            # 클릭한 지점을 중심으로 확대하기 위한 추가 계산
            # 현재 이미지 크기와 위치 계산
            scaled_pixmap = self.high_quality_resize_to_fit(self.original_pixmap)
            fit_width = scaled_pixmap.width()
            fit_height = scaled_pixmap.height()
            
            # 이미지 위치 (Fit 모드에서 이미지는 중앙 정렬됨)
            view_width = self.scroll_area.width()
            view_height = self.scroll_area.height()
            img_x = (view_width - fit_width) // 2
            img_y = (view_height - fit_height) // 2
            
            # 더블클릭 위치가 이미지 내부인지 확인
            click_x = self.double_click_pos.x() - img_x
            click_y = self.double_click_pos.y() - img_y
            
            if 0 <= click_x < fit_width and 0 <= click_y < fit_height:
                # 먼저 클릭 위치 중심 플래그를 설정
                self.center_on_click = True
                self.center_image = False  # center_image가 우선순위가 높으므로 False로 설정
                
                # 100% 줌 모드로 변경
                self.zoom_mode = "100%"  # 직접 모드 설정
                self.zoom_100_radio.setChecked(True)
                
                # 직접 zoom 처리 (on_zoom_changed 호출하지 않음)
                if self.original_pixmap and self.grid_mode == "Off":
                    self.apply_zoom_to_image()
                
                # 미니맵 업데이트
                self.toggle_minimap(self.minimap_toggle.isChecked())
                
        # 100% 또는 200% 모드에서 더블클릭 시 Fit으로 복귀
        elif self.grid_mode == "Off" and self.zoom_mode in ["100%", "200%"]:
            self.fit_radio.setChecked(True)
            self.on_zoom_changed(self.fit_radio)

    def reset_program_state(self):
        """프로그램 상태를 초기화 (Delete 키)"""
        reply = self.show_themed_message_box(QMessageBox.Question, 
                                    LanguageManager.translate("프로그램 초기화"),
                                    LanguageManager.translate("모든 설정과 로드된 파일을 초기화하시겠습니까?"),
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Undo/Redo 히스토리 초기화 추가
            self.move_history = []
            self.history_pointer = -1
            logging.info("프로그램 초기화: Undo/Redo 히스토리 초기화됨")

            # 모든 백그라운드 작업 취소
            logging.info("프로그램 초기화: 모든 백그라운드 작업 종료 중...")
            
            # 이미지 로더 작업 취소
            for future in self.image_loader.active_futures:
                future.cancel()
            self.image_loader.active_futures.clear()
            
            # 그리드 썸네일 생성 작업 취소
            for future in self.active_thumbnail_futures:
                future.cancel()
            self.active_thumbnail_futures.clear()
            
            # 로딩 인디케이터 타이머 중지 (있다면)
            if hasattr(self, 'loading_indicator_timer') and self.loading_indicator_timer.isActive():
                self.loading_indicator_timer.stop()
            
            # RAW 디코더 결과 처리 타이머 중지
            if hasattr(self, 'decoder_timer') and self.decoder_timer.isActive():
                self.decoder_timer.stop()
            
            # 현재 로딩 작업 취소
            if hasattr(self, '_current_loading_future') and self._current_loading_future:
                self._current_loading_future.cancel()
                self._current_loading_future = None
                
            # 리소스 매니저 작업 취소
            self.resource_manager.cancel_all_tasks()
            
            # 내부 변수 초기화 (가장 먼저 수행)
            self.current_folder = ""
            self.raw_folder = ""
            self.image_files = [] # 이미지 목록 비우기
            self.raw_files = {}
            self.current_image_index = -1
            self.is_raw_only_mode = False # <--- 명시적으로 RAW 모드 해제
            self.move_raw_files = True
            self.target_folders = ["", "", ""]
            self.folder_count = 3  # 항상 3개 폴더 사용
            self.zoom_mode = "Fit" # Zoom 모드 초기화
            self.grid_mode = "Off" # Grid 모드 초기화
            self.update_counter_layout() # 레이아웃 업데이트 호출
            self.grid_page_start_index = 0
            self.current_grid_index = 0
            self.previous_grid_mode = None
            self.original_pixmap = None # 원본 이미지 제거

            # 이미지 캐시 초기화
            self.fit_pixmap_cache.clear()
            self.image_loader.clear_cache()

            # --- 그리드 썸네일 캐시 및 백그라운드 작업 초기화 ---
            self.grid_thumbnail_cache_2x2.clear()  # 2x2 그리드 캐시 초기화
            self.grid_thumbnail_cache_3x3.clear()  # 3x3 그리드 캐시 초기화

            # --- UI 컨트롤 상태 설정 ---
            self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))
            self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
            for i in range(3):
                self.folder_path_labels[i].setText(LanguageManager.translate("폴더 경로"))

            self.update_folder_buttons() # 분류 폴더 UI 업데이트
            self.update_jpg_folder_ui_state() # JPG 폴더 UI 상태 업데이트
            self.update_raw_folder_ui_state() # RAW 폴더 UI 상태 업데이트

            # Zoom 라디오 버튼
            self.fit_radio.setChecked(True)

            # Grid 라디오 버튼
            self.grid_off_radio.setChecked(True)

            # RAW 토글 (update_raw_folder_ui_state 에서 처리됨)

            # 미니맵 토글 (상태는 유지하되, 숨김 처리)
            # self.minimap_toggle.setChecked(True) # 이전 상태 유지 또는 초기화 선택

            # --- UI 갱신 함수 호출 ---
            self.update_grid_view() # 이미지 뷰 초기화 (Grid Off 가정)
            self.update_zoom_radio_buttons_state()
            self.toggle_minimap(self.minimap_toggle.isChecked())
            self.update_file_info_display(None)
            self.update_counters() # 카운터 업데이트 (update_image_count_label 포함)
            self.update_window_title_with_selection() # 창 제목 초기화 (이미지 없으므로 기본 제목)
            self.update_match_raw_button_state()
            # ========== 패널 위치 및 크기 재적용 ==========
            QTimer.singleShot(0, self._apply_panel_position)
            # ==============================================

        else:
            logging.info("프로그램 초기화 취소됨")

    def setup_file_info_ui(self):
        """이미지 파일 정보 표시 UI 구성"""
        # 파일명 레이블 (커스텀 클래스 사용)
        # ========== UIScaleManager 적용 ==========
        filename_padding = UIScaleManager.get("filename_label_padding")
        self.info_filename_label = FilenameLabel("-", fixed_height_padding=filename_padding)
        self.info_filename_label.doubleClicked.connect(self.open_current_file_in_explorer)
        self.control_layout.addWidget(self.info_filename_label)

        # 정보 표시를 위한 레이블들 (왼쪽 정렬)
        # ========== UIScaleManager 적용 ==========
        info_padding = UIScaleManager.get("info_label_padding")
        info_label_style = f"color: #A8A8A8; padding-left: {info_padding}px;"
        info_font = QFont("Arial", UIScaleManager.get("font_size")) # 전역 폰트 크기 사용

        # 정보 레이블 공통 설정 함수
        def configure_info_label(label):
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            label.setStyleSheet(info_label_style)
            label.setFont(info_font)
            label.setWordWrap(False)  # 줄바꿈 방지
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)  # 텍스트 선택 가능
            # 가로 방향으로 고정된 크기 정책 설정 (확장 방지)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            # 말줄임표 설정 (오른쪽에 ... 표시)
            label.setTextFormat(Qt.PlainText)  # 일반 텍스트 형식 사용
            try:
                # Qt 6에서는 setElideMode가 없을 수 있음
                if hasattr(label, "setElideMode"):
                    label.setElideMode(Qt.ElideRight)
            except:
                pass

        # 정보 레이블 생성 및 설정 적용
        self.info_datetime_label = QLabel("-")
        configure_info_label(self.info_datetime_label)

        self.info_resolution_label = QLabel("-")
        configure_info_label(self.info_resolution_label)

        self.info_camera_label = QLabel("-")
        configure_info_label(self.info_camera_label)

        self.info_focal_label = QLabel("-")
        configure_info_label(self.info_focal_label)

        # 레이아웃에 위젯 추가 (요청된 순서대로)
        self.control_layout.addWidget(self.info_datetime_label)    # 1. 촬영 날짜
        self.control_layout.addWidget(self.info_resolution_label)  # 2. 해상도
        self.control_layout.addWidget(self.info_camera_label)      # 3. 카메라
        self.control_layout.addWidget(self.info_focal_label)       # 4. 초점거리

    def update_file_info_display(self, image_path):
        """파일 정보 표시 - 비동기 버전"""
        # 정보 초기화
        if not image_path:
            self.info_filename_label.setText("-")
            self.info_resolution_label.setText("-")
            self.info_camera_label.setText("-")
            self.info_datetime_label.setText("-")
            self.info_focal_label.setText("-")
            self.current_exif_path = None  # 현재 처리 중인 경로 초기화
            return
        
        # 파일명은 즉시 표시 (비동기 처리 필요 없음)
        filename = Path(image_path).name
        self.info_filename_label.setText(filename)
        
        # 현재 처리 중인 EXIF 경로 업데이트
        self.current_exif_path = image_path
        
        # 로딩 중 표시 (영어/한국어 언어 감지)
        loading_text = "▪ ···"
        self.info_resolution_label.setText(loading_text)
        self.info_camera_label.setText(loading_text)
        self.info_datetime_label.setText(loading_text)
        self.info_focal_label.setText(loading_text)
        
        # 캐시 확인
        if image_path in self.exif_cache:
            # 캐시에 있으면 바로 표시
            self.update_info_ui_from_exif(self.exif_cache[image_path], image_path)
            return
        
        # 캐시에 없으면 비동기 처리 시작
        # QMetaObject.invokeMethod 대신 시그널 사용
        self.exif_worker.request_process.emit(image_path)

    def on_exif_info_ready(self, exif_data, image_path):
        """ExifWorker에서 정보 추출 완료 시 호출"""
        # 캐시에 저장
        self.exif_cache[image_path] = exif_data
        
        # 현재 표시 중인 이미지와 일치하는지 확인
        if self.current_exif_path == image_path:
            # 현재 이미지에 대한 정보면 UI 업데이트
            self.update_info_ui_from_exif(exif_data, image_path)

    def on_exif_info_error(self, error_msg, image_path):
        """ExifWorker에서 오류 발생 시 호출"""
        logging.error(f"EXIF 정보 추출 오류 ({Path(image_path).name}): {error_msg}")
        
        # 현재 표시 중인 이미지와 일치하는지 확인
        if self.current_exif_path == image_path:
            # 오류 표시 (영어/한국어 언어 감지)
            error_text = "▪ Error" if LanguageManager.get_current_language() == "en" else "▪ 오류"
            self.info_resolution_label.setText(error_text)
            self.info_camera_label.setText(error_text)
            self.info_datetime_label.setText(error_text)
            self.info_focal_label.setText(error_text)

    def update_info_ui_from_exif(self, exif_data, image_path):
        """EXIF 데이터로 UI 레이블 업데이트"""
        try:
            # 해상도 정보 설정
            if self.original_pixmap and not self.original_pixmap.isNull():
                display_w = self.original_pixmap.width()
                display_h = self.original_pixmap.height()
                
                if exif_data["exif_resolution"]:
                    res_w, res_h = exif_data["exif_resolution"]
                    if display_w >= display_h:
                        resolution_text = f"▪ {res_w} x {res_h}"
                    else:
                        resolution_text = f"▪ {res_h} x {res_w}"
                    self.info_resolution_label.setText(resolution_text)
                else:
                    # QPixmap 크기 사용
                    if display_w >= display_h:
                        resolution_text = f"▪ {display_w} x {display_h}"
                    else:
                        resolution_text = f"▪ {display_h} x {display_w}"
                    self.info_resolution_label.setText(resolution_text)
            elif exif_data["exif_resolution"]:
                res_w, res_h = exif_data["exif_resolution"]
                if res_w >= res_h:
                    resolution_text = f"▪ {res_w} x {res_h}"
                else:
                    resolution_text = f"▪ {res_h} x {res_w}"
                self.info_resolution_label.setText(resolution_text)
            else:
                self.info_resolution_label.setText("▪ -")
            
            # 카메라 정보 설정
            make = exif_data["exif_make"]
            model = exif_data["exif_model"]
            camera_info = f"▪ {make} {model}".strip()
            self.info_camera_label.setText(camera_info if len(camera_info) > 2 else "▪ -")
            
            # 날짜 정보 설정
            datetime_str = exif_data["exif_datetime"]
            if datetime_str:
                try:
                    formatted_datetime = DateFormatManager.format_date(datetime_str)
                    self.info_datetime_label.setText(formatted_datetime)
                except Exception:
                    self.info_datetime_label.setText(f"▪ {datetime_str}")
            else:
                self.info_datetime_label.setText("▪ -")
            
            # 초점 거리 정보 설정
            focal_str = "▪ "
            focal_parts = []
            
            # 초점 거리
            if exif_data["exif_focal_mm"] is not None:
                if isinstance(exif_data["exif_focal_mm"], (int, float)):
                    focal_parts.append(f"{exif_data['exif_focal_mm']:.0f} mm")
                else:
                    focal_parts.append(exif_data["exif_focal_mm"])
                    if "mm" not in str(exif_data["exif_focal_mm"]).lower():
                        focal_parts[-1] += " mm"
            
            # 35mm 환산 초점 거리
            if exif_data["exif_focal_35mm"] is not None:
                focal_conversion = f"({LanguageManager.translate('환산')}: "
                if isinstance(exif_data["exif_focal_35mm"], (int, float)):
                    focal_conversion += f"{exif_data['exif_focal_35mm']:.0f} mm"
                else:
                    focal_conversion += str(exif_data["exif_focal_35mm"])
                    if "mm" not in str(exif_data["exif_focal_35mm"]).lower():
                        focal_conversion += " mm"
                focal_conversion += ")"
                focal_parts.append(focal_conversion)
            
            if focal_parts:
                focal_str += " ".join(focal_parts)
                self.info_focal_label.setText(focal_str)
            else:
                self.info_focal_label.setText("▪ -")

        except Exception as e:
            logging.error(f"EXIF 정보 UI 업데이트 오류: {e}")
            # 에러가 발생해도 기본 정보는 표시 시도
            self.info_resolution_label.setText("▪ -")
            self.info_camera_label.setText("▪ -")
            self.info_datetime_label.setText("▪ -")
            self.info_focal_label.setText("▪ -")


    def open_current_file_in_explorer(self, filename):
        """전달받은 파일명을 현재 폴더 경로와 조합하여 파일 열기 (RAW 모드 지원)"""
        # --- 모드에 따라 기준 폴더 결정 ---
        if self.is_raw_only_mode:
            base_folder = self.raw_folder
        else:
            base_folder = self.current_folder
        # --- 결정 끝 ---

        if not base_folder or not filename: # 기준 폴더나 파일명이 없으면 중단
            logging.warning("기준 폴더 또는 파일명이 없어 파일을 열 수 없습니다.")
            return

        file_path = Path(base_folder) / filename # 올바른 기준 폴더 사용
        if not file_path.exists():
            logging.warning(f"파일을 찾을 수 없음: {file_path}")
            return

        try:
            if sys.platform == 'win32':
                os.startfile(str(file_path)) # 파일 경로 전달
            elif sys.platform == 'darwin':
                subprocess.run(['open', str(file_path)])
            else:
                subprocess.run(['xdg-open', str(file_path)])
        except Exception as e:
            logging.error(f"파일 열기 실패: {e}")

            # 사용자에게 오류 메시지 표시 (선택 사항)
            self.show_themed_message_box(
                QMessageBox.Warning,
                LanguageManager.translate("오류"),
                f"{LanguageManager.translate('파일 열기 실패')}: {filename}\n\n{LanguageManager.translate('연결된 프로그램이 없거나 파일을 열 수 없습니다.')}"
            )

    def display_current_image(self):
        """현재 선택된 이미지 표시 (비동기 방식)"""
        # 강제 새로고침 플래그 확인
        force_refresh = getattr(self, 'force_refresh', False)
        if force_refresh:
            # Fit 모드에서 캐시만 리셋하고 원본은 유지 (깜빡임 방지)
            self.last_fit_size = (0, 0)
            self.fit_pixmap_cache.clear()
            # 플래그 초기화
            self.force_refresh = False

        # 그리드 모드 또는 이미지 없는 경우 처리
        if self.grid_mode != "Off":
            self.update_grid_view()
            return

        if not self.image_files or self.current_image_index < 0 or self.current_image_index >= len(self.image_files):
            # 이미지 없을 때 빈 화면만 표시 (텍스트 제거)
            self.image_label.clear()
            self.image_label.setStyleSheet("background-color: transparent;")
            self.setWindowTitle("PhotoSort")
            self.original_pixmap = None
            self.update_file_info_display(None)
            
            # 방향 정보 초기화
            self.previous_image_orientation = None
            self.current_image_orientation = None

            # 미니맵 숨기기 추가
            if self.minimap_visible:
                self.minimap_widget.hide()
                self.minimap_visible = False
            return
                
        try:
            # 현재 이미지 정보 저장
            current_index = self.current_image_index
            image_path = self.image_files[current_index]
            
            # 파일 정보는 즉시 업데이트
            self.update_file_info_display(str(image_path))
            self.setWindowTitle(f"PhotoSort - {image_path.name}")
            
            # 이미 메모리에 있으면 즉시 적용 시도 추가
            cached_pixmap = self.image_loader.cache.get(str(image_path))
            if cached_pixmap and not cached_pixmap.isNull():
                print(f"캐시된 이미지 즉시 적용: {image_path.name}")
                
                # 이전 이미지 방향을 저장
                self.previous_image_orientation = self.current_image_orientation
                
                # 새 이미지의 방향 설정
                if cached_pixmap.width() >= cached_pixmap.height():
                    self.current_image_orientation = "landscape"
                else:
                    self.current_image_orientation = "portrait"
                    
                self.original_pixmap = cached_pixmap
                
                # 중요: 이미지를 명시적으로 갱신하기 위해 apply_zoom_to_image 호출
                self.apply_zoom_to_image()
                self.update_counters()
                
                # 미니맵 업데이트
                if self.minimap_visible and self.minimap_toggle.isChecked():
                    self.toggle_minimap(True)
                    
                # 이미 로드되었으므로 비동기 로딩 건너뛰기
                return
                
            # 지연된 로딩 인디케이터 설정 (기존 로직 유지)
            if not hasattr(self, 'loading_indicator_timer'):
                self.loading_indicator_timer = QTimer(self)
                self.loading_indicator_timer.setSingleShot(True)
                self.loading_indicator_timer.timeout.connect(self.show_loading_indicator)
            else:
                self.loading_indicator_timer.stop()
                    
            # 500ms 후에도 로딩이 완료되지 않으면 로딩 인디케이터 표시
            self.loading_indicator_timer.start(500)
            
            # 비동기 이미지 로딩 시작
            self.load_image_async(str(image_path), current_index)
            
        except Exception as e:
            self.image_label.setText(f"{LanguageManager.translate('이미지 표시 중 오류 발생')}: {str(e)}")
            self.original_pixmap = None
            self.update_counters()

    def show_loading_indicator(self):
        """로딩 중 표시"""
        # 로딩 플레이스홀더 표시
        loading_pixmap = QPixmap(200, 200)
        loading_pixmap.fill(QColor(40, 40, 40))
        self.image_label.setPixmap(loading_pixmap)
        self.image_label.setText(LanguageManager.translate("이미지 로드 중..."))
        self.image_label.setStyleSheet("color: white; background-color: transparent;")

    def load_image_async(self, image_path, requested_index):
        """이미지 비동기 로딩 (높은 우선순위)"""
        # 기존 작업 취소
        if hasattr(self, '_current_loading_future') and self._current_loading_future:
            self._current_loading_future.cancel()
        
        # 우선순위 높음으로 현재 이미지 로딩 시작
        self._current_loading_future = self.resource_manager.submit_imaging_task_with_priority(
            'high',  # 높은 우선순위
            self._load_image_task,
            image_path,
            requested_index
        )
        
        # 인접 이미지 미리 로드 시작
        self.preload_adjacent_images(requested_index)

    def _load_image_task(self, image_path, requested_index):
        """백그라운드 스레드에서 실행되는 이미지 로딩 작업"""
        try:
            # 이미지 로드
            pixmap = self.image_loader.load_image_with_orientation(image_path)
            
            # QTimer.singleShot 대신 시그널 사용
            self.image_loader.loadCompleted.emit(pixmap, image_path, requested_index)
            return True
        except Exception as e:
            logging.error(f"이미지 로드 작업 오류: {e}")
            # 오류도 시그널로 전달
            self.image_loader.loadFailed.emit(str(e), image_path, requested_index)
            return False

    def _on_image_loaded_for_display(self, pixmap, image_path, requested_index):
        """이미지 로드 완료 후 UI 스레드에서 실행"""
        # 요청 시점의 인덱스와 현재 인덱스 비교 (이미지 변경 여부 확인)
        if self.current_image_index != requested_index:
            print(f"이미지가 변경되어 로드 결과 무시: 요청={requested_index}, 현재={self.current_image_index}")
            return
        
        # 로딩 인디케이터 타이머 중지
        if hasattr(self, 'loading_indicator_timer'):
            self.loading_indicator_timer.stop()
            
        if pixmap.isNull():
            self.image_label.setText(f"{LanguageManager.translate('이미지 로드 실패')}")
            self.original_pixmap = None
            return
            
        # 로딩 성공 처리
        # 이전 이미지 방향을 저장
        self.previous_image_orientation = self.current_image_orientation
        
        # 새 이미지의 방향 설정
        if pixmap.width() >= pixmap.height():
            self.current_image_orientation = "landscape"
        else:
            self.current_image_orientation = "portrait"
            
        self.original_pixmap = pixmap
        
        # Zoom 모드 적용
        self.apply_zoom_to_image()
        
        # 미니맵 업데이트
        if self.minimap_toggle.isChecked():
            self.toggle_minimap(True)
            
        self.update_counters()


    def preload_adjacent_images(self, current_index):
        """인접 이미지 미리 로드 - 스마트 로딩 시스템"""
        if not self.image_files:
            return
        
        total_images = len(self.image_files)
        
        # 이동 방향 감지 (이전과 동일)
        direction = 1  # 기본값: 앞으로 이동
        if hasattr(self, 'previous_image_index'):
            if self.previous_image_index < current_index:
                direction = 1  # 앞으로 이동 중
            elif self.previous_image_index > current_index:
                direction = -1  # 뒤로 이동 중
        
        # 현재 인덱스 저장 (다음 호출에서 방향 감지용)
        self.previous_image_index = current_index
        
        # 1. 이미지 로더 캐시 상태 확인
        cached_images = set()
        requested_images = set()  # 이미 요청된 이미지들
        
        # 현재 캐시에 있는 이미지 확인
        for i in range(max(0, current_index - 3), min(total_images, current_index + 8)):
            img_path = str(self.image_files[i])
            if img_path in self.image_loader.cache:
                cached_images.add(i)
        
        # 2. 우선적으로 로드해야 할 이미지 결정
        # 앞으로 최대 6개, 뒤로 최대 2개의 이미지 로드
        to_preload = []
        
        # 앞으로 이동 중이면 앞쪽을 더 많이 로드
        if direction >= 0:
            # 앞쪽 6개
            for offset in range(1, 7):
                idx = (current_index + offset) % total_images
                if idx not in cached_images:
                    to_preload.append((idx, "forward", offset))
            
            # 뒤쪽 2개
            for offset in range(1, 3):
                idx = (current_index - offset) % total_images
                if idx not in cached_images:
                    to_preload.append((idx, "backward", offset))
        else:
            # 뒤로 이동 중이면 뒤쪽을 더 많이 로드
            # 뒤쪽 6개
            for offset in range(1, 7):
                idx = (current_index - offset) % total_images
                if idx not in cached_images:
                    to_preload.append((idx, "backward", offset))
            
            # 앞쪽 2개
            for offset in range(1, 3):
                idx = (current_index + offset) % total_images
                if idx not in cached_images:
                    to_preload.append((idx, "forward", offset))
        
        # 3. 우선순위에 따라 로드 요청
        for idx, direction_type, offset in to_preload:
            img_path = str(self.image_files[idx])
            if img_path in requested_images:
                continue
            
            # 우선순위 결정
            if direction_type == "forward":
                if offset <= 3:
                    priority = 'high'  # 앞으로 가까운 이미지
                else:
                    priority = 'medium'  # 앞으로 먼 이미지
            else:  # backward
                if offset <= 2:
                    priority = 'medium'  # 뒤로 가까운 이미지
                else:
                    priority = 'low'  # 뒤로 먼 이미지
            
            # 로드 요청 제출
            self.resource_manager.submit_imaging_task_with_priority(
                priority,
                self.image_loader._preload_image,
                img_path
            )
            
            requested_images.add(img_path)
            
            # 디버그 정보 추가
            if offset <= 3:
                logging.debug(f"Preloading: {direction_type} {offset} (priority: {priority}): {Path(img_path).name}")

    def on_grid_cell_clicked(self, clicked_label, clicked_index):
        """그리드 셀 클릭 이벤트 핸들러"""
        if self.grid_mode == "Off" or not self.grid_labels:
            return

        try:
            current_page_image_count = min(len(self.grid_labels), len(self.image_files) - self.grid_page_start_index)

            if 0 <= clicked_index < current_page_image_count:
                if clicked_label.property("original_pixmap"):
                    self.current_grid_index = clicked_index
                    self.update_grid_selection_border()
                    self.update_window_title_with_selection()

                    # 선택된 셀의 이미지 정보 업데이트
                    image_list_index = self.grid_page_start_index + self.current_grid_index
                    if 0 <= image_list_index < len(self.image_files):
                        selected_image_path = str(self.image_files[image_list_index])
                        self.update_file_info_display(selected_image_path)
                    else:
                        self.update_file_info_display(None) # 유효하지 않으면 초기화
                else:
                    print("빈 셀 클릭됨")
                    self.update_file_info_display(None) # 빈 셀 클릭 시 정보 초기화
            else:
                 print(f"유효하지 않은 셀 클릭됨: index {clicked_index}, image_count {current_page_image_count}")
                 self.update_file_info_display(None) # 유효하지 않은 셀 클릭 시 정보 초기화

        except Exception as e:
             logging.error(f"셀 클릭 처리 중 오류 발생: {e}")
             self.update_file_info_display(None) # 오류 시 초기화

    def update_image_count_label(self):
        """이미지 및 페이지 카운트 레이블 업데이트"""
        total = len(self.image_files)
        text = "- / -" # 기본값

        if total > 0:
            current_display_index = -1
            if self.grid_mode != "Off":
                # Grid 모드: 이미지 카운트와 페이지 정보 함께 표시
                selected_image_list_index = self.grid_page_start_index + self.current_grid_index
                if 0 <= selected_image_list_index < total:
                    current_display_index = selected_image_list_index + 1

                rows, cols = (2, 2) if self.grid_mode == '2x2' else (3, 3)
                num_cells = rows * cols
                total_pages = (total + num_cells - 1) // num_cells
                current_page = (self.grid_page_start_index // num_cells) + 1

                count_part = f"{current_display_index} / {total}" if current_display_index != -1 else f"- / {total}"
                page_part = f"Pg. {current_page} / {total_pages}"
                text = f"{count_part} ({page_part})"

            else:
                # Grid Off 모드: 이미지 카운트만 표시
                if 0 <= self.current_image_index < total:
                    current_display_index = self.current_image_index + 1
                text = f"{current_display_index} / {total}" if current_display_index != -1 else f"- / {total}"

        self.image_count_label.setText(text)

    def update_counters(self):
        """이미지 카운터 레이블 업데이트"""
        self.update_image_count_label()

    def get_script_dir(self):
        """실행 파일 또는 스크립트의 디렉토리를 반환"""
        if getattr(sys, 'frozen', False):
            # PyInstaller 등으로 패키징된 경우
            return Path(sys.executable).parent
        else:
            # 일반 스크립트로 실행된 경우
            return Path(__file__).parent

    def save_state(self):
        """현재 애플리케이션 상태를 JSON 파일에 저장"""
        state_data = {
            "current_folder": str(self.current_folder) if self.current_folder else "",
            "raw_folder": str(self.raw_folder) if self.raw_folder else "",
            # raw_files: Path 객체를 문자열로 변환하여 저장
            "raw_files": {k: str(v) for k, v in self.raw_files.items()},
            "move_raw_files": self.move_raw_files,
            "target_folders": [str(f) if f else "" for f in self.target_folders],
            # folder_count는 저장하지 않음 (항상 3개 사용)
            "zoom_mode": self.zoom_mode,
            "minimap_visible": self.minimap_toggle.isChecked(), # 체크박스 상태 저장
            "grid_mode": self.grid_mode,
            "current_image_index": self.current_image_index,
            "current_grid_index": self.current_grid_index,
            "grid_page_start_index": self.grid_page_start_index,
            "previous_grid_mode": self.previous_grid_mode,
            "language": LanguageManager.get_current_language(),
            "date_format": DateFormatManager.get_current_format(),
            "theme": ThemeManager.get_current_theme_name(),
            "is_raw_only_mode": self.is_raw_only_mode,
            "control_panel_on_right": getattr(self, 'control_panel_on_right', False),
            "raw_strategy": RawProcessingStrategyManager.get_current_strategy(),  # RAW 처리 전략 저장
        }

        save_path = self.get_script_dir() / self.STATE_FILE
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=4, ensure_ascii=False)
            logging.info(f"상태 저장 완료: {save_path}")
        except Exception as e:
            logging.error(f"상태 저장 실패: {e}")

    def load_state(self):
        """JSON 파일에서 애플리케이션 상태 불러오기"""
        logging.warning(f"111111")

        load_path = self.get_script_dir() / self.STATE_FILE

        # 첫 실행 감지 - 상태 파일이 없을 때
        is_first_run = not load_path.exists()

        if is_first_run:
            logging.info("첫 실행 감지: 초기 상태로 설정합니다.")
            # 상태 파일 없을 때도 초기 UI 상태 업데이트
            self.update_jpg_folder_ui_state()
            self.update_raw_folder_ui_state()
            # 첫 실행 설정 팝업 표시
            self.show_first_run_settings_popup()
            return

        try:
            with open(load_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            logging.info(f"상태 불러오기 완료: {load_path}")
            logging.warning(f"22222")
            logging.warning(f"로드된 상태 데이터(파일 경로: {load_path}): {loaded_data}")

            # 먼저 설정 부터 복원
            language = loaded_data.get("language", "ko")
            date_format = loaded_data.get("date_format", "yyyy-mm-dd")
            theme = loaded_data.get("theme", "default")
            raw_strategy = loaded_data.get("raw_strategy", "high_quality")  # RAW 처리 전략 로드
            
            # 설정 적용
            LanguageManager.set_language(language)
            DateFormatManager.set_date_format(date_format)
            ThemeManager.set_theme(theme)
            RawProcessingStrategyManager.set_strategy(raw_strategy)  # RAW 처리 전략 적용
            logging.warning(f"22222")
            logging.warning(f"RawProcessingStrategyManager 현재 전략(파일 경로: {load_path}): {RawProcessingStrategyManager.get_current_strategy()}")

            # ========== 컨트롤 패널 위치 로드 ==========
            # UI 업데이트 전에 상태 변수 먼저 로드
            self.control_panel_on_right = loaded_data.get("control_panel_on_right", False)
            logging.info(f"load_state: 컨트롤 패널 오른쪽 로드됨 = {self.control_panel_on_right}")
            # ==========================================

            # 내부 변수 복원 (오류 방지를 위해 .get 사용)
            loaded_current_folder = loaded_data.get("current_folder", "")
            self.raw_folder = loaded_data.get("raw_folder", "")
            # raw_files: 문자열 경로를 다시 Path 객체로 변환
            raw_files_str = loaded_data.get("raw_files", {})
            # 값(경로 문자열)이 존재하고, 해당 경로가 실제로 존재하는지 확인 후 Path 객체로 변환
            self.raw_files = {k: Path(v) for k, v in raw_files_str.items() if v and Path(v).exists()}

            # self.move_raw_files 는 update_raw_toggle_state 에서 사용됨
            self.move_raw_files = loaded_data.get("move_raw_files", True)
            loaded_target_folders = loaded_data.get("target_folders", ["", "", ""])
            self.target_folders = [f for f in loaded_target_folders] # 복사본 생성

            # 항상 3개 폴더 사용 (folder_count 로드 안 함)
            self.folder_count = 3

            self.zoom_mode = loaded_data.get("zoom_mode", "Fit")
            minimap_visible_loaded = loaded_data.get("minimap_visible", True)
            self.grid_mode = loaded_data.get("grid_mode", "Off")
            self.is_raw_only_mode = loaded_data.get("is_raw_only_mode", False)
            # current_image_index 등은 이미지 로드 후 유효성 검사 필요
            loaded_current_image_index = loaded_data.get("current_image_index", -1)
            loaded_current_grid_index = loaded_data.get("current_grid_index", 0)
            loaded_grid_page_start_index = loaded_data.get("grid_page_start_index", 0)
            self.previous_grid_mode = loaded_data.get("previous_grid_mode", None)
            
            self.current_folder = loaded_current_folder

            # --- 중요: 상태 변수 복원 후, 이미지 로드 전에 UI 상태 업데이트 ---
            # 폴더 경로 UI 업데이트 (폴더 유효성 검사는 load_images_from_folder 등에서 수행)
            self.folder_path_label.setText(loaded_current_folder if loaded_current_folder else LanguageManager.translate("폴더 경로"))
            self.raw_folder_path_label.setText(self.raw_folder if self.raw_folder else LanguageManager.translate("폴더 경로"))
            # 분류 폴더 레이블 업데이트
            for i, folder in enumerate(self.target_folders):
                self.folder_path_labels[i].setText(folder if folder else LanguageManager.translate("폴더 경로"))

            # 기타 UI 컨트롤 상태 업데이트 (버튼 텍스트/활성화, 토글 등)
            self.update_jpg_folder_ui_state() # 여기서 folder_path_label 스타일/활성화 재설정
            self.update_raw_folder_ui_state() # 여기서 raw_folder_path_label 스타일/활성화 재설정 및 토글 상태 업데이트
            self.update_folder_buttons()      # 여기서 분류 폴더 레이블 스타일/활성화 재설정
            self.update_match_raw_button_state() # <--- 버튼 텍스트/상태 업데이트 호출!
            self.update_zoom_radio_buttons_state() # Grid 모드에 따라 Zoom 버튼 상태 조정

            # Zoom 라디오 버튼 업데이트
            if self.zoom_mode == "Fit": self.fit_radio.setChecked(True)
            elif self.zoom_mode == "100%": self.zoom_100_radio.setChecked(True)
            elif self.zoom_mode == "200%": self.zoom_200_radio.setChecked(True)

            # Grid 라디오 버튼 업데이트
            if self.grid_mode == "Off": self.grid_off_radio.setChecked(True)
            elif self.grid_mode == "2x2": self.grid_2x2_radio.setChecked(True)
            elif self.grid_mode == "3x3": self.grid_3x3_radio.setChecked(True)

            # 미니맵 토글 업데이트
            self.minimap_toggle.setChecked(minimap_visible_loaded)

            # --- 이미지 목록 로드 (RAW 모드 우선 확인) ---
            images_loaded_successfully = False
            if self.is_raw_only_mode: # <--- RAW 모드인지 먼저 확인
                # RAW 모드 상태 복원 시도
                if self.raw_folder and Path(self.raw_folder).is_dir():
                    print(f"저장된 상태(RAW 모드) 복원 시도: {self.raw_folder}")
                    images_loaded_successfully = self.reload_raw_files_from_state(self.raw_folder)
                    if not images_loaded_successfully:
                        logging.warning("RAW 파일 리로드 실패. 모드를 초기화합니다.")
                        self.is_raw_only_mode = False # 실패 시 모드 리셋
                        self.raw_folder = ""          # RAW 폴더 정보도 클리어
                        self.image_files = []         # 이미지 목록 클리어
                        self.update_raw_folder_ui_state() # 관련 UI 업데이트
                        self.update_match_raw_button_state()
                else:
                    # RAW 모드였지만 폴더 정보가 유효하지 않은 경우
                    logging.warning("저장된 RAW 폴더 경로가 유효하지 않아 모드를 초기화합니다.")
                    self.is_raw_only_mode = False # 모드 리셋
                    self.raw_folder = ""          # RAW 폴더 정보 클리어
                    self.image_files = []         # 이미지 목록 클리어
                    self.update_raw_folder_ui_state() # 관련 UI 업데이트
                    self.update_match_raw_button_state()

            # elif는 RAW 모드가 아니고, 저장된 JPG 폴더 경로(loaded_current_folder)가 유효할 때 실행되어야 합니다.
            elif not self.is_raw_only_mode and loaded_current_folder and Path(loaded_current_folder).is_dir(): # <--- loaded_current_folder 사용으로 수정
                 # JPG 모드 상태 복원 시도 (RAW 모드가 아닐 때)
                print(f"저장된 상태(JPG 모드) 복원 시도: {loaded_current_folder}")
                # loaded_current_folder 경로로 이미지를 로드합니다.
                # load_images_from_folder 내부에서 self.current_folder가 설정됩니다.
                images_loaded_successfully = self.load_images_from_folder(loaded_current_folder) # <--- 로드 함수에 loaded_current_folder 전달

            # else: 로드할 폴더 정보가 없는 경우 images_loaded_successfully = False 유지

            # --- 중요: 뷰 상태 복원 (이미지 로드 성공 시) ---
            if images_loaded_successfully:
                total_images = len(self.image_files)

                # 저장된 인덱스 로드 (뷰 상태 복원 전에 로드해야 함)
                loaded_current_image_index = loaded_data.get("current_image_index", -1)
                loaded_current_grid_index = loaded_data.get("current_grid_index", 0)
                loaded_grid_page_start_index = loaded_data.get("grid_page_start_index", 0)

                if self.grid_mode != "Off":
                    # Grid 모드 상태 복원
                    rows, cols = (2, 2) if self.grid_mode == '2x2' else (3, 3)
                    num_cells = rows * cols
                    max_page_start_index = ((total_images + num_cells - 1) // num_cells - 1) * num_cells
                    if loaded_grid_page_start_index >= 0 and loaded_grid_page_start_index % num_cells == 0 and loaded_grid_page_start_index <= max_page_start_index:
                       self.grid_page_start_index = loaded_grid_page_start_index
                    else:
                       self.grid_page_start_index = 0 # 유효하지 않으면 0
                    current_page_image_count = min(num_cells, total_images - self.grid_page_start_index)
                    if loaded_current_grid_index >= 0 and loaded_current_grid_index < current_page_image_count:
                        self.current_grid_index = loaded_current_grid_index
                    else:
                        self.current_grid_index = 0 # 유효하지 않으면 0

                    self.update_grid_view() # Grid 뷰 표시

                else:
                    # Grid Off 모드 상태 복원
                    if loaded_current_image_index >= 0 and loaded_current_image_index < total_images:
                        self.current_image_index = loaded_current_image_index
                    elif total_images > 0:
                        self.current_image_index = 0 # 유효하지 않지만 이미지 있으면 0
                    else:
                        self.current_image_index = -1 # 이미지 없으면 -1

                    self.display_current_image() # 단일 이미지 표시

                # 카운터 및 미니맵 업데이트 (로드 성공 후)
                self.update_counter_layout() # 레이아웃 재조정 및 카운터 업데이트
                self.toggle_minimap(self.minimap_toggle.isChecked()) # 미니맵 상태 복원

                # Grid Off 모드이고 이미지 로딩 성공 시 백그라운드 로딩 시작
                if self.grid_mode == "Off":
                    self.start_background_image_preloading()

            else:
                # 이미지 로드 실패 또는 로드할 폴더 없음 (기존 로직 유지)
                logging.warning("이미지 목록 로드 실패 또는 대상 폴더 없음. 초기 화면 표시.")
                self.image_files = []
                self.current_image_index = -1
                self.current_grid_index = 0
                self.grid_page_start_index = 0
                if self.grid_mode != "Off":
                    self.grid_mode = "Off"
                    self.grid_off_radio.setChecked(True)
                    self.update_zoom_radio_buttons_state()
                self.update_grid_view()
                self.update_file_info_display(None)
                self.update_counter_layout()
                self.toggle_minimap(False)
                # --- 중요: 모든 상태 로드 및 이미지 로드 시도 후 최종 레이아웃 적용 ---
                # ========== 초기 패널 위치 및 크기 적용 ==========
                # 위젯 추가는 __init__에서 조건부로 이미 처리되었거나 여기서 다시 처리 필요
                # 여기서는 _apply_panel_position 호출하여 순서 및 크기 재조정
                QTimer.singleShot(0, self._apply_panel_position) # 이벤트 루프 시작 후 실행되도록 Timer 사용
                # =============================================

            # load_state 끝에서 포커스 설정 등 필요한 마무리 작업
            self.setFocus()


        except json.JSONDecodeError as e:
            error_msg = LanguageManager.translate("저장된 상태 파일을 읽는 중 오류가 발생했습니다. 기본 설정으로 시작합니다.")
            logging.error(f"상태 파일 읽기 오류 (JSON 형식): {e}")
            self.show_themed_message_box(QMessageBox.Warning, 
                                        LanguageManager.translate("상태 로드 오류"), 
                                        error_msg)
        except Exception as e:
            error_msg = LanguageManager.translate("상태를 불러오는 중 오류가 발생했습니다")
            logging.error(f"상태 불러오기 중 예상치 못한 오류: {e}")
            self.show_themed_message_box(QMessageBox.Critical, 
                                        LanguageManager.translate("상태 로드 오류"), 
                                        f"{error_msg}: {e}")
        # self.showMaximized()

    def reload_raw_files_from_state(self, folder_path):
        """ 저장된 RAW 폴더 경로에서 파일 목록을 다시 로드 """
        target_path = Path(folder_path)
        temp_raw_file_list = []
        try:
            # RAW 파일 검색
            for ext in self.raw_extensions:
                temp_raw_file_list.extend(target_path.glob(f'*{ext}'))
                temp_raw_file_list.extend(target_path.glob(f'*{ext.upper()}'))

            # 중복 제거 및 정렬
            unique_raw_files = sorted(list(set(temp_raw_file_list)))

            if unique_raw_files:
                self.image_files = unique_raw_files # 메인 리스트 업데이트
                print(f"RAW 파일 목록 복원됨: {len(self.image_files)}개")
                return True # 성공
            else:
                logging.warning(f"경고: RAW 폴더({folder_path})에서 파일을 찾지 못했습니다.")
                return False # 실패
        except Exception as e:
            logging.error(f"RAW 파일 목록 리로드 중 오류 발생: {e}")
            return False # 실패

    def add_move_history(self, move_info):
        """ 파일 이동 기록을 히스토리에 추가하고 포인터 업데이트 """
        logging.debug(f"Adding to history: {move_info}") # 디버깅 로그

        # 현재 포인터 이후의 기록(Redo 가능한 기록)은 삭제
        if self.history_pointer < len(self.move_history) - 1:
            self.move_history = self.move_history[:self.history_pointer + 1]

        # 새 기록 추가
        self.move_history.append(move_info)

        # 히스토리 최대 개수 제한
        if len(self.move_history) > self.max_history:
            self.move_history.pop(0) # 가장 오래된 기록 제거

        # 포인터를 마지막 기록으로 이동
        self.history_pointer = len(self.move_history) - 1
        logging.debug(f"History pointer updated to: {self.history_pointer}") # 디버깅 로그
        logging.debug(f"Current history length: {len(self.move_history)}") # 디버깅 로그

    def undo_move(self):
        """ 마지막 파일 이동 작업을 취소 (Undo) """
        if self.history_pointer < 0:
            logging.warning("Undo: 히스토리 없음")
            return # 실행 취소할 작업 없음

        # 현재 포인터에 해당하는 기록 가져오기
        move_info = self.move_history[self.history_pointer]
        logging.debug(f"Undoing: {move_info}") # 디버깅 로그

        jpg_source_path = Path(move_info["jpg_source"])
        jpg_target_path = Path(move_info["jpg_target"])
        raw_source_path = Path(move_info["raw_source"]) if move_info["raw_source"] else None
        raw_target_path = Path(move_info["raw_target"]) if move_info["raw_target"] else None
        index_before_move = move_info["index_before_move"]
        mode_before_move = move_info.get("mode", "Off") # 이전 모드 가져오기 (없으면 Off)

        try:
            # 1. JPG 파일 원래 위치로 이동
            #    이동 전 경로에 파일이 이미 있는지 확인 (덮어쓰기 방지 또는 다른 처리 필요 시)
            if jpg_source_path.exists():
                logging.warning(f"경고: Undo 대상 위치에 이미 파일 존재: {jpg_source_path}")
                # 필요시 파일명 변경 로직 추가
                # 여기서는 일단 덮어쓰도록 진행 (shutil.move는 기본적으로 덮어씀)
                # 또는 사용자에게 확인 요청

            # 대상 폴더(이동되었던 곳)에 파일이 있는지 확인 후 이동
            if jpg_target_path.exists():
                shutil.move(str(jpg_target_path), str(jpg_source_path))
                logging.debug(f"Undo: Moved {jpg_target_path} -> {jpg_source_path}")
            else:
                logging.warning(f"경고: Undo할 파일이 대상 위치에 없음: {jpg_target_path}")
                # 파일이 없다면 히스토리 포인터만 이동하고 종료할 수 있음
                # self.history_pointer -= 1
                # return

            # 2. RAW 파일 원래 위치로 이동 (존재하고, 이동되었었다면)
            if raw_source_path and raw_target_path:
                if raw_source_path.exists():
                    logging.warning(f"경고: Undo RAW 대상 위치에 이미 파일 존재: {raw_source_path}")
                    
                if raw_target_path.exists():
                    shutil.move(str(raw_target_path), str(raw_source_path))
                    logging.debug(f"Undo: Moved RAW {raw_target_path} -> {raw_source_path}")
                else:
                    logging.warning(f"경고: Undo할 RAW 파일이 대상 위치에 없음: {raw_target_path}")

            # 3. 파일 목록 복원 (self.image_files)
            #    인덱스 유효성 검사 후 삽입
            if 0 <= index_before_move <= len(self.image_files):
                self.image_files.insert(index_before_move, jpg_source_path)
            else:
                # 인덱스가 잘못된 경우 맨 끝에 추가하거나 오류 처리
                logging.warning(f"경고: Undo 시 잘못된 인덱스({index_before_move}), 파일 목록 끝에 추가합니다.")
                self.image_files.append(jpg_source_path)
                index_before_move = len(self.image_files) - 1  # 추가된 위치를 새 인덱스로 사용

            # 4. RAW 파일 딕셔너리 복원 (self.raw_files)
            if raw_source_path: # RAW 파일이 원래 있었다면
                self.raw_files[jpg_source_path.stem] = raw_source_path

            # 5. 히스토리 포인터 이동
            self.history_pointer -= 1
            logging.debug(f"Undo complete. History pointer: {self.history_pointer}") # 디버깅 로그

            # 6. UI 업데이트
            #    복원된 이미지를 선택 및 표시하도록 변경
            if mode_before_move == "Off":
                # 복원된 이미지 위치로 이동하도록 인덱스 설정
                self.current_image_index = index_before_move  # 원래 인덱스로 복원
                
                # Grid 모드일 경우 Grid Off로 전환
                if self.grid_mode != "Off":
                    self.grid_mode = "Off"
                    self.grid_off_radio.setChecked(True)
                    self.update_zoom_radio_buttons_state()
                    self.update_counter_layout()
                    
                # 이미지 강제 새로고침 설정
                self.force_refresh = True
                
                # Fit 모드인 경우 기존 캐시 무효화 추가
                if self.zoom_mode == "Fit":
                    self.last_fit_size = (0, 0)
                    self.fit_pixmap_cache.clear()
                    
                self.display_current_image()  # 복원된 이미지 표시
                
            else:  # Grid 모드에서 이동했었다면
                rows, cols = (2, 2) if mode_before_move == '2x2' else (3, 3)
                num_cells = rows * cols
                self.grid_page_start_index = (index_before_move // num_cells) * num_cells
                self.current_grid_index = index_before_move % num_cells
                
                # 현재 Grid 모드가 이전과 다르다면 변경
                if self.grid_mode != mode_before_move:
                    self.grid_mode = mode_before_move
                    if mode_before_move == "2x2":
                        self.grid_2x2_radio.setChecked(True)
                    elif mode_before_move == "3x3":
                        self.grid_3x3_radio.setChecked(True)
                    self.update_zoom_radio_buttons_state()
                    self.update_counter_layout()
                    
                # 강제 새로고침 플래그 설정
                self.force_refresh = True
                    
                self.update_grid_view()  # 그리드 뷰 업데이트 및 복원된 이미지 선택

            self.update_counters()  # 카운터 업데이트

        except Exception as e:
            self.show_themed_message_box(QMessageBox.Critical, LanguageManager.translate("에러"), f"{LanguageManager.translate('실행 취소 중 오류 발생')}: {str(e)}")
            # 오류 발생 시 히스토리 포인터는 그대로 두거나, 사용자에게 알림

    def redo_move(self):
            """ 취소된 파일 이동 작업을 다시 실행 (Redo) """
            if self.history_pointer >= len(self.move_history) - 1:
                print("Redo: 히스토리 없음")
                return # 다시 실행할 작업 없음

            # 다음 포인터로 이동하고 해당 기록 가져오기
            self.history_pointer += 1
            move_info = self.move_history[self.history_pointer]
            logging.debug(f"Redoing: {move_info}") # 디버깅 로그

            jpg_source_path = Path(move_info["jpg_source"])
            jpg_target_path = Path(move_info["jpg_target"])
            raw_source_path = Path(move_info["raw_source"]) if move_info["raw_source"] else None
            raw_target_path = Path(move_info["raw_target"]) if move_info["raw_target"] else None
            # index_before_move = move_info["index_before_move"] # Redo 시에는 이 인덱스를 직접 사용하지 않음
            mode_at_move = move_info.get("mode", "Off") # 이동이 발생했던 모드

            try:
                # 1. JPG 파일 다시 대상 위치로 이동
                #    대상 위치에 파일 존재 여부 확인 (덮어쓰기 또는 처리)
                if jpg_target_path.exists():
                    logging.warning(f"경고: Redo 대상 위치에 이미 파일 존재: {jpg_target_path}")
                    # 처리 로직 추가 또는 덮어쓰기 진행

                # 소스 위치에 파일이 있는지 확인 후 이동
                if jpg_source_path.exists():
                    shutil.move(str(jpg_source_path), str(jpg_target_path))
                    logging.debug(f"Redo: Moved {jpg_source_path} -> {jpg_target_path}")
                else:
                    logging.warning(f"경고: Redo할 원본 파일이 없음: {jpg_source_path}")
                    # 파일이 없다면 히스토리 포인터 되돌리고 종료
                    # self.history_pointer -= 1
                    # return

                # 2. RAW 파일 다시 대상 위치로 이동 (존재하고, 이동되었었다면)
                if raw_source_path and raw_target_path:
                    if raw_target_path.exists():
                        logging.warning(f"경고: Redo 대상 RAW 위치에 이미 파일 존재: {raw_target_path}")
                        # 처리 로직 추가 또는 덮어쓰기 진행
                    if raw_source_path.exists():
                        shutil.move(str(raw_source_path), str(raw_target_path))
                        logging.debug(f"Redo: Moved RAW {raw_source_path} -> {raw_target_path}")
                    else:
                        logging.warning(f"경고: Redo할 원본 RAW 파일이 없음: {raw_source_path}")

                # 3. 파일 목록 업데이트 (self.image_files)
                #    경로 기반으로 제거 시도
                try:
                    self.image_files.remove(jpg_source_path)
                except ValueError:
                    logging.warning(f"경고: Redo 시 파일 목록에서 경로를 찾지 못함: {jpg_source_path}")
                    # 필요 시 다른 방법으로 목록 갱신

                # 4. RAW 파일 딕셔너리 업데이트 (self.raw_files)
                if raw_source_path: # RAW 파일이 원래 있었다면
                    if jpg_source_path.stem in self.raw_files:
                        # Redo 시에는 이동되었으므로 raw_files 딕셔너리에서 제거
                        del self.raw_files[jpg_source_path.stem]

                logging.debug(f"Redo complete. History pointer: {self.history_pointer}") # 디버깅 로그

                # 5. UI 업데이트
                #    Redo 후의 상태에 맞게 업데이트 (이동 후 로직과 유사)
                if self.image_files:
                    # 현재 인덱스를 Redo된 파일이 제거된 후의 유효한 위치로 조정
                    # 간단하게는, 제거된 인덱스 또는 그 이전 인덱스를 가리키도록 함
                    redo_removed_index = move_info["index_before_move"]
                    new_index = min(redo_removed_index, len(self.image_files) - 1)
                    if new_index < 0: new_index = 0 # 이미지가 하나라도 있으면 0 이상
                    
                    # 강제 새로고침 플래그 설정 (중요: 이미지 변경 확실히 반영)
                    self.force_refresh = True

                    if mode_at_move == "Off":
                        self.current_image_index = new_index
                        if self.grid_mode != "Off": # 현재 Grid 모드면 Off로
                            self.grid_mode = "Off"
                            self.grid_off_radio.setChecked(True)
                            self.update_zoom_radio_buttons_state()
                        
                        # Fit 모드일 경우 캐시 무효화 추가
                        if self.zoom_mode == "Fit":
                            self.last_fit_size = (0, 0)
                            self.fit_pixmap_cache.clear()
                            
                        self.display_current_image()
                    else: # Grid 모드였다면
                        rows, cols = (2, 2) if mode_at_move == '2x2' else (3, 3)
                        num_cells = rows * cols
                        self.grid_page_start_index = (new_index // num_cells) * num_cells
                        self.current_grid_index = new_index % num_cells
                        if self.grid_mode == "Off": # 현재 Off 모드면 이전 Grid 모드로
                            self.grid_mode = mode_at_move
                            if mode_at_move == '2x2': self.grid_2x2_radio.setChecked(True)
                            else: self.grid_3x3_radio.setChecked(True)
                            self.update_zoom_radio_buttons_state()
                        self.update_grid_view()
                else:
                    # 모든 파일이 이동된 경우
                    self.current_image_index = -1
                    if self.grid_mode != "Off":
                        self.grid_mode = "Off"
                        self.grid_off_radio.setChecked(True)
                        self.update_zoom_radio_buttons_state()
                    self.display_current_image() # 빈 화면 표시

                self.update_counters() # 카운터 업데이트

            except Exception as e:
                self.show_themed_message_box(QMessageBox.Critical, LanguageManager.translate("에러"), f"{LanguageManager.translate('다시 실행 중 오류 발생')}: {str(e)}")
                # 오류 발생 시 히스토리 포인터를 이전 상태로 되돌릴 수 있음
                # self.history_pointer -= 1

    def closeEvent(self, event):
        """창 닫기 이벤트 처리 시 상태 저장 및 스레드 종료"""
        logging.info("앱 종료 중: 리소스 정리 시작...")
        
        # 타이머 중지
        if hasattr(self, 'memory_monitor_timer') and self.memory_monitor_timer.isActive():
            self.memory_monitor_timer.stop()
        
        # 열려있는 다이얼로그가 있다면 닫기
        if hasattr(self, 'file_list_dialog') and self.file_list_dialog and self.file_list_dialog.isVisible():
            self.file_list_dialog.close()  # 다이얼로그 닫기 요청

        self.save_state()  # 상태 저장

        # 메모리 집약적인 객체 명시적 해제
        logging.info("메모리 해제: 이미지 캐시 정리...")
        if hasattr(self, 'image_loader') and hasattr(self.image_loader, 'cache'):
            self.image_loader.cache.clear()
        self.fit_pixmap_cache.clear()
        self.grid_thumbnail_cache_2x2.clear()
        self.grid_thumbnail_cache_3x3.clear()
        self.original_pixmap = None
        
        # 모든 백그라운드 작업 취소
        logging.info("메모리 해제: 백그라운드 작업 취소...")
        for future in self.active_thumbnail_futures:
            future.cancel()
        self.active_thumbnail_futures.clear()
        
        # 단일 리소스 매니저 종료 (중복 종료 방지)
        logging.info("메모리 해제: 리소스 매니저 종료...")
        if hasattr(self, 'resource_manager'):
            self.resource_manager.shutdown()

        # === EXIF 스레드 정리 ===
        if hasattr(self, 'exif_thread') and self.exif_thread.isRunning():
            logging.info("EXIF 워커 스레드 종료 중...")
            if hasattr(self, 'exif_worker'):
                self.exif_worker.stop()  # 작업 중지 플래그 설정
            self.exif_thread.quit()
            if not self.exif_thread.wait(1000):  # 1초 대기
                self.exif_thread.terminate()  # 강제 종료
            logging.info("EXIF 워커 스레드 종료 완료")
        # === EXIF 스레드 정리 끝 ===

        # grid_thumbnail_executor 종료 추가
        if hasattr(self, 'grid_thumbnail_executor'):
            logging.info("Grid Thumbnail 스레드 풀 종료 시도...")
            self.grid_thumbnail_executor.shutdown(wait=False, cancel_futures=True)
            logging.info("Grid Thumbnail 스레드 풀 종료 완료")
        
        # 메모리 정리를 위한 가비지 컬렉션 명시적 호출
        logging.info("메모리 해제: 가비지 컬렉션 호출...")
        import gc
        gc.collect()
        
        logging.info("앱 종료 중: 리소스 정리 완료")

        # 로그 핸들러 정리
        for handler in logging.root.handlers[:]:
            handler.close()
            logging.root.removeHandler(handler)

        super().closeEvent(event)  # 부모 클래스의 closeEvent 호출

    def set_current_image_from_dialog(self, index):
        """FileListDialog에서 호출되어 특정 인덱스의 이미지 표시"""
        if not (0 <= index < len(self.image_files)):
            logging.error(f"오류: 잘못된 인덱스({index})로 이미지 설정 시도")
            return

        # 이미지 변경 전 강제 새로고침 플래그 설정
        self.force_refresh = True
        
        if self.grid_mode != "Off":
            # Grid 모드: 해당 인덱스가 포함된 페이지로 이동하고 셀 선택
            rows, cols = (2, 2) if self.grid_mode == '2x2' else (3, 3)
            num_cells = rows * cols
            self.grid_page_start_index = (index // num_cells) * num_cells
            self.current_grid_index = index % num_cells

            # Grid 뷰 업데이트 (Grid 모드 유지 시)
            self.update_grid_view() 
        else:
            # Grid Off 모드: 해당 인덱스로 바로 이동
            self.current_image_index = index
            
            # Fit 모드인 경우 기존 캐시 무효화
            if self.zoom_mode == "Fit":
                self.last_fit_size = (0, 0)
                self.fit_pixmap_cache.clear()
            
            # 이미지 표시
            self.display_current_image()
            
            # 이미지 로더의 캐시 확인하여 이미 메모리에 있으면 즉시 적용을 시도
            image_path = str(self.image_files[index])
            if image_path in self.image_loader.cache:
                cached_pixmap = self.image_loader.cache[image_path]
                if cached_pixmap and not cached_pixmap.isNull():
                    # 캐시된 이미지가 있으면 즉시 적용 시도
                    self.original_pixmap = cached_pixmap
                    if self.zoom_mode == "Fit":
                        self.apply_zoom_to_image()

        # 메인 윈도우 활성화 및 포커스 설정
        self.activateWindow()
        self.setFocus()

    def eventFilter(self, obj, event):
        """애플리케이션 레벨 이벤트 필터 - 키 이벤트 처리"""
        if event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()

            is_mac = sys.platform == 'darwin'
            ctrl_modifier = Qt.MetaModifier if is_mac else Qt.ControlModifier
            shift_modifier = Qt.ShiftModifier

            # --- Undo: Ctrl+Z (Win/Linux) or Command+Z (Mac) ---
            if modifiers == ctrl_modifier and key == Qt.Key_Z:
                logging.debug("Undo shortcut detected") # 디버깅 로그
                self.undo_move()
                return True # 이벤트 처리 완료

            # --- Redo: Ctrl+Y (Win/Linux) or Command+Y (Mac) ---
            elif modifiers == ctrl_modifier and key == Qt.Key_Y:
                logging.debug("Redo (Y) shortcut detected") # 디버깅 로그
                self.redo_move()
                return True # 이벤트 처리 완료

            # --- Redo: Ctrl+Shift+Z (Win/Linux) or Command+Shift+Z (Mac) ---
            # PySide6에서는 Shift와의 조합이 Control이나 Meta보다 우선순위가 높게 인식될 수 있음
            # 따라서 (ctrl_modifier | shift_modifier) 로 체크
            elif (modifiers & ctrl_modifier) and (modifiers & shift_modifier) and key == Qt.Key_Z:
                 logging.debug("Redo (Shift+Z) shortcut detected") # 디버깅 로그
                 self.redo_move()
                 return True # 이벤트 처리 완료

            # --- Enter 키 처리 수정 (중복 방지 추가) ---
            if key == Qt.Key_Return or key == Qt.Key_Enter:
                # 파일 목록 다이얼로그가 열려있지 않은 경우에만 새로 생성
                if self.file_list_dialog is None or not self.file_list_dialog.isVisible():
                    if self.image_files: # 로드된 이미지가 있을 때만 실행
                        current_selected_index = -1
                        if self.grid_mode == "Off":
                            current_selected_index = self.current_image_index
                        else: # Grid 모드일 때
                            potential_index = self.grid_page_start_index + self.current_grid_index
                            if 0 <= potential_index < len(self.image_files):
                                current_selected_index = potential_index

                        # 유효한 인덱스가 있을 때만 대화상자 표시
                        if current_selected_index != -1:
                            # 새 다이얼로그 생성 및 인스턴스 저장
                            self.file_list_dialog = FileListDialog(self.image_files, current_selected_index, self.image_loader, self)
                            # 다이얼로그가 닫힐 때 인스턴스 참조 제거
                            self.file_list_dialog.finished.connect(self.on_file_list_dialog_closed)
                            self.file_list_dialog.show() # 모달리스로 실행 (선택)
                        else:
                            logging.debug("Enter 키: 유효한 선택된 이미지가 없습니다.") # 디버깅용
                    else:
                        logging.debug("Enter 키: 로드된 이미지가 없습니다.") # 디버깅용
                else:
                    # 이미 다이얼로그가 열려있으면 활성화하고 맨 위로 올림
                    self.file_list_dialog.activateWindow()
                    self.file_list_dialog.raise_()
                return True # Enter 키 이벤트 처리 완료

            # --- F1, F2, F3, Delete 키 처리 ---
            if key == Qt.Key_F1:
                self.grid_off_radio.setChecked(True)
                self.on_grid_changed(self.grid_off_radio)
                return True
            elif key == Qt.Key_F2:
                self.grid_2x2_radio.setChecked(True)
                self.on_grid_changed(self.grid_2x2_radio)
                return True
            elif key == Qt.Key_F3:
                self.grid_3x3_radio.setChecked(True)
                self.on_grid_changed(self.grid_3x3_radio)
                return True
            elif key == Qt.Key_Delete:
                self.reset_program_state()
                return True

            # --- ESC 키 처리 ---
            if key == Qt.Key_Escape:
                # 파일 목록 다이얼로그가 열려 있으면 닫기
                if self.file_list_dialog and self.file_list_dialog.isVisible():
                    self.file_list_dialog.reject() # 또는 close()
                    return True # ESC는 다이얼로그 닫는 용도로만 사용

                # 다이얼로그가 없다면 기존 확대/그리드 모드 복귀 로직 수행
                if self.zoom_mode != "Fit":
                    self.fit_radio.setChecked(True)
                    self.on_zoom_changed(self.fit_radio)
                    return True
                elif self.grid_mode == "Off" and self.previous_grid_mode and self.previous_grid_mode != "Off":
                    if self.previous_grid_mode == "2x2":
                        self.grid_2x2_radio.setChecked(True)
                        self.on_grid_changed(self.grid_2x2_radio)
                    elif self.previous_grid_mode == "3x3":
                        self.grid_3x3_radio.setChecked(True)
                        self.on_grid_changed(self.grid_3x3_radio)
                    return True

            # --- 스페이스바 처리 수정 ---
            if key == Qt.Key_Space and self.grid_mode != "Off":
                # 현재 그리드에서 선택된 이미지의 인덱스를 계산
                current_selected_grid_index = self.grid_page_start_index + self.current_grid_index

                # 유효한 인덱스일 경우 current_image_index 업데이트
                if 0 <= current_selected_grid_index < len(self.image_files):
                    self.current_image_index = current_selected_grid_index
                    
                    # 이미지 변경 시 강제 새로고침 플래그 설정 추가
                    self.force_refresh = True
                    
                    # Fit 모드인 경우 기존 캐시 무효화 추가
                    if self.zoom_mode == "Fit":
                        self.last_fit_size = (0, 0)
                        self.fit_pixmap_cache.clear()

                # 이전 그리드 모드 저장
                self.previous_grid_mode = self.grid_mode
                # Grid Off로 전환
                self.grid_mode = "Off"
                self.grid_off_radio.setChecked(True)
                # 스페이스바로 전환되었음을 표시 (on_grid_changed에서 이전 모드 초기화 방지용)
                self.space_pressed = True
                # 뷰 업데이트 (이제 업데이트된 current_image_index 사용)
                self.update_grid_view()
                # 줌 버튼 상태 업데이트
                self.update_zoom_radio_buttons_state()
                self.update_counter_layout() # 레이아웃 업데이트 호출
                return True # 스페이스바 이벤트 처리 완료

            # --- Grid 모드 또는 Grid Off 모드 키 처리 ---
            if self.grid_mode != "Off":
                # Grid 모드 네비게이션 및 폴더 이동
                if modifiers & Qt.ShiftModifier:
                    if key == Qt.Key_A or key == Qt.Key_Left:
                        self.navigate_to_adjacent_page(-1)
                        return True
                    elif key == Qt.Key_D or key == Qt.Key_Right:
                        self.navigate_to_adjacent_page(1)
                        return True
                else: # Shift 안 눌렀을 때
                    rows, cols = (2, 2) if self.grid_mode == '2x2' else (3, 3)
                    if key == Qt.Key_A or key == Qt.Key_Left:
                        self.navigate_grid(-1)
                        return True
                    elif key == Qt.Key_D or key == Qt.Key_Right:
                        self.navigate_grid(1)
                        return True
                    elif key == Qt.Key_W or key == Qt.Key_Up:
                        self.navigate_grid(-cols)
                        return True
                    elif key == Qt.Key_S or key == Qt.Key_Down:
                        self.navigate_grid(cols)
                        return True
                    elif Qt.Key_1 <= key <= Qt.Key_3:
                        folder_index = key - Qt.Key_1
                        self.move_grid_image(folder_index)
                        return True
            else:
                # Grid Off 모드 네비게이션 및 폴더 이동
                if key == Qt.Key_A or key == Qt.Key_Left:
                    self.show_previous_image()
                    return True # 이벤트 소비하여 스크롤 방지
                elif key == Qt.Key_D or key == Qt.Key_Right:
                    self.show_next_image()
                    return True # 이벤트 소비하여 스크롤 방지
                elif Qt.Key_1 <= key <= Qt.Key_3:
                    folder_index = key - Qt.Key_1
                    self.move_current_image_to_folder(folder_index)
                    return True # 이벤트 소비

            # --- 처리되지 않은 키는 기본 처리 ---
            return False # False 반환 시 이벤트 계속 전파

        # 키 이벤트가 아니면 기본 처리
        return super().eventFilter(obj, event)

    def on_file_list_dialog_closed(self, result):
        """FileListDialog가 닫혔을 때 호출되는 슬롯"""
        # finished 시그널은 인자(result)를 받으므로 맞춰줌
        self.file_list_dialog = None # 다이얼로그 참조 제거
        print("File list dialog closed.") # 확인용 로그

    def update_raw_toggle_state(self):
        """RAW 폴더 유효성 및 RAW 전용 모드에 따라 'RAW 이동' 체크박스 상태 업데이트"""
        if self.is_raw_only_mode:
            # RAW 전용 모드일 때: 항상 체크됨 + 비활성화
            self.raw_toggle_button.setChecked(True)
            self.raw_toggle_button.setEnabled(False)
            self.move_raw_files = True # 내부 상태도 강제 설정
        else:
            # JPG 모드일 때: RAW 폴더 유효성에 따라 활성화/비활성화 및 상태 반영
            is_raw_folder_valid = bool(self.raw_folder and Path(self.raw_folder).is_dir())
            self.raw_toggle_button.setEnabled(is_raw_folder_valid)
            if is_raw_folder_valid:
                # 폴더가 유효하면 저장된 self.move_raw_files 상태 반영
                self.raw_toggle_button.setChecked(self.move_raw_files)
            else:
                # 폴더가 유효하지 않으면 체크 해제
                self.raw_toggle_button.setChecked(False)
                # self.move_raw_files = False # 내부 상태도 해제할 수 있음 (선택적)

    def update_match_raw_button_state(self):
        """ JPG 로드 상태에 따라 RAW 관련 버튼의 텍스트/상태 업데이트 """
        if self.is_raw_only_mode:
            # RAW 전용 모드일 때: 버튼 비활성화
            self.match_raw_button.setText(LanguageManager.translate("RAW 불러오기"))
            self.match_raw_button.setEnabled(False)
            self.load_button.setEnabled(False) # JPG 버튼도 함께 비활성화
        elif self.image_files:
            # JPG 로드됨: "JPG - RAW 연결" 버튼으로 변경
            self.match_raw_button.setText(LanguageManager.translate("JPG - RAW 연결"))
            # RAW 폴더가 이미 로드된 상태인지 확인
            is_raw_loaded = bool(self.raw_folder and Path(self.raw_folder).is_dir())
            # RAW 폴더가 로드된 상태이면 버튼 비활성화, 아니면 활성화
            self.match_raw_button.setEnabled(not is_raw_loaded)
            # JPG가 이미 로드된 상태면 JPG 버튼 비활성화
            self.load_button.setEnabled(False)
        else:
            # JPG 로드 안됨: "RAW 불러오기" 버튼으로 변경
            self.match_raw_button.setText(LanguageManager.translate("RAW 불러오기"))
            self.match_raw_button.setEnabled(True)
            self.load_button.setEnabled(True)  # 둘 다 로드 안됨: JPG 버튼 활성화

    def update_folder_label_style(self, label, folder_path):
        """폴더 경로 유효성에 따라 레이블 스타일 및 활성화 상태 업데이트"""
        is_valid = bool(folder_path and Path(folder_path).is_dir())
        if is_valid:
            label.setStyleSheet(f"""
                QLabel {{
                    color: #AAAAAA;
                    padding: 5px;
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border-radius: 1px;
                }}
            """)
            label.setEnabled(True) # 경로 있으면 활성화
        else:
            label.setStyleSheet(f"""
                QLabel {{
                    color: {ThemeManager.get_color('text_disabled')};
                    padding: 5px;
                    background-color: {ThemeManager.get_color('bg_disabled')};
                    border-radius: 1px;
                }}
            """)
            label.setEnabled(False) # 경로 없으면 비활성화

    def update_jpg_folder_ui_state(self):
        is_valid = bool(self.current_folder and Path(self.current_folder).is_dir())
        self.update_folder_label_style(self.folder_path_label, self.current_folder)
        if hasattr(self, 'jpg_clear_button'): # 버튼이 생성된 후 호출되도록 확인
            self.jpg_clear_button.setEnabled(is_valid)
        # 추가: JPG 폴더가 로드된 상태에서는 버튼 비활성화
        if hasattr(self, 'load_button'):
            self.load_button.setEnabled(not is_valid)  # 폴더가 로드되어 있으면 버튼 비활성화

    def update_raw_folder_ui_state(self):
        is_valid = bool(self.raw_folder and Path(self.raw_folder).is_dir())
        self.update_folder_label_style(self.raw_folder_path_label, self.raw_folder)
        if hasattr(self, 'raw_clear_button'): # 버튼이 생성된 후 호출되도록 확인
            self.raw_clear_button.setEnabled(is_valid)
        self.update_raw_toggle_state() # RAW 토글 상태도 같이 업데이트

    def clear_jpg_folder(self):
        """JPG 폴더 지정 해제 및 관련 상태 초기화"""
        # 백그라운드 작업 취소 추가
        print("모든 백그라운드 작업 취소 중...")
        
        # 이미지 로더 작업 취소
        for future in self.image_loader.active_futures:
            future.cancel()
        self.image_loader.active_futures.clear()
        
        # 그리드 썸네일 생성 작업 취소
        for future in self.active_thumbnail_futures:
            future.cancel()
        self.active_thumbnail_futures.clear()
        
        # 로딩 인디케이터 타이머 중지 (있다면)
        if hasattr(self, 'loading_indicator_timer') and self.loading_indicator_timer.isActive():
            self.loading_indicator_timer.stop()
        
        # RAW 디코더 결과 처리 타이머 중지
        if hasattr(self, 'decoder_timer') and self.decoder_timer.isActive():
            self.decoder_timer.stop()
        
        # 현재 로딩 작업 취소
        if hasattr(self, '_current_loading_future') and self._current_loading_future:
            self._current_loading_future.cancel()
            self._current_loading_future = None

        # Undo/Redo 히스토리 초기화 추가
        self.move_history = []
        self.history_pointer = -1
        logging.info("JPG 폴더 초기화: Undo/Redo 히스토리 초기화됨")

        self.current_folder = ""
        self.image_files = []
        self.current_image_index = -1
        self.is_raw_only_mode = False # <--- 모드 해제
        self.original_pixmap = None
        self.image_loader.clear_cache() # 이미지 로더 캐시 비우기
        self.fit_pixmap_cache.clear()   # Fit 모드 캐시 비우기

        # === 현재 Zoom 모드를 Fit으로 변경 ===
        if self.zoom_mode != "Fit":
            self.zoom_mode = "Fit"
            self.fit_radio.setChecked(True)
            # Zoom 라디오 버튼의 checked 상태만 변경하고 콜백은 직접 호출하지 않음
            # 빈 상태에서는 이미지가 없으므로 강제로 Fit 모드만 설정

        # Grid 관련 상태 초기화
        self.grid_page_start_index = 0
        self.current_grid_index = 0
        if self.grid_mode != "Off":
            self.grid_mode = "Off"
            self.grid_off_radio.setChecked(True)
            self.update_zoom_radio_buttons_state()

        # 미니맵 숨기기 추가
        if self.minimap_visible:
            self.minimap_widget.hide()
            self.minimap_visible = False

        # RAW 폴더 지정도 함께 해제 (clear_raw_folder 내부에서 is_raw_only_mode가 false이므로 일반 해제 로직 실행됨)
        self.clear_raw_folder()

        # UI 업데이트
        self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        self.update_jpg_folder_ui_state() # 레이블 스타일 및 X 버튼 상태 업데이트
        self.load_button.setEnabled(True) # <--- JPG 버튼 활성화
        self.update_match_raw_button_state() # <--- RAW 버튼 상태 업데이트 ("RAW 불러오기"로)
        # update_raw_folder_ui_state()는 clear_raw_folder 내부에서 호출됨

        # 이미지 뷰 및 정보 업데이트
        self.update_grid_view() # Grid Off 모드로 전환하며 뷰 클리어
        self.update_file_info_display(None)
        self.update_counters()
        self.setWindowTitle("PhotoSort") # 창 제목 초기화

        print("JPG 폴더 지정 해제됨.")

    def clear_raw_folder(self):
        """RAW 폴더 지정 해제 및 관련 상태 초기화 (RAW 전용 모드 처리 추가)"""
        if self.is_raw_only_mode:
            # --- RAW 전용 모드 해제 및 전체 초기화 ---
            print("RAW 전용 모드 해제 및 초기화...")

            # Undo/Redo 히스토리 초기화 추가
            self.move_history = []
            self.history_pointer = -1
            logging.info("RAW 전용 모드 초기화: Undo/Redo 히스토리 초기화됨")

            # 모든 백그라운드 작업 취소
            print("모든 백그라운드 작업 취소 중...")
            
            # 이미지 로더 작업 취소
            for future in self.image_loader.active_futures:
                future.cancel()
            self.image_loader.active_futures.clear()
            
            # 그리드 썸네일 생성 작업 취소
            for future in self.active_thumbnail_futures:
                future.cancel()
            self.active_thumbnail_futures.clear()
            
            # 로딩 인디케이터 타이머 중지
            if hasattr(self, 'loading_indicator_timer') and self.loading_indicator_timer.isActive():
                self.loading_indicator_timer.stop()
            
            # RAW 디코더 결과 처리 타이머 중지
            if hasattr(self, 'decoder_timer') and self.decoder_timer.isActive():
                self.decoder_timer.stop()
            
            # 현재 로딩 작업 취소
            if hasattr(self, '_current_loading_future') and self._current_loading_future:
                self._current_loading_future.cancel()
                self._current_loading_future = None
                
            # 리소스 매니저의 작업 모두 취소 
            self.resource_manager.cancel_all_tasks()
            
            # RAW 디코딩 보류 중인 작업 취소 및 전략 초기화 (메서드 활용)
            self.image_loader.cancel_all_raw_decoding()
                
            # RAW 디코더 풀 초기화 (강제 종료 및 새로 생성)
            try:
                # 기존 디코더 풀 종료 우선 시도
                if hasattr(self.resource_manager, 'raw_decoder_pool'):
                    self.resource_manager.raw_decoder_pool.shutdown()
                    
                    # 새 디코더 풀 생성 (내부 작업 큐 초기화)
                    available_cores = cpu_count()
                    raw_processes = min(2, max(1, available_cores // 4))
                    self.resource_manager.raw_decoder_pool = RawDecoderPool(num_processes=raw_processes)
                    print("RAW 디코더 풀 재초기화 완료")
            except Exception as e:
                logging.error(f"RAW 디코더 풀 재초기화 중 오류: {e}")

            # 이미지 로더의 RAW 전략 및 캐시 강제 초기화
            self.image_loader._raw_load_strategy = "undetermined"
            self.image_loader.cache.clear()
            print("이미지 로더 RAW 전략 및 캐시 초기화 완료")

            self.raw_folder = ""
            self.raw_files = {} # 사용 안하지만 초기화
            self.image_files = [] # 메인 파일 리스트 비우기
            self.current_image_index = -1
            self.original_pixmap = None
            self.fit_pixmap_cache.clear()

            # === 현재 Zoom 모드를 Fit으로 변경 ===
            if self.zoom_mode != "Fit":
                self.zoom_mode = "Fit"
                self.fit_radio.setChecked(True)
                # Zoom 라디오 버튼의 checked 상태만 변경하고 콜백은 직접 호출하지 않음

            # 미니맵 숨기기 추가
            if self.minimap_visible:
                self.minimap_widget.hide()
                self.minimap_visible = False

            # Grid 관련 상태 초기화
            self.grid_page_start_index = 0
            self.current_grid_index = 0
            if self.grid_mode != "Off":
                self.grid_mode = "Off"
                self.grid_off_radio.setChecked(True)
                self.update_zoom_radio_buttons_state() # Zoom 버튼 상태 복원

            # UI 업데이트
            self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
            self.update_raw_folder_ui_state() # 레이블 스타일, X 버튼, 토글 상태 업데이트 (여기서 토글 Off+활성화됨)

            # 이미지 뷰 및 정보 업데이트
            self.update_grid_view() # Grid Off 모드로 전환하며 뷰 클리어
            self.update_file_info_display(None)
            self.update_counters()
            self.setWindowTitle("PhotoSort") # 창 제목 초기화

            # RAW 전용 모드 플래그 해제
            self.is_raw_only_mode = False

            # JPG 불러오기 버튼 활성화
            self.load_button.setEnabled(True)

            # RAW 관련 버튼 텍스트 업데이트 ("RAW 불러오기"로)
            self.update_match_raw_button_state()

        else:
            # --- 기존 로직: JPG 모드에서 RAW 연결만 해제 ---
            self.raw_folder = ""
            self.raw_files = {}
            # UI 업데이트
            self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
            self.update_raw_folder_ui_state() # 레이블 스타일, X 버튼, 토글 상태 업데이트
            self.update_match_raw_button_state() # RAW 버튼 상태 업데이트 ("JPG - RAW 연결"로)

            print("RAW 폴더 지정 해제됨.")

    def on_language_radio_changed(self, button):
        """언어 라디오 버튼 변경 시 호출되는 함수"""
        if button == self.english_radio:
            LanguageManager.set_language("en")
        elif button == self.korean_radio:
            LanguageManager.set_language("ko")

    def on_date_format_changed(self, index):
        """날짜 형식 변경 시 호출되는 함수"""
        if index < 0:
            return
        format_code = self.date_format_combo.itemData(index)
        DateFormatManager.set_date_format(format_code)

    def update_ui_texts(self):
        """UI의 모든 텍스트를 현재 언어로 업데이트"""
        # 버튼 텍스트 업데이트
        self.load_button.setText(LanguageManager.translate("JPG 불러오기"))
        # 직접 설정하던 부분 제거: self.match_raw_button.setText(LanguageManager.translate("JPG - RAW 연결"))
        self.update_match_raw_button_state()  # 대신 상태에 맞는 버튼 텍스트를 설정하는 메서드 호출
        self.raw_toggle_button.setText(LanguageManager.translate("JPG + RAW 이동"))
        self.minimap_toggle.setText(LanguageManager.translate("미니맵"))

        # RAW 처리 전략 라디오 버튼 텍스트 업데이트 추가
        if hasattr(self, 'strategy_radio_buttons'):
            current_lang = LanguageManager.get_current_language()
            for strategy, radio_button in self.strategy_radio_buttons.items():
                strategy_name = RawProcessingStrategyManager.get_strategy_name(strategy, current_lang)
                radio_button.setText(strategy_name)
        
        # 폴더 경로 레이블 업데이트 - 조건 수정
        if self.folder_path_label.text() == "폴더 경로" or self.folder_path_label.text() == "Folder Path":
            self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        if self.raw_folder_path_label.text() == "폴더 경로" or self.raw_folder_path_label.text() == "Folder Path":
            self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
            
        # 분류 폴더 경로 레이블 업데이트 - 조건 수정
        for label in self.folder_path_labels:
            if label.text() == "폴더 경로" or label.text() == "Folder Path":
                label.setText(LanguageManager.translate("폴더 경로"))
        
        # 파일 정보 레이블 업데이트 (현재 선택된 이미지 경로 가져오기)
        self.update_file_info_display(self.get_current_image_path())
        
        # 창 제목 업데이트
        self.update_window_title_with_selection()
        
        # settings_popup 객체가 존재하고 현재 화면에 보이는 경우에만 업데이트 시도
        if hasattr(self, 'settings_popup') and self.settings_popup and self.settings_popup.isVisible():
            print("설정 팝업 텍스트 업데이트 중...") # 확인용 로그
            # 팝업 창 제목 업데이트
            popup_title_key = "초기 설정" if self.settings_popup.windowTitle() in ["초기 설정", "Initial Setup"] else "설정 및 정보"
            self.settings_popup.setWindowTitle(LanguageManager.translate(popup_title_key))

            # 팝업 내부 위젯 텍스트 업데이트 (재귀 함수 호출)
            self.update_settings_labels_texts(self.settings_popup)

            # '확인' 버튼 텍스트 업데이트 (첫 실행 팝업에만 존재)
            if hasattr(self.settings_popup, 'confirm_button'):
                self.settings_popup.confirm_button.setText(LanguageManager.translate("확인"))

            # 결제 서비스 이름 업데이트 추가
            for qr_label in self.settings_popup.findChildren(QRLinkLabel):
                # 현재 텍스트 확인
                if qr_label.text() in ["네이버페이", "NaverPay", "NaverPay 🇰🇷"]:
                    qr_label.setText(LanguageManager.translate("네이버페이") if LanguageManager.get_current_language() == "ko" else "NaverPay 🇰🇷")
                elif qr_label.text() in ["카카오페이", "KakaoPay", "KakaoPay 🇰🇷"]:
                    qr_label.setText(LanguageManager.translate("카카오페이") if LanguageManager.get_current_language() == "ko" else "KakaoPay 🇰🇷")

            # ========== 정보 텍스트 업데이트 코드 추가 ==========
            # 정보 텍스트 레이블 찾기 - PhotoSort로 시작하는 텍스트를 가진 QLabel을 찾기
            for info_label in self.settings_popup.findChildren(QLabel):
                if info_label.text().strip().startswith("<h2>PhotoSort</h2>"):
                    # 정보 텍스트 재생성 - 새로운 create_translated_info_text() 함수 사용
                    updated_info_text = self.create_translated_info_text()
                    info_label.setText(updated_info_text)
                    print("정보 텍스트 업데이트 완료")
                    break
            # ========== 정보 텍스트 업데이트 코드 끝 ==========
            
            # 현재 전략 레이블 업데이트
            if hasattr(self.settings_popup, 'current_strategy_label'):
                self.update_strategy_label()

            # 전략 제목 및 레이블 업데이트
            strategy_title = self.findChild(QLabel, "strategy_title_label")
            if strategy_title:
                strategy_title.setText(LanguageManager.translate("RAW 처리 방식 ⓘ"))
                strategy_title.setToolTip(self._build_raw_strategy_tooltip_text())
            
            # 현재 선택된 전략 레이블 업데이트
            if hasattr(self.settings_popup, 'current_strategy_label'):
                current_lang = LanguageManager.get_current_language()
                strategy = RawProcessingStrategyManager.get_current_strategy()
                strategy_name = RawProcessingStrategyManager.get_strategy_name(strategy, current_lang)
                self.settings_popup.current_strategy_label.setText(strategy_name)
            
            print("설정 팝업 텍스트 업데이트 완료.")

        # 현재 파일 정보 다시 표시 (날짜 형식 등 반영 위해 필요)
        self.update_file_info_display(self.get_current_image_path())

    def update_settings_labels_texts(self, widget):
        """설정 UI의 라벨 텍스트 업데이트 (재귀적으로 모든 자식 위젯 검색)"""
        
        # 현재 위젯이 QLabel인 경우 확인
        if isinstance(widget, QLabel):
            widget_object_name = widget.objectName() # 위젯의 ObjectName 가져오기

            # 1. ObjectName으로 먼저 확인 (더 안정적인 방법)
            if widget_object_name == "first_run_welcome_label":
                widget.setText(LanguageManager.translate("기본 설정을 선택해주세요."))
            elif widget_object_name == "shortcuts_title_label":
                widget.setText(LanguageManager.translate("단축키 안내"))
            elif widget_object_name == "shortcuts_content_label":
                self._update_shortcut_label_text(widget) # 헬퍼 함수 사용
            elif widget_object_name == "panel_pos_title_label":
                 widget.setText(LanguageManager.translate("컨트롤 패널"))
            elif widget_object_name == "language_title_label": # setup_settings_ui에서 설정 필요
                 widget.setText(LanguageManager.translate("언어"))
            elif widget_object_name == "date_format_title_label": # setup_settings_ui에서 설정 필요
                 widget.setText(LanguageManager.translate("날짜 형식"))
            elif widget_object_name == "theme_title_label": # setup_settings_ui에서 설정 필요
                 widget.setText(LanguageManager.translate("테마"))
            elif widget_object_name == "shortcut_info_label":
                widget.setText(LanguageManager.translate("∗ 단축키 확인 ⓘ")) # 라벨 텍스트 업데이트
                tooltip_text = self._build_shortcut_tooltip_text() # 툴팁 텍스트 재생성
                widget.setToolTip(tooltip_text) # 툴팁 업데이트
            elif widget_object_name == "shortcut_icon_label":
                tooltip_text = self._build_shortcut_tooltip_text() # 툴팁 내용 재생성
                widget.setToolTip(tooltip_text) # 툴팁 업데이트
            # ===============================================================

            # 2. ObjectName으로 찾지 못한 경우, 기존 방식대로 텍스트 내용으로 확인 (차선책)
            #    주의: 이 방식은 라벨의 현재 텍스트가 한국어 또는 영어 원본과 일치해야 작동합니다.
            #    ObjectName 방식이 구현되면 이 부분은 제거해도 됩니다.
            elif widget.text() == "언어" or widget.text() == "Language":
                widget.setText(LanguageManager.translate("언어"))
            elif widget.text() == "날짜 형식" or widget.text() == "Date Format":
                widget.setText(LanguageManager.translate("날짜 형식"))
            elif widget.text() == "테마" or widget.text() == "Theme":
                widget.setText(LanguageManager.translate("테마"))
            elif widget.text() == "컨트롤 패널" or widget.text() == "Control Panel Position": # 키 수정됨
                widget.setText(LanguageManager.translate("컨트롤 패널")) # 키 수정됨

        elif isinstance(widget, QRadioButton):
            if widget.text() == "좌측" or widget.text() == "Left":
                widget.setText(LanguageManager.translate("좌측"))
            elif widget.text() == "우측" or widget.text() == "Right":
                widget.setText(LanguageManager.translate("우측"))
        
        # 자식 위젯이 있는 경우 재귀적으로 검색
        for child in widget.findChildren(QObject):
            if isinstance(child, QWidget) and child is not widget:
             # 자식 위젯의 objectName을 확인하여 불필요한 재귀 방지 가능 (선택적 최적화)
             self.update_settings_labels_texts(child)

    def update_date_formats(self):
        """날짜 형식이 변경되었을 때 UI 업데이트"""
        # 현재 표시 중인 파일 정보 업데이트
        self.update_file_info_display(self.get_current_image_path())

    def get_current_image_path(self):
        """현재 선택된 이미지 경로 반환"""
        if not self.image_files:
            return None
            
        if self.grid_mode == "Off":
            if 0 <= self.current_image_index < len(self.image_files):
                return str(self.image_files[self.current_image_index])
        else:
            # 그리드 모드에서 선택된 이미지
            index = self.grid_page_start_index + self.current_grid_index
            if 0 <= index < len(self.image_files):
                return str(self.image_files[index])
                
        return None

    def _on_panel_position_changed(self, button):
        """컨트롤 패널 위치 라디오 버튼 클릭 시 호출"""
        button_id = self.panel_position_group.id(button) # 클릭된 버튼의 ID 가져오기 (0: 좌측, 1: 우측)
        new_state_on_right = (button_id == 1) # ID가 1이면 오른쪽

        # 현재 상태와 비교하여 변경되었을 때만 처리
        current_state = getattr(self, 'control_panel_on_right', False)
        if new_state_on_right != current_state:
            print(f"패널 위치 변경 감지: {'오른쪽' if new_state_on_right else '왼쪽'}")
            self.control_panel_on_right = new_state_on_right # 상태 업데이트
            self._apply_panel_position() # 레이아웃 즉시 적용
            # self.save_state() # 설정을 즉시 저장하고 싶다면 호출 (선택 사항)
        else:
            print("패널 위치 변경 없음")

    def _apply_panel_position(self):
        """현재 self.control_panel_on_right 상태에 따라 패널 위치 및 크기 적용"""
        print(f"_apply_panel_position 호출됨: 오른쪽 배치 = {self.control_panel_on_right}")

        # 0. 유효성 검사 (splitter가 준비되었는지)
        if not hasattr(self, 'splitter') or not self.splitter:
            logging.warning("Warning: Splitter가 아직 준비되지 않았습니다.")
            return
        if not hasattr(self, 'control_panel') or not hasattr(self, 'image_panel'):
            logging.warning("Warning: 컨트롤 또는 이미지 패널이 아직 준비되지 않았습니다.")
            return

        try:
            # 현재 스플리터 크기 저장 (선택 사항)
            # current_sizes = self.splitter.sizes()

            # 위젯 참조 저장
            control_panel_ref = self.control_panel
            image_panel_ref = self.image_panel

            # 스플리터 비우기 (위젯을 삭제하지 않음)
            # count() 만큼 반복하며 widget(0)을 가져와 setParent(None) 호출
            # count가 0이 될 때까지 반복
            while self.splitter.count() > 0:
                widget = self.splitter.widget(0)
                if widget:
                    widget.setParent(None) # splitter에서 분리만 함
                else:
                    # 예외 처리: 혹시 모를 None 위젯 방지
                    break

            # 2. 새로운 순서로 위젯 다시 추가
            if self.control_panel_on_right:
                self.splitter.addWidget(image_panel_ref)
                self.splitter.addWidget(control_panel_ref)
                print("  -> 스플리터에 위젯 추가: 이미지, 컨트롤 순")
            else:
                self.splitter.addWidget(control_panel_ref)
                self.splitter.addWidget(image_panel_ref)
                print("  -> 스플리터에 위젯 추가: 컨트롤, 이미지 순")

            # 3. 레이아웃 크기 재조정 (adjust_layout 호출)
            #    adjust_layout은 내부적으로 self.control_panel_on_right를 확인하여 올바른 setSizes를 호출함
            print("  -> adjust_layout 호출")
            self.adjust_layout()

            # (선택 사항) 저장된 크기 복원 시도 - 하지만 adjust_layout이 우선될 수 있음
            # if 'current_sizes' in locals() and len(current_sizes) == 2:
            #    if self.control_panel_on_right and current_sizes[0] != 0 and current_sizes[1] != 0:
            #        # 순서 바꿔서 복원 시도
            #        try: self.splitter.setSizes([current_sizes[1], current_sizes[0]])
            #        except Exception: pass # 실패해도 adjust_layout 결과 사용
            #    elif not self.control_panel_on_right and current_sizes[0] != 0 and current_sizes[1] != 0:
            #        try: self.splitter.setSizes(current_sizes)
            #        except Exception: pass

            print("_apply_panel_position 완료")

        except Exception as e:
            logging.error(f"Error applying panel position: {e}")
            import traceback
            traceback.print_exc() # 상세 오류 출력

    def _on_image_load_failed(self, image_path, error_message, requested_index):
        """이미지 로드 실패 시 UI 스레드에서 실행"""
        # 요청 시점의 인덱스와 현재 인덱스 비교 (이미지 변경 여부 확인)
        if self.current_image_index != requested_index:
            print(f"이미지가 변경되어 오류 결과 무시: 요청={requested_index}, 현재={self.current_image_index}")
            return
            
        self.image_label.setText(f"{LanguageManager.translate('이미지 로드 실패')}: {error_message}")
        self.original_pixmap = None
        self.update_counters()


class FileListDialog(QDialog):
    """사진 목록과 미리보기를 보여주는 팝업 대화상자"""
    def __init__(self, image_files, current_index, image_loader, parent=None):
        super().__init__(parent)
        self.image_files = image_files
        self.image_loader = image_loader
        self.preview_size = 750 # --- 미리보기 크기 750으로 변경 ---

        self.setWindowTitle(LanguageManager.translate("사진 목록"))
        # 창 크기 조정 (미리보기 증가 고려)
        self.setMinimumSize(1200, 850)

        # --- 제목 표시줄 다크 테마 적용 (이전 코드 유지) ---
        if ctypes and sys.platform == "win32":
            try:
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                dwmapi = ctypes.WinDLL("dwmapi")
                dwmapi.DwmSetWindowAttribute.argtypes = [
                    ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int), ctypes.c_uint
                ]
                hwnd = int(self.winId())
                value = ctypes.c_int(1)
                dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
            except Exception as e:
                logging.error(f"FileListDialog 제목 표시줄 다크 테마 적용 실패: {e}")

        # --- 다크 테마 배경 설정 (이전 코드 유지) ---
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(ThemeManager.get_color('bg_primary')))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # --- 메인 레이아웃 (이전 코드 유지) ---
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(15)

        # --- 좌측: 파일 목록 (이전 코드 유지, 스타일 포함) ---
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: 1px solid {ThemeManager.get_color('border')};
                border-radius: 4px;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 2px 0px;
            }}
            QListWidget::item:selected {{
                background-color: {ThemeManager.get_color('accent')};
                color: {ThemeManager.get_color('bg_primary')};
            }}
        """)
        list_font = parent.default_font if parent and hasattr(parent, 'default_font') else QFont("Arial", 10)
        list_font.setPointSize(9)
        self.list_widget.setFont(list_font)

        # 파일 목록 채우기 (이전 코드 유지)
        for i, file_path in enumerate(self.image_files):
            item = QListWidgetItem(file_path.name)
            item.setData(Qt.UserRole, str(file_path))
            self.list_widget.addItem(item)

        # 현재 항목 선택 및 스크롤 (이전 코드 유지)
        if 0 <= current_index < self.list_widget.count():
            self.list_widget.setCurrentRow(current_index)
            self.list_widget.scrollToItem(self.list_widget.item(current_index), QListWidget.PositionAtCenter)

        # --- 우측: 미리보기 레이블 ---
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(self.preview_size, self.preview_size) # --- 크기 750 적용 ---
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(f"background-color: black; border-radius: 4px;")

        # --- 레이아웃에 위젯 추가 (이전 코드 유지) ---
        self.main_layout.addWidget(self.list_widget, 1)
        self.main_layout.addWidget(self.preview_label, 0)

        # --- 미리보기 업데이트 지연 로딩을 위한 타이머 설정 ---
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True) # 한 번만 실행
        self.preview_timer.setInterval(200)  # 200ms 지연
        self.preview_timer.timeout.connect(self.load_preview) # 타이머 만료 시 load_preview 호출

        # --- 시그널 연결 변경: currentItemChanged -> on_selection_changed ---
        self.list_widget.currentItemChanged.connect(self.on_selection_changed)
        # --- 더블클릭 시그널 연결 추가 ---
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)

        # 초기 미리보기 로드 (즉시 로드)
        self.update_preview(self.list_widget.currentItem())

    def on_selection_changed(self, current, previous):
        """목록 선택 변경 시 호출되는 슬롯, 미리보기 타이머 시작/재시작"""
        # 현재 선택된 항목이 유효할 때만 타이머 시작
        if current:
            self.preview_timer.start() # 타이머 시작 (이미 실행 중이면 재시작)
        else:
            # 선택된 항목이 없으면 미리보기 즉시 초기화하고 타이머 중지
            self.preview_timer.stop()
            self.preview_label.clear()
            self.preview_label.setText(LanguageManager.translate("선택된 파일 없음"))
            self.preview_label.setStyleSheet(f"background-color: black; color: white; border-radius: 4px;")


    def load_preview(self):
        """타이머 만료 시 실제 미리보기 로딩 수행"""
        current_item = self.list_widget.currentItem()
        self.update_preview(current_item)


    def update_preview(self, current_item): # current_item 인자 유지
        """선택된 항목의 미리보기 업데이트 (실제 로직)"""
        if not current_item:
            # load_preview 에서 currentItem()을 가져오므로, 여기서 다시 체크할 필요는 적지만 안전하게 둠
            self.preview_label.clear()
            self.preview_label.setText(LanguageManager.translate("선택된 파일 없음"))
            self.preview_label.setStyleSheet(f"background-color: black; color: white; border-radius: 4px;")
            return

        file_path = current_item.data(Qt.UserRole)
        if not file_path:
            self.preview_label.clear()
            self.preview_label.setText(LanguageManager.translate("파일 경로 없음"))
            self.preview_label.setStyleSheet(f"background-color: black; color: white; border-radius: 4px;")
            return

        # 이미지 로더를 통해 이미지 로드 (캐시 활용)
        pixmap = self.image_loader.load_image_with_orientation(file_path)

        if pixmap.isNull():
            self.preview_label.clear()
            self.preview_label.setText(LanguageManager.translate("미리보기 로드 실패"))
            self.preview_label.setStyleSheet(f"background-color: black; color: red; border-radius: 4px;")
        else:
            # 스케일링 속도 개선 (FastTransformation 유지)
            scaled_pixmap = pixmap.scaled(self.preview_size, self.preview_size, Qt.KeepAspectRatio, Qt.FastTransformation)
            self.preview_label.setPixmap(scaled_pixmap)
            # 텍스트 제거를 위해 스타일 초기화
            self.preview_label.setStyleSheet(f"background-color: black; border-radius: 4px;")

    # --- 더블클릭 처리 메서드 추가 ---
    def on_item_double_clicked(self, item):
        """리스트 항목 더블클릭 시 호출되는 슬롯"""
        file_path_str = item.data(Qt.UserRole)
        if not file_path_str:
            return

        file_path = Path(file_path_str)
        parent_app = self.parent() # PhotoSortApp 인스턴스 가져오기

        # 부모가 PhotoSortApp 인스턴스이고 필요한 속성/메서드가 있는지 확인
        if parent_app and hasattr(parent_app, 'image_files') and hasattr(parent_app, 'set_current_image_from_dialog'):
            try:
                # PhotoSortApp의 image_files 리스트에서 해당 Path 객체의 인덱스 찾기
                index = parent_app.image_files.index(file_path)
                parent_app.set_current_image_from_dialog(index) # 부모 앱의 메서드 호출
                self.accept() # 다이얼로그 닫기 (성공적으로 처리되면)
            except ValueError:
                logging.error(f"오류: 더블클릭된 파일을 메인 목록에서 찾을 수 없습니다: {file_path}")
                # 사용자를 위한 메시지 박스 표시 등 추가 가능
                # 수정: LanguageManager 적용
                QMessageBox.warning(self, 
                                    LanguageManager.translate("오류"), 
                                    LanguageManager.translate("선택한 파일을 현재 목록에서 찾을 수 없습니다.\n목록이 변경되었을 수 있습니다."))
            except Exception as e:
                logging.error(f"더블클릭 처리 중 오류 발생: {e}")
                # 수정: LanguageManager 적용
                QMessageBox.critical(self, 
                                     LanguageManager.translate("오류"), 
                                     f"{LanguageManager.translate('이미지 이동 중 오류가 발생했습니다')}:\n{e}")
        else:
            logging.error("오류: 부모 위젯 또는 필요한 속성/메서드를 찾을 수 없습니다.")
            # 수정: LanguageManager 적용
            QMessageBox.critical(self, 
                                 LanguageManager.translate("오류"), 
                                 LanguageManager.translate("내부 오류로 인해 이미지로 이동할 수 없습니다."))

def main():
    # PyInstaller로 패키징된 실행 파일을 위한 멀티프로세싱 지원 추가
    freeze_support()  # 이 호출이 멀티프로세싱 무한 재귀 문제를 해결합니다

    # 로그 레벨 설정: 개발 환경에서는 DEBUG, 배포 환경에서는 INFO로 설정
    # 실제 환경에 따라 조정 가능
    is_dev_mode = getattr(sys, 'frozen', False) is False  # 스크립트 모드면 개발 환경
    log_level = logging.DEBUG if is_dev_mode else logging.INFO
    
    # 로그 레벨 적용
    logging.getLogger().setLevel(log_level)
    
    # 로깅 정보 출력
    print(f"PhotoSort 실행 환경: {'개발' if is_dev_mode else '배포'}, 로그 레벨: {logging.getLevelName(log_level)}")
    
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.Floor)

    # 번역 데이터 초기화
    translations = {
        "JPG 불러오기": "Load JPG",
        "RAW 불러오기": "Load RAW",
        "폴더 경로": "Folder Path",
        "JPG - RAW 연결": "Link JPG - RAW",
        "JPG + RAW 이동": "Move JPG + RAW",
        "폴더 선택": "Select Folder",
        "미니맵": "Minimap",
        "환산": "Eq. 35mm",
        "테마": "Theme",
        "설정 및 정보": "Settings and Info",
        "정보": "Info",
        "JPG 파일이 있는 폴더 선택": "Select JPG Folder",
        "경고": "Warning",
        "선택한 폴더에 JPG 파일이 없습니다.": "No JPG files found in the selected folder.",
        "선택한 폴더에 RAW 파일이 없습니다.": "No RAW files found in the selected folder.",
        "표시할 이미지가 없습니다": "No image to display.",
        "이미지 로드 실패": "Failed to load image",
        "이미지 표시 중 오류 발생": "Error displaying image.",
        "먼저 JPG 파일을 불러와야 합니다.": "Load JPG files first.",
        "RAW 파일이 있는 폴더 선택": "Select RAW Folder",
        "선택한 RAW 폴더에서 매칭되는 파일을 찾을 수 없습니다.": "No matching files found in the selected RAW folder.",
        "RAW 파일 매칭 결과": "RAW File Matching Results",
        "RAW 파일이 매칭되었습니다.": "RAW files matched.",
        "RAW 폴더를 선택하세요": "Select RAW folder",
        "폴더를 선택하세요": "Select folder",
        "완료": "Complete",
        "모든 이미지가 분류되었습니다.": "All images have been sorted.",
        "에러": "Error",
        "오류": "Error",
        "파일 이동 중 오류 발생": "Error moving file.",
        "프로그램 초기화": "Reset App",
        "모든 설정과 로드된 파일을 초기화하시겠습니까?": "Reset all settings and loaded files?",
        "초기화 완료": "Reset Complete",
        "프로그램이 초기 상태로 복원되었습니다.": "App restored to initial state.",
        "상태 로드 오류": "State Load Error",
        "저장된 상태 파일을 읽는 중 오류가 발생했습니다. 기본 설정으로 시작합니다.": "Error reading saved state file. Starting with default settings.",
        "상태를 불러오는 중 오류가 발생했습니다": "Error loading state.",
        "사진 목록": "Photo List",
        "선택된 파일 없음": "No file selected.",
        "파일 경로 없음": "File path not found.",
        "미리보기 로드 실패": "Failed to load preview.",
        "선택한 파일을 현재 목록에서 찾을 수 없습니다.\n목록이 변경되었을 수 있습니다.": "Selected file not found in the current list.\nThe list may have been updated.",
        "이미지 이동 중 오류가 발생했습니다": "Error moving image.",
        "내부 오류로 인해 이미지로 이동할 수 없습니다": "Cannot navigate to image due to internal error.",
        "언어": "Language",
        "날짜 형식": "Date Format",
        "실행 취소 중 오류 발생": "Error during Undo operation.",
        "다시 실행 중 오류 발생": "Error during Redo operation.",
        "초기 설정": "Initial Setup",
        "기본 설정을 선택해주세요.": "Please select your preferences before starting.",
        "확인": "Confirm",
        "컨트롤 패널": "Control Panel",
        "좌측": "Left",
        "우측": "Right",
        "단축키 안내": "Keyboard Shortcuts",
        "∗ 단축키 확인 ⓘ": "∗ View Shortcuts ⓘ",
        "닫기": "Close",
        "▪ WASD 또는 방향키: 사진 넘기기": "▪ WASD or Arrow Keys: Next/Previous Photo",
        "▪ Shift+WASD 또는 Shift+방향키: 그리드 페이지 넘기기": "▪ Shift + WASD/Arrows: Next/Previous Grid Page",
        "▪ 1, 2, 3: 지정한 폴더로 이동": "▪ 1, 2, 3: Move to Assigned Folder",
        "▪ F1, F2, F3: 그리드 옵션 변경": "▪ F1, F2, F3: Change Grid Mode",
        "▪ Ctrl + Z: 파일 이동 취소": "▪ Ctrl + Z: Undo File Move",
        "▪ Ctrl + Y 또는 Ctrl + Shift + Z: 파일 이동 다시 실행": "▪ Ctrl + Y or Ctrl + Shift + Z: Redo File Move",
        "▪ Delete: 프로그램 초기화": "▪ Delete: Reset App",
        "조건 없이 자유롭게 사용할 수 있는 무료 소프트웨어입니다.": "This is completely free software with no restrictions — use it as you like.",
        "제작자 정보를 바꿔서 배포하지만 말아주세요.": "Just please don't redistribute it under someone else's name.",
        "이 프로그램이 마음에 드신다면, 커피 한 잔으로 응원해 주세요.": "If you truly enjoy this app, consider supporting it with a cup of coffee!",
        "QR 코드": "QR Code",
        "후원 QR 코드": "Donation QR Code",
        "네이버페이": "NaverPay",
        "카카오페이": "KakaoPay",
        # 새로운 RAW 처리 전략 관련 번역 추가
        "RAW 처리 방식 ⓘ": "RAW Processing ⓘ",
        "매우 빠름": "Ultra Fast",
        "빠름": "Fast",
        "고품질": "High Quality",
        "최고 품질": "Ultra Quality",
        "미리보기 이미지 추출 실패. RAW 파일 처리 설정을 바꿔보세요": "Failed to extract preview. Try changing RAW processing settings.",
        "호환성 문제": "Compatibility Issue",
        "RAW 디코딩 실패. 미리보기를 대신 사용합니다.": "RAW decoding failed. Using preview instead.",
        "미리보기 추출 실패": "Preview Extraction Failed",
        "피드백 및 업데이트 확인:": "Feedback & Updates:",
        "이미지 로드 중...": "Loading image...",
    }
    
    LanguageManager.initialize_translations(translations)

    app = QApplication(sys.argv)

    UIScaleManager.initialize() # UI 스케일 모드 결정
    application_font = QFont("Arial", UIScaleManager.get("font_size", 10)) # 결정된 폰트 크기 가져오기 (기본값 10)
    app.setFont(application_font) # 애플리케이션 기본 폰트 설정

    window = PhotoSortApp()
    window.load_state()
    window.show()
    sys.exit(app.exec()) #수정

if __name__ == "__main__":
    main()

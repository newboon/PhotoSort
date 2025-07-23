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
import logging
import logging.handlers
from functools import partial
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
import pillow_heif

# PySide6 - Qt framework imports
from PySide6.QtCore import (Qt, QEvent, QMetaObject, QObject, QPoint, Slot,
                           QThread, QTimer, QUrl, Signal, Q_ARG, QRect, QPointF,
                           QMimeData, QAbstractListModel, QModelIndex, QSize, QSharedMemory)

from PySide6.QtGui import (QAction, QColor, QDesktopServices, QFont, QGuiApplication, 
                          QImage, QImageReader, QKeyEvent, QMouseEvent, QPainter, QPalette, QIcon,
                          QPen, QPixmap, QWheelEvent, QFontMetrics, QKeySequence, QDrag)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox,
                              QDialog, QFileDialog, QFrame, QGridLayout, 
                              QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                              QListView, QStyledItemDelegate, QStyle,
                              QMainWindow, QMenu, QMessageBox, QPushButton, QRadioButton,
                              QScrollArea, QSizePolicy, QSplitter, QTextBrowser,
                              QVBoxLayout, QWidget, QToolTip, QInputDialog, QLineEdit, 
                              QSpinBox, QProgressDialog)


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
    logging.info("PhotoSort 시작 (버전: 25.07.15)")
    
    return logger
# 로거 초기화
logger = setup_logger()

def apply_dark_title_bar(widget):
    """주어진 위젯의 제목 표시줄에 다크 테마를 적용합니다 (Windows 전용)."""
    if sys.platform == "win32":
        try:
            import ctypes
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            dwmapi = ctypes.WinDLL("dwmapi")
            hwnd = int(widget.winId())
            value = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
        except Exception as e:
            logging.error(f"{type(widget).__name__} 제목 표시줄 다크 테마 적용 실패: {e}")

class UIScaleManager:
    """해상도에 따른 UI 크기를 관리하는 클래스"""

    # 기본 UI 크기 설정
    NORMAL_SETTINGS = {
        "control_panel_margins": (8, 9, 8, 9), # 컨트롤 패널 내부 여백 (좌, 상, 우, 하)
        "control_layout_spacing": 8,               # 컨트롤 레이아웃 위젯 간 기본 간격
        "button_min_height": 30,                   # 일반 버튼 최소 높이
        "button_padding": 8,                       # 일반 버튼 내부 패딩
        "delete_button_width": 45,                 # 분류폴더 번호 및 삭제(X) 버튼 너비
        "JPG_RAW_spacing": 8,
        "section_spacing": 20,                     # 구분선(HorizontalLine) 주변 간격
        "group_box_spacing": 15,                   # 라디오 버튼 등 그룹 내 간격
        "title_spacing": 10,                       # Zoom, Grid 등 섹션 제목 아래 간격
        "settings_button_size": 35,                # 설정(톱니바퀴) 버튼 크기
        "filename_label_padding": 40,              # 파일명 레이블 상하 패딩
        "info_label_padding": 5,                   # 파일 정보 레이블 좌측 패딩
        "font_size": 10,                           # 기본 폰트 크기
        "zoom_grid_font_size": 11,                 # Zoom, Grid 등 섹션 제목 폰트 크기
        "zoom_spinbox_width": 85,                 # Zoom Spinbox 너비
        "filename_font_size": 11,                  # 파일명 폰트 크기
        "folder_container_spacing": 6,             # 분류폴더 번호버튼 - 레이블 - X버튼 간격
        "folder_label_padding": 13,                # 폴더 경로 레이블 높이 계산용 패딩
        "sort_folder_label_padding": 25,           # 분류폴더 레이블 패딩
        "category_folder_vertical_spacing": 10,    # 분류 폴더 UI 사이 간격
        "info_container_width": 300,
        "combobox_padding": 4,
        "settings_label_width": 250,               # 설정 창 라벨 최소 너비
        "control_panel_min_width": 280,            # 컨트롤 패널 최소 너비
        # 라디오 버튼 스타일 관련 키
        "radiobutton_size": 13,
        "radiobutton_border": 2,
        "radiobutton_border_radius": 8,
        "radiobutton_padding": 0,
        # 체크박스 스타일 관련 키
        "checkbox_size": 12,
        "checkbox_border": 2,
        "checkbox_border_radius": 2,
        "checkbox_padding": 0,
        # 설정 창 관련 키 추가
        "settings_popup_width": 785,
        "settings_popup_height": 800,
        "settings_layout_vspace": 15,
        "infotext_licensebutton": 30,
        "donation_between_tworows": 25,
        "bottom_space": 25,
        # 정보 텍스트 여백 관련 키 추가
        "info_version_margin": 30,
        "info_paragraph_margin": 30,
        "info_bottom_margin": 30,
        "info_donation_spacing": 35,
        # 썸네일 패널 관련 키 추가
        "thumbnail_item_height": 180,          # 썸네일 아이템 높이
        "thumbnail_item_spacing": 2,           # 썸네일 아이템 간 간격
        "thumbnail_image_size": 140,           # 썸네일 이미지 크기
        "thumbnail_text_height": 24,           # 파일명 텍스트 영역 높이
        "thumbnail_padding": 6,                # 썸네일 내부 패딩
        "thumbnail_border_width": 2,           # 선택 테두리 두께
        "thumbnail_panel_min_width": 180,      # 썸네일 패널 최소 너비
        # 
        "compare_filename_padding": 5,
    }

    # 컴팩트 모드 UI 크기 설정
    COMPACT_SETTINGS = {
        "control_panel_margins": (6, 6, 6, 6), # 컨트롤 패널 내부 여백 (좌, 상, 우, 하)
        "control_layout_spacing": 6,               # 컨트롤 레이아웃 위젯 간 기본 간격
        "button_min_height": 20,                   # 일반 버튼 최소 높이
        "button_padding": 6,                       # 일반 버튼 내부 패딩
        "delete_button_width": 35,                 # 분류폴더 번호 및 삭제(X) 버튼 너비
        "JPG_RAW_spacing": 6, 
        "section_spacing": 12,                     # 구분선(HorizontalLine) 주변 간격
        "group_box_spacing": 10,                   # 라디오 버튼 등 그룹 내 간격
        "title_spacing": 7,                        # Zoom, Grid 등 섹션 제목 아래 간격
        "settings_button_size": 25,                # 설정(톱니바퀴) 버튼 크기
        "filename_label_padding": 25,              # 파일명 레이블 상하 패딩
        "info_label_padding": 5,                   # 파일 정보 레이블 좌측 패딩
        "font_size": 9,                            # 기본 폰트 크기
        "zoom_grid_font_size": 10,                 # Zoom, Grid 등 섹션 제목 폰트 크기
        "zoom_spinbox_width": 70,                 # Zoom Spinbox 너비
        "filename_font_size": 10,                  # 파일명 폰트 크기
        "folder_container_spacing": 4,             # 분류폴더 번호버튼 - 레이블 - X버튼 간격
        "folder_label_padding": 10,                # 폴더 경로 레이블 높이 계산용 패딩
        "sort_folder_label_padding": 20,           # 분류폴더 레이블 패딩
        "category_folder_vertical_spacing": 6,     # 분류 폴더 UI 사이 간격
        "info_container_width": 200,
        "combobox_padding": 3,
        "settings_label_width": 180,               # 설정 창 라벨 최소 너비 (컴팩트 모드에서는 더 작게)
        "control_panel_min_width": 220,            # 컨트롤 패널 최소 너비 (컴팩트 모드에서는 더 작게)
        # 라디오 버튼 스타일 관련 키
        "radiobutton_size": 9,
        "radiobutton_border": 2,
        "radiobutton_border_radius": 6,
        "radiobutton_padding": 0,
        # 체크박스 스타일 관련 키
        "checkbox_size": 8,
        "checkbox_border": 2,
        "checkbox_border_radius": 1,
        "checkbox_padding": 0,
        # 설정 창 관련 키 추가 (컴팩트 모드에서는 더 작게)
        "settings_popup_width": 750,
        "settings_popup_height": 700,
        "settings_layout_vspace": 7,
        "infotext_licensebutton": 20,
        "donation_between_tworows": 17,
        "bottom_space": 15,
        # 정보 텍스트 여백 관련 키 추가 (컴팩트 모드에서는 여백 축소)
        "info_version_margin": 20,
        "info_paragraph_margin": 20,
        "info_bottom_margin": 20,
        "info_donation_spacing": 25,
        # 썸네일 패널 관련 설정 (컴팩트 모드에서는 더 작게)
        "thumbnail_item_height": 160,          # 썸네일 아이템 높이
        "thumbnail_item_spacing": 2,           # 썸네일 아이템 간 간격
        "thumbnail_image_size": 120,           # 썸네일 이미지 크기
        "thumbnail_text_height": 20,           # 파일명 텍스트 영역 높이
        "thumbnail_padding": 5,                # 썸네일 내부 패딩
        "thumbnail_border_width": 2,           # 선택 테두리 두께
        "thumbnail_panel_min_width": 150,      # 썸네일 패널 최소 너비
        # 
        "compare_filename_padding": 5,
    }

    _current_settings = NORMAL_SETTINGS # 초기값은 Normal로 설정

    @classmethod
    def initialize(cls):
        """애플리케이션 시작 시 호출되어 화면 해상도 확인 및 모드 설정"""
        try:
            screen = QGuiApplication.primaryScreen()
            if not screen:
                logging.warning("Warning: Primary screen not found. Using default UI scale.")
                cls._current_settings = cls.NORMAL_SETTINGS.copy()
                return

            screen_geometry = screen.geometry()
            vertical_resolution = screen_geometry.height()
            is_compact = vertical_resolution < 1201 

            if is_compact:
                cls._current_settings = cls.COMPACT_SETTINGS.copy()
                logging.info(f"세로 해상도: {vertical_resolution}px / Compact UI 모드 활성")
            else:
                cls._current_settings = cls.NORMAL_SETTINGS.copy()
                logging.info(f"세로 해상도: {vertical_resolution}px / Normal UI 모드 활성")

            # # 화면 비율에 따른 group_box_spacing 조정
            # if cls.is_16_10_or_less():
            #     cls._current_settings["group_box_spacing"] = 15
            #     logging.info("화면 비율 16:10 이하: group_box_spacing = 15")
            # else:
            #     cls._current_settings["group_box_spacing"] = 15
            #     logging.info("화면 비율 16:10 초과: group_box_spacing = 40")

        except Exception as e:
            logging.error(f"Error initializing UIScaleManager: {e}. Using default UI scale.")
            cls._current_settings = cls.NORMAL_SETTINGS.copy()

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
    
    @classmethod
    def is_16_10_or_less(cls):
        """
        화면의 가로/세로 비율이 16:10(1.6)과 같거나 그보다 작은지 판별.
        약간의 오차 허용 (1.6 이하 또는 1.6±0.05 이내면 True)
        """
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return False
        geometry = screen.geometry()
        width = geometry.width()
        height = geometry.height()
        if height == 0:
            return False
        aspect_ratio = width / height
        # 16:10(1.6)과 같거나 그보다 작으면 True, 1.6±0.05 이내도 허용
        return aspect_ratio <= 1.6 or abs(aspect_ratio - 1.6) < 0.05

class ThemeManager:

    _UI_COLORS_DEFAULT = {
        "accent": "#848484",        # 강조색
        "accent_hover": "#555555",  # 강조색 호버 상태(밝음)
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
    _UI_COLORS_SONY = {
        "accent": "#FF6600",
        "accent_hover": "#FF6600",
        "accent_pressed": "#CC5200",
        "text": "#D8D8D8",
        "text_disabled": "#595959",
        "bg_primary": "#333333",
        "bg_secondary": "#444444",
        "bg_hover": "#555555",
        "bg_pressed": "#222222",
        "bg_disabled": "#222222",
        "border": "#555555",
    }
    _UI_COLORS_NIKON = {
        "accent": "#FFE100",
        "accent_hover": "#FFE100",
        "accent_pressed": "#CCB800",
        "text": "#D8D8D8",
        "text_disabled": "#595959",
        "bg_primary": "#333333",
        "bg_secondary": "#444444",
        "bg_hover": "#555555",
        "bg_pressed": "#222222",
        "bg_disabled": "#222222",
        "border": "#555555",
    }
    _UI_COLORS_CANON = {
        "accent": "#CC0000",
        "accent_hover": "#CC0000",
        "accent_pressed": "#A30000",
        "text": "#D8D8D8",
        "text_disabled": "#595959",
        "bg_primary": "#333333",
        "bg_secondary": "#444444",
        "bg_hover": "#555555",
        "bg_pressed": "#222222",
        "bg_disabled": "#222222",
        "border": "#555555",
    }
    _UI_COLORS_FUJIFILM = {
        "accent": "#01916D",
        "accent_hover": "#01916D",
        "accent_pressed": "#016954",
        "text": "#D8D8D8",
        "text_disabled": "#595959",
        "bg_primary": "#333333",
        "bg_secondary": "#444444",
        "bg_hover": "#555555",
        "bg_pressed": "#222222",
        "bg_disabled": "#222222",
        "border": "#555555",
    }
    _UI_COLORS_PANASONIC = {
        "accent": "#0041C0",
        "accent_hover": "#0041C0",
        "accent_pressed": "#002D87",
        "text": "#D8D8D8",
        "text_disabled": "#595959",
        "bg_primary": "#333333",
        "bg_secondary": "#444444",
        "bg_hover": "#555555",
        "bg_pressed": "#222222",
        "bg_disabled": "#222222",
        "border": "#555555",
    }
    _UI_COLORS_LEICA = {
        "accent": "#E20612",
        "accent_hover": "#E20612",
        "accent_pressed": "#B00000",
        "text": "#D8D8D8",
        "text_disabled": "#595959",
        "bg_primary": "#333333",
        "bg_secondary": "#444444",
        "bg_hover": "#555555",
        "bg_pressed": "#222222",
        "bg_disabled": "#222222",
        "border": "#555555",
    }
    _UI_COLORS_OLYMPUS = {
        "accent": "#08107B",
        "accent_hover": "#08107B",
        "accent_pressed": "#050A5B",
        "text": "#D8D8D8",
        "text_disabled": "#595959",
        "bg_primary": "#333333",
        "bg_secondary": "#444444",
        "bg_hover": "#555555",
        "bg_pressed": "#222222",
        "bg_disabled": "#222222",
        "border": "#555555",
    }
    _UI_COLORS_SAMSUNG = {
        "accent": "#1428A0",
        "accent_hover": "#1428A0",
        "accent_pressed": "#101F7A",
        "text": "#D8D8D8",
        "text_disabled": "#595959",
        "bg_primary": "#333333",
        "bg_secondary": "#444444",
        "bg_hover": "#555555",
        "bg_pressed": "#222222",
        "bg_disabled": "#222222",
        "border": "#555555",
    }
    _UI_COLORS_PENTAX = {
        "accent": "#01CA47",
        "accent_hover": "#01CA47",
        "accent_pressed": "#019437",
        "text": "#D8D8D8",
        "text_disabled": "#595959",
        "bg_primary": "#333333",
        "bg_secondary": "#444444",
        "bg_hover": "#555555",
        "bg_pressed": "#222222",
        "bg_disabled": "#222222",
        "border": "#555555",
    }
    _UI_COLORS_RICOH = {
        "accent": "#D61B3E",
        "accent_hover": "#D61B3E",
        "accent_pressed": "#B00030",
        "text": "#D8D8D8",
        "text_disabled": "#595959",
        "bg_primary": "#333333",
        "bg_secondary": "#444444",
        "bg_hover": "#555555",
        "bg_pressed": "#222222",
        "bg_disabled": "#222222",
        "border": "#555555",
    }   

    # 모든 테마 저장
    THEMES = {
        "default": _UI_COLORS_DEFAULT, # 또는 ThemeManager._UI_COLORS_DEFAULT
        "sony": _UI_COLORS_SONY,
        "canon": _UI_COLORS_CANON,
        "nikon": _UI_COLORS_NIKON,
        "fujifilm": _UI_COLORS_FUJIFILM,
        "panasonic": _UI_COLORS_PANASONIC,
        "ricoh": _UI_COLORS_RICOH,
        "leica": _UI_COLORS_LEICA,
        "olympus": _UI_COLORS_OLYMPUS,
        "pentax": _UI_COLORS_PENTAX,
        "samsung": _UI_COLORS_SAMSUNG,
    }
    
    _current_theme = "default"  # 현재 테마
    _theme_change_callbacks = []  # 테마 변경 시 호출할 콜백 함수 목록
    
    @classmethod
    def generate_radio_button_style(cls):
        """현재 테마와 UI 스케일에 맞는 라디오 버튼 스타일시트를 생성합니다."""
        return f"""
            QRadioButton {{
                color: {cls.get_color('text')};
                padding: {UIScaleManager.get("radiobutton_padding")}px;
            }}
            QRadioButton::indicator {{
                width: {UIScaleManager.get("radiobutton_size")}px;
                height: {UIScaleManager.get("radiobutton_size")}px;
            }}
            QRadioButton::indicator:checked {{
                background-color: {cls.get_color('accent')};
                border: {UIScaleManager.get("radiobutton_border")}px solid {cls.get_color('accent')};
                border-radius: {UIScaleManager.get("radiobutton_border_radius")}px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: {cls.get_color('bg_primary')};
                border: {UIScaleManager.get("radiobutton_border")}px solid {cls.get_color('border')};
                border-radius: {UIScaleManager.get("radiobutton_border_radius")}px;
            }}
            QRadioButton::indicator:unchecked:hover {{
                border: {UIScaleManager.get("radiobutton_border")}px solid {cls.get_color('text_disabled')};
            }}
        """

    @classmethod
    def generate_checkbox_style(cls):
        """현재 테마와 UI 스케일에 맞는 체크박스 스타일시트를 생성합니다."""
        return f"""
            QCheckBox {{
                color: {cls.get_color('text')};
                padding: {UIScaleManager.get("checkbox_padding")}px;
            }}
            QCheckBox:disabled {{
                color: {cls.get_color('text_disabled')};
            }}
            QCheckBox::indicator {{
                width: {UIScaleManager.get("checkbox_size")}px;
                height: {UIScaleManager.get("checkbox_size")}px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {cls.get_color('accent')};
                border: {UIScaleManager.get("checkbox_border")}px solid {cls.get_color('accent')};
                border-radius: {UIScaleManager.get("checkbox_border_radius")}px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {cls.get_color('bg_primary')};
                border: {UIScaleManager.get("checkbox_border")}px solid {cls.get_color('border')};
                border-radius: {UIScaleManager.get("checkbox_border_radius")}px;
            }}
            QCheckBox::indicator:unchecked:hover {{
                border: {UIScaleManager.get("checkbox_border")}px solid {cls.get_color('text_disabled')};
            }}
            QCheckBox::indicator:disabled {{
                background-color: {cls.get_color('bg_disabled')};
                border: {UIScaleManager.get("checkbox_border")}px solid {cls.get_color('text_disabled')};
            }}
        """

    @classmethod
    def generate_main_button_style(cls):
        """현재 테마에 맞는 기본 버튼 스타일시트를 생성합니다."""
        return f"""
            QPushButton {{
                background-color: {cls.get_color('bg_secondary')};
                color: {cls.get_color('text')};
                border: none;
                padding: {UIScaleManager.get("button_padding")}px;
                border-radius: 1px;
                min-height: {UIScaleManager.get("button_min_height")}px;
            }}
            QPushButton:hover {{
                background-color: {cls.get_color('accent_hover')};
            }}
            QPushButton:pressed {{
                background-color: {cls.get_color('accent_pressed')};
            }}
            QPushButton:disabled {{
                background-color: {cls.get_color('bg_disabled')};
                color: {cls.get_color('text_disabled')};
                opacity: 0.7;
            }}
        """

    @classmethod
    def generate_action_button_style(cls):
        """현재 테마에 맞는 액션 버튼(X, ✓) 스타일시트를 생성합니다."""
        return f"""
            QPushButton {{
                background-color: {cls.get_color('bg_secondary')};
                color: {cls.get_color('text')};
                border: none;
                padding: 4px;
                border-radius: 1px;
                min-height: {UIScaleManager.get("button_min_height")}px;
            }}
            QPushButton:hover {{
                background-color: {cls.get_color('accent_hover')};
                color: white;
            }}
            QPushButton:pressed {{
                background-color: {cls.get_color('accent_pressed')};
                color: white;
            }}
            QPushButton:disabled {{
                background-color: {cls.get_color('bg_disabled')};
                color: {cls.get_color('text_disabled')};
            }}
        """

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

class HardwareProfileManager:
    """시스템 하드웨어 및 예상 사용 시나리오를 기반으로 성능 프로필을 결정하고 관련 파라미터를 제공하는 클래스."""
    
    _profile = "balanced"
    _system_memory_gb = 8
    _cpu_cores = 4

    PROFILES = {
        "conservative": {
            "name": "저사양 (8GB RAM)",
            "max_imaging_threads": 2, "max_raw_processes": 1, "cache_size_images": 30,
            "preload_range_adjacent": (5, 2), "preload_range_priority": 2, "preload_grid_bg_limit_factor": 0.3,
            "memory_thresholds": {"danger": 88, "warning": 82, "caution": 75},
            "cache_clear_ratios": {"danger": 0.5, "warning": 0.3, "caution": 0.15},
            "idle_preload_enabled": False,
        },
        "balanced": {
            "name": "표준 (16GB RAM)",
            "max_imaging_threads": 3, "max_raw_processes": lambda cores: min(2, max(1, cores // 4)), "cache_size_images": 60,
            "preload_range_adjacent": (8, 3), "preload_range_priority": 3, "preload_grid_bg_limit_factor": 0.5,
            "memory_thresholds": {"danger": 92, "warning": 88, "caution": 80},
            "cache_clear_ratios": {"danger": 0.5, "warning": 0.3, "caution": 0.15},
            "idle_preload_enabled": True, "idle_interval_ms": 2200,
        },
        "enhanced": {
            "name": "상급 (24GB RAM)",
            "max_imaging_threads": 4, "max_raw_processes": lambda cores: min(2, max(1, cores // 4)), "cache_size_images": 80,
            "preload_range_adjacent": (10, 4), "preload_range_priority": 4, "preload_grid_bg_limit_factor": 0.6,
            "memory_thresholds": {"danger": 94, "warning": 90, "caution": 85},
            "cache_clear_ratios": {"danger": 0.5, "warning": 0.3, "caution": 0.15},
            "idle_preload_enabled": True, "idle_interval_ms": 1800,
        },
        "aggressive": {
            "name": "고성능 (32GB RAM)",
            "max_imaging_threads": 4, "max_raw_processes": lambda cores: min(3, max(2, cores // 3)), "cache_size_images": 120,
            "preload_range_adjacent": (12, 5), "preload_range_priority": 5, "preload_grid_bg_limit_factor": 0.75,
            "memory_thresholds": {"danger": 95, "warning": 92, "caution": 88},
            "cache_clear_ratios": {"danger": 0.4, "warning": 0.25, "caution": 0.1},
            "idle_preload_enabled": True, "idle_interval_ms": 1500,
        },
        "extreme": {
            "name": "초고성능 (64GB RAM)",
            "max_imaging_threads": 4, "max_raw_processes": lambda cores: min(4, max(2, cores // 3)), "cache_size_images": 150,
            "preload_range_adjacent": (18, 6), "preload_range_priority": 6, "preload_grid_bg_limit_factor": 0.8,
            "memory_thresholds": {"danger": 96, "warning": 94, "caution": 90},
            "cache_clear_ratios": {"danger": 0.4, "warning": 0.2, "caution": 0.1},
            "idle_preload_enabled": True, "idle_interval_ms": 1200,
        },
        "dominator": {
            "name": "워크스테이션 (96GB+ RAM)",
            "max_imaging_threads": 5, "max_raw_processes": lambda cores: min(8, max(4, cores // 3)), "cache_size_images": 200,
            "preload_range_adjacent": (20, 8), "preload_range_priority": 7, "preload_grid_bg_limit_factor": 0.9,
            "memory_thresholds": {"danger": 97, "warning": 95, "caution": 92},
            "cache_clear_ratios": {"danger": 0.3, "warning": 0.15, "caution": 0.05},
            "idle_preload_enabled": True, "idle_interval_ms": 800,
        }
    }

    @classmethod
    def initialize(cls):
        try:
            cls._system_memory_gb = psutil.virtual_memory().total / (1024 ** 3)
            physical_cores = psutil.cpu_count(logical=False)
            logical_cores = psutil.cpu_count(logical=True)
            cls._cpu_cores = physical_cores if physical_cores is not None and physical_cores > 0 else logical_cores
        except Exception:
            cls._profile = "conservative"
            logging.warning("시스템 사양 확인 실패. 보수적인 성능 프로필을 사용합니다.")
            return
        
        if cls._system_memory_gb >= 90:
            cls._profile = "dominator"
        elif cls._system_memory_gb >= 45:
            cls._profile = "extreme"
        elif cls._system_memory_gb >= 30:
            cls._profile = "aggressive"
        elif cls._system_memory_gb >= 22:
            cls._profile = "enhanced"
        elif cls._system_memory_gb >= 12:
            cls._profile = "balanced"
        else:
            cls._profile = "conservative"
        
        logging.info(f"시스템 사양: {cls._system_memory_gb:.1f}GB RAM, {cls._cpu_cores} Cores. 성능 프로필 '{cls.PROFILES[cls._profile]['name']}' 활성화.")

    @classmethod
    def get(cls, key):
        param = cls.PROFILES[cls._profile].get(key)
        if callable(param):
            return param(cls._cpu_cores)
        return param

    @classmethod
    def get_current_profile_name(cls):
        return cls.PROFILES[cls._profile]["name"]

    @classmethod
    def get_current_profile_key(cls):
        return cls._profile

    @classmethod
    def set_profile_manually(cls, profile_key):
        if profile_key in cls.PROFILES:
            cls._profile = profile_key
            logging.info(f"사용자가 성능 프로필을 수동으로 '{cls.PROFILES[profile_key]['name']}'(으)로 변경했습니다.")
            return True
        return False

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

class QRLinkLabel(QLabel):
    """
    마우스 오버 시 QR 코드를 보여주고 (macOS에서는 HTML 툴팁, 그 외 OS에서는 팝업),
    클릭 시 URL을 여는 범용 라벨 클래스.
    """
    def __init__(self, text, url, qr_path=None, parent=None, color="#D8D8D8", qr_display_size=400): # size -> qr_display_size로 변경
        super().__init__(text, parent)
        self.url = url
        self._qr_path = qr_path  # macOS HTML 툴팁과 다른 OS 팝업에서 공통으로 사용
        self._qr_display_size = qr_display_size # QR 코드 표시 크기 (툴팁/팝업 공통)

        self.normal_color = color
        self.hover_color = "#FFFFFF" # 또는 ThemeManager 사용

        # --- 스타일 및 커서 설정 ---
        self.setStyleSheet(f"""
            color: {self.normal_color};
            text-decoration: none; /* 링크 밑줄 제거 원하면 */
            font-weight: normal;
        """)
        self.setCursor(Qt.PointingHandCursor)

        # --- macOS가 아닌 경우에만 사용할 QR 팝업 멤버 ---
        self.qr_popup_widget = None # 실제 팝업 QLabel 위젯 (macOS에서는 사용 안 함)

        # --- macOS가 아닌 경우, 팝업 생성 (필요하다면) ---
        if platform.system() != "Darwin" and self._qr_path:
            self._create_non_mac_qr_popup()

    def _create_non_mac_qr_popup(self):
        """macOS가 아닌 환경에서 사용할 QR 코드 팝업 QLabel을 생성합니다."""
        if not self._qr_path or not Path(self._qr_path).exists():
            return

        self.qr_popup_widget = QLabel(self.window()) # 부모를 메인 윈도우로 설정하여 다른 위젯 위에 뜨도록
        self.qr_popup_widget.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.qr_popup_widget.setAttribute(Qt.WA_TranslucentBackground)
        # 흰색 배경, 둥근 모서리, 약간의 패딩을 가진 깔끔한 팝업 스타일
        self.qr_popup_widget.setStyleSheet(
            "background-color: white; border-radius: 5px; padding: 5px; border: 1px solid #CCCCCC;"
        )

        qr_pixmap = QPixmap(self._qr_path)
        if not qr_pixmap.isNull():
            scaled_pixmap = qr_pixmap.scaled(self._qr_display_size, self._qr_display_size,
                                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.qr_popup_widget.setPixmap(scaled_pixmap)
            self.qr_popup_widget.adjustSize() # 콘텐츠 크기에 맞게 조절
        else:
            self.qr_popup_widget = None # Pixmap 로드 실패 시 팝업 사용 안 함

    def enterEvent(self, event):
        """마우스가 위젯에 들어왔을 때 스타일 변경 및 QR 코드/툴팁 표시"""
        self.setStyleSheet(f"""
            color: {self.hover_color};
            text-decoration: none;
            font-weight: bold;
        """)

        if platform.system() == "Darwin":
            if self._qr_path and Path(self._qr_path).exists():
                # macOS: HTML 툴팁 표시
                # QUrl.fromLocalFile을 사용하여 로컬 파일 경로를 올바른 URL 형식으로 변환
                local_file_url = QUrl.fromLocalFile(Path(self._qr_path).resolve()).toString()
                html = f'<img src="{local_file_url}" width="{self._qr_display_size}">'
                QToolTip.showText(self.mapToGlobal(event.pos()), html, self) # 세 번째 인자로 위젯 전달
            # else: macOS이지만 qr_path가 없으면 아무것도 안 함 (또는 기본 툴팁)
        else:
            # 다른 OS: 생성된 팝업 위젯 표시
            if self.qr_popup_widget and self.qr_popup_widget.pixmap() and not self.qr_popup_widget.pixmap().isNull():
                # 팝업 위치 계산 (마우스 커서 근처 또는 라벨 위 등)
                global_pos = self.mapToGlobal(QPoint(0, self.height())) # 라벨 하단 중앙 기준
                
                # 화면 경계 고려하여 팝업 위치 조정 (간단한 예시)
                screen_geo = QApplication.primaryScreen().availableGeometry()
                popup_width = self.qr_popup_widget.width()
                popup_height = self.qr_popup_widget.height()

                popup_x = global_pos.x() + (self.width() - popup_width) // 2
                popup_y = global_pos.y() + 5 # 라벨 아래에 약간의 간격

                # 화면 오른쪽 경계 초과 방지
                if popup_x + popup_width > screen_geo.right():
                    popup_x = screen_geo.right() - popup_width
                # 화면 왼쪽 경계 초과 방지
                if popup_x < screen_geo.left():
                    popup_x = screen_geo.left()
                # 화면 아래쪽 경계 초과 방지 (위로 올림)
                if popup_y + popup_height > screen_geo.bottom():
                    popup_y = global_pos.y() - popup_height - self.height() - 5 # 라벨 위로 이동
                # 화면 위쪽 경계 초과 방지 (아래로 내림 - 드문 경우)
                if popup_y < screen_geo.top():
                    popup_y = screen_geo.top()

                self.qr_popup_widget.move(popup_x, popup_y)
                self.qr_popup_widget.show()
                self.qr_popup_widget.raise_() # 다른 위젯 위로 올림

        super().enterEvent(event) # 부모 클래스의 enterEvent도 호출 (필요시)

    def leaveEvent(self, event):
        """마우스가 위젯을 벗어났을 때 스타일 복원 및 QR 코드/툴팁 숨김"""
        self.setStyleSheet(f"""
            color: {self.normal_color};
            text-decoration: none;
            font-weight: normal;
        """)

        if platform.system() == "Darwin":
            QToolTip.hideText() # macOS HTML 툴팁 숨김
        else:
            # 다른 OS: 팝업 위젯 숨김
            if self.qr_popup_widget:
                self.qr_popup_widget.hide()

        super().leaveEvent(event) # 부모 클래스의 leaveEvent도 호출

    def mouseReleaseEvent(self, event):
        """마우스 클릭 시 URL 열기"""
        if event.button() == Qt.LeftButton and self.url: # url이 있을 때만
            QDesktopServices.openUrl(QUrl(self.url))
        super().mouseReleaseEvent(event)

    # QR 팝업 위젯의 내용(QR 이미지)을 업데이트해야 할 경우를 위한 메서드 (선택 사항)
    def setQrPath(self, qr_path: str):
        self._qr_path = qr_path
        if platform.system() != "Darwin":
            # 기존 팝업이 있다면 숨기고, 새로 만들거나 업데이트
            if self.qr_popup_widget:
                self.qr_popup_widget.hide()
                # self.qr_popup_widget.deleteLater() # 필요시 이전 팝업 삭제
                self.qr_popup_widget = None
            if self._qr_path:
                self._create_non_mac_qr_popup()
        # macOS에서는 enterEvent에서 바로 처리하므로 별도 업데이트 불필요

class InfoFolderPathLabel(QLabel):
    """
    JPG/RAW 폴더 경로를 표시하기 위한 QLabel 기반 레이블. (기존 FolderPathLabel)
    2줄 높이, 줄 바꿈, 폴더 드래그 호버 효과를 지원합니다.
    """
    doubleClicked = Signal(str)
    folderDropped = Signal(str) # 폴더 경로만 전달

    def __init__(self, text="", parent=None):
        super().__init__(parent=parent)
        self.full_path = ""
        self.original_style = ""
        self.folder_index = -1 # 기본값 설정
        
        fixed_height_padding = UIScaleManager.get("folder_label_padding")
        
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(LanguageManager.translate("더블클릭하면 해당 폴더가 열립니다 (전체 경로 표시)"))
        font = QFont("Arial", UIScaleManager.get("font_size"))
        self.setFont(font)
        fm = QFontMetrics(font)
        line_height = fm.height()
        default_height = (line_height * 2) + fixed_height_padding
        self.setFixedHeight(default_height)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setAcceptDrops(True)
        
        self.set_style(is_valid=False)
        self.original_style = self.styleSheet()
        self.setText(text)

    def set_folder_index(self, index):
        """폴더 인덱스를 저장합니다."""
        self.folder_index = index

    def set_style(self, is_valid):
        """경로 유효성에 따라 스타일을 설정합니다."""
        if is_valid:
            style = f"""
                QLabel {{
                    color: #AAAAAA;
                    padding: 5px;
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border-radius: 1px;
                }}
            """
        else:
            style = f"""
                QLabel {{
                    color: {ThemeManager.get_color('text_disabled')};
                    padding: 5px;
                    background-color: {ThemeManager.get_color('bg_disabled')};
                    border-radius: 1px;
                }}
            """
        self.setStyleSheet(style)
        self.original_style = style

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and Path(urls[0].toLocalFile()).is_dir():
                event.acceptProposedAction()
                self.setStyleSheet(f"""
                    QLabel {{
                        color: #AAAAAA;
                        padding: 5px;
                        background-color: {ThemeManager.get_color('bg_primary')};
                        border: 2px solid {ThemeManager.get_color('accent')};
                        border-radius: 1px;
                    }}
                """)
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.original_style)

    def dropEvent(self, event):
        self.setStyleSheet(self.original_style)
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            if Path(file_path).is_dir():
                self.folderDropped.emit(file_path)
                event.acceptProposedAction()
                return
        event.ignore()

    def setText(self, text: str):
        self.full_path = text
        self.setToolTip(text)
        
        # 긴 경로 생략 로직
        max_length = 60
        prefix_length = 20
        suffix_length = 35
        # QGuiApplication.primaryScreen()을 사용하여 현재 화면의 비율을 얻는 것이 더 안정적입니다.
        screen = QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.geometry()
            aspect_ratio = geometry.width() / geometry.height() if geometry.height() else 0
            if abs(aspect_ratio - 1.6) < 0.1: # 대략 16:10 비율
                max_length=30; prefix_length=12; suffix_length=15

        if len(text) > max_length:
            display_text = text[:prefix_length] + "..." + text[-suffix_length:]
        else:
            display_text = text
        super().setText(display_text)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.full_path and self.full_path != LanguageManager.translate("폴더 경로"):
            self.doubleClicked.emit(self.full_path)

class EditableFolderPathLabel(QLineEdit):
    """
    분류 폴더 경로를 위한 QLineEdit 기반 위젯.
    상태에 따라 편집 가능/읽기 전용 모드를 전환하며 하위 폴더 생성을 지원합니다.
    """
    STATE_DISABLED = 0
    STATE_EDITABLE = 1
    STATE_SET = 2

    doubleClicked = Signal(str)
    imageDropped = Signal(int, str)
    folderDropped = Signal(int, str)
    stateChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.full_path = ""
        self.folder_index = -1
        self._current_state = self.STATE_DISABLED
        self.original_style = ""
        
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.set_state(self.STATE_DISABLED)

    def set_folder_index(self, index):
        self.folder_index = index
        fm = QFontMetrics(self.font())
        line_height = fm.height()
        padding = UIScaleManager.get("sort_folder_label_padding")
        single_line_height = line_height + padding
        self.setFixedHeight(single_line_height)

    def set_state(self, state, path=None):
        self._current_state = state
        
        if self._current_state == self.STATE_DISABLED:
            self.setReadOnly(True)
            self.setCursor(Qt.ArrowCursor)
            style = f"""
                QLineEdit {{
                    color: {ThemeManager.get_color('text_disabled')};
                    background-color: {ThemeManager.get_color('bg_disabled')};
                    border: 1px solid {ThemeManager.get_color('bg_disabled')};
                    padding: 5px; border-radius: 1px;
                }}
            """
            self.setPlaceholderText("")
            self.setText(LanguageManager.translate("폴더 경로"))
            self.setToolTip(LanguageManager.translate("폴더를 드래그하여 지정하세요."))
        elif self._current_state == self.STATE_EDITABLE:
            self.setReadOnly(False)
            self.setCursor(Qt.IBeamCursor)
            style = f"""
                QLineEdit {{
                    color: {ThemeManager.get_color('text')};
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border: 1px solid {ThemeManager.get_color('bg_primary')};
                    padding: 5px; border-radius: 1px;
                }}
                QLineEdit:focus {{ border: 1px solid {ThemeManager.get_color('accent')}; }}
            """
            self.setText("")
            self.setPlaceholderText(LanguageManager.translate("폴더 경로"))
            self.setToolTip(LanguageManager.translate("새 폴더명을 입력하거나 폴더를 드래그하여 지정하세요."))
        elif self._current_state == self.STATE_SET:
            self.setReadOnly(True)
            self.setCursor(Qt.PointingHandCursor)
            style = f"""
                QLineEdit {{
                    color: #AAAAAA;
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border: 1px solid {ThemeManager.get_color('bg_primary')};
                    padding: 5px; border-radius: 1px;
                }}
            """
            self.setPlaceholderText("")
            if path:
                self.set_path_text(path)
            self.setToolTip(f"{self.full_path}\n{LanguageManager.translate('더블클릭하면 해당 폴더가 열립니다.')}")
        
        self.setStyleSheet(style)
        self.original_style = style
        self.stateChanged.emit(self.folder_index, self._current_state)

    def set_path_text(self, text: str):
        self.full_path = text
        self.setToolTip(text)
        max_len = 25; suf_len = 20
        display_text = text
        if len(text) > max_len:
            display_text = "..." + text[-suf_len:]
        super().setText(display_text)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self._current_state == self.STATE_SET and self.full_path:
            self.doubleClicked.emit(self.full_path)
        else:
            super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        if self._can_accept_drop(event):
            event.acceptProposedAction()
            self.apply_drag_hover_style()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._can_accept_drop(event):
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.restore_original_style()

    def dropEvent(self, event):
        self.restore_original_style()
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            if Path(file_path).is_dir():
                self.folderDropped.emit(self.folder_index, file_path)
                event.acceptProposedAction()
                return
        elif event.mimeData().hasText():
            drag_data = event.mimeData().text()
            if drag_data.startswith("image_drag:"):
                if self.folder_index >= 0 and self._current_state == self.STATE_SET:
                    self.imageDropped.emit(self.folder_index, drag_data)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def _can_accept_drop(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            return len(urls) == 1 and Path(urls[0].toLocalFile()).is_dir()
        
        can_accept_image = (self.folder_index >= 0 and self._current_state == self.STATE_SET)
        if event.mimeData().hasText() and event.mimeData().text().startswith("image_drag:") and can_accept_image:
            return True
            
        return False

    def apply_drag_hover_style(self):
        """드래그 호버 시 테두리만 강조하는 스타일을 적용합니다."""
        hover_style = ""
        # <<< 수정 시작: 각 상태에 맞는 완전한 호버 스타일을 정의 >>>
        if self._current_state == self.STATE_DISABLED:
            hover_style = f"""
                QLineEdit {{
                    color: {ThemeManager.get_color('text_disabled')};
                    background-color: {ThemeManager.get_color('bg_disabled')};
                    border: 2px solid {ThemeManager.get_color('accent')};
                    padding: 4px; border-radius: 1px;
                }}
            """
        elif self._current_state == self.STATE_EDITABLE:
            hover_style = f"""
                QLineEdit {{
                    color: {ThemeManager.get_color('text')};
                    background-color: {ThemeManager.get_color('bg_secondary')};
                    border: 2px solid {ThemeManager.get_color('accent')};
                    padding: 4px; border-radius: 1px;
                }}
                QLineEdit:focus {{ border: 2px solid {ThemeManager.get_color('accent')}; }}
            """
        elif self._current_state == self.STATE_SET:
            hover_style = f"""
                QLineEdit {{
                    color: #AAAAAA;
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border: 2px solid {ThemeManager.get_color('accent')};
                    padding: 4px; border-radius: 1px;
                }}
            """
        # <<< 수정 끝 >>>
        if hover_style:
            self.setStyleSheet(hover_style)

    def apply_keypress_highlight(self, highlight: bool):
        if self._current_state != self.STATE_SET:
            return

        if highlight:
            style = f"""
                QLineEdit {{
                    color: #FFFFFF;
                    background-color: {ThemeManager.get_color('accent')};
                    border: 1px solid {ThemeManager.get_color('accent')};
                    padding: 5px; border-radius: 1px;
                }}
            """
            self.setStyleSheet(style)
        else:
            self.restore_original_style()

    def restore_original_style(self):
        self.setStyleSheet(self.original_style)

class FilenameLabel(QLabel):
    """파일명을 표시하는 레이블 클래스, 더블클릭 시 파일 열기"""
    doubleClicked = Signal(str) # 시그널에 파일명(str) 전달

    def __init__(self, text="", fixed_height_padding=40, parent=None):
        super().__init__(parent=parent)
        self._raw_display_text = "" # 아이콘 포함될 수 있는, 화면 표시용 전체 텍스트
        self._actual_filename_for_opening = "" # 더블클릭 시 열어야 할 실제 파일명 (아이콘X)
        
        self.setCursor(Qt.PointingHandCursor)
        self.setAlignment(Qt.AlignCenter)

        font = QFont("Arial", UIScaleManager.get("filename_font_size"))
        font.setBold(True)
        self.setFont(font)

        fm = QFontMetrics(font)
        line_height = fm.height()
        fixed_height = line_height + fixed_height_padding
        self.setFixedHeight(fixed_height)

        self.setWordWrap(True)
        self.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        
        # 초기 텍스트 설정 (만약 text에 아이콘이 있다면 분리 필요)
        self.set_display_and_actual_filename(text, text.replace("🔗", "")) # 아이콘 제거 시도

    def set_display_and_actual_filename(self, display_text: str, actual_filename: str):
        """표시용 텍스트와 실제 열릴 파일명을 별도로 설정"""
        self._raw_display_text = display_text # 아이콘 포함 가능성 있는 전체 표시 텍스트
        self._actual_filename_for_opening = actual_filename # 아이콘 없는 순수 파일명

        self.setToolTip(self._raw_display_text) # 툴팁에는 전체 표시 텍스트

        # 화면 표시용 텍스트 생략 처리 (아이콘 포함된 _raw_display_text 기준)
        if len(self._raw_display_text) > 17: # 아이콘 길이를 고려하여 숫자 조정 필요 가능성
            # 아이콘이 있다면 아이콘은 유지하면서 앞부분만 생략
            if "🔗" in self._raw_display_text:
                name_part = self._raw_display_text.replace("🔗", "")
                if len(name_part) > 15: # 아이콘 제외하고 15자 초과 시
                    display_text_for_label = name_part[:6] + "..." + name_part[-7:] + "🔗"
                else:
                    display_text_for_label = self._raw_display_text
            else: # 아이콘 없을 때
                display_text_for_label = self._raw_display_text[:6] + "..." + self._raw_display_text[-10:]
        else:
            display_text_for_label = self._raw_display_text

        super().setText(display_text_for_label)

    # setText는 이제 set_display_and_actual_filename을 사용하도록 유도하거나,
    # 이전 setText의 역할을 유지하되 내부적으로 _actual_filename_for_opening을 관리해야 함.
    # 여기서는 set_display_and_actual_filename을 주 사용 메서드로 가정.
    def setText(self, text: str): # 이 메서드는 PhotoSortApp에서 직접 호출 시 주의
        # 아이콘 유무에 따라 실제 열릴 파일명 결정
        actual_name = text.replace("🔗", "")
        self.set_display_and_actual_filename(text, actual_name)

    def text(self) -> str: # 화면에 표시되는 텍스트 반환 (생략된 텍스트)
        return super().text()

    def raw_display_text(self) -> str: # 아이콘 포함된 전체 표시 텍스트 반환
        return self._raw_display_text

    def actual_filename_for_opening(self) -> str: # 실제 열릴 파일명 반환
        return self._actual_filename_for_opening

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """더블클릭 시 _actual_filename_for_opening으로 시그널 발생"""
        if self._actual_filename_for_opening:
            self.doubleClicked.emit(self._actual_filename_for_opening) # 아이콘 없는 파일명 전달

class HorizontalLine(QFrame):
    """구분선을 나타내는 수평선 위젯"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        self.setStyleSheet(f"background-color: {ThemeManager.get_color('border')};")
        self.setFixedHeight(1)

class ZoomScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 부모 참조 저장 (PhotoSortApp 인스턴스)
        self.app_parent = parent

    def wheelEvent(self, event: QWheelEvent):
        # 부모 위젯 (PhotoSortApp) 상태 및 마우스 휠 설정 확인
        if self.app_parent and hasattr(self.app_parent, 'mouse_wheel_action'):
            # Ctrl 키가 눌린 상태에서 Spin 모드일 때 줌 조정
            if (event.modifiers() & Qt.ControlModifier and 
                hasattr(self.app_parent, 'zoom_mode') and 
                self.app_parent.zoom_mode == "Spin"):
                wheel_delta = event.angleDelta().y()
                if wheel_delta != 0:
                    # SpinBox에서 직접 정수 값 가져오기 (부동소수점 오차 방지)
                    if hasattr(self.app_parent, 'zoom_spin'):
                        current_zoom = self.app_parent.zoom_spin.value()  # 이미 정수값
                        # 휠 방향에 따라 10씩 증가/감소
                        if wheel_delta > 0:
                            new_zoom = min(500, current_zoom + 10)  # 최대 500%
                        else:
                            new_zoom = max(10, current_zoom - 10)   # 최소 10%
                        # 값이 실제로 변경되었을 때만 업데이트
                        if new_zoom != current_zoom:
                            # SpinBox 값 먼저 설정 (정확한 정수값 보장)
                            self.app_parent.zoom_spin.setValue(new_zoom)
                            # zoom_spin_value 동기화
                            self.app_parent.zoom_spin_value = new_zoom / 100.0
                            # 이미지에 즉시 반영
                            self.app_parent.apply_zoom_to_image()
                    event.accept()
                    return
            # 마우스 휠 동작이 "없음"으로 설정된 경우 기존 방식 사용
            if getattr(self.app_parent, 'mouse_wheel_action', 'photo_navigation') == 'none':
                # 기존 ZoomScrollArea 동작 (100%/Spin 모드에서 휠 이벤트 무시)
                if hasattr(self.app_parent, 'zoom_mode') and self.app_parent.zoom_mode in ["100%", "Spin"]:
                    event.accept()
                    return
                else:
                    super().wheelEvent(event)
                    return
            # 마우스 휠 동작이 "사진 넘기기"로 설정된 경우
            if hasattr(self.app_parent, 'grid_mode'):
                wheel_delta = event.angleDelta().y()
                if wheel_delta == 0:
                    super().wheelEvent(event)
                    return
                if self.app_parent.grid_mode == "Off":
                    # === Grid Off 모드: 이전/다음 사진 ===
                    if wheel_delta > 0:
                        self.app_parent.show_previous_image()
                    else:
                        self.app_parent.show_next_image()
                    event.accept()
                    return
                elif self.app_parent.grid_mode != "Off":
                    # === Grid 모드: 그리드 셀 간 이동 ===
                    if wheel_delta > 0:
                        self.app_parent.navigate_grid(-1)
                    else:
                        self.app_parent.navigate_grid(1)
                    event.accept()
                    return
        # 기타 경우에는 기본 스크롤 동작 수행
        super().wheelEvent(event)


class GridCellWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._filename = ""
        self._show_filename = False
        self._is_selected = False
        self.setMinimumSize(1, 1) # 최소 크기 설정 중요

        # 드래그 앤 드롭 관련 변수
        self.drag_start_pos = QPoint(0, 0)
        self.is_potential_drag = False
        self.drag_threshold = 10
        
        # 마우스 추적 활성화
        self.setMouseTracking(True)

    def setPixmap(self, pixmap):
        if pixmap is None:
            self._pixmap = QPixmap()
        else:
            self._pixmap = pixmap
        self.update() # 위젯을 다시 그리도록 요청

    def setText(self, text):
        if self._filename != text: # 텍스트가 실제로 변경될 때만 업데이트
            self._filename = text
            self.update() # 변경 시 다시 그리기

    def setShowFilename(self, show):
        if self._show_filename != show: # 상태가 실제로 변경될 때만 업데이트
            self._show_filename = show
            self.update() # 변경 시 다시 그리기

    def setSelected(self, selected):
        self._is_selected = selected
        self.update()

    def pixmap(self):
        return self._pixmap

    def text(self):
        return self._filename

    def mousePressEvent(self, event):
        """마우스 클릭 이벤트 처리 - 드래그 시작 준비"""
        try:
            # 부모 앱 참조 얻기
            app = self.get_parent_app()
            if not app:
                super().mousePressEvent(event)
                return
            
            # === Fit 모드에서 드래그 앤 드롭 시작 준비 ===
            if (event.button() == Qt.LeftButton and 
                app.zoom_mode == "Fit" and 
                app.image_files and 
                0 <= app.current_image_index < len(app.image_files)):
                
                # 드래그 시작 준비
                self.drag_start_pos = event.position().toPoint()
                self.is_potential_drag = True
                logging.debug(f"Grid 셀에서 드래그 시작 준비: {self.drag_start_pos}")
                return
            
            # 기존 이벤트 처리
            super().mousePressEvent(event)
            
        except Exception as e:
            logging.error(f"GridCellWidget.mousePressEvent 오류: {e}")
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """마우스 이동 이벤트 처리 - 드래그 시작 감지"""
        try:
            # 부모 앱 참조 얻기
            app = self.get_parent_app()
            if not app:
                super().mouseMoveEvent(event)
                return
            
            # === Fit 모드에서 드래그 시작 감지 ===
            if (self.is_potential_drag and 
                app.zoom_mode == "Fit" and 
                app.image_files and 
                0 <= app.current_image_index < len(app.image_files)):
                
                current_pos = event.position().toPoint()
                move_distance = (current_pos - self.drag_start_pos).manhattanLength()
                
                if move_distance > self.drag_threshold:
                    # 드래그 시작
                    app.start_image_drag()
                    self.is_potential_drag = False
                    logging.debug("Grid 셀에서 드래그 시작됨")
                    return
            
            # 기존 이벤트 처리
            super().mouseMoveEvent(event)
            
        except Exception as e:
            logging.error(f"GridCellWidget.mouseMoveEvent 오류: {e}")
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """마우스 릴리스 이벤트 처리 - 드래그 상태 초기화"""
        try:
            # 드래그 상태 초기화
            if self.is_potential_drag:
                self.is_potential_drag = False
                logging.debug("Grid 셀에서 드래그 시작 준비 상태 해제")
            
            # 기존 이벤트 처리
            super().mouseReleaseEvent(event)
            
        except Exception as e:
            logging.error(f"GridCellWidget.mouseReleaseEvent 오류: {e}")
            super().mouseReleaseEvent(event)

    def get_parent_app(self):
        """부모 위젯을 타고 올라가면서 PhotoSortApp 인스턴스 찾기"""
        try:
            current_widget = self.parent()
            while current_widget:
                if hasattr(current_widget, 'start_image_drag'):
                    return current_widget
                current_widget = current_widget.parent()
            return None
        except Exception as e:
            logging.error(f"get_parent_app 오류: {e}")
            return None



    # 그리드 파일명 상단 중앙
    # def paintEvent(self, event):
    #     painter = QPainter(self)
    #     painter.setRenderHint(QPainter.Antialiasing, True)
    #     painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    #     rect = self.rect() # 현재 위젯의 전체 영역

    #     # 1. 배경색 설정 (기본 검정)
    #     painter.fillRect(rect, QColor("black"))

    #     # 2. 이미지 그리기 (비율 유지, 중앙 정렬)
    #     if not self._pixmap.isNull():
    #         # 위젯 크기에 맞춰 픽스맵 스케일링 (Qt.KeepAspectRatio)
    #         scaled_pixmap = self._pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
    #         # 중앙에 그리기 위한 위치 계산
    #         x = (rect.width() - scaled_pixmap.width()) / 2
    #         y = (rect.height() - scaled_pixmap.height()) / 2
    #         painter.drawPixmap(int(x), int(y), scaled_pixmap)

    #     # 3. 파일명 그리기 (show_filename이 True이고 filename이 있을 때)
    #     if self._show_filename and self._filename:
    #         # 텍스트 배경 (이미지 위에 반투명 검정)
    #         # 파일명 길이에 따라 배경 너비 조절 가능 또는 셀 상단 전체에 고정 너비
    #         font_metrics = QFontMetrics(painter.font())
    #         text_width = font_metrics.horizontalAdvance(self._filename)
    #         text_height = font_metrics.height()
            
    #         # 배경 사각형 위치 및 크기 (상단 중앙)
    #         bg_rect_height = text_height + 4 # 상하 패딩
    #         bg_rect_y = 1 # 테두리 바로 아래부터 시작하도록 수정 (테두리 두께 1px 가정)
    #         # 배경 너비는 텍스트 너비에 맞추거나, 셀 너비에 맞출 수 있음
    #         # 여기서는 텍스트 너비 + 좌우 패딩으로 설정
    #         bg_rect_width = min(text_width + 10, rect.width() - 4) # 셀 너비 초과하지 않도록
    #         bg_rect_x = (rect.width() - bg_rect_width) / 2
            
    #         text_bg_rect = QRect(int(bg_rect_x), bg_rect_y, int(bg_rect_width), bg_rect_height)
    #         painter.fillRect(text_bg_rect, QColor(0, 0, 0, 150)) # 반투명 검정 (alpha 150)

    #         # 텍스트 그리기 설정
    #         painter.setPen(QColor("white"))
    #         font = QFont("Arial", 10) # 파일명 폰트
    #         painter.setFont(font)
            
    #         # 텍스트를 배경 사각형 중앙에 그리기
    #         # QPainter.drawText()는 다양한 오버로드가 있음
    #         # QRectF와 플래그를 사용하는 것이 정렬에 용이
    #         text_rect = QRect(int(bg_rect_x + 2), bg_rect_y + 2, int(bg_rect_width - 4), text_height) # 패딩 고려
    #         painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignVCenter, self._filename)


    #     # 4. 테두리 그리기 (선택 상태에 따라 다름)
    #     pen_color = QColor("white") if self._is_selected else QColor("#555555")
    #     pen = QPen(pen_color)
    #     pen.setWidth(1) # 테두리 두께
    #     painter.setPen(pen)
    #     painter.drawRect(rect.adjusted(0, 0, -1, -1)) # adjusted로 테두리가 위젯 안쪽에 그려지도록

    #     painter.end()

    # 마우스 이벤트 처리를 위해 기존 QLabel과 유사하게 이벤트 핸들러 추가 가능
    # (PhotoSortApp의 on_grid_cell_clicked 등에서 사용하기 위해)
    # 하지만 GridCellWidget 자체가 이벤트를 직접 처리하도록 하는 것이 더 일반적입니다.
    # 여기서는 PhotoSortApp에서 처리하는 방식을 유지하기 위해 추가하지 않겠습니다.
    # 대신, GridCellWidget에 인덱스나 경로 정보를 저장하고,
    # PhotoSortApp에서 클릭된 GridCellWidget을 식별하는 방식이 필요합니다.

    # 그리드 파일명 상단 좌측
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = self.rect()

        painter.fillRect(rect, QColor("black"))

        if not self._pixmap.isNull():
            scaled_pixmap = self._pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (rect.width() - scaled_pixmap.width()) / 2
            y = (rect.height() - scaled_pixmap.height()) / 2
            painter.drawPixmap(int(x), int(y), scaled_pixmap)

        if self._show_filename and self._filename:
            font = QFont("Arial", 10) # 파일명 폰트 먼저 설정
            if self._is_selected:
                font.setBold(True)  # 선택된 셀이면 볼드체 적용
            else:
                font.setBold(False) # 선택되지 않았으면 볼드체 해제
            painter.setFont(font)   # painter에 (볼드체가 적용되거나 해제된) 폰트 적용
            font_metrics = QFontMetrics(painter.font()) # painter에 적용된 폰트로 metrics 가져오기
            
            # 파일명 축약 (elidedText 사용)
            # 셀 너비에서 좌우 패딩(예: 각 5px)을 뺀 값을 기준으로 축약
            available_text_width = rect.width() - 10 
            elided_filename_for_paint = font_metrics.elidedText(self._filename, Qt.ElideRight, available_text_width)

            text_height = font_metrics.height()
            
            # 배경 사각형 위치 및 크기 (상단 좌측)
            bg_rect_height = text_height + 4 # 상하 패딩
            bg_rect_y = 1 # 테두리 바로 아래부터
            
            # 배경 너비: 축약된 텍스트 너비 + 좌우 패딩, 또는 셀 너비의 일정 비율 등
            # 여기서는 축약된 텍스트 너비 + 약간의 패딩으로 설정
            bg_rect_width = min(font_metrics.horizontalAdvance(elided_filename_for_paint) + 10, rect.width() - 4)
            bg_rect_x = 2 # 좌측에서 약간의 패딩 (테두리 두께 1px + 여백 1px)
            
            text_bg_rect = QRect(int(bg_rect_x), bg_rect_y, int(bg_rect_width), bg_rect_height)
            painter.fillRect(text_bg_rect, QColor(0, 0, 0, 150)) # 반투명 검정 (alpha 150)

            painter.setPen(QColor("white"))
            # 텍스트를 배경 사각형의 좌측 상단에 (약간의 내부 패딩을 주어) 그리기
            # Qt.AlignLeft | Qt.AlignVCenter 를 사용하면 배경 사각형 내에서 세로 중앙, 가로 좌측 정렬
            text_draw_x = bg_rect_x + 3 # 배경 사각형 내부 좌측 패딩
            text_draw_y = bg_rect_y + 2 # 배경 사각형 내부 상단 패딩 (텍스트 baseline 고려)
            
            # drawText는 QPointF와 문자열을 받을 수 있습니다.
            # 또는 QRectF와 정렬 플래그를 사용할 수 있습니다.
            # 여기서는 QRectF를 사용하여 정렬 플래그로 제어합니다.
            text_paint_rect = QRect(int(text_draw_x), int(text_draw_y),
                                    int(bg_rect_width - 6), # 좌우 패딩 제외한 너비
                                    text_height)
            painter.drawText(text_paint_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_filename_for_paint)


        pen_color = QColor("white") if self._is_selected else QColor("#555555")
        pen = QPen(pen_color)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        painter.end()

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
            suffix = file_path_obj.suffix.lower()
            is_raw = file_path_obj.suffix.lower() in self.raw_extensions
            is_heic = file_path_obj.suffix.lower() in {'.heic', '.heif'} 

            skip_piexif_formats = {'.heic', '.heif', '.png', '.webp', '.bmp'} # piexif 시도를 건너뛸 포맷 목록
            
            # 결과를 저장할 딕셔너리 초기화
            result = {
                "exif_resolution": None,
                "exif_make": "",
                "exif_model": "",
                "exif_datetime": None,
                "exif_focal_mm": None,
                "exif_focal_35mm": None,
                "exif_exposure_time": None,
                "exif_fnumber": None,
                "exif_iso": None,
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
            if self._running and suffix not in skip_piexif_formats: # <<< HEIC 파일이면 piexif 시도 건너뛰기
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

                    # 노출 시간
                    if result["exif_exposure_time"] is None and piexif.ExifIFD.ExposureTime in exif_ifd:
                        val = exif_ifd.get(piexif.ExifIFD.ExposureTime)
                        if isinstance(val, tuple) and len(val) == 2 and val[1] != 0:
                            result["exif_exposure_time"] = val[0] / val[1]
                    
                    # 조리개값
                    if result["exif_fnumber"] is None and piexif.ExifIFD.FNumber in exif_ifd:
                        val = exif_ifd.get(piexif.ExifIFD.FNumber)
                        if isinstance(val, tuple) and len(val) == 2 and val[1] != 0:
                            result["exif_fnumber"] = val[0] / val[1]
                    
                    # ISO
                    if result["exif_iso"] is None and piexif.ExifIFD.ISOSpeedRatings in exif_ifd:
                        result["exif_iso"] = exif_ifd.get(piexif.ExifIFD.ISOSpeedRatings)

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
                if is_heic: # <<< HEIC 파일은 항상 ExifTool 필요
                    needs_exiftool = True
                elif is_raw and result["exif_orientation"] is None:
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

                    # 노출 시간
                    if result["exif_exposure_time"] is None:
                        exposure_val = exif_data_tool.get("ExposureTime")
                        if exposure_val:
                            try:
                                result["exif_exposure_time"] = float(exposure_val)
                            except (ValueError, TypeError):
                                result["exif_exposure_time"] = str(exposure_val)
                    
                    # 조리개값
                    if result["exif_fnumber"] is None:
                        fnumber_val = exif_data_tool.get("FNumber")
                        if fnumber_val:
                            try:
                                result["exif_fnumber"] = float(fnumber_val)
                            except (ValueError, TypeError):
                                result["exif_fnumber"] = str(fnumber_val)
                    
                    # ISO
                    if result["exif_iso"] is None:
                        iso_val = exif_data_tool.get("ISO")
                        if iso_val:
                            try:
                                result["exif_iso"] = int(iso_val)
                            except (ValueError, TypeError):
                                result["exif_iso"] = str(iso_val)

            # 작업 완료, 결과 전송
            if self._running:
                self.finished.emit(result, image_path)
            
        except Exception as e:
            # 오류 발생, 오류 메시지 전송
            if self._running:
                self.error.emit(str(e), image_path)

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
            task_info = None
            
            try:
                # 1. 높은 우선순위 큐 먼저 확인
                task_info = self.task_queues['high'].get_nowait()
            except queue.Empty:
                try:
                    # 2. 중간 우선순위 큐 확인
                    task_info = self.task_queues['medium'].get_nowait()
                except queue.Empty:
                    try:
                        # 3. 낮은 우선순위 큐 확인
                        task_info = self.task_queues['low'].get_nowait()
                    except queue.Empty:
                        # 모든 큐가 비어있으면 잠시 대기
                        time.sleep(0.05)
                        continue  # 루프의 처음으로 돌아가 다시 확인

            # task_info가 성공적으로 가져와졌다면 작업 제출
            if task_info:
                # task_info는 (wrapper_function, args, kwargs) 튜플
                try:
                    super().submit(task_info[0], *task_info[1], **task_info[2])
                except Exception as e:
                    logging.error(f"작업 제출 실패: {e}")
    
    def submit_with_priority(self, priority, fn, *args, **kwargs):
        """우선순위와 함께 작업 제출"""
        if priority not in self.task_queues:
            priority = 'low'  # 기본값
        
        from concurrent.futures import Future
        future = Future()

        # 실제 실행될 함수를 래핑하여 future 결과를 설정하도록 함
        def wrapper():
            try:
                result = fn(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

        # 큐에 (래핑된 함수, 빈 인자, 빈 키워드 인자, future 객체)를 추가
        self.task_queues[priority].put((wrapper, (), {}))
        return future
    
    def shutdown(self, wait=True, cancel_futures=False):
        """스레드 풀 종료"""
        self.shutdown_flag = True
        super().shutdown(wait=wait, cancel_futures=cancel_futures)

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

        # HardwareProfileManager에서 직접 파라미터 가져오기
        HardwareProfileManager.initialize() # 앱의 이 시점에서 초기화
        max_imaging_threads = HardwareProfileManager.get("max_imaging_threads")
        raw_processes = HardwareProfileManager.get("max_raw_processes")

        # 통합 이미징 스레드 풀
        self.imaging_thread_pool = PriorityThreadPoolExecutor(
            max_workers=max_imaging_threads,
            thread_name_prefix="Imaging"
        )
        # RAW 디코더 프로세스 풀
        self.raw_decoder_pool = RawDecoderPool(num_processes=raw_processes)
        
        self.active_tasks = set()
        self.pending_tasks = {}
        self._running = True
        logging.info(f"ResourceManager 초기화 ({HardwareProfileManager.get_current_profile_name()}): 이미징 스레드 {max_imaging_threads}개, RAW 디코더 프로세스 {raw_processes}개")
        
        # 작업 모니터링 타이머 (이 부분은 유지)
        self.monitor_timer = QTimer()
        self.monitor_timer.setInterval(5000)
        self.monitor_timer.timeout.connect(self.monitor_resources)
        self.monitor_timer.start()

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
            
            future = self.imaging_thread_pool.submit_with_priority(priority, fn, *args, **kwargs)
            if future: # 반환된 future가 유효한지 확인 (선택적이지만 안전함)
                self.active_tasks.add(future)
                future.add_done_callback(lambda f: self.active_tasks.discard(f))
            return future

        else:
            # 우선순위 지원하지 않으면 일반 제출
            return self.submit_imaging_task(fn, *args, **kwargs)


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
        self._running = False # <<< 종료 플래그 설정
        
        # 활성 작업 취소 (기존 로직 유지)
        self.cancel_all_tasks() 
        
        # 스레드 풀 종료
        logging.info("ResourceManager: 이미징 스레드 풀 종료 시도 (wait=True)...")
        # self.imaging_thread_pool.shutdown(wait=False, cancel_futures=True) # 이전 코드
        self.imaging_thread_pool.shutdown(wait=True, cancel_futures=True) # <<< wait=True로 변경
        logging.info("ResourceManager: 이미징 스레드 풀 종료 완료.")
        
        # RAW 디코더 풀 종료 (기존 로직 유지)
        self.raw_decoder_pool.shutdown()
        
        print("ResourceManager: 리소스 종료 완료")

class ThumbnailModel(QAbstractListModel):
    """썸네일 패널을 위한 가상화된 리스트 모델"""
    
    # 시그널 정의
    thumbnailRequested = Signal(str, int)  # 썸네일 로딩 요청 (파일 경로, 인덱스)
    currentIndexChanged = Signal(int)      # 현재 선택 인덱스 변경
    
    def __init__(self, image_files=None, image_loader=None, parent=None):
        super().__init__(parent)
        self._image_files = image_files or []         # ← 첫 번째 버전과 동일하게 _image_files 사용
        self.image_loader = image_loader              # ← 새로 추가
        self._current_index = -1                      # 현재 선택된 인덱스
        self._thumbnail_cache = {}                    # 썸네일 캐시 {파일경로: QPixmap}
        self._thumbnail_size = UIScaleManager.get("thumbnail_image_size")  # 64 → 동적 크기
        self._loading_set = set()                     # 현재 로딩 중인 파일 경로들
        
        # ResourceManager 인스턴스 참조
        self.resource_manager = ResourceManager.instance()
        
    def set_image_files(self, image_files):
        """이미지 파일 목록 설정"""
        self.beginResetModel()
        self._image_files = image_files or []
        self._current_index = -1
        self._thumbnail_cache.clear()
        self._loading_set.clear()
        self.endResetModel()
        
        # 캐시에서 불필요한 항목 제거
        self._cleanup_cache()
        
    def set_current_index(self, index):
        """현재 선택 인덱스 설정"""
        if 0 <= index < len(self._image_files) and index != self._current_index:
            old_index = self._current_index
            self._current_index = index
            
            # 변경된 인덱스들 업데이트
            if old_index >= 0:
                self.dataChanged.emit(self.createIndex(old_index, 0), 
                                    self.createIndex(old_index, 0))
            if self._current_index >= 0:
                self.dataChanged.emit(self.createIndex(self._current_index, 0), 
                                    self.createIndex(self._current_index, 0))
                
            self.currentIndexChanged.emit(self._current_index)
    
    def get_current_index(self):
        """현재 선택 인덱스 반환"""
        return self._current_index
    
    def rowCount(self, parent=QModelIndex()):
        """모델의 행 개수 반환 (가상화 지원)"""
        count = len(self._image_files)
        if count > 0:  # 이미지가 있을 때만 로그 출력
            logging.debug(f"ThumbnailModel.rowCount: {count}개 파일")
        return count
    
    def data(self, index, role=Qt.DisplayRole):
        """모델 데이터 제공"""
        if not index.isValid() or index.row() >= len(self._image_files):
            return None
            
        row = index.row()
        file_path = str(self._image_files[row])
        
        # 기본 호출 로그 추가
        logging.debug(f"ThumbnailModel.data 호출: row={row}, role={role}, file={Path(file_path).name}")
        
        if role == Qt.DisplayRole:
            # 파일명만 반환
            return Path(file_path).name
            
        elif role == Qt.DecorationRole:
            # 썸네일 이미지 반환
            logging.debug(f"ThumbnailModel.data: Qt.DecorationRole 요청 - {Path(file_path).name}")
            return self._get_thumbnail(file_path, row)
            
        elif role == Qt.UserRole:
            # 파일 경로 반환
            return file_path
            
        elif role == Qt.UserRole + 1:
            # 현재 선택 여부 반환
            return row == self._current_index
            
        elif role == Qt.ToolTipRole:
            # 툴팁: 파일명 + 경로
            return f"{Path(file_path).name}\n{file_path}"
            
        return None
    
    def flags(self, index):
        """아이템 플래그 반환 (선택, 드래그 가능)"""
        if not index.isValid():
            return Qt.NoItemFlags
            
        return (Qt.ItemIsEnabled | 
                Qt.ItemIsSelectable | 
                Qt.ItemIsDragEnabled)
    
    def _get_thumbnail(self, file_path, row):
        """썸네일 이미지 반환 (캐시 우선, 없으면 비동기 로딩)"""
        # 캐시에서 확인
        if file_path in self._thumbnail_cache:
            thumbnail = self._thumbnail_cache[file_path]
            if thumbnail and not thumbnail.isNull():
                logging.debug(f"썸네일 캐시 히트: {Path(file_path).name}")
                return thumbnail
        
        # 로딩 중이 아니면 비동기 로딩 요청
        if file_path not in self._loading_set:
            logging.debug(f"썸네일 비동기 로딩 요청: {Path(file_path).name}")
            self._loading_set.add(file_path)
            self.thumbnailRequested.emit(file_path, row)
        else:
            logging.debug(f"썸네일 이미 로딩 중: {Path(file_path).name}")
        
        # 기본 이미지 반환 (로딩 중 표시)
        return self._create_loading_pixmap()
    
    def _create_loading_pixmap(self):
        """로딩 중 표시할 기본 픽스맵 생성"""
        size = UIScaleManager.get("thumbnail_image_size")
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(ThemeManager.get_color('bg_secondary')))
        
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor(ThemeManager.get_color('text_disabled')), 1))
        painter.drawRect(0, 0, size-1, size-1)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "...")
        painter.end()
        
        return pixmap
    
    def set_thumbnail(self, file_path, pixmap):
        """썸네일 캐시에 저장 및 UI 업데이트"""
        if not pixmap or pixmap.isNull():
            return
            
        # 캐시에 저장
        self._thumbnail_cache[file_path] = pixmap
        
        # 로딩 상태에서 제거
        self._loading_set.discard(file_path)
        
        # 해당 인덱스 찾아서 UI 업데이트
        for i, image_file in enumerate(self._image_files):
            if str(image_file) == file_path:
                index = self.createIndex(i, 0)
                self.dataChanged.emit(index, index, [Qt.DecorationRole])
                break
    
    def _cleanup_cache(self):
        """불필요한 캐시 항목 제거"""
        if not self._image_files:
            self._thumbnail_cache.clear()
            return
            
        # 현재 이미지 파일 목록에 없는 캐시 항목 제거
        current_paths = {str(f) for f in self._image_files}
        cached_paths = set(self._thumbnail_cache.keys())
        
        for path in cached_paths - current_paths:
            del self._thumbnail_cache[path]
    
    def clear_cache(self):
        """모든 캐시 지우기"""
        self._thumbnail_cache.clear()
        self._loading_set.clear()
    
    def preload_thumbnails(self, center_index, radius=10):
        """중심 인덱스 주변의 썸네일 미리 로딩"""
        if not self._image_files or center_index < 0:
            return
            
        start = max(0, center_index - radius)
        end = min(len(self._image_files), center_index + radius + 1)
        
        for i in range(start, end):
            file_path = str(self._image_files[i])
            if (file_path not in self._thumbnail_cache and 
                file_path not in self._loading_set):
                self._loading_set.add(file_path)
                self.thumbnailRequested.emit(file_path, i)

class ImageLoader(QObject):
    """이미지 로딩 및 캐싱을 관리하는 클래스"""

    imageLoaded = Signal(int, QPixmap, str)  # 인덱스, 픽스맵, 이미지 경로
    loadCompleted = Signal(QPixmap, str, int)  # pixmap, image_path, requested_index
    loadFailed = Signal(str, str, int)  # error_message, image_path, requested_index
    decodingFailedForFile = Signal(str) # 디코딩 실패 시 PhotoSortApp에 알리기 위한 새 시그널(실패한 파일 경로 전달)

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
        self._raw_load_strategy = "preview" # PhotoSortApp에서 명시적으로 설정하기 전까지의 기본값
        self.load_executor = self.resource_manager.imaging_thread_pool
        
        # RAW 디코딩 보류 중인 파일 추적 
        self.pending_raw_decoding = set()

        # 전략 결정을 위한 락 추가
        self._strategy_lock = threading.Lock()

    def cancel_loading(self):
        """진행 중인 모든 이미지 로딩 작업을 취소합니다."""
        for future in self.active_futures:
            future.cancel()
        self.active_futures.clear()
        logging.info("ImageLoader: 활성 로딩 작업이 취소되었습니다.")

    def get_system_memory_gb(self):
        """시스템 메모리 크기 확인 (GB)"""
        try:
            import psutil
            return psutil.virtual_memory().total / (1024 * 1024 * 1024)
        except:
            return 8.0  # 기본값 8GB
        
        
    def calculate_adaptive_cache_size(self):
        """시스템 프로필에 맞는 캐시 크기를 가져옵니다."""
        # HardwareProfileManager가 이미 초기화되었다고 가정
        size = HardwareProfileManager.get("cache_size_images")
        logging.info(f"ImageLoader: 캐시 크기 설정 -> {size}개 이미지 ({HardwareProfileManager.get_current_profile_name()} 프로필)")
        return size
    
    def create_lru_cache(self, max_size): # 이 함수는 OrderedDict를 반환하며, 실제 크기 제한은 _add_to_cache에서 self.cache_limit을 사용하여 관리됩니다.
        """LRU 캐시 생성 (OrderedDict 기반)"""
        from collections import OrderedDict
        return OrderedDict()
    
    def check_cache_health(self):
        """캐시 상태 확인 및 시스템 프로필에 따라 동적으로 축소"""
        try:
            memory_percent = psutil.virtual_memory().percent
            current_time = time.time()

            # HardwareProfileManager에서 현재 프로필의 임계값과 비율 가져오기
            thresholds = HardwareProfileManager.get("memory_thresholds")
            ratios = HardwareProfileManager.get("cache_clear_ratios")
            
            # 임시 쿨다운 (향후 프로필에 추가 가능)
            cooldowns = {"danger": 5, "warning": 10, "caution": 30}

            level = None
            if memory_percent > thresholds["danger"]: level = "danger"
            elif memory_percent > thresholds["warning"]: level = "warning"
            elif memory_percent > thresholds["caution"]: level = "caution"

            if level and (current_time - self.last_cache_adjustment > cooldowns[level]):
                reduction_count = max(1, int(len(self.cache) * ratios[level]))
                removed_count = self._remove_oldest_items_from_cache(reduction_count)
                
                log_level_map = {"danger": logging.CRITICAL, "warning": logging.WARNING, "caution": logging.INFO}
                logging.log(
                    log_level_map[level],
                    f"메모리 사용량 {level.upper()} 수준 ({memory_percent}%): 캐시 {ratios[level]*100:.0f}% 정리 ({removed_count}개 항목 제거)"
                )
                
                self.last_cache_adjustment = current_time
                gc.collect()

        except Exception as e:
            if "psutil" not in str(e):
                logging.warning(f"check_cache_health에서 예외 발생: {e}")

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


    def cancel_all_raw_decoding(self):
        """진행 중인 모든 RAW 디코딩 작업 취소"""
        # 보류 중인 RAW 디코딩 작업 목록 초기화
        self.pending_raw_decoding.clear()
        
        # 캐시와 전략 초기화
        self._raw_load_strategy = "preview"
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
    
    def load_image_with_orientation(self, file_path, strategy_override=None):
        """EXIF 방향 정보를 고려하여 이미지를 올바른 방향으로 로드 (RAW 로딩 방식은 _raw_load_strategy 따름)
           RAW 디코딩은 ResourceManager를 통해 요청하고, 이 메서드는 디코딩된 데이터 또는 미리보기를 반환합니다.
           실제 디코딩 작업은 비동기로 처리될 수 있으며, 이 함수는 즉시 QPixmap을 반환하지 않을 수 있습니다.
           대신 PhotoSortApp의 _load_image_task 에서 이 함수를 호출하고 콜백으로 결과를 받습니다.
        """
        logging.debug(f"ImageLoader ({id(self)}): load_image_with_orientation 호출됨. 파일: {Path(file_path).name}, 내부 전략: {self._raw_load_strategy}, 오버라이드: {strategy_override}")
        if not ResourceManager.instance()._running:
            logging.info(f"ImageLoader.load_image_with_orientation: ResourceManager 종료 중, 로드 중단 ({Path(file_path).name})")
            return QPixmap()
        # strategy_override가 사용된 경우 캐시를 건너뛰지 않도록 캐시 확인 로직 유지
        if strategy_override is None and file_path in self.cache:
            self.cache.move_to_end(file_path)
            return self.cache[file_path]
        file_path_obj = Path(file_path)
        is_raw = file_path_obj.suffix.lower() in self.raw_extensions
        pixmap = None
        if is_raw:
            current_processing_method = strategy_override if strategy_override else self._raw_load_strategy
            logging.debug(f"ImageLoader ({id(self)}): RAW 파일 '{file_path_obj.name}' 처리 시작, 최종 방식: {current_processing_method}")
            if current_processing_method == "preview":
                logging.info(f"ImageLoader: 'preview' 방식으로 로드 시도 ({file_path_obj.name})")
                preview_pixmap_result, _, _ = self._load_raw_preview_with_orientation(file_path)
                if preview_pixmap_result and not preview_pixmap_result.isNull():
                    pixmap = preview_pixmap_result
                else:
                    logging.warning(f"'preview' 방식 실패, 미리보기 로드 불가 ({file_path_obj.name})")
                    pixmap = QPixmap()
            elif current_processing_method == "decode":
                logging.info(f"ImageLoader: 'decode' 방식으로 *직접* 로드 시도 (스레드 풀 내) ({file_path_obj.name})")
                current_time = time.time()
                if file_path_obj.name in self.recently_decoded:
                    last_decode_time = self.recently_decoded[file_path_obj.name]
                    if current_time - last_decode_time < self.decoding_cooldown:
                        logging.debug(f"최근 디코딩한 파일(성공/실패 무관): {file_path_obj.name}, 플레이스홀더 반환")
                        placeholder = QPixmap(100, 100); placeholder.fill(QColor(40, 40, 40))
                        return placeholder
                try:
                    self.recently_decoded[file_path_obj.name] = current_time
                    if not ResourceManager.instance()._running:
                        return QPixmap()
                    with rawpy.imread(file_path) as raw:
                        rgb = raw.postprocess(use_camera_wb=True, output_bps=8, no_auto_bright=False)
                        height, width, _ = rgb.shape
                        rgb_contiguous = np.ascontiguousarray(rgb)
                        qimage = QImage(rgb_contiguous.data, width, height, rgb_contiguous.strides[0], QImage.Format_RGB888)
                        pixmap_result = QPixmap.fromImage(qimage)
                        if pixmap_result and not pixmap_result.isNull():
                            pixmap = pixmap_result
                            logging.info(f"RAW 직접 디코딩 성공 (스레드 풀 내) ({file_path_obj.name})")
                        else:
                            logging.warning(f"RAW 직접 디코딩 후 QPixmap 변환 실패 ({file_path_obj.name})")
                            pixmap = QPixmap()
                            self.decodingFailedForFile.emit(file_path)
                except Exception as e_raw_decode:
                    logging.error(f"RAW 직접 디코딩 실패 (스레드 풀 내) ({file_path_obj.name}): {e_raw_decode}")
                    pixmap = QPixmap()
                    self.decodingFailedForFile.emit(file_path)
                self._clean_old_decoding_history(current_time)
            else:
                logging.warning(f"ImageLoader: 알 수 없거나 설정되지 않은 _raw_load_strategy ('{current_processing_method}'). 'preview' 사용 ({file_path_obj.name})")
                preview_pixmap_result, _, _ = self._load_raw_preview_with_orientation(file_path)
                if preview_pixmap_result and not preview_pixmap_result.isNull():
                    pixmap = preview_pixmap_result
                else:
                    pixmap = QPixmap()
            
            # strategy_override가 사용되지 않은 경우에만 캐시에 저장
            if pixmap and not pixmap.isNull():
                if strategy_override is None:
                    self._add_to_cache(file_path, pixmap)
                return pixmap
            else:
                logging.error(f"RAW 처리 최종 실패 ({file_path_obj.name}), 빈 QPixmap 반환됨.")
                return QPixmap()
        else:
            try:
                if not ResourceManager.instance()._running:
                    return QPixmap()
                with open(file_path, 'rb') as f:
                    image = Image.open(f)
                    image.load()
                orientation = 1
                if hasattr(image, 'getexif'):
                    exif = image.getexif()
                    if exif and 0x0112 in exif:
                        orientation = exif[0x0112]
                if orientation > 1:
                    if orientation == 2: image = image.transpose(Image.FLIP_LEFT_RIGHT)
                    elif orientation == 3: image = image.transpose(Image.ROTATE_180)
                    elif orientation == 4: image = image.transpose(Image.FLIP_TOP_BOTTOM)
                    elif orientation == 5: image = image.transpose(Image.TRANSPOSE)
                    elif orientation == 6: image = image.transpose(Image.ROTATE_270)
                    elif orientation == 7: image = image.transpose(Image.TRANSVERSE)
                    elif orientation == 8: image = image.transpose(Image.ROTATE_90)
                if image.mode == 'P' or image.mode == 'RGBA': image = image.convert('RGBA')
                elif image.mode != 'RGB': image = image.convert('RGB')
                img_format = QImage.Format_RGBA8888 if image.mode == 'RGBA' else QImage.Format_RGB888
                bytes_per_pixel = 4 if image.mode == 'RGBA' else 3
                data = image.tobytes('raw', image.mode)
                qimage = QImage(data, image.width, image.height, image.width * bytes_per_pixel, img_format)
                pixmap = QPixmap.fromImage(qimage)
                if pixmap and not pixmap.isNull():
                    self._add_to_cache(file_path, pixmap)
                    return pixmap
                else:
                    logging.warning(f"JPG QPixmap 변환 실패 ({file_path_obj.name})")
                    return QPixmap()
            except Exception as e_jpg:
                logging.error(f"JPG 이미지 처리 오류 ({file_path_obj.name}): {e_jpg}")
                try:
                    pixmap = QPixmap(file_path)
                    if not pixmap.isNull(): self._add_to_cache(file_path, pixmap); return pixmap
                    else: return QPixmap()
                except Exception: return QPixmap()

    def set_raw_load_strategy(self, strategy: str):
        """이 ImageLoader 인스턴스의 RAW 처리 방식을 설정합니다 ('preview' 또는 'decode')."""
        if strategy in ["preview", "decode"]:
            old_strategy = self._raw_load_strategy
            self._raw_load_strategy = strategy
            logging.info(f"ImageLoader ({id(self)}): RAW 처리 방식 변경됨: {old_strategy} -> {self._raw_load_strategy}") # <<< 상세 로그 추가
        else:
            logging.warning(f"ImageLoader ({id(self)}): 알 수 없는 RAW 처리 방식 '{strategy}'. 변경 안 함. 현재: {self._raw_load_strategy}")
    
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

    def preload_page(self, image_files, page_start_index, cells_per_page, strategy_override=None):
        """특정 페이지의 이미지를 미리 로딩"""
        self.last_requested_page = page_start_index // cells_per_page
        for future in self.active_futures:
            future.cancel()
        self.active_futures.clear()
        end_idx = min(page_start_index + cells_per_page, len(image_files))
        futures = []
        for i in range(page_start_index, end_idx):
            if i < 0 or i >= len(image_files):
                continue
            img_path = str(image_files[i])
            if img_path in self.cache:
                pixmap = self.cache[img_path]
                self.imageLoaded.emit(i - page_start_index, pixmap, img_path)
            else:
                future = self.load_executor.submit(self._load_and_signal, i - page_start_index, img_path, strategy_override)
                futures.append(future)
        self.active_futures = futures
        next_page_start = page_start_index + cells_per_page
        if next_page_start < len(image_files):
            next_end = min(next_page_start + cells_per_page, len(image_files))
            for i in range(next_page_start, next_end):
                if i >= len(image_files):
                    break
                img_path = str(image_files[i])
                if img_path not in self.cache:
                    future = self.load_executor.submit(self._preload_image, img_path, strategy_override)
                    self.active_futures.append(future)
    
    def _load_and_signal(self, cell_index, img_path, strategy_override=None):
        """이미지 로드 후 시그널 발생"""
        try:
            pixmap = self.load_image_with_orientation(img_path, strategy_override=strategy_override)
            self.imageLoaded.emit(cell_index, pixmap, img_path)
            return True
        except Exception as e:
            logging.error(f"이미지 로드 오류 (인덱스 {cell_index}): {e}")
            return False
    
    def _preload_image(self, img_path, strategy_override=None):
        """이미지 미리 로드 (시그널 없음)"""
        try:
            self.load_image_with_orientation(img_path, strategy_override=strategy_override)
            return True
        except:
            return False
    
    def clear_cache(self):
        """캐시 초기화"""
        self.cache.clear()
        logging.info(f"ImageLoader ({id(self)}): Cache cleared. RAW load strategy '{self._raw_load_strategy}' is preserved.") # 로그 수정
        
        # 활성 로딩 작업도 취소
        for future in self.active_futures:
            future.cancel()
        self.active_futures.clear()
        logging.info(f"ImageLoader ({id(self)}): Active loading futures cleared.")

    def set_raw_load_strategy(self, strategy: str):
        """이 ImageLoader 인스턴스의 RAW 처리 방식을 설정합니다 ('preview' 또는 'decode')."""
        if strategy in ["preview", "decode"]:
            self._raw_load_strategy = strategy
            logging.info(f"ImageLoader: RAW 처리 방식 설정됨: {strategy}")
        else:
            logging.warning(f"ImageLoader: 알 수 없는 RAW 처리 방식 '{strategy}'. 변경 안 함.")

class ThumbnailDelegate(QStyledItemDelegate):
    """썸네일 아이템의 렌더링을 담당하는 델리게이트"""
    
    # 썸네일 클릭 시그널
    thumbnailClicked = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._placeholder_pixmap = self._create_placeholder()
    
    def _create_placeholder(self):
        """플레이스홀더 이미지 생성"""
        size = UIScaleManager.get("thumbnail_image_size")
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor("#222222"))
        return pixmap
    
    def paint(self, painter, option, index):
        """썸네일 아이템 렌더링 (중앙 정렬 보장)"""
        painter.save()  # 페인터 상태 저장
        painter.setRenderHint(QPainter.Antialiasing)
        
        # --- 기본 변수 설정 ---
        rect = option.rect
        image_size = UIScaleManager.get("thumbnail_image_size")
        padding = UIScaleManager.get("thumbnail_padding")
        text_height = UIScaleManager.get("thumbnail_text_height")
        border_width = UIScaleManager.get("thumbnail_border_width")
        
        # --- 1. 배경 그리기 ---
        is_current = index.data(Qt.UserRole + 1)
        is_selected = option.state & QStyle.State_Selected
        
        # 선택 상태에 따른 배경색 설정
        if is_current or is_selected:
            bg_color = "#444444"  # 선택된 아이템은 배경색 변경
        else:
            bg_color = ThemeManager.get_color('bg_primary')
            
        painter.fillRect(rect, QColor(bg_color))
        
        # painter.setRenderHint(QPainter.Antialiasing, False)
        # --- 2. 테두리 그리기 (모든 아이템에 동일한 테두리) ---
        border_color = "#474747"  # 고정 테두리 색상
        painter.setPen(QPen(QColor(border_color), border_width))
        painter.drawRect(rect.adjusted(1, 1, -1, -1))
            
        # --- 3. 이미지 그리기 ---
        image_path = index.data(Qt.UserRole)
        if image_path:
            pixmap = index.data(Qt.DecorationRole)
            
            # 사용할 픽스맵 결정 (로딩 완료 시 썸네일, 아니면 플레이스홀더)
            target_pixmap = pixmap if pixmap and not pixmap.isNull() else self._placeholder_pixmap
            
            # 종횡비를 유지하며 스케일링
            scaled_pixmap = target_pixmap.scaled(
                image_size, image_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # 중앙 정렬을 위한 좌표 계산
            # 아이템의 전체 너비(rect.width())를 기준으로 계산해야 합니다.
            x_pos = rect.x() + (rect.width() - scaled_pixmap.width()) // 2
            
            # y 좌표도 중앙 정렬을 위해 계산
            # 이미지 영역 높이 = 전체 높이 - 텍스트 영역 높이 - 패딩*3 (상단, 이미지-텍스트 사이, 하단)
            image_area_height = rect.height() - text_height - (padding * 3)
            y_pos = rect.y() + padding + (image_area_height - scaled_pixmap.height()) // 2
            
            # 계산된 위치에 픽스맵 그리기
            painter.drawPixmap(x_pos, y_pos, scaled_pixmap)

        # --- 4. 파일명 텍스트 그리기 ---
        filename = index.data(Qt.DisplayRole)
        if filename:
            # 텍스트 영역 계산 (이미지 바로 아래)
            # y 좌표: 이미지 시작점(padding) + 이미지 높이(image_size) + 이미지와 텍스트 사이 간격(padding)
            text_rect = QRect(
                rect.x() + padding,
                rect.y() + padding + image_size + padding,
                rect.width() - (padding * 2),
                text_height
            )
            
            painter.setPen(QColor(ThemeManager.get_color('text')))
            font = QFont()
            font.setPointSize(UIScaleManager.get("font_size"))
            painter.setFont(font)
            
            metrics = painter.fontMetrics()
            elided_text = metrics.elidedText(filename, Qt.ElideMiddle, text_rect.width())
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, elided_text)

        painter.restore() # 페인터 상태 복원

    
    def sizeHint(self, option, index):
        """아이템 크기 힌트"""
        height = UIScaleManager.get("thumbnail_item_height")
        return QSize(0, height)

class DraggableThumbnailView(QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_start_position = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()
        # 기본 mousePressEvent를 호출하지 않아 즉시 선택되는 것을 방지
        # super().mousePressEvent(event) 

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if not self.drag_start_position:
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return

        # 드래그 시작
        drag = QDrag(self)
        mime_data = QMimeData()
        
        index = self.indexAt(self.drag_start_position)
        if not index.isValid():
            return
        
        # 드래그 데이터에 이미지 인덱스 저장
        mime_data.setText(f"thumbnail_drag:{index.row()}")
        drag.setMimeData(mime_data)

        # 드래그 시 보여줄 썸네일 이미지 설정
        pixmap = index.data(Qt.DecorationRole)
        if pixmap and not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            drag.setPixmap(scaled_pixmap)
            drag.setHotSpot(QPoint(32, 32))

        drag.exec_(Qt.CopyAction)
        self.drag_start_position = None # 드래그 후 초기화

    def mouseReleaseEvent(self, event):
        # 드래그가 시작되지 않았다면, 일반 클릭으로 간주하여 선택 처리
        if self.drag_start_position is not None:
            # 마우스 누른 위치와 뗀 위치가 거의 같다면 클릭으로 처리
            if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
                # 기본 QListView의 클릭 동작을 여기서 수행
                super().mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, event.pos(), event.globalPos(), event.button(), event.buttons(), event.modifiers()))
                super().mouseReleaseEvent(event)
        self.drag_start_position = None

class ThumbnailPanel(QWidget):
    """썸네일 패널 위젯 - 현재 이미지 주변의 썸네일들을 표시"""
    
    # 시그널 정의
    thumbnailClicked = Signal(int)           # 썸네일 클릭 시 인덱스 전달
    thumbnailDoubleClicked = Signal(int)     # 썸네일 더블클릭 시 인덱스 전달
    selectionChanged = Signal(list)          # 다중 선택 변경 시 인덱스 리스트 전달
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent  # PhotoSortApp 참조
        
        # 모델과 델리게이트 생성 (image_loader 전달)
        self.model = ThumbnailModel([], self.parent_app.image_loader if self.parent_app else None, self)
        self.delegate = ThumbnailDelegate(self)

        self.setup_ui()
        self.connect_signals()
        
        # 테마/언어 변경 콜백 등록
        ThemeManager.register_theme_change_callback(self.update_ui_colors)
        
    def setup_ui(self):
        """UI 구성 요소 초기화"""
        # 메인 레이아웃
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(UIScaleManager.get("control_layout_spacing"))
        
        # 썸네일 리스트 뷰
        self.list_view = DraggableThumbnailView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.delegate)
        self.list_view.setDragEnabled(True)
        
        # 리스트 뷰 설정
        self.list_view.setSelectionMode(QListView.ExtendedSelection)  # 다중 선택 허용
        self.list_view.setDragDropMode(QListView.DragOnly)           # 드래그 허용
        self.list_view.setDefaultDropAction(Qt.MoveAction)
        self.list_view.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list_view.setSpacing(UIScaleManager.get("thumbnail_item_spacing"))

        # 썸네일 아이템 간격 설정
        item_spacing = UIScaleManager.get("thumbnail_item_spacing")
        
        # 스타일 설정
        self.list_view.setStyleSheet(f"""
            QListView {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: none;
                outline: none;
                padding: {item_spacing}px;
                spacing: {item_spacing}px;
            }}
            QListView::item {{
                border: none;
                padding: 0px;
                margin-bottom: {item_spacing}px;
            }}
            QListView::item:selected {{
                background-color: {ThemeManager.get_color('accent')};
                background-color: rgba(255, 255, 255, 30);
            }}
            QScrollBar:vertical {{
                border: none;
                background: {ThemeManager.get_color('bg_primary')};
                width: 10px;
                margin: 0px 0px 0px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {ThemeManager.get_color('border')};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {ThemeManager.get_color('accent_hover')};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px;
            }}
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        
        # 레이아웃에 추가
        self.layout.addWidget(self.list_view, 1)  # 확장 가능
        
        # 패널 전체 스타일
        self.setStyleSheet(f"""
            ThumbnailPanel {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border-right: 1px solid {ThemeManager.get_color('border')};
            }}
        """)
        
        # 최소 크기 설정
        min_width = UIScaleManager.get("thumbnail_panel_min_width")
        self.setMinimumWidth(min_width)
        
    def connect_signals(self):
        """시그널 연결"""
        # 모델 시그널 연결
        logging.info("ThumbnailPanel: 시그널 연결 시작")
        self.model.currentIndexChanged.connect(self.on_current_index_changed)
        
        # 리스트 뷰 시그널 연결
        self.list_view.clicked.connect(self.on_thumbnail_clicked)
        self.list_view.doubleClicked.connect(self.on_thumbnail_double_clicked)
        
        # 선택 변경 시그널
        selection_model = self.list_view.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self.on_selection_changed)
        
        logging.info("ThumbnailPanel: 모든 시그널 연결 완료")
    
    def set_image_files(self, image_files):
        """이미지 파일 목록 설정"""
        logging.info(f"ThumbnailPanel.set_image_files: {len(image_files) if image_files else 0}개 파일 설정")
        self.model.set_image_files(image_files)
        
        # 모델 상태 확인
        logging.debug(f"ThumbnailPanel: 모델 rowCount={self.model.rowCount()}")
                
    def set_current_index(self, index):
        """현재 인덱스 설정 및 스크롤"""
        if not self.model._image_files or index < 0 or index >= len(self.model._image_files):
            return
        
        self.model.set_current_index(index)
        
        self.scroll_to_index(index)
        
        self.preload_surrounding_thumbnails(index)
    
    def scroll_to_index(self, index):
        """지정된 인덱스가 리스트 중앙에 오도록 스크롤"""
        if index < 0 or index >= self.model.rowCount():
            return
            
        model_index = self.model.createIndex(index, 0)
        self.list_view.scrollTo(model_index, QListView.PositionAtCenter)
    
    def preload_surrounding_thumbnails(self, center_index, radius=5):
        """중심 인덱스 주변의 썸네일 미리 로딩"""
        self.model.preload_thumbnails(center_index, radius)

    
    def on_current_index_changed(self, index):
        """모델의 현재 인덱스 변경 시 호출"""
        # 필요시 추가 처리
        pass
    
    def on_thumbnail_clicked(self, model_index):
        """썸네일 클릭 시 호출"""
        if model_index.isValid():
            index = model_index.row()
            self.thumbnailClicked.emit(index)
    
    def on_thumbnail_double_clicked(self, model_index):
        """썸네일 더블클릭 시 호출"""
        if model_index.isValid():
            index = model_index.row()
            self.thumbnailDoubleClicked.emit(index)
    
    def on_selection_changed(self, selected, deselected):
        """선택 변경 시 호출"""
        selection_model = self.list_view.selectionModel()
        selected_indexes = selection_model.selectedIndexes()
        selected_rows = [index.row() for index in selected_indexes]
        self.selectionChanged.emit(selected_rows)
    
    def get_selected_indexes(self):
        """현재 선택된 인덱스들 반환"""
        selection_model = self.list_view.selectionModel()
        selected_indexes = selection_model.selectedIndexes()
        return [index.row() for index in selected_indexes]
    
    def clear_selection(self):
        """선택 해제"""
        self.list_view.clearSelection()
    
    
    def update_ui_colors(self):
        """테마 변경 시 UI 색상 업데이트"""
        
        self.list_view.setStyleSheet(f"""
            QListView {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: none;
                outline: none;
            }}
            QListView::item {{
                border: none;
                padding: 0px;
            }}
            QListView::item:selected {{
                background-color: {ThemeManager.get_color('accent')};
                background-color: rgba(255, 255, 255, 30);
            }}
            QScrollBar:vertical {{
                border: none;
                background: {ThemeManager.get_color('bg_primary')};
                width: 10px;
                margin: 0px 0px 0px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {ThemeManager.get_color('border')};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {ThemeManager.get_color('accent_hover')};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px;
            }}
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
    



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

        # 제목표시줄 다크 테마
        apply_dark_title_bar(self)

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

class SessionManagementDialog(QDialog):
    def __init__(self, parent_widget: QWidget, main_app_logic: 'PhotoSortApp'): # 부모 위젯과 로직 객체를 분리
        super().__init__(parent_widget) # QDialog의 부모 설정
        self.parent_app = main_app_logic # PhotoSortApp의 메서드 호출을 위해 저장

        self.setWindowTitle(LanguageManager.translate("세션 관리"))
        self.setMinimumSize(500, 400) # 팝업창 최소 크기

        # 다크 테마 적용 (PhotoSortApp의 show_themed_message_box 또는 settings_popup 참조)
        apply_dark_title_bar(self)
        palette = QPalette(); palette.setColor(QPalette.Window, QColor(ThemeManager.get_color('bg_primary')))
        self.setPalette(palette); self.setAutoFillBackground(True)

        # --- 메인 레이아웃 ---
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # --- 1. 현재 세션 저장 버튼 ---
        self.save_current_button = QPushButton(LanguageManager.translate("현재 세션 저장"))
        self.save_current_button.setStyleSheet(self.parent_app.load_button.styleSheet()) # PhotoSortApp의 버튼 스타일 재활용
        self.save_current_button.clicked.connect(self.prompt_and_save_session)
        main_layout.addWidget(self.save_current_button)

        # --- 2. 저장된 세션 목록 ---
        list_label = QLabel(LanguageManager.translate("저장된 세션 목록 (최대 20개):"))
        list_label.setStyleSheet(f"color: {ThemeManager.get_color('text')}; margin-top: 10px;")
        main_layout.addWidget(list_label)

        self.session_list_widget = QListWidget()
        self.session_list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: 1px solid {ThemeManager.get_color('border')};
                border-radius: 3px; padding: 5px;
            }}
            QListWidget::item {{ padding: 3px 2px; }}
            QListWidget::item:selected {{
                background-color: {ThemeManager.get_color('accent')};
                color: white; /* 선택 시 텍스트 색상 */
            }}
        """)
        self.session_list_widget.currentItemChanged.connect(self.update_all_button_states) # 시그널 연결 확인
        main_layout.addWidget(self.session_list_widget, 1) # 목록이 남은 공간 차지

        # --- 3. 불러오기 및 삭제 버튼 ---
        buttons_layout = QHBoxLayout()
        self.load_button = QPushButton(LanguageManager.translate("선택 세션 불러오기"))
        self.load_button.setStyleSheet(self.parent_app.load_button.styleSheet())
        self.load_button.clicked.connect(self.load_selected_session)
        self.load_button.setEnabled(False) # 초기에는 비활성화

        self.delete_button = QPushButton(LanguageManager.translate("선택 세션 삭제"))
        self.delete_button.setStyleSheet(self.parent_app.load_button.styleSheet())
        self.delete_button.clicked.connect(self.delete_selected_session)
        self.delete_button.setEnabled(False) # 초기에는 비활성화

        buttons_layout.addStretch(1)
        buttons_layout.addWidget(self.load_button)
        buttons_layout.addWidget(self.delete_button)
        buttons_layout.addStretch(1)
        main_layout.addLayout(buttons_layout)
        
        self.populate_session_list() # 처음 열릴 때 목록 채우기
        self.update_all_button_states() # <<< 추가: 초기 버튼 상태 설정

    def populate_session_list(self):
        """PhotoSortApp의 saved_sessions를 가져와 목록 위젯을 채웁니다."""
        self.session_list_widget.clear()
        # 저장된 세션을 타임스탬프(또는 이름) 역순으로 정렬하여 최신 항목이 위로 오도록
        # 세션 이름에 날짜시간이 포함되므로, 이름 자체로 역순 정렬하면 어느 정도 최신순이 됨
        sorted_session_names = sorted(self.parent_app.saved_sessions.keys(), reverse=True)
        
        for session_name in sorted_session_names:
            # 세션 정보에서 타임스탬프를 가져와 함께 표시 (선택 사항)
            session_data = self.parent_app.saved_sessions.get(session_name, {})
            timestamp = session_data.get("timestamp", "")
            display_text = session_name
            if timestamp:
                try: # 저장된 타임스탬프 형식에 맞춰 파싱 및 재포맷
                    dt_obj = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    formatted_ts = dt_obj.strftime("%y/%m/%d %H:%M") # 예: 23/05/24 10:30
                    display_text = f"{session_name} ({formatted_ts})"
                except ValueError:
                    pass # 파싱 실패 시 이름만 표시
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, session_name) # 실제 세션 이름(키)을 데이터로 저장
            self.session_list_widget.addItem(item)
        self.update_all_button_states()


    def update_all_button_states(self): # <<< 새로운 메서드 또는 기존 update_button_states 확장
        """세션 목록 선택 상태 및 이미지 로드 상태에 따라 모든 버튼의 활성화 상태를 업데이트합니다."""
        # 1. 불러오기/삭제 버튼 상태 업데이트 (기존 로직)
        selected_item = self.session_list_widget.currentItem()
        is_item_selected = selected_item is not None
        self.load_button.setEnabled(is_item_selected)
        self.delete_button.setEnabled(is_item_selected)
        logging.debug(f"SessionManagementDialog.update_all_button_states: Item selected={is_item_selected}")

        # 2. "현재 세션 저장" 버튼 상태 업데이트
        # PhotoSortApp의 image_files 목록이 비어있지 않을 때만 활성화
        can_save_session = bool(self.parent_app.image_files) # 이미지 파일 목록이 있는지 확인
        self.save_current_button.setEnabled(can_save_session)
        logging.debug(f"SessionManagementDialog.update_all_button_states: Can save session={can_save_session}")



    def prompt_and_save_session(self):
        default_name = self.parent_app._generate_default_session_name()

        self.parent_app.is_input_dialog_active = True # 메인 앱의 플래그 설정
        try:
            text, ok = QInputDialog.getText(self,
                                             LanguageManager.translate("세션 이름"),
                                             LanguageManager.translate("저장할 세션 이름을 입력하세요:"),
                                             QLineEdit.Normal,
                                             default_name)
        finally:
            self.parent_app.is_input_dialog_active = False # 메인 앱의 플래그 해제

        if ok and text:
            if self.parent_app.save_current_session(text): # 성공 시
                self.populate_session_list() # 목록 새로고침
        elif ok and not text:
            self.parent_app.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("저장 오류"), LanguageManager.translate("세션 이름을 입력해야 합니다."))


    def load_selected_session(self):
        selected_items = self.session_list_widget.selectedItems()
        if selected_items:
            session_name_to_load = selected_items[0].data(Qt.UserRole) # 저장된 실제 이름 가져오기
            self.parent_app.load_session(session_name_to_load)
            # self.accept() # load_session 내부에서 이 팝업을 닫을 수 있음

    def delete_selected_session(self):
        selected_items = self.session_list_widget.selectedItems()
        if selected_items:
            session_name_to_delete = selected_items[0].data(Qt.UserRole)
            reply = self.parent_app.show_themed_message_box(
                QMessageBox.Question,
                LanguageManager.translate("삭제 확인"),
                LanguageManager.translate("'{session_name}' 세션을 정말 삭제하시겠습니까?").format(session_name=session_name_to_delete),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.parent_app.delete_session(session_name_to_delete)
                # self.populate_session_list() # delete_session 내부에서 호출될 것임

def format_camera_name(make, model):
    make_str = (make or "").strip()
    model_str = (model or "").strip()
    # 1. OLYMPUS IMAGING CORP. → OLYMPUS로 치환
    if make_str.upper() == "OLYMPUS IMAGING CORP.":
        make_str = "OLYMPUS"
    # 2. RICOH가 make에 있으면 make 생략
    if "RICOH" in make_str.upper():
        make_str = ""
    if make_str.upper().find("NIKON") != -1 and model_str.upper().startswith("NIKON"):
        return model_str
    if make_str.upper().find("CANON") != -1 and model_str.upper().startswith("CANON"):
        return model_str
    return f"{make_str} {model_str}".strip()

class FolderLoaderWorker(QObject):
    """백그라운드 스레드에서 폴더 스캔, 파일 매칭, 정렬 작업을 수행하는 워커"""
    startProcessing = Signal(str, str, str, list)
    
    finished = Signal(list, dict, str, str, str)
    progress = Signal(str)
    error = Signal(str, str)

    def __init__(self, supported_extensions, raw_extensions, get_datetime_func):
        super().__init__()
        self.supported_image_extensions = supported_extensions
        self.raw_extensions = raw_extensions
        self.get_datetime_from_file_fast = get_datetime_func
        self._is_running = True
        
        self.startProcessing.connect(self.process_folders)

    def stop(self):
        self._is_running = False

    @Slot(str, str, str, list)
    def process_folders(self, jpg_folder_path, raw_folder_path, mode, raw_file_list_from_main):
        """메인 처리 함수 (mode에 따라 분기)"""
        self._is_running = True
        try:
            image_files = []
            raw_files = {}

            if mode == 'raw_only':
                self.progress.emit(LanguageManager.translate("RAW 파일 정렬 중..."))
                image_files = sorted(raw_file_list_from_main, key=self.get_datetime_from_file_fast)
            
            else: # 'jpg_with_raw' or 'jpg_only'
                self.progress.emit(LanguageManager.translate("이미지 파일 스캔 중..."))
                target_path = Path(jpg_folder_path)
                temp_image_files = []
                for file_path in target_path.iterdir():
                    if not self._is_running: return
                    if file_path.is_file() and file_path.suffix.lower() in self.supported_image_extensions:
                        temp_image_files.append(file_path)
                
                if not temp_image_files:
                    self.error.emit(LanguageManager.translate("선택한 폴더에 지원하는 이미지 파일이 없습니다."), LanguageManager.translate("경고"))
                    return

                self.progress.emit(LanguageManager.translate("파일 정렬 중..."))
                image_files = sorted(temp_image_files, key=self.get_datetime_from_file_fast)

                if mode == 'jpg_with_raw' and raw_folder_path:
                    self.progress.emit(LanguageManager.translate("RAW 파일 매칭 중..."))
                    jpg_filenames = {f.stem: f for f in image_files}
                    for file_path in Path(raw_folder_path).iterdir():
                        if not self._is_running: return
                        if file_path.is_file() and file_path.suffix.lower() in self.raw_extensions:
                            if file_path.stem in jpg_filenames:
                                raw_files[file_path.stem] = file_path
            
            if not self._is_running: return
            self.finished.emit(image_files, raw_files, jpg_folder_path, raw_folder_path, mode)

        except Exception as e:
            logging.error(f"백그라운드 폴더 로딩 중 오류: {e}")
            self.error.emit(str(e), LanguageManager.translate("오류"))

class PhotoSortApp(QMainWindow):
    STATE_FILE = "photosort_data.json" # 상태 저장 파일 이름 정의
    
    # 단축키 정의 (두 함수에서 공통으로 사용)
    SHORTCUT_DEFINITIONS = [
        ("group", "탐색"),
        ("key", "WASD / 방향키", "사진 넘기기"),
        ("key", "Shift + WASD/방향키", "뷰포트 이동 (확대 중에)"),
        ("key", "Shift + A/D", "이전/다음 페이지 (그리드 모드)"),
        ("key", "Enter", "사진 목록 보기"),
        ("key", "F5", "폴더 새로고침"),
        
        ("group", "보기 설정"),
        ("key", "F1 / F2 / F3", "줌 모드 변경 (Fit / 100% / 가변)"),
        ("key", "Space", "줌 전환 (Fit/100%) 또는 그리드에서 확대"),
        ("key", "ESC", "줌 아웃 또는 그리드 복귀"),
        ("key", "Z(Zoom-out)", "줌 아웃 (가변 모드)"),
        ("key", "X(eXpand)", "줌 인 (가변 모드)"),
        ("key", "R(Reset)", "뷰포트 중앙 정렬"),
        ("key", "G(Grid)", "그리드 모드 켜기/끄기"),
        ("key", "C(Compare)", "A | B 비교 모드 켜기/끄기"),

        ("group", "파일 작업"),
        ("key", "1 ~ 9", "지정한 폴더로 사진 이동"),
        ("key", "Ctrl + Z", "파일 이동 취소 (Undo)"),
        ("key", "Ctrl + Y / Ctrl + Shift + Z", "파일 이동 다시 실행 (Redo)"),
        ("key", "Ctrl + A", "페이지 전체 선택 (그리드 모드)"),
        ("key", "Delete", "작업 상태 초기화"),
    ]

    def __init__(self):
        super().__init__()
        
        # 앱 제목 설정
        self.setWindowTitle("PhotoSort")

        # 크로스 플랫폼 윈도우 아이콘 설정
        self.set_window_icon()
        
        # 내부 변수 초기화
        self.current_folder = ""
        self.raw_folder = ""
        self.image_files = []
        self.supported_image_extensions = {
            '.jpg', '.jpeg'
        }
        self.raw_files = {}  # 키: 기본 파일명, 값: RAW 파일 경로
        self.is_raw_only_mode = False # RAW 단독 로드 모드인지 나타내는 플래그
        self.raw_extensions = {'.arw', '.crw', '.dng', '.cr2', '.cr3', '.nef', 
                             '.nrw', '.raf', '.srw', '.srf', '.sr2', '.rw2', 
                             '.rwl', '.x3f', '.gpr', '.orf', '.pef', '.ptx', 
                             '.3fr', '.fff', '.mef', '.iiq', '.braw', '.ari', '.r3d'}
        self.current_image_index = -1
        self.move_raw_files = True  # RAW 파일 이동 여부 (기본값: True)
        self.folder_count = 3  # 기본 폴더 개수 (load_state에서 덮어쓸 값)
        self.target_folders = [""] * self.folder_count  # folder_count에 따라 동적으로 리스트 생성
        self.zoom_mode = "Fit"  # 기본 확대 모드: "Fit", "100%", "Spin"
        self.last_active_zoom_mode = "100%" # 기본 확대 모드는 100%
        self.zoom_spin_value = 2.0  # 기본 200% (2.0 배율)
        self.original_pixmap = None  # 원본 이미지 pixmap
        self.panning = False  # 패닝 모드 여부
        self.pan_start_pos = QPoint(0, 0)  # 패닝 시작 위치
        self.scroll_pos = QPoint(0, 0)  # 스크롤 위치 

        self.control_panel_on_right = False # 기본값: 왼쪽 (False)

        self.viewport_move_speed = 5 # 뷰포트 이동 속도 (1~10), 기본값 5
        self.mouse_wheel_action = "photo_navigation"  # 마우스 휠 동작: "photo_navigation" 또는 "none"
        self.last_processed_camera_model = None
        self.show_grid_filenames = False  # 그리드 모드에서 파일명 표시 여부 (기본값: False)

        self.image_processing = False  # 이미지 처리 중 여부

        # --- 세션 저장을 위한 딕셔너리 ---
        # 형식: {"세션이름": {상태정보 딕셔너리}}
        self.saved_sessions = {} # 이전 self.saved_workspaces 에서 이름 변경
        # load_state에서 로드되므로 여기서 _load_saved_sessions 호출 불필요
        
        # 세션 관리 팝업 인스턴스 (중복 생성 방지용)
        self.session_management_popup = None

        # --- 뷰포트 부드러운 이동을 위한 변수 ---
        self.viewport_move_timer = QTimer(self)
        self.viewport_move_timer.setInterval(16) # 약 60 FPS (1000ms / 60 ~= 16ms)
        self.viewport_move_timer.timeout.connect(self.smooth_viewport_move)
        self.pressed_keys_for_viewport = set() # 현재 뷰포트 이동을 위해 눌린 키 저장

        # 뷰포트 저장 및 복구를 위한 변수
        self.viewport_focus_by_orientation = {
            # "landscape": {"rel_center": QPointF(0.5, 0.5), "zoom_level": "100%"},
            # "portrait": {"rel_center": QPointF(0.5, 0.5), "zoom_level": "100%"}
        } # 초기에는 비어있거나 기본값으로 채울 수 있음

        self.current_active_rel_center = QPointF(0.5, 0.5)
        self.current_active_zoom_level = "Fit"
        self.zoom_change_trigger = None        
        # self.zoom_triggered_by_double_click = False # 이전 플래그 -> self.zoom_change_trigger로 대체
        # 현재 활성화된(보여지고 있는) 뷰포트의 상대 중심과 줌 레벨
        # 이 정보는 사진 변경 시 다음 사진으로 "이어질" 수 있음
        self.current_active_rel_center = QPointF(0.5, 0.5)
        self.current_active_zoom_level = "Fit" # 초기값은 Fit
        self.zoom_change_trigger = None # "double_click", "space_key_to_zoom", "radio_button", "photo_change_same_orientation", "photo_change_diff_orientation"

        # 메모리 모니터링 및 자동 조정을 위한 타이머
        self.memory_monitor_timer = QTimer(self)
        self.memory_monitor_timer.setInterval(10000)  # 10초마다 확인
        self.memory_monitor_timer.timeout.connect(self.check_memory_usage)
        self.memory_monitor_timer.start()

        # current_image_index 주기적 자동동저장을 위한
        self.state_save_timer = QTimer(self)
        self.state_save_timer.setSingleShot(True) # 한 번만 실행되도록 설정
        self.state_save_timer.setInterval(5000)  # 5초 (5000ms)
        self.state_save_timer.timeout.connect(self._trigger_state_save_for_index) # 새 슬롯 연결

        # 시스템 사양 검사
        self.system_memory_gb = self.get_system_memory_gb()
        self.system_cores = cpu_count()

        # 파일 이동 기록 (Undo/Redo 용)
        self.move_history = [] # 이동 기록을 저장할 리스트
        self.history_pointer = -1 # 현재 히스토리 위치 (-1은 기록 없음)
        self.max_history = 10 # 최대 저장할 히스토리 개수

        # Grid 관련 변수 추가
        self.grid_mode = "Off" # 'Off', '2x2', '3x3'
        self.last_active_grid_mode = "2x2"  # 마지막으로 활성화된 그리드 모드 저장 (기본값 "2x2")
        self.current_grid_index = 0 # 현재 선택된 그리드 셀 인덱스 (0부터 시작)
        self.grid_page_start_index = 0 # 현재 그리드 페이지의 시작 이미지 인덱스
        self.previous_grid_mode = None # 이전 그리드 모드 저장 변수
        self.grid_layout = None # 그리드 레이아웃 객체
        self.grid_labels = []   # 그리드 셀 QLabel 목록

        # 다중 선택 관리 변수 추가
        self.selected_grid_indices = set()  # 선택된 그리드 셀 인덱스들 (페이지 내 상대 인덱스)
        self.primary_selected_index = -1  # 첫 번째로 선택된 이미지의 인덱스 (파일 정보 표시용)
        self.last_single_click_index = -1  # Shift+클릭 범위 선택을 위한 마지막 단일 클릭 인덱스

        # 리소스 매니저 초기화
        self.resource_manager = ResourceManager.instance()

        # === 유휴 프리로더(Idle Preloader) 타이머 추가 ===
        self.idle_preload_timer = QTimer(self)
        self.idle_preload_timer.setSingleShot(True)
        # HardwareProfileManager에서 유휴 로딩 관련 설정 가져오기
        self.idle_preload_enabled = HardwareProfileManager.get("idle_preload_enabled")
        if self.idle_preload_enabled:
            idle_interval = HardwareProfileManager.get("idle_interval_ms")
            self.idle_preload_timer.setInterval(idle_interval)
            self.idle_preload_timer.timeout.connect(self.start_idle_preloading)
            self.is_idle_preloading_active = False # 진행 중 작업 추적 플래그
            logging.info(f"유휴 프리로더 활성화 (유휴 시간: {idle_interval}ms)")
        else:
            logging.info("유휴 프리로더 비활성화 (Conservative 프로필)")

        # RAW 디코더 결과 처리 타이머 
        if not hasattr(self, 'raw_result_processor_timer'): # 중복 생성 방지
            self.raw_result_processor_timer = QTimer(self)
            self.raw_result_processor_timer.setInterval(100)  # 0.1초마다 결과 확인 (조정 가능)
            self.raw_result_processor_timer.timeout.connect(self.process_pending_raw_results)
            self.raw_result_processor_timer.start()

        # --- 그리드 썸네일 사전 생성을 위한 변수 추가 ---
        self.grid_thumbnail_cache = {"2x2": {}, "3x3": {}, "4x4": {}}
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
        self.image_loader.decodingFailedForFile.connect(self.handle_raw_decoding_failure) # <<< 새 시그널 연결

        self.is_input_dialog_active = False # 플래그 초기화 (세션창 QInputDialog가 떠 있는지 여부)
        
        # 그리드 로딩 시 빠른 표시를 위한 플레이스홀더 이미지
        self.placeholder_pixmap = QPixmap(100, 100)
        self.placeholder_pixmap.fill(QColor("#222222"))

        # === 이미지→폴더 드래그 앤 드롭 관련 변수 ===
        self.drag_start_pos = QPoint(0, 0)  # 드래그 시작 위치
        self.is_potential_drag = False  # 드래그 시작 가능 상태
        self.drag_threshold = 10  # 드래그 시작을 위한 최소 이동 거리 (픽셀)
        
        # 드래그 앤 드롭 관련 변수
        self.drag_target_label = None  # 현재 드래그 타겟 레이블
        self.original_label_styles = {}
        
        logging.info("이미지→폴더 드래그 앤 드롭 기능 초기화됨")
        # === 이미지→폴더 드래그 앤 드롭 설정 끝 ===

        self.pressed_number_keys = set()  # 현재 눌린 숫자키 추적

        # --- 첫 RAW 파일 디코딩 진행률 대화상자 ---
        self.first_raw_load_progress = None

        # --- 카메라별 RAW 처리 설정을 위한 딕셔너리 ---
        # 형식: {"카메라모델명": {"method": "preview" or "decode", "dont_ask": True or False}}
        self.camera_raw_settings = {} 

        # === 비교 모드 관련 변수 ===
        self.compare_mode_active = False  # 비교 모드 활성화 여부
        self.image_B_path = None          # B 패널에 표시될 이미지 경로
        self.original_pixmap_B = None     # B 패널의 원본 QPixmap

        
        # ==================== 여기서부터 UI 관련 코드 ====================

        # 다크 테마 적용
        self.setup_dark_theme()
        
        # 제목 표시줄 다크 테마 적용
        apply_dark_title_bar(self)
        
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

        # === 썸네일 패널 생성 ===
        self.thumbnail_panel = ThumbnailPanel(self)
        self.thumbnail_panel.hide()  # 초기에는 숨김 (Grid Off 모드에서만 표시)

        # 썸네일 패널 시그널 연결
        self.thumbnail_panel.thumbnailClicked.connect(self.on_thumbnail_clicked)
        self.thumbnail_panel.thumbnailDoubleClicked.connect(self.on_thumbnail_double_clicked)
        self.thumbnail_panel.selectionChanged.connect(self.on_thumbnail_selection_changed)
        self.thumbnail_panel.model.thumbnailRequested.connect(self.request_thumbnail_load)
        
        # 1. 스크롤 가능한 컨트롤 패널을 위한 QScrollArea 생성
        self.control_panel = QScrollArea() # 기존 self.control_panel을 QScrollArea로 변경
        self.control_panel.setWidgetResizable(True) # 내용물이 스크롤 영역에 꽉 차도록 설정
        self.control_panel.setFrameShape(QFrame.NoFrame) # 테두리 제거
        self.control_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff) # 가로 스크롤바는 항상 끔

        # 2. 스크롤 영역에 들어갈 실제 콘텐츠를 담을 위젯 생성
        scroll_content_widget = QWidget()

        # 3. 기존 control_layout을 이 새로운 위젯에 설정
        self.control_layout = QVBoxLayout(scroll_content_widget)
        self.control_layout.setContentsMargins(*UIScaleManager.get_margins())
        self.control_layout.setSpacing(UIScaleManager.get("control_layout_spacing"))

        # 4. QScrollArea(self.control_panel)에 콘텐츠 위젯을 설정
        self.control_panel.setWidget(scroll_content_widget)

        # --- [수정] 이미지 뷰 영역: 분할 가능한 구조로 변경 ---
        # 1. 전체 이미지 뷰를 담을 메인 패널 (기존 image_panel 역할)
        self.image_panel = QFrame()
        self.image_panel.setFrameShape(QFrame.NoFrame)
        self.image_panel.setAutoFillBackground(True)
        image_palette = self.image_panel.palette()
        image_palette.setColor(QPalette.Window, QColor(0, 0, 0))
        self.image_panel.setPalette(image_palette)
        # 캔버스 전체 영역에 대한 드래그 앤 드롭 활성화
        self.image_panel.setAcceptDrops(True)
        self.image_panel.dragEnterEvent = self.canvas_dragEnterEvent
        self.image_panel.dropEvent = self.canvas_dropEvent
        
        # 2. 메인 패널 내부에 레이아웃과 스플리터 배치
        self.view_splitter_layout = QHBoxLayout(self.image_panel)
        self.view_splitter_layout.setContentsMargins(0, 0, 0, 0)
        self.view_splitter_layout.setSpacing(0)
        self.view_splitter = QSplitter(Qt.Horizontal)
        self.view_splitter.setStyleSheet("QSplitter::handle { background-color: #222222; } QSplitter::handle:hover { background-color: #444444; }")
        self.view_splitter.setHandleWidth(4) # 분할자 핸들 너비
        self.view_splitter_layout.addWidget(self.view_splitter)

        # 3. 패널 A (기존 메인 뷰) 위젯 설정
        self.image_container = QWidget()
        self.image_container.setStyleSheet("background-color: black;")
        self.image_label = QLabel(self.image_container)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: transparent;")
        self.scroll_area = ZoomScrollArea(self)
        self.scroll_area.setWidget(self.image_container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: black; border: none;")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 패널 A 마우스 이벤트 연결 (기존과 동일)
        self.image_container.setMouseTracking(True)
        self.image_container.mousePressEvent = self.image_mouse_press_event
        self.image_container.mouseMoveEvent = self.image_mouse_move_event
        self.image_container.mouseReleaseEvent = self.image_mouse_release_event
        self.image_container.mouseDoubleClickEvent = self.image_mouse_double_click_event

        # 4. 패널 B (비교 뷰) 위젯 설정
        self.image_container_B = QWidget()
        self.image_container_B.setStyleSheet("background-color: black;")
        self.image_label_B = QLabel(self.image_container_B)
        self.image_label_B.setAlignment(Qt.AlignCenter)
        self.image_label_B.setStyleSheet("background-color: transparent; color: #888888;")
        self.image_label_B.setText(LanguageManager.translate("비교할 이미지를 썸네일 패널에서 이곳으로 드래그하세요."))
        self.scroll_area_B = ZoomScrollArea(self)
        self.scroll_area_B.setWidget(self.image_container_B)
        self.scroll_area_B.setWidgetResizable(True)
        self.scroll_area_B.setAlignment(Qt.AlignCenter)
        self.scroll_area_B.setStyleSheet("background-color: black; border: none;")
        self.scroll_area_B.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area_B.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 패널 B 드래그 앤 드롭, 마우스 이벤트, 우클릭 메뉴 연결
        self.scroll_area_B.setAcceptDrops(True)
        self.scroll_area_B.dragEnterEvent = self.canvas_B_dragEnterEvent
        self.scroll_area_B.dropEvent = self.canvas_B_dropEvent
        
        self.image_container_B.setMouseTracking(True)
        self.image_container_B.mousePressEvent = self.image_B_mouse_press_event
        self.image_container_B.mouseMoveEvent = self.image_B_mouse_move_event
        self.image_container_B.mouseReleaseEvent = self.image_B_mouse_release_event

        # 5. 스플리터에 패널 A, B 추가
        self.view_splitter.addWidget(self.scroll_area)   # 패널 A
        self.view_splitter.addWidget(self.scroll_area_B) # 패널 B
        self.scroll_area_B.hide() # 비교 모드가 아니면 숨김

        # B 패널 내에 레이아웃 설정
        self.image_container_B_layout = QVBoxLayout(self.image_container_B)
        self.image_container_B_layout.setContentsMargins(0, 0, 0, 0)
        self.image_container_B_layout.addWidget(self.image_label_B)

        # B 패널 닫기 버튼 추가
        self.close_compare_button = QPushButton("✕", self.scroll_area_B)
        self.close_compare_button.setFixedSize(40, 40)
        self.close_compare_button.setCursor(Qt.PointingHandCursor)
        self.close_compare_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 40, 40, 180);
                color: #AAAAAA;
                border: 1px solid #555555;
                border-radius: 20px;
                font-size: 20px;
            }
            QPushButton:hover {
                background-color: rgba(60, 60, 60, 220);
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: rgba(20, 20, 20, 220);
            }
        """)
        self.close_compare_button.clicked.connect(self.deactivate_compare_mode)
        self.close_compare_button.hide() # 평소에는 숨김

        # 6. 미니맵 위젯 생성 (부모를 self.image_panel로 유지)
        self.minimap_widget = QWidget(self.scroll_area)
        self.minimap_widget.setStyleSheet("background-color: rgba(20, 20, 20, 200); border: 1px solid #666666;")
        self.minimap_widget.setFixedSize(self.minimap_width, self.minimap_height)
        self.minimap_widget.hide()
        self.minimap_label = QLabel(self.minimap_widget)
        self.minimap_label.setAlignment(Qt.AlignCenter)
        self.minimap_layout = QVBoxLayout(self.minimap_widget)
        self.minimap_layout.setContentsMargins(0, 0, 0, 0)
        self.minimap_layout.addWidget(self.minimap_label)
        self.minimap_widget.setMouseTracking(True)
        self.minimap_widget.mousePressEvent = self.minimap_mouse_press_event
        self.minimap_widget.mouseMoveEvent = self.minimap_mouse_move_event
        self.minimap_widget.mouseReleaseEvent = self.minimap_mouse_release_event

        # Compare 모드 파일명 라벨
        self.filename_label_A = QLabel(self.scroll_area)
        self.filename_label_B = QLabel(self.scroll_area_B)
        
        filename_label_style = """
            QLabel {
                background-color: rgba(0, 0, 0, 0.6);
                color: white;
                padding: 4px 4px;
                border-radius: 3px;
                font-size: 10pt;
            }
        """
        self.filename_label_A.setStyleSheet(filename_label_style)
        self.filename_label_B.setStyleSheet(filename_label_style)
        
        self.filename_label_A.hide()
        self.filename_label_B.hide()
        
        # 세로 가운데 정렬을 위한 상단 Stretch
        self.control_layout.addStretch(1)

        # --- JPG 폴더 섹션 ---
        self.load_button = QPushButton(LanguageManager.translate("이미지 불러오기")) # 버튼 먼저 추가
        self.load_button.setStyleSheet(ThemeManager.generate_main_button_style())
        self.load_button.clicked.connect(self.load_jpg_folder)
        self.control_layout.addWidget(self.load_button) # 컨트롤 레이아웃에 직접 추가

        # JPG 폴더 경로/클리어 컨테이너
        jpg_folder_container = QWidget()
        jpg_folder_layout = QHBoxLayout(jpg_folder_container)
        jpg_folder_layout.setContentsMargins(0, 0, 0, 0)  # 상하 여백 제거 (0,3,0,3)->(0,0,0,0)
        jpg_folder_layout.setSpacing(UIScaleManager.get("folder_container_spacing", 5))

        # JPG 폴더 경로 표시 레이블 추가
        folder_label_padding = UIScaleManager.get("folder_label_padding")
        self.folder_path_label = InfoFolderPathLabel(LanguageManager.translate("폴더 경로"))
        self.folder_path_label.set_folder_index(-2) # JPG 폴더 인덱스: -2
        self.folder_path_label.doubleClicked.connect(self.open_folder_in_explorer)
        self.folder_path_label.folderDropped.connect(self._handle_canvas_folder_drop)

        # JPG 폴더 클리어 버튼 (X) 추가
        self.jpg_clear_button = QPushButton("✕")
        self.jpg_clear_button.setStyleSheet(ThemeManager.generate_action_button_style())
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
        self.match_raw_button.setStyleSheet(ThemeManager.generate_main_button_style())
        self.match_raw_button.clicked.connect(self.on_match_raw_button_clicked)
        self.control_layout.addWidget(self.match_raw_button) # 컨트롤 레이아웃에 직접 추가

        # RAW 폴더 경로/클리어 컨테이너
        raw_folder_container = QWidget()
        raw_folder_layout = QHBoxLayout(raw_folder_container)
        raw_folder_layout.setContentsMargins(0, 0, 0, 0) # 상하 여백 제거 (0,3,0,3)->(0,0,0,0)
        raw_folder_layout.setSpacing(UIScaleManager.get("folder_container_spacing", 5))

        # RAW 폴더 경로 표시 레이블 추가
        folder_label_padding = UIScaleManager.get("folder_label_padding")
        self.raw_folder_path_label = InfoFolderPathLabel(LanguageManager.translate("폴더 경로"))
        self.raw_folder_path_label.set_folder_index(-1) # RAW 폴더 인덱스: -1
        self.raw_folder_path_label.doubleClicked.connect(self.open_raw_folder_in_explorer)
        self.raw_folder_path_label.folderDropped.connect(lambda path: self._handle_raw_folder_drop(path))

        # RAW 폴더 클리어 버튼 (X) 추가
        self.raw_clear_button = QPushButton("✕")
        self.raw_clear_button.setStyleSheet(ThemeManager.generate_action_button_style())
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
        self.raw_toggle_button.setStyleSheet(ThemeManager.generate_checkbox_style())
        
        # 토글 버튼을 레이아웃에 가운데 정렬로 추가
        self.toggle_layout.addStretch()
        self.toggle_layout.addWidget(self.raw_toggle_button)
        self.toggle_layout.addStretch()
        
        # 컨트롤 패널에 토글 컨테이너 추가
        self.control_layout.addWidget(self.toggle_container)
        
        # 구분선 추가
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        self.line_before_folders = HorizontalLine()
        self.control_layout.addWidget(self.line_before_folders)
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))

        # 분류 폴더 설정 영역
        self._rebuild_folder_selection_ui() # 이 시점에는 self.folder_count = 3
        
        # 구분선 추가
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        self.control_layout.addWidget(HorizontalLine())
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        
        # 이미지 줌 설정 UI 구성
        self.setup_zoom_ui()

        # 구분선 추가
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        self.control_layout.addWidget(HorizontalLine())
        self.control_layout.addSpacing(UIScaleManager.get("section_spacing", 20))
        
        # Grid 설정 UI 구성 (Zoom UI 아래 추가)
        self.setup_grid_ui()

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

        logging.info(f"__init__: 컨트롤 패널 오른쪽 배치 = {getattr(self, 'control_panel_on_right', False)}")

        # 초기에는 2패널 구조로 시작 (썸네일 패널은 숨김)
        self.thumbnail_panel.hide()
        
        if getattr(self, 'control_panel_on_right', False):
            # 우측 컨트롤 패널: [이미지] [컨트롤]
            self.splitter.addWidget(self.image_panel)      # 인덱스 0
            self.splitter.addWidget(self.control_panel)    # 인덱스 1
        else:
            # 좌측 컨트롤 패널: [컨트롤] [이미지]
            self.splitter.addWidget(self.control_panel)    # 인덱스 0
            self.splitter.addWidget(self.image_panel)      # 인덱스 1
        
        # 화면 크기가 변경되면 레이아웃 다시 조정
        QGuiApplication.instance().primaryScreen().geometryChanged.connect(self.adjust_layout)

        # --- 초기 UI 상태 설정 추가 ---
        self.update_raw_toggle_state() # RAW 토글 초기 상태 설정
        self.update_info_folder_label_style(self.folder_path_label, self.current_folder) # JPG 폴더 레이블 초기 스타일
        self.update_info_folder_label_style(self.raw_folder_path_label, self.raw_folder) # RAW 폴더 레이블 초기 스타일
        self.update_match_raw_button_state() # <--- 추가: RAW 관련 버튼 초기 상태 업데이트      
        
        # 화면 해상도 기반 면적 75% 크기로 중앙 배치
        screen = QGuiApplication.primaryScreen()
        if screen:
            available_geometry = screen.availableGeometry()
            screen_width = available_geometry.width()
            screen_height = available_geometry.height()
            
            # 면적 기준 75%를 위한 스케일 팩터 계산
            scale_factor = 0.75 ** 0.5  # √0.75 ≈ 0.866
            
            # 75% 면적 크기 계산
            window_width = int(screen_width * scale_factor)
            window_height = int(screen_height * scale_factor)
            
            # 중앙 위치 계산
            center_x = (screen_width - window_width) // 2
            center_y = (screen_height - window_height) // 2
            
            # 윈도우 크기 및 위치 설정
            self.setGeometry(center_x, center_y, window_width, window_height)
        else:
            # 화면 정보를 가져올 수 없는 경우 기본 크기로 설정
            self.resize(1200, 800)

        # 초기 레이아웃 설정
        QApplication.processEvents()
        self.adjust_layout()
        
        # 키보드 포커스 설정
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        
        # 더블클릭 줌 관련 변수 추가
        self.center_image = False  # 이미지를 가운데로 이동할지 여부 플래그
        self.center_on_click = False  # 클릭한 지점을 중심으로 줌할지 여부 플래그
        self.double_click_pos = QPoint(0, 0)  # 더블클릭 위치 저장

        # 스페이스바 처리를 위한 플래그 추가
        self.space_pressed = False

        # 애플리케이션 레벨 이벤트 필터 설치
        self.installEventFilter(self)

        # --- 프로그램 시작 시 상태 불러오기 (UI 로드 후 실행) ---
        # QTimer.singleShot(100, self.load_state)

        # --- 파일 목록 다이얼로그 인스턴스 변수 추가 ---
        self.file_list_dialog = None

        # 테마 관리자 초기화 및 콜백 등록
        ThemeManager.register_theme_change_callback(self.update_ui_colors)
        
        # 언어 및 날짜 형식 관련 콜백 등록
        LanguageManager.register_language_change_callback(self.update_ui_texts)
        LanguageManager.register_language_change_callback(self.update_performance_profile_combo_text)
        DateFormatManager.register_format_change_callback(self.update_date_formats)

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

        # 드래그 앤 드랍 관련 변수
        self.drag_target_label = None  # 현재 드래그 타겟 레이블
        self.original_label_styles = {}  # 원래 레이블 스타일 저장
        
        logging.info("드래그 앤 드랍 기능 활성화됨")
        # === 드래그 앤 드랍 설정 끝 ===

        self.update_scrollbar_style()

        # 설정 창에 사용될 UI 컨트롤들을 미리 생성합니다.
        self._create_settings_controls()

        self.update_all_folder_labels_state()

        self._is_silent_load = False

        # --- 백그라운드 폴더 로더 설정 ---
        self.folder_loader_thread = QThread()
        self.folder_loader_worker = FolderLoaderWorker(
            self.supported_image_extensions, self.raw_extensions, self.get_datetime_from_file_fast
        )
        self.folder_loader_worker.moveToThread(self.folder_loader_thread)

        # 시그널 연결
        self.folder_loader_worker.finished.connect(self.on_loading_finished)
        self.folder_loader_worker.progress.connect(self.on_loading_progress)
        self.folder_loader_worker.error.connect(self.on_loading_error)
        
        self.folder_loader_thread.start()
        self.loading_progress_dialog = None
        # --- 백그라운드 폴더 로더 설정 끝 ---

        self.scroll_area.verticalScrollBar().valueChanged.connect(self._sync_viewports)
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self._sync_viewports)


    def on_loading_progress(self, message):
        """로딩 진행 상황을 로딩창에 업데이트합니다."""
        if self.loading_progress_dialog:
            self.loading_progress_dialog.setLabelText(message)
            QApplication.processEvents() # UI 업데이트 강제

    def on_loading_error(self, message, title):
        """로딩 중 오류 발생 시 처리합니다."""
        if self.loading_progress_dialog:
            self.loading_progress_dialog.close()
            self.loading_progress_dialog = None
        
        self.show_themed_message_box(QMessageBox.Warning, title, message)
        self._reset_workspace_after_load_fail()

    def on_loading_finished(self, image_files, raw_files, jpg_folder, raw_folder, final_mode):
        """백그라운드 로딩 완료 시 UI를 업데이트합니다."""
        if self.loading_progress_dialog:
            self.loading_progress_dialog.close()
            self.loading_progress_dialog = None

        if not image_files:
            logging.warning("백그라운드 로더가 빈 이미지 목록을 반환했습니다.")
            self._reset_workspace_after_load_fail()
            return
            
        # 성공적으로 로드된 데이터로 앱 상태 업데이트
        self.image_files = image_files
        self.raw_files = raw_files
        
        if final_mode == 'raw_only':
            self.is_raw_only_mode = True
            self.raw_folder = jpg_folder
            self.current_folder = ""
        else:
            self.is_raw_only_mode = False
            self.current_folder = jpg_folder
            self.raw_folder = raw_folder

        logging.info(f"백그라운드 로딩 완료 (모드: {final_mode}): {len(self.image_files)}개 이미지, {len(self.raw_files)}개 RAW 매칭")

        if final_mode == 'jpg_with_raw' and not self._is_silent_load:
            matched_count = len(raw_files)
            total_jpg_count = len(image_files)
            if matched_count > 0:
                self.show_themed_message_box(
                    QMessageBox.Information,
                    LanguageManager.translate("RAW 파일 매칭 결과"),
                    f"{LanguageManager.translate('RAW 파일이 매칭되었습니다.')}\n{matched_count} / {total_jpg_count}"
                )
            else:
                self.show_themed_message_box(
                    QMessageBox.Information,
                    LanguageManager.translate("정보"),
                    LanguageManager.translate("선택한 RAW 폴더에서 매칭되는 파일을 찾을 수 없습니다.")
                )

        # UI 업데이트
        if self.current_folder:
            self.folder_path_label.setText(self.current_folder)
        else:
            self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        
        if self.raw_folder:
            self.raw_folder_path_label.setText(self.raw_folder)
        else:
            self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        
        self.grid_page_start_index = 0
        self.current_grid_index = 0
        self.image_loader.clear_cache()
        self.zoom_mode = "Fit"
        self.fit_radio.setChecked(True)
        self.grid_mode = "Off"
        self.grid_off_radio.setChecked(True)
        self.update_zoom_radio_buttons_state()
        
        self.current_image_index = 0
        self.display_current_image()
        
        self.update_jpg_folder_ui_state()
        self.update_raw_folder_ui_state()
        self.update_match_raw_button_state()
        self.update_all_folder_labels_state()

        self.thumbnail_panel.set_image_files(self.image_files)
        self.update_thumbnail_panel_visibility()
        if self.current_image_index >= 0:
            self.thumbnail_panel.set_current_index(self.current_image_index)
        
        self.save_state()

        self._is_silent_load = False

    def _reset_workspace_after_load_fail(self):
        """로드 실패 후 UI를 안전한 상태로 초기화합니다."""
        self.image_files = []
        self.current_image_index = -1
        self.is_raw_only_mode = False
        self.image_label.clear()
        self.image_label.setStyleSheet("background-color: black;")
        self.setWindowTitle("PhotoSort")
        self.update_counters()
        self.update_file_info_display(None)
        self.update_jpg_folder_ui_state()
        self.update_raw_folder_ui_state()
        self.update_match_raw_button_state()
        self.update_all_folder_labels_state()

    def reset_application_settings(self):
        """사용자에게 확인을 받은 후, 설정 파일을 삭제하고 앱을 재시작합니다."""
        title = LanguageManager.translate("초기화 확인")
        message = LanguageManager.translate("모든 설정을 초기화하고 프로그램을 재시작하시겠습니까?\n이 작업은 되돌릴 수 없습니다.")
        
        reply = self.show_themed_message_box(
            QMessageBox.Question,
            title,
            message,
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel
        )

        if reply == QMessageBox.Yes:
            logging.info("사용자가 프로그램 설정 초기화를 승인했습니다.")
            
            state_file_path = self.get_script_dir() / self.STATE_FILE
            
            try:
                if state_file_path.exists():
                    state_file_path.unlink()
                    logging.info(f"설정 파일 삭제 성공: {state_file_path}")
            except Exception as e:
                logging.error(f"설정 파일 삭제 실패: {e}")
                self.show_themed_message_box(
                    QMessageBox.Critical, LanguageManager.translate("오류"),
                    f"설정 파일 삭제에 실패했습니다:\n{e}"
                )
                return

            # 파일 삭제 후 즉시 재시작 함수 호출
            self.restart_application()

    def restart_application(self):
        """현재 애플리케이션을 재시작합니다. (안정적인 os.execv 방식)"""
        logging.info("애플리케이션 재시작을 시도합니다.")
        
        # closeEvent가 호출되지 않으므로, 재시작 전에 필수적인 정리 작업을 수행합니다.
        try:
            logging.info("재시작 전 리소스 정리 시작...")
            # 활성 타이머 중지
            if hasattr(self, 'memory_monitor_timer') and self.memory_monitor_timer.isActive():
                self.memory_monitor_timer.stop()
            if hasattr(self, 'raw_result_processor_timer') and self.raw_result_processor_timer.isActive():
                self.raw_result_processor_timer.stop()
                
            # 리소스 매니저 종료
            if hasattr(self, 'resource_manager'):
                self.resource_manager.shutdown()
            
            # 로그 핸들러 닫기
            for handler in logging.root.handlers[:]:
                handler.close()
                logging.root.removeHandler(handler)
                
            logging.info("리소스 정리 완료. os.execv 호출...")

            # 현재 실행 파일 경로와 인자 가져오기
            executable = sys.executable
            args = sys.argv
            
            # 현재 프로세스를 새 프로세스로 완전히 대체합니다.
            os.execv(executable, [executable] + args)
            
        except Exception as e:
            logging.error(f"애플리케이션 재시작 실패: {e}")
            # 이 시점에서는 메시지 박스가 제대로 동작하지 않을 수 있으므로, 로그에만 의존합니다.
            # 만약 이 코드가 실행된다면, os.execv 호출에 실패한 것입니다.


    def start_idle_preloading(self):
        """사용자가 유휴 상태일 때 백그라운드에서 이미지를 미리 로드합니다."""
        # 앱 상태 확인
        if not self.image_files or self.grid_mode != "Off" or self.is_idle_preloading_active:
            return

        # 현재 캐시된 파일들의 set과 로딩 중인 파일들의 set을 만듭니다.
        cached_paths = set(self.image_loader.cache.keys())
        # ResourceManager를 통해 현재 활성/대기 중인 작업 경로를 가져오는 기능이 필요할 수 있으나,
        # 여기서는 간단하게 캐시된 경로만 확인합니다.

        # 미리 로드할 파일 목록을 결정합니다.
        # 현재 이미지 위치에서부터 양방향으로 순차적으로 찾는 것이 효과적입니다.
        files_to_preload = []
        total_files = len(self.image_files)
        
        # 캐시가 꽉 찼는지 먼저 확인
        if len(cached_paths) >= self.image_loader.cache_limit:
            logging.info("유휴 프리로더: 캐시가 이미 가득 차서 실행하지 않습니다.")
            return

        # 현재 인덱스에서 시작하여 양방향으로 탐색
        for i in range(1, total_files):
            # 앞으로 탐색
            forward_index = (self.current_image_index + i) % total_files
            forward_path = str(self.image_files[forward_index])
            if forward_path not in cached_paths:
                files_to_preload.append(forward_path)

            # 뒤로 탐색 (중복 방지)
            backward_index = (self.current_image_index - i + total_files) % total_files
            if backward_index != forward_index:
                backward_path = str(self.image_files[backward_index])
                if backward_path not in cached_paths:
                    files_to_preload.append(backward_path)
        
        if not files_to_preload:
            logging.info("유휴 프리로더: 모든 이미지가 이미 캐시되었습니다.")
            return

        logging.info(f"유휴 프리로더: {len(files_to_preload)}개의 이미지를 낮은 우선순위로 로딩 시작합니다.")
        self.is_idle_preloading_active = True

        # ResourceManager를 통해 'low' 우선순위로 작업을 제출합니다.
        for path in files_to_preload:
            # 매번 루프를 돌 때마다 중단 플래그와 캐시 상태를 확인합니다.
            if not self.is_idle_preloading_active:
                logging.info("유휴 프리로더: 사용자 입력으로 인해 로딩이 중단되었습니다.")
                break
            
            if len(self.image_loader.cache) >= self.image_loader.cache_limit:
                logging.info("유휴 프리로더: 캐시가 가득 차서 로딩을 중단합니다.")
                break
            
            # 이미 캐시되었거나 다른 작업에서 로딩 중일 수 있으므로 다시 확인
            if path in self.image_loader.cache:
                continue
            
            # _preload_image_for_grid 함수는 내부적으로 ImageLoader 캐시를 채우므로 재사용합니다.
            # 이 함수는 RAW 파일의 경우 preview만 로드하므로, 유휴 로딩 시에도 시스템 부하가 적습니다.
            self.resource_manager.submit_imaging_task_with_priority(
                'low',
                self._preload_image_for_grid,
                path
            )

        # 모든 작업 제출이 끝나면 플래그를 리셋합니다.
        # 실제 작업은 백그라운드에서 계속됩니다.
        self.is_idle_preloading_active = False
        logging.info("유휴 프리로더: 모든 로딩 작업 제출 완료.")

    def deactivate_compare_mode(self):
        """비교 모드 X 버튼 클릭 시 동작 처리"""
        if not self.compare_mode_active:
            return

        # B 캔버스에 이미지가 로드되어 있으면, 이미지만 언로드
        if self.image_B_path:
            logging.info("비교 이미지 언로드")
            self.image_B_path = None
            self.original_pixmap_B = None
            self.image_label_B.clear()
            self.image_label_B.setText(LanguageManager.translate("비교할 이미지를 썸네일 패널에서 이곳으로 드래그하세요."))
        else:
            # B 캔버스가 비어있으면, 비교 모드 종료 (Grid Off로 전환)
            logging.info("비교 모드 종료")
            self.grid_off_radio.setChecked(True)
            self._on_grid_mode_toggled(self.grid_off_radio)

    def image_B_mouse_press_event(self, event):
        """B 패널 마우스 클릭 이벤트 처리 (패닝 시작 및 우클릭 메뉴)"""
        if event.button() == Qt.RightButton and self.image_B_path:
            self.show_context_menu_for_B(event.pos())
            return
            
        # 100% 또는 Spin 모드에서만 패닝 활성화
        if self.zoom_mode in ["100%", "Spin"]:
            if event.button() == Qt.LeftButton:
                self.panning = True
                self.pan_start_pos = event.position().toPoint()
                self.image_start_pos = self.image_label.pos() # A 캔버스 위치 기준
                self.setCursor(Qt.ClosedHandCursor)

    def image_B_mouse_move_event(self, event):
        """B 패널 마우스 이동 이벤트 처리 (A와 동일한 패닝 로직)"""
        if not self.panning:
            return
        
        # A 캔버스의 패닝 로직을 그대로 사용합니다.
        # A 캔버스의 image_label 위치를 변경하고, _sync_viewports를 호출합니다.
        self.image_mouse_move_event(event)

    def image_B_mouse_release_event(self, event):
        """B 패널 마우스 릴리스 이벤트 처리 (A와 동일한 패닝 종료 로직)"""
        if event.button() == Qt.LeftButton and self.panning:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
            # A 캔버스와 동일하게 뷰포트 포커스 저장
            if self.grid_mode == "Off" and self.zoom_mode in ["100%", "Spin"] and \
               self.original_pixmap and 0 <= self.current_image_index < len(self.image_files):
                current_rel_center = self._get_current_view_relative_center()
                self.current_active_rel_center = current_rel_center
                self.current_active_zoom_level = self.zoom_mode
                self._save_orientation_viewport_focus(self.current_image_orientation, current_rel_center, self.zoom_mode)
            
            if self.minimap_visible and self.minimap_widget.isVisible():
                self.update_minimap()

    def move_image_B_to_folder(self, folder_index, specific_index=None):
        """B 패널의 이미지를 이동합니다. specific_index가 주어지면 해당 인덱스의 파일을 이동합니다."""
        image_to_move_path = None
        image_to_move_index = -1

        # 1. 이동할 파일 경로와 인덱스 결정
        if specific_index is not None and 0 <= specific_index < len(self.image_files):
             image_to_move_path = self.image_files[specific_index]
             image_to_move_index = specific_index
        elif self.image_B_path: # 우클릭 메뉴 등 인덱스 없이 호출된 경우
             image_to_move_path = self.image_B_path
             try:
                 image_to_move_index = self.image_files.index(image_to_move_path)
             except ValueError:
                 logging.error(f"B 캔버스 이미지({image_to_move_path.name})가 메인 리스트에 없습니다.")
                 image_to_move_index = -1
        
        if not image_to_move_path:
            logging.warning("B 패널에서 이동할 이미지를 찾을 수 없습니다.")
            return
        
        target_folder = self.target_folders[folder_index]
        if not target_folder or not os.path.isdir(target_folder):
            self.show_themed_message_box(QMessageBox.Warning, "경고", "유효하지 않은 폴더입니다.")
            return

        # 2. 파일 이동 실행 (Undo/Redo를 위한 정보 수집 포함)
        moved_jpg_path = None
        moved_raw_path = None
        raw_path_before_move = None
        
        try:
            moved_jpg_path = self.move_file(image_to_move_path, target_folder)
            if moved_jpg_path is None:
                self.show_themed_message_box(QMessageBox.Critical, "에러", f"파일 이동 중 오류 발생: {image_to_move_path.name}")
                return

            raw_moved_successfully = True
            if self.move_raw_files:
                base_name = image_to_move_path.stem
                if base_name in self.raw_files:
                    raw_path_before_move = self.raw_files[base_name]
                    moved_raw_path = self.move_file(raw_path_before_move, target_folder)
                    if moved_raw_path:
                        del self.raw_files[base_name]
                    else:
                        raw_moved_successfully = False
                        self.show_themed_message_box(QMessageBox.Warning, "경고", f"RAW 파일 이동 실패: {raw_path_before_move.name}")

            # 3. Undo/Redo 히스토리 추가
            if moved_jpg_path and image_to_move_index != -1:
                history_entry = {
                    "jpg_source": str(image_to_move_path),
                    "jpg_target": str(moved_jpg_path),
                    "raw_source": str(raw_path_before_move) if raw_path_before_move else None,
                    "raw_target": str(moved_raw_path) if moved_raw_path and raw_moved_successfully else None,
                    "index_before_move": image_to_move_index, # 이동된 B 이미지의 인덱스
                    "a_index_before_move": self.current_image_index, # <<< 추가: 당시 A 이미지의 인덱스
                    "mode": "CompareB"
                }
                self.add_move_history(history_entry)

            # 4. B 패널 UI 초기화
            self.image_B_path = None
            self.original_pixmap_B = None
            self.image_label_B.clear()
            self.image_label_B.setText(LanguageManager.translate("비교할 이미지를 썸네일 패널에서 이곳으로 드래그하세요."))
            
            # 5. 메인 파일 리스트에서 제거 및 A 패널 업데이트
            if image_to_move_index != -1:
                self.image_files.pop(image_to_move_index)
                
                # 만약 이동한 파일이 A 패널에도 보이고 있었다면 A 패널도 업데이트
                if image_to_move_index == self.current_image_index:
                    if not self.image_files:
                        self.current_image_index = -1
                    elif self.current_image_index >= len(self.image_files):
                        self.current_image_index = len(self.image_files) - 1
                    
                    self.display_current_image()
                # A 패널의 인덱스가 이동한 파일보다 뒤에 있었다면 인덱스 조정
                elif image_to_move_index < self.current_image_index:
                    self.current_image_index -= 1
            
            # 6. 썸네일 패널 및 카운터 업데이트
            self.thumbnail_panel.set_image_files(self.image_files)
            self.update_thumbnail_current_index()
            self.update_counters()

        except Exception as e:
            logging.error(f"B 패널 이미지 이동 중 예외 발생: {e}")
            self.show_themed_message_box(QMessageBox.Critical, "에러", f"파일 이동 중 오류 발생: {str(e)}")

    def show_context_menu_for_B(self, pos):
        if not self.image_B_path:
            return

        context_menu = QMenu(self)
        context_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: 1px solid {ThemeManager.get_color('border')};
                padding: 2px;
            }}
            QMenu::item {{
                padding: 8px 16px;
                background-color: transparent;
            }}
            QMenu::item:selected {{
                background-color: {ThemeManager.get_color('accent')};
                color: {ThemeManager.get_color('text')};
            }}
        """)
        
        # <<< 로직을 create_context_menu와 동일하게 수정 >>>
        for i in range(self.folder_count):
            folder_path = self.target_folders[i] if i < len(self.target_folders) else ""
            
            if folder_path and os.path.isdir(folder_path):
                folder_name = Path(folder_path).name
                menu_text = LanguageManager.translate("이동 - 폴더 {0} [{1}]").format(i + 1, folder_name)
            else:
                menu_text = LanguageManager.translate("이동 - 폴더 {0}").format(i + 1)
                
            action = QAction(menu_text, self)
            action.triggered.connect(lambda checked, idx=i: self.move_image_B_to_folder(idx))
            
            # 폴더가 지정되지 않았거나 유효하지 않으면 비활성화
            if not folder_path or not os.path.isdir(folder_path):
                action.setEnabled(False)
                
            context_menu.addAction(action)

        context_menu.exec_(self.image_container_B.mapToGlobal(pos))

    def _sync_viewports(self):
            """A와 B 캔버스의 스크롤 위치 및 이미지 위치를 동기화합니다."""
            if not self.compare_mode_active or not self.original_pixmap_B:
                return

            # 1. 스크롤바 위치 동기화 (스크롤바가 있는 경우)
            v_scroll_A = self.scroll_area.verticalScrollBar()
            h_scroll_A = self.scroll_area.horizontalScrollBar()
            v_scroll_B = self.scroll_area_B.verticalScrollBar()
            h_scroll_B = self.scroll_area_B.horizontalScrollBar()
            
            # A의 스크롤바 값을 B에 그대로 설정
            if v_scroll_A.value() != v_scroll_B.value():
                v_scroll_B.setValue(v_scroll_A.value())
            if h_scroll_A.value() != h_scroll_B.value():
                h_scroll_B.setValue(h_scroll_A.value())
                
            # 2. 이미지 라벨 위치 동기화 (패닝 시)
            pos_A = self.image_label.pos()
            pos_B = self.image_label_B.pos()
            
            if pos_A != pos_B:
                self.image_label_B.move(pos_A)


    def canvas_B_dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("thumbnail_drag:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def canvas_B_dropEvent(self, event):
        mime_text = event.mimeData().text()
        if mime_text.startswith("thumbnail_drag:"):
            try:
                index = int(mime_text.split(":")[1])
                if 0 <= index < len(self.image_files):
                    self.image_B_path = self.image_files[index]
                    self.original_pixmap_B = self.image_loader.load_image_with_orientation(str(self.image_B_path))
                    
                    if self.original_pixmap_B and not self.original_pixmap_B.isNull():
                        self.image_label_B.setText("") # 안내 문구 제거
                        self._apply_zoom_to_canvas('B') # B 캔버스에 줌/뷰포트 적용
                        self.update_compare_filenames()
                    else:
                        self.image_B_path = None
                        self.original_pixmap_B = None
                        self.image_label_B.setText("이미지 로드 실패")
                event.acceptProposedAction()
            except (ValueError, IndexError) as e:
                logging.error(f"B 패널 드롭 오류: {e}")
                event.ignore()
        else:
            event.ignore()

    def _show_first_raw_decode_progress(self):
        """첫 RAW 파일 디코딩 시 진행률 대화상자를 표시합니다."""
        if self.first_raw_load_progress is None:
            line1 = LanguageManager.translate("쾌적한 작업을 위해 RAW 파일을 준비하고 있습니다.")
            line2 = LanguageManager.translate("잠시만 기다려주세요.")
            progress_text = f"<p style='margin-bottom: 10px;'>{line1}</p><p>{line2}</p>"
            progress_title = LanguageManager.translate("파일 준비 중")
            
            self.first_raw_load_progress = QProgressDialog(
                progress_text,
                "", 0, 0, self
            )
            self.first_raw_load_progress.setWindowTitle(progress_title)
            self.first_raw_load_progress.setCancelButton(None)
            self.first_raw_load_progress.setWindowModality(Qt.WindowModal)
            self.first_raw_load_progress.setMinimumDuration(0)
            apply_dark_title_bar(self.first_raw_load_progress)
            
            # [FIX] start_background_loading과 동일한 스타일시트 적용
            self.first_raw_load_progress.setStyleSheet(f"""
                QProgressDialog {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                    color: {ThemeManager.get_color('text')};
                }}
                QProgressDialog > QLabel {{
                    padding-top: 20px;
                    padding-bottom: 30px;
                }}
                QProgressBar {{
                    text-align: center;
                }}
            """)
            
        # 대화상자를 메인 윈도우 중앙에 위치시키는 로직
        parent_geometry = self.geometry()
        self.first_raw_load_progress.adjustSize()
        dialog_size = self.first_raw_load_progress.size()
        new_x = parent_geometry.x() + (parent_geometry.width() - dialog_size.width()) // 2
        new_y = parent_geometry.y() + (parent_geometry.height() - dialog_size.height()) // 2
        self.first_raw_load_progress.move(new_x, new_y)
        self.first_raw_load_progress.show()
        QApplication.processEvents()

    def _close_first_raw_decode_progress(self):
        """진행률 대화상자를 닫습니다."""
        if self.first_raw_load_progress is not None and self.first_raw_load_progress.isVisible():
            self.first_raw_load_progress.close()
            self.first_raw_load_progress = None

    def refresh_folder_contents(self):
        """F5 키를 눌렀을 때 현재 로드된 폴더의 내용을 새로고침합니다."""
        if not self.current_folder and not self.is_raw_only_mode:
            logging.debug("새로고침 건너뛰기: 로드된 폴더가 없습니다.")
            return

        logging.info("폴더 내용 새로고침을 시작합니다...")

        current_index_before_refresh = self.current_image_index
        current_path_before_refresh = self.get_current_image_path()
        
        new_image_files = []

        if self.is_raw_only_mode:
            if self.raw_folder and Path(self.raw_folder).is_dir():
                raw_path = Path(self.raw_folder)
                scanned_files = []
                for ext in self.raw_extensions:
                    scanned_files.extend(raw_path.glob(f'*{ext}'))
                    scanned_files.extend(raw_path.glob(f'*{ext.upper()}'))
                new_image_files = sorted(list(set(scanned_files)), key=self.get_datetime_from_file_fast)
            
            if not new_image_files:
                logging.warning("새로고침 결과: RAW 폴더에 파일이 더 이상 없습니다. 초기화합니다.")
                self.clear_raw_folder()
                return

        else: # JPG 모드
            if self.current_folder and Path(self.current_folder).is_dir():
                jpg_path = Path(self.current_folder)
                scanned_files = []
                for file_path in jpg_path.iterdir():
                    if file_path.is_file() and file_path.suffix.lower() in self.supported_image_extensions:
                        scanned_files.append(file_path)
                new_image_files = sorted(scanned_files, key=self.get_datetime_from_file_fast)

            if not new_image_files:
                logging.warning("새로고침 결과: JPG 폴더에 파일이 더 이상 없습니다. 초기화합니다.")
                self.clear_jpg_folder()
                return
            
            if self.raw_folder and Path(self.raw_folder).is_dir():
                self.match_raw_files(self.raw_folder, silent=True)

        self.image_files = new_image_files
        logging.info(f"새로고침 완료: 총 {len(self.image_files)}개의 파일을 찾았습니다.")

        new_index = -1
        if current_path_before_refresh:
            try:
                new_index = self.image_files.index(Path(current_path_before_refresh))
                logging.info(f"이전 이미지 '{Path(current_path_before_refresh).name}'를 새 목록에서 찾았습니다. 인덱스: {new_index}")
            except ValueError:
                logging.info("이전에 보던 파일이 삭제되었습니다. 인덱스를 조정합니다.")
                new_index = min(current_index_before_refresh, len(self.image_files) - 1)
        
        if new_index < 0 and self.image_files:
            new_index = 0

        self.force_refresh = True
        
        if self.grid_mode == "Off":
            self.current_image_index = new_index
            self.display_current_image()
            self.thumbnail_panel.set_image_files(self.image_files)
            if self.current_image_index >= 0:
                self.thumbnail_panel.set_current_index(self.current_image_index)
        else: # Grid 모드
            rows, cols = self._get_grid_dimensions()
            num_cells = rows * cols
            if new_index != -1:
                self.grid_page_start_index = (new_index // num_cells) * num_cells
                self.current_grid_index = new_index % num_cells
            else:
                self.grid_page_start_index = 0
                self.current_grid_index = 0
            self.update_grid_view()

        self.update_counters()
        logging.info("UI 새로고침이 완료되었습니다.")

    def request_thumbnail_load(self, file_path, index):
        """ThumbnailModel로부터 썸네일 로딩 요청을 받아 처리"""
        if not self.resource_manager or not self.resource_manager._running:
            return

        thumbnail_size = UIScaleManager.get("thumbnail_image_size")

        # --- [핵심 수정] future가 None이 아닌지 확인하는 방어 코드 추가 ---
        future = self.resource_manager.submit_imaging_task_with_priority(
            'low',
            self._generate_thumbnail_task,
            file_path,
            thumbnail_size
        )
        
        if future: # <<< future가 유효할 때만 콜백을 연결합니다.
            future.add_done_callback(
                lambda f, path=file_path: self._on_thumbnail_generated(f, path)
            )
        else:
            logging.warning(f"썸네일 로딩 작업 제출 실패 (future is None): {Path(file_path).name}")

    
    def _on_thumbnail_generated(self, future, file_path):
        """
        [Main Thread] 썸네일 생성이 완료되면 호출되는 콜백.
        """
        try:
            qimage = future.result()
            if qimage and not qimage.isNull():
                pixmap = QPixmap.fromImage(qimage)
                # 생성된 썸네일을 모델에 전달하여 UI 업데이트
                self.thumbnail_panel.model.set_thumbnail(file_path, pixmap)
        except Exception as e:
            logging.error(f"썸네일 결과 처리 중 오류 ({Path(file_path).name}): {e}")

    def on_thumbnail_clicked(self, index):
        """썸네일 클릭 시 해당 이미지로 이동"""
        if 0 <= index < len(self.image_files):
            self.current_image_index = index
            
            # Fit 모드인 경우 기존 캐시 무효화
            if self.zoom_mode == "Fit":
                self.last_fit_size = (0, 0)
                self.fit_pixmap_cache.clear()
            
            # 이미지 표시
            self.display_current_image()
            
            # 썸네일 패널 현재 인덱스 업데이트
            self.thumbnail_panel.set_current_index(index)

    def _generate_thumbnail_task(self, file_path, size):
        """
        [Worker Thread] QImageReader를 사용하여 썸네일용 QImage를 생성합니다.
        스레드에 안전하며, 메인 스레드에서 QPixmap으로 변환됩니다.
        """
        try:
            is_raw = Path(file_path).suffix.lower() in self.raw_extensions
            if is_raw:
                preview_pixmap, _, _ = self.image_loader._load_raw_preview_with_orientation(file_path)
                if preview_pixmap and not preview_pixmap.isNull():
                    return preview_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation).toImage()
                else:
                    logging.warning(f"썸네일 패널용 프리뷰 없음: {file_path}")
                    return QImage()
            reader = QImageReader(str(file_path))
            if not reader.canRead():
                logging.warning(f"썸네일 생성을 위해 파일을 읽을 수 없음: {file_path}")
                if Path(file_path).suffix.lower() in ['.heic', '.heif']:
                    try:
                        from PIL import Image
                        pil_image = Image.open(file_path)
                        pil_image.thumbnail((size, size), Image.Resampling.LANCZOS)
                        if pil_image.mode != 'RGB':
                            pil_image = pil_image.convert('RGB')
                        width, height = pil_image.size
                        rgb_data = pil_image.tobytes('raw', 'RGB')
                        qimage = QImage(rgb_data, width, height, QImage.Format_RGB888)
                        logging.info(f"PIL로 HEIC 썸네일 생성 성공: {file_path}")
                        return qimage
                    except Exception as e:
                        logging.error(f"PIL로 HEIC 썸네일 생성 실패: {e}")
                return None
            reader.setAutoTransform(True)
            original_size = reader.size()
            scaled_size = original_size.scaled(size, size, Qt.KeepAspectRatio)
            reader.setScaledSize(scaled_size)
            qimage = reader.read()
            if qimage.isNull():
                logging.error(f"QImageReader로 썸네일 읽기 실패: {file_path}")
                if Path(file_path).suffix.lower() in ['.heic', '.heif']:
                    try:
                        from PIL import Image
                        pil_image = Image.open(file_path)
                        pil_image.thumbnail((size, size), Image.Resampling.LANCZOS)
                        if pil_image.mode != 'RGB':
                            pil_image = pil_image.convert('RGB')
                        width, height = pil_image.size
                        rgb_data = pil_image.tobytes('raw', 'RGB')
                        qimage = QImage(rgb_data, width, height, QImage.Format_RGB888)
                        logging.info(f"PIL로 HEIC 썸네일 생성 성공 (QImageReader 실패 후): {file_path}")
                        return qimage
                    except Exception as e:
                        logging.error(f"PIL로 HEIC 썸네일 생성 실패 (QImageReader 실패 후): {e}")
                return None
            return qimage
        except Exception as e:
            logging.error(f"썸네일 생성 작업 중 오류 ({Path(file_path).name}): {e}")
            return None


    def on_thumbnail_double_clicked(self, index):
        """썸네일 더블클릭 시 처리 (단일 클릭과 동일하게 처리)"""
        self.on_thumbnail_clicked(index)

    def on_thumbnail_selection_changed(self, selected_indices):
        """썸네일 다중 선택 변경 시 처리"""
        if selected_indices:
            # 첫 번째 선택된 이미지로 이동
            self.on_thumbnail_clicked(selected_indices[0])

    def toggle_thumbnail_panel(self):
        """썸네일 패널 표시/숨김 토글 (Grid Off 모드에서만)"""
        if self.grid_mode == "Off":
            if self.thumbnail_panel.isVisible():
                self.thumbnail_panel.hide()
            else:
                self.thumbnail_panel.show()
                # 썸네일 패널이 표시될 때 현재 이미지 파일 목록 설정
                self.thumbnail_panel.set_image_files(self.image_files)
                if self.current_image_index >= 0:
                    self.thumbnail_panel.set_current_index(self.current_image_index)
            
            # 레이아웃 재조정
            self.adjust_layout()

    def update_thumbnail_panel_visibility(self):
        """Grid 모드에 따른 썸네일 패널 표시 상태 업데이트"""
        thumbnail_should_be_visible = (self.grid_mode == "Off")
        
        # 현재 상태와 목표 상태가 다를 때만 위젯 구성 변경
        if self.thumbnail_panel.isVisible() != thumbnail_should_be_visible:
            if thumbnail_should_be_visible:
                self.thumbnail_panel.show()
                self.thumbnail_panel.set_image_files(self.image_files)
                if self.current_image_index >= 0:
                    self.thumbnail_panel.set_current_index(self.current_image_index)
            else:
                self.thumbnail_panel.hide()
                
            # 위젯 구성 변경이 필요하므로 재구성 함수 호출
            self._reorganize_splitter_widgets(thumbnail_should_be_visible, self.control_panel_on_right)

            self.adjust_layout()
        
    def update_thumbnail_current_index(self):
        """현재 이미지 인덱스가 변경될 때 썸네일 패널 업데이트"""
        if self.thumbnail_panel.isVisible() and self.current_image_index >= 0:
            self.thumbnail_panel.set_current_index(self.current_image_index)


    def set_window_icon(self):
        """크로스 플랫폼 윈도우 아이콘을 설정합니다."""
        try:
            from PySide6.QtGui import QIcon
            
            # 플랫폼별 아이콘 파일 결정
            if sys.platform == "darwin":  # macOS
                icon_filename = "app_icon.icns"
            else:  # Windows, Linux
                icon_filename = "app_icon.ico"
            
            # 아이콘 파일 경로 결정
            if getattr(sys, 'frozen', False):
                # PyInstaller/Nuitka로 패키징된 경우
                icon_path = Path(sys.executable).parent / icon_filename
            else:
                # 일반 스크립트로 실행된 경우
                icon_path = Path(__file__).parent / icon_filename
            
            if icon_path.exists():
                icon = QIcon(str(icon_path))
                self.setWindowIcon(icon)
                
                # 애플리케이션 레벨에서도 아이콘 설정 (macOS Dock용)
                QApplication.instance().setWindowIcon(icon)
                
                logging.info(f"윈도우 아이콘 설정 완료: {icon_path}")
            else:
                logging.warning(f"아이콘 파일을 찾을 수 없습니다: {icon_path}")
                
        except Exception as e:
            logging.error(f"윈도우 아이콘 설정 실패: {e}")

    def _rebuild_folder_selection_ui(self):
            """기존 분류 폴더 UI를 제거하고 새로 생성하여 교체합니다."""
            if hasattr(self, 'category_folder_container') and self.category_folder_container:
                self.category_folder_container.deleteLater()
                self.category_folder_container = None

            self.category_folder_container = self.setup_folder_selection_ui()

            # <<< [수정] 로직 단순화: 구분선(line_before_folders) 바로 아래에 삽입 >>>
            try:
                # 구분선의 인덱스를 찾아서 그 바로 아래(+2, 구분선과 그 아래 spacing)에 삽입
                insertion_index = self.control_layout.indexOf(self.line_before_folders) + 2
                self.control_layout.insertWidget(insertion_index, self.category_folder_container)
            except Exception as e:
                # 예외 발생 시 (예: 구분선을 찾지 못함) 레이아웃의 끝에 추가 (안전 장치)
                logging.error(f"_rebuild_folder_selection_ui에서 삽입 위치 찾기 실패: {e}. 레이아웃 끝에 추가합니다.")
                self.control_layout.addWidget(self.category_folder_container)

            self.update_all_folder_labels_state()

    def on_folder_count_changed(self, index):
        """분류 폴더 개수 콤보박스 변경 시 호출되는 슬롯"""
        if index < 0: return
        
        new_count = self.folder_count_combo.itemData(index)
        if new_count is None or new_count == self.folder_count:
            return

        logging.info(f"분류 폴더 개수 변경: {self.folder_count} -> {new_count}")
        self.folder_count = new_count

        # self.target_folders 리스트 크기 조정
        current_len = len(self.target_folders)
        if new_count > current_len:
            # 늘어난 만큼 빈 문자열 추가
            self.target_folders.extend([""] * (new_count - current_len))
        elif new_count < current_len:
            # 줄어든 만큼 뒤에서부터 잘라냄
            self.target_folders = self.target_folders[:new_count]
            
        # UI 재구축
        self._rebuild_folder_selection_ui()
        
        # 변경된 상태 저장
        self.save_state()

    # === 폴더 경로 레이블 드래그 앤 드랍 관련 코드 시작 === #
    def dragEnterEvent(self, event):
        """드래그 진입 시 호출"""
        try:
            # 폴더만 허용
            if event.mimeData().hasUrls():
                urls = event.mimeData().urls()
                if len(urls) == 1:  # 하나의 항목만 허용
                    file_path = urls[0].toLocalFile()
                    if file_path and Path(file_path).is_dir():
                        event.acceptProposedAction()
                        logging.debug(f"드래그 진입: 폴더 감지됨 - {file_path}")
                        return
            
            # 조건에 맞지 않으면 거부
            event.ignore()
            logging.debug("드래그 진입: 폴더가 아니거나 여러 항목 감지됨")
        except Exception as e:
            logging.error(f"dragEnterEvent 오류: {e}")
            event.ignore()

    def dragMoveEvent(self, event):
        """드래그 이동 시 호출"""
        try:
            if event.mimeData().hasUrls():
                urls = event.mimeData().urls()
                if len(urls) == 1:
                    file_path = urls[0].toLocalFile()
                    if file_path and Path(file_path).is_dir():
                        # 현재 마우스 위치에서 타겟 레이블 찾기
                        pos = event.position().toPoint() if hasattr(event.position(), 'toPoint') else event.pos()
                        target_label, target_type = self._find_target_label_at_position(pos)
                        
                        # 폴더 유효성 검사
                        is_valid = self._validate_folder_for_target(file_path, target_type)
                        
                        # 이전 타겟과 다르면 스타일 복원
                        if self.drag_target_label and self.drag_target_label != target_label:
                            self._restore_original_style(self.drag_target_label)
                            self.drag_target_label = None
                        
                        # 새 타겟에 스타일 적용
                        if target_label and target_label != self.drag_target_label:
                            self._save_original_style(target_label)
                            if is_valid:
                                self._set_drag_accept_style(target_label)
                            else:
                                self._set_drag_reject_style(target_label)
                            self.drag_target_label = target_label
                        
                        event.acceptProposedAction()
                        return
            
            # 조건에 맞지 않으면 스타일 복원 후 거부
            if self.drag_target_label:
                self._restore_original_style(self.drag_target_label)
                self.drag_target_label = None
            event.ignore()
        except Exception as e:
            logging.error(f"dragMoveEvent 오류: {e}")
            event.ignore()

    def dragLeaveEvent(self, event):
        """드래그 벗어날 때 호출"""
        try:
            # 모든 스타일 복원
            if self.drag_target_label:
                self._restore_original_style(self.drag_target_label)
                self.drag_target_label = None
            logging.debug("드래그 벗어남: 스타일 복원됨")
        except Exception as e:
            logging.error(f"dragLeaveEvent 오류: {e}")

    def dropEvent(self, event):
        """드랍 시 호출"""
        try:
            if event.mimeData().hasUrls():
                urls = event.mimeData().urls()
                if len(urls) == 1:
                    file_path = urls[0].toLocalFile()
                    if file_path and Path(file_path).is_dir():
                        # 현재 마우스 위치에서 타겟 레이블 찾기
                        pos = event.position().toPoint() if hasattr(event.position(), 'toPoint') else event.pos()
                        target_label, target_type = self._find_target_label_at_position(pos)
                        
                        # 스타일 복원
                        if self.drag_target_label:
                            self._restore_original_style(self.drag_target_label)
                            self.drag_target_label = None
                        
                        # 타겟에 따른 처리
                        success = self._handle_folder_drop(file_path, target_type)
                        
                        if success:
                            event.acceptProposedAction()
                            logging.info(f"폴더 드랍 성공: {file_path} -> {target_type}")
                        else:
                            event.ignore()
                            logging.warning(f"폴더 드랍 실패: {file_path} -> {target_type}")
                        return
            
            # 조건에 맞지 않으면 거부
            event.ignore()
            logging.debug("dropEvent: 유효하지 않은 드랍")
        except Exception as e:
            logging.error(f"dropEvent 오류: {e}")
            event.ignore()

    def _find_target_label_at_position(self, pos):
        """좌표에서 타겟 레이블과 타입을 찾기"""
        try:
            # 컨트롤 패널 내의 위젯에서 좌표 확인
            widget_at_pos = self.childAt(pos)
            if not widget_at_pos:
                return None, None
            
            # 부모 위젯들을 따라가며 타겟 레이블 찾기
            current_widget = widget_at_pos
            for _ in range(10):  # 최대 10단계까지 부모 탐색
                if current_widget is None:
                    break
                
                # JPG 폴더 레이블 확인
                if hasattr(self, 'folder_path_label') and current_widget == self.folder_path_label:
                    return self.folder_path_label, "image_folder"
                
                # RAW 폴더 레이블 확인
                if hasattr(self, 'raw_folder_path_label') and current_widget == self.raw_folder_path_label:
                    return self.raw_folder_path_label, "raw_folder"
                
                # 분류 폴더 레이블들 확인
                if hasattr(self, 'folder_path_labels'):
                    for i, label in enumerate(self.folder_path_labels):
                        if current_widget == label:
                            return label, f"category_folder_{i}"
                
                # 부모로 이동
                current_widget = current_widget.parent()
            
            return None, None
        except Exception as e:
            logging.error(f"_find_target_label_at_position 오류: {e}")
            return None, None

    def _validate_folder_for_target(self, folder_path, target_type):
        """타겟별 폴더 유효성 검사"""
        try:
            if not folder_path or not target_type:
                return False
            
            folder_path_obj = Path(folder_path)
            if not folder_path_obj.is_dir():
                return False
            
            if target_type == "image_folder":
                # 이미지 폴더: 지원하는 이미지 파일이 있는지 확인
                return self._has_supported_image_files(folder_path_obj)
            
            elif target_type == "raw_folder":
                # RAW 폴더: RAW 파일이 있는지 확인
                return self._has_raw_files(folder_path_obj)
            
            elif target_type.startswith("category_folder_"):
                # 분류 폴더: 모든 디렉토리 허용
                return True
            
            return False
        except Exception as e:
            logging.error(f"_validate_folder_for_target 오류: {e}")
            return False

    def _has_supported_image_files(self, folder_path):
        """폴더에 지원하는 이미지 파일이 있는지 확인"""
        try:
            for file_path in folder_path.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in self.supported_image_extensions:
                    return True
            return False
        except Exception as e:
            logging.debug(f"이미지 파일 확인 오류: {e}")
            return False

    def _has_raw_files(self, folder_path):
        """폴더에 RAW 파일이 있는지 확인"""
        try:
            for file_path in folder_path.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in self.raw_extensions:
                    return True
            return False
        except Exception as e:
            logging.debug(f"RAW 파일 확인 오류: {e}")
            return False

    def _save_original_style(self, widget):
        """원래 스타일 저장"""
        try:
            if widget:
                self.original_label_styles[widget] = widget.styleSheet()
        except Exception as e:
            logging.error(f"_save_original_style 오류: {e}")

    def _set_drag_accept_style(self, widget):
        """드래그 수락 스타일 적용"""
        try:
            if widget:
                widget.setStyleSheet(f"""
                    QLabel {{
                        color: #AAAAAA;
                        padding: 5px;
                        background-color: {ThemeManager.get_color('bg_primary')};
                        border: 2px solid #08E25F;
                        border-radius: 1px;
                    }}
                """)
        except Exception as e:
            logging.error(f"_set_drag_accept_style 오류: {e}")

    def _set_drag_reject_style(self, widget):
        """드래그 거부 스타일 적용"""
        try:
            if widget:
                widget.setStyleSheet(f"""
                    QLabel {{
                        color: #AAAAAA;
                        padding: 5px;
                        background-color: {ThemeManager.get_color('bg_primary')};
                        border: 2px solid #FF4444;
                        border-radius: 1px;
                    }}
                """)
        except Exception as e:
            logging.error(f"_set_drag_reject_style 오류: {e}")

    def _restore_original_style(self, widget):
        """원래 스타일 복원"""
        try:
            if widget and widget in self.original_label_styles:
                original_style = self.original_label_styles[widget]
                widget.setStyleSheet(original_style)
                del self.original_label_styles[widget]
        except Exception as e:
            logging.error(f"_restore_original_style 오류: {e}")

    def _handle_folder_drop(self, folder_path, target_type):
        """타겟별 폴더 드랍 처리"""
        try:
            if not folder_path or not target_type:
                return False
            
            folder_path_obj = Path(folder_path)
            if not folder_path_obj.is_dir():
                return False
            
            if target_type == "image_folder":
                # 이미지 폴더 처리
                return self._handle_image_folder_drop(folder_path)
            
            elif target_type == "raw_folder":
                # RAW 폴더 처리
                return self._handle_raw_folder_drop(folder_path)
            
            elif target_type.startswith("category_folder_"):
                # 분류 폴더 처리
                folder_index = int(target_type.split("_")[-1])
                return self._handle_category_folder_drop(folder_path, folder_index)
            
            return False
        except Exception as e:
            logging.error(f"_handle_folder_drop 오류: {e}")
            return False

    def _handle_image_folder_drop(self, folder_path):
        """이미지 폴더 드랍 처리"""
        try:
            # 기존 load_images_from_folder 함수 재사용
            success = self.load_images_from_folder(folder_path)
            if success:
                # load_jpg_folder와 동일한 UI 업데이트 로직 추가
                self.current_folder = folder_path
                self.folder_path_label.setText(folder_path)
                self.update_jpg_folder_ui_state()  # UI 상태 업데이트
                self.save_state()  # 상태 저장
                
                # 세션 관리 팝업이 열려있으면 업데이트
                if self.session_management_popup and self.session_management_popup.isVisible():
                    self.session_management_popup.update_all_button_states()
                
                logging.info(f"드래그 앤 드랍으로 이미지 폴더 로드 성공: {folder_path}")
                return True
            else:
                # 실패 시에도 load_images_from_folder 내부에서 UI 초기화가 이미 처리됨
                # 추가로 current_folder도 초기화
                self.current_folder = ""
                self.update_jpg_folder_ui_state()
                
                if self.session_management_popup and self.session_management_popup.isVisible():
                    self.session_management_popup.update_all_button_states()
                
                logging.warning(f"드래그 앤 드랍으로 이미지 폴더 로드 실패: {folder_path}")
                return False
        except Exception as e:
            logging.error(f"_handle_image_folder_drop 오류: {e}")
            return False

    def _prepare_raw_only_load(self, folder_path):
        """RAW 단독 로드 전처리: 파일 스캔, 첫 파일 분석, 사용자 선택 요청 (메인 스레드)"""
        if not folder_path:
            return None, None
        
        # [빠른 작업] 파일 목록 스캔
        target_path = Path(folder_path)
        temp_raw_file_list = []
        for ext in self.raw_extensions:
            temp_raw_file_list.extend(target_path.glob(f'*{ext}'))
            temp_raw_file_list.extend(target_path.glob(f'*{ext.upper()}'))
        
        unique_raw_files = list(set(temp_raw_file_list))
        if not unique_raw_files:
            self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("경고"), LanguageManager.translate("선택한 폴더에 RAW 파일이 없습니다."))
            return None, None

        # [빠른 작업] 첫 파일 분석 및 사용자 선택 다이얼로그
        first_raw_file_path_obj = sorted(unique_raw_files)[0]
        is_raw_compatible, model_name, orig_res, prev_res = self._analyze_first_raw_file(str(first_raw_file_path_obj))
        chosen_method, dont_ask = self._get_user_raw_method_choice(is_raw_compatible, model_name, orig_res, prev_res)

        if chosen_method is None:
            return None, None # 사용자가 취소

        # "다시 묻지 않음" 설정 저장
        if model_name != LanguageManager.translate("알 수 없는 카메라"):
            self.set_camera_raw_setting(model_name, chosen_method, dont_ask)
        
        self.image_loader.set_raw_load_strategy(chosen_method)
        
        # RAW 디코딩 모드일 경우 진행률 대화상자 표시
        if chosen_method == "decode":
            self._show_first_raw_decode_progress()
            
        return unique_raw_files, chosen_method

    def _handle_raw_folder_drop(self, folder_path):
        """RAW 폴더 드랍 처리 (비동기 로딩으로 변경)"""
        try:
            if not self.image_files: # RAW 단독 로드
                raw_files_to_load, chosen_method = self._prepare_raw_only_load(folder_path)
                if raw_files_to_load and chosen_method:
                    self.start_background_loading(
                        jpg_folder_path=folder_path,
                        raw_folder_path=None,
                        mode='raw_only',
                        raw_file_list=raw_files_to_load
                    )
                    return True
                return False
            else: # JPG-RAW 매칭
                self.start_background_loading(
                    jpg_folder_path=self.current_folder,
                    raw_folder_path=folder_path,
                    mode='jpg_with_raw',
                    raw_file_list=None
                )
                return True
        except Exception as e:
            logging.error(f"_handle_raw_folder_drop 오류: {e}")
            return False

    def _analyze_first_raw_file(self, first_raw_file_path_str):
        """첫 번째 RAW 파일을 분석하여 호환성, 모델명, 해상도 정보를 반환합니다."""
        logging.info(f"첫 번째 RAW 파일 분석 시작: {Path(first_raw_file_path_str).name}")
        is_raw_compatible = False
        camera_model_name = LanguageManager.translate("알 수 없는 카메라")
        original_resolution_str = "-"
        preview_resolution_str = "-"
        rawpy_exif_data = {}
        exiftool_path = self.get_exiftool_path()
        exiftool_available = Path(exiftool_path).exists() and Path(exiftool_path).is_file()

        try:
            with rawpy.imread(first_raw_file_path_str) as raw:
                is_raw_compatible = True
                original_width = raw.sizes.width
                original_height = raw.sizes.height
                if original_width > 0 and original_height > 0:
                    original_resolution_str = f"{original_width}x{original_height}"
                
                make = raw.camera_manufacturer.strip() if hasattr(raw, 'camera_manufacturer') and raw.camera_manufacturer else ""
                model = raw.model.strip() if hasattr(raw, 'model') and raw.model else ""
                camera_model_name = format_camera_name(make, model)
                rawpy_exif_data["exif_make"] = make
                rawpy_exif_data["exif_model"] = model
        except Exception as e_rawpy:
            is_raw_compatible = False
            logging.warning(f"rawpy로 첫 파일 분석 중 오류: {e_rawpy}")

        if (not camera_model_name or camera_model_name == LanguageManager.translate("알 수 없는 카메라") or original_resolution_str == "-") and exiftool_available:
            try:
                cmd = [exiftool_path, "-json", "-Model", "-ImageWidth", "-ImageHeight", "-Make", first_raw_file_path_str]
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, creationflags=creationflags)
                if process.returncode == 0 and process.stdout:
                    exif_data = json.loads(process.stdout)[0]
                    model = exif_data.get("Model")
                    make = exif_data.get("Make")
                    if not rawpy_exif_data.get("exif_model") and model:
                        rawpy_exif_data["exif_model"] = model.strip()
                    if not rawpy_exif_data.get("exif_make") and make:
                        rawpy_exif_data["exif_make"] = make.strip()
                    if not camera_model_name or camera_model_name == LanguageManager.translate("알 수 없는 카메라"):
                         camera_model_name = format_camera_name(make, model)
                    if original_resolution_str == "-":
                        width = exif_data.get("ImageWidth")
                        height = exif_data.get("ImageHeight")
                        if width and height and int(width) > 0 and int(height) > 0:
                            original_resolution_str = f"{width}x{height}"
            except Exception as e_exiftool:
                logging.error(f"Exiftool로 정보 추출 중 오류: {e_exiftool}")

        final_camera_model_display = camera_model_name if camera_model_name else LanguageManager.translate("알 수 없는 카메라")
        
        preview_pixmap, preview_width, preview_height = self.image_loader._load_raw_preview_with_orientation(first_raw_file_path_str)
        if preview_pixmap and not preview_pixmap.isNull() and preview_width and preview_height:
            preview_resolution_str = f"{preview_width}x{preview_height}"
        else:
            preview_resolution_str = LanguageManager.translate("정보 없음")

        return is_raw_compatible, final_camera_model_display, original_resolution_str, preview_resolution_str

    def _get_user_raw_method_choice(self, is_compatible, model_name, orig_res, prev_res):
        """저장된 설정을 확인하거나 사용자에게 RAW 처리 방식을 묻는 다이얼로그를 표시합니다."""
        chosen_method = None
        dont_ask = False
        if model_name != LanguageManager.translate("알 수 없는 카메라"):
            saved_setting = self.get_camera_raw_setting(model_name)
            if saved_setting and saved_setting.get("dont_ask"):
                chosen_method = saved_setting.get("method")
                dont_ask = True
                logging.info(f"'{model_name}' 모델에 저장된 '다시 묻지 않음' 설정 사용: {chosen_method}")
                return chosen_method, dont_ask
        
        # 저장된 설정이 없거나 '다시 묻지 않음'이 아닌 경우
        result = self._show_raw_processing_choice_dialog(is_compatible, model_name, orig_res, prev_res)
        if result:
            chosen_method, dont_ask = result
        
        return chosen_method, dont_ask

    def _handle_category_folder_drop(self, folder_path, folder_index):
        """분류 폴더 드랍 처리"""
        try:
            if 0 <= folder_index < len(self.target_folders):
                self.target_folders[folder_index] = folder_path
                # <<< 수정 시작 >>>
                # setText 대신 set_state를 사용하여 UI와 상태를 한 번에 업데이트합니다.
                self.folder_path_labels[folder_index].set_state(EditableFolderPathLabel.STATE_SET, folder_path)
                # <<< 수정 끝 >>>
                self.save_state()
                logging.info(f"드래그 앤 드랍으로 분류 폴더 {folder_index+1} 설정 완료: {folder_path}")
                return True
            else:
                logging.error(f"잘못된 분류 폴더 인덱스: {folder_index}")
                return False
        except Exception as e:
            logging.error(f"_handle_category_folder_drop 오류: {e}")
            return False
    # === 폴더 경로 레이블 드래그 앤 드랍 관련 코드 끝 === #

    # === 캔버스 영역 드래그 앤 드랍 관련 코드 시작 === #
    def canvas_dragEnterEvent(self, event):
        """캔버스 영역 드래그 진입 시 호출"""
        try:
            # 폴더만 허용
            if event.mimeData().hasUrls():
                urls = event.mimeData().urls()
                if len(urls) == 1:  # 하나의 항목만 허용
                    file_path = urls[0].toLocalFile()
                    if file_path and Path(file_path).is_dir():
                        event.acceptProposedAction()
                        logging.debug(f"캔버스 드래그 진입: 폴더 감지됨 - {file_path}")
                        return
            
            # 조건에 맞지 않으면 거부
            event.ignore()
            logging.debug("캔버스 드래그 진입: 폴더가 아니거나 여러 항목 감지됨")
        except Exception as e:
            logging.error(f"canvas_dragEnterEvent 오류: {e}")
            event.ignore()

    def canvas_dragMoveEvent(self, event):
        """캔버스 영역 드래그 이동 시 호출"""
        try:
            if event.mimeData().hasUrls():
                urls = event.mimeData().urls()
                if len(urls) == 1:
                    file_path = urls[0].toLocalFile()
                    if file_path and Path(file_path).is_dir():
                        event.acceptProposedAction()
                        return
            
            event.ignore()
        except Exception as e:
            logging.error(f"canvas_dragMoveEvent 오류: {e}")
            event.ignore()

    def canvas_dragLeaveEvent(self, event):
        """캔버스 영역 드래그 벗어날 때 호출"""
        try:
            logging.debug("캔버스 드래그 벗어남")
        except Exception as e:
            logging.error(f"canvas_dragLeaveEvent 오류: {e}")

    def canvas_dropEvent(self, event):
        """캔버스 영역 드랍 시 호출"""
        try:
            if event.mimeData().hasUrls():
                urls = event.mimeData().urls()
                if len(urls) == 1:
                    file_path = urls[0].toLocalFile()
                    if file_path and Path(file_path).is_dir():
                        # 캔버스 폴더 드랍 처리
                        success = self._handle_canvas_folder_drop(file_path)
                        
                        if success:
                            event.acceptProposedAction()
                            logging.info(f"캔버스 폴더 드랍 성공: {file_path}")
                        else:
                            event.ignore()
                            logging.warning(f"캔버스 폴더 드랍 실패: {file_path}")
                        return
            
            # 조건에 맞지 않으면 거부
            event.ignore()
            logging.debug("canvas_dropEvent: 유효하지 않은 드랍")
        except Exception as e:
            logging.error(f"canvas_dropEvent 오류: {e}")
            event.ignore()

    def _analyze_folder_contents(self, folder_path):
        """폴더 내용 분석 (RAW 파일, 일반 이미지 파일, 매칭 여부)"""
        try:
            folder_path_obj = Path(folder_path)
            if not folder_path_obj.is_dir():
                return None
            
            # 파일 분류
            raw_files = []
            image_files = []
            
            for file_path in folder_path_obj.iterdir():
                if not file_path.is_file():
                    continue
                
                ext = file_path.suffix.lower()
                if ext in self.raw_extensions:
                    raw_files.append(file_path)
                elif ext in self.supported_image_extensions:
                    image_files.append(file_path)
            
            # 매칭 파일 확인 (이름이 같은 파일)
            raw_stems = {f.stem for f in raw_files}
            image_stems = {f.stem for f in image_files}
            matching_files = raw_stems & image_stems
            
            return {
                'raw_files': raw_files,
                'image_files': image_files,
                'has_raw': len(raw_files) > 0,
                'has_images': len(image_files) > 0,
                'has_matching': len(matching_files) > 0,
                'matching_count': len(matching_files)
            }
        except Exception as e:
            logging.error(f"_analyze_folder_contents 오류: {e}")
            return None

    def _show_folder_choice_dialog(self, has_matching=False):
        """폴더 선택지 팝업 대화상자 (반환 ID 통일)"""
        try:
            dialog = QDialog(self)
            dialog.setWindowTitle(LanguageManager.translate("폴더 불러오기"))
            # 다크 테마 적용
            apply_dark_title_bar(dialog)
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(ThemeManager.get_color('bg_primary')))
            dialog.setPalette(palette)
            dialog.setAutoFillBackground(True)
            layout = QVBoxLayout(dialog)
            layout.setSpacing(10)
            layout.setContentsMargins(20, 20, 20, 20)
            
            # 메시지 레이블 생성
            message_text = LanguageManager.translate("폴더 내에 일반 이미지 파일과 RAW 파일이 같이 있습니다.\n무엇을 불러오시겠습니까?")
            message_label = QLabel(message_text)
            message_label.setWordWrap(True)
            message_label.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
            layout.addWidget(message_label)

            fm = message_label.fontMetrics()
            lines = message_text.split('\n')
            max_width = 0
            for line in lines:
                line_width = fm.horizontalAdvance(line)
                if line_width > max_width:
                    max_width = line_width
            dialog.setMinimumWidth(max_width + 60)

            # 라디오 버튼 그룹 및 스타일
            radio_group = QButtonGroup(dialog)
            radio_style = f"""
                QRadioButton {{
                    color: {ThemeManager.get_color('text')};
                    padding: 0px;
                }}
                QRadioButton::indicator {{
                    width: {UIScaleManager.get("radiobutton_size")}px;
                    height: {UIScaleManager.get("radiobutton_size")}px;
                }}
                QRadioButton::indicator:checked {{
                    background-color: {ThemeManager.get_color('accent')};
                    border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('accent')};
                    border-radius: {UIScaleManager.get("radiobutton_border_radius")}px;
                }}
                QRadioButton::indicator:unchecked {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('border')};
                    border-radius: {UIScaleManager.get("radiobutton_border_radius")}px;
                }}
                QRadioButton::indicator:unchecked:hover {{
                    border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('text_disabled')};
                }}
            """
            
            layout.addSpacing(20)

            if has_matching:
                # 3선택지: 매칭(0), 일반 이미지(1), RAW(2)
                option1 = QRadioButton(LanguageManager.translate("파일명이 같은 이미지 파일과 RAW 파일을 매칭하여 불러오기"))
                option2 = QRadioButton(LanguageManager.translate("일반 이미지 파일만 불러오기"))
                option3 = QRadioButton(LanguageManager.translate("RAW 파일만 불러오기"))
                option1.setStyleSheet(radio_style)
                option2.setStyleSheet(radio_style)
                option3.setStyleSheet(radio_style)
                radio_group.addButton(option1, 0) # ID 0: 매칭
                radio_group.addButton(option2, 1) # ID 1: 일반
                radio_group.addButton(option3, 2) # ID 2: RAW
                option1.setChecked(True)
                layout.addWidget(option1)
                layout.addSpacing(10)
                layout.addWidget(option2)
                layout.addSpacing(10)
                layout.addWidget(option3)
            else:
                # 2선택지: 일반 이미지(1), RAW(2) -> ID를 3선택지와 맞춤
                option1 = QRadioButton(LanguageManager.translate("일반 이미지 파일만 불러오기"))
                option2 = QRadioButton(LanguageManager.translate("RAW 파일만 불러오기"))
                option1.setStyleSheet(radio_style)
                option2.setStyleSheet(radio_style)
                radio_group.addButton(option1, 1) # ID 1: 일반
                radio_group.addButton(option2, 2) # ID 2: RAW
                option1.setChecked(True)
                layout.addWidget(option1)
                layout.addSpacing(10)
                layout.addWidget(option2)

            layout.addSpacing(20)

            # 확인 버튼
            confirm_button = QPushButton(LanguageManager.translate("확인"))
            confirm_button.setStyleSheet(f"""
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
            confirm_button.clicked.connect(dialog.accept)
            
            # 버튼 컨테이너 (가운데 정렬)
            button_container = QWidget()
            button_layout = QHBoxLayout(button_container)
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_layout.addStretch(1)
            button_layout.addWidget(confirm_button)
            button_layout.addStretch(1)
            layout.addWidget(button_container)

            if dialog.exec() == QDialog.Accepted:
                return radio_group.checkedId()
            else:
                return None
        except Exception as e:
            logging.error(f"_show_folder_choice_dialog 오류: {e}")
            return None

    def _handle_canvas_folder_drop(self, folder_path):
        """캔버스 영역 폴더 드랍 메인 처리 로직 (비동기 로딩 적용)"""
        try:
            if self.image_files:
                reply = self.show_themed_message_box(
                    QMessageBox.Question,
                    LanguageManager.translate("새 폴더 불러오기"),
                    LanguageManager.translate("현재 진행 중인 작업을 종료하고 새로운 폴더를 불러오시겠습니까?"),
                    QMessageBox.Yes | QMessageBox.Cancel,
                    QMessageBox.Cancel
                )
                if reply == QMessageBox.Cancel:
                    return False
                self._reset_workspace()
                # 초기화 후, 함수를 처음부터 다시 실행하는 것처럼 동작해야 함
                # 재귀 호출 대신 바로 이어서 로직을 실행
            
            analysis = self._analyze_folder_contents(folder_path)
            if not analysis:
                return False

            # 로딩 모드 결정 및 비동기 로딩 호출
            if analysis['has_raw'] and not analysis['has_images']:
                return self._handle_raw_folder_drop(folder_path)
            
            elif analysis['has_images'] and not analysis['has_raw']:
                self.start_background_loading(folder_path, None, mode='jpg_only', raw_file_list=None)
                return True

            elif analysis['has_raw'] and analysis['has_images']:
                choice_id = self._show_folder_choice_dialog(has_matching=analysis['has_matching'])
                if choice_id is None: return False

                if choice_id == 0: # 매칭
                    self.start_background_loading(folder_path, folder_path, mode='jpg_with_raw', raw_file_list=None)
                elif choice_id == 1: # JPG만
                    self.start_background_loading(folder_path, None, mode='jpg_only', raw_file_list=None)
                elif choice_id == 2: # RAW만
                    return self._handle_raw_folder_drop(folder_path)
                return True
            
            else:
                self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("경고"), LanguageManager.translate("선택한 폴더에 지원하는 파일이 없습니다."))
                return False

        except Exception as e:
            logging.error(f"_handle_canvas_folder_drop 오류: {e}")
            # 에러 로그에 스택 트레이스를 추가하여 더 자세한 정보 확인
            import traceback
            traceback.print_exc()
            return False
    # === 캔버스 영역 드래그 앤 드랍 관련 코드 끝 === #

    def on_extension_checkbox_changed(self, state):
        # QTimer.singleShot을 사용하여 이 함수의 실행을 이벤트 루프의 다음 사이클로 지연시킵니다.
        # 이렇게 하면 모든 체크박스의 상태 업데이트가 완료된 후에 로직이 실행되어 안정성이 높아집니다.
        QTimer.singleShot(0, self._update_supported_extensions)

    def _update_supported_extensions(self):
        """실제로 지원 확장자 목록을 업데이트하고 UI를 검증하는 내부 메서드"""
        extension_groups = {
            "JPG": ['.jpg', '.jpeg'],
            "HEIC": ['.heic', '.heif'],
            "PNG": ['.png'],
            "WebP": ['.webp'],
            "BMP": ['.bmp'],
            "TIFF": ['.tif', '.tiff']
        }

        # 1. 현재 UI에 표시된 모든 체크박스의 상태를 다시 확인
        new_supported_extensions = set()
        checked_count = 0
        for name, checkbox in self.ext_checkboxes.items():
            if checkbox.isChecked():
                checked_count += 1
                new_supported_extensions.update(extension_groups[name])

        # 2. 체크된 박스가 하나도 없는지 검증
        if checked_count == 0:
            logging.warning("모든 확장자 선택 해제 감지됨. JPG를 강제로 다시 선택합니다.")
            jpg_checkbox = self.ext_checkboxes.get("JPG")
            if jpg_checkbox:
                # 이 시점에서는 이미 모든 체크가 해제된 상태이므로,
                # 시그널을 막을 필요 없이 그냥 켜기만 하면 됩니다.
                jpg_checkbox.setChecked(True)
            
            # JPG가 다시 켜졌으므로, 지원 확장자 목록을 JPG만 포함하도록 재설정
            self.supported_image_extensions = set(extension_groups["JPG"])
        else:
            # 체크된 박스가 하나 이상 있으면, 그 상태를 그대로 데이터에 반영
            self.supported_image_extensions = new_supported_extensions

        logging.info(f"지원 확장자 변경됨: {sorted(list(self.supported_image_extensions))}")

    
    def _trigger_state_save_for_index(self): # 자동저장
        """current_image_index를 포함한 전체 상태를 저장합니다 (주로 타이머에 의해 호출)."""
        logging.debug(f"Index save timer triggered. Saving state (current_image_index: {self.current_image_index}).")
        self.save_state()


    def _save_orientation_viewport_focus(self, orientation_type: str, rel_center: QPointF, zoom_level_str: str):
        """주어진 화면 방향 타입('landscape' 또는 'portrait')에 대한 뷰포트 중심과 줌 레벨을 저장합니다."""
        if orientation_type not in ["landscape", "portrait"]:
            logging.warning(f"잘못된 orientation_type으로 포커스 저장 시도: {orientation_type}")
            return

        focus_point_info = {
            "rel_center": rel_center,
            "zoom_level": zoom_level_str
        }
        self.viewport_focus_by_orientation[orientation_type] = focus_point_info
        logging.debug(f"방향별 뷰포트 포커스 저장: {orientation_type} -> {focus_point_info}")

    def _get_current_view_relative_center(self):
        """현재 image_label의 뷰포트 중심의 상대 좌표를 반환합니다."""
        if not self.original_pixmap or self.zoom_mode == "Fit": # Fit 모드에서는 항상 (0.5,0.5)로 간주 가능
            return QPointF(0.5, 0.5)

        view_rect = self.scroll_area.viewport().rect()
        image_label_pos = self.image_label.pos()
        
        # <<<--- 줌 배율 계산 로직 수정 ---<<<
        if self.zoom_mode == "100%":
            current_zoom_factor = 1.0
        elif self.zoom_mode == "Spin":
            current_zoom_factor = self.zoom_spin_value
        else: # 예외 상황 (이론상 발생 안 함)
            current_zoom_factor = 1.0
        
        zoomed_img_width = self.original_pixmap.width() * current_zoom_factor
        zoomed_img_height = self.original_pixmap.height() * current_zoom_factor

        if zoomed_img_width <= 0 or zoomed_img_height <= 0: return QPointF(0.5, 0.5)

        viewport_center_x_abs = view_rect.center().x() - image_label_pos.x()
        viewport_center_y_abs = view_rect.center().y() - image_label_pos.y()
        
        rel_x = max(0.0, min(1.0, viewport_center_x_abs / zoomed_img_width))
        rel_y = max(0.0, min(1.0, viewport_center_y_abs / zoomed_img_height))
        return QPointF(rel_x, rel_y)

    def _get_orientation_viewport_focus(self, orientation_type: str, requested_zoom_level: str):
        """
        주어진 화면 방향 타입에 저장된 포커스 정보를 반환합니다.
        저장된 상대 중심과 "요청된" 줌 레벨을 함께 반환합니다.
        정보가 없으면 기본값(중앙, 요청된 줌 레벨)을 반환합니다.
        """
        if orientation_type in self.viewport_focus_by_orientation:
            saved_focus = self.viewport_focus_by_orientation[orientation_type]
            saved_zoom_level = saved_focus.get("zoom_level", "")
            saved_rel_center = saved_focus.get("rel_center", QPointF(0.5, 0.5))
            
            # 200% → Spin 호환성 처리
            if saved_zoom_level == "200%" and requested_zoom_level == "Spin":
                # 기존 200% 데이터를 Spin으로 사용 (2.0 = 200%)
                if not hasattr(self, 'zoom_spin_value') or self.zoom_spin_value != 2.0:
                    self.zoom_spin_value = 2.0
                    if hasattr(self, 'zoom_spin'):
                        self.zoom_spin.setValue(200)
                logging.debug(f"200% → Spin 호환성 처리: zoom_spin_value를 2.0으로 설정")
            
            logging.debug(f"_get_orientation_viewport_focus: 방향 '{orientation_type}'에 저장된 포커스 사용: rel_center={saved_rel_center} (원래 줌: {saved_zoom_level}), 요청 줌: {requested_zoom_level}")
            return saved_rel_center, requested_zoom_level
        
        logging.debug(f"_get_orientation_viewport_focus: 방향 '{orientation_type}'에 저장된 포커스 없음. 중앙 및 요청 줌({requested_zoom_level}) 사용.")
        return QPointF(0.5, 0.5), requested_zoom_level


    def _prepare_for_photo_change(self):
        """사진 변경 직전에 현재 활성 뷰포트와 이전 이미지 상태를 기록합니다."""
        # 현재 활성 뷰포트 정보를 "방향 타입" 고유 포커스로 저장
        if self.grid_mode == "Off" and self.current_active_zoom_level in ["100%", "Spin"] and \
           self.original_pixmap and hasattr(self, 'current_image_orientation') and self.current_image_orientation:
            self._save_orientation_viewport_focus(
                self.current_image_orientation, # 현재 이미지의 방향 타입
                self.current_active_rel_center, 
                self.current_active_zoom_level
            )
        
        # 다음 이미지 로드 시 비교를 위한 정보 저장
        self.previous_image_orientation_for_carry_over = self.current_image_orientation
        self.previous_zoom_mode_for_carry_over = self.current_active_zoom_level # 현재 "활성" 줌 레벨
        self.previous_active_rel_center_for_carry_over = self.current_active_rel_center # 현재 "활성" 중심



    def _generate_default_session_name(self):
        """현재 상태를 기반으로 기본 세션 이름을 생성합니다."""
        base_folder_name = "Untitled"
        if self.is_raw_only_mode and self.raw_folder:
            base_folder_name = Path(self.raw_folder).name
        elif self.current_folder:
            base_folder_name = Path(self.current_folder).name
        
        # 날짜 부분 (YYYYMMDD)
        date_str = datetime.now().strftime("%Y%m%d")
        # 시간 부분 (HHMMSS) - 이름 중복 시 사용
        time_str = datetime.now().strftime("%H%M%S")

        # 기본 이름: 폴더명_날짜
        default_name = f"{base_folder_name}_{date_str}"
        
        # 중복 확인 및 처리 (이름 뒤에 _HHMMSS 또는 (숫자) 추가)
        final_name = default_name
        counter = 1
        while final_name in self.saved_sessions:
            # 방법 1: 시간 추가 (더 고유함)
            # final_name = f"{default_name}_{time_str}" # 이렇게 하면 거의 항상 고유
            # if final_name in self.saved_sessions: # 시간까지 겹치면 숫자
            #     final_name = f"{default_name}_{time_str}({counter})"
            #     counter += 1
            # 방법 2: 숫자 추가 (요구사항에 더 가까움)
            final_name = f"{default_name}({counter})"
            counter += 1
            if counter > 99: # 무한 루프 방지 (극단적인 경우)
                final_name = f"{default_name}_{time_str}" # 최후의 수단으로 시간 사용
                break 
        return final_name

    def _capture_current_session_state(self):
        """현재 작업 상태를 딕셔너리로 캡처하여 반환합니다."""
        # save_state에서 저장하는 항목들 중 필요한 것들만 선택
        actual_current_image_list_index = -1
        if self.grid_mode != "Off":
            if self.image_files and 0 <= self.grid_page_start_index + self.current_grid_index < len(self.image_files):
                actual_current_image_list_index = self.grid_page_start_index + self.current_grid_index
        else:
            if self.image_files and 0 <= self.current_image_index < len(self.image_files):
                actual_current_image_list_index = self.current_image_index

        session_data = {
            "current_folder": str(self.current_folder) if self.current_folder else "",
            "raw_folder": str(self.raw_folder) if self.raw_folder else "",
            "raw_files": {k: str(v) for k, v in self.raw_files.items()}, # Path를 str로
            "move_raw_files": self.move_raw_files,
            "target_folders": [str(f) if f else "" for f in self.target_folders],
            "folder_count": self.folder_count,  # 분류 폴더 개수 저장 추가
            "minimap_visible": self.minimap_toggle.isChecked(), # 현재 UI 상태 반영
            "current_image_index": actual_current_image_list_index, # 전역 인덱스
            "current_grid_index": self.current_grid_index,
            "grid_page_start_index": self.grid_page_start_index,
            "is_raw_only_mode": self.is_raw_only_mode,
            "show_grid_filenames": self.show_grid_filenames,
            "last_used_raw_method": self.image_loader._raw_load_strategy if hasattr(self, 'image_loader') else "preview",
            "zoom_mode": self.zoom_mode,
            "grid_mode": self.grid_mode,
            "previous_grid_mode": self.previous_grid_mode,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return session_data

    def save_current_session(self, session_name: str):
        """주어진 이름으로 현재 작업 세션을 저장합니다."""
        if not session_name:
            logging.warning("세션 이름 없이 저장을 시도했습니다.")
            # 사용자에게 알림 (선택 사항)
            self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("저장 오류"), LanguageManager.translate("세션 이름을 입력해야 합니다."))
            return False

        if len(self.saved_sessions) >= 20:
            logging.warning("최대 저장 가능한 세션 개수(20개)에 도달했습니다.")
            self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("저장 한도 초과"), LanguageManager.translate("최대 20개의 세션만 저장할 수 있습니다. 기존 세션을 삭제 후 다시 시도해주세요."))
            return False

        current_state_data = self._capture_current_session_state()
        self.saved_sessions[session_name] = current_state_data
        self.save_state() # 변경된 self.saved_sessions를 photosort_data.json에 저장
        logging.info(f"세션 저장됨: {session_name}")
        
        # 세션 관리 팝업이 열려있다면 목록 업데이트
        if self.session_management_popup and self.session_management_popup.isVisible():
            self.session_management_popup.populate_session_list()
        return True


    def load_session(self, session_name: str):
        """저장된 작업 세션을 불러옵니다."""
        if session_name not in self.saved_sessions:
            logging.error(f"세션 '{session_name}'을(를) 찾을 수 없습니다.")
            self.show_themed_message_box(QMessageBox.Critical, LanguageManager.translate("불러오기 오류"), LanguageManager.translate("선택한 세션을 찾을 수 없습니다."))
            return False

        logging.info(f"세션 불러오기 시작: {session_name}")
        session_data = self.saved_sessions[session_name]

        # --- 현재 작업 상태를 덮어쓰기 전에 사용자에게 확인 (선택 사항) ---
        # reply = self.show_themed_message_box(QMessageBox.Question, ...)
        # if reply == QMessageBox.No: return False
        # --- 확인 끝 ---

        # 불러올 상태 값들을 현재 PhotoSortApp 인스턴스에 적용
        # (load_state와 유사한 로직이지만, 파일에서 읽는 대신 session_data 딕셔너리에서 가져옴)

        # 0. 모든 백그라운드 작업 중지 및 캐시 클리어 (새로운 환경 로드 준비)
        self.resource_manager.cancel_all_tasks() # 중요
        if hasattr(self, 'image_loader'): self.image_loader.clear_cache()
        self.fit_pixmap_cache.clear()
        if hasattr(self, 'grid_thumbnail_cache'):
            for key in self.grid_thumbnail_cache:
                self.grid_thumbnail_cache[key].clear()
        self.original_pixmap = None

        # 1. 분류 폴더 개수 설정 먼저 복원 (UI 재구성 전에)
        loaded_folder_count = session_data.get("folder_count", 3)
        if loaded_folder_count != self.folder_count:
            logging.info(f"세션 불러오기: 분류 폴더 개수 변경 {self.folder_count} -> {loaded_folder_count}")
            self.folder_count = loaded_folder_count
            
            # 설정창의 콤보박스 동기화
            if hasattr(self, 'folder_count_combo'):
                current_count_idx = self.folder_count_combo.findData(self.folder_count)
                if current_count_idx >= 0:
                    self.folder_count_combo.setCurrentIndex(current_count_idx)
                    logging.info(f"세션 불러오기: 설정창 폴더 개수 콤보박스 동기화 완료")

        # 2. 폴더 및 파일 관련 상태 복원
        self.current_folder = session_data.get("current_folder", "")
        self.raw_folder = session_data.get("raw_folder", "")
        raw_files_str_dict = session_data.get("raw_files", {})
        self.raw_files = {k: Path(v) for k, v in raw_files_str_dict.items() if v} # Path 객체로
        self.move_raw_files = session_data.get("move_raw_files", True)
        
        # target_folders 복원 (folder_count 기반으로 크기 조정)
        loaded_folders = session_data.get("target_folders", [])
        self.target_folders = (loaded_folders + [""] * self.folder_count)[:self.folder_count]
        
        self.is_raw_only_mode = session_data.get("is_raw_only_mode", False)

        # 3. 분류 폴더 UI 재구성 (folder_count 변경 시 필요)
        self._rebuild_folder_selection_ui()

        # 4. 폴더 경로 UI 라벨 업데이트
        if self.current_folder and Path(self.current_folder).is_dir():
            self.folder_path_label.setText(self.current_folder)
        else:
            self.current_folder = ""
            self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))

        if self.raw_folder and Path(self.raw_folder).is_dir():
            self.raw_folder_path_label.setText(self.raw_folder)
        else:
            self.raw_folder = ""
            self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))

        # 분류 폴더 경로 라벨 업데이트
        for i in range(self.folder_count):
            if i < len(self.target_folders) and self.target_folders[i] and Path(self.target_folders[i]).is_dir():
                folder_path = self.target_folders[i]
                # <<< 수정 시작 >>>
                # 복잡한 setText 호출 대신 set_state를 사용합니다.
                self.folder_path_labels[i].set_state(EditableFolderPathLabel.STATE_SET, folder_path)
                # <<< 수정 끝 >>>
            else:
                # 경로가 없거나 유효하지 않으면 상태에 따라 editable 또는 disabled로 설정
                if self.image_files:
                    self.folder_path_labels[i].set_state(EditableFolderPathLabel.STATE_EDITABLE)
                else:
                    self.folder_path_labels[i].set_state(EditableFolderPathLabel.STATE_DISABLED)

        # 5. UI 관련 상태 복원
        self.minimap_toggle.setChecked(session_data.get("minimap_visible", True))
        self.show_grid_filenames = session_data.get("show_grid_filenames", False)
        if hasattr(self, 'filename_toggle_grid'): self.filename_toggle_grid.setChecked(self.show_grid_filenames)

        self.zoom_mode = session_data.get("zoom_mode", "Fit")
        if self.zoom_mode == "Fit": self.fit_radio.setChecked(True)
        elif self.zoom_mode == "100%": self.zoom_100_radio.setChecked(True)
        elif self.zoom_mode == "Spin": self.zoom_spin_btn.setChecked(True)

        # 6. 이미지 목록 로드 (저장된 폴더 경로 기반)
        images_loaded_successfully = False
        self.image_files = []
        
        if self.is_raw_only_mode:
            if self.raw_folder and Path(self.raw_folder).is_dir():
                images_loaded_successfully = self.reload_raw_files_from_state(self.raw_folder)
        elif self.current_folder and Path(self.current_folder).is_dir():
            images_loaded_successfully = self.load_images_from_folder(self.current_folder)
            # JPG 로드 성공 시 연결된 RAW 폴더 정보가 있다면 그것도 UI에 반영 (raw_files는 이미 위에서 복원됨)
            if images_loaded_successfully and self.raw_folder and Path(self.raw_folder).is_dir():
                self.raw_folder_path_label.setText(self.raw_folder) # 경로 표시
            else: # 연결된 RAW 폴더 정보가 없거나 유효하지 않으면
                if not self.is_raw_only_mode: # RAW Only 모드가 아닐 때만 초기화
                    self.raw_folder = "" 
                    # self.raw_files = {} # 위에서 session_data로부터 이미 설정됨
                    self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        
        # 7. 로드 후 폴더 UI 상태 업데이트
        self.update_jpg_folder_ui_state()
        self.update_raw_folder_ui_state()
        self.update_all_folder_labels_state()
        self.update_match_raw_button_state()

        # 8. ImageLoader 전략 설정
        last_method = session_data.get("last_used_raw_method", "preview")
        if hasattr(self, 'image_loader'):
            self.image_loader.set_raw_load_strategy(last_method)
        logging.info(f"세션 불러오기: ImageLoader 처리 방식 설정됨: {last_method}")

        # 9. 뷰 상태 복원 (인덱스, 그리드 모드 등)
        if images_loaded_successfully and self.image_files:
            total_images = len(self.image_files)
            self.grid_mode = session_data.get("grid_mode", "Off")
            self.previous_grid_mode = session_data.get("previous_grid_mode", None)

            if self.grid_mode == "Off": self.grid_off_radio.setChecked(True)
            elif self.grid_mode == "2x2": self.grid_2x2_radio.setChecked(True)
            elif self.grid_mode == "3x3": self.grid_3x3_radio.setChecked(True)
            self.update_zoom_radio_buttons_state()

            loaded_actual_idx = session_data.get("current_image_index", -1)
            
            if 0 <= loaded_actual_idx < total_images:
                if self.grid_mode != "Off":
                    rows, cols = self._get_grid_dimensions()
                    num_cells = rows * cols
                    self.grid_page_start_index = (loaded_actual_idx // num_cells) * num_cells
                    self.current_grid_index = loaded_actual_idx % num_cells
                    self.update_grid_view()
                else: # Grid Off
                    self.current_image_index = loaded_actual_idx
                    self.display_current_image()
            elif total_images > 0 : # 유효 인덱스 없지만 이미지 있으면 첫번째로
                self.current_image_index = 0; self.current_grid_index = 0; self.grid_page_start_index = 0;
                if self.grid_mode != "Off": self.update_grid_view()
                else: self.display_current_image()
            else: # 이미지 없음
                self.current_image_index = -1; self.current_grid_index = 0; self.grid_page_start_index = 0;
                if self.grid_mode != "Off": self.update_grid_view()
                else: self.display_current_image()
        else: # 이미지 로드 실패
            self.image_files = []
            self.current_image_index = -1
            self.grid_mode = "Off"; self.grid_off_radio.setChecked(True)
            self.update_zoom_radio_buttons_state()
            self.update_grid_view() # 빈 화면
            self.update_file_info_display(None)

        self.update_counter_layout()
        self.toggle_minimap(self.minimap_toggle.isChecked())
        if self.grid_mode == "Off" and images_loaded_successfully:
            self.start_background_thumbnail_preloading()
        
        # 세션 관리 팝업이 열려있다면 닫기
        if self.session_management_popup and self.session_management_popup.isVisible():
            self.session_management_popup.accept()

        logging.info(f"세션 '{session_name}' 불러오기 완료.")
        self.show_themed_message_box(QMessageBox.Information, LanguageManager.translate("불러오기 완료"), LanguageManager.translate("'{session_name}' 세션을 불러왔습니다.").format(session_name=session_name))
        
        if self.session_management_popup and self.session_management_popup.isVisible():
            self.session_management_popup.update_all_button_states()
            
        return True


    def delete_session(self, session_name: str):
        """저장된 작업 세션을 삭제합니다."""
        if session_name in self.saved_sessions:
            del self.saved_sessions[session_name]
            self.save_state() # 변경 사항을 photosort_data.json에 저장
            logging.info(f"세션 삭제됨: {session_name}")
            # 세션 관리 팝업이 열려있다면 목록 업데이트
            if self.session_management_popup and self.session_management_popup.isVisible():
                self.session_management_popup.populate_session_list()
            return True
        else:
            logging.warning(f"삭제할 세션 없음: {session_name}")
            return False

    def show_session_management_popup(self):
        """세션 저장 및 불러오기 팝업창을 표시합니다."""
        # 현재 활성화된 settings_popup을 부모로 사용하거나, 없으면 self (메인 윈도우)를 부모로 사용
        current_active_popup = QApplication.activeModalWidget() # 현재 활성화된 모달 위젯 찾기
        parent_widget = self # 기본 부모는 메인 윈도우

        if current_active_popup and isinstance(current_active_popup, QDialog):
             # settings_popup이 현재 활성화된 모달 다이얼로그인지 확인
             if hasattr(self, 'settings_popup') and current_active_popup is self.settings_popup:
                 parent_widget = self.settings_popup
                 logging.debug("SessionManagementDialog의 부모를 settings_popup으로 설정합니다.")
             else:
                 # 다른 모달 위젯이 떠 있는 경우, 그 위에 표시되도록 할 수도 있음.
                 # 또는 항상 메인 윈도우를 부모로 할 수도 있음.
                 # 여기서는 settings_popup이 아니면 메인 윈도우를 부모로 유지.
                 logging.debug(f"활성 모달 위젯({type(current_active_popup)})이 settings_popup이 아니므로, SessionManagementDialog의 부모를 메인 윈도우로 설정합니다.")
        
        # SessionManagementDialog가 이미 존재하고 부모가 다른 경우 문제가 될 수 있으므로,
        # 부모가 바뀔 가능성이 있다면 새로 생성하는 것이 안전할 수 있음.
        # 여기서는 일단 기존 인스턴스를 재활용하되, 부모가 의도와 다른지 확인.
        if self.session_management_popup is None or not self.session_management_popup.isVisible():
            # 생성 시 올바른 부모 전달
            self.session_management_popup = SessionManagementDialog(parent_widget, self) 
            logging.debug(f"새 SessionManagementDialog 생성. 부모: {type(parent_widget)}")
        elif self.session_management_popup.parent() is not parent_widget:
            # 부모가 변경되어야 한다면, 이전 팝업을 닫고 새로 생성하거나 setParent 호출.
            # QWidget.setParent()는 주의해서 사용해야 하므로, 새로 생성하는 것이 더 간단할 수 있음.
            logging.warning(f"SessionManagementDialog의 부모가 변경되어야 함. (현재: {type(self.session_management_popup.parent())}, 필요: {type(parent_widget)}) 새로 생성합니다.")
            self.session_management_popup.close() # 이전 것 닫기
            self.session_management_popup = SessionManagementDialog(parent_widget, self)
            
        self.session_management_popup.populate_session_list()
        self.session_management_popup.update_all_button_states() # 팝업 표시 직전에 버튼 상태 강제 업데이트

        
        # exec_()를 사용하여 모달로 띄우면 "설정 및 정보" 팝업은 비활성화됨
        # show()를 사용하여 모달리스로 띄우면 두 팝업이 동시에 상호작용 가능할 수 있으나,
        # 이 경우 "설정 및 정보" 팝업이 닫힐 때 함께 닫히도록 처리하거나,
        # "세션 관리" 팝업이 항상 위에 오도록 setWindowFlags(Qt.WindowStaysOnTopHint) 설정 필요.
        # 여기서는 모달로 띄우는 것을 기본으로 가정.
        # self.session_management_popup.show() 
        # self.session_management_popup.activateWindow()
        # self.session_management_popup.raise_()
        
        # "설정 및 정보" 팝업 위에서 "세션 관리" 팝업을 모달로 띄우려면,
        # "설정 및 정보" 팝업을 잠시 hide() 했다가 "세션 관리" 팝업이 닫힌 후 다시 show() 하거나,
        # "세션 관리" 팝업을 모달리스로 하되 항상 위에 있도록 해야 함.
        # 또는, "세션 관리" 팝업 자체를 "설정 및 정보" 팝업 내부에 통합된 위젯으로 만드는 것도 방법.

        # 가장 간단한 접근: "세션 관리" 팝업을 "설정 및 정보" 팝업에 대해 모달로 띄운다.
        # 이렇게 하면 "설정 및 정보"는 "세션 관리"가 닫힐 때까지 비활성화됨.
        self.session_management_popup.exec_() # exec_()는 블로킹 호출




    def smooth_viewport_move(self):
        """타이머에 의해 호출되어 뷰포트를 부드럽게 이동시킵니다."""
        if not (self.grid_mode == "Off" and self.zoom_mode in ["100%", "Spin"] and self.original_pixmap and self.pressed_keys_for_viewport):
            self.viewport_move_timer.stop() # 조건 안 맞으면 타이머 중지
            return

        move_step_base = getattr(self, 'viewport_move_speed', 5) 
        # 실제 이동량은 setInterval에 따라 조금씩 움직이므로, move_step_base는 한 번의 timeout당 이동량의 기준으로 사용
        # 예를 들어, 속도 5, interval 16ms이면, 초당 약 5 * (1000/16) = 약 300px 이동 효과.
        # 실제로는 방향키 조합에 따라 대각선 이동 시 속도 보정 필요할 수 있음.
        # 여기서는 단순하게 각 방향 이동량을 move_step_base로 사용.
        # 더 부드럽게 하려면 move_step_base 값을 작게, interval도 작게 조절.
        # 여기서는 단계별 이동량이므로, *10은 제거하고, viewport_move_speed 값을 직접 사용하거나 약간의 배율만 적용.
        move_amount = move_step_base * 12 # 한 번의 timeout당 이동 픽셀 (조절 가능)

        dx, dy = 0, 0

        # 8방향 이동 로직 (눌린 키 조합 확인)
        if Qt.Key_Left in self.pressed_keys_for_viewport: dx += move_amount
        if Qt.Key_Right in self.pressed_keys_for_viewport: dx -= move_amount
        if Qt.Key_Up in self.pressed_keys_for_viewport: dy += move_amount
        if Qt.Key_Down in self.pressed_keys_for_viewport: dy -= move_amount
        
        # Shift+WASD 에 대한 처리도 여기에 추가
        # (eventFilter에서 pressed_keys_for_viewport에 WASD도 Arrow Key처럼 매핑해서 넣어줌)

        if dx == 0 and dy == 0: # 이동할 방향이 없으면
            self.viewport_move_timer.stop()
            return

        current_pos = self.image_label.pos()
        new_x, new_y = current_pos.x() + dx, current_pos.y() + dy

        # 패닝 범위 제한 로직 (동일하게 적용)
        if self.zoom_mode == "100%":
            zoom_factor = 1.0
        else: # Spin 모드
            zoom_factor = self.zoom_spin_value
            
        img_width = self.original_pixmap.width() * zoom_factor
        img_height = self.original_pixmap.height() * zoom_factor
        view_width = self.scroll_area.width(); view_height = self.scroll_area.height()
        x_min_limit = min(0, view_width - img_width) if img_width > view_width else (view_width - img_width) // 2
        x_max_limit = 0 if img_width > view_width else x_min_limit
        y_min_limit = min(0, view_height - img_height) if img_height > view_height else (view_height - img_height) // 2
        y_max_limit = 0 if img_height > view_height else y_min_limit
        
        final_x = max(x_min_limit, min(x_max_limit, new_x))
        final_y = max(y_min_limit, min(y_max_limit, new_y))

        if current_pos.x() != final_x or current_pos.y() != final_y:
            self.image_label.move(int(final_x), int(final_y))
            self._sync_viewports()
            if self.minimap_visible and self.minimap_widget.isVisible():
                self.update_minimap()


    def handle_raw_decoding_failure(self, failed_file_path: str):
        """RAW 파일 디코딩 실패 시 호출되는 슬롯"""
        logging.warning(f"RAW 파일 디코딩 실패 감지됨: {failed_file_path}")
        
        # 현재 표시하려던 파일과 실패한 파일이 동일한지 확인
        current_path_to_display = None
        if self.grid_mode == "Off":
            if 0 <= self.current_image_index < len(self.image_files):
                current_path_to_display = str(self.image_files[self.current_image_index])
        else:
            grid_idx = self.grid_page_start_index + self.current_grid_index
            if 0 <= grid_idx < len(self.image_files):
                current_path_to_display = str(self.image_files[grid_idx])

        if current_path_to_display == failed_file_path:
            # 사용자에게 알림 (기존 show_compatibility_message 사용 또는 새 메시지)
            self.show_themed_message_box( # 기존 show_compatibility_message 대신 직접 호출
                QMessageBox.Warning,
                LanguageManager.translate("호환성 문제"),
                LanguageManager.translate("RAW 디코딩 실패. 미리보기를 대신 사용합니다.")
            )

            # 해당 파일에 대해 강제로 "preview" 방식으로 전환하고 이미지 다시 로드 시도
            # (주의: 이로 인해 무한 루프가 발생하지 않도록 ImageLoader에서 처리했는지 확인 필요.
            #  ImageLoader가 실패 시 빈 QPixmap을 반환하므로, PhotoSortApp에서 다시 로드 요청해야 함)
            
            # 카메라 모델 가져오기 (실패할 수 있음)
            camera_model = self.get_camera_model_from_exif_or_path(failed_file_path) # 이 함수는 새로 만들어야 할 수 있음
            
            if camera_model != LanguageManager.translate("알 수 없는 카메라"):
                # 이 카메라 모델에 대해 "preview"로 강제하고, "다시 묻지 않음"은 그대로 두거나 해제할 수 있음
                current_setting = self.get_camera_raw_setting(camera_model)
                dont_ask_original = current_setting.get("dont_ask", False) if current_setting else False
                self.set_camera_raw_setting(camera_model, "preview", dont_ask_original) # 미리보기로 강제, 다시 묻지 않음은 유지
                logging.info(f"'{camera_model}' 모델의 처리 방식을 'preview'로 강제 변경 (디코딩 실패)")
            
            # ImageLoader의 현재 인스턴스 전략도 preview로 변경
            self.image_loader.set_raw_load_strategy("preview")
            
            # 디스플레이 강제 새로고침
            if self.grid_mode == "Off":
                self.force_refresh = True
                self.display_current_image() # 미리보기로 다시 로드 시도
            else:
                self.force_refresh = True # 그리드도 새로고침 필요
                self.update_grid_view()
        else:
            # 현재 표시하려는 파일이 아닌 다른 파일의 디코딩 실패 (예: 백그라운드 프리로딩 중)
            # 이 경우 사용자에게 직접 알릴 필요는 없을 수 있지만, 로깅은 중요
            logging.warning(f"백그라운드 RAW 디코딩 실패: {failed_file_path}")

    def get_camera_model_from_exif_or_path(self, file_path_str: str) -> str:
        """주어진 파일 경로에서 카메라 모델명을 추출 시도 (캐시 우선, 실패 시 exiftool)"""
        if file_path_str in self.exif_cache:
            exif_data = self.exif_cache[file_path_str]
            make = exif_data.get("exif_make", "")
            model = exif_data.get("exif_model", "")
            if make and model: return f"{make} {model}"
            if model: return model
        
        # 캐시에 없으면 exiftool 시도 (간략화된 버전)
        try:
            exiftool_path = self.get_exiftool_path()
            if Path(exiftool_path).exists():
                cmd = [exiftool_path, "-json", "-Model", "-Make", file_path_str]
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, creationflags=creationflags)
                if process.returncode == 0 and process.stdout:
                    exif_data_list = json.loads(process.stdout)
                    if exif_data_list:
                        exif_data = exif_data_list[0]
                        make = exif_data.get("Make")
                        model = exif_data.get("Model")
                        if make and model: return f"{make.strip()} {model.strip()}"
                        if model: return model.strip()
        except Exception as e:
            logging.error(f"get_camera_model_from_exif_or_path에서 오류 ({Path(file_path_str).name}): {e}")
        return LanguageManager.translate("알 수 없는 카메라")

    def get_camera_raw_setting(self, camera_model: str):
        """주어진 카메라 모델에 대한 저장된 RAW 처리 설정을 반환합니다."""
        return self.camera_raw_settings.get(camera_model, None) # 설정 없으면 None 반환

    def set_camera_raw_setting(self, camera_model: str, method: str, dont_ask: bool):
            """주어진 카메라 모델에 대한 RAW 처리 설정을 self.camera_raw_settings에 업데이트하고,
            변경 사항을 메인 상태 파일에 즉시 저장합니다."""
            if not camera_model:
                logging.warning("카메라 모델명 없이 RAW 처리 설정을 저장하려고 시도했습니다.")
                return
                
            self.camera_raw_settings[camera_model] = {
                "method": method,
                "dont_ask": dont_ask
            }
            logging.info(f"카메라별 RAW 설정 업데이트됨 (메모리): {camera_model} -> {self.camera_raw_settings[camera_model]}")
            self.save_state() # <<< 변경 사항을 photosort_data.json에 즉시 저장


    def reset_all_camera_raw_settings(self):
            """모든 카메라별 RAW 처리 설정을 초기화하고 메인 상태 파일에 즉시 저장합니다."""
            reply = self.show_themed_message_box(
                QMessageBox.Question,
                LanguageManager.translate("초기화"),
                LanguageManager.translate("저장된 모든 카메라 모델의 RAW 파일 처리 방식을 초기화하시겠습니까? 이 작업은 되돌릴 수 없습니다."),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.camera_raw_settings = {} # 메모리 내 설정 초기화
                self.save_state() # <<< 변경 사항을 photosort_data.json에 즉시 저장
                logging.info("모든 카메라별 RAW 처리 설정이 초기화되었습니다 (메인 상태 파일에 반영).")


    def get_system_memory_gb(self):
        """시스템 메모리 크기 확인 (GB)"""
        try:
            import psutil
            return psutil.virtual_memory().total / (1024 * 1024 * 1024)
        except:
            return 8.0  # 기본값 8GB
    

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
        if hasattr(self, 'grid_thumbnail_cache'):
            for key in self.grid_thumbnail_cache:
                self.grid_thumbnail_cache[key].clear()
        
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
        """프로그램 최초 실행 시 설정 팝업을 표시(좌우 패널 구조)"""
        # 설정 팝업창 생성
        self.settings_popup = QDialog(self)
        self.settings_popup.setWindowTitle(LanguageManager.translate("초기 설정"))
        self.settings_popup.setProperty("is_first_run_popup", True)
        self.settings_popup.setMinimumSize(500,350) # 가로, 세로 크기 조정
        
        # 제목 표시줄 다크 테마 적용 (Windows용)
        apply_dark_title_bar(self.settings_popup)
        
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
        
        self.settings_popup.welcome_label = QLabel(LanguageManager.translate("기본 설정을 선택해주세요."))
        self.settings_popup.welcome_label.setObjectName("first_run_welcome_label")
        self.settings_popup.welcome_label.setStyleSheet(f"color: {ThemeManager.get_color('text')}; font-size: 11pt;")
        self.settings_popup.welcome_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.settings_popup.welcome_label)
        main_layout.addSpacing(10)

        settings_ui_widget = self.setup_settings_ui(
            groups_to_build=["general", "advanced"], 
            is_first_run=True
        )
        main_layout.addWidget(settings_ui_widget)

        # 확인 버튼 추가
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 10, 0, 0)
        
        # 🎯 중요: 확인 버튼을 self의 멤버로 만들어서 언어 변경 시 업데이트 가능하게 함
        self.first_run_confirm_button = QPushButton(LanguageManager.translate("확인"))
        
        # 스타일 적용 (기존 스타일 재사용 또는 새로 정의)
        if platform.system() == "Darwin": # Mac 스타일
            self.first_run_confirm_button.setStyleSheet("""
                QPushButton { background-color: #444444; color: #D8D8D8; border: none; 
                            padding: 8px 16px; border-radius: 4px; min-width: 100px; }
                QPushButton:hover { background-color: #555555; }
                QPushButton:pressed { background-color: #222222; } """)
        else: # Windows/Linux 등
            self.first_run_confirm_button.setStyleSheet(f"""
                QPushButton {{ background-color: {ThemeManager.get_color('bg_secondary')}; color: {ThemeManager.get_color('text')};
                            border: none; padding: 8px 16px; border-radius: 4px; min-width: 100px; }}
                QPushButton:hover {{ background-color: {ThemeManager.get_color('accent_hover')}; }}
                QPushButton:pressed {{ background-color: {ThemeManager.get_color('accent_pressed')}; }} """)

        self.first_run_confirm_button.clicked.connect(self.settings_popup.accept)
        
        # 🎯 언어 변경 콜백 등록 - 첫 실행 팝업의 텍스트 업데이트
        def update_first_run_popup_texts():
            if hasattr(self, 'settings_popup') and self.settings_popup and self.settings_popup.isVisible():
                # 팝업 제목 업데이트
                self.settings_popup.setWindowTitle(LanguageManager.translate("초기 설정"))
                # 환영 메시지 업데이트
                if hasattr(self.settings_popup, 'welcome_label'):
                    self.settings_popup.welcome_label.setText(LanguageManager.translate("기본 설정을 선택해주세요."))
                # 확인 버튼 텍스트 업데이트
                if hasattr(self, 'first_run_confirm_button'):
                    self.first_run_confirm_button.setText(LanguageManager.translate("확인"))
        
        LanguageManager.register_language_change_callback(update_first_run_popup_texts)
        
        button_layout.addStretch(1)
        button_layout.addWidget(self.first_run_confirm_button)
        button_layout.addStretch(1)
        
        main_layout.addWidget(button_container)
        
        # --- dialog.exec_() 호출 및 결과에 따른 save_state() 실행 ---
        result = self.settings_popup.exec_() # 모달로 실행하고 결과 받기

        # 🎯 팝업이 닫힌 후 콜백 제거 및 멤버 변수 정리
        if update_first_run_popup_texts in LanguageManager._language_change_callbacks:
            LanguageManager._language_change_callbacks.remove(update_first_run_popup_texts)
        
        if hasattr(self, 'first_run_confirm_button'):
            delattr(self, 'first_run_confirm_button')

        if result == QDialog.Accepted: # 사용자가 "확인" 버튼을 눌렀다면
            logging.info("첫 실행 설정: '확인' 버튼 클릭됨. 상태 저장 실행.")
            self.save_state() # photosort_data.json 파일 생성 및 현재 설정 저장
            return True # <<< "확인" 눌렀음을 알림
        else: # 사용자가 "확인" 버튼을 누르지 않았다면 (팝업 닫기, ESC 키 등)
            logging.info("첫 실행 설정: '확인' 버튼을 누르지 않음. 상태 저장 안함.")
            return False # <<< "확인" 누르지 않았음을 알림

    def show_first_run_settings_popup_delayed(self):
        """메인 윈도우 표시 후 첫 실행 설정 팝업을 표시"""
        accepted_first_run = self.show_first_run_settings_popup()
        
        if not accepted_first_run:
            logging.info("PhotoSortApp: 첫 실행 설정이 완료되지 않아 앱을 종료합니다.")
            
            # 🎯 추가 검증: photosort_data.json 파일이 생성되지 않았는지 확인
            state_file_path = self.get_script_dir() / self.STATE_FILE
            if state_file_path.exists():
                logging.warning("PhotoSortApp: 첫 실행 설정 취소했으나 상태 파일이 존재함. 삭제합니다.")
                try:
                    state_file_path.unlink()
                    logging.info("PhotoSortApp: 상태 파일 삭제 완료.")
                except Exception as e:
                    logging.error(f"PhotoSortApp: 상태 파일 삭제 실패: {e}")
            
            QApplication.quit()
            return
        
        # 첫 실행 플래그 제거
        if hasattr(self, 'is_first_run'):
            delattr(self, 'is_first_run')
        
        logging.info("PhotoSortApp: 첫 실행 설정 완료")


    def _build_shortcut_html(self):
        """단축키 안내를 위한 HTML 문자열을 생성하는 통합 함수입니다."""
        # 테이블 스타일 정의
        html = """
        <style>
            table { width: 100%; border-collapse: collapse; font-size: 10pt; }
            th { text-align: left; padding: 12px 8px; color: #FFFFFF; border-bottom: 1px solid #666666; }
            td { padding: 8px; vertical-align: top; }
            td.key { font-weight: bold; color: #E0E0E0; width: 35%; padding-right: 25px; }
            td.desc { color: #B0B0B0; }
            .group-title { 
                padding-top: 45px; 
                font-size: 12pt; 
                font-weight: bold; 
                color: #FFFFFF;
                padding-bottom: 10px;
            }
            .group-title-first {
                padding-top: 15px;
                font-size: 12pt; 
                font-weight: bold; 
                color: #FFFFFF;
                padding-bottom: 10px;
            }
        </style>
        <table>
        """
        first_group = True # 첫 번째 그룹인지 확인하기 위한 플래그
        for item in self.SHORTCUT_DEFINITIONS:
            if len(item) == 2 and item[0] == "group":
                # 그룹 제목 행
                item_type, col1 = item
                group_title = LanguageManager.translate(col1)
                
                if first_group:
                    html += f"<tr><td colspan='2' class='group-title-first' style='text-align: center;'>[ {group_title} ]</td></tr>"
                    first_group = False
                else:
                    html += f"<tr><td colspan='2' class='group-title' style='text-align: center;'>[ {group_title} ]</td></tr>"
            elif len(item) == 3 and item[0] == "key":
                # 단축키 항목 행
                item_type, col1, col2 = item
                key_text = LanguageManager.translate(col1)
                desc_text = LanguageManager.translate(col2)
                html += f"<tr><td class='key'>{key_text}</td><td class='desc'>{desc_text}</td></tr>"
        html += "</table>"
        return html


    def _update_shortcut_label_text(self, label_widget):
        """주어진 라벨 위젯의 텍스트를 현재 언어의 단축키 안내로 업데이트"""
        if label_widget:
            label_widget.setText(self._build_shortcut_html())

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

    def start_background_thumbnail_preloading(self):
        """Grid Off 상태일 때 그리드 썸네일 백그라운드 생성을 시작합니다."""
        if self.grid_mode != "Off" or not self.image_files:
            return

        logging.info("백그라운드 그리드 썸네일 생성 시작...")
        for future in self.active_thumbnail_futures:
            future.cancel()
        self.active_thumbnail_futures.clear()

        current_index = self.current_image_index
        if current_index < 0:
            return

        # HardwareProfileManager에서 그리드 미리 로딩 한도 비율 가져오기
        limit_factor = HardwareProfileManager.get("preload_grid_bg_limit_factor")
        preload_limit = int(self.image_loader.cache_limit * limit_factor)
        max_preload = min(preload_limit, len(self.image_files))
        
        logging.debug(f"그리드 썸네일 사전 로드 한도: {max_preload}개 (캐시 크기: {self.image_loader.cache_limit}, 비율: {limit_factor})")
        # --- 로직 개선 끝 ---

        preload_range = self.calculate_adaptive_thumbnail_preload_range()
        futures = []
        
        # 우선순위 이미지 (현재 이미지 주변)
        priority_indices = []
        # 중복 추가를 방지하기 위한 set
        added_indices = set()

        for offset in range(preload_range + 1):
            if len(priority_indices) >= max_preload: break
            
            # 현재 위치
            if offset == 0:
                idx = current_index
                if idx not in added_indices:
                    priority_indices.append(idx)
                    added_indices.add(idx)
                continue
                
            # 앞쪽
            idx_fwd = (current_index + offset) % len(self.image_files)
            if idx_fwd not in added_indices:
                priority_indices.append(idx_fwd)
                added_indices.add(idx_fwd)
                if len(priority_indices) >= max_preload: break

            # 뒤쪽
            idx_bwd = (current_index - offset + len(self.image_files)) % len(self.image_files)
            if idx_bwd not in added_indices:
                priority_indices.append(idx_bwd)
                added_indices.add(idx_bwd)
                if len(priority_indices) >= max_preload: break

        # 우선순위 이미지 로드
        for idx in priority_indices:
            img_path = str(self.image_files[idx])
            future = self.grid_thumbnail_executor.submit(
                self._preload_image_for_grid, img_path
            )
            futures.append(future)

        self.active_thumbnail_futures = futures
        logging.info(f"총 {len(futures)}개의 그리드용 이미지 사전 로딩 작업 제출됨.")

    def calculate_adaptive_thumbnail_preload_range(self):
        """시스템 메모리에 따라 프리로딩 범위 결정"""
        try:
            import psutil
            system_memory_gb = psutil.virtual_memory().total / (1024 * 1024 * 1024)
            
            if system_memory_gb >= 24:
                return 8  # 앞뒤 각각 8개 이미지 (총 17개)
            elif system_memory_gb >= 12:
                return 5  # 앞뒤 각각 5개 이미지 (총 11개)
            else:
                return 3  # 앞뒤 각각 3개 이미지 (총 7개)
        except:
            return 3  # 기본값

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
        
    def on_mouse_wheel_action_changed(self, button):
        """마우스 휠 동작 설정 변경 시 호출"""
        if button == self.mouse_wheel_photo_radio:
            self.mouse_wheel_action = "photo_navigation"
            logging.info("마우스 휠 동작: 사진 넘기기로 변경됨")
        elif button == self.mouse_wheel_none_radio:
            self.mouse_wheel_action = "none"
            logging.info("마우스 휠 동작: 없음으로 변경됨")

    def _create_settings_controls(self):
        """설정 창에 사용될 모든 UI 컨트롤들을 미리 생성하고 초기화합니다."""
        # --- 공통 스타일 ---
        radio_style = f"""
            QRadioButton {{ color: {ThemeManager.get_color('text')}; padding: 5px 10px; }}
            QRadioButton::indicator {{ width: {UIScaleManager.get("radiobutton_size")}px; height: {UIScaleManager.get("radiobutton_size")}px; }}
            QRadioButton::indicator:checked {{ background-color: {ThemeManager.get_color('accent')}; border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('accent')}; border-radius: {UIScaleManager.get("radiobutton_border_radius")}px; }}
            QRadioButton::indicator:unchecked {{ background-color: {ThemeManager.get_color('bg_primary')}; border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('border')}; border-radius: {UIScaleManager.get("radiobutton_border_radius")}px; }}
            QRadioButton::indicator:unchecked:hover {{ border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('text_disabled')}; }}
        """
        checkbox_style = f"""
            QCheckBox {{ color: {ThemeManager.get_color('text')}; padding: 3px 5px; }}
            QCheckBox::indicator {{ width: {UIScaleManager.get("checkbox_size")}px; height: {UIScaleManager.get("checkbox_size")}px; }}
            QCheckBox::indicator:checked {{ background-color: {ThemeManager.get_color('accent')}; border: {UIScaleManager.get("checkbox_border")}px solid {ThemeManager.get_color('accent')}; border-radius: {UIScaleManager.get("checkbox_border_radius")}px; }}
            QCheckBox::indicator:unchecked {{ background-color: {ThemeManager.get_color('bg_primary')}; border: {UIScaleManager.get("checkbox_border")}px solid {ThemeManager.get_color('border')}; border-radius: {UIScaleManager.get("checkbox_border_radius")}px; }}
            QCheckBox::indicator:unchecked:hover {{ border: {UIScaleManager.get("checkbox_border")}px solid {ThemeManager.get_color('text_disabled')}; }}
        """

        # --- 언어 설정 ---
        self.language_group = QButtonGroup(self)
        self.english_radio = QRadioButton("English")
        self.korean_radio = QRadioButton("한국어")
        self.english_radio.setStyleSheet(radio_style)
        self.korean_radio.setStyleSheet(radio_style)
        self.language_group.addButton(self.english_radio, 0)
        self.language_group.addButton(self.korean_radio, 1)
        self.language_group.buttonClicked.connect(self.on_language_radio_changed)

        # --- 테마 설정 ---
        self.theme_combo = QComboBox()
        for theme_name in ThemeManager.get_available_themes():
            self.theme_combo.addItem(theme_name.capitalize())
        self.theme_combo.setStyleSheet(self.generate_combobox_style())
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)

        # --- 컨트롤 패널 위치 설정 ---
        self.panel_position_group = QButtonGroup(self)
        self.panel_pos_left_radio = QRadioButton() # 텍스트 제거
        self.panel_pos_right_radio = QRadioButton() # 텍스트 제거
        self.panel_pos_left_radio.setStyleSheet(radio_style)
        self.panel_pos_right_radio.setStyleSheet(radio_style)
        self.panel_position_group.addButton(self.panel_pos_left_radio, 0)
        self.panel_position_group.addButton(self.panel_pos_right_radio, 1)
        self.panel_position_group.buttonClicked.connect(self._on_panel_position_changed)

        # --- 날짜 형식 설정 ---
        self.date_format_combo = QComboBox()
        for format_code in DateFormatManager.get_available_formats():
            display_name = DateFormatManager.get_format_display_name(format_code)
            self.date_format_combo.addItem(display_name, format_code)
        self.date_format_combo.setStyleSheet(self.generate_combobox_style())
        self.date_format_combo.currentIndexChanged.connect(self.on_date_format_changed)

        # --- 불러올 이미지 형식 설정 ---
        self.ext_checkboxes = {}
        extension_groups = {"JPG": ['.jpg', '.jpeg'], "PNG": ['.png'], "WebP": ['.webp'], "HEIC": ['.heic', '.heif'], "BMP": ['.bmp'], "TIFF": ['.tif', '.tiff']}
        for name, exts in extension_groups.items():
            checkbox = QCheckBox(name)
            checkbox.setStyleSheet(checkbox_style)
            checkbox.stateChanged.connect(self.on_extension_checkbox_changed)
            self.ext_checkboxes[name] = checkbox
    
        # --- 분류 폴더 개수 설정 ---
        self.folder_count_combo = QComboBox()
        for i in range(1, 10):
            self.folder_count_combo.addItem(str(i), i)
        self.folder_count_combo.setStyleSheet(self.generate_combobox_style())
        self.folder_count_combo.setMinimumWidth(80)
        self.folder_count_combo.currentIndexChanged.connect(self.on_folder_count_changed)

        # --- 뷰포트 이동 속도 설정 ---
        self.viewport_speed_combo = QComboBox()
        for i in range(1, 11):
            self.viewport_speed_combo.addItem(str(i), i)
        self.viewport_speed_combo.setStyleSheet(self.generate_combobox_style())
        self.viewport_speed_combo.setMinimumWidth(80)
        self.viewport_speed_combo.currentIndexChanged.connect(self.on_viewport_speed_changed)

        # --- 마우스 휠 동작 설정 ---
        self.mouse_wheel_group = QButtonGroup(self)
        self.mouse_wheel_photo_radio = QRadioButton() # 텍스트 제거
        self.mouse_wheel_none_radio = QRadioButton() # 텍스트 제거
        self.mouse_wheel_photo_radio.setStyleSheet(radio_style)
        self.mouse_wheel_none_radio.setStyleSheet(radio_style)
        self.mouse_wheel_group.addButton(self.mouse_wheel_photo_radio, 0)
        self.mouse_wheel_group.addButton(self.mouse_wheel_none_radio, 1)
        self.mouse_wheel_group.buttonClicked.connect(self.on_mouse_wheel_action_changed)

        # --- 저장된 RAW 처리 방식 초기화 버튼 ---
        button_style = f"""
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')}; color: {ThemeManager.get_color('text')};
                border: none; padding: 8px 12px; border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {ThemeManager.get_color('bg_hover')}; }}
            QPushButton:pressed {{ background-color: {ThemeManager.get_color('bg_pressed')}; }}
        """
        self.reset_camera_settings_button = QPushButton() # 텍스트 제거
        self.reset_camera_settings_button.setStyleSheet(button_style)
        self.reset_camera_settings_button.clicked.connect(self.reset_all_camera_raw_settings)

        # --- 프로그램 초기화 버튼 ---
        self.reset_app_settings_button = QPushButton(LanguageManager.translate("프로그램 설정 초기화"))
        self.reset_app_settings_button.setStyleSheet(button_style)
        self.reset_app_settings_button.clicked.connect(self.reset_application_settings)

        # --- 세션 관리 및 단축키 버튼 생성 ---
        self.session_management_button = QPushButton() # 텍스트 제거
        self.session_management_button.setStyleSheet(button_style)
        self.session_management_button.clicked.connect(self.show_session_management_popup)

        self.shortcuts_button = QPushButton() # 텍스트 제거
        self.shortcuts_button.setStyleSheet(button_style)
        self.shortcuts_button.clicked.connect(self.show_shortcuts_popup)

        # --- 성능 프로필 설정 ---
        self.performance_profile_combo = QComboBox()
        # 아이템 추가 로직을 전용 업데이트 함수로 이전
        self.update_performance_profile_combo_text()
        self.performance_profile_combo.setStyleSheet(self.generate_combobox_style())
        self.performance_profile_combo.currentIndexChanged.connect(self.on_performance_profile_changed)

    def update_performance_profile_combo_text(self):
        """성능 프로필 콤보박스의 텍스트를 현재 언어에 맞게 업데이트합니다."""
        if not hasattr(self, 'performance_profile_combo'):
            return

        # 현재 선택된 프로필 키를 저장해 둡니다.
        current_key = self.performance_profile_combo.itemData(self.performance_profile_combo.currentIndex())
        
        # 시그널을 잠시 막고 아이템을 다시 채웁니다.
        self.performance_profile_combo.blockSignals(True)
        self.performance_profile_combo.clear()
        
        for profile_key, profile_data in HardwareProfileManager.PROFILES.items():
            # 번역 키를 가져와서 번역합니다.
            translated_name = LanguageManager.translate(profile_data["name"])
            self.performance_profile_combo.addItem(translated_name, profile_key)
        
        # 이전에 선택했던 프로필을 다시 선택합니다.
        if current_key:
            index = self.performance_profile_combo.findData(current_key)
            if index != -1:
                self.performance_profile_combo.setCurrentIndex(index)
                
        self.performance_profile_combo.blockSignals(False)

    def update_all_settings_controls_text(self):
        """현재 언어 설정에 맞게 모든 설정 관련 컨트롤의 텍스트를 업데이트합니다."""
        # --- 라디오 버튼 ---
        self.panel_pos_left_radio.setText(LanguageManager.translate("좌측"))
        self.panel_pos_right_radio.setText(LanguageManager.translate("우측"))
        self.mouse_wheel_photo_radio.setText(LanguageManager.translate("사진 넘기기"))
        self.mouse_wheel_none_radio.setText(LanguageManager.translate("없음"))

        # --- 버튼 ---
        self.reset_camera_settings_button.setText(LanguageManager.translate("RAW 처리 방식 초기화"))
        self.reset_app_settings_button.setText(LanguageManager.translate("프로그램 설정 초기화"))
        self.session_management_button.setText(LanguageManager.translate("세션 관리"))
        self.shortcuts_button.setText(LanguageManager.translate("단축키 확인"))

        # 설정 창이 열려있을 때, 그 내부의 라벨 텍스트들도 업데이트
        if hasattr(self, 'settings_popup') and self.settings_popup and self.settings_popup.isVisible():
            self.update_settings_labels_texts(self.settings_popup)

    def setup_settings_ui(self, groups_to_build=None, is_first_run=False):
        """
        설정 UI의 특정 그룹들을 동적으로 구성하고 컨테이너 위젯을 반환합니다.
        is_first_run: 최초 실행 팝업인지 여부를 나타내는 플래그.
        """
        if groups_to_build is None:
            groups_to_build = ["general", "workflow", "advanced"]

        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(UIScaleManager.get("settings_layout_vspace", 15) * 1.5) # 그룹 간 간격 조정

        group_builders = {
            "general": self._build_general_settings_group,
            "workflow": self._build_workflow_settings_group,
            "advanced": self._build_advanced_tools_group,
        }

        for i, group_name in enumerate(groups_to_build):
            if group_name in group_builders:
                # is_first_run 플래그를 각 그룹 빌더에 전달
                group_widget = group_builders[group_name](is_first_run=is_first_run)
                main_layout.addWidget(group_widget)
                
                # 그룹 사이에 구분선 추가 (최초 실행이 아니고, 마지막 그룹이 아닐 때)
                if not is_first_run and i < len(groups_to_build) - 1:
                    separator = QFrame()
                    separator.setFrameShape(QFrame.HLine)
                    separator.setFrameShadow(QFrame.Sunken)
                    separator.setStyleSheet(f"background-color: {ThemeManager.get_color('border')}; max-height: 1px;")
                    main_layout.addWidget(separator)
        
        main_layout.addStretch(1)

        return main_container

    def _build_group_widget(self, title_key, add_widgets_func, show_title=True):
        """설정 그룹 UI를 위한 템플릿 위젯을 생성합니다."""
        group_box = QWidget()
        group_layout = QVBoxLayout(group_box)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(UIScaleManager.get("settings_layout_vspace", 15))

        if show_title:
            title_label = QLabel(LanguageManager.translate(title_key))
            font = QFont(self.font())
            font.setBold(True)
            font.setPointSize(UIScaleManager.get("font_size") + 1)
            title_label.setFont(font)
            title_label.setStyleSheet(f"""
                color: {ThemeManager.get_color('text')}; 
                margin-bottom: 5px;
                padding-left: 0px;
            """)
            title_label.setObjectName(f"group_title_{title_key.replace(' ', '_')}")
            
            group_layout.addWidget(title_label)
        
        add_widgets_func(group_layout)

        return group_box

    def _build_general_settings_group(self, is_first_run=False):
        """'UI 설정' 그룹 UI를 생성합니다."""
        def add_widgets(layout):
            layout.addWidget(self._create_setting_row("언어", self._create_language_radios()))
            layout.addWidget(self._create_setting_row("테마", self.theme_combo))
            layout.addWidget(self._create_setting_row("컨트롤 패널", self._create_panel_position_radios()))
            layout.addWidget(self._create_setting_row("날짜 형식", self.date_format_combo))
        
        return self._build_group_widget("UI 설정", add_widgets, show_title=not is_first_run)
    
    def _build_workflow_settings_group(self, is_first_run=False):
        """'작업 설정' 그룹 UI를 생성합니다."""
        def add_widgets(layout):
            layout.addWidget(self._create_setting_row("불러올 이미지 형식", self._create_extension_checkboxes()))
            layout.addWidget(self._create_setting_row("분류 폴더 개수", self.folder_count_combo))
            layout.addWidget(self._create_setting_row("뷰포트 이동 속도", self.viewport_speed_combo))
            layout.addWidget(self._create_setting_row("마우스 휠 동작", self._create_mouse_wheel_radios()))

        return self._build_group_widget("작업 설정", add_widgets)

    def update_quick_sort_input_style(self):
        """빠른 분류 입력 필드의 활성화/비활성화 스타일을 업데이트합니다."""
        # 활성화 스타일
        active_style = f"""
            QLineEdit {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: 1px solid {ThemeManager.get_color('border')};
                padding: 4px; border-radius: 3px;
            }}
            QLineEdit:focus {{ border: 1px solid {ThemeManager.get_color('accent')}; }}
        """
        # 비활성화 스타일
        disabled_style = f"""
            QLineEdit {{
                background-color: {ThemeManager.get_color('bg_disabled')};
                color: {ThemeManager.get_color('text_disabled')};
                border: 1px solid {ThemeManager.get_color('border')};
                padding: 4px; border-radius: 3px;
            }}
        """
        
        self.quick_sort_e_input.setEnabled(self.quick_sort_e_enabled)
        self.quick_sort_e_input.setStyleSheet(active_style if self.quick_sort_e_enabled else disabled_style)

        self.quick_sort_f_input.setEnabled(self.quick_sort_f_enabled)
        self.quick_sort_f_input.setStyleSheet(active_style if self.quick_sort_f_enabled else disabled_style)


    def _is_valid_foldername(self, name):
        """폴더명으로 사용 가능한지 검증하는 헬퍼 메서드"""
        if not name or not name.strip():
            return False
        invalid_chars = '\\/:*?"<>|'
        if any(char in name for char in invalid_chars):
            return False
        return True

    def on_performance_profile_changed(self, index):
        if index < 0: return
        profile_key = self.performance_profile_combo.itemData(index)
        
        HardwareProfileManager.set_profile_manually(profile_key)
        logging.info(f"사용자가 성능 프로필을 '{profile_key}'로 변경했습니다. 앱을 재시작해야 적용됩니다.")
        
        # 번역 키 사용
        title = LanguageManager.translate("설정 변경")
        line1_key = "성능 프로필이 '{profile_name}'(으)로 변경되었습니다."
        line2_key = "이 설정은 앱을 재시작해야 완전히 적용됩니다."
        
        profile_name_key = HardwareProfileManager.get("name")
        
        translated_profile_name = LanguageManager.translate(profile_name_key)
        
        message = (
            LanguageManager.translate(line1_key).format(profile_name=translated_profile_name) +
            "\n\n" +
            LanguageManager.translate(line2_key)
        )
        
        self.show_themed_message_box(QMessageBox.Information, title, message)

    def _build_advanced_tools_group(self, is_first_run=False):
        """'도구 및 고급 설정' 그룹 UI를 생성합니다."""
        def add_widgets(layout):
            if not is_first_run:
                # 성능 프로필 설정 추가
                layout.addWidget(self._create_setting_row("성능 설정 ⓘ", self.performance_profile_combo))

                # "세션 관리" 버튼을 라벨 없이 바로 추가
                container_session = QWidget()
                layout_session = QHBoxLayout(container_session)
                layout_session.setContentsMargins(0,0,0,0)
                layout_session.addWidget(self.session_management_button)
                layout_session.addStretch(1)
                layout.addWidget(container_session)

                # "RAW 처리 방식 초기화" 버튼을 라벨 없이 바로 추가
                container_raw = QWidget()
                layout_raw = QHBoxLayout(container_raw)
                layout_raw.setContentsMargins(0,0,0,0)
                layout_raw.addWidget(self.reset_camera_settings_button)
                layout_raw.addStretch(1)
                layout.addWidget(container_raw)

            # "단축키 확인" 버튼을 라벨 없이 바로 추가
            container_shortcuts = QWidget()
            layout_shortcuts = QHBoxLayout(container_shortcuts)
            layout_shortcuts.setContentsMargins(0,0,0,0)
            layout_shortcuts.addWidget(self.shortcuts_button)
            layout_shortcuts.addStretch(1)
            layout.addWidget(container_shortcuts)

            if not is_first_run:
                container_app_reset = QWidget()
                layout_app_reset = QHBoxLayout(container_app_reset)
                layout_app_reset.setContentsMargins(0,0,0,0)
                layout_app_reset.addWidget(self.reset_app_settings_button)
                layout_app_reset.addStretch(1)
                layout.addWidget(container_app_reset)

        return self._build_group_widget("도구 및 고급 설정", add_widgets, show_title=not is_first_run)

    def _create_setting_row(self, label_key, control_widget):
        """설정 항목 한 줄(라벨 + 컨트롤)을 생성하는 헬퍼 메서드"""
        row_container = QWidget()
        row_layout = QHBoxLayout(row_container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        label_text = LanguageManager.translate(label_key)
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        label.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        label.setMinimumWidth(UIScaleManager.get("settings_label_width"))
        label.setObjectName(f"{label_key.replace(' ', '_')}_label")
        # 툴팁 추가
        if label_key == "성능 설정 ⓘ":
            tooltip_key = "시스템 사양에 맞춰 자동으로 설정된 프로필입니다.\n높은 단계일수록 더 많은 메모리와 CPU를 사용하여 작업 속도를 높입니다.\n앱이 시스템을 느리게 하거나 메모리를 너무 많이 차지하는 경우 낮은 단계로 변경해주세요."
            tooltip_text = LanguageManager.translate(tooltip_key)
            label.setToolTip(tooltip_text)
            label.setCursor(Qt.WhatsThisCursor)

        row_layout.addWidget(label)

        if control_widget:
            row_layout.addWidget(control_widget)
            # 컨트롤 위젯이 버튼이면, 버튼 크기만큼만 공간을 차지하고 나머지는 빈 공간으로 둡니다.
            if isinstance(control_widget, QPushButton):
                row_layout.addStretch(1)
            # 콤보박스나 체크박스 그룹처럼 스스로 너비를 조절하는 위젯이 아니면 Stretch 추가
            elif not isinstance(control_widget, (QComboBox, QCheckBox)):
                 if control_widget.layout() is not None and isinstance(control_widget.layout(), QHBoxLayout):
                     pass
                 else:
                     row_layout.addStretch(1)
        else:
             row_layout.addStretch(1)

        return row_container

    def _create_language_radios(self):
        """언어 선택 라디오 버튼 그룹 위젯 생성"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.addWidget(self.english_radio)
        layout.addWidget(self.korean_radio)
        layout.addStretch(1)
        return container

    def _create_panel_position_radios(self):
        """패널 위치 선택 라디오 버튼 그룹 위젯 생성"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.addWidget(self.panel_pos_left_radio)
        layout.addWidget(self.panel_pos_right_radio)
        layout.addStretch(1)
        return container

    def _create_mouse_wheel_radios(self):
        """마우스 휠 동작 선택 라디오 버튼 그룹 위젯 생성"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.addWidget(self.mouse_wheel_photo_radio)
        layout.addWidget(self.mouse_wheel_none_radio)
        layout.addStretch(1)
        return container

    def _create_extension_checkboxes(self):
        """이미지 형식 체크박스 그룹 위젯 생성 (2줄 구조)"""
        # 전체 체크박스들을 담을 메인 컨테이너와 수직 레이아웃
        main_container = QWidget()
        vertical_layout = QVBoxLayout(main_container)
        vertical_layout.setContentsMargins(0, 0, 0, 0)
        vertical_layout.setSpacing(10)  # 줄 사이의 수직 간격

        # 첫 번째 줄 체크박스 키 목록
        keys_row1 = ["JPG", "HEIC", "WebP"]
        # 두 번째 줄 체크박스 키 목록
        keys_row2 = ["PNG", "BMP", "TIFF"]

        # --- 첫 번째 줄 생성 ---
        row1_container = QWidget()
        row1_layout = QHBoxLayout(row1_container)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(20) # 체크박스 사이의 수평 간격

        for name in keys_row1:
            if name in self.ext_checkboxes:
                row1_layout.addWidget(self.ext_checkboxes[name])
        row1_layout.addStretch(1) # 오른쪽에 남는 공간을 채움

        # --- 두 번째 줄 생성 ---
        row2_container = QWidget()
        row2_layout = QHBoxLayout(row2_container)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(20) # 체크박스 사이의 수평 간격

        for name in keys_row2:
            if name in self.ext_checkboxes:
                row2_layout.addWidget(self.ext_checkboxes[name])
        row2_layout.addStretch(1) # 오른쪽에 남는 공간을 채움

        # --- 메인 레이아웃에 각 줄 추가 ---
        vertical_layout.addWidget(row1_container)
        vertical_layout.addWidget(row2_container)

        return main_container

    def on_viewport_speed_changed(self, index):
        """뷰포트 이동 속도 콤보박스 변경 시 호출"""
        if index < 0: return
        selected_speed = self.viewport_speed_combo.itemData(index)
        if selected_speed is not None:
            self.viewport_move_speed = int(selected_speed)
            logging.info(f"뷰포트 이동 속도 변경됨: {self.viewport_move_speed}")
            # self.save_state() # 즉시 저장하려면 호출 (set_camera_raw_setting처럼)


    def on_theme_changed(self, theme_name):
        """테마 변경 시 호출되는 함수"""
        # 소문자로 변환 (ThemeManager에서는 소문자 키 사용)
        theme_name = theme_name.lower()
        ThemeManager.set_theme(theme_name)
        # 모든 UI가 update_ui_colors()를 통해 자동으로 업데이트됨


    def update_scrollbar_style(self):
        """컨트롤 패널의 스크롤바 스타일을 현재 테마에 맞게 업데이트합니다."""
        if hasattr(self, 'control_panel') and isinstance(self.control_panel, QScrollArea):
            self.control_panel.setStyleSheet(f"""
                QScrollArea {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border: none;
                }}
                QScrollBar:vertical {{
                    border: none;
                    background: {ThemeManager.get_color('bg_primary')};
                    width: 6px;
                    margin: 0px 0px 0px 0px;
                }}
                QScrollBar::handle:vertical {{
                    background: {ThemeManager.get_color('border')};
                    min-height: 20px;
                    border-radius: 5px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background: {ThemeManager.get_color('accent_hover')};
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                    border: none;
                    background: none;
                    height: 0px;
                }}
                QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{
                    background: none;
                }}
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                    background: none;
                }}
            """)

    def update_ui_colors(self):
        """테마 변경 시 모든 UI 요소의 색상을 업데이트"""
        # 모든 UI 요소의 스타일시트를 다시 설정
        self.update_button_styles()
        self.update_label_styles()
        self.update_folder_styles()
        self.update_scrollbar_style()
        
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
        button_style = ThemeManager.generate_main_button_style()
        # 삭제 버튼 스타일
        delete_button_style = ThemeManager.generate_action_button_style()
        # 라디오 버튼 스타일
        radio_style = ThemeManager.generate_radio_button_style()

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
        if hasattr(self, 'folder_action_buttons'): # folder_delete_buttons -> folder_action_buttons
            for button in self.folder_action_buttons:
                button.setStyleSheet(delete_button_style)
        # 줌 라디오 버튼 스타일 적용
        if hasattr(self, 'zoom_group'):
            for button in self.zoom_group.buttons():
                button.setStyleSheet(radio_style)
                
        if hasattr(self, 'grid_mode_group'):
            for button in self.grid_mode_group.buttons():
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

        # 미니맵 토글 및 RAW 토글 체크박스 스타일 업데이트
        if hasattr(self, 'minimap_toggle'):
            self.minimap_toggle.setStyleSheet(ThemeManager.generate_checkbox_style())
        if hasattr(self, 'raw_toggle_button'):
            self.raw_toggle_button.setStyleSheet(ThemeManager.generate_checkbox_style())
        if hasattr(self, 'filename_toggle_grid'):
            self.filename_toggle_grid.setStyleSheet(ThemeManager.generate_checkbox_style())
        
    
    def update_folder_styles(self):
        """폴더 관련 UI 요소의 스타일을 업데이트 (테마 변경 시 호출됨)"""
        # 1. JPG/RAW 폴더 UI 상태 업데이트 (내부적으로 InfoFolderPathLabel의 스타일 재설정)
        if hasattr(self, 'folder_path_label'):
            self.update_jpg_folder_ui_state()
        if hasattr(self, 'raw_folder_path_label'):
            self.update_raw_folder_ui_state()

        # 2. 분류 폴더 UI 상태 업데이트 (내부적으로 EditableFolderPathLabel의 스타일 재설정)
        if hasattr(self, 'folder_path_labels'):
            self.update_all_folder_labels_state()
    
    def _create_settings_popup(self):
        """설정 팝업창을 최초 한 번만 생성하고 레이아웃을 구성합니다."""
        self.settings_popup = QDialog(self)
        self.settings_popup.setWindowTitle(LanguageManager.translate("설정 및 정보"))
        popup_width = UIScaleManager.get("settings_popup_width", 785)
        popup_height = UIScaleManager.get("settings_popup_height", 910)
        self.settings_popup.setMinimumSize(popup_width, popup_height)
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(ThemeManager.get_color('bg_primary')))
        self.settings_popup.setPalette(palette)
        self.settings_popup.setAutoFillBackground(True)

        # --- 메인 레이아웃 (수평 2컬럼) ---
        main_layout = QHBoxLayout(self.settings_popup)
        main_layout.setContentsMargins(25, 20, 25, 20)
        main_layout.setSpacing(30)

        # --- 왼쪽 컬럼 (설정 항목들) ---
        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        settings_ui_widget = self.setup_settings_ui()
        left_layout.addWidget(settings_ui_widget)

        # --- 중앙 구분선 ---
        separator_vertical = QFrame()
        separator_vertical.setFrameShape(QFrame.VLine)
        separator_vertical.setFrameShadow(QFrame.Sunken)
        separator_vertical.setStyleSheet(f"background-color: {ThemeManager.get_color('border')}; max-width: 1px;")

        # --- 오른쪽 컬럼 (정보 및 후원) ---
        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(UIScaleManager.get("info_donation_spacing", 40))
        info_section = self._build_info_section()
        right_layout.addWidget(info_section)
        separator_horizontal = QFrame()
        separator_horizontal.setFrameShape(QFrame.HLine)
        separator_horizontal.setFrameShadow(QFrame.Sunken)
        separator_horizontal.setStyleSheet(f"background-color: {ThemeManager.get_color('border')}; max-height: 1px;")
        right_layout.addWidget(separator_horizontal)
        donation_section = self._build_donation_section()
        right_layout.addWidget(donation_section)
        right_layout.addStretch(1)

        # --- 메인 레이아웃에 컬럼 추가 ---
        main_layout.addWidget(left_column, 6)
        main_layout.addWidget(separator_vertical)
        main_layout.addWidget(right_column, 4)

    def show_settings_popup(self):
        """설정 버튼 클릭 시 호출, 팝업을 생성하거나 기존 팝업을 보여줍니다."""
        if not hasattr(self, 'settings_popup') or self.settings_popup is None:
            self._create_settings_popup()

        # 팝업을 보여주기 전에 현재 상태를 UI 컨트롤에 반영
        # (예: 테마 콤보박스)
        current_theme_name = ThemeManager.get_current_theme_name()
        index = self.theme_combo.findText(current_theme_name.capitalize(), Qt.MatchFixedString)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        
        # 현재 언어 설정 반영
        current_lang = LanguageManager.get_current_language()
        if current_lang == "en":
            self.english_radio.setChecked(True)
        else:
            self.korean_radio.setChecked(True)

        # 팝업의 모든 텍스트를 현재 언어에 맞게 업데이트
        self.update_settings_labels_texts(self.settings_popup)

        apply_dark_title_bar(self.settings_popup)
        self.settings_popup.exec_()


    def _build_info_section(self):
        """'정보' 섹션 UI를 생성합니다."""
        info_section = QWidget()
        info_layout = QVBoxLayout(info_section)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(0)

        info_text = self.create_translated_info_text()
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        info_label.setObjectName("photosort_info_label")
        info_label.setOpenExternalLinks(True)
        info_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        info_layout.addWidget(info_label)
        info_layout.addSpacing(UIScaleManager.get("infotext_licensebutton", 40))

        license_button_container = QWidget()
        license_button_layout = QHBoxLayout(license_button_container)
        license_button_layout.setContentsMargins(0, 0, 0, 0)
        licenses_button = QPushButton("Open Source Licenses")
        licenses_button.setStyleSheet(f"""
            QPushButton {{ background-color: {ThemeManager.get_color('bg_secondary')}; color: {ThemeManager.get_color('text')}; border: none; padding: 8px 16px; border-radius: 4px; min-width: 180px; }}
            QPushButton:hover {{ background-color: {ThemeManager.get_color('bg_hover')}; }}
            QPushButton:pressed {{ background-color: {ThemeManager.get_color('bg_pressed')}; }}
        """)
        licenses_button.setCursor(Qt.PointingHandCursor)
        licenses_button.clicked.connect(self.show_licenses_popup)
        license_button_layout.addStretch(1)
        license_button_layout.addWidget(licenses_button)
        license_button_layout.addStretch(1)
        info_layout.addWidget(license_button_container)
        
        return info_section

    def _build_donation_section(self):
        """'후원' 섹션 UI를 생성합니다."""
        # 이 부분은 기존 show_settings_popup의 후원 섹션 로직을 그대로 가져옵니다.
        # (코드가 길어 생략하고, 기존 로직을 이 함수 안으로 옮기면 됩니다.)
        donation_section = QWidget()
        donation_layout = QVBoxLayout(donation_section)
        donation_layout.setContentsMargins(0, 0, 0, 0)
        
        current_language = LanguageManager.get_current_language()

        if current_language == "en":
            donation_content_container = QWidget()
            donation_content_layout = QHBoxLayout(donation_content_container)
            donation_content_layout.setContentsMargins(0, 0, 0, 0)
            
            coffee_icon_path = self.resource_path("resources/coffee_icon.png")
            coffee_icon = QPixmap(coffee_icon_path)
            coffee_emoji = QLabel()
            if not coffee_icon.isNull():
                coffee_icon = coffee_icon.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                coffee_emoji.setPixmap(coffee_icon)
            else:
                coffee_emoji.setText("☕")
            coffee_emoji.setFixedWidth(60)
            coffee_emoji.setStyleSheet("padding-left: 10px;")
            coffee_emoji.setAlignment(Qt.AlignCenter)

            links_container = QWidget()
            links_layout = QVBoxLayout(links_container)
            links_layout.setContentsMargins(0, 0, 0, 0)
            links_layout.setSpacing(UIScaleManager.get("donation_between_tworows", 30))
            
            row1_container = QWidget()
            row1_layout = QHBoxLayout(row1_container)
            row1_layout.setContentsMargins(0, 0, 0, 0)
            
            bmc_url = "https://buymeacoffee.com/ffamilist"
            qr_path_bmc = self.resource_path("resources/bmc_qr.png")
            bmc_label = QRLinkLabel("Buy Me a Coffee", bmc_url, qr_path=qr_path_bmc, qr_display_size=250, parent=self.settings_popup)
            bmc_label.setAlignment(Qt.AlignCenter)
            
            paypal_url = "https://paypal.me/ffamilist"
            paypal_label = QRLinkLabel("PayPal", paypal_url, qr_path="", qr_display_size=250, parent=self.settings_popup)
            paypal_label.setAlignment(Qt.AlignCenter)
            paypal_label.setToolTip("Click to go to PayPal")
            
            row1_layout.addWidget(bmc_label)
            row1_layout.addWidget(paypal_label)
            
            row2_container = QWidget()
            row2_layout = QHBoxLayout(row2_container)
            row2_layout.setContentsMargins(0, 0, 0, 0)
            
            qr_path_kakaopay = self.resource_path("resources/kakaopay_qr.png")
            kakaopay_label = QRLinkLabel("KakaoPay 🇰🇷", "", qr_path=qr_path_kakaopay, qr_display_size=400, parent=self.settings_popup)
            kakaopay_label.setAlignment(Qt.AlignCenter)
            
            qr_path_naverpay = self.resource_path("resources/naverpay_qr.png")
            naverpay_label = QRLinkLabel("NaverPay 🇰🇷", "", qr_path=qr_path_naverpay, qr_display_size=250, parent=self.settings_popup)
            naverpay_label.setAlignment(Qt.AlignCenter)
            
            row2_layout.addWidget(kakaopay_label)
            row2_layout.addWidget(naverpay_label)
            
            links_layout.addWidget(row1_container)
            links_layout.addWidget(row2_container)
            
            donation_content_layout.addWidget(coffee_emoji, 0, Qt.AlignVCenter)
            donation_content_layout.addWidget(links_container, 1)
            
            donation_layout.addWidget(donation_content_container)
        else: # "ko"
            ko_payment_container = QWidget()
            ko_payment_layout = QHBoxLayout(ko_payment_container)
            ko_payment_layout.setContentsMargins(0, 0, 0, 0)
            
            coffee_icon_path = self.resource_path("resources/coffee_icon.png")
            coffee_icon = QPixmap(coffee_icon_path)
            coffee_emoji = QLabel()
            if not coffee_icon.isNull():
                coffee_icon = coffee_icon.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                coffee_emoji.setPixmap(coffee_icon)
            else:
                coffee_emoji.setText("☕")
            coffee_emoji.setFixedWidth(60)
            coffee_emoji.setStyleSheet("padding-left: 10px;")
            coffee_emoji.setAlignment(Qt.AlignCenter)
            
            links_container = QWidget()
            links_layout = QVBoxLayout(links_container)
            links_layout.setContentsMargins(0, 0, 0, 0)
            links_layout.setSpacing(UIScaleManager.get("donation_between_tworows", 30))
            
            row1_container = QWidget()
            row1_layout = QHBoxLayout(row1_container)
            row1_layout.setContentsMargins(0, 0, 0, 0)
            
            qr_path_kakaopay_ko = self.resource_path("resources/kakaopay_qr.png")
            kakaopay_label = QRLinkLabel(LanguageManager.translate("카카오페이"), "", qr_path=qr_path_kakaopay_ko, qr_display_size=400, parent=self.settings_popup)
            kakaopay_label.setAlignment(Qt.AlignCenter)
            
            qr_path_naverpay_ko = self.resource_path("resources/naverpay_qr.png")
            naverpay_label = QRLinkLabel(LanguageManager.translate("네이버페이"), "", qr_path=qr_path_naverpay_ko, qr_display_size=250, parent=self.settings_popup)
            naverpay_label.setAlignment(Qt.AlignCenter)
            
            row1_layout.addWidget(kakaopay_label)
            row1_layout.addWidget(naverpay_label)
            
            row2_container = QWidget()
            row2_layout = QHBoxLayout(row2_container)
            row2_layout.setContentsMargins(0, 0, 0, 0)
            
            bmc_url_ko = "https://buymeacoffee.com/ffamilist"
            qr_path_bmc_ko = self.resource_path("resources/bmc_qr.png")
            bmc_label = QRLinkLabel("Buy Me a Coffee", bmc_url_ko, qr_path=qr_path_bmc_ko, qr_display_size=250, parent=self.settings_popup)
            bmc_label.setAlignment(Qt.AlignCenter)
            
            paypal_url_ko = "https://paypal.me/ffamilist"
            paypal_label = QRLinkLabel("PayPal", paypal_url_ko, qr_path="", qr_display_size=250, parent=self.settings_popup)
            paypal_label.setAlignment(Qt.AlignCenter)
            paypal_label.setToolTip("Click to go to PayPal")
            
            row2_layout.addWidget(bmc_label)
            row2_layout.addWidget(paypal_label)
            
            links_layout.addWidget(row1_container)
            links_layout.addWidget(row2_container)
            
            ko_payment_layout.addWidget(coffee_emoji, 0, Qt.AlignVCenter)
            ko_payment_layout.addWidget(links_container, 1)
            
            donation_layout.addWidget(ko_payment_container)

        return donation_section

    def show_shortcuts_popup(self):
        """단축키 안내 팝업창을 표시합니다."""
        if hasattr(self, 'shortcuts_info_popup') and self.shortcuts_info_popup.isVisible():
            self.shortcuts_info_popup.activateWindow()
            return

        self.shortcuts_info_popup = QDialog(self)
        self.shortcuts_info_popup.setWindowTitle(LanguageManager.translate("단축키")) # 새 번역 키
        
        # 다크 테마 적용 (기존 show_themed_message_box 또는 settings_popup 참조)
        apply_dark_title_bar(self.shortcuts_info_popup)
        palette = QPalette(); palette.setColor(QPalette.Window, QColor(ThemeManager.get_color('bg_primary')))
        self.shortcuts_info_popup.setPalette(palette); self.shortcuts_info_popup.setAutoFillBackground(True)

        layout = QVBoxLayout(self.shortcuts_info_popup)
        layout.setContentsMargins(20, 20, 20, 20)

        # 스크롤 가능한 텍스트 영역으로 변경 (내용이 길어지므로)
        text_browser = QTextBrowser() # QLabel 대신 QTextBrowser 사용
        text_browser.setReadOnly(True)
        text_browser.setOpenExternalLinks(False) # 이 팝업에는 링크가 없을 것이므로
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: transparent; /* 부모 위젯 배경색 사용 */
                color: {ThemeManager.get_color('text')};
                border: none; /* 테두리 없음 */
            }}
        """)
        html_content = self._build_shortcut_html() # 위에서 만든 함수 호출
        text_browser.setHtml(html_content)
        
        # 텍스트 브라우저의 최소/권장 크기 설정 (내용에 따라 조절)
        text_browser.setMinimumHeight(1000)
        text_browser.setMinimumWidth(700)

        layout.addWidget(text_browser)

        close_button = QPushButton(LanguageManager.translate("닫기"))
        # ... (닫기 버튼 스타일 설정 - 기존 설정 팝업의 버튼 스타일 재사용 가능) ...
        button_style = f"""
            QPushButton {{
                background-color: {ThemeManager.get_color('bg_secondary')}; color: {ThemeManager.get_color('text')};
                border: none; padding: 8px 16px; border-radius: 4px; min-width: 80px;
            }}
            QPushButton:hover {{ background-color: {ThemeManager.get_color('accent_hover')}; }}
            QPushButton:pressed {{ background-color: {ThemeManager.get_color('accent_pressed')}; }}
        """
        close_button.setStyleSheet(button_style)
        close_button.clicked.connect(self.shortcuts_info_popup.accept)
        
        button_layout = QHBoxLayout() # 버튼 중앙 정렬용
        button_layout.addStretch(1)
        button_layout.addWidget(close_button)
        button_layout.addStretch(1)
        layout.addLayout(button_layout)

        self.shortcuts_info_popup.exec_()



    def create_translated_info_text(self):
        """현재 언어에 맞게 번역된 정보 텍스트를 생성하여 반환"""
        version_margin = UIScaleManager.get("info_version_margin", 40)
        paragraph_margin = UIScaleManager.get("info_paragraph_margin", 30) 
        bottom_margin = UIScaleManager.get("info_bottom_margin", 30)
        accent_color = "#01CA47"

        info_text = f"""
        <h2 style="color: {accent_color};">PhotoSort</h2>
        <p style="margin-bottom: {version_margin}px;">Version: 25.07.15</p>
        <p>{LanguageManager.translate("개인적인 용도로 자유롭게 사용할 수 있는 무료 소프트웨어입니다.")}</p>
        <p>{LanguageManager.translate("상업적 이용은 허용되지 않습니다.")}</p>
        <p style="margin-bottom: {paragraph_margin}px;">{LanguageManager.translate("이 프로그램이 마음에 드신다면, 커피 한 잔으로 응원해 주세요.")}</p>
        <p style="margin-bottom: {bottom_margin}px;">Copyright © 2025 newboon</p>
        <p>
            {LanguageManager.translate("피드백 및 업데이트 확인:")}
            <a href="https://medium.com/@ffamilist/photosort-simple-sorting-for-busy-dads-e9a4f45b03dc" style="color: {accent_color}; text-decoration: none;">[EN]</a>&nbsp;
            <a href="https://blog.naver.com/ffamilist/223844618813" style="color: {accent_color}; text-decoration: none;">[KR]</a>&nbsp;
            <a href="https://github.com/newboon/PhotoSort/releases" style="color: {accent_color}; text-decoration: none;">[GitHub]</a>
        </p>
        """
        return info_text

    def show_licenses_popup(self):
        """오픈소스 라이선스 정보를 표시하는 팝업"""
        # 다이얼로그 생성
        licenses_popup = QDialog(self)
        licenses_popup.setWindowTitle("Open Source Licenses Info")
        licenses_popup.setMinimumSize(950, 950)
        
        # Windows용 다크 테마 제목 표시줄 설정
        apply_dark_title_bar(licenses_popup)
        
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

        <h2>pillow-heif</h2>
        <ul>
        <li><strong>License</strong>: Apache-2.0 (Python wrapper), LGPL-3.0 (libheif core)</li>
        <li><strong>Website</strong>: <a href="https://github.com/bigcat88/pillow_heif">https://github.com/bigcat88/pillow_heif</a></li>
        <li>A Pillow-plugin for HEIF/HEIC support, powered by libheif.</li>
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
                padding: {UIScaleManager.get("combobox_padding")}px;
                border-radius: 1px;
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
    
    # def generate_combobox_style(self):
    #     """현재 테마에 맞는 콤보박스 스타일 생성"""
    #     return f"""
    #         QComboBox {{
    #             background-color: {ThemeManager.get_color('bg_primary')};
    #             color: {ThemeManager.get_color('text')};
    #             border: 1px solid {ThemeManager.get_color('border')};
    #             border-radius: 1px;
    #             padding: {UIScaleManager.get("combobox_padding")}px;
    #         }}
    #         QComboBox:hover {{
    #             background-color: #555555;
    #         }}
    #         QComboBox QAbstractItemView {{
    #             background-color: {ThemeManager.get_color('bg_secondary')};
    #             color: {ThemeManager.get_color('text')};
    #             selection-background-color: #505050;
    #             selection-color: {ThemeManager.get_color('text')};
    #         }}
    #     """

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
    
    def adjust_layout(self):
        """(비율 기반) 이미지 영역 3:2 비율 유지 및 좌우 패널 크기 동적 조절"""
        window_width = self.width()
        window_height = self.height()
        
        # 썸네일 패널의 현재 가시성 상태를 직접 확인
        thumbnail_visible = self.thumbnail_panel.isVisible()
        
        # 스플리터 위젯 재구성은 필요할 때만 호출 (예: on_grid_changed, _apply_panel_position)
        # 여기서 직접 호출하지 않음
        
        # 1. 패널들의 최소 너비와 비율 정의
        control_min_width = UIScaleManager.get("control_panel_min_width")
        thumbnail_min_width = UIScaleManager.get("thumbnail_panel_min_width")
        
        control_ratio = 319.0  # 부동소수점 계산을 위해 .0 추가
        thumbnail_ratio = 240.0
        
        # 2. 캔버스 크기 우선 결정
        side_panels_min_width = control_min_width + (thumbnail_min_width if thumbnail_visible else 0)
        available_for_canvas_width = window_width - side_panels_min_width
        
        canvas_ideal_width = window_height * 1.5
        canvas_width = max(100, min(canvas_ideal_width, available_for_canvas_width))

        # 3. 남은 공간을 컨트롤/썸네일 패널에 비율대로 배분
        remaining_width = window_width - canvas_width
        
        sizes = []
        if thumbnail_visible:
            total_ratio = control_ratio + thumbnail_ratio
            control_width = remaining_width * (control_ratio / total_ratio)
            thumbnail_width = remaining_width * (thumbnail_ratio / total_ratio)
            
            if control_width < control_min_width:
                control_width = control_min_width
                thumbnail_width = remaining_width - control_width
            elif thumbnail_width < thumbnail_min_width:
                thumbnail_width = thumbnail_min_width
                control_width = remaining_width - thumbnail_width
            
            sizes = [int(control_width), int(canvas_width), int(thumbnail_width)]
        else:
            control_width = remaining_width
            sizes = [int(control_width), int(canvas_width)]

        # 컨트롤 패널 위치에 따라 순서 조정
        control_on_right = getattr(self, 'control_panel_on_right', False)
        if control_on_right:
            # 3단: [썸네일, 이미지, 컨트롤] -> [컨트롤, 이미지, 썸네일]
            # 2단: [이미지, 컨트롤] -> [컨트롤, 이미지]
            sizes.reverse()

        # 4. 스플리터에 최종 크기 적용
        # 스플리터의 위젯 수와 sizes 리스트의 길이가 맞는지 확인
        if self.splitter.count() == len(sizes):
            self.splitter.setSizes(sizes)
        else:
            # 위젯 수가 맞지 않으면 재구성 후 다시 adjust_layout 호출
            logging.warning("스플리터 위젯 수와 크기 목록 불일치. 재구성합니다.")
            self._reorganize_splitter_widgets(thumbnail_visible, control_on_right)
            # 재구성 후에는 QTimer를 통해 adjust_layout을 다시 호출하여 안정성 확보
            QTimer.singleShot(0, self.adjust_layout)
            return # 현재 adjust_layout 실행은 중단
        
        # 이미지가 로드된 경우 이미지 크기도 조정
        if hasattr(self, 'current_image_index') and self.current_image_index >= 0 and self.grid_mode == "Off":
            self.apply_zoom_to_image()


    def _need_splitter_reorganization(self):
        """스플리터 재구성이 필요한지 확인"""
        try:
            # 위젯 순서가 올바른지 확인
            control_on_right = getattr(self, 'control_panel_on_right', False)
            thumbnail_visible = (self.grid_mode == "Off")
            
            if self.splitter.count() == 3 and thumbnail_visible:
                # 3패널일 때 순서 확인
                if control_on_right:
                    # 예상 순서: [썸네일] [이미지] [컨트롤]
                    return (self.splitter.widget(0) != self.thumbnail_panel or
                            self.splitter.widget(1) != self.image_panel or
                            self.splitter.widget(2) != self.control_panel)
                else:
                    # 예상 순서: [컨트롤] [이미지] [썸네일]
                    return (self.splitter.widget(0) != self.control_panel or
                            self.splitter.widget(1) != self.image_panel or
                            self.splitter.widget(2) != self.thumbnail_panel)
            elif self.splitter.count() == 2 and not thumbnail_visible:
                # 2패널일 때 순서 확인
                if control_on_right:
                    # 예상 순서: [이미지] [컨트롤]
                    return (self.splitter.widget(0) != self.image_panel or
                            self.splitter.widget(1) != self.control_panel)
                else:
                    # 예상 순서: [컨트롤] [이미지]
                    return (self.splitter.widget(0) != self.control_panel or
                            self.splitter.widget(1) != self.image_panel)
            
            return True  # 패널 수가 맞지 않으면 재구성 필요
        except:
            return True  # 오류 발생 시 재구성

    def _reorganize_splitter_widgets(self, thumbnail_visible, control_on_right):
        """스플리터 위젯 재구성"""
        # 모든 위젯을 스플리터에서 제거
        while self.splitter.count() > 0:
            widget = self.splitter.widget(0)
            if widget:
                widget.setParent(None)
        
        # 썸네일 패널 표시/숨김 설정
        if thumbnail_visible:
            self.thumbnail_panel.show()
        else:
            self.thumbnail_panel.hide()
        
        # 위젯을 올바른 순서로 다시 추가
        if thumbnail_visible:
            # 3패널 구조
            if control_on_right:
                # [썸네일] [이미지] [컨트롤]
                self.splitter.addWidget(self.thumbnail_panel)
                self.splitter.addWidget(self.image_panel)
                self.splitter.addWidget(self.control_panel)
            else:
                # [컨트롤] [이미지] [썸네일]
                self.splitter.addWidget(self.control_panel)
                self.splitter.addWidget(self.image_panel)
                self.splitter.addWidget(self.thumbnail_panel)
        else:
            # 2패널 구조
            if control_on_right:
                # [이미지] [컨트롤]
                self.splitter.addWidget(self.image_panel)
                self.splitter.addWidget(self.control_panel)
            else:
                # [컨트롤] [이미지]
                self.splitter.addWidget(self.control_panel)
                self.splitter.addWidget(self.image_panel)
    
    def resizeEvent(self, event):
            """창 크기 변경 이벤트 처리"""
            super().resizeEvent(event)
            self.adjust_layout()
            self.update_minimap_position()
            
            # 비교 모드 닫기 버튼 위치 업데이트
            if self.compare_mode_active and self.close_compare_button.isVisible():
                padding = 10
                btn_size = self.close_compare_button.width()
                # B 캔버스(scroll_area_B)의 우측 상단에 위치
                new_x = self.scroll_area_B.width() - btn_size - padding
                new_y = padding
                self.close_compare_button.move(new_x, new_y)
    
    def load_jpg_folder(self):
        """JPG 등 이미지 파일이 있는 폴더 선택 및 백그라운드 로드 시작"""
        folder_path = QFileDialog.getExistingDirectory(
            self, LanguageManager.translate("이미지 파일이 있는 폴더 선택"), "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if folder_path:
            logging.info(f"이미지(JPG) 폴더 선택: {folder_path}")
            self.clear_raw_folder()
            self.start_background_loading(
                jpg_folder_path=folder_path, 
                raw_folder_path=None, 
                mode='jpg_only', 
                raw_file_list=None
            )

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


    def get_datetime_from_file_fast(self, file_path):
        """파일에서 촬영 시간을 빠르게 추출 (캐시 우선 사용)"""
        file_key = str(file_path)
        
        # 1. 캐시에서 먼저 확인
        if file_key in self.exif_cache:
            cached_data = self.exif_cache[file_key]
            if 'exif_datetime' in cached_data:
                cached_value = cached_data['exif_datetime']
                # 캐시된 값이 문자열이면 datetime 객체로 변환
                if isinstance(cached_value, str):
                    try:
                        return datetime.strptime(cached_value, '%Y:%m:%d %H:%M:%S')
                    except:
                        pass
                elif isinstance(cached_value, datetime):
                    return cached_value
        
        # 2. RAW 파일의 경우 rawpy로 빠른 메타데이터 추출
        if file_path.suffix.lower() in self.raw_extensions:
            try:
                import rawpy
                with rawpy.imread(str(file_path)) as raw:
                    # rawpy는 exiftool보다 훨씬 빠름
                    if hasattr(raw, 'metadata') and 'DateTimeOriginal' in raw.metadata:
                        datetime_str = raw.metadata['DateTimeOriginal']
                        return datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
            except:
                pass
        
        # 3. JPG/HEIC의 경우 piexif 사용 (이미 구현됨)
        try:
            import piexif
            exif_data = piexif.load(str(file_path))
            if piexif.ExifIFD.DateTimeOriginal in exif_data['Exif']:
                datetime_str = exif_data['Exif'][piexif.ExifIFD.DateTimeOriginal].decode()
                return datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
        except:
            pass
        
        # 4. 마지막 수단: 파일 수정 시간
        return datetime.fromtimestamp(file_path.stat().st_mtime)

    def load_images_from_folder(self, folder_path):
        """
        폴더에서 이미지 로드를 시작하는 통합 트리거 함수.
        실제 로딩은 백그라운드에서 수행됩니다.
        """
        if not folder_path:
            return False
        
        self.start_background_loading(
            jpg_folder_path=folder_path, 
            raw_folder_path=self.raw_folder, 
            mode='jpg_with_raw', 
            raw_file_list=None
        )
        return True

    
    def start_background_loading(self, jpg_folder_path, raw_folder_path, mode, raw_file_list=None):
        """백그라운드 로딩을 시작하고 로딩창을 표시합니다."""
        self._reset_workspace()
        self.loading_progress_dialog = QProgressDialog(
            LanguageManager.translate("폴더를 읽는 중입니다..."),
            "", 0, 0, self
        )
        self.loading_progress_dialog.setCancelButton(None)
        self.loading_progress_dialog.setWindowModality(Qt.WindowModal)
        self.loading_progress_dialog.setMinimumDuration(0)
        apply_dark_title_bar(self.loading_progress_dialog)
        self.loading_progress_dialog.setStyleSheet(f"""
            QProgressDialog {{
                background-color: {ThemeManager.get_color('bg_primary')};
                color: {ThemeManager.get_color('text')};
            }}
            QProgressBar {{
                text-align: center;
            }}
        """)
        
        # [추가] 대화상자를 메인 윈도우 중앙에 위치시키는 로직
        parent_geometry = self.geometry()
        self.loading_progress_dialog.adjustSize()
        dialog_size = self.loading_progress_dialog.size()
        new_x = parent_geometry.x() + (parent_geometry.width() - dialog_size.width()) // 2
        new_y = parent_geometry.y() + (parent_geometry.height() - dialog_size.height()) // 2
        self.loading_progress_dialog.move(new_x, new_y)

        self.loading_progress_dialog.show()
        # 이 방식은 복잡한 Python 타입을 더 안정적으로 처리합니다.
        jpg_path_str = jpg_folder_path if jpg_folder_path is not None else ""
        raw_path_str = raw_folder_path if raw_folder_path is not None else ""
        self.folder_loader_worker.startProcessing.emit(
            jpg_path_str,
            raw_path_str,
            mode,
            raw_file_list if raw_file_list is not None else []
        )

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

    def _apply_zoom_to_canvas(self, canvas_id):
        """지정된 캔버스(A 또는 B)에 현재 줌 모드와 뷰포트를 적용합니다."""
        # 1. canvas_id에 따라 사용할 위젯과 데이터 소스를 결정합니다.
        if canvas_id == 'A':
            scroll_area = self.scroll_area
            image_label = self.image_label
            image_container = self.image_container
            original_pixmap = self.original_pixmap
        elif canvas_id == 'B':
            scroll_area = self.scroll_area_B
            image_label = self.image_label_B
            image_container = self.image_container_B
            original_pixmap = self.original_pixmap_B
        else:
            return

        # 2. 원본 이미지가 없으면 캔버스를 비우고 종료합니다.
        if not original_pixmap or original_pixmap.isNull():
            image_label.clear()
            image_label.setText(LanguageManager.translate("비교할 이미지를 썸네일 패널에서 이곳으로 드래그하세요.") if canvas_id == 'B' else "")
            return
            
        # 3. 기존 apply_zoom_to_image의 로직을 그대로 가져와서,
        #    self.xxx 대신 지역 변수(scroll_area, image_label 등)를 사용하도록 수정합니다.
        view_width = scroll_area.width()
        view_height = scroll_area.height()
        img_width_orig = original_pixmap.width()
        img_height_orig = original_pixmap.height()
        
        # Fit 모드 처리
        if self.zoom_mode == "Fit":
            # Fit 모드에서는 각 캔버스가 자신의 크기에 맞게 이미지를 조정합니다.
            scaled_pixmap = self.high_quality_resize_to_fit(original_pixmap, scroll_area)
            image_label.setPixmap(scaled_pixmap)
            image_label.setGeometry(
                (view_width - scaled_pixmap.width()) // 2, (view_height - scaled_pixmap.height()) // 2,
                scaled_pixmap.width(), scaled_pixmap.height()
            )
            image_container.setMinimumSize(1, 1)
            return # Fit 모드는 여기서 종료

        # Zoom 100% 또는 Spin 모드 처리
        if self.zoom_mode == "100%":
            new_zoom_factor = 1.0
        elif self.zoom_mode == "Spin":
            new_zoom_factor = self.zoom_spin_value
        else:
            return
            
        new_zoomed_width = img_width_orig * new_zoom_factor
        new_zoomed_height = img_height_orig * new_zoom_factor

        # B 캔버스는 항상 A 캔버스의 뷰포트를 따라가므로, 뷰포트 계산은 A 캔버스에서만 수행합니다.
        if canvas_id == 'A':
            final_target_rel_center = QPointF(0.5, 0.5)
            trigger = self.zoom_change_trigger
            image_orientation_type = self.current_image_orientation
            # ... (기존 apply_zoom_to_image의 뷰포트 계산 로직 전체) ...
            if trigger == "double_click":
                scaled_fit_pixmap = self.high_quality_resize_to_fit(original_pixmap, scroll_area)
                fit_img_rect = QRect((view_width - scaled_fit_pixmap.width()) // 2, (view_height - scaled_fit_pixmap.height()) // 2, scaled_fit_pixmap.width(), scaled_fit_pixmap.height())
                if fit_img_rect.width() > 0 and fit_img_rect.height() > 0:
                    rel_x = (self.double_click_pos.x() - fit_img_rect.x()) / fit_img_rect.width()
                    rel_y = (self.double_click_pos.y() - fit_img_rect.y()) / fit_img_rect.height()
                    final_target_rel_center = QPointF(max(0.0, min(1.0, rel_x)), max(0.0, min(1.0, rel_y)))
                self.current_active_rel_center = final_target_rel_center
                self.current_active_zoom_level = "100%"
                self._save_orientation_viewport_focus(image_orientation_type, self.current_active_rel_center, "100%")
            elif trigger in ["space_key_to_zoom", "radio_button", "photo_change_carry_over_focus", "photo_change_central_focus"]:
                 final_target_rel_center = self.current_active_rel_center
                 self._save_orientation_viewport_focus(image_orientation_type, final_target_rel_center, self.current_active_zoom_level)
            else:
                final_target_rel_center, new_active_zoom = self._get_orientation_viewport_focus(image_orientation_type, self.zoom_mode)
                self.current_active_rel_center = final_target_rel_center
                self.current_active_zoom_level = new_active_zoom
                self._save_orientation_viewport_focus(image_orientation_type, self.current_active_rel_center, self.current_active_zoom_level)

            target_abs_x = final_target_rel_center.x() * new_zoomed_width
            target_abs_y = final_target_rel_center.y() * new_zoomed_height
            new_x = view_width / 2 - target_abs_x
            new_y = view_height / 2 - target_abs_y
            
            if new_zoomed_width <= view_width: new_x = (view_width - new_zoomed_width) // 2
            else: new_x = min(0, max(view_width - new_zoomed_width, new_x))
            if new_zoomed_height <= view_height: new_y = (view_height - new_zoomed_height) // 2
            else: new_y = min(0, max(view_height - new_zoomed_height, new_y))

            # 계산된 위치를 image_label에 적용
            if self.zoom_mode == "100%":
                image_label.setPixmap(original_pixmap)
            else: # Spin 모드
                scaled_pixmap = original_pixmap.scaled(
                    int(new_zoomed_width), int(new_zoomed_height), 
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                image_label.setPixmap(scaled_pixmap)
            image_label.setGeometry(int(new_x), int(new_y), int(new_zoomed_width), int(new_zoomed_height))
            image_container.setMinimumSize(int(new_zoomed_width), int(new_zoomed_height))
            self.zoom_change_trigger = None
        
        # B 캔버스는 A 캔버스와 동일한 줌/패닝을 적용받습니다.
        elif canvas_id == 'B':
            # A 캔버스의 현재 뷰포트 정보를 가져옵니다.
            pos_A = self.image_label.pos()
            
            # B 캔버스에 동일한 줌을 적용합니다.
            if self.zoom_mode == "100%":
                image_label.setPixmap(original_pixmap)
            else: # Spin 모드
                scaled_pixmap = original_pixmap.scaled(
                    int(new_zoomed_width), int(new_zoomed_height), 
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                image_label.setPixmap(scaled_pixmap)
            
            # A 캔버스와 동일한 위치 및 크기로 설정합니다.
            image_label.setGeometry(pos_A.x(), pos_A.y(), int(new_zoomed_width), int(new_zoomed_height))
            image_container.setMinimumSize(int(new_zoomed_width), int(new_zoomed_height))

    def apply_zoom_to_image(self):
        """A 캔버스에 줌을 적용하고, 비교 모드이면 B 캔버스도 동기화하는 래퍼 함수."""
        if self.grid_mode != "Off": return
        
        # 1. A 캔버스에 줌/뷰포트 적용
        self._apply_zoom_to_canvas('A')
        
        # 2. 비교 모드가 활성화되어 있으면 B 캔버스도 업데이트
        if self.compare_mode_active:
            self._apply_zoom_to_canvas('B')
            # 스크롤바 위치도 동기화
            self._sync_viewports()
        
        # 3. 미니맵 업데이트 (A 캔버스 기준)
        if self.minimap_toggle.isChecked():
            self.toggle_minimap(True)

    def high_quality_resize_to_fit(self, pixmap, target_widget):
            """고품질 이미지 리사이징 (Fit 모드용) - 메모리 최적화"""
            if not pixmap or not target_widget:
                return pixmap
                
            # 이미지 패널 크기 가져오기
            panel_width = target_widget.width()
            panel_height = target_widget.height()

            if panel_width <= 0 or panel_height <= 0:
                return pixmap
                
            # 크기가 같다면 캐시 확인 (캐시 키는 이제 튜플 (너비, 높이) 사용)
            current_size = (panel_width, panel_height)
            # Fit 캐시는 A 패널 전용으로 유지하는 것이 간단합니다. B는 A의 결과를 따르기 때문입니다.
            if target_widget is self.scroll_area and self.last_fit_size == current_size and current_size in self.fit_pixmap_cache:
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
                # 캐시 업데이트 (A 패널에 대해서만)
                if target_widget is self.scroll_area:
                    self.fit_pixmap_cache[current_size] = result_pixmap
                    self.last_fit_size = current_size
                return result_pixmap
                
            # 이미지가 패널보다 작으면 원본 사용
            return pixmap
    
    def image_mouse_press_event(self, event):
        """이미지 영역 마우스 클릭 이벤트 처리"""
        # === 우클릭 컨텍스트 메뉴 처리 ===
        if event.button() == Qt.RightButton and self.image_files:
            # 이미지가 로드된 상태에서 우클릭 시 컨텍스트 메뉴 표시
            context_menu = self.create_context_menu(event.position().toPoint())
            if context_menu:
                context_menu.exec_(self.image_container.mapToGlobal(event.position().toPoint()))
            return
        
        # === 빈 캔버스 클릭 시 폴더 선택 기능 ===
        if event.button() == Qt.LeftButton and not self.image_files:
            # 아무 이미지도 로드되지 않은 상태에서 캔버스 클릭 시 폴더 선택
            self.open_folder_dialog_for_canvas()
            return
        
        # === Fit 모드에서 드래그 앤 드롭 시작 준비 ===
        if (event.button() == Qt.LeftButton and 
            self.zoom_mode == "Fit" and 
            self.image_files and 
            0 <= self.current_image_index < len(self.image_files)):
            
            # 드래그 시작 준비
            self.drag_start_pos = event.position().toPoint()
            self.is_potential_drag = True
            logging.debug(f"드래그 시작 준비: {self.drag_start_pos}")
            return
        
        # === 기존 패닝 기능 ===
        # 100% 또는 Spin 모드에서만 패닝 활성화
        if self.zoom_mode in ["100%", "Spin"]:
            if event.button() == Qt.LeftButton:
                # 패닝 상태 활성화
                self.panning = True
                self.pan_start_pos = event.position().toPoint()
                self.image_start_pos = self.image_label.pos()
                self.setCursor(Qt.ClosedHandCursor)
    
    def open_folder_dialog_for_canvas(self):
        """캔버스 클릭 시 폴더 선택 다이얼로그 열기"""
        try:
            folder_path = QFileDialog.getExistingDirectory(
                self, 
                LanguageManager.translate("이미지 파일이 있는 폴더 선택"), 
                "",
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )
            
            if folder_path:
                # 선택된 폴더에 대해 캔버스 폴더 드롭 로직 적용
                success = self._handle_canvas_folder_drop(folder_path)
                if success:
                    logging.info(f"캔버스 클릭으로 폴더 로드 성공: {folder_path}")
                else:
                    logging.warning(f"캔버스 클릭으로 폴더 로드 실패: {folder_path}")
            else:
                logging.debug("캔버스 클릭 폴더 선택 취소됨")
                
        except Exception as e:
            logging.error(f"캔버스 클릭 폴더 선택 오류: {e}")
            self.show_themed_message_box(
                QMessageBox.Critical,
                LanguageManager.translate("오류"),
                LanguageManager.translate("폴더 선택 중 오류가 발생했습니다.")
            )
    
    def start_image_drag(self, dragged_grid_index=None, canvas=None):
        """이미지 드래그 시작 (A, B 캔버스 및 그리드 지원)"""
        try:
            if not self.image_files:
                logging.warning("드래그 시작 실패: 유효한 이미지가 없음")
                return

            drag_image_path = None
            mime_text_payload = ""
            drag_pixmap_source = None

            if self.grid_mode != "Off":
                # Grid 모드에서 드래그 시작
                drag_image_index = -1
                if dragged_grid_index is not None:
                    drag_image_index = self.grid_page_start_index + dragged_grid_index
                else: # Fallback
                    drag_image_index = self.grid_page_start_index + self.current_grid_index
                
                if not (0 <= drag_image_index < len(self.image_files)):
                    logging.warning("드래그 시작 실패: 유효하지 않은 그리드 인덱스")
                    return
                
                drag_image_path = self.image_files[drag_image_index]
                drag_pixmap_source = self.image_loader.cache.get(str(drag_image_path))

                # 다중 선택 여부 확인
                if (hasattr(self, 'selected_grid_indices') and self.selected_grid_indices and 
                    len(self.selected_grid_indices) > 1 and 
                    (dragged_grid_index in self.selected_grid_indices)):
                    # 다중 선택된 이미지를 드래그하는 경우
                    selected_global_indices = sorted([self.grid_page_start_index + i for i in self.selected_grid_indices])
                    indices_str = ",".join(map(str, selected_global_indices))
                    mime_text_payload = f"image_drag:grid:{indices_str}"
                    logging.info(f"다중 이미지 드래그 시작: {len(selected_global_indices)}개 이미지")
                else:
                    # 단일 이미지 드래그
                    mime_text_payload = f"image_drag:grid:{drag_image_index}"

            else: # canvas == 'A' 또는 기본값 (Grid Off 모드)
                if not (0 <= self.current_image_index < len(self.image_files)):
                    return
                drag_image_path = self.image_files[self.current_image_index]
                drag_pixmap_source = self.original_pixmap
                mime_text_payload = f"image_drag:off:{self.current_image_index}"

            if not drag_image_path or not mime_text_payload:
                logging.warning("드래그할 이미지를 결정할 수 없습니다.")
                return

            # 2. QDrag 객체 생성 및 데이터 설정
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(mime_text_payload)
            drag.setMimeData(mime_data)
            
            # 3. 드래그 커서 이미지 설정
            if drag_pixmap_source and not drag_pixmap_source.isNull():
                thumbnail = drag_pixmap_source.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                drag.setPixmap(thumbnail)
                drag.setHotSpot(QPoint(32, 32))

            logging.info(f"이미지 드래그 시작: {drag_image_path.name} (from: {mime_text_payload})")
            
            # 4. 드래그 실행
            drag.exec_(Qt.MoveAction)
            
        except Exception as e:
            logging.error(f"이미지 드래그 시작 오류: {e}")

    def image_mouse_move_event(self, event):
        """이미지 영역 마우스 이동 이벤트 처리"""
        # === Fit 모드에서 드래그 시작 감지 ===
        if (self.is_potential_drag and 
            self.zoom_mode == "Fit" and 
            self.image_files and 
            0 <= self.current_image_index < len(self.image_files)):
            
            current_pos = event.position().toPoint()
            move_distance = (current_pos - self.drag_start_pos).manhattanLength()
            
            if move_distance > self.drag_threshold:
                # 드래그 시작
                self.start_image_drag()
                self.is_potential_drag = False
                return
        
        # === 기존 패닝 기능 ===
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
            
            # 이미지 크기 가져오기 - 키보드 이동과 동일한 로직 적용
            if self.zoom_mode == "100%":
                img_width = self.original_pixmap.width()
                img_height = self.original_pixmap.height()
            else:  # Spin 모드 - zoom_spin_value 사용으로 수정
                img_width = self.original_pixmap.width() * self.zoom_spin_value
                img_height = self.original_pixmap.height() * self.zoom_spin_value
            
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
            self._sync_viewports()

            # 미니맵 뷰박스 업데이트 - 패닝 중에는 미니맵 업데이트 빈도 낮추기
            if current_time - getattr(self, 'last_minimap_update_time', 0) > 50:  # 20fps로 제한
                self.last_minimap_update_time = current_time
                if self.minimap_visible and self.minimap_widget.isVisible():
                    self.update_minimap()
    
    def image_mouse_release_event(self, event: QMouseEvent): # QMouseEvent 타입 명시
        # === 드래그 상태 초기화 ===
        if self.is_potential_drag:
            self.is_potential_drag = False
            logging.debug("드래그 시작 준비 상태 해제")
        
        # === 기존 패닝 기능 ===
        if event.button() == Qt.LeftButton and self.panning:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
            
            # --- 수정: 올바른 인자 전달 ---
            if self.grid_mode == "Off" and self.zoom_mode in ["100%", "Spin"] and \
               self.original_pixmap and 0 <= self.current_image_index < len(self.image_files):
                current_rel_center = self._get_current_view_relative_center() # 현재 뷰 중심 계산
                current_zoom_level = self.zoom_mode
                
                # 현재 활성 포커스도 업데이트
                self.current_active_rel_center = current_rel_center
                self.current_active_zoom_level = current_zoom_level
                
                # 방향별 포커스 저장 (파일 경로가 아닌 orientation 전달)
                self._save_orientation_viewport_focus(self.current_image_orientation, current_rel_center, current_zoom_level)
            # --- 수정 끝 ---
            
            if self.minimap_visible and self.minimap_widget.isVisible():
                self.update_minimap()
    
    def create_context_menu(self, mouse_pos):
        """컨텍스트 메뉴 생성 - folder_count에 따라 동적 생성"""
        # 이미지가 없거나 폴더가 없으면 메뉴 표시 안 함
        if not self.image_files or not self.target_folders:
            return None
            
        # 컨텍스트 메뉴 생성
        context_menu = QMenu(self)
        
        # 테마 스타일 적용
        context_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {ThemeManager.get_color('bg_secondary')};
                color: {ThemeManager.get_color('text')};
                border: 1px solid {ThemeManager.get_color('border')};
                padding: 2px;
            }}
            QMenu::item {{
                padding: 8px 16px;
                background-color: transparent;
            }}
            QMenu::item:selected {{
                background-color: {ThemeManager.get_color('accent')};
                color: {ThemeManager.get_color('text')};
            }}
        """)
        
        # folder_count에 따라 메뉴 항목 생성
        for i in range(self.folder_count):
            # 폴더가 설정되지 않았으면 비활성화
            folder_path = self.target_folders[i] if i < len(self.target_folders) else ""
            
            # 메뉴 항목 텍스트 생성 - 실제 폴더 이름 포함
            if folder_path and os.path.isdir(folder_path):
                folder_name = Path(folder_path).name
                menu_text = LanguageManager.translate("이동 - 폴더 {0} [{1}]").format(i + 1, folder_name)
            else:
                # 폴더가 설정되지 않았거나 유효하지 않은 경우 기존 형식 사용
                menu_text = LanguageManager.translate("이동 - 폴더 {0}").format(i + 1)
            
            # 메뉴 액션 생성
            action = QAction(menu_text, self)
            action.triggered.connect(lambda checked, idx=i: self.move_to_folder_from_context(idx))
            
            # 폴더가 설정되지 않았거나 유효하지 않으면 비활성화
            if not folder_path or not os.path.isdir(folder_path):
                action.setEnabled(False)
            
            context_menu.addAction(action)
        
        return context_menu
    
    def move_to_folder_from_context(self, folder_index):
        """컨텍스트 메뉴에서 폴더 이동 처리"""
        if self.grid_mode == "Off":
            # Grid Off 모드: 현재 이미지 이동
            if 0 <= self.current_image_index < len(self.image_files):
                logging.info(f"컨텍스트 메뉴에서 이미지 이동 (Grid Off): 폴더 {folder_index + 1}")
                self.move_current_image_to_folder(folder_index)
        else:
            # Grid On 모드: 선택된 이미지들 이동
            logging.info(f"컨텍스트 메뉴에서 이미지 이동 (Grid On): 폴더 {folder_index + 1}")
            self.move_grid_image(folder_index)
    
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
            if self.match_raw_files(folder_path): # match_raw_files가 성공 여부 반환하도록 수정 필요
                self.save_state() # <<< 저장

    def load_raw_only_folder(self):
        """ RAW 파일만 로드하는 기능, 첫 파일 분석 및 사용자 선택 요청 """
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
                if self.session_management_popup and self.session_management_popup.isVisible():
                    self.session_management_popup.update_all_button_states()                
                return
            
            # --- 1. 첫 번째 RAW 파일 분석 ---
            first_raw_file_path_obj = unique_raw_files[0]
            first_raw_file_path_str = str(first_raw_file_path_obj)
            logging.info(f"첫 번째 RAW 파일 분석 시작: {first_raw_file_path_obj.name}")

            is_raw_compatible = False
            camera_model_name = LanguageManager.translate("알 수 없는 카메라") # 기본값
            original_resolution_str = "-"
            preview_resolution_str = "-"
            
            # exiftool을 사용해야 할 수도 있으므로 미리 경로 확보
            exiftool_path = self.get_exiftool_path() # 기존 get_exiftool_path() 사용
            exiftool_available = Path(exiftool_path).exists() and Path(exiftool_path).is_file()


            # 1.1. {RAW 호환 여부} 및 {원본 해상도 (rawpy 시도)}, {카메라 모델명 (rawpy 시도)}
            rawpy_exif_data = {} # rawpy에서 얻은 부분적 EXIF 저장용
            try:
                with rawpy.imread(first_raw_file_path_str) as raw:
                    is_raw_compatible = True
                    original_width = raw.sizes.width # postprocess 후 크기 (raw_width는 센서 크기)
                    original_height = raw.sizes.height
                    if original_width > 0 and original_height > 0 :
                        original_resolution_str = f"{original_width}x{original_height}"
                    
                    if hasattr(raw, 'camera_manufacturer') and raw.camera_manufacturer and \
                    hasattr(raw, 'model') and raw.model:
                        camera_model_name = f"{raw.camera_manufacturer.strip()} {raw.model.strip()}"
                    elif hasattr(raw, 'model') and raw.model: # 모델명만 있는 경우
                        camera_model_name = raw.model.strip()
                    
                    # 임시로 rawpy에서 일부 EXIF 정보 추출 (카메라 모델 등)
                    rawpy_exif_data["exif_make"] = raw.camera_manufacturer.strip() if hasattr(raw, 'camera_manufacturer') and raw.camera_manufacturer else ""
                    rawpy_exif_data["exif_model"] = raw.model.strip() if hasattr(raw, 'model') and raw.model else ""

            except Exception as e_rawpy:
                is_raw_compatible = False # rawpy로 기본 정보 읽기 실패 시 호환 안됨으로 간주
                logging.warning(f"rawpy로 첫 파일({first_raw_file_path_obj.name}) 분석 중 오류 (호환 안됨 가능성): {e_rawpy}")

            # 1.2. {카메라 모델명 (ExifTool 시도 - rawpy 실패 시 또는 보강)} 및 {원본 해상도 (ExifTool 시도 - rawpy 실패 시)}
            if (not camera_model_name or camera_model_name == LanguageManager.translate("알 수 없는 카메라") or \
            not original_resolution_str or original_resolution_str == "-") and exiftool_available:
                logging.info(f"Exiftool로 추가 정보 추출 시도: {first_raw_file_path_obj.name}")
                try:
                    cmd = [exiftool_path, "-json", "-Model", "-ImageWidth", "-ImageHeight", "-Make", first_raw_file_path_str]
                    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                    process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, creationflags=creationflags)
                    if process.returncode == 0 and process.stdout:
                        exif_data_list = json.loads(process.stdout)
                        if exif_data_list and isinstance(exif_data_list, list):
                            exif_data = exif_data_list[0]
                            model = exif_data.get("Model")
                            make = exif_data.get("Make")
                            
                            if make and model and (not camera_model_name or camera_model_name == LanguageManager.translate("알 수 없는 카메라")):
                                camera_model_name = f"{make.strip()} {model.strip()}"
                            elif model and (not camera_model_name or camera_model_name == LanguageManager.translate("알 수 없는 카메라")):
                                camera_model_name = model.strip()
                            
                            # rawpy_exif_data 보강
                            if not rawpy_exif_data.get("exif_make") and make: rawpy_exif_data["exif_make"] = make.strip()
                            if not rawpy_exif_data.get("exif_model") and model: rawpy_exif_data["exif_model"] = model.strip()


                            if (not original_resolution_str or original_resolution_str == "-"): # is_raw_compatible이 False인 경우 등
                                width = exif_data.get("ImageWidth")
                                height = exif_data.get("ImageHeight")
                                if width and height and int(width) > 0 and int(height) > 0:
                                    original_resolution_str = f"{width}x{height}"
                except Exception as e_exiftool:
                    logging.error(f"Exiftool로 정보 추출 중 오류: {e_exiftool}")
            
            # 최종 카메라 모델명 결정 (rawpy_exif_data 우선, 없으면 camera_model_name 변수 사용)
            final_camera_model_display = ""
            if rawpy_exif_data.get("exif_make") and rawpy_exif_data.get("exif_model"):
                final_camera_model_display = format_camera_name(rawpy_exif_data["exif_make"], rawpy_exif_data["exif_model"])
            elif rawpy_exif_data.get("exif_model"):
                final_camera_model_display = rawpy_exif_data["exif_model"]
            elif camera_model_name and camera_model_name != LanguageManager.translate("알 수 없는 카메라"):
                final_camera_model_display = camera_model_name
            else:
                final_camera_model_display = LanguageManager.translate("알 수 없는 카메라")


            # 1.3. {미리보기 해상도} 추출
            # ImageLoader의 _load_raw_preview_with_orientation을 임시로 호출하여 미리보기 정보 얻기
            # (ImageLoader 인스턴스가 필요)
            preview_pixmap, preview_width, preview_height = self.image_loader._load_raw_preview_with_orientation(first_raw_file_path_str)
            if preview_pixmap and not preview_pixmap.isNull() and preview_width and preview_height:
                preview_resolution_str = f"{preview_width}x{preview_height}"
            else: # 미리보기 추출 실패 또는 정보 없음
                preview_resolution_str = LanguageManager.translate("정보 없음") # 또는 "-"

            logging.info(f"파일 분석 완료: 호환={is_raw_compatible}, 모델='{final_camera_model_display}', 원본={original_resolution_str}, 미리보기={preview_resolution_str}")

            self.last_processed_camera_model = None # 새 폴더 로드 시 이전 카메라 모델 정보 초기화
            
            # --- 2. 저장된 설정 확인 및 메시지 박스 표시 결정 ---
            chosen_method = None # 사용자가 최종 선택한 처리 방식 ("preview" or "decode")
            dont_ask_again_for_this_model = False

            # final_camera_model_display가 유효할 때만 camera_raw_settings 확인
            if final_camera_model_display != LanguageManager.translate("알 수 없는 카메라"):
                saved_setting_for_this_action = self.get_camera_raw_setting(final_camera_model_display)
                if saved_setting_for_this_action: # 해당 모델에 대한 설정이 존재하면
                    # 저장된 "dont_ask" 값을 dont_ask_again_for_this_model의 초기값으로 사용
                    dont_ask_again_for_this_model = saved_setting_for_this_action.get("dont_ask", False)

                    if dont_ask_again_for_this_model: # "다시 묻지 않음"이 True이면
                        chosen_method = saved_setting_for_this_action.get("method")
                        logging.info(f"'{final_camera_model_display}' 모델에 저장된 '다시 묻지 않음' 설정 사용: {chosen_method}")
                    else: # "다시 묻지 않음"이 False이거나 dont_ask 키가 없으면 메시지 박스 표시
                        chosen_method, dont_ask_again_for_this_model_from_dialog = self._show_raw_processing_choice_dialog(
                            is_raw_compatible, final_camera_model_display, original_resolution_str, preview_resolution_str
                        )
                        # 사용자가 대화상자를 닫지 않았을 때만 dont_ask_again_for_this_model 값을 업데이트
                        if chosen_method is not None:
                            dont_ask_again_for_this_model = dont_ask_again_for_this_model_from_dialog
                else: # 해당 모델에 대한 설정이 아예 없으면 메시지 박스 표시
                    chosen_method, dont_ask_again_for_this_model_from_dialog = self._show_raw_processing_choice_dialog(
                        is_raw_compatible, final_camera_model_display, original_resolution_str, preview_resolution_str
                    )
                    if chosen_method is not None:
                        dont_ask_again_for_this_model = dont_ask_again_for_this_model_from_dialog
            else: # 카메라 모델을 알 수 없는 경우 -> 항상 메시지 박스 표시
                logging.info(f"카메라 모델을 알 수 없어, 메시지 박스 표시 (호환성 기반)")
                chosen_method, dont_ask_again_for_this_model_from_dialog = self._show_raw_processing_choice_dialog(
                    is_raw_compatible, final_camera_model_display, original_resolution_str, preview_resolution_str
                )
                if chosen_method is not None:
                    dont_ask_again_for_this_model = dont_ask_again_for_this_model_from_dialog


            if chosen_method is None:
                logging.info("RAW 처리 방식 선택되지 않음 (대화상자 닫힘 등). 로드 취소.")
                return
            
            logging.info(f"사용자 선택 RAW 처리 방식: {chosen_method}") # <<< 로그 추가

            # --- "decode" 모드일 경우 진행률 대화상자 표시 ---
            if chosen_method == "decode":
                self._show_first_raw_decode_progress()


            # --- 3. "다시 묻지 않음" 선택 시 설정 저장 ---
            # dont_ask_again_for_this_model은 위 로직을 통해 올바른 값 (기존 값 또는 대화상자 선택 값)을 가짐
            if final_camera_model_display != LanguageManager.translate("알 수 없는 카메라"):
                # chosen_method가 None이 아닐 때만 저장 로직 실행
                self.set_camera_raw_setting(final_camera_model_display, chosen_method, dont_ask_again_for_this_model)
            
            if final_camera_model_display != LanguageManager.translate("알 수 없는 카메라"):
                self.last_processed_camera_model = final_camera_model_display
            else:
                self.last_processed_camera_model = None
            
            # --- 4. ImageLoader에 선택된 처리 방식 설정 및 나머지 파일 로드 ---
            self.image_loader.set_raw_load_strategy(chosen_method) # <<< 중요!
            logging.info(f"ImageLoader 처리 방식 설정 (새 로드): {chosen_method}")

            # --- RAW 로드 성공 시 ---
            print(f"로드된 RAW 파일 수: {len(unique_raw_files)}")
            self.image_files = unique_raw_files

            # 썸네일 패널에 파일 목록 설정
            self.thumbnail_panel.set_image_files(self.image_files)
            
            self.raw_folder = folder_path
            self.is_raw_only_mode = True

            self.current_folder = ""
            self.raw_files = {} # RAW 전용 모드에서는 이 딕셔너리는 다른 용도로 사용되지 않음
            self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))
            self.update_jpg_folder_ui_state()

            self.raw_folder_path_label.setText(folder_path)
            self.update_raw_folder_ui_state()
            self.update_match_raw_button_state()
            self.load_button.setEnabled(False)

            self.grid_page_start_index = 0
            self.current_grid_index = 0
            self.image_loader.clear_cache() # 이전 캐시 비우기 (다른 전략이었을 수 있으므로)

            self.zoom_mode = "Fit"
            self.fit_radio.setChecked(True)
            self.grid_mode = "Off"
            self.grid_off_radio.setChecked(True)
            self.update_zoom_radio_buttons_state()
            self.save_state() # <<< 저장

            self.current_image_index = 0
            # display_current_image() 호출 전에 ImageLoader의 _raw_load_strategy가 설정되어 있어야 함
            logging.info(f"display_current_image 호출 직전 ImageLoader 전략: {self.image_loader._raw_load_strategy} (ID: {id(self.image_loader)})") # <<< 로그 추가
            self.display_current_image() 

            if self.grid_mode == "Off":
                self.start_background_thumbnail_preloading()

            if self.session_management_popup and self.session_management_popup.isVisible():
                self.session_management_popup.update_all_button_states()

    def _show_raw_processing_choice_dialog(self, is_compatible, model_name, orig_res, prev_res):
        """RAW 처리 방식 선택을 위한 맞춤형 대화상자를 표시합니다."""
        dialog = QDialog(self)
        dialog.setWindowTitle(LanguageManager.translate("RAW 파일 처리 방식 선택")) # 새 번역 키
        
        # 다크 테마 적용 (메인 윈도우의 show_themed_message_box 참조)
        apply_dark_title_bar(dialog)
        palette = QPalette(); palette.setColor(QPalette.Window, QColor(ThemeManager.get_color('bg_primary')))
        dialog.setPalette(palette); dialog.setAutoFillBackground(True)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        message_label = QLabel()
        message_label.setWordWrap(True)
        message_label.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        message_label.setTextFormat(Qt.RichText) # <<< RichText 사용 명시

        radio_group = QButtonGroup(dialog)
        preview_radio = QRadioButton()
        decode_radio = QRadioButton()
        
        # 체크박스 스타일은 PhotoSortApp의 것을 재사용하거나 여기서 정의
        checkbox_style = f"""
            QCheckBox {{ color: {ThemeManager.get_color('text')}; padding: {UIScaleManager.get("checkbox_padding")}px; }}
            QCheckBox::indicator {{ width: {UIScaleManager.get("checkbox_size")}px; height: {UIScaleManager.get("checkbox_size")}px; }}
            QCheckBox::indicator:checked {{ background-color: {ThemeManager.get_color('accent')}; border: {UIScaleManager.get("checkbox_border")}px solid {ThemeManager.get_color('accent')}; border-radius: {UIScaleManager.get("checkbox_border_radius")}px; }}
            QCheckBox::indicator:unchecked {{ background-color: {ThemeManager.get_color('bg_primary')}; border: {UIScaleManager.get("checkbox_border")}px solid {ThemeManager.get_color('border')}; border-radius: {UIScaleManager.get("checkbox_border_radius")}px; }}
            QCheckBox::indicator:unchecked:hover {{ border: {UIScaleManager.get("checkbox_border")}px solid {ThemeManager.get_color('text_disabled')}; }}
        """
        radio_style = f"""
            QRadioButton {{ color: {ThemeManager.get_color('text')}; padding: 0px; }} 
            QRadioButton::indicator {{ width: {UIScaleManager.get("radiobutton_size")}px; height: {UIScaleManager.get("radiobutton_size")}px; }}
            QRadioButton::indicator:checked {{ background-color: {ThemeManager.get_color('accent')}; border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('accent')}; border-radius: {UIScaleManager.get("radiobutton_border_radius")}px; }}
            QRadioButton::indicator:unchecked {{ background-color: {ThemeManager.get_color('bg_primary')}; border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('border')}; border-radius: {UIScaleManager.get("radiobutton_border_radius")}px; }}
            QRadioButton::indicator:unchecked:hover {{ border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('text_disabled')}; }}
        """
        preview_radio.setStyleSheet(radio_style)
        decode_radio.setStyleSheet(radio_style)

        # 1. 번역할 기본 템플릿 문자열 키를 정의합니다.
        checkbox_text_template_key = "{camera_model_placeholder}의 RAW 처리 방식에 대해 다시 묻지 않습니다."
        # 2. 해당 키로 번역된 템플릿을 가져옵니다.
        translated_checkbox_template = LanguageManager.translate(checkbox_text_template_key)
        # 3. 번역된 템플릿에 실제 카메라 모델명을 포맷팅합니다.
        #    model_name이 "알 수 없는 카메라"일 경우, 해당 번역도 고려해야 함.
        #    여기서는 model_name 자체를 그대로 사용.
        final_checkbox_text = translated_checkbox_template.format(camera_model_placeholder=model_name)
        
        dont_ask_checkbox = QCheckBox(final_checkbox_text) # 포맷팅된 최종 텍스트 사용
        dont_ask_checkbox.setStyleSheet(checkbox_style) # checkbox_style은 이미 정의되어 있다고 가정

        confirm_button = QPushButton(LanguageManager.translate("확인"))
        confirm_button.setStyleSheet(self.load_button.styleSheet()) # 기존 버튼 스타일 재활용
        confirm_button.clicked.connect(dialog.accept)
        
        chosen_method_on_accept = None # 확인 버튼 클릭 시 선택된 메소드 저장용

        # line-height 스타일 적용 (선택 사항)
        html_wrapper_start = "<div style='line-height: 150%;'>" # 예시 줄 간격
        html_wrapper_end = "</div>"

        if is_compatible:
            dialog.setMinimumWidth(917)
            msg_template_key = ("{model_name_placeholder}의 원본 이미지 해상도는 <b>{orig_res_placeholder}</b>입니다.<br>"
                                "{model_name_placeholder}의 RAW 파일에 포함된 미리보기(프리뷰) 이미지의 해상도는 <b>{prev_res_placeholder}</b>입니다.<br>"
                                "미리보기를 통해 이미지를 보시겠습니까, RAW 파일을 디코딩해서 보시겠습니까?")
            translated_msg_template = LanguageManager.translate(msg_template_key)
            formatted_text = translated_msg_template.format(
                model_name_placeholder=model_name,
                orig_res_placeholder=orig_res,
                prev_res_placeholder=prev_res
            )
            # HTML로 감싸기
            message_label.setText(f"{html_wrapper_start}{formatted_text}{html_wrapper_end}")
            
            preview_radio.setText(LanguageManager.translate("미리보기 이미지 사용 (미리보기의 해상도가 충분하거나 빠른 작업 속도가 중요한 경우.)"))

            # "RAW 디코딩" 라디오 버튼 텍스트 설정 시 \n 포함된 키 사용
            decode_radio_key = "RAW 디코딩 (느림. 일부 카메라 호환성 문제 있음.\n미리보기의 해상도가 너무 작거나 원본 해상도가 반드시 필요한 경우에만 사용 권장.)"
            decode_radio.setText(LanguageManager.translate(decode_radio_key))
            
            radio_group.addButton(preview_radio, 0) # preview = 0
            radio_group.addButton(decode_radio, 1)  # decode = 1
            preview_radio.setChecked(True) # 기본 선택: 미리보기

            layout.addWidget(message_label)
            layout.addSpacing(25) # <<< message_label과 첫 번째 라디오 버튼 사이 간격
            layout.addWidget(preview_radio)
            layout.addSpacing(10)
            layout.addWidget(decode_radio)
            layout.addSpacing(25) # 두 번째 라디오버튼과 don't ask 체크박스 사이 간격
            layout.addWidget(dont_ask_checkbox)
            layout.addSpacing(15) # <<< don't ask 체크박스와 확인 버튼 사이 간격
            layout.addWidget(confirm_button, 0, Qt.AlignCenter)

            if dialog.exec() == QDialog.Accepted:
                chosen_method_on_accept = "preview" if radio_group.checkedId() == 0 else "decode"
                return chosen_method_on_accept, dont_ask_checkbox.isChecked()
            else:
                return None, False # 대화상자 닫힘
        else: # 호환 안됨
            dialog.setMinimumWidth(933)
            msg_template_key_incompatible = ("호환성 문제로 {model_name_placeholder}의 RAW 파일을 디코딩 할 수 없습니다.<br>"
                                             "RAW 파일에 포함된 <b>{prev_res_placeholder}</b>의 미리보기 이미지를 사용하겠습니다.<br>"
                                             "({model_name_placeholder}의 원본 이미지 해상도는 <b>{orig_res_placeholder}</b>입니다.)")
            translated_msg_template_incompatible = LanguageManager.translate(msg_template_key_incompatible)
            formatted_text = translated_msg_template_incompatible.format(
                model_name_placeholder=model_name,
                prev_res_placeholder=prev_res,
                orig_res_placeholder=orig_res
            )
            message_label.setText(f"{html_wrapper_start}{formatted_text}{html_wrapper_end}")

            layout.addWidget(message_label)
            layout.addSpacing(20) # <<< message_label과 don't ask 체크박스 사이 간격
            layout.addWidget(dont_ask_checkbox) # 이 경우에도 다시 묻지 않음은 유효
            layout.addSpacing(15) # <<< don't ask 체크박스와 확인 버튼 사이 간격
            layout.addWidget(confirm_button, 0, Qt.AlignCenter)

            if dialog.exec() == QDialog.Accepted:
                # 호환 안되면 무조건 미리보기 사용
                return "preview", dont_ask_checkbox.isChecked()
            else:
                return None, False # 대화상자 닫힘

    def match_raw_files(self, folder_path, silent=False):
        """JPG 파일과 RAW 파일 매칭 (백그라운드에서 실행)"""
        if not folder_path or not self.current_folder:
            if not silent:
                self.show_themed_message_box(QMessageBox.Warning, "경고", "먼저 JPG 폴더를 로드해야 합니다.")
            return False
            
        logging.info(f"RAW 폴더 매칭 시작: {folder_path}")
        
        self._is_silent_load = silent
        
        self.start_background_loading(
            jpg_folder_path=self.current_folder, 
            raw_folder_path=folder_path, 
            mode='jpg_with_raw',
            raw_file_list=None
        )
        return True


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
                background-color: {ThemeManager.get_color('bg_hover')};
            }}
            QPushButton:pressed {{
                background-color: {ThemeManager.get_color('bg_pressed')};
            }}
        """)

        # 제목 표시줄 다크 테마 적용 (Windows용)
        apply_dark_title_bar(message_box)

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

    def on_folder_image_dropped(self, folder_index, drag_data):
        """폴더 레이블에 이미지가 드롭되었을 때 호출"""
        try:
            logging.info(f"이미지 드롭 이벤트: 폴더 {folder_index}, 데이터: {drag_data}")
            
            # 캔버스 드래그인 경우 (2단계에서 추가된 기능)
            if drag_data == "image_drag":
                return self.handle_canvas_to_folder_drop(folder_index)
            elif drag_data.startswith("image_drag:compareB:"):
                # B 캔버스에서 드롭된 경우
                try:
                    image_index_to_move = int(drag_data.split(":")[-1])
                    self.move_image_B_to_folder(folder_index, specific_index=image_index_to_move)
                except (ValueError, IndexError):
                    logging.error(f"잘못된 B 캔버스 드래그 데이터: {drag_data}")
                return

            # 기존 그리드 드래그 처리 ("image_drag:mode:indices" 형태)
            parts = drag_data.split(":")
            if len(parts) < 3 or parts[0] != "image_drag":
                logging.error(f"잘못된 드래그 데이터 형식: {drag_data}")
                return
            
            mode = parts[1]  # "off" 또는 "grid"
            indices_str = parts[2]  # 이미지 인덱스들
            
            # 폴더 유효성 확인
            if (folder_index < 0 or 
                folder_index >= len(self.target_folders) or 
                not self.target_folders[folder_index] or 
                not os.path.isdir(self.target_folders[folder_index])):
                
                self.show_themed_message_box(
                    QMessageBox.Warning,
                    LanguageManager.translate("경고"),
                    LanguageManager.translate("유효하지 않은 폴더입니다.")
                )
                return
            
            # 모드에 따른 이미지 이동 처리 (기존 코드)
            if mode == "off":
                # Grid Off 모드: 단일 이미지 이동
                try:
                    image_index = int(indices_str)
                    if 0 <= image_index < len(self.image_files):
                        # 현재 인덱스를 임시로 설정하고 이동
                        original_index = self.current_image_index
                        self.current_image_index = image_index
                        self.move_current_image_to_folder(folder_index)
                        # 인덱스는 move_current_image_to_folder에서 자동으로 조정됨
                    else:
                        logging.error(f"유효하지 않은 이미지 인덱스: {image_index}")
                except ValueError:
                    logging.error(f"이미지 인덱스 파싱 오류: {indices_str}")
            
            elif mode == "grid":
                # Grid 모드: 단일 또는 다중 이미지 이동
                try:
                    if "," in indices_str:
                        # 다중 선택된 경우 (기존 코드)
                        selected_indices = [int(idx) for idx in indices_str.split(",")]
                        grid_indices = []
                        for global_idx in selected_indices:
                            if self.grid_page_start_index <= global_idx < self.grid_page_start_index + 9:
                                grid_idx = global_idx - self.grid_page_start_index
                                grid_indices.append(grid_idx)
                        
                        if grid_indices:
                            self.selected_grid_indices = set(grid_indices)
                            self.move_grid_image(folder_index)
                    else:
                        # 단일 선택된 경우 (기존 코드)
                        global_index = int(indices_str)
                        if 0 <= global_index < len(self.image_files):
                            rows, cols = self._get_grid_dimensions()
                            num_cells = rows * cols
                            self.grid_page_start_index = (global_index // num_cells) * num_cells
                            self.current_grid_index = global_index % num_cells
                            
                            if hasattr(self, 'selected_grid_indices'):
                                self.selected_grid_indices.clear()
                            
                            self.move_grid_image(folder_index)
                        else:
                            logging.error(f"유효하지 않은 이미지 인덱스: {global_index}")
                except ValueError:
                    logging.error(f"그리드 인덱스 파싱 오류: {indices_str}")
            
            else:
                logging.error(f"알 수 없는 드래그 모드: {mode}")
            
        except Exception as e:
            logging.error(f"on_folder_image_dropped 오류: {e}")
            self.show_themed_message_box(
                QMessageBox.Critical,
                LanguageManager.translate("오류"),
                LanguageManager.translate("이미지 이동 중 오류가 발생했습니다.")
            )

    def handle_canvas_to_folder_drop(self, folder_index):
        """캔버스에서 폴더로 드래그 앤 드롭 처리"""
        try:
            # 1. Zoom Fit 상태 확인
            if self.zoom_mode != "Fit":
                self.show_themed_message_box(
                    QMessageBox.Information,
                    LanguageManager.translate("알림"),
                    LanguageManager.translate("Zoom Fit 모드에서만 드래그 앤 드롭이 가능합니다.")
                )
                return False
            
            # 2. 이미지 로드 상태 확인
            if not self.image_files or self.current_image_index < 0 or self.current_image_index >= len(self.image_files):
                self.show_themed_message_box(
                    QMessageBox.Warning,
                    LanguageManager.translate("경고"),
                    LanguageManager.translate("이동할 이미지가 없습니다.")
                )
                return False
            
            # 3. 폴더 유효성 확인
            if (folder_index < 0 or 
                folder_index >= len(self.target_folders) or 
                not self.target_folders[folder_index] or 
                not os.path.isdir(self.target_folders[folder_index])):
                
                self.show_themed_message_box(
                    QMessageBox.Warning,
                    LanguageManager.translate("경고"),
                    LanguageManager.translate("유효하지 않은 폴더입니다.")
                )
                return False
            
            # 4. Grid Off/Grid 모드에 따른 처리
            if self.grid_mode == "Off":
                # Grid Off 모드: move_current_image_to_folder 사용
                logging.info(f"Grid Off 모드: 현재 이미지 ({self.current_image_index}) 폴더 {folder_index}로 이동")
                self.move_current_image_to_folder(folder_index)
                return True
                
            elif self.grid_mode != "Off":
                # Grid 모드: move_grid_image 사용
                logging.info(f"Grid 모드: 현재 그리드 이미지 폴더 {folder_index}로 이동")
                
                # 현재 그리드에서 선택된 이미지가 있는지 확인
                if hasattr(self, 'current_grid_index') and self.current_grid_index >= 0:
                    # 단일 선택 상태로 설정
                    if hasattr(self, 'selected_grid_indices'):
                        self.selected_grid_indices.clear()
                    
                    self.move_grid_image(folder_index)
                    return True
                else:
                    self.show_themed_message_box(
                        QMessageBox.Warning,
                        LanguageManager.translate("경고"),
                        LanguageManager.translate("선택된 그리드 이미지가 없습니다.")
                    )
                    return False
            else:
                logging.error(f"알 수 없는 그리드 모드: {self.grid_mode}")
                return False
                
        except Exception as e:
            logging.error(f"handle_canvas_to_folder_drop 오류: {e}")
            self.show_themed_message_box(
                QMessageBox.Critical,
                LanguageManager.translate("오류"),
                LanguageManager.translate("이미지 이동 중 오류가 발생했습니다.")
            )
            return False

    def setup_folder_selection_ui(self):
        """분류 폴더 설정 UI를 동적으로 구성하고 컨테이너 위젯을 반환합니다."""
        self.folder_buttons = []
        self.folder_path_labels = []
        self.folder_action_buttons = []
        
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(UIScaleManager.get("category_folder_vertical_spacing"))
        
        # UIScaleManager 값 미리 가져오기
        button_padding = UIScaleManager.get("button_padding")
        delete_button_width = UIScaleManager.get("delete_button_width")
        folder_container_spacing = UIScaleManager.get("folder_container_spacing", 5)

        # 버튼 스타일 미리 정의
        number_button_style = ThemeManager.generate_main_button_style()
        action_button_style = ThemeManager.generate_action_button_style()
        
        for i in range(self.folder_count):
            folder_container = QWidget()
            folder_layout = QHBoxLayout(folder_container)
            folder_layout.setContentsMargins(0, 0, 0, 0)
            folder_layout.setSpacing(folder_container_spacing)

            folder_button = QPushButton(f"{i+1}")
            folder_button.setStyleSheet(number_button_style)
            folder_button.clicked.connect(lambda checked=False, idx=i: self.select_category_folder(idx))

            folder_path_label = EditableFolderPathLabel()
            folder_path_label.set_folder_index(i)
            folder_path_label.imageDropped.connect(self.on_folder_image_dropped)
            folder_path_label.folderDropped.connect(lambda index, path: self._handle_category_folder_drop(path, index))
            folder_path_label.doubleClicked.connect(lambda full_path, idx=i: self.open_category_folder(idx, full_path))
            folder_path_label.stateChanged.connect(self.update_folder_action_button)
            folder_path_label.returnPressed.connect(lambda idx=i: self.confirm_subfolder_creation(idx))

            action_button = QPushButton("✕")
            action_button.setStyleSheet(action_button_style)

            action_button.clicked.connect(lambda checked=False, idx=i: self.on_folder_action_button_clicked(idx))
            
            # 높이 동기화
            fm_label = QFontMetrics(folder_path_label.font())
            label_line_height = fm_label.height()
            padding = UIScaleManager.get("sort_folder_label_padding")
            fixed_height = label_line_height + padding
            folder_button.setFixedHeight(fixed_height)
            action_button.setFixedHeight(fixed_height)
            folder_button.setFixedWidth(delete_button_width)
            action_button.setFixedWidth(delete_button_width)
            
            folder_layout.addWidget(folder_button)
            folder_layout.addWidget(folder_path_label, 1)
            folder_layout.addWidget(action_button)
            
            main_layout.addWidget(folder_container)
            
            self.folder_buttons.append(folder_button)
            self.folder_path_labels.append(folder_path_label)
            self.folder_action_buttons.append(action_button)

        self.update_all_folder_labels_state()
        return main_container


    def update_all_folder_labels_state(self):
        """모든 분류 폴더 레이블의 상태를 현재 앱 상태에 맞게 업데이트합니다."""
        if not hasattr(self, 'folder_path_labels'):
            return

        images_loaded = bool(self.image_files)
        
        for i, label in enumerate(self.folder_path_labels):
            has_path = bool(i < len(self.target_folders) and self.target_folders[i])
            
            if has_path:
                label.set_state(EditableFolderPathLabel.STATE_SET, self.target_folders[i])
            elif images_loaded:
                label.set_state(EditableFolderPathLabel.STATE_EDITABLE)
            else:
                label.set_state(EditableFolderPathLabel.STATE_DISABLED)

    def update_folder_action_button(self, index, state):
        """지정된 인덱스의 액션 버튼('X'/'V')을 상태에 맞게 업데이트합니다."""
        if index < 0 or index >= len(self.folder_action_buttons):
            return
        button = self.folder_action_buttons[index]
        
        if state == EditableFolderPathLabel.STATE_DISABLED:
            button.setText("✕")
            button.setEnabled(False)
        elif state == EditableFolderPathLabel.STATE_EDITABLE:
            button.setText("✓")
            button.setEnabled(True)
        elif state == EditableFolderPathLabel.STATE_SET:
            button.setText("✕")
            button.setEnabled(True)

    def on_folder_action_button_clicked(self, index):
        """분류 폴더의 액션 버튼(X/V) 클릭을 처리하는 통합 핸들러"""
        if index < 0 or index >= len(self.folder_action_buttons):
            return
        
        button = self.folder_action_buttons[index]
        button_text = button.text()

        if button_text == "✓":
            # 체크 표시일 경우: 하위 폴더 생성 로직 호출
            self.confirm_subfolder_creation(index)
        elif button_text == "✕":
            # X 표시일 경우: 폴더 지정 취소 로직 호출
            self.clear_category_folder(index)            

    def confirm_subfolder_creation(self, index):
        """입력된 이름으로 하위 폴더를 생성하고 UI를 업데이트합니다."""
        if index < 0 or index >= len(self.folder_path_labels):
            return
            
        label = self.folder_path_labels[index]
        new_folder_name = label.text().strip()

        # 1. 유효성 검사
        if not self._is_valid_foldername(new_folder_name):
            self.show_themed_message_box(QMessageBox.Warning, 
                                        LanguageManager.translate("경고"), 
                                        LanguageManager.translate("잘못된 폴더명입니다."))
            return

        # 2. 기본 경로 설정
        base_path_str = self.raw_folder if self.is_raw_only_mode else self.current_folder
        if not base_path_str:
            self.show_themed_message_box(QMessageBox.Warning, 
                                        LanguageManager.translate("경고"), 
                                        LanguageManager.translate("기준 폴더가 로드되지 않았습니다."))
            return
            
        base_path = Path(base_path_str)
        new_full_path = base_path / new_folder_name

        # 3. 폴더 생성
        try:
            new_full_path.mkdir(parents=True, exist_ok=True)
            logging.info(f"하위 폴더 생성 성공: {new_full_path}")
        except Exception as e:
            logging.error(f"하위 폴더 생성 실패: {e}")
            self.show_themed_message_box(QMessageBox.Critical, 
                                        LanguageManager.translate("에러"), 
                                        f"{LanguageManager.translate('폴더 생성 실패')}:\n{e}")
            return

        # 4. 상태 업데이트
        self.target_folders[index] = str(new_full_path)
        label.set_state(EditableFolderPathLabel.STATE_SET, str(new_full_path))
        self.save_state()

    def update_folder_buttons(self):
        """폴더 설정 상태에 따라 UI 업데이트"""
        # 안전한 범위 검사 추가
        if not hasattr(self, 'folder_buttons') or not self.folder_buttons:
            return  # 버튼이 아직 생성되지 않았으면 건너뛰기
        
        # 실제 생성된 버튼 개수와 설정된 폴더 개수 중 작은 값 사용
        actual_button_count = len(self.folder_buttons)
        target_count = min(self.folder_count, actual_button_count)
        
        # 모든 폴더 버튼은 항상 활성화
        for i in range(target_count):
            # 폴더 버튼 항상 활성화
            self.folder_buttons[i].setEnabled(True)
            
            # 폴더 경로 레이블 및 X 버튼 상태 설정
            has_folder = bool(i < len(self.target_folders) and self.target_folders[i] and os.path.isdir(self.target_folders[i]))
            
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
            
            self.folder_path_labels[i].update_original_style(self.folder_path_labels[i].styleSheet())

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
            # <<< 수정 시작 >>>
            # setText 대신 set_state를 사용하여 UI와 상태를 한 번에 업데이트합니다.
            self.folder_path_labels[index].set_state(EditableFolderPathLabel.STATE_SET, folder_path)
            # <<< 수정 끝 >>>
            self.save_state()
    
    def clear_category_folder(self, index):
        """분류 폴더 지정 취소"""
        self.target_folders[index] = ""
        # 현재 이미지 로드 상태에 따라 editable 또는 disabled 상태로 변경
        if self.image_files:
            self.folder_path_labels[index].set_state(EditableFolderPathLabel.STATE_EDITABLE)
        else:
            self.folder_path_labels[index].set_state(EditableFolderPathLabel.STATE_DISABLED)
        self.save_state()

    
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
    
    
    def navigate_to_adjacent_page(self, direction):
        """그리드 모드에서 페이지 단위 이동 처리 (순환 기능 추가)"""
        if self.grid_mode == "Off" or not self.image_files:
            return

        rows, cols = self._get_grid_dimensions()
        if rows == 0: return
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

        # 페이지 전환 시 선택 상태 초기화
        self.clear_grid_selection()

        # 그리드 뷰 업데이트
        self.update_grid_view()
    

    def show_previous_image(self):
        if not self.image_files: return
        self._prepare_for_photo_change()
        if self.current_image_index <= 0: self.current_image_index = len(self.image_files) - 1
        else: self.current_image_index -= 1
        self.force_refresh = True
        self.display_current_image()
        # 썸네일 패널 동기화 추가
        self.update_thumbnail_current_index()
    
    def set_current_image_from_dialog(self, index):
        if not (0 <= index < len(self.image_files)): return
        self._prepare_for_photo_change() # <<< 사진 변경 전 처리
        # ... (나머지 로직) ...
        self.current_image_index = index
        self.force_refresh = True
        # ... (Grid 모드/Off 모드에 따른 display_current_image 또는 update_grid_view 호출) ...
        if self.grid_mode != "Off":
            # ... (그리드 인덱스 설정) ...
            self.update_grid_view()
        else:
            self.display_current_image()


    def show_next_image(self):
        if not self.image_files: return
        self._prepare_for_photo_change()
        if self.current_image_index >= len(self.image_files) - 1: self.current_image_index = 0
        else: self.current_image_index += 1
        self.force_refresh = True
        self.display_current_image()
        # 썸네일 패널 동기화 추가
        self.update_thumbnail_current_index()
    
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
                if self.session_management_popup and self.session_management_popup.isVisible():
                    self.session_management_popup.update_all_button_states()
                # 미니맵 숨기기 추가
                if self.minimap_visible:
                    self.minimap_widget.hide()
                    self.minimap_visible = False
                self.show_themed_message_box(QMessageBox.Information, LanguageManager.translate("완료"), LanguageManager.translate("모든 이미지가 분류되었습니다."))

        except Exception as e:
            # move_file 에서 예외 처리하지만, pop 등 다른 로직에서 발생할 수 있으므로 유지
            self.show_themed_message_box(QMessageBox.Critical, LanguageManager.translate("에러"), f"{LanguageManager.translate('파일 이동 중 오류 발생')}: {str(e)}")
            # 만약 파일 이동 중 예외 발생 시, 히스토리 추가는 되지 않음

    # 파일 이동 안정성 강화(재시도 로직). 파일 이동(shutil.move) 시 PermissionError (주로 Windows에서 다른 프로세스가 파일을 사용 중일 때 발생)가 발생하면, 즉시 실패하는 대신 짧은 시간 대기 후 최대 20번까지 재시도합니다.
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

        # 이미 같은 이름의 파일이 있는지 확인 (수정: 파일명 중복 처리 로직을 재시도 로직과 분리)
        if target_path.exists():
            counter = 1
            while True:
                new_name = f"{source_path.stem}_{counter}{source_path.suffix}"
                new_target_path = target_dir / new_name
                if not new_target_path.exists():
                    target_path = new_target_path # 최종 타겟 경로 업데이트
                    break
                counter += 1
            logging.info(f"파일명 중복 처리: {source_path.name} -> {target_path.name}")

        # 파일 이동
        delay = 0.1 # <<< 재시도 대기 시간
        for attempt in range(20): # 최대 20번 재시도 (초 단위 2초 대기)
        # 재시도 로직 추가
            try: # <<< 파일 이동 시 오류 처리 추가
                shutil.move(str(source_path), str(target_path))
                logging.info(f"파일 이동: {source_path} -> {target_path}")
                return target_path # <<< 이동 성공 시 최종 target_path 반환
            except PermissionError as e:
                if hasattr(e, 'winerror') and e.winerror == 32:
                    print(f"[{attempt+1}] 파일 점유 중 (WinError 32), 재시도 대기: {source_path}")
                    time.sleep(delay)
                else:
                    print(f"[{attempt+1}] PermissionError: {e}")
                    return None # <<< 권한 오류 발생 시 None 반환
            except Exception as e:
                logging.error(f"파일 이동 실패: {source_path} -> {target_path}, 오류: {e}")
                return None # <<< 이동 실패 시 None 반환

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
        font = QFont(self.font()) # <<< 현재 위젯(PhotoSortApp)의 폰트를 가져와서 복사
        # font.setBold(True) # 이 새 폰트 객체에만 볼드 적용
        font.setPointSize(UIScaleManager.get("zoom_grid_font_size")) # 이 새 폰트 객체에만 크기 적용
        zoom_label.setFont(font) # 수정된 새 폰트를 레이블에 적용
        self.control_layout.addWidget(zoom_label)
        self.control_layout.addSpacing(UIScaleManager.get("title_spacing"))

        # 확대 옵션 컨테이너 (가로 배치)
        zoom_container = QWidget()
        zoom_layout = QHBoxLayout(zoom_container)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(UIScaleManager.get("group_box_spacing"))
        
        # 라디오 버튼 생성
        self.fit_radio = QRadioButton("Fit")
        self.zoom_100_radio = QRadioButton("100%")
        self.zoom_spin_btn = QRadioButton()
        
        # 버튼 그룹에 추가
        self.zoom_group = QButtonGroup(self)
        self.zoom_group.addButton(self.fit_radio, 0)
        self.zoom_group.addButton(self.zoom_100_radio, 1)
        self.zoom_group.addButton(self.zoom_spin_btn, 2) # ID: 2 (기존 200 자리)

        # 동적 줌 SpinBox 설정
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(10, 500)
        self.zoom_spin.setValue(int(self.zoom_spin_value * 100)) # 2.0 -> 200
        self.zoom_spin.setSuffix("%")
        self.zoom_spin.setSingleStep(10)
        self.zoom_spin.setFixedWidth(UIScaleManager.get("zoom_spinbox_width"))
        self.zoom_spin.lineEdit().setReadOnly(True)
        self.zoom_spin.setContextMenuPolicy(Qt.NoContextMenu)
        self.zoom_spin.valueChanged.connect(self.on_zoom_spinbox_value_changed)
        self.zoom_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {ThemeManager.get_color('bg_primary')};
                color: {ThemeManager.get_color('text')};
                border: 1px solid {ThemeManager.get_color('border')};
                border-radius: 1px;
                padding: 2px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: {ThemeManager.get_color('bg_primary')};
                border: 1px solid {ThemeManager.get_color('border')};
                width: 16px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background-color: {ThemeManager.get_color('bg_secondary')};
            }}
            QSpinBox::up-arrow, QSpinBox::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
            }}
        """)
        # 기본값: Fit
        self.fit_radio.setChecked(True)
        
        # 버튼 스타일 설정 (기존 코드 재사용)
        radio_style = ThemeManager.generate_radio_button_style()

        self.fit_radio.setStyleSheet(radio_style)
        self.zoom_100_radio.setStyleSheet(radio_style)
        self.zoom_spin_btn.setStyleSheet(radio_style)
        
        # 이벤트 연결
        self.zoom_group.buttonClicked.connect(self.on_zoom_changed)
        
        # 레이아웃에 위젯 추가 (가운데 정렬)
        zoom_layout.addStretch()
        zoom_layout.addWidget(self.fit_radio)
        zoom_layout.addWidget(self.zoom_100_radio)
        # <<<--- 중첩 레이아웃으로 Spin UI 묶기 ---<<<
        spin_widget_container = QWidget()
        spin_layout = QHBoxLayout(spin_widget_container)
        spin_layout.setContentsMargins(0,0,0,0)
        spin_layout.setSpacing(0) # 라디오 버튼과 스핀박스 사이 간격
        spin_layout.addWidget(self.zoom_spin_btn)
        spin_layout.addWidget(self.zoom_spin)

        zoom_layout.addWidget(spin_widget_container) # 묶인 위젯을 한 번에 추가
        # <<<----중첩 레이아웃으로 Spin UI 묶기 끝 ----<<<
        zoom_layout.addStretch()
        
        self.control_layout.addWidget(zoom_container)
        
        # 미니맵 토글 체크박스 추가
        self.minimap_toggle = QCheckBox(LanguageManager.translate("미니맵"))
        self.minimap_toggle.setChecked(True)  # 기본값 체크(ON)
        self.minimap_toggle.toggled.connect(self.toggle_minimap)
        self.minimap_toggle.setStyleSheet(ThemeManager.generate_checkbox_style())
        
        # 미니맵 토글을 중앙에 배치
        minimap_container = QWidget()
        minimap_layout = QHBoxLayout(minimap_container)
        minimap_layout.setContentsMargins(0, 10, 0, 0)
        minimap_layout.addStretch()
        minimap_layout.addWidget(self.minimap_toggle)
        minimap_layout.addStretch()
        
        self.control_layout.addWidget(minimap_container)


    def on_zoom_changed(self, button):
        old_zoom_mode = self.zoom_mode
        new_zoom_mode = ""
        if button == self.fit_radio:
            new_zoom_mode = "Fit"
            self.update_thumbnail_panel_visibility()
        elif button == self.zoom_100_radio:
            new_zoom_mode = "100%"
        elif button == self.zoom_spin_btn:
            new_zoom_mode = "Spin"
        else:
            return

        if old_zoom_mode == new_zoom_mode:
            return

        # [수정] Fit이 아닌 모드로 변경될 때, 그 모드를 last_active_zoom_mode로 저장
        if new_zoom_mode != "Fit":
            self.last_active_zoom_mode = new_zoom_mode
            logging.debug(f"Last active zoom mode updated to: {self.last_active_zoom_mode}")

        current_orientation = self.current_image_orientation
        
        # 디버깅: 현재 상태 로그
        logging.debug(f"줌 모드 변경: {old_zoom_mode} -> {new_zoom_mode}, 방향: {current_orientation}")

        # 현재 뷰포트 포커스 저장 (100%/Spin -> Fit 전환 시)
        if old_zoom_mode in ["100%", "Spin"] and current_orientation:
            # 중요: zoom_mode를 변경하기 전에 현재 뷰포트 위치를 계산해야 함
            current_rel_center = self._get_current_view_relative_center()
            logging.debug(f"뷰포트 위치 저장: {current_orientation} -> {current_rel_center} (줌: {old_zoom_mode})")
            
            # 현재 활성 포커스 업데이트
            self.current_active_rel_center = current_rel_center
            self.current_active_zoom_level = old_zoom_mode
            
            # 방향별 포커스 저장
            self._save_orientation_viewport_focus(
                current_orientation,
                current_rel_center,
                old_zoom_mode
            )

        # 줌 모드 변경
        self.zoom_mode = new_zoom_mode

        if self.zoom_mode == "Fit":
            self.current_active_rel_center = QPointF(0.5, 0.5)
            self.current_active_zoom_level = "Fit"
            logging.debug("Fit 모드로 전환: 중앙 포커스 설정")
        else:
            # 저장된 뷰포트 포커스 복구 (Fit -> 100%/Spin 전환 시)
            if current_orientation:
                saved_rel_center, saved_zoom_level = self._get_orientation_viewport_focus(current_orientation, self.zoom_mode)
                self.current_active_rel_center = saved_rel_center
                self.current_active_zoom_level = self.zoom_mode
                logging.debug(f"뷰포트 포커스 복구: {current_orientation} -> 중심={saved_rel_center}, 줌={self.zoom_mode}")
            else:
                # orientation 정보가 없으면 중앙 사용
                self.current_active_rel_center = QPointF(0.5, 0.5)
                self.current_active_zoom_level = self.zoom_mode
                logging.debug(f"orientation 정보 없음: 중앙 사용")

        self.zoom_change_trigger = "radio_button"

        # 그리드 모드 관련 처리
        if self.zoom_mode != "Fit" and self.grid_mode != "Off":
            if self.image_files and 0 <= self.grid_page_start_index + self.current_grid_index < len(self.image_files):
                self.current_image_index = self.grid_page_start_index + self.current_grid_index
            else:
                self.current_image_index = 0 if self.image_files else -1
            
            self.grid_mode = "Off"
            self.grid_off_radio.setChecked(True)
            self.update_grid_view()
            self.update_zoom_radio_buttons_state()
            self.update_counter_layout()
            
            if self.original_pixmap is None and self.current_image_index != -1:
                logging.debug("on_zoom_changed: Grid에서 Off로 전환, original_pixmap 로드 위해 display_current_image 호출")
                self.display_current_image()
                return
        
        # 이미지 적용
        if self.original_pixmap:
            logging.debug(f"on_zoom_changed: apply_zoom_to_image 호출 (줌: {self.zoom_mode}, 활성중심: {self.current_active_rel_center})")
            self.apply_zoom_to_image()

        self.toggle_minimap(self.minimap_toggle.isChecked())

    def on_zoom_spinbox_value_changed(self, value):
        """줌 스핀박스 값 변경 시 호출"""
        self.zoom_spin_value = value / 100.0  # 300 -> 3.0
        if self.zoom_mode == "Spin":
            # 현재 모드가 Spin일 때만 즉시 이미지에 반영
            self.image_processing = True
            self.apply_zoom_to_image()
            self.image_processing = False

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
        """미니맵 위치 업데이트 (A 캔버스 기준)"""
        if not self.minimap_visible:
            return
        padding = 10
        # 기준을 self.image_panel에서 self.scroll_area로 변경
        panel_width = self.scroll_area.width()
        panel_height = self.scroll_area.height()
        minimap_x = panel_width - self.minimap_width - padding
        minimap_y = panel_height - self.minimap_height - padding
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
            elif zoom_level == "Spin":
                zoom_percent = self.zoom_spin_value
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
        """Grid 설정 UI 구성 (라디오 버튼 + 콤보박스)"""
        # Grid 제목 레이블
        grid_title = QLabel("Grid")
        grid_title.setAlignment(Qt.AlignCenter)
        grid_title.setStyleSheet(f"color: {ThemeManager.get_color('text')};")
        font = QFont(self.font())
        font.setPointSize(UIScaleManager.get("zoom_grid_font_size"))
        grid_title.setFont(font)
        self.control_layout.addWidget(grid_title)
        self.control_layout.addSpacing(UIScaleManager.get("title_spacing"))

        # Grid 옵션 컨테이너 (가로 배치)
        grid_container = QWidget()
        grid_layout_h = QHBoxLayout(grid_container)
        grid_layout_h.setContentsMargins(0, 0, 0, 0)
        grid_layout_h.setSpacing(UIScaleManager.get("group_box_spacing"))

        # --- UI 요소 생성 ---
        self.grid_off_radio = QRadioButton("Off")
        self.grid_on_radio = QRadioButton() # 텍스트 없는 라디오 버튼

        self.grid_size_combo = QComboBox()
        self.grid_size_combo.addItems(["2 x 2", "3 x 3", "4 x 4"])
        self.grid_size_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {ThemeManager.get_color('bg_primary')};
                color: {ThemeManager.get_color('text')};
                border: 1px solid {ThemeManager.get_color('border')};
                border-radius: 1px;
                padding: {UIScaleManager.get("combobox_padding")}px;
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
        """)


        # 버튼 그룹으로 Off/On 상태 관리
        self.grid_mode_group = QButtonGroup(self)
        self.grid_mode_group.addButton(self.grid_off_radio, 0) # ID 0: Off
        self.grid_mode_group.addButton(self.grid_on_radio, 1)  # ID 1: On

        # 기본값: Off
        self.grid_off_radio.setChecked(True)
        self.grid_size_combo.setEnabled(False) # 초기에는 콤보박스 비활성화

        # 스타일 설정
        radio_style = ThemeManager.generate_radio_button_style()

        self.grid_off_radio.setStyleSheet(radio_style)
        self.grid_on_radio.setStyleSheet(radio_style)

        # --- 이벤트 연결 ---
        self.grid_mode_group.buttonClicked.connect(self._on_grid_mode_toggled)
        self.grid_size_combo.currentTextChanged.connect(self._on_grid_size_changed)

        # --- 레이아웃에 위젯 추가 ---
        grid_layout_h.addStretch()
        grid_layout_h.addWidget(self.grid_off_radio)
        # On 라디오 버튼과 콤보박스를 묶어서 추가
        grid_on_container = QHBoxLayout()
        grid_on_container.setContentsMargins(0, 0, 0, 0)
        grid_on_container.setSpacing(5)
        grid_on_container.addWidget(self.grid_on_radio)
        grid_on_container.addWidget(self.grid_size_combo)
        grid_layout_h.addLayout(grid_on_container)
        self.compare_radio = QRadioButton("A | B")
        self.compare_radio.setStyleSheet(radio_style)
        self.grid_mode_group.addButton(self.compare_radio, 2) # ID 2: 비교 모드 
        grid_layout_h.addWidget(self.compare_radio) # <<< 레이아웃에 추가
        grid_layout_h.addStretch()

        self.control_layout.addWidget(grid_container)

        # "파일명" 토글 체크박스는 기존과 동일하게 유지
        self.filename_toggle_grid = QCheckBox(LanguageManager.translate("파일명"))
        self.filename_toggle_grid.setChecked(self.show_grid_filenames)
        self.filename_toggle_grid.toggled.connect(self.on_filename_toggle_changed)
        self.filename_toggle_grid.setStyleSheet(ThemeManager.generate_checkbox_style())
        filename_toggle_container = QWidget()
        filename_toggle_layout = QHBoxLayout(filename_toggle_container)
        filename_toggle_layout.setContentsMargins(0, 10, 0, 0)
        filename_toggle_layout.addStretch()
        filename_toggle_layout.addWidget(self.filename_toggle_grid)
        filename_toggle_layout.addStretch()
        self.control_layout.addWidget(filename_toggle_container)

    def _on_grid_mode_toggled(self, button):
        """Grid On/Off/Compare 라디오 버튼 클릭 시 호출"""
        button_id = self.grid_mode_group.id(button)
        
        new_compare_active = (button_id == 2)
        is_grid_on = (button_id == 1)
        
        # 1. 새로운 grid_mode 결정
        new_grid_mode = "Off" # 기본값
        if is_grid_on:
            combo_text = self.grid_size_combo.currentText().replace(" ", "")
            new_grid_mode = combo_text if combo_text else self.last_active_grid_mode

        # 2. 상태 변경이 있는지 확인 후 업데이트
        if self.compare_mode_active != new_compare_active or self.grid_mode != new_grid_mode:
            self.compare_mode_active = new_compare_active
            self.grid_mode = new_grid_mode

            # UI 컨트롤 상태 동기화
            self.grid_size_combo.setEnabled(is_grid_on)

            # 뷰 업데이트
            self._update_view_for_grid_change()

    def _on_grid_size_changed(self, text):
        """Grid 크기 콤보박스 변경 시 호출"""
        new_mode = text.replace(" ", "")
        self.last_active_grid_mode = new_mode
        
        # <<< 수정: 콤보박스 변경은 항상 Grid On 상태를 의미하도록 함 >>>
        if not self.grid_on_radio.isChecked():
            self.grid_on_radio.setChecked(True)
            # setChecked(True)가 _on_grid_mode_toggled를 호출하므로,
            # 여기서 grid_mode를 직접 바꾸는 대신 토글 함수에 맡깁니다.
            # _on_grid_mode_toggled 함수가 올바른 new_mode를 설정할 것입니다.
            return # _on_grid_mode_toggled가 나머지 처리를 할 것이므로 여기서 종료

        # 이미 Grid On 상태에서 콤보박스만 변경된 경우
        if self.grid_mode != new_mode:
            self.grid_mode = new_mode
            self._update_view_for_grid_change()

    def _update_view_for_grid_change(self):
        """Grid/Compare 모드 변경에 따른 공통 UI 업데이트 로직 (최종 수정)"""
        logging.debug(f"View change triggered. Target Grid mode: {self.grid_mode}, Compare mode: {self.compare_mode_active}")
        
        # 뷰 크기 및 버튼 위치를 업데이트하는 내부 함수
        def update_ui_after_resize():
            if self.compare_mode_active:
                splitter_width = self.view_splitter.width()
                self.view_splitter.setSizes([splitter_width // 2, splitter_width // 2])
                padding = 10
                btn_size = self.close_compare_button.width()
                new_x = self.scroll_area_B.width() - btn_size - padding
                new_y = padding
                self.close_compare_button.move(new_x, new_y)
                self.close_compare_button.raise_()
            else:
                self.view_splitter.setSizes([self.view_splitter.width(), 0])
            self.apply_zoom_to_image()

        # 모드에 따른 상태 설정
        if self.compare_mode_active:
            self.scroll_area_B.show()
            self.close_compare_button.show()
            if not self.image_B_path:
                self.image_label_B.setText(LanguageManager.translate("비교할 이미지를 썸네일 패널에서 이곳으로 드래그하세요."))
            self.grid_mode = "Off"
        else:
            self.scroll_area_B.hide()
            self.close_compare_button.hide()
            self.image_B_path = None
            self.original_pixmap_B = None
            self.image_label_B.clear()

        QTimer.singleShot(10, update_ui_after_resize)
        self.update_thumbnail_panel_visibility()

        # <<< 핵심 수정: 모드에 따라 인덱스 관리 로직 분리 >>>
        if self.grid_mode != "Off": # Grid On으로 전환/유지
            if self.zoom_mode != "Fit":
                self.zoom_mode = "Fit"
                self.fit_radio.setChecked(True)
            # current_image_index를 기준으로 그리드 페이지 계산
            if self.current_image_index != -1:
                rows, cols = self._get_grid_dimensions()
                if rows > 0:
                    num_cells = rows * cols
                    self.grid_page_start_index = (self.current_image_index // num_cells) * num_cells
                    self.current_grid_index = self.current_image_index % num_cells
            self.selected_grid_indices.clear()
            self.selected_grid_indices.add(self.current_grid_index)
            self.primary_selected_index = self.grid_page_start_index + self.current_grid_index
            self.last_single_click_index = self.current_grid_index
        else: # Grid Off 또는 Compare 모드로 전환/유지
            # 현재 self.current_image_index 값을 그대로 유지하는 것이 원칙.
            # Grid -> Off 전환 시에만 인덱스를 그리드로부터 가져옴.
            if not self.compare_mode_active: # Compare 모드가 아닐 때만
                if self.image_files:
                    # primary_selected_index는 그리드에서만 유효하므로, 여기서 사용
                    if self.primary_selected_index != -1:
                        global_idx = self.primary_selected_index
                        self.current_image_index = global_idx if 0 <= global_idx < len(self.image_files) else 0
                        self.primary_selected_index = -1 # Grid Off 모드에서는 초기화
                else:
                    self.current_image_index = -1
            self.force_refresh = True
        
        self.update_grid_view()
        self.update_zoom_radio_buttons_state()
        self.update_counter_layout()
        self.update_compare_filenames()

    def update_compare_filenames(self):
        """Compare 모드에서 A, B 캔버스의 파일명 라벨을 업데이트합니다."""
        # 1. Compare 모드가 아니거나, 파일명 표시 옵션이 꺼져있으면 라벨을 숨기고 종료합니다.
        if not self.compare_mode_active or not self.show_grid_filenames:
            self.filename_label_A.hide()
            self.filename_label_B.hide()
            return

        padding = UIScaleManager.get("compare_filename_padding", 10)

        # 2. A 캔버스 파일명 라벨 업데이트
        # A 캔버스에 유효한 이미지가 표시되고 있는지 확인합니다.
        if self.original_pixmap and 0 <= self.current_image_index < len(self.image_files):
            # 파일명을 라벨에 설정하고, 내용에 맞게 크기를 조절합니다.
            self.filename_label_A.setText(self.image_files[self.current_image_index].name)
            self.filename_label_A.adjustSize()
            # 좌측 상단에 위치시킵니다.
            self.filename_label_A.move(padding, padding)
            # 라벨을 보이게 하고, 다른 위젯 위에 오도록 합니다.
            self.filename_label_A.show()
            self.filename_label_A.raise_()
        else:
            # 이미지가 없으면 숨깁니다.
            self.filename_label_A.hide()

        # 3. B 캔버스 파일명 라벨 업데이트
        # B 캔버스에 이미지가 로드되었는지 확인합니다.
        if self.image_B_path:
            self.filename_label_B.setText(self.image_B_path.name)
            self.filename_label_B.adjustSize()
            self.filename_label_B.move(padding, padding)
            self.filename_label_B.show()
            self.filename_label_B.raise_()
        else:
            self.filename_label_B.hide()

    def _get_grid_dimensions(self):
        """현재 grid_mode에 맞는 (행, 열)을 반환합니다."""
        if self.grid_mode == '2x2':
            return 2, 2
        if self.grid_mode == '3x3':
            return 3, 3
        if self.grid_mode == '4x4':
            return 4, 4
        return 0, 0 # Grid Off 또는 예외 상황

    def update_zoom_radio_buttons_state(self):
        """그리드 모드에 따라 줌 라디오 버튼 활성화/비활성화"""
        if self.grid_mode != "Off":
            # 그리드 모드에서 100%, spin 비활성화
            self.zoom_100_radio.setEnabled(False)
            self.zoom_spin_btn.setEnabled(False)
            # 비활성화 스타일 적용
            disabled_radio_style = f"""
                QRadioButton {{
                    color: {ThemeManager.get_color('text_disabled')};
                    padding: {UIScaleManager.get("radiobutton_padding")}px;
                }}
                QRadioButton::indicator {{
                    width: {UIScaleManager.get("radiobutton_size")}px;
                    height: {UIScaleManager.get("radiobutton_size")}px;
                }}
                QRadioButton::indicator:checked {{
                    background-color: {ThemeManager.get_color('accent')};
                    border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('accent')};
                    border-radius: {UIScaleManager.get("radiobutton_border_radius")}px;
                }}
                QRadioButton::indicator:unchecked {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border: {UIScaleManager.get("radiobutton_border")}px solid {ThemeManager.get_color('border')};
                    border-radius: {UIScaleManager.get("radiobutton_border_radius")}px;
                }}
            """
            self.zoom_100_radio.setStyleSheet(disabled_radio_style)
            self.zoom_spin_btn.setStyleSheet(disabled_radio_style)
            
            # SpinBox 비활성화 스타일 적용
            disabled_spinbox_style = f"""
                QSpinBox {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                    color: {ThemeManager.get_color('text_disabled')};
                    border: 1px solid {ThemeManager.get_color('border')};
                    border-radius: 1px;
                    padding: 2px;
                }}
                QSpinBox::up-button, QSpinBox::down-button {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border: 1px solid {ThemeManager.get_color('border')};
                    width: 16px;
                }}
                QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                }}
                QSpinBox::up-arrow, QSpinBox::down-arrow {{
                    image: none;
                    width: 0px;
                    height: 0px;
                }}
            """
            self.zoom_spin.setStyleSheet(disabled_spinbox_style)
            
        else:
            # 그리드 모드가 아닐 때 모든 버튼 활성화
            self.zoom_100_radio.setEnabled(True)
            self.zoom_spin_btn.setEnabled(True)
            # 활성화 스타일 복원
            radio_style = ThemeManager.generate_radio_button_style()
            self.zoom_100_radio.setStyleSheet(radio_style)
            self.zoom_spin_btn.setStyleSheet(radio_style)
            
            # SpinBox 활성화 스타일 복원
            active_spinbox_style = f"""
                QSpinBox {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                    color: {ThemeManager.get_color('text')};
                    border: 1px solid {ThemeManager.get_color('border')};
                    border-radius: 1px;
                    padding: 2px;
                }}
                QSpinBox::up-button, QSpinBox::down-button {{
                    background-color: {ThemeManager.get_color('bg_primary')};
                    border: 1px solid {ThemeManager.get_color('border')};
                    width: 16px;
                }}
                QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                    background-color: {ThemeManager.get_color('bg_secondary')};
                }}
                QSpinBox::up-arrow, QSpinBox::down-arrow {{
                    image: none;
                    width: 0px;
                    height: 0px;
                }}
            """
            self.zoom_spin.setStyleSheet(active_spinbox_style)


    def grid_cell_mouse_press_event(self, event, widget, index):
        """Grid 셀 마우스 프레스 이벤트 - 드래그와 클릭을 함께 처리"""
        try:
            # === 우클릭 컨텍스트 메뉴 처리 ===
            if event.button() == Qt.RightButton and self.image_files:
                # 해당 셀에 이미지가 있는지 확인
                global_index = self.grid_page_start_index + index
                if 0 <= global_index < len(self.image_files):
                    # 우클릭한 셀이 이미 선택된 셀들 중 하나인지 확인
                    if index not in self.selected_grid_indices:
                        # 선택되지 않은 셀을 우클릭한 경우: 해당 셀만 선택
                        self.selected_grid_indices.clear()
                        self.selected_grid_indices.add(index)
                        self.primary_selected_index = global_index
                        self.current_grid_index = index
                        self.update_grid_selection_border()
                    # 이미 선택된 셀을 우클릭한 경우: 기존 선택 유지 (아무것도 하지 않음)
                    
                    # 컨텍스트 메뉴 표시
                    context_menu = self.create_context_menu(event.position().toPoint())
                    if context_menu:
                        context_menu.exec_(widget.mapToGlobal(event.position().toPoint()))
                return
            
            # === Fit 모드에서 드래그 앤 드롭 시작 준비 ===
            if (event.button() == Qt.LeftButton and 
                self.zoom_mode == "Fit" and 
                self.image_files and 
                0 <= self.current_image_index < len(self.image_files)):
                
                # 드래그 시작 준비
                widget.drag_start_pos = event.position().toPoint()
                widget.is_potential_drag = True
                logging.debug(f"Grid 셀에서 드래그 시작 준비: index {index}")
            
            # 기존 클릭 처리는 드래그가 시작되지 않으면 mouseReleaseEvent에서 처리
            widget._click_widget = widget
            widget._click_index = index
            widget._click_event = event
            
        except Exception as e:
            logging.error(f"grid_cell_mouse_press_event 오류: {e}")

    def grid_cell_mouse_move_event(self, event, widget, index):
        """Grid 셀 마우스 이동 이벤트 - 드래그 시작 감지"""
        try:
            # === Fit 모드에서 드래그 시작 감지 ===
            if (hasattr(widget, 'is_potential_drag') and 
                widget.is_potential_drag and 
                self.zoom_mode == "Fit" and 
                self.image_files and 
                0 <= self.current_image_index < len(self.image_files)):
                
                current_pos = event.position().toPoint()
                move_distance = (current_pos - widget.drag_start_pos).manhattanLength()
                
                if move_distance > getattr(widget, 'drag_threshold', 10):
                    # 드래그 시작 - 드래그된 셀의 인덱스 전달
                    self.start_image_drag(dragged_grid_index=index)
                    widget.is_potential_drag = False
                    logging.debug(f"Grid 셀에서 드래그 시작됨: index {index}")
                    return
            
        except Exception as e:
            logging.error(f"grid_cell_mouse_move_event 오류: {e}")

    def grid_cell_mouse_release_event(self, event, widget, index):
        """Grid 셀 마우스 릴리스 이벤트 - 드래그 상태 초기화 및 클릭 처리"""
        try:
            # 드래그 상태 초기화
            if hasattr(widget, 'is_potential_drag') and widget.is_potential_drag:
                widget.is_potential_drag = False
                
                # 드래그가 시작되지 않았으면 클릭으로 처리
                if (hasattr(widget, '_click_widget') and 
                    hasattr(widget, '_click_index') and 
                    hasattr(widget, '_click_event')):
                    
                    # 기존 클릭 처리 로직 호출
                    self.on_grid_cell_clicked(widget._click_widget, widget._click_index)
                    
                    # 임시 변수 정리
                    delattr(widget, '_click_widget')
                    delattr(widget, '_click_index')
                    delattr(widget, '_click_event')
                
                logging.debug(f"Grid 셀에서 드래그 시작 준비 상태 해제: index {index}")
            
        except Exception as e:
            logging.error(f"grid_cell_mouse_release_event 오류: {e}")

    def update_grid_view(self):
        """Grid 모드에 따라 이미지 뷰를 동기적으로 재구성합니다. (최종 안정화 버전)"""
        # 1. 모든 관련 비동기 작업을 중단시킵니다.
        self.image_loader.cancel_loading()
        if hasattr(self, 'loading_indicator_timer') and self.loading_indicator_timer.isActive():
            self.loading_indicator_timer.stop()

        # 2. scroll_area에서 현재 위젯을 분리합니다.
        current_view_widget = self.scroll_area.takeWidget()

        # 3. Grid Off 또는 Compare 모드일 경우
        if self.grid_mode == "Off":
            # 이전에 그리드 뷰가 있었다면 삭제합니다.
            if current_view_widget and current_view_widget is not self.image_container:
                current_view_widget.deleteLater()
            
            # 영구적인 image_container를 scroll_area에 다시 설정합니다.
            self.scroll_area.setWidget(self.image_container)
            self.force_refresh = True
            self.display_current_image()
            return

        # 4. Grid On 모드일 경우 (새 그리드 생성)
        # 이전에 단일 뷰(image_container)가 있었다면, 부모 관계만 끊어 재사용할 수 있도록 보존합니다.
        if current_view_widget and current_view_widget is self.image_container:
            current_view_widget.setParent(None)
        
        self.grid_labels.clear()
        self.grid_layout = None

        # 새로운 그리드 UI 구조를 생성합니다.
        rows, cols = self._get_grid_dimensions()
        if rows == 0: return

        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(0)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_container_widget = QWidget() # 그리드 뷰는 항상 새로 생성
        grid_container_widget.setLayout(self.grid_layout)
        grid_container_widget.setStyleSheet("background-color: black;")
        self.scroll_area.setWidget(grid_container_widget) # 새로 만든 그리드를 scroll_area에 설정
        self.scroll_area.setWidgetResizable(True)

        num_cells = rows * cols
        # ... (이하 그리드 셀을 생성하고 채우는 로직은 이전과 동일) ...
        start_idx = self.grid_page_start_index
        end_idx = min(start_idx + num_cells, len(self.image_files))
        images_to_display = self.image_files[start_idx:end_idx]

        if self.current_grid_index >= len(images_to_display) and len(images_to_display) > 0:
             self.current_grid_index = len(images_to_display) - 1
        elif len(images_to_display) == 0:
             self.current_grid_index = 0

        for i in range(num_cells):
            row, col = divmod(i, cols)
            cell_widget = GridCellWidget(parent=grid_container_widget)
            from functools import partial
            cell_widget.mousePressEvent = partial(self.grid_cell_mouse_press_event, widget=cell_widget, index=i)
            cell_widget.mouseMoveEvent = partial(self.grid_cell_mouse_move_event, widget=cell_widget, index=i)
            cell_widget.mouseReleaseEvent = partial(self.grid_cell_mouse_release_event, widget=cell_widget, index=i)
            cell_widget.mouseDoubleClickEvent = partial(self.on_grid_cell_double_clicked, clicked_widget=cell_widget, clicked_index=i)
            
            if i < len(images_to_display):
                current_image_path_obj = images_to_display[i]
                current_image_path = str(current_image_path_obj)
                cell_widget.setProperty("image_path", current_image_path)
                cell_widget.setPixmap(self.placeholder_pixmap)
            
            self.grid_layout.addWidget(cell_widget, row, col)
            self.grid_labels.append(cell_widget)

        # 5. 새로운 UI가 완전히 준비된 후, 새로운 비동기 작업을 시작합니다.
        self.update_grid_selection_border()
        self.update_window_title_with_selection()
        
        self.image_loader.preload_page(self.image_files, self.grid_page_start_index, num_cells, strategy_override="preview")
        
        QTimer.singleShot(0, self.resize_grid_images)

        selected_image_list_index_gw = self.grid_page_start_index + self.current_grid_index
        if 0 <= selected_image_list_index_gw < len(self.image_files):
            self.update_file_info_display(str(self.image_files[selected_image_list_index_gw]))
        else:
            self.update_file_info_display(None)
        
        self.update_counters()
        if self.grid_mode != "Off" and self.image_files:
            self.state_save_timer.start()

    def on_filename_toggle_changed(self, checked):
        """그리드 파일명 표시 토글 상태 변경 시 호출"""
        self.show_grid_filenames = checked
        logging.debug(f"Grid Filename Toggle: {'On' if checked else 'Off'}")

        # Grid 모드이고, 그리드 라벨(이제 GridCellWidget)들이 존재할 때만 업데이트
        if self.grid_mode != "Off" and self.grid_labels:
            for cell_widget in self.grid_labels:
                # 1. 각 GridCellWidget에 파일명 표시 상태를 설정합니다.
                cell_widget.setShowFilename(checked)
                
                # 2. (중요) 파일명 텍스트를 다시 설정합니다.
                #    show_grid_filenames 상태가 변경되었으므로,
                #    표시될 텍스트 내용 자체가 바뀔 수 있습니다 (보이거나 안 보이거나).
                #    이 로직은 resize_grid_images나 update_grid_view에서 가져올 수 있습니다.
                image_path = cell_widget.property("image_path")
                filename_text = ""
                if image_path and checked: # checked (self.show_grid_filenames) 상태를 사용
                    filename = Path(image_path).name
                    # 파일명 축약 로직 (GridCellWidget의 paintEvent에서 하는 것이 더 정확할 수 있으나, 여기서도 처리)
                    # font_metrics를 여기서 가져오기 어려우므로, 간단한 길이 기반 축약 사용
                    if len(filename) > 20: # 예시 길이
                        filename = filename[:10] + "..." + filename[-7:]
                    filename_text = filename
                cell_widget.setText(filename_text) # 파일명 텍스트 업데이트

                # 3. 각 GridCellWidget의 update()를 호출하여 즉시 다시 그리도록 합니다.
                #    setShowFilename 내부에서 update()를 호출했다면 이 줄은 필요 없을 수 있지만,
                #    명시적으로 호출하여 확실하게 합니다.
                #    (GridCellWidget의 setShowFilename, setText 메서드에서 이미 update()를 호출한다면 중복될 수 있으니 확인 필요)
                cell_widget.update() # paintEvent를 다시 호출하게 함
        elif self.compare_mode_active:
            self.update_compare_filenames()

        # Grid Off 모드에서는 이 설정이 현재 뷰에 직접적인 영향을 주지 않으므로
        # 별도의 즉각적인 뷰 업데이트는 필요하지 않습니다.
        # (다음에 Grid On으로 전환될 때 self.show_grid_filenames 상태가 반영됩니다.)

    def on_image_loaded(self, cell_index, pixmap, img_path):
            """비동기 이미지 로딩 완료 시 호출되는 슬롯"""
            if self.grid_mode == "Off" or not self.grid_labels:
                return
                
            if 0 <= cell_index < len(self.grid_labels):
                cell_widget = self.grid_labels[cell_index] # 이제 GridCellWidget
                # GridCellWidget의 경로와 일치하는지 확인
                if cell_widget.property("image_path") == img_path:
                    cell_widget.setProperty("original_pixmap_ref", pixmap) # 원본 참조 저장
                    cell_widget.setPixmap(pixmap) # setPixmap 호출 (내부에서 update 트리거)
                    cell_widget.setProperty("loaded", True)

                    # 파일명도 여기서 다시 설정해줄 수 있음 (선택적)
                    if self.show_grid_filenames:
                        filename = Path(img_path).name
                        if len(filename) > 20:
                            filename = filename[:10] + "..." + filename[-7:]
                        cell_widget.setText(filename)
                    cell_widget.setShowFilename(self.show_grid_filenames) # 파일명 표시 상태 업데이트

    def resize_grid_images(self):
        """그리드 셀 크기에 맞춰 이미지 리사이징 (고품질) 및 파일명 업데이트"""
        if not self.grid_labels or self.grid_mode == "Off":
            return

        for cell_widget in self.grid_labels: # 이제 GridCellWidget
            image_path = cell_widget.property("image_path")
            original_pixmap_ref = cell_widget.property("original_pixmap_ref") # 저장된 원본 참조 가져오기

            if image_path and original_pixmap_ref and isinstance(original_pixmap_ref, QPixmap) and not original_pixmap_ref.isNull():
                # GridCellWidget의 setPixmap은 내부적으로 update()를 호출하므로,
                # 여기서 setPixmap을 다시 호출하면 paintEvent가 실행되어 스케일링된 이미지가 그려짐.
                # paintEvent에서 rect.size()를 사용하므로 별도의 스케일링 호출은 불필요.
                # cell_widget.setPixmap(original_pixmap_ref) # 이렇게만 해도 paintEvent에서 처리
                cell_widget.update() # 강제 리페인트 요청으로도 충분할 수 있음
            elif image_path:
                # 플레이스홀더가 이미 설정되어 있거나, 다시 설정
                # cell_widget.setPixmap(self.placeholder_pixmap)
                cell_widget.update()
            else:
                # cell_widget.setPixmap(QPixmap())
                cell_widget.update()

            # 파일명 업데이트 (필요시) - GridCellWidget의 paintEvent에서 처리하므로 여기서 직접 할 필요는 없을 수도 있음
            if self.show_grid_filenames and image_path:
                filename = Path(image_path).name
                # 파일명 축약은 GridCellWidget.paintEvent 내에서 하는 것이 더 정확함
                # (현재 위젯 크기를 알 수 있으므로)
                # 여기서는 setShowFilename 상태만 전달
                if len(filename) > 20:
                    filename = filename[:10] + "..." + filename[-7:]
                cell_widget.setText(filename) # 텍스트 설정
            else:
                cell_widget.setText("")
            cell_widget.setShowFilename(self.show_grid_filenames) # 상태 전달
            # cell_widget.update() # setShowFilename 후에도 업데이트

        self.update_grid_selection_border() # 테두리 업데이트는 별도

    def update_grid_selection_border(self):
        """선택된 그리드 셀들의 테두리 업데이트 (다중 선택 지원)"""
        if not self.grid_labels or self.grid_mode == "Off":
            return

        for i, cell_widget in enumerate(self.grid_labels): # 이제 GridCellWidget
            if i in self.selected_grid_indices:
                cell_widget.setSelected(True)
            else:
                cell_widget.setSelected(False)

    def get_primary_grid_cell_index(self):
        """primary 선택의 페이지 내 인덱스를 반환 (기존 current_grid_index 호환성용)"""
        if self.primary_selected_index != -1:
            return self.primary_selected_index - self.grid_page_start_index
        return 0

    def clear_grid_selection(self, preserve_current_index=False):
        """그리드 선택 상태 초기화"""
        self.selected_grid_indices.clear()
        self.primary_selected_index = -1
        
        # preserve_current_index가 True이면 현재 인덱스 유지
        if not preserve_current_index:
            self.current_grid_index = 0
        
        # 현재 위치를 단일 선택으로 설정 (빈 폴더가 아닌 경우)
        if (self.grid_mode != "Off" and self.image_files and 
            0 <= self.grid_page_start_index + self.current_grid_index < len(self.image_files)):
            self.selected_grid_indices.add(self.current_grid_index)
            self.primary_selected_index = self.grid_page_start_index + self.current_grid_index
        
        self.update_grid_selection_border()
        self.update_window_title_with_selection()

    def toggle_select_all_in_page(self):
        """현재 페이지의 모든 이미지 선택/해제 토글"""
        if self.grid_mode == "Off" or not self.image_files:
            return
        
        rows, cols = self._get_grid_dimensions()
        if rows == 0: return

        num_cells = rows * cols
        
        # 현재 페이지에 실제로 있는 이미지 수 계산
        current_page_image_count = min(num_cells, len(self.image_files) - self.grid_page_start_index)
        
        if current_page_image_count <= 0:
            return
        
        # 현재 페이지의 모든 셀이 선택되어 있는지 확인
        all_selected = True
        for i in range(current_page_image_count):
            if i not in self.selected_grid_indices:
                all_selected = False
                break
        
        if all_selected:
            # 모두 선택되어 있으면 모두 해제
            self.selected_grid_indices.clear()
            self.primary_selected_index = -1
            logging.info("전체 선택 해제")
        else:
            # 일부만 선택되어 있거나 선택이 없으면 모두 선택
            self.selected_grid_indices.clear()
            for i in range(current_page_image_count):
                self.selected_grid_indices.add(i)
            
            # 첫 번째 이미지를 primary로 설정
            self.primary_selected_index = self.grid_page_start_index
            logging.info(f"전체 선택: {current_page_image_count}개 이미지")
        
        # UI 업데이트
        self.update_grid_selection_border()
        self.update_window_title_with_selection()
        
        # 파일 정보 업데이트
        if self.primary_selected_index != -1 and 0 <= self.primary_selected_index < len(self.image_files):
            selected_image_path = str(self.image_files[self.primary_selected_index])
            self.update_file_info_display(selected_image_path)
        else:
            self.update_file_info_display(None)

    def update_window_title_with_selection(self):
        """그리드 모드에서 창 제목 업데이트 (다중/단일 선택 모두 지원)"""
        if self.grid_mode == "Off":
             # Grid Off 모드에서는 display_current_image에서 처리
             return

        total_images = len(self.image_files)
        
        # 다중 선택 상태 확인
        if hasattr(self, 'selected_grid_indices') and self.selected_grid_indices:
            selected_count = len(self.selected_grid_indices)
            if selected_count > 1:
                # 다중 선택: 개수 표시
                if hasattr(self, 'original_title'):
                    title = f"{self.original_title} - 선택됨: {selected_count}개"
                else:
                    self.original_title = "PhotoSort"
                    title = f"{self.original_title} - 선택됨: {selected_count}개"
            else:
                # 단일 선택: 파일명 표시
                if self.primary_selected_index != -1 and 0 <= self.primary_selected_index < total_images:
                    selected_filename = self.image_files[self.primary_selected_index].name
                    title = f"PhotoSort - {selected_filename}"
                else:
                    title = "PhotoSort"
        else:
            # 기존 단일 선택 방식 (호환성)
            selected_image_list_index = self.grid_page_start_index + self.current_grid_index
            if 0 <= selected_image_list_index < total_images:
                selected_filename = self.image_files[selected_image_list_index].name
                title = f"PhotoSort - {selected_filename}"
            else:
                title = "PhotoSort"

        self.setWindowTitle(title)


    def navigate_grid(self, delta):
        """Grid 셀 간 이동 및 페이지 전환 처리 (다중 선택 시 단일 선택으로 변경)"""
        if not self.image_files or self.grid_mode == "Off":
            return

        total_images = len(self.image_files)
        if total_images <= 0: return # 이미지가 없으면 중단

        rows, cols = self._get_grid_dimensions()
        if rows == 0: return
        num_cells = rows * cols

        # 현재 페이지의 셀 개수 계산 (마지막 페이지는 다를 수 있음)
        current_page_first_image_index = self.grid_page_start_index
        current_page_last_possible_image_index = min(current_page_first_image_index + num_cells - 1, total_images - 1)
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
            
            # 키보드 네비게이션 시 다중 선택을 단일 선택으로 변경
            if hasattr(self, 'selected_grid_indices'):
                self.selected_grid_indices.clear()
                self.selected_grid_indices.add(new_grid_index)
                self.primary_selected_index = self.grid_page_start_index + new_grid_index
                logging.debug(f"키보드 네비게이션: 단일 선택으로 변경 - index {new_grid_index}")
            
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
            # 페이지 변경 시에도 다중 선택을 단일 선택으로 변경
            if hasattr(self, 'selected_grid_indices'):
                self.selected_grid_indices.clear()
                self.selected_grid_indices.add(self.current_grid_index)
                self.primary_selected_index = self.grid_page_start_index + self.current_grid_index
                logging.debug(f"페이지 변경: 단일 선택으로 변경 - index {self.current_grid_index}")
            
            # 페이지 변경/순환 시에는 update_grid_view가 모든 UI 업데이트를 처리
            self.update_grid_view()
            logging.debug(f"Navigating grid: Page changed to start index {self.grid_page_start_index}, grid index {self.current_grid_index}") # 디버깅 로그

    def move_grid_image(self, folder_index):
        """Grid 모드에서 선택된 이미지(들)를 지정된 폴더로 이동 (다중 선택 지원)"""
        if self.grid_mode == "Off" or not self.grid_labels:
            return
        
        if hasattr(self, 'selected_grid_indices') and self.selected_grid_indices:
            selected_global_indices = []
            for grid_index in self.selected_grid_indices:
                global_index = self.grid_page_start_index + grid_index
                if 0 <= global_index < len(self.image_files):
                    selected_global_indices.append(global_index)
            if not selected_global_indices:
                logging.warning("선택된 이미지가 없습니다.")
                return
            logging.info(f"다중 이미지 이동 시작: {len(selected_global_indices)}개 파일")
        else:
            image_list_index = self.grid_page_start_index + self.current_grid_index
            if not (0 <= image_list_index < len(self.image_files)):
                logging.warning("선택된 셀에 이동할 이미지가 없습니다.")
                return
            selected_global_indices = [image_list_index]
            logging.info(f"단일 이미지 이동: index {image_list_index}")
            
        target_folder = self.target_folders[folder_index]
        if not target_folder or not os.path.isdir(target_folder):
            return
            
        selected_global_indices.sort(reverse=True)
        
        show_progress = len(selected_global_indices) >= 2
        progress_dialog = None
        if show_progress:
            progress_dialog = QProgressDialog(
                LanguageManager.translate("이미지 이동 중..."),
                "", 
                0, len(selected_global_indices), self
            )
            progress_dialog.setCancelButton(None)
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.show()
            QApplication.processEvents()

        successful_moves = []
        failed_moves = []
        move_history_entries = []
        user_canceled = False
        try:
            for idx, global_index in enumerate(selected_global_indices):
                if show_progress and progress_dialog:
                    progress_dialog.setValue(idx)
                    if progress_dialog.wasCanceled():
                        logging.info("사용자가 이동 작업을 취소했습니다.")
                        user_canceled = True
                        break
                    QApplication.processEvents()
                
                if global_index >= len(self.image_files):
                    continue
                
                current_image_path = self.image_files[global_index]
                moved_jpg_path = None
                moved_raw_path = None
                raw_path_before_move = None
                
                try:
                    moved_jpg_path = self.move_file(current_image_path, target_folder)
                    if moved_jpg_path is None:
                        failed_moves.append(current_image_path.name)
                        logging.error(f"파일 이동 실패: {current_image_path.name}")
                        continue
                    
                    raw_moved_successfully = True
                    if self.move_raw_files:
                        base_name = current_image_path.stem
                        if base_name in self.raw_files:
                            raw_path_before_move = self.raw_files[base_name]
                            moved_raw_path = self.move_file(raw_path_before_move, target_folder)
                            if moved_raw_path is None:
                                logging.warning(f"RAW 파일 이동 실패: {raw_path_before_move.name}")
                                raw_moved_successfully = False
                            else:
                                del self.raw_files[base_name]
                    
                    self.image_files.pop(global_index)
                    successful_moves.append(moved_jpg_path.name)
                    
                    if moved_jpg_path:
                        history_entry = {
                            "jpg_source": str(current_image_path),
                            "jpg_target": str(moved_jpg_path),
                            "raw_source": str(raw_path_before_move) if raw_path_before_move else None,
                            "raw_target": str(moved_raw_path) if moved_raw_path and raw_moved_successfully else None,
                            "index_before_move": global_index,
                            "mode": self.grid_mode
                        }
                        move_history_entries.append(history_entry)
                except Exception as e:
                    failed_moves.append(current_image_path.name)
                    logging.error(f"이미지 이동 중 오류 발생 ({current_image_path.name}): {str(e)}")
            
            if show_progress and progress_dialog:
                progress_dialog.close()
                progress_dialog = None

            if user_canceled:
                if successful_moves:
                    msg_template = LanguageManager.translate("작업 취소됨.\n성공: {success_count}개, 실패: {fail_count}개")
                    message = msg_template.format(success_count=len(successful_moves), fail_count=len(failed_moves))
                    self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("경고"), message)
            elif successful_moves and failed_moves:
                msg_template = LanguageManager.translate("성공: {success_count}개\n실패: {fail_count}개")
                message = msg_template.format(success_count=len(successful_moves), fail_count=len(failed_moves))
                self.show_themed_message_box(QMessageBox.Warning, LanguageManager.translate("경고"), message)
            elif failed_moves:
                msg_template = LanguageManager.translate("모든 파일 이동 실패: {fail_count}개")
                message = msg_template.format(fail_count=len(failed_moves))
                self.show_themed_message_box(QMessageBox.Critical, LanguageManager.translate("에러"), message)
            
            ### 변경 시작: num_cells 계산 방식 수정 ###
            rows, cols = self._get_grid_dimensions()
            num_cells = rows * cols
            ### 변경 끝 ###
            
            if hasattr(self, 'selected_grid_indices'):
                self.clear_grid_selection(preserve_current_index=True)
                
            current_page_image_count = min(num_cells, len(self.image_files) - self.grid_page_start_index)
            if self.current_grid_index >= current_page_image_count and current_page_image_count > 0:
                self.current_grid_index = current_page_image_count - 1
            if current_page_image_count == 0 and len(self.image_files) > 0:
                self.grid_page_start_index = max(0, self.grid_page_start_index - num_cells)
                new_page_image_count = min(num_cells, len(self.image_files) - self.grid_page_start_index)
                self.current_grid_index = max(0, new_page_image_count - 1)
            
            self.update_grid_view()
            
            if not self.image_files:
                self.grid_mode = "Off"
                self.grid_off_radio.setChecked(True)
                self.update_grid_view()
                if self.minimap_visible:
                    self.minimap_widget.hide()
                    self.minimap_visible = False
                if self.session_management_popup and self.session_management_popup.isVisible():
                    self.session_management_popup.update_all_button_states()
                self.show_themed_message_box(QMessageBox.Information, LanguageManager.translate("완료"), LanguageManager.translate("모든 이미지가 분류되었습니다."))
            
            self.update_counters()
        except Exception as e:
            if show_progress and progress_dialog:
                progress_dialog.close()
            self.show_themed_message_box(QMessageBox.Critical, LanguageManager.translate("에러"), f"{LanguageManager.translate('파일 이동 중 오류 발생')}: {str(e)}")
        
        if move_history_entries:
            if len(move_history_entries) == 1:
                self.add_move_history(move_history_entries[0])
                logging.info(f"단일 이동 히스토리 추가: 1개 항목")
            else:
                self.add_batch_move_history(move_history_entries)
                logging.info(f"배치 이동 히스토리 추가: {len(move_history_entries)}개 항목")


    def on_grid_cell_double_clicked(self, event, clicked_widget, clicked_index): # 파라미터 이름을 clicked_widget으로
        """그리드 셀 더블클릭 시 Grid Off 모드로 전환"""
        if self.grid_mode == "Off" or not self.grid_labels:
            logging.debug("Grid Off 모드이거나 그리드 레이블이 없어 더블클릭 무시")
            return
        
        try:
            # 현재 페이지에 실제로 표시될 수 있는 이미지의 총 개수
            current_page_image_count = min(len(self.grid_labels), len(self.image_files) - self.grid_page_start_index)
            
            # 클릭된 인덱스가 유효한 범위 내에 있고, 해당 인덱스에 해당하는 이미지가 실제로 존재하는지 확인
            if 0 <= clicked_index < current_page_image_count:
                # clicked_widget은 GridCellWidget 인스턴스여야 합니다.
                # 해당 셀에 연결된 image_path가 있는지 확인하여 유효한 이미지 셀인지 판단합니다.
                image_path_property = clicked_widget.property("image_path")

                if image_path_property: # 이미지 경로가 있다면 유효한 셀로 간주
                    logging.debug(f"셀 더블클릭: index {clicked_index}, path {image_path_property}")
                    # 해당 셀에 이미지가 있는지 확인 (실제 픽스맵이 로드되었는지는 여기서 중요하지 않음)
                    # GridCellWidget의 pixmap()이 null이 아닌지 확인할 수도 있지만, image_path로 충분
                    
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
                    self.grid_off_radio.setChecked(True) # 라디오 버튼 상태 업데이트
                    
                    self.update_thumbnail_panel_visibility()
                    # Grid Off 모드로 변경 및 이미지 표시
                    # update_grid_view()가 내부적으로 display_current_image() 호출
                    self.update_grid_view()

                    # 썸네일 패널 동기화 추가
                    self.update_thumbnail_current_index()

                    
                    # 이미지 로더의 캐시 확인하여 이미 메모리에 있으면 즉시 적용을 시도
                    # (display_current_image 내에서 이미 처리될 수 있지만, 명시적으로도 가능)
                    if 0 <= self.current_image_index < len(self.image_files):
                        image_path = str(self.image_files[self.current_image_index])
                        if image_path in self.image_loader.cache:
                            cached_pixmap = self.image_loader.cache[image_path]
                            if cached_pixmap and not cached_pixmap.isNull():
                                self.original_pixmap = cached_pixmap
                                # Fit 모드인 경우 apply_zoom_to_image를 호출하여 즉시 반영
                                if self.zoom_mode == "Fit":
                                    self.apply_zoom_to_image()
                    
                    # 줌 라디오 버튼 상태 업데이트 (활성화)
                    self.update_zoom_radio_buttons_state()
                    self.update_counter_layout() # 레이아웃 업데이트 호출
                    
                    # 이중 이벤트 방지를 위해 클릭 이벤트 상태 초기화 (이 부분은 원래 없었으므로 제거 가능)
                    # self.click_timer = None
                else:
                    logging.debug(f"빈 셀 더블클릭됨 (이미지 경로 없음): index {clicked_index}")
            else:
                 logging.debug(f"유효하지 않은 셀 더블클릭됨 (인덱스 범위 초과): index {clicked_index}, page_img_count {current_page_image_count}")

        except Exception as e:
            logging.error(f"그리드 셀 더블클릭 처리 중 오류 발생: {e}")
            import traceback
            traceback.print_exc() # 상세 오류 로깅
        finally:
            # self.update_counters() # update_counter_layout() 내부에서 호출되므로 중복 가능성 있음
            pass


    def image_mouse_double_click_event(self, event: QMouseEvent):
        if self.grid_mode == "Off" and self.original_pixmap:
            current_image_path_str = str(self.image_files[self.current_image_index]) if 0 <= self.current_image_index < len(self.image_files) else None
            current_orientation = self.current_image_orientation
            if self.zoom_mode == "Fit":
                self.double_click_pos = event.position().toPoint()
                # <<< 수정 시작: target_widget 인자 추가 >>>
                scaled_fit_pixmap = self.high_quality_resize_to_fit(self.original_pixmap, self.scroll_area)
                # <<< 수정 끝 >>>
                view_width = self.scroll_area.width()
                view_height = self.scroll_area.height()
                fit_img_width = scaled_fit_pixmap.width()
                fit_img_height = scaled_fit_pixmap.height()
                fit_img_rect_in_view = QRect(
                    (view_width - fit_img_width) // 2, (view_height - fit_img_height) // 2,
                    fit_img_width, fit_img_height
                )
                click_x_vp = self.double_click_pos.x()
                click_y_vp = self.double_click_pos.y()
                if fit_img_rect_in_view.contains(int(click_x_vp), int(click_y_vp)):
                    target_zoom_mode = self.last_active_zoom_mode
                    logging.debug(f"더블클릭: Fit -> {target_zoom_mode} 요청")
                    current_orientation = self.current_image_orientation
                    if current_orientation:
                        saved_rel_center, _ = self._get_orientation_viewport_focus(current_orientation, target_zoom_mode)
                        self.current_active_rel_center = saved_rel_center
                    else:
                        self.current_active_rel_center = QPointF(0.5, 0.5)
                    self.current_active_zoom_level = target_zoom_mode
                    self.zoom_change_trigger = "double_click"
                    self.zoom_mode = target_zoom_mode
                    if target_zoom_mode == "100%":
                        self.zoom_100_radio.setChecked(True)
                    elif target_zoom_mode == "Spin":
                        self.zoom_spin_btn.setChecked(True)
                    self.apply_zoom_to_image() 
                    self.toggle_minimap(self.minimap_toggle.isChecked())
                else:
                    logging.debug("더블클릭 위치가 이미지 바깥입니다 (Fit 모드).")
            elif self.zoom_mode in ["100%", "Spin"]:
                logging.debug(f"더블클릭: {self.zoom_mode} -> Fit 요청")
                current_orientation = self.current_image_orientation
                if current_orientation:
                    current_rel_center = self._get_current_view_relative_center()
                    logging.debug(f"더블클릭 뷰포트 위치 저장: {current_orientation} -> {current_rel_center}")
                    self.current_active_rel_center = current_rel_center
                    self.current_active_zoom_level = self.zoom_mode
                    self._save_orientation_viewport_focus(
                        current_orientation,
                        current_rel_center,
                        self.zoom_mode
                    )
                self.last_active_zoom_mode = self.zoom_mode
                logging.debug(f"Last active zoom mode updated to: {self.last_active_zoom_mode}")
                self.zoom_mode = "Fit"
                self.current_active_rel_center = QPointF(0.5, 0.5)
                self.current_active_zoom_level = "Fit"
                self.fit_radio.setChecked(True)
                self.apply_zoom_to_image()


    def reset_program_state(self):
        """프로그램 상태를 초기화 (Delete 키)"""
        reply = self.show_themed_message_box(QMessageBox.Question, 
                                    LanguageManager.translate("프로그램 초기화"),
                                    LanguageManager.translate("로드된 파일과 현재 작업 상태를 초기화하시겠습니까?"),
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 핵심 초기화 로직을 헬퍼 메서드로 이동
            self._reset_workspace()

            self.grid_mode = "Off" # grid_mode를 명시적으로 Off로 설정
            self.grid_off_radio.setChecked(True)
            self._update_view_for_grid_change() # 뷰를 강제로 업데이트
            
            # 추가적으로 UI 컨트롤 상태를 기본값으로 설정
            self.zoom_mode = "Fit"
            self.fit_radio.setChecked(True)
            self.zoom_spin_value = 2.0
            if hasattr(self, 'zoom_spin'):
                self.zoom_spin.setValue(int(self.zoom_spin_value * 100))
            
            self.grid_mode = "Off"
            self.grid_off_radio.setChecked(True)

            self.update_zoom_radio_buttons_state()
            self.update_counter_layout()
            self.toggle_minimap(self.minimap_toggle.isChecked())

            self.save_state() 
            if self.session_management_popup and self.session_management_popup.isVisible():
                self.session_management_popup.update_all_button_states()
            logging.info("프로그램 상태 초기화 완료 (카메라별 RAW 설정은 유지됨).")
        else:
            logging.info("프로그램 초기화 취소됨")

    def _reset_workspace(self):
        """로드된 파일과 현재 작업 상태를 초기화하는 핵심 로직."""
        logging.info("작업 공간 초기화 시작...")
        # 1. 백그라운드 작업 취소
        self.resource_manager.cancel_all_tasks()
        for future in self.image_loader.active_futures:
            future.cancel()
        self.image_loader.active_futures.clear()
        for future in self.active_thumbnail_futures:
            future.cancel()
        self.active_thumbnail_futures.clear()
        # 2. Undo/Redo 히스토리 초기화
        self.move_history = []
        self.history_pointer = -1
        # 3. 상태 변수 초기화 (이미지 목록을 먼저 비웁니다)
        self.image_files = [] # <<< 중요: UI 업데이트 전에 데이터부터 비웁니다.
        self.current_folder = ""
        self.raw_folder = ""
        self.raw_files = {}
        self.current_image_index = -1
        self.is_raw_only_mode = False
        self.compare_mode_active = False
        # 4. 캐시 및 원본 이미지 초기화
        self.original_pixmap = None
        self.image_loader.clear_cache()
        self.fit_pixmap_cache.clear()
        self.thumbnail_panel.model.set_image_files([])
        if hasattr(self, 'grid_thumbnail_cache'):
            for key in self.grid_thumbnail_cache:
                self.grid_thumbnail_cache[key].clear()
        # 5. 뷰 및 UI 상태 초기화 (grid_mode를 먼저 Off로 설정)
        self.grid_mode = "Off" # <<< 중요: update_grid_view가 참조할 상태를 먼저 설정합니다.
        self.grid_page_start_index = 0
        self.current_grid_index = 0
        self.previous_grid_mode = None
        self.viewport_focus_by_orientation.clear()
        self.current_active_rel_center = QPointF(0.5, 0.5)
        self.current_active_zoom_level = "Fit"
        
        # 6. UI 업데이트 (상태 변수 설정 후)
        self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        self.update_jpg_folder_ui_state()
        self.update_raw_folder_ui_state()
        self.update_match_raw_button_state()
        self.update_all_folder_labels_state()

        # [수정] display_current_image() 대신 update_grid_view()를 호출합니다.
        # self.grid_mode가 "Off"로 설정되었으므로, 이 함수는 그리드를 정리하고
        # 빈 단일 이미지 뷰로 전환하는 작업을 올바르게 수행합니다.
        self.update_grid_view()

        # [추가] update_grid_view 호출 후, 나머지 UI 컨트롤 상태도 동기화합니다.
        if hasattr(self, 'grid_off_radio'):
            self.grid_off_radio.setChecked(True)
        self.update_zoom_radio_buttons_state()
        self.update_thumbnail_panel_visibility()
        
        logging.info("작업 공간 초기화 완료.")

    def setup_file_info_ui(self):
        """이미지 파일 정보 표시 UI 구성"""
        # 파일명 레이블 (커스텀 클래스 사용)
        # ========== UIScaleManager 적용 ==========
        filename_padding = UIScaleManager.get("filename_label_padding")
        self.info_filename_label = FilenameLabel("-", fixed_height_padding=filename_padding)
        self.info_filename_label.doubleClicked.connect(self.open_current_file_in_explorer)
        self.control_layout.addWidget(self.info_filename_label)

        # 정보 레이블들을 담을 하나의 컨테이너
        info_container = QWidget()
        info_container.setFixedWidth(UIScaleManager.get("info_container_width"))  # 고정 너비 설정으로 가운데 정렬 효과
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(UIScaleManager.get("control_layout_spacing"))

        # 정보 표시를 위한 레이블들 (왼쪽 정렬)
        # ========== UIScaleManager 적용 ==========
        info_padding = UIScaleManager.get("info_label_padding")
        info_label_style = f"color: #A8A8A8; padding-left: {info_padding}px;"
        info_font = QFont("Arial", UIScaleManager.get("font_size"))

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
        info_layout.addWidget(self.info_datetime_label)

        self.info_resolution_label = QLabel("-")
        configure_info_label(self.info_resolution_label)
        info_layout.addWidget(self.info_resolution_label)

        self.info_camera_label = QLabel("-")
        configure_info_label(self.info_camera_label)
        info_layout.addWidget(self.info_camera_label)

        self.info_exposure_label = QLabel("-")
        configure_info_label(self.info_exposure_label)
        info_layout.addWidget(self.info_exposure_label)

        self.info_focal_label = QLabel("-")
        configure_info_label(self.info_focal_label)
        info_layout.addWidget(self.info_focal_label)

        self.info_aperture_label = QLabel("-")
        configure_info_label(self.info_aperture_label)
        info_layout.addWidget(self.info_aperture_label)

        self.info_iso_label = QLabel("-")
        configure_info_label(self.info_iso_label)
        info_layout.addWidget(self.info_iso_label)

        # 컨테이너를 가운데 정렬하여 메인 레이아웃에 추가
        container_wrapper = QWidget()
        wrapper_layout = QHBoxLayout(container_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addStretch()
        wrapper_layout.addWidget(info_container)
        wrapper_layout.addStretch()
        
        self.control_layout.addWidget(container_wrapper)

    def update_file_info_display(self, image_path):
        """파일 정보 표시 - 비동기 버전, RAW 연결 아이콘 추가"""
        if not image_path:
            # FilenameLabel의 setText는 아이콘 유무를 판단하므로 '-'만 전달해도 됨
            self.info_filename_label.setText("-")
            self.info_resolution_label.setText("-")
            self.info_camera_label.setText("-")
            self.info_datetime_label.setText("-")
            self.info_exposure_label.setText("-")
            self.info_focal_label.setText("-")
            self.info_aperture_label.setText("-")
            self.info_iso_label.setText("-")
            self.current_exif_path = None
            return
        
        file_path_obj = Path(image_path)
        actual_filename = file_path_obj.name # 아이콘 없는 순수 파일명
        display_filename = actual_filename   # 표시용 파일명 초기값

        if not self.is_raw_only_mode and file_path_obj.suffix.lower() in ['.jpg', '.jpeg']:
            base_name = file_path_obj.stem
            if self.raw_files and base_name in self.raw_files:
                display_filename += "🔗" # 표시용 파일명에만 아이콘 추가
        
        # FilenameLabel에 표시용 텍스트와 실제 열릴 파일명 전달
        self.info_filename_label.set_display_and_actual_filename(display_filename, actual_filename)
        
        self.current_exif_path = image_path
        loading_text = "▪ ···"
        
        self.info_resolution_label.setText(loading_text)
        self.info_camera_label.setText(loading_text)
        self.info_datetime_label.setText(loading_text)
        self.info_exposure_label.setText(loading_text)
        self.info_focal_label.setText(loading_text)
        self.info_aperture_label.setText(loading_text)
        self.info_iso_label.setText(loading_text)
        
        if image_path in self.exif_cache:
            self.update_info_ui_from_exif(self.exif_cache[image_path], image_path)
            return
        
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
            self.info_exposure_label.setText(error_text)
            self.info_focal_label.setText(error_text)
            self.info_aperture_label.setText(error_text)
            self.info_iso_label.setText(error_text)

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
            camera_info = f"▪ {format_camera_name(make, model)}"
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

            # 노출 시간 정보 설정
            exposure_str = "▪ "
            if exif_data["exif_exposure_time"] is not None:
                exposure_val = exif_data["exif_exposure_time"]
                try:
                    if isinstance(exposure_val, (int, float)):
                        if exposure_val >= 1:
                            exposure_str += f"{exposure_val:.1f}s"
                        else:
                            # 1초 미만일 때는 분수로 표시
                            fraction = 1 / exposure_val
                            exposure_str += f"1/{fraction:.0f}s"
                    else:
                        exposure_str += str(exposure_val)
                        if not str(exposure_val).endswith('s'):
                            exposure_str += "s"
                except (ValueError, TypeError, ZeroDivisionError):
                    exposure_str += str(exposure_val)
                self.info_exposure_label.setText(exposure_str)
            else:
                self.info_exposure_label.setText("▪ -")
            
            # 초점 거리 정보 설정
            focal_str = "▪ "
            focal_parts = []
            
            # 1. 숫자 값으로 변환하여 비교 준비
            focal_mm_num = None
            focal_35mm_num = None
            try:
                val = exif_data.get("exif_focal_mm")
                if val is not None:
                    # 정수로 비교하기 위해 float으로 변환 후 int로 캐스팅
                    focal_mm_num = int(float(str(val).lower().replace(" mm", "")))
            except (ValueError, TypeError):
                pass # 변환 실패 시 None 유지
            try:
                val = exif_data.get("exif_focal_35mm")
                if val is not None:
                    focal_35mm_num = int(float(str(val).lower().replace(" mm", "")))
            except (ValueError, TypeError):
                pass

            # 2. 기본 초점 거리(focal_mm)가 있으면 먼저 추가
            if focal_mm_num is not None:
                focal_parts.append(f"{focal_mm_num}mm")

            # 3. 35mm 환산 초점 거리가 있고, 기본 초점 거리와 다를 경우에만 추가
            if focal_35mm_num is not None:
                # 조건: 기본 초점 거리가 없거나(None), 두 값이 다를 때
                if focal_mm_num is None or focal_mm_num != focal_35mm_num:
                    focal_conversion = f"({LanguageManager.translate('환산')}: {focal_35mm_num}mm)"
                    focal_parts.append(focal_conversion)
            
            if focal_parts:
                focal_str += " ".join(focal_parts)
                self.info_focal_label.setText(focal_str)
            else:
                self.info_focal_label.setText("▪ -")

            # 조리개 정보 설정
            aperture_str = "▪ "
            if exif_data["exif_fnumber"] is not None:
                fnumber_val = exif_data["exif_fnumber"]
                try:
                    if isinstance(fnumber_val, (int, float)):
                        aperture_str += f"F{fnumber_val:.1f}"
                    else:
                        aperture_str += f"F{fnumber_val}"
                except (ValueError, TypeError):
                    aperture_str += str(fnumber_val)
                self.info_aperture_label.setText(aperture_str)
            else:
                self.info_aperture_label.setText("▪ -")
            
            # ISO 정보 설정
            iso_str = "▪ "
            if exif_data["exif_iso"] is not None:
                iso_val = exif_data["exif_iso"]
                try:
                    if isinstance(iso_val, (int, float)):
                        iso_str += f"ISO {int(iso_val)}"
                    else:
                        iso_str += f"ISO {iso_val}"
                except (ValueError, TypeError):
                    iso_str += str(iso_val)
                self.info_iso_label.setText(iso_str)
            else:
                self.info_iso_label.setText("▪ -")

        except Exception as e:
            logging.error(f"EXIF 정보 UI 업데이트 오류: {e}")
            # 에러가 발생해도 기본 정보는 표시 시도
            self.info_resolution_label.setText("▪ -")
            self.info_camera_label.setText("▪ -")
            self.info_datetime_label.setText("▪ -")
            self.info_exposure_label.setText("▪ -")
            self.info_focal_label.setText("▪ -")
            self.info_aperture_label.setText("▪ -")
            self.info_iso_label.setText("▪ -")


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
            title = LanguageManager.translate("오류")
            line1 = LanguageManager.translate("파일 열기 실패")
            line2 = LanguageManager.translate("연결된 프로그램이 없거나 파일을 열 수 없습니다.")
            self.show_themed_message_box(
                QMessageBox.Warning,
                title,
                f"{line1}: {filename}\n\n{line2}"
            )

    def display_current_image(self):
        force_refresh = getattr(self, 'force_refresh', False)
        if force_refresh:
            self.last_fit_size = (0, 0)
            self.fit_pixmap_cache.clear()
            self.force_refresh = False

        if self.grid_mode != "Off":
            self.update_grid_view()
            return

        if not self.image_files or self.current_image_index < 0 or self.current_image_index >= len(self.image_files):
            self.image_label.clear()
            self.image_label.setStyleSheet("background-color: transparent;")
            self.setWindowTitle("PhotoSort")
            self.original_pixmap = None
            self.update_file_info_display(None)
            self.previous_image_orientation = None
            self.current_image_orientation = None
            if self.minimap_visible:
                self.minimap_widget.hide()
            self.update_counters()
            self.state_save_timer.stop() # 이미지가 없으면 저장 타이머 중지
            return
                
        try:
            current_index = self.current_image_index
            image_path = self.image_files[current_index]
            image_path_str = str(image_path)

            logging.info(f"display_current_image 호출: index={current_index}, path='{image_path.name}'")

            self.update_file_info_display(image_path_str)
            self.setWindowTitle(f"PhotoSort - {image_path.name}")
            
            # --- 캐시 확인 및 즉시 적용 로직 ---
            if image_path_str in self.image_loader.cache:
                cached_pixmap = self.image_loader.cache[image_path_str]
                if cached_pixmap and not cached_pixmap.isNull():
                    logging.info(f"display_current_image: 캐시된 이미지 즉시 적용 - '{image_path.name}'")
                    
                    # _on_image_loaded_for_display와 유사한 로직으로 UI 업데이트
                    self.previous_image_orientation = self.current_image_orientation
                    new_orientation = "landscape" if cached_pixmap.width() >= cached_pixmap.height() else "portrait"
                    # 사진 변경 시 뷰포트 처리 로직 (캐시 히트 시에도 필요)
                    prev_orientation_for_decision = getattr(self, 'previous_image_orientation_for_carry_over', None) # 이전 사진의 방향
                    is_photo_actually_changed = (hasattr(self, 'previous_image_path_for_focus_carry_over') and
                                                 self.previous_image_path_for_focus_carry_over is not None and
                                                 self.previous_image_path_for_focus_carry_over != image_path_str)

                    if is_photo_actually_changed:
                        prev_zoom_for_decision = getattr(self, 'previous_zoom_mode_for_carry_over', "Fit")
                        prev_rel_center_for_decision = getattr(self, 'previous_active_rel_center_for_carry_over', QPointF(0.5, 0.5))
                        if prev_zoom_for_decision in ["100%", "Spin"] and prev_orientation_for_decision == new_orientation:
                            self.zoom_mode = prev_zoom_for_decision
                            self.current_active_rel_center = prev_rel_center_for_decision
                            self.current_active_zoom_level = self.zoom_mode
                            self.zoom_change_trigger = "photo_change_carry_over_focus"
                            if image_path_str: self._save_orientation_viewport_focus(new_orientation, self.current_active_rel_center, self.current_active_zoom_level)
                        else:
                            self.zoom_mode = "Fit"
                            self.current_active_rel_center = QPointF(0.5, 0.5)
                            self.current_active_zoom_level = "Fit"
                            self.zoom_change_trigger = "photo_change_to_fit"
                    # 라디오 버튼 UI 동기화
                    if self.zoom_mode == "Fit": self.fit_radio.setChecked(True)
                    elif self.zoom_mode == "100%": self.zoom_100_radio.setChecked(True)
                    elif self.zoom_mode == "Spin": self.zoom_spin_btn.setChecked(True)

                    self.current_image_orientation = new_orientation
                    self.original_pixmap = cached_pixmap
                    
                    self.apply_zoom_to_image() # 줌 적용
                    
                    if self.minimap_toggle.isChecked(): self.toggle_minimap(True)
                    self.update_counters()
                    
                    # --- 캐시 히트 후 타이머 시작 ---
                    if self.grid_mode == "Off":
                        self.state_save_timer.start()
                        logging.debug(f"display_current_image (cache hit): Index save timer (re)started for index {self.current_image_index}")
                    # --- 타이머 시작 끝 ---
                    
                    # 사용한 임시 변수 초기화
                    if hasattr(self, 'previous_image_path_for_focus_carry_over'): self.previous_image_path_for_focus_carry_over = None
                    self.update_compare_filenames()
                    return # 캐시 사용했으므로 비동기 로딩 불필요
            
            # --- 캐시에 없거나 유효하지 않으면 비동기 로딩 요청 ---
            logging.info(f"display_current_image: 캐시에 없음. 비동기 로딩 시작 및 로딩 인디케이터 타이머 설정 - '{image_path.name}'")
            if not hasattr(self, 'loading_indicator_timer'):
                self.loading_indicator_timer = QTimer(self)
                self.loading_indicator_timer.setSingleShot(True)
                self.loading_indicator_timer.timeout.connect(self.show_loading_indicator)
            
            self.loading_indicator_timer.stop() 
            self.loading_indicator_timer.start(500)
            
            self.load_image_async(image_path_str, current_index) # 비동기 로딩
            
        except Exception as e:
            logging.error(f"display_current_image에서 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            self.image_label.setText(f"{LanguageManager.translate('이미지 표시 중 오류 발생')}: {str(e)}")
            self.original_pixmap = None
            self.update_counters()
            self.state_save_timer.stop() # 오류 시 타이머 중지

        self.update_compare_filenames()
        # 썸네일 패널 업데이트 (함수 끝 부분에 추가)
        self.update_thumbnail_current_index()


    def show_loading_indicator(self):
        """로딩 중 표시 (image_label을 image_container 크기로 설정)"""
        logging.debug("show_loading_indicator: 로딩 인디케이터 표시 시작")

        # 1. image_label의 부모가 image_container인지, 그리고 유효한지 확인
        if self.image_label.parent() is not self.image_container or \
           not self.image_container or \
           self.image_container.width() <= 0 or \
           self.image_container.height() <= 0:
            logging.warning("show_loading_indicator: image_container가 유효하지 않거나 크기가 없어 로딩 인디케이터 중앙 정렬 불가. 기본 동작 수행.")
            # 기존 로직 (크기 설정 없이)
            loading_pixmap = QPixmap(200, 200)
            loading_pixmap.fill(QColor(40, 40, 40))
            self.image_label.setPixmap(loading_pixmap)
            self.image_label.setText(LanguageManager.translate("이미지 로드 중..."))
            self.image_label.setStyleSheet("color: white; background-color: transparent;")
            self.image_label.setAlignment(Qt.AlignCenter) # image_label 내부에서 중앙 정렬
            return

        # 2. image_container의 현재 크기를 가져옵니다.
        container_width = self.image_container.width()
        container_height = self.image_container.height()
        logging.debug(f"  image_container 크기: {container_width}x{container_height}")

        # 3. image_label의 geometry를 image_container의 전체 영역으로 설정합니다.
        #    이렇게 하면 image_label이 image_container를 꽉 채우게 됩니다.
        self.image_label.setGeometry(0, 0, container_width, container_height)
        logging.debug(f"  image_label geometry 설정: 0,0, {container_width}x{container_height}")

        # 4. 로딩 플레이스홀더 픽스맵 생성 (선택 사항: 크기를 image_label에 맞출 수도 있음)
        #    기존 200x200 크기를 유지하고, image_label 내에서 중앙 정렬되도록 합니다.
        #    또는, 로딩 아이콘이 너무 커지는 것을 방지하기 위해 적절한 크기를 유지합니다.
        placeholder_size = min(200, container_width // 2, container_height // 2) # 너무 커지지 않도록 제한
        if placeholder_size < 50: placeholder_size = 50 # 최소 크기 보장
        
        loading_pixmap = QPixmap(placeholder_size, placeholder_size)
        loading_pixmap.fill(QColor(40, 40, 40)) # 어두운 회색 배경

        # 5. image_label에 픽스맵과 텍스트 설정
        self.image_label.setPixmap(loading_pixmap)
        self.image_label.setText(LanguageManager.translate("이미지 로드 중..."))
        
        # 6. image_label의 스타일과 정렬 설정
        #    - 배경은 투명하게 하여 image_container의 검은색 배경이 보이도록 합니다.
        #    - 텍스트 색상은 흰색으로 합니다.
        #    - setAlignment(Qt.AlignCenter)를 통해 픽스맵과 텍스트가 image_label의 중앙에 오도록 합니다.
        #      (image_label이 이제 image_container 전체 크기이므로, 이는 곧 캔버스 중앙 정렬을 의미합니다.)
        self.image_label.setStyleSheet("color: white; background-color: transparent;")
        self.image_label.setAlignment(Qt.AlignCenter)

        logging.debug("show_loading_indicator: 로딩 인디케이터 표시 완료 (중앙 정렬됨)")

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
        """백그라운드 스레드에서 실행되는 이미지 로딩 작업. RAW 디코딩은 RawDecoderPool에 위임."""
        try:
            resource_manager = ResourceManager.instance()
            if not resource_manager._running:
                logging.info(f"PhotoSortApp._load_image_task: ResourceManager가 종료 중이므로 작업 중단 ({Path(image_path).name})")
                # ... (기존 종료 시그널 처리) ...
                if hasattr(self, 'image_loader'):
                    QMetaObject.invokeMethod(self.image_loader, "loadFailed", Qt.QueuedConnection,
                                             Q_ARG(str, "ResourceManager_shutdown"),
                                             Q_ARG(str, image_path),
                                             Q_ARG(int, requested_index))
                return False

            file_path_obj = Path(image_path)
            is_raw = file_path_obj.suffix.lower() in self.raw_extensions
            
            # ImageLoader의 현재 RAW 처리 전략 확인
            # (PhotoSortApp이 ImageLoader의 전략을 관리하므로, PhotoSortApp의 상태를 참조하거나
            #  ImageLoader에 질의하는 것이 더 적절할 수 있습니다.
            #  여기서는 ImageLoader의 내부 상태를 직접 참조하는 것으로 가정합니다.)
            raw_processing_method = self.image_loader._raw_load_strategy

            if is_raw and raw_processing_method == "decode":
                logging.info(f"_load_image_task: RAW 파일 '{file_path_obj.name}'의 'decode' 요청. RawDecoderPool에 제출.")
                
                # --- 콜백 래핑 시작 ---
                # requested_index와 is_main_display_image 값을 캡처하는 람다 함수 사용
                # 이 람다 함수는 오직 'result' 딕셔너리 하나만 인자로 받음
                wrapped_callback = lambda result_dict: self._on_raw_decoded_for_display(
                    result_dict, 
                    requested_index=requested_index, # 캡처된 값 사용
                    is_main_display_image=True     # 캡처된 값 사용
                )
                # --- 콜백 래핑 끝 ---
                
                task_id = self.resource_manager.submit_raw_decoding(image_path, wrapped_callback) # 래핑된 콜백 전달
                if task_id is None: 
                    raise RuntimeError("Failed to submit RAW decoding task.")
                return True 
            else:
                # JPG 또는 RAW (preview 모드)는 기존 ImageLoader.load_image_with_orientation 직접 호출
                logging.info(f"_load_image_task: '{file_path_obj.name}' 직접 로드 시도 (JPG 또는 RAW-preview).")
                pixmap = self.image_loader.load_image_with_orientation(image_path)

                if not resource_manager._running: # 로드 후 다시 확인
                    # ... (기존 종료 시그널 처리) ...
                    if hasattr(self, 'image_loader'):
                        QMetaObject.invokeMethod(self.image_loader, "loadFailed", Qt.QueuedConnection,
                                                 Q_ARG(str, "ResourceManager_shutdown_post"),
                                                 Q_ARG(str, image_path),
                                                 Q_ARG(int, requested_index))
                    return False
                
                if hasattr(self, 'image_loader'):
                    QMetaObject.invokeMethod(self.image_loader, "loadCompleted", Qt.QueuedConnection,
                                             Q_ARG(QPixmap, pixmap),
                                             Q_ARG(str, image_path),
                                             Q_ARG(int, requested_index))
                return True

        except Exception as e:
            # ... (기존 오류 처리) ...
            if ResourceManager.instance()._running:
                logging.error(f"_load_image_task 오류 ({Path(image_path).name if image_path else 'N/A'}): {e}")
                import traceback
                traceback.print_exc()
                if hasattr(self, 'image_loader'):
                    QMetaObject.invokeMethod(self.image_loader, "loadFailed", Qt.QueuedConnection,
                                             Q_ARG(str, str(e)),
                                             Q_ARG(str, image_path),
                                             Q_ARG(int, requested_index))
            else:
                logging.info(f"_load_image_task 중 오류 발생했으나 ResourceManager 이미 종료됨 ({Path(image_path).name if image_path else 'N/A'}): {e}")
            return False


    def _on_image_loaded_for_display(self, pixmap, image_path_str_loaded, requested_index):
        if self.current_image_index != requested_index: # ... (무시 로직) ...
            return
        if hasattr(self, 'loading_indicator_timer'): self.loading_indicator_timer.stop()
        if pixmap.isNull():
            self.image_label.setText(f"{LanguageManager.translate('이미지 로드 실패')}")
            self.original_pixmap = None; self.update_counters(); return

        new_image_orientation = "landscape" if pixmap.width() >= pixmap.height() else "portrait"
        
        prev_orientation = getattr(self, 'previous_image_orientation_for_carry_over', None)
        prev_zoom = getattr(self, 'previous_zoom_mode_for_carry_over', "Fit")
        prev_rel_center = getattr(self, 'previous_active_rel_center_for_carry_over', QPointF(0.5, 0.5))

        is_photo_actually_changed = (hasattr(self, 'previous_image_path_for_focus_carry_over') and # 이 변수는 여전히 사진 변경 자체를 판단하는 데 사용
                                     self.previous_image_path_for_focus_carry_over is not None and
                                     self.previous_image_path_for_focus_carry_over != image_path_str_loaded)
        
        if is_photo_actually_changed:
            if prev_zoom in ["100%", "Spin"] and prev_orientation == new_image_orientation:
                # 방향 동일 & 이전 줌: 이전 "활성" 포커스 이어받기
                self.zoom_mode = prev_zoom
                self.current_active_rel_center = prev_rel_center
                self.current_active_zoom_level = self.zoom_mode
                self.zoom_change_trigger = "photo_change_carry_over_focus"
                # 새 사진의 "방향 타입" 포커스를 이전 활성 포커스로 덮어쓰기
                self._save_orientation_viewport_focus(new_image_orientation, self.current_active_rel_center, self.current_active_zoom_level)
            else: # Fit에서 왔거나, 방향이 다르거나, 이전 줌 정보 부적절
                self.zoom_mode = "Fit" # 새 사진은 Fit으로 시작
                self.current_active_rel_center = QPointF(0.5, 0.5)
                self.current_active_zoom_level = "Fit"
                self.zoom_change_trigger = "photo_change_to_fit"
        # else: 사진 변경 아님 (zoom_change_trigger는 다른 곳에서 설정되어 apply_zoom_to_image로 전달됨)

        # 라디오 버튼 UI 동기화 및 나머지 로직 (original_pixmap 설정, apply_zoom_to_image 호출 등)
        # ... (이전 답변의 _on_image_loaded_for_display 나머지 부분과 유사하게 진행) ...
        if self.zoom_mode == "Fit": self.fit_radio.setChecked(True)
        elif self.zoom_mode == "100%": self.zoom_100_radio.setChecked(True)
        elif self.zoom_mode == "Spin": self.zoom_spin_btn.setChecked(True)
        
        # self.previous_image_orientation = self.current_image_orientation # 이제 _prepare_for_photo_change에서 관리
        self.current_image_orientation = new_image_orientation # 새 이미지의 방향으로 업데이트
        self.original_pixmap = pixmap
        
        self.apply_zoom_to_image() # 여기서 current_active_... 값들이 사용됨
        
        # 임시 변수 초기화
        if hasattr(self, 'previous_image_path_for_focus_carry_over'): self.previous_image_path_for_focus_carry_over = None 
        if hasattr(self, 'previous_image_orientation_for_carry_over'): self.previous_image_orientation_for_carry_over = None
        if hasattr(self, 'previous_zoom_mode_for_carry_over'): self.previous_zoom_mode_for_carry_over = None
        if hasattr(self, 'previous_active_rel_center_for_carry_over'): self.previous_active_rel_center_for_carry_over = None

        if self.minimap_toggle.isChecked(): self.toggle_minimap(True)
        self.update_counters()

        # --- 이미지 표시 완료 후 상태 저장 타이머 시작 ---
        if self.grid_mode == "Off": # Grid Off 모드에서만 이 경로로 current_image_index가 안정화됨
            self.state_save_timer.start()
            logging.debug(f"_on_image_loaded_for_display: Index save timer (re)started for index {self.current_image_index}")
        # --- 타이머 시작 끝 ---
        self.update_compare_filenames()


    def _on_raw_decoded_for_display(self, result: dict, requested_index: int, is_main_display_image: bool = False):
        file_path = result.get('file_path')
        success = result.get('success', False)
        logging.info(f"_on_raw_decoded_for_display 시작: 파일='{Path(file_path).name if file_path else 'N/A'}', 요청 인덱스={requested_index}, 성공={success}, 메인={is_main_display_image}")

        # 1. 디코딩에 실패했으면 아무것도 하지 않고 종료
        if not success:
            error_msg = result.get('error', 'Unknown error')
            logging.error(f"  _on_raw_decoded_for_display: RAW 디코딩 실패 ({Path(file_path).name if file_path else 'N/A'}): {error_msg}")
            # 메인 이미지 로딩 실패 시에만 사용자에게 알림
            if is_main_display_image:
                self._close_first_raw_decode_progress()
                self.image_label.setText(f"{LanguageManager.translate('이미지 로드 실패')}: {error_msg}")
                self.original_pixmap = None
                self.update_counters()
                if file_path and hasattr(self, 'image_loader'):
                    self.image_loader.decodingFailedForFile.emit(file_path)
            return

        # 2. 디코딩에 성공했으면, 먼저 QPixmap을 만들고 즉시 캐시에 저장
        try:
            data_bytes = result.get('data')
            shape = result.get('shape')
            if not data_bytes or not shape:
                raise ValueError("디코딩 결과 데이터 또는 형태 정보 누락")
            height, width, _ = shape
            qimage = QImage(data_bytes, width, height, width * 3, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimage)
            if pixmap.isNull():
                raise ValueError("디코딩된 데이터로 QPixmap 생성 실패")

            # *** 핵심 수정: 성공한 모든 결과를 캐시에 저장 ***
            if hasattr(self, 'image_loader'):
                self.image_loader._add_to_cache(file_path, pixmap)
            logging.info(f"  _on_raw_decoded_for_display: RAW 이미지 캐싱 성공: '{Path(file_path).name}'")

        except Exception as e:
            logging.error(f"  _on_raw_decoded_for_display: RAW 디코딩 성공 후 QPixmap 처리 오류 ({Path(file_path).name if file_path else 'N/A'}): {e}")
            return # QPixmap 생성 실패 시 더 이상 진행 불가

        # 3. 이 결과가 현재 화면에 표시해야 할 '메인 이미지'인 경우에만 UI 업데이트 수행
        current_path_to_display = self.get_current_image_path()
        path_match = file_path and current_path_to_display and Path(file_path).resolve() == Path(current_path_to_display).resolve()

        if is_main_display_image and path_match:
            logging.info(f"  _on_raw_decoded_for_display: 메인 이미지 UI 업데이트 시작. 파일='{Path(file_path).name}'")
            if hasattr(self, 'loading_indicator_timer'):
                self.loading_indicator_timer.stop()

            self.previous_image_orientation = self.current_image_orientation
            self.current_image_orientation = "landscape" if pixmap.width() >= pixmap.height() else "portrait"
            self.original_pixmap = pixmap
            self.apply_zoom_to_image()
            if self.minimap_toggle.isChecked(): self.toggle_minimap(True)
            self.update_counters()
            
            if self.grid_mode == "Off":
                self.state_save_timer.start()
            
            self._close_first_raw_decode_progress() # UI 업데이트 후 진행률 대화상자 닫기
            self.update_compare_filenames()
            logging.info(f"  _on_raw_decoded_for_display: 메인 이미지 UI 업데이트 완료.")
        else:
            logging.info(f"  _on_raw_decoded_for_display: 프리로드된 이미지 캐싱 완료, UI 업데이트는 건너뜀. 파일='{Path(file_path).name}'")

        logging.info(f"_on_raw_decoded_for_display 종료: 파일='{Path(file_path).name if file_path else 'N/A'}'")

    def process_pending_raw_results(self):
        """ResourceManager를 통해 RawDecoderPool의 완료된 결과들을 처리합니다."""
        if hasattr(self, 'resource_manager') and self.resource_manager:
            # 한 번에 최대 5개의 결과를 처리하도록 시도 (조정 가능)
            processed_count = self.resource_manager.process_raw_results(max_results=5)
            if processed_count > 0:
                logging.debug(f"process_pending_raw_results: {processed_count}개의 RAW 디코딩 결과 처리됨.")
        # else: # ResourceManager가 없는 예외적인 경우
            # logging.warning("process_pending_raw_results: ResourceManager 인스턴스가 없습니다.")


    def _on_image_load_failed(self, image_path, error_message, requested_index):
        """이미지 로드 실패 시 UI 스레드에서 실행"""
        # 요청 시점의 인덱스와 현재 인덱스 비교 (이미지 변경 여부 확인)
        if self.current_image_index != requested_index:
            print(f"이미지가 변경되어 오류 결과 무시: 요청={requested_index}, 현재={self.current_image_index}")
            return
            
        self.image_label.setText(f"{LanguageManager.translate('이미지 로드 실패')}: {error_message}")
        self.original_pixmap = None
        self.update_counters()



    def preload_adjacent_images(self, current_index):
        """인접 이미지 미리 로드 - 시스템 프로필에 따라 동적으로 범위 조절."""
        if not self.image_files:
            return

        # HardwareProfileManager에서 현재 프로필의 미리 로드 범위 가져오기
        forward_preload_count, backward_preload_count = HardwareProfileManager.get("preload_range_adjacent")
        priority_close_threshold = HardwareProfileManager.get("preload_range_priority")
        
        total_images = len(self.image_files)
        
        # 이동 방향 감지 (기존 로직 유지)
        direction = 1
        if hasattr(self, 'previous_image_index') and self.previous_image_index != current_index:
            if self.previous_image_index < current_index or \
            (self.previous_image_index == total_images - 1 and current_index == 0):
                direction = 1
            elif self.previous_image_index > current_index or \
                (self.previous_image_index == 0 and current_index == total_images - 1):
                direction = -1
        self.previous_image_index = current_index

        # 캐시된 이미지와 현재 로딩 요청된 이미지 확인
        cached_images = set(self.image_loader.cache.keys())
        # (이하 로직은 기존과 거의 동일하나, 범위 변수를 프로필에서 가져온 값으로 사용)
        
        to_preload = []
        if direction >= 0: # 앞으로 이동
            for offset in range(1, forward_preload_count + 1):
                idx = (current_index + offset) % total_images
                if str(self.image_files[idx]) not in cached_images:
                    priority = 'high' if offset <= priority_close_threshold else ('medium' if offset <= priority_close_threshold * 2 else 'low')
                    to_preload.append((idx, priority))
            for offset in range(1, backward_preload_count + 1):
                idx = (current_index - offset + total_images) % total_images
                if str(self.image_files[idx]) not in cached_images:
                    priority = 'medium' if offset <= priority_close_threshold else 'low'
                    to_preload.append((idx, priority))
        else: # 뒤로 이동
            for offset in range(1, forward_preload_count + 1):
                idx = (current_index - offset + total_images) % total_images
                if str(self.image_files[idx]) not in cached_images:
                    priority = 'high' if offset <= priority_close_threshold else ('medium' if offset <= priority_close_threshold * 2 else 'low')
                    to_preload.append((idx, priority))
            for offset in range(1, backward_preload_count + 1):
                idx = (current_index + offset) % total_images
                if str(self.image_files[idx]) not in cached_images:
                    priority = 'medium' if offset <= priority_close_threshold else 'low'
                    to_preload.append((idx, priority))

        # 로드 요청 제출
        for idx, priority in to_preload:
            img_path = str(self.image_files[idx])
            # ... (기존과 동일하게 RAW/JPG 구분하여 작업 제출) ...
            # 여기서는 _preload_image_for_grid를 사용하여 preview만 로드하는 것으로 단순화
            self.resource_manager.submit_imaging_task_with_priority(
                priority,
                self._preload_image_for_grid, 
                img_path
            )


    def on_grid_cell_clicked(self, clicked_widget, clicked_index):
        """그리드 셀 클릭 이벤트 핸들러 (다중 선택 지원, Shift+클릭 범위 선택 추가)"""
        if self.grid_mode == "Off" or not self.grid_labels:
            return

        try:
            # 현재 페이지에 실제로 표시될 수 있는 이미지의 총 개수
            current_page_image_count = min(len(self.grid_labels), len(self.image_files) - self.grid_page_start_index)

            # 클릭된 인덱스가 유효한 범위 내에 있고, 해당 인덱스에 해당하는 이미지가 실제로 존재하는지 확인
            if 0 <= clicked_index < current_page_image_count:
                image_path_property = clicked_widget.property("image_path")

                if image_path_property:
                    # 키 상태 확인
                    modifiers = QApplication.keyboardModifiers()
                    ctrl_pressed = bool(modifiers & Qt.ControlModifier)
                    shift_pressed = bool(modifiers & Qt.ShiftModifier)
                    
                    if shift_pressed and self.last_single_click_index != -1:
                        # Shift+클릭: 범위 선택
                        start_index = min(self.last_single_click_index, clicked_index)
                        end_index = max(self.last_single_click_index, clicked_index)
                        
                        # 범위 내의 모든 유효한 셀 선택
                        self.selected_grid_indices.clear()
                        for i in range(start_index, end_index + 1):
                            if i < current_page_image_count:
                                # 해당 인덱스에 실제 이미지가 있는지 확인
                                if i < len(self.grid_labels):
                                    cell_widget = self.grid_labels[i]
                                    if cell_widget.property("image_path"):
                                        self.selected_grid_indices.add(i)
                        
                        # Primary 선택을 범위의 첫 번째로 설정
                        if self.selected_grid_indices:
                            self.primary_selected_index = self.grid_page_start_index + start_index
                            self.current_grid_index = start_index
                        
                        logging.debug(f"Shift+클릭 범위 선택: {start_index}~{end_index} ({len(self.selected_grid_indices)}개 선택)")
                        
                    elif ctrl_pressed:
                        # Ctrl+클릭: 다중 선택 토글 (기존 코드)
                        if clicked_index in self.selected_grid_indices:
                            self.selected_grid_indices.remove(clicked_index)
                            logging.debug(f"셀 선택 해제: index {clicked_index}")
                            
                            if self.primary_selected_index == self.grid_page_start_index + clicked_index:
                                if self.selected_grid_indices:
                                    first_selected = min(self.selected_grid_indices)
                                    self.primary_selected_index = self.grid_page_start_index + first_selected
                                else:
                                    self.primary_selected_index = -1
                        else:
                            self.selected_grid_indices.add(clicked_index)
                            logging.debug(f"셀 선택 추가: index {clicked_index}")
                            
                            if self.primary_selected_index == -1:
                                self.primary_selected_index = self.grid_page_start_index + clicked_index
                    else:
                        # 일반 클릭: 기존 선택 모두 해제하고 새로 선택
                        self.selected_grid_indices.clear()
                        self.selected_grid_indices.add(clicked_index)
                        self.primary_selected_index = self.grid_page_start_index + clicked_index
                        self.current_grid_index = clicked_index
                        self.last_single_click_index = clicked_index  # 마지막 단일 클릭 인덱스 저장
                        logging.debug(f"단일 셀 선택: index {clicked_index}")

                    # UI 업데이트
                    self.update_grid_selection_border()
                    self.update_window_title_with_selection()

                    # 파일 정보는 primary 선택 이미지로 표시
                    if self.primary_selected_index != -1 and 0 <= self.primary_selected_index < len(self.image_files):
                        selected_image_path = str(self.image_files[self.primary_selected_index])
                        self.update_file_info_display(selected_image_path)
                    else:
                        self.update_file_info_display(None)
                        
                    # 선택이 있으면 타이머 시작
                    if self.selected_grid_indices:
                        self.state_save_timer.start()
                        logging.debug(f"on_grid_cell_clicked: Index save timer (re)started for grid cells {self.selected_grid_indices}")

                    # 카운터 업데이트 추가
                    self.update_counters()

                else:
                    logging.debug(f"빈 셀 클릭됨 (이미지 경로 없음): index {clicked_index}")
                    self.update_file_info_display(None)
            else:
                logging.debug(f"유효하지 않은 셀 클릭됨: index {clicked_index}")
                self.update_file_info_display(None)
        except Exception as e:
            logging.error(f"on_grid_cell_clicked 오류: {e}")
            self.update_file_info_display(None)
             

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

                rows, cols = self._get_grid_dimensions()
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

        #첫 실행 중에는 상태를 저장하지 않음
        if hasattr(self, 'is_first_run') and self.is_first_run:
            logging.debug("save_state: 첫 실행 중이므로 상태 저장을 건너뜀")
            return
        
        # --- 현재 실제로 선택/표시된 이미지의 '전체 리스트' 인덱스 계산 ---
        actual_current_image_list_index = -1
        if self.grid_mode != "Off":
            if self.image_files and 0 <= self.grid_page_start_index + self.current_grid_index < len(self.image_files):
                actual_current_image_list_index = self.grid_page_start_index + self.current_grid_index
        else: # Grid Off 모드
            if self.image_files and 0 <= self.current_image_index < len(self.image_files):
                actual_current_image_list_index = self.current_image_index
        # --- 계산 끝 ---

        state_data = {
            "current_folder": str(self.current_folder) if self.current_folder else "",
            "raw_folder": str(self.raw_folder) if self.raw_folder else "",
            "raw_files": {k: str(v) for k, v in self.raw_files.items()},
            "move_raw_files": self.move_raw_files,
            "target_folders": [str(f) if f else "" for f in self.target_folders],
            "zoom_mode": self.zoom_mode,
            "zoom_spin_value": self.zoom_spin_value,
            "minimap_visible": self.minimap_toggle.isChecked(),
            "grid_mode": self.grid_mode,
            # "current_image_index": self.current_image_index, # 이전 방식
            "current_image_index": actual_current_image_list_index, # <<< 수정: 실제로 보고 있던 이미지의 전역 인덱스 저장
            "current_grid_index": self.current_grid_index, # Grid 모드일 때의 페이지 내 인덱스 (복원 시 참고용)
            "grid_page_start_index": self.grid_page_start_index, # Grid 모드일 때의 페이지 시작 인덱스 (복원 시 참고용)
            "previous_grid_mode": self.previous_grid_mode,
            "language": LanguageManager.get_current_language(),
            "date_format": DateFormatManager.get_current_format(),
            "theme": ThemeManager.get_current_theme_name(),
            "is_raw_only_mode": self.is_raw_only_mode,
            "control_panel_on_right": getattr(self, 'control_panel_on_right', False),
            "show_grid_filenames": self.show_grid_filenames, # 파일명 표시 상태
            "last_used_raw_method": self.image_loader._raw_load_strategy if hasattr(self, 'image_loader') else "preview",
            "camera_raw_settings": self.camera_raw_settings, # 카메라별 raw 설정
            "viewport_move_speed": getattr(self, 'viewport_move_speed', 5), # 키보드 뷰포트 이동속도
            "mouse_wheel_action": getattr(self, 'mouse_wheel_action', 'photo_navigation'),  # 마우스 휠 동작
            "folder_count": self.folder_count,
            "supported_image_extensions": sorted(list(self.supported_image_extensions)),
            "saved_sessions": self.saved_sessions,
            "performance_profile": HardwareProfileManager.get_current_profile_key(),
            "compare_mode_active": self.compare_mode_active,
            "image_B_path": str(self.image_B_path) if self.image_B_path else "",
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
        logging.info(f"PhotoSortApp.load_state: 상태 불러오기 시작")
        load_path = self.get_script_dir() / self.STATE_FILE
        is_first_run = not load_path.exists()
        logging.debug(f"  load_state: is_first_run = {is_first_run}")

        if is_first_run:
            logging.info("PhotoSortApp.load_state: 첫 실행 감지. 초기 설정으로 시작합니다.")
            
            # --- 1. 모든 상태 변수를 안전한 기본값으로 초기화 ---
            self.initialize_to_default_state()

            # --- 2. 첫 실행 시 특별히 설정할 기본값들 (상태 변수) ---
            #    (대부분 initialize_to_default_state에 포함되었지만,
            #     첫 실행에만 적용할 설정이 있다면 여기에 추가)
            LanguageManager.set_language("en") 
            ThemeManager.set_theme("default")  
            DateFormatManager.set_date_format("yyyy-mm-dd")
            self.supported_image_extensions = {'.jpg', '.jpeg'}
            self.mouse_wheel_action = "photo_navigation"
            # camera_raw_settings는 기본적으로 빈 딕셔너리로 시작하므로 별도 설정 불필요

            # --- 3. UI 컨트롤들을 기본값으로 설정 ---
            #    (UI 컨트롤은 initialize_to_default_state에서 처리하지 않으므로 여기서 설정)
            if hasattr(self, 'english_radio'):
                self.english_radio.setChecked(True)
            if hasattr(self, 'panel_pos_left_radio'):
                self.panel_pos_left_radio.setChecked(True)
            if hasattr(self, 'ext_checkboxes'):
                for name, checkbox in self.ext_checkboxes.items():
                    checkbox.setChecked(name == "JPG")
            if hasattr(self, 'folder_count_combo'):
                index = self.folder_count_combo.findData(self.folder_count)
                if index != -1: self.folder_count_combo.setCurrentIndex(index)
            if hasattr(self, 'viewport_speed_combo'):
                index = self.viewport_speed_combo.findData(self.viewport_move_speed)
                if index != -1: self.viewport_speed_combo.setCurrentIndex(index)
            if hasattr(self, 'mouse_wheel_photo_radio'):
                self.mouse_wheel_photo_radio.setChecked(True)

            # --- 4. 전체 UI 상태를 데이터에 맞춰 최종 업데이트 ---
            self.update_all_ui_after_load_failure_or_first_run()
            self._sync_performance_profile_ui() # 자동 감지된 프로필로 UI 동기화

            # --- 5. 첫 실행 플래그 설정 및 마무리 ---
            self.is_first_run = True
            QTimer.singleShot(0, self._apply_panel_position)
            self.setFocus()
            return True

        try:
            with open(load_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            logging.info(f"PhotoSortApp.load_state: 상태 파일 로드 완료 ({load_path})")
            logging.debug(f"PhotoSortApp.load_state: 로드된 데이터: {loaded_data}")

            # 1. 기본 설정 복원 (언어, 날짜 형식, 테마, RAW 전략, 패널 위치, 파일명 표시 여부 등)
            language = loaded_data.get("language", "en")
            LanguageManager.set_language(language)

            date_format = loaded_data.get("date_format", "yyyy-mm-dd")
            DateFormatManager.set_date_format(date_format)

            theme = loaded_data.get("theme", "default")
            ThemeManager.set_theme(theme)

            self.camera_raw_settings = loaded_data.get("camera_raw_settings", {}) # <<< 카메라별 설정 로드, 없으면 빈 딕셔셔너리
            logging.info(f"PhotoSortApp.load_state: 로드된 camera_raw_settings: {self.camera_raw_settings}")
            
            self.control_panel_on_right = loaded_data.get("control_panel_on_right", False)
            self.show_grid_filenames = loaded_data.get("show_grid_filenames", False)
            
            self.viewport_move_speed = loaded_data.get("viewport_move_speed", 5) # <<< 뷰포트 이동속도, 기본값 5
            logging.info(f"PhotoSortApp.load_state: 로드된 viewport_move_speed: {self.viewport_move_speed}")
    
            self.mouse_wheel_action = loaded_data.get("mouse_wheel_action", "photo_navigation")

            self.mouse_wheel_action = loaded_data.get("mouse_wheel_action", "photo_navigation")  # 추가
            logging.info(f"PhotoSortApp.load_state: 로드된 mouse_wheel_action: {self.mouse_wheel_action}")

            self.saved_sessions = loaded_data.get("saved_sessions", {})
            logging.info(f"PhotoSortApp.load_state: 로드된 saved_sessions: (총 {len(self.saved_sessions)}개)")

            # <<< 저장된 확장자 설정 불러오기 (기본값 설정 포함) >>>
            default_extensions = {'.jpg', '.jpeg'}
            loaded_extensions = loaded_data.get("supported_image_extensions", list(default_extensions))
            self.supported_image_extensions = set(loaded_extensions)

            # 불러온 데이터로 체크박스 UI 상태 동기화
            if hasattr(self, 'ext_checkboxes'):
                extension_groups = {"JPG": ['.jpg', '.jpeg'], "PNG": ['.png'], "WebP": ['.webp'], "HEIC": ['.heic', '.heif'], "BMP": ['.bmp'], "TIFF": ['.tif', '.tiff']}
                for name, checkbox in self.ext_checkboxes.items():
                    # 해당 그룹의 확장자 중 하나라도 지원 목록에 포함되어 있는지 확인
                    is_checked = any(ext in self.supported_image_extensions for ext in extension_groups[name])
                    checkbox.setChecked(is_checked)

            self.folder_count = loaded_data.get("folder_count", 3)
            loaded_folders = loaded_data.get("target_folders", [])
            self.target_folders = (loaded_folders + [""] * self.folder_count)[:self.folder_count]

            # 2. UI 컨트롤 업데이트 (설정 복원 후, 폴더 경로 설정 전)
            if hasattr(self, 'language_group'):
                lang_button_id = 0 if language == "en" else 1
                button_to_check = self.language_group.button(lang_button_id)
                if button_to_check: button_to_check.setChecked(True)
            
            if hasattr(self, 'date_format_combo'):
                idx = self.date_format_combo.findData(date_format)
                if idx >= 0: self.date_format_combo.setCurrentIndex(idx)

            if hasattr(self, 'theme_combo'):
                idx = self.theme_combo.findText(theme.capitalize())
                if idx >= 0: self.theme_combo.setCurrentIndex(idx)
            
            if hasattr(self, 'panel_position_group'):
                panel_button_id = 1 if self.control_panel_on_right else 0
                panel_button_to_check = self.panel_position_group.button(panel_button_id)
                if panel_button_to_check: panel_button_to_check.setChecked(True)

            if hasattr(self, 'filename_toggle_grid'):
                self.filename_toggle_grid.setChecked(self.show_grid_filenames)

            # 뷰포트 속도 콤보박스 UI 업데이트 (만약 setup_settings_ui보다 먼저 호출된다면, 콤보박스 생성 후 설정 필요)
            if hasattr(self, 'viewport_speed_combo'): # 콤보박스가 이미 생성되었다면
                idx = self.viewport_speed_combo.findData(self.viewport_move_speed)
                if idx >= 0:
                    self.viewport_speed_combo.setCurrentIndex(idx)

            # 마우스 휠 라디오 버튼 UI 업데이트 (설정창이 생성된 후)
            if hasattr(self, 'mouse_wheel_photo_radio') and hasattr(self, 'mouse_wheel_none_radio'):
                if self.mouse_wheel_action == 'photo_navigation':
                    self.mouse_wheel_photo_radio.setChecked(True)
                else:
                    self.mouse_wheel_none_radio.setChecked(True)
        
            self.move_raw_files = loaded_data.get("move_raw_files", True)
            # update_raw_toggle_state()는 폴더 유효성 검사 후 호출 예정

            self.zoom_mode = loaded_data.get("zoom_mode", "Fit")
            self.zoom_spin_value = loaded_data.get("zoom_spin_value", 2.0)
            if self.zoom_mode == "Fit": self.fit_radio.setChecked(True)
            elif self.zoom_mode == "100%": self.zoom_100_radio.setChecked(True)
            elif self.zoom_mode == "Spin": self.zoom_spin_btn.setChecked(True)

            # SpinBox UI 업데이트 추가
            if hasattr(self, 'zoom_spin'):
                self.zoom_spin.setValue(int(self.zoom_spin_value * 100))
                logging.info(f"PhotoSortApp.load_state: 동적 줌 SpinBox 값 복원: {int(self.zoom_spin_value * 100)}%")

            if hasattr(self, 'folder_count_combo'):
                index = self.folder_count_combo.findData(self.folder_count)
                if index >= 0:
                    self.folder_count_combo.setCurrentIndex(index)

            self.minimap_toggle.setChecked(loaded_data.get("minimap_visible", True))

            # 3. 폴더 경로 및 파일 목록 관련 '상태 변수' 우선 설정
            self.current_folder = loaded_data.get("current_folder", "")
            self.raw_folder = loaded_data.get("raw_folder", "")
            raw_files_str = loaded_data.get("raw_files", {})
            self.raw_files = {k: Path(v) for k, v in raw_files_str.items() if v and Path(v).exists()} # 경로 유효성 검사 후
            self.folder_count = loaded_data.get("folder_count", 3)
            loaded_folders = loaded_data.get("target_folders", []) # 없으면 빈 리스트
            self.target_folders = (loaded_folders + [""] * self.folder_count)[:self.folder_count]
            self.is_raw_only_mode = loaded_data.get("is_raw_only_mode", False)
            self.previous_grid_mode = loaded_data.get("previous_grid_mode", None)

            # ===> 폴더 경로 상태 변수가 설정된 직후, UI 레이블에 '저장된 경로'를 먼저 반영 <===
            if self.current_folder and Path(self.current_folder).is_dir():
                self.folder_path_label.setText(self.current_folder)
            else:
                self.current_folder = "" # 유효하지 않으면 상태 변수도 비움
                self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))

            if self.raw_folder and Path(self.raw_folder).is_dir():
                self.raw_folder_path_label.setText(self.raw_folder)
            else:
                self.raw_folder = ""
                self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
            

            # ===> 앱 재시작 시 마지막 사용된 RAW 처리 방식 로드 <===
            # 이 값은 이미지 목록 로드 후, 실제 display_current_image/update_grid_view 전에 ImageLoader에 설정됨
            self.last_loaded_raw_method_from_state = loaded_data.get("last_used_raw_method", "preview")
            logging.info(f"PhotoSortApp.load_state: 직전 세션 RAW 처리 방식 로드: {self.last_loaded_raw_method_from_state}")


            # 4. 이미지 목록 로드 시도
            images_loaded_successfully = False
            if self.is_raw_only_mode:
                if self.raw_folder and Path(self.raw_folder).is_dir():
                    logging.info(f"PhotoSortApp.load_state: RAW 전용 모드 복원 시도 - 폴더: {self.raw_folder}")
                    images_loaded_successfully = self.reload_raw_files_from_state(self.raw_folder)
                    # reload_raw_files_from_state 내부에서 self.raw_folder_path_label.setText(self.raw_folder)가 이미 호출될 수 있음
                    # 여기서는 self.raw_folder_path_label.setText(self.raw_folder)를 다시 호출하지 않음
                    if not images_loaded_successfully:
                        logging.warning(f"PhotoSortApp.load_state: RAW 전용 모드 폴더({self.raw_folder})에서 파일 로드 실패.")
                        self.is_raw_only_mode = False
                        self.raw_folder = ""
                        self.image_files = []
                        self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로")) # 실패 시 초기화
            elif self.current_folder and Path(self.current_folder).is_dir(): # JPG 모드
                logging.info(f"PhotoSortApp.load_state: JPG 모드 복원 시도 - 폴더: {self.current_folder}")
                images_loaded_successfully = self.load_images_from_folder(self.current_folder) # 내부에서 folder_path_label 업데이트
                if images_loaded_successfully:
                    if self.raw_folder and Path(self.raw_folder).is_dir():
                        # self.raw_folder_path_label.setText(self.raw_folder) # 이미 위에서 설정됨
                        # self.match_raw_files(self.raw_folder) # 필요시 호출 또는 저장된 raw_files 사용
                        pass # raw_files는 이미 로드됨
                    else:
                        self.raw_folder = ""
                        self.raw_files = {}
                        self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
                else:
                    logging.warning(f"PhotoSortApp.load_state: JPG 모드 폴더({self.current_folder})에서 파일 로드 실패.")
                    self.current_folder = ""
                    self.image_files = []
                    self.folder_path_label.setText(LanguageManager.translate("폴더 경로")) # 실패 시 초기화
            else:
                logging.info("PhotoSortApp.load_state: 저장된 폴더 정보가 없거나 유효하지 않아 이미지 로드 건너뜀.")
                self.image_files = []

            # --- 로드 후 폴더 관련 UI '상태'(활성화, 버튼 텍스트 등) 최종 업데이트 ---
            self.update_jpg_folder_ui_state() # JPG 폴더 레이블 스타일/X버튼, JPG 로드 버튼 상태
            self.update_raw_folder_ui_state() # RAW 폴더 레이블 스타일/X버튼, RAW 이동 토글 상태
            self.update_match_raw_button_state()# RAW 관련 버튼 텍스트/상태
            self._rebuild_folder_selection_ui()

            # ===> ImageLoader 전략 설정 (이미지 목록 로드 성공 후, 뷰 업데이트 전) <===
            if images_loaded_successfully and self.image_files:
                # 앱 재시작 시에는 저장된 last_loaded_raw_method_from_state를 사용
                self.image_loader.set_raw_load_strategy(self.last_loaded_raw_method_from_state)
                logging.info(f"PhotoSortApp.load_state: ImageLoader 처리 방식 설정됨 (재시작): {self.last_loaded_raw_method_from_state}")

                # --- 재실행 시 RAW 디코딩 모드이면 진행률 대화상자 표시 ---
                if self.is_raw_only_mode and self.last_loaded_raw_method_from_state == "decode":
                    self._show_first_raw_decode_progress()

            elif hasattr(self, 'image_loader'): # 이미지가 없더라도 ImageLoader는 존재하므로 기본값 설정
                self.image_loader.set_raw_load_strategy("preview") # 이미지가 없으면 기본 preview
                logging.info(f"PhotoSortApp.load_state: 이미지 로드 실패/없음. ImageLoader 기본 'preview' 설정.")


            # 5. 뷰 상태 복원 (이미지 로드 성공 시)
            if images_loaded_successfully and self.image_files:
                self.thumbnail_panel.set_image_files(self.image_files)
                total_images = len(self.image_files)

                # <<< 최종 수정된 뷰 복원 로직 시작 >>>
                
                # 1. 저장된 상태 값들을 먼저 변수로 불러옵니다.
                saved_compare_mode = loaded_data.get("compare_mode_active", False)
                saved_grid_mode = loaded_data.get("grid_mode", "Off")
                image_B_path_str = loaded_data.get("image_B_path", "")

                # 2. 최종으로 적용할 모드를 결정합니다. (예외 조건 우선 처리)
                final_compare_mode = saved_compare_mode
                final_grid_mode = saved_grid_mode

                if self.is_raw_only_mode and self.last_loaded_raw_method_from_state == "decode":
                    logging.info("RAW+Decode 모드 재실행 감지. Grid/Compare 모드를 강제로 'Off'로 설정합니다.")
                    final_compare_mode = False
                    final_grid_mode = "Off"
                
                # B 캔버스 이미지가 없으면 Compare 모드를 강제로 비활성화합니다.
                if image_B_path_str and Path(image_B_path_str).exists():
                    self.image_B_path = Path(image_B_path_str)
                else:
                    self.image_B_path = None
                    final_compare_mode = False # B 이미지가 없으면 Compare 모드는 무조건 해제

                # 3. 최종 결정된 모드를 앱 상태 변수에 할당합니다.
                self.compare_mode_active = final_compare_mode
                self.grid_mode = final_grid_mode
                
                # 4. 최종 모드에 따라 UI 컨트롤(라디오 버튼, 콤보박스)의 상태를 명확하게 설정합니다.
                if self.compare_mode_active:
                    self.compare_radio.setChecked(True)
                elif self.grid_mode == "Off":
                    self.grid_off_radio.setChecked(True)
                else: # Grid On
                    self.grid_on_radio.setChecked(True)
                    combo_text = self.grid_mode.replace("x", " x ")
                    index = self.grid_size_combo.findText(combo_text)
                    if index != -1: self.grid_size_combo.setCurrentIndex(index)
                
                self.grid_size_combo.setEnabled(self.grid_mode != "Off" and not self.compare_mode_active)
                self.update_zoom_radio_buttons_state()

                # 5. 마지막으로 보고 있던 이미지 인덱스를 복원합니다.
                loaded_actual_current_image_index = loaded_data.get("current_image_index", -1)
                
                if not (0 <= loaded_actual_current_image_index < total_images):
                    loaded_actual_current_image_index = 0 if total_images > 0 else -1
                
                # 6. 최종 결정된 모드에 따라 뷰를 업데이트하고 이미지를 표시합니다.
                if self.grid_mode != "Off": # Grid On
                    rows, cols = self._get_grid_dimensions()
                    num_cells = rows * cols
                    self.grid_page_start_index = (loaded_actual_current_image_index // num_cells) * num_cells
                    self.current_grid_index = loaded_actual_current_image_index % num_cells
                    self.update_grid_view()
                else: # Grid Off 또는 Compare
                    self.current_image_index = loaded_actual_current_image_index
                    self._update_view_for_grid_change() # 뷰 구조 먼저 설정
                    self.display_current_image() # 그 다음 이미지 표시

                # 7. B 캔버스 이미지 복원 (필요한 경우)
                if self.compare_mode_active and self.image_B_path:
                    def restore_b_canvas():
                        self.original_pixmap_B = self.image_loader.load_image_with_orientation(str(self.image_B_path))
                        self._apply_zoom_to_canvas('B')
                        self._sync_viewports()
                        self.update_compare_filenames()
                    QTimer.singleShot(100, restore_b_canvas)
                
                # 8. 썸네일 패널 스크롤
                if 0 <= loaded_actual_current_image_index < total_images:
                    self.thumbnail_panel.model.set_current_index(loaded_actual_current_image_index)
                    QTimer.singleShot(100, lambda idx=loaded_actual_current_image_index: self.thumbnail_panel.scroll_to_index(idx))
                    
                    logging.info(f"앱 재실행: 썸네일 패널 스크롤 예약 (index: {loaded_actual_current_image_index}).")

                self.update_counter_layout()
                self.toggle_minimap(self.minimap_toggle.isChecked())
                if self.grid_mode == "Off":
                    self.start_background_thumbnail_preloading()
            else:
                logging.warning("PhotoSortApp.load_state: 이미지 목록 로드 실패 또는 대상 폴더에 파일 없음. UI 초기화.")
                self.image_files = []
                self.current_image_index = -1
                self.grid_page_start_index = 0
                self.current_grid_index = 0
                self.grid_mode = "Off"
                self.grid_off_radio.setChecked(True)
                self.update_zoom_radio_buttons_state()
                self.update_grid_view()
                self.update_file_info_display(None)
                self.update_counter_layout()
                self.toggle_minimap(False)
            
            # 6. 최종 UI 조정 및 포커스 설정
            QTimer.singleShot(0, self._apply_panel_position)
            self.setFocus()

            # --- 성능 프로필 콤보박스 UI 동기화 ---
            # 저장된 프로필이 있다면 수동으로 설정
            saved_profile = loaded_data.get("performance_profile")
            if saved_profile:
                HardwareProfileManager.set_profile_manually(saved_profile)
            
            self._sync_performance_profile_ui()
            # --- 동기화 끝 ---

            logging.info("PhotoSortApp.load_state: 상태 불러오기 완료됨.")
            return True # 정상적으로 상태 로드 완료

        except json.JSONDecodeError as e:
            logging.error(f"PhotoSortApp.load_state: 상태 파일 JSON 디코딩 오류: {e}. 기본 설정으로 시작합니다.")
            self.show_themed_message_box(QMessageBox.Warning, 
                                         LanguageManager.translate("상태 로드 오류"), 
                                         LanguageManager.translate("저장된 상태 파일을 읽는 중 오류가 발생했습니다. 기본 설정으로 시작합니다."))
            # 여기서 안전한 초기화 로직 호출
            self.initialize_to_default_state() # <<< 새 헬퍼 함수 호출
            self.update_all_ui_after_load_failure_or_first_run()
            QTimer.singleShot(0, self._apply_panel_position) # 패널 위치도 기본값으로
            self.setFocus()
            return True # 오류가 있었지만 기본값으로 계속 실행함을 알림
        except Exception as e: # JSONDecodeError 외의 다른 모든 예외
            logging.error(f"PhotoSortApp.load_state: 상태 불러오는 중 예외 발생: {e}")
            import traceback
            traceback.print_exc()
            self.show_themed_message_box(QMessageBox.Critical, 
                                         LanguageManager.translate("상태 로드 오류"), 
                                         f"{LanguageManager.translate('저장된 상태 파일을 불러오는 데 실패했습니다. 기본 설정으로 시작합니다.')}\n\nError: {e}")
            # 여기서도 안전한 초기화 로직 호출
            self.initialize_to_default_state() # <<< 새 헬퍼 함수 호출
            self.update_all_ui_after_load_failure_or_first_run()
            QTimer.singleShot(0, self._apply_panel_position)
            self.setFocus()
            logging.info("PhotoSortApp.load_state: 상태 불러오기 완료됨.")

            # 상태 로드가 완료된 후, 최종 언어 설정에 맞게 모든 컨트롤의 텍스트를 업데이트합니다.
            self.update_all_settings_controls_text()

            return True # 정상적으로 상태 로드 완료

    def _sync_performance_profile_ui(self):
        """현재 활성화된 HardwareProfileManager 프로필을 UI 콤보박스와 동기화합니다."""
        # 저장된 프로필이 있다면 수동으로 설정 (load_state에서 호출 시)
        # 이 부분은 load_state에서만 처리하도록 분리하는 것이 더 명확할 수 있습니다.
        # 여기서는 현재 활성화된 프로필을 UI에 반영하는 데 집중합니다.
        
        current_profile_key = HardwareProfileManager.get_current_profile_key()
        if hasattr(self, 'performance_profile_combo'):
            index = self.performance_profile_combo.findData(current_profile_key)
            if index != -1:
                # 시그널 발생을 막기 위해 blockSignals 사용
                self.performance_profile_combo.blockSignals(True)
                self.performance_profile_combo.setCurrentIndex(index)
                self.performance_profile_combo.blockSignals(False)
                logging.debug(f"성능 프로필 UI 동기화 완료: '{current_profile_key}'")

    def initialize_to_default_state(self):
        """애플리케이션 상태를 안전한 기본값으로 초기화합니다 (파일 로드 실패 시 등)."""
        logging.info("PhotoSortApp.initialize_to_default_state: 앱 상태를 기본값으로 초기화합니다.")

        # --- 1. 모든 백그라운드 작업 및 타이머 중지 ---
        logging.debug("  -> 활성 타이머 및 백그라운드 작업 중지...")
        
        # 리소스 매니저를 통해 모든 스레드/프로세스 풀의 작업을 취소합니다.
        if hasattr(self, 'resource_manager'):
            self.resource_manager.cancel_all_tasks()
        
        # 그리드 썸네일 전용 스레드 풀의 작업도 취소합니다.
        if hasattr(self, 'active_thumbnail_futures'):
            for future in self.active_thumbnail_futures:
                future.cancel()
            self.active_thumbnail_futures.clear()

        # 모든 활성 타이머를 중지합니다.
        if hasattr(self, 'loading_indicator_timer') and self.loading_indicator_timer.isActive():
            self.loading_indicator_timer.stop()
        if hasattr(self, 'state_save_timer') and self.state_save_timer.isActive():
            self.state_save_timer.stop()
        if hasattr(self, 'viewport_move_timer') and self.viewport_move_timer.isActive():
            self.viewport_move_timer.stop()
        if hasattr(self, 'idle_preload_timer') and self.idle_preload_timer.isActive():
            self.idle_preload_timer.stop()
        # raw_result_processor_timer와 memory_monitor_timer는 앱 전역에서 계속 실행되어야 하므로 중지하지 않습니다.

        # --- 2. 상태 변수 초기화 ---
        logging.debug("  -> 상태 변수 초기화...")

        # 폴더 및 파일 관련 상태
        self.current_folder = ""
        self.raw_folder = ""
        self.image_files = []
        self.raw_files = {}
        self.is_raw_only_mode = False
        self.move_raw_files = True
        self.folder_count = 3
        self.target_folders = [""] * self.folder_count
        
        # 뷰 관련 상태
        self.zoom_mode = "Fit"
        self.zoom_spin_value = 2.0
        self.grid_mode = "Off"
        self.current_image_index = -1
        self.current_grid_index = 0
        self.grid_page_start_index = 0
        self.previous_grid_mode = None
        self.original_pixmap = None
        self.compare_mode_active = False
        self.image_B_path = None
        self.original_pixmap_B = None

        # 캐시 초기화
        if hasattr(self, 'image_loader'):
            self.image_loader.clear_cache()
            self.image_loader.set_raw_load_strategy("preview")
        self.fit_pixmap_cache.clear()
        self.last_fit_size = (0,0)

        # 기타 UI 및 상호작용 관련 상태
        self.last_processed_camera_model = None
        self.viewport_move_speed = 5
        self.show_grid_filenames = False
        self.control_panel_on_right = False
        self.pressed_keys_for_viewport.clear()
        self.pressed_number_keys.clear()
        self.is_potential_drag = False
        self.is_idle_preloading_active = False

        # Undo/Redo 히스토리 초기화
        self.move_history = []
        self.history_pointer = -1
        
        logging.info("  -> 상태 초기화 완료.")

    def update_all_ui_after_load_failure_or_first_run(self):
        """load_state 실패 또는 첫 실행 시 UI를 기본 상태로 설정하는 헬퍼"""
        self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        for label in self.folder_path_labels:
            label.setText(LanguageManager.translate("폴더 경로"))
        self.update_jpg_folder_ui_state()
        self.update_raw_folder_ui_state()
        self.update_all_folder_labels_state()
        self.update_match_raw_button_state()
        self.grid_mode = "Off"; self.grid_off_radio.setChecked(True)
        self.zoom_mode = "Fit"; self.fit_radio.setChecked(True)
        self.zoom_spin_value = 2.0
        # SpinBox UI 업데이트 추가
        if hasattr(self, 'zoom_spin'):
            self.zoom_spin.setValue(int(self.zoom_spin_value * 100))
        self.update_zoom_radio_buttons_state()
        self.display_current_image() # 빈 화면 표시
        self.update_counter_layout()
        self.toggle_minimap(False)
        QTimer.singleShot(0, self._apply_panel_position)
        self.setFocus()

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
        """ 파일 이동 기록을 히스토리에 추가하고 포인터 업데이트 (배치 작업 지원) """
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

    def add_batch_move_history(self, move_entries):
        """ 배치 파일 이동 기록을 히스토리에 추가 """
        if not move_entries:
            return
            
        # 배치 작업을 하나의 히스토리 엔트리로 묶음
        batch_entry = {
            "type": "batch",
            "entries": move_entries,
            "timestamp": datetime.now().isoformat()
        }
        
        logging.debug(f"Adding batch to history: {len(move_entries)} entries")
        self.add_move_history(batch_entry)

    def undo_move(self):
        """ 마지막 파일 이동 작업을 취소 (Undo) - 배치 작업 지원 """
        if self.history_pointer < 0:
            logging.warning("Undo: 히스토리 없음")
            return # 실행 취소할 작업 없음

        # 현재 포인터에 해당하는 기록 가져오기
        move_info = self.move_history[self.history_pointer]
        logging.debug(f"Undoing: {move_info}") # 디버깅 로그

        # 배치 작업인지 확인
        if isinstance(move_info, dict) and move_info.get("type") == "batch":
            # 배치 작업 Undo
            self.undo_batch_move(move_info["entries"])
        else:
            # 단일 작업 Undo (기존 로직)
            self.undo_single_move(move_info)

        # 히스토리 포인터 이동
        self.history_pointer -= 1
        logging.debug(f"Undo complete. History pointer: {self.history_pointer}")

    def undo_batch_move(self, batch_entries):
        """ 배치 이동 작업을 취소 """
        try:
            # 배치 엔트리들을 역순으로 처리 (이동 순서와 반대로)
            for move_info in reversed(batch_entries):
                self.undo_single_move_internal(move_info)
            
            # UI 업데이트는 마지막에 한 번만
            self.update_ui_after_undo_batch(batch_entries)
            
        except Exception as e:
            logging.error(f"배치 Undo 중 오류 발생: {e}")
            self.show_themed_message_box(
                QMessageBox.Critical, 
                LanguageManager.translate("에러"), 
                f"{LanguageManager.translate('실행 취소 중 오류 발생')}: {str(e)}"
            )

    def undo_single_move_internal(self, move_info):
        """ 단일 이동 작업을 취소 (UI 업데이트 없음) """
        jpg_source_path = Path(move_info["jpg_source"])
        jpg_target_path = Path(move_info["jpg_target"])
        raw_source_path = Path(move_info["raw_source"]) if move_info["raw_source"] else None
        raw_target_path = Path(move_info["raw_target"]) if move_info["raw_target"] else None
        index_before_move = move_info["index_before_move"]

        # 1. JPG 파일 원래 위치로 이동
        if jpg_target_path.exists():
            shutil.move(str(jpg_target_path), str(jpg_source_path))
            logging.debug(f"Undo: Moved {jpg_target_path} -> {jpg_source_path}")

        # 2. RAW 파일 원래 위치로 이동
        if raw_source_path and raw_target_path and raw_target_path.exists():
            shutil.move(str(raw_target_path), str(raw_source_path))
            logging.debug(f"Undo: Moved RAW {raw_target_path} -> {raw_source_path}")

        # 3. 파일 목록 복원 (중복 검사 추가)
        if jpg_source_path not in self.image_files:
            if 0 <= index_before_move <= len(self.image_files):
                self.image_files.insert(index_before_move, jpg_source_path)
                logging.debug(f"Undo: Inserted {jpg_source_path.name} at index {index_before_move}")
            else:
                self.image_files.append(jpg_source_path)
                logging.debug(f"Undo: Appended {jpg_source_path.name} to end of list")
        else:
            logging.warning(f"Undo: Skipped duplicate file insertion for {jpg_source_path.name}")

        # 4. RAW 파일 딕셔너리 복원 (중복 검사 추가)
        if raw_source_path:
            if jpg_source_path.stem not in self.raw_files:
                self.raw_files[jpg_source_path.stem] = raw_source_path
                logging.debug(f"Undo: Restored RAW file mapping for {jpg_source_path.stem}")
            else:
                logging.warning(f"Undo: Skipped duplicate RAW file mapping for {jpg_source_path.stem}")

        if move_info.get("mode") == "CompareB":
            jpg_source_path = Path(move_info["jpg_source"])
            self.image_B_path = jpg_source_path
            # B 캔버스용 pixmap도 다시 로드
            self.original_pixmap_B = self.image_loader.load_image_with_orientation(str(self.image_B_path))
            self.update_compare_filenames()
            logging.debug(f"Undo: Restored image to Canvas B: {self.image_B_path.name}")

    def undo_single_move(self, move_info):
        """ 단일 이동 작업을 취소 (기존 로직) """
        self.undo_single_move_internal(move_info)
        
        mode_before_move = move_info.get("mode", "Off")
        index_before_move = move_info["index_before_move"]
        
        self.force_refresh = True
        
        if mode_before_move == "CompareB":
            a_index = move_info.get("a_index_before_move", 0)
            if a_index >= len(self.image_files):
                a_index = len(self.image_files) - 1
            self.current_image_index = a_index

            self.compare_mode_active = True
            self.grid_mode = "Off" 
            self.compare_radio.setChecked(True)
            self._update_view_for_grid_change()
            
            # <<< 수정 시작: B 캔버스 복원 로직을 타이머로 지연 >>>
            def restore_compare_view():
                self.display_current_image()
                self._apply_zoom_to_canvas('B')
                self._sync_viewports() # 타이머 콜백 내에서 동기화

            QTimer.singleShot(20, restore_compare_view) # 20ms 지연으로 안정성 확보
            # <<< 수정 끝 >>>

        elif mode_before_move == "Off":
            self.current_image_index = index_before_move
            if self.grid_mode != "Off" or self.compare_mode_active:
                self.compare_mode_active = False
                self.grid_mode = "Off"
                self.grid_off_radio.setChecked(True)
                self._update_view_for_grid_change()
            self.display_current_image()
        else: # Grid 모드
            self.compare_mode_active = False
            self.grid_mode = mode_before_move
            
            rows, cols = self._get_grid_dimensions()
            if rows == 0:
                logging.error("Undo: Grid 모드 복원 중 잘못된 grid_mode 값 감지")
                self.grid_mode = "2x2"
                rows, cols = self._get_grid_dimensions()

            num_cells = rows * cols
            
            self.grid_page_start_index = (index_before_move // num_cells) * num_cells
            self.current_grid_index = index_before_move % num_cells
            self._update_view_for_grid_change()
        
        self.update_counters()
        self.thumbnail_panel.set_image_files(self.image_files)
        self.update_thumbnail_current_index()

    def update_ui_after_undo_batch(self, batch_entries):
        """ 배치 Undo 후 UI 업데이트 """
        if not batch_entries:
            return

        # 첫 번째 엔트리의 모드와 인덱스를 기준으로 UI 상태 복원
        first_entry = batch_entries[0]
        mode_before_move = first_entry.get("mode", "Off")
        first_index = first_entry["index_before_move"]
        
        # 강제 새로고침 플래그 설정
        self.force_refresh = True

        # 복원할 이미지들의 페이지 내 인덱스 계산
        restored_grid_indices = set()
        target_page_start_index = -1

        if mode_before_move != "Off":
            rows, cols = self._get_grid_dimensions() # 올바른 그리드 크기 가져오기
            num_cells = rows * cols
            target_page_start_index = (first_index // num_cells) * num_cells
            
            for entry in batch_entries:
                idx = entry["index_before_move"]
                if target_page_start_index <= idx < target_page_start_index + num_cells:
                    restored_grid_indices.add(idx - target_page_start_index)

        # UI 업데이트
        if mode_before_move == "Off":
            self.current_image_index = first_index
            if self.grid_mode != "Off":
                self.grid_mode = "Off"
                self.grid_off_radio.setChecked(True)
                self.update_zoom_radio_buttons_state()
                self.update_counter_layout()
            if self.zoom_mode == "Fit":
                self.last_fit_size = (0, 0)
                self.fit_pixmap_cache.clear()
            self.display_current_image()
        else: # Grid 모드 복원
            self.grid_page_start_index = target_page_start_index
            self.current_grid_index = first_index - target_page_start_index # primary 선택
            self.selected_grid_indices = restored_grid_indices # 다중 선택 상태 복원
            self.primary_selected_index = first_index

            if self.grid_mode != mode_before_move:
                self.grid_mode = mode_before_move
                if mode_before_move == "2x2": self.grid_size_combo.setCurrentIndex(0)
                elif mode_before_move == "3x3": self.grid_size_combo.setCurrentIndex(1)
                elif mode_before_move == "4x4": self.grid_size_combo.setCurrentIndex(2)
                self.grid_on_radio.setChecked(True)
                self.update_zoom_radio_buttons_state()
                self.update_counter_layout()
                
            self.update_grid_view()

        self.update_counters()

    def redo_move(self):
        """ 취소된 파일 이동 작업을 다시 실행 (Redo) - 배치 작업 지원 """
        if self.history_pointer >= len(self.move_history) - 1:
            logging.warning("Redo: 히스토리 없음")
            return # 다시 실행할 작업 없음

        # 다음 포인터로 이동하고 해당 기록 가져오기
        self.history_pointer += 1
        move_info = self.move_history[self.history_pointer]
        logging.debug(f"Redoing: {move_info}")

        # 배치 작업인지 확인
        if isinstance(move_info, dict) and move_info.get("type") == "batch":
            # 배치 작업 Redo
            self.redo_batch_move(move_info["entries"])
        else:
            # 단일 작업 Redo (기존 로직)
            self.redo_single_move(move_info)

        logging.debug(f"Redo complete. History pointer: {self.history_pointer}")

    def redo_batch_move(self, batch_entries):
        """ 배치 이동 작업을 다시 실행 """
        try:
            # 배치 엔트리들을 순서대로 처리
            for move_info in batch_entries:
                self.redo_single_move_internal(move_info)
            
            # UI 업데이트는 마지막에 한 번만
            self.update_ui_after_redo_batch(batch_entries)
            
        except Exception as e:
            logging.error(f"배치 Redo 중 오류 발생: {e}")
            self.show_themed_message_box(
                QMessageBox.Critical, 
                LanguageManager.translate("에러"), 
                f"{LanguageManager.translate('다시 실행 중 오류 발생')}: {str(e)}"
            )

    def redo_single_move_internal(self, move_info):
        """ 단일 이동 작업을 다시 실행 (UI 업데이트 없음) """
        jpg_source_path = Path(move_info["jpg_source"])
        jpg_target_path = Path(move_info["jpg_target"])
        raw_source_path = Path(move_info["raw_source"]) if move_info["raw_source"] else None
        raw_target_path = Path(move_info["raw_target"]) if move_info["raw_target"] else None

        # 1. JPG 파일 다시 대상 위치로 이동
        if jpg_target_path.exists():
            logging.warning(f"경고: Redo 대상 위치에 이미 파일 존재: {jpg_target_path}")

        if jpg_source_path.exists():
            shutil.move(str(jpg_source_path), str(jpg_target_path))
            logging.debug(f"Redo: Moved {jpg_source_path} -> {jpg_target_path}")

        # 2. RAW 파일 다시 대상 위치로 이동
        if raw_source_path and raw_target_path:
            if raw_target_path.exists():
                logging.warning(f"경고: Redo 대상 RAW 위치에 이미 파일 존재: {raw_target_path}")
            if raw_source_path.exists():
                shutil.move(str(raw_source_path), str(raw_target_path))
                logging.debug(f"Redo: Moved RAW {raw_source_path} -> {raw_target_path}")

        # 3. 파일 목록 업데이트
        try:
            self.image_files.remove(jpg_source_path)
        except ValueError:
            logging.warning(f"경고: Redo 시 파일 목록에서 경로를 찾지 못함: {jpg_source_path}")

        # 4. RAW 파일 딕셔너리 업데이트
        if raw_source_path and jpg_source_path.stem in self.raw_files:
            del self.raw_files[jpg_source_path.stem]

    def update_ui_after_redo_batch(self, batch_entries):
        """ 배치 Redo 후 UI 업데이트 """
        if not batch_entries:
            return
            
        first_entry = batch_entries[0]
        mode_at_move = first_entry.get("mode", "Off")
        
        self.force_refresh = True
        
        if self.image_files:
            first_removed_index = first_entry["index_before_move"]
            new_index = min(first_removed_index, len(self.image_files) - 1)
            if new_index < 0: new_index = 0
            
            if mode_at_move == "Off":
                self.current_image_index = new_index
                if self.grid_mode != "Off":
                    self.grid_mode = "Off"
                    self.grid_off_radio.setChecked(True)
                    self.update_zoom_radio_buttons_state()
                    self.update_counter_layout()
                if self.zoom_mode == "Fit":
                    self.last_fit_size = (0, 0)
                    self.fit_pixmap_cache.clear()
                self.display_current_image()
            else:
                # Grid 모드
                if self.grid_mode != mode_at_move:
                    self.grid_mode = mode_at_move
                    # 새로운 UI 상태로 업데이트
                    self.grid_on_radio.setChecked(True)
                    self.grid_size_combo.setEnabled(True)
                    combo_text = self.grid_mode.replace("x", " x ")
                    index = self.grid_size_combo.findText(combo_text)
                    if index != -1: self.grid_size_combo.setCurrentIndex(index)
                    self.update_zoom_radio_buttons_state()
                    self.update_counter_layout()

                rows, cols = self._get_grid_dimensions()
                num_cells = rows * cols
                self.grid_page_start_index = (new_index // num_cells) * num_cells
                self.current_grid_index = new_index % num_cells
                self.update_grid_view()
        else:
            # 모든 파일이 이동된 경우
            self.current_image_index = -1
            if self.grid_mode != "Off":
                self.grid_mode = "Off"
                self.grid_off_radio.setChecked(True)
                self.update_zoom_radio_buttons_state()
            self.display_current_image()
        
        self.update_counters()

    def redo_single_move(self, move_info):
        """ 단일 이동 작업을 다시 실행 (기존 로직) """
        self.redo_single_move_internal(move_info)
        
        mode_at_move = move_info.get("mode", "Off")
        
        if self.image_files:
            redo_removed_index = move_info["index_before_move"]
            new_index = min(redo_removed_index, len(self.image_files) - 1)
            if new_index < 0: new_index = 0
            
            self.force_refresh = True

            if mode_at_move == "Off":
                self.current_image_index = new_index
                if self.grid_mode != "Off":
                    self.grid_mode = "Off"
                    self.grid_off_radio.setChecked(True)
                    self.update_zoom_radio_buttons_state()
                if self.zoom_mode == "Fit":
                    self.last_fit_size = (0, 0)
                    self.fit_pixmap_cache.clear()
                self.display_current_image()
            else:
                # Grid 모드
                if self.grid_mode != mode_at_move:
                    self.grid_mode = mode_at_move
                    # 새로운 UI 상태로 업데이트
                    self.grid_on_radio.setChecked(True)
                    self.grid_size_combo.setEnabled(True)
                    combo_text = self.grid_mode.replace("x", " x ")
                    index = self.grid_size_combo.findText(combo_text)
                    if index != -1: self.grid_size_combo.setCurrentIndex(index)
                    self.update_zoom_radio_buttons_state()

                rows, cols = self._get_grid_dimensions()
                num_cells = rows * cols
                self.grid_page_start_index = (new_index // num_cells) * num_cells
                self.current_grid_index = new_index % num_cells
                self.update_grid_view()
        else:
            # 모든 파일이 이동된 경우
            self.current_image_index = -1
            if self.grid_mode != "Off":
                self.grid_mode = "Off"
                self.grid_off_radio.setChecked(True)
                self.update_zoom_radio_buttons_state()
            self.display_current_image()

        self.update_counters()

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
        if hasattr(self, 'grid_thumbnail_cache'):
            for key in self.grid_thumbnail_cache:
                self.grid_thumbnail_cache[key].clear()
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

        # 폴더 로더 스레드를 종료.
        if hasattr(self, 'folder_loader_thread') and self.folder_loader_thread.isRunning():
            logging.info("폴더 로더 스레드 종료 중...")
            if hasattr(self, 'folder_loader_worker'):
                self.folder_loader_worker.stop() # 진행 중인 작업을 중단하도록 신호
            self.folder_loader_thread.quit()     # 스레드의 이벤트 루프 종료
            if not self.folder_loader_thread.wait(1000): # 1초간 기다림
                self.folder_loader_thread.terminate()    # 응답 없으면 강제 종료
            logging.info("폴더 로더 스레드 종료 완료")

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
            rows, cols = self._get_grid_dimensions()
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

    def highlight_folder_label(self, folder_index, highlight):
        """분류 폴더 레이블에 숫자 키 누름 하이라이트를 적용합니다."""
        if folder_index < 0 or folder_index >= len(self.folder_path_labels):
            return
        try:
            label = self.folder_path_labels[folder_index]
            # EditableFolderPathLabel에 새로 추가한 메서드 호출
            label.apply_keypress_highlight(highlight)
        except Exception as e:
            logging.error(f"highlight_folder_label 오류: {e}")

    def center_viewport(self):
        """뷰포트를 이미지 중앙으로 이동 (Zoom 100% 또는 Spin 모드에서만)"""
        try:
            # 전제 조건 확인
            if (self.grid_mode != "Off" or 
                self.zoom_mode not in ["100%", "Spin"] or 
                not self.original_pixmap):
                logging.debug("center_viewport: 조건 불만족 (Grid Off, Zoom 100%/Spin, 이미지 필요)")
                return False
            
            # 뷰포트 크기 가져오기
            view_width = self.scroll_area.width()
            view_height = self.scroll_area.height()
            
            # 이미지 크기 계산
            if self.zoom_mode == "100%":
                img_width = self.original_pixmap.width()
                img_height = self.original_pixmap.height()
            else:  # Spin 모드
                img_width = self.original_pixmap.width() * self.zoom_spin_value
                img_height = self.original_pixmap.height() * self.zoom_spin_value
            
            # 중앙 정렬 위치 계산
            if img_width <= view_width:
                # 이미지가 뷰포트보다 작으면 중앙 정렬
                new_x = (view_width - img_width) // 2
            else:
                # 이미지가 뷰포트보다 크면 이미지 중앙이 뷰포트 중앙에 오도록
                new_x = (view_width - img_width) // 2
            
            if img_height <= view_height:
                # 이미지가 뷰포트보다 작으면 중앙 정렬
                new_y = (view_height - img_height) // 2
            else:
                # 이미지가 뷰포트보다 크면 이미지 중앙이 뷰포트 중앙에 오도록
                new_y = (view_height - img_height) // 2
            
            # 위치 제한 (패닝 범위 계산과 동일한 로직)
            if img_width <= view_width:
                x_min = x_max = (view_width - img_width) // 2
            else:
                x_min = min(0, view_width - img_width)
                x_max = 0
            
            if img_height <= view_height:
                y_min = y_max = (view_height - img_height) // 2
            else:
                y_min = min(0, view_height - img_height)
                y_max = 0
            
            # 범위 내로 제한
            new_x = max(x_min, min(x_max, new_x))
            new_y = max(y_min, min(y_max, new_y))
            
            # 이미지 위치 업데이트
            self.image_label.move(int(new_x), int(new_y))
            
            # 뷰포트 포커스 정보 업데이트
            if self.current_image_orientation:
                current_rel_center = self._get_current_view_relative_center()
                self.current_active_rel_center = current_rel_center
                self.current_active_zoom_level = self.zoom_mode
                
                # 방향별 뷰포트 포커스 저장
                self._save_orientation_viewport_focus(
                    self.current_image_orientation, 
                    current_rel_center, 
                    self.zoom_mode
                )
            
            # 미니맵 업데이트
            if self.minimap_visible and self.minimap_widget.isVisible():
                self.update_minimap()
            
            logging.info(f"뷰포트 중앙 이동 완료: {self.zoom_mode} 모드, 위치: ({new_x}, {new_y})")
            return True
            
        except Exception as e:
            logging.error(f"center_viewport 오류: {e}")
            return False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            focused_widget = QApplication.focusWidget()
            if isinstance(focused_widget, (QLineEdit, QSpinBox, QTextBrowser)):
                return super().eventFilter(obj, event)
            if self.is_input_dialog_active:
                return super().eventFilter(obj, event)
            key = event.key()
            modifiers = event.modifiers()
            # --- 숫자 키 처리 (하이라이트만) ---
            if Qt.Key_1 <= key <= (Qt.Key_1 + self.folder_count - 1):
                if not event.isAutoRepeat():
                    folder_index = key - Qt.Key_1
                    self.highlight_folder_label(folder_index, True)
                    self.pressed_number_keys.add(key)
                return True
            # --- 다른 키 처리들 ---
            is_mac = sys.platform == 'darwin'
            ctrl_modifier = Qt.MetaModifier if is_mac else Qt.ControlModifier
            if modifiers == ctrl_modifier and key == Qt.Key_Z: self.undo_move(); return True
            elif modifiers == ctrl_modifier and key == Qt.Key_Y: self.redo_move(); return True
            elif (modifiers & ctrl_modifier) and (modifiers & Qt.ShiftModifier) and key == Qt.Key_Z: self.redo_move(); return True
            if key == Qt.Key_Return or key == Qt.Key_Enter:
                if self.file_list_dialog is None or not self.file_list_dialog.isVisible():
                    if self.image_files:
                        current_selected_index = -1
                        if self.grid_mode == "Off":
                            current_selected_index = self.current_image_index
                        else:
                            potential_index = self.grid_page_start_index + self.current_grid_index
                            if 0 <= potential_index < len(self.image_files):
                                current_selected_index = potential_index
                        if current_selected_index != -1:
                            self.file_list_dialog = FileListDialog(self.image_files, current_selected_index, self.image_loader, self)
                            self.file_list_dialog.finished.connect(self.on_file_list_dialog_closed)
                            self.file_list_dialog.show()
                else:
                    self.file_list_dialog.activateWindow()
                    self.file_list_dialog.raise_()
                return True
            
            if key == Qt.Key_G:
                if self.grid_mode == "Off":
                    self.grid_on_radio.setChecked(True)
                    self._on_grid_mode_toggled(self.grid_on_radio)
                else:
                    self.grid_off_radio.setChecked(True)
                    self._on_grid_mode_toggled(self.grid_off_radio)
                return True

            elif key == Qt.Key_C:
                # Compare 모드는 Grid Off 상태에서만 토글 가능
                if self.grid_mode == "Off":
                    if self.compare_mode_active:
                        # Compare -> Grid Off
                        self.grid_off_radio.setChecked(True)
                        self._on_grid_mode_toggled(self.grid_off_radio)
                    else:
                        # Grid Off -> Compare
                        self.compare_radio.setChecked(True)
                        self._on_grid_mode_toggled(self.compare_radio)
                return True

            if key == Qt.Key_F1: # Zoom Fit
                self.fit_radio.setChecked(True)
                self.on_zoom_changed(self.fit_radio)
                return True
            elif key == Qt.Key_F2: # Zoom 100%
                if self.zoom_100_radio.isEnabled():
                    self.zoom_100_radio.setChecked(True)
                    self.on_zoom_changed(self.zoom_100_radio)
                return True
            elif key == Qt.Key_F3: # Zoom Spin
                if self.zoom_spin_btn.isEnabled():
                    self.zoom_spin_btn.setChecked(True)
                    self.on_zoom_changed(self.zoom_spin_btn)
                return True
                
            elif key == Qt.Key_F5: self.refresh_folder_contents(); return True
            elif key == Qt.Key_Delete: self.reset_program_state(); return True
            if key == Qt.Key_Escape:
                if self.file_list_dialog and self.file_list_dialog.isVisible(): self.file_list_dialog.reject(); return True
                if self.zoom_mode != "Fit":
                    self.last_active_zoom_mode = self.zoom_mode
                    self.fit_radio.setChecked(True)
                    self.on_zoom_changed(self.fit_radio)
                    return True
                elif self.grid_mode == "Off" and self.previous_grid_mode and self.previous_grid_mode != "Off":
                    self.grid_on_radio.setChecked(True)
                    idx = self.grid_size_combo.findText(self.previous_grid_mode.replace("x", " x "))
                    if idx != -1: self.grid_size_combo.setCurrentIndex(idx)
                    self._on_grid_mode_toggled(self.grid_on_radio)
                    return True
            if key == Qt.Key_R:
                if (self.grid_mode == "Off" and self.zoom_mode in ["100%", "Spin"] and self.original_pixmap):
                    self.center_viewport()
                    return True
            if key == Qt.Key_Space:
                if self.grid_mode == "Off":
                    if self.original_pixmap:
                        if self.zoom_mode == "Fit":
                            target_zoom_mode = self.last_active_zoom_mode
                            
                            ### 변경 시작: 뷰포트 복구 로직 추가 ###
                            # 1. 현재 이미지의 방향 가져오기
                            current_orientation = self.current_image_orientation
                            if current_orientation:
                                # 2. 해당 방향에 저장된 뷰포트 정보 가져오기
                                saved_rel_center, _ = self._get_orientation_viewport_focus(current_orientation, target_zoom_mode)
                                # 3. '활성' 뷰포트 정보를 복구된 값으로 설정
                                self.current_active_rel_center = saved_rel_center
                            else:
                                # 방향 정보가 없으면 중앙으로 (안전 장치)
                                self.current_active_rel_center = QPointF(0.5, 0.5)
                            ### 변경 끝 ###

                            # 4. 줌 모드 및 UI 업데이트
                            self.zoom_mode = target_zoom_mode
                            if target_zoom_mode == "100%": self.zoom_100_radio.setChecked(True)
                            elif target_zoom_mode == "Spin": self.zoom_spin_btn.setChecked(True)

                            # 5. apply_zoom_to_image를 위한 상태 설정
                            self.current_active_zoom_level = target_zoom_mode
                            self.zoom_change_trigger = "space_key_to_zoom" # 이 트리거는 이제 복구된 active_rel_center를 사용
                            
                            # 6. 뷰 적용
                            self.apply_zoom_to_image()
                            self.toggle_minimap(self.minimap_toggle.isChecked())
                        else: # 100% or Spin
                            self.last_active_zoom_mode = self.zoom_mode
                            self.zoom_mode = "Fit"
                            self.fit_radio.setChecked(True)
                            self.apply_zoom_to_image()
                    return True
                else: # Grid On
                    current_selected_grid_index = self.grid_page_start_index + self.current_grid_index
                    if 0 <= current_selected_grid_index < len(self.image_files):
                        self.current_image_index = current_selected_grid_index
                        self.force_refresh = True
                    self.previous_grid_mode = self.grid_mode
                    self.grid_mode = "Off"
                    self.grid_off_radio.setChecked(True)
                    self.space_pressed = True
                    self.update_thumbnail_panel_visibility() # 썸네일 패널 표시
                    self.update_grid_view()
                    self.update_zoom_radio_buttons_state()
                    self.update_counter_layout()
                    return True
            if self.zoom_mode == "Spin" and (key == Qt.Key_Z or key == Qt.Key_X):
                if hasattr(self, 'zoom_spin'):
                    current_zoom = self.zoom_spin.value()
                    
                    if key == Qt.Key_X: # Zoom In
                        new_zoom = min(500, current_zoom + 20)
                    else: # key == Qt.Key_Z, Zoom Out
                        new_zoom = max(10, current_zoom - 20)
                    
                    if new_zoom != current_zoom:
                        self.zoom_spin.setValue(new_zoom)
                return True

            is_viewport_move_condition = (self.grid_mode == "Off" and self.zoom_mode in ["100%", "Spin"] and self.original_pixmap)
            key_to_add_for_viewport = None
            if is_viewport_move_condition:
                if modifiers & Qt.ShiftModifier:
                    if key == Qt.Key_A: key_to_add_for_viewport = Qt.Key_Left
                    elif key == Qt.Key_D: key_to_add_for_viewport = Qt.Key_Right
                    elif key == Qt.Key_W: key_to_add_for_viewport = Qt.Key_Up
                    elif key == Qt.Key_S: key_to_add_for_viewport = Qt.Key_Down
                elif not (modifiers & Qt.ShiftModifier):
                    if key == Qt.Key_Left: key_to_add_for_viewport = Qt.Key_Left
                    elif key == Qt.Key_Right: key_to_add_for_viewport = Qt.Key_Right
                    elif key == Qt.Key_Up: key_to_add_for_viewport = Qt.Key_Up
                    elif key == Qt.Key_Down: key_to_add_for_viewport = Qt.Key_Down
            if key_to_add_for_viewport:
                if not event.isAutoRepeat():
                    if key_to_add_for_viewport not in self.pressed_keys_for_viewport:
                        self.pressed_keys_for_viewport.add(key_to_add_for_viewport)
                    if not self.viewport_move_timer.isActive():
                        self.viewport_move_timer.start()
                return True
            if self.grid_mode == "Off":
                if not (modifiers & Qt.ShiftModifier):
                    if key == Qt.Key_A or key == Qt.Key_W: self.show_previous_image(); return True
                    elif key == Qt.Key_D or key == Qt.Key_S: self.show_next_image(); return True
                if self.zoom_mode == "Fit" and not (modifiers & Qt.ShiftModifier):
                    if key == Qt.Key_Left or key == Qt.Key_Up: self.show_previous_image(); return True
                    elif key == Qt.Key_Right or key == Qt.Key_Down: self.show_next_image(); return True
            elif self.grid_mode != "Off":
                rows, cols = self._get_grid_dimensions()
                if modifiers & Qt.ShiftModifier:
                    if (key == Qt.Key_A or key == Qt.Key_Left) and not (modifiers & Qt.ControlModifier): self.navigate_to_adjacent_page(-1); return True
                    elif key == Qt.Key_D or key == Qt.Key_Right: self.navigate_to_adjacent_page(1); return True
                else:
                    if (key == Qt.Key_A or key == Qt.Key_Left) and not (modifiers & Qt.ControlModifier): self.navigate_grid(-1); return True
                    elif key == Qt.Key_D or key == Qt.Key_Right: self.navigate_grid(1); return True
                    elif key == Qt.Key_W or key == Qt.Key_Up: self.navigate_grid(-cols); return True
                    elif key == Qt.Key_S or key == Qt.Key_Down: self.navigate_grid(cols); return True
            if key == Qt.Key_A and (modifiers & Qt.ControlModifier):
                if self.grid_mode != "Off" and self.image_files:
                    self.toggle_select_all_in_page()
                return True
            return False
        elif event.type() == QEvent.KeyRelease:
            key = event.key()
            if self.is_input_dialog_active or event.isAutoRepeat():
                return super().eventFilter(obj, event)
            if key in self.pressed_number_keys:
                folder_index = key - Qt.Key_1
                self.highlight_folder_label(folder_index, False)
                self.pressed_number_keys.remove(key)
                if not self.image_processing:
                    self.image_processing = True
                    if self.grid_mode != "Off":
                        self.move_grid_image(folder_index)
                    else:
                        self.move_current_image_to_folder(folder_index)
                    self.image_processing = False
                return True
            key_to_remove_from_viewport = None
            if key == Qt.Key_Shift:
                if self.pressed_keys_for_viewport: self.pressed_keys_for_viewport.clear()
            elif key == Qt.Key_Left: key_to_remove_from_viewport = Qt.Key_Left
            elif key == Qt.Key_Right: key_to_remove_from_viewport = Qt.Key_Right
            elif key == Qt.Key_Up: key_to_remove_from_viewport = Qt.Key_Up
            elif key == Qt.Key_Down: key_to_remove_from_viewport = Qt.Key_Down
            elif key == Qt.Key_A: key_to_remove_from_viewport = Qt.Key_Left
            elif key == Qt.Key_D: key_to_remove_from_viewport = Qt.Key_Right
            elif key == Qt.Key_W: key_to_remove_from_viewport = Qt.Key_Up
            elif key == Qt.Key_S: key_to_remove_from_viewport = Qt.Key_Down
            action_taken = False
            if key_to_remove_from_viewport and key_to_remove_from_viewport in self.pressed_keys_for_viewport:
                self.pressed_keys_for_viewport.remove(key_to_remove_from_viewport)
                action_taken = True
            if not self.pressed_keys_for_viewport and self.viewport_move_timer.isActive():
                self.viewport_move_timer.stop()
                if self.grid_mode == "Off" and self.zoom_mode in ["100%", "Spin"] and self.original_pixmap:
                    final_rel_center = self._get_current_view_relative_center()
                    self.current_active_rel_center = final_rel_center
                    self.current_active_zoom_level = self.zoom_mode
                    self._save_orientation_viewport_focus(self.current_image_orientation, final_rel_center, self.zoom_mode)
            if action_taken or key == Qt.Key_Shift:
                return True
            return False
        return super().eventFilter(obj, event)

    def on_file_list_dialog_closed(self, result):
        """FileListDialog가 닫혔을 때 호출되는 슬롯"""
        # finished 시그널은 인자(result)를 받으므로 맞춰줌
        self.file_list_dialog = None # 다이얼로그 참조 제거
        print("File list dialog closed.") # 확인용 로그

    def update_raw_toggle_state(self):
        """RAW 폴더 유효성 및 RAW 전용 모드에 따라 'RAW 이동' 체크박스 상태 업데이트"""
        self.raw_toggle_button.blockSignals(True)
        try:
            if self.is_raw_only_mode:
                # RAW 전용 모드일 때는 항상 체크되고 비활성화되어야 함
                self.raw_toggle_button.setChecked(True)
                self.raw_toggle_button.setEnabled(False)
                self.move_raw_files = True # 내부 상태도 강제로 동기화
            else:
                # JPG 모드일 때
                is_raw_folder_valid = bool(self.raw_folder and Path(self.raw_folder).is_dir())
                self.raw_toggle_button.setEnabled(is_raw_folder_valid)
                if is_raw_folder_valid:
                    # 유효한 RAW 폴더가 연결되면, 저장된 내부 상태를 UI에 반영
                    self.raw_toggle_button.setChecked(self.move_raw_files)
                else:
                    # 유효한 RAW 폴더가 없으면 체크박스는 비활성화되고 체크 해제됨
                    # 이때 내부 상태(self.move_raw_files)는 변경하지 않아야 함
                    self.raw_toggle_button.setChecked(False)
        finally:
            # try...finally 구문을 사용하여 어떤 경우에도 시그널 차단이 해제되도록 보장
            self.raw_toggle_button.blockSignals(False)

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

    def update_info_folder_label_style(self, label: InfoFolderPathLabel, folder_path: str):
        """InfoFolderPathLabel의 스타일을 경로 유효성에 따라 업데이트합니다."""
        is_valid = bool(folder_path and Path(folder_path).is_dir())
        label.set_style(is_valid=is_valid)


    def update_jpg_folder_ui_state(self):
        is_valid = bool(self.current_folder and Path(self.current_folder).is_dir())
        self.update_info_folder_label_style(self.folder_path_label, self.current_folder) # <<< 수정
        if hasattr(self, 'jpg_clear_button'):
            self.jpg_clear_button.setEnabled(is_valid)
        if hasattr(self, 'load_button'):
            self.load_button.setEnabled(not is_valid and not self.is_raw_only_mode)
            
    def update_raw_folder_ui_state(self):
        is_valid = bool(self.raw_folder and Path(self.raw_folder).is_dir())
        self.update_info_folder_label_style(self.raw_folder_path_label, self.raw_folder) # <<< 수정
        if hasattr(self, 'raw_clear_button'):
            self.raw_clear_button.setEnabled(is_valid)
        self.update_raw_toggle_state()

    def clear_jpg_folder(self):
        """JPG 폴더 지정 해제 및 관련 상태 초기화"""
        self._reset_workspace()
        
        # clear_jpg_folder는 모든 것을 초기화하므로 target_folders도 초기화
        self.target_folders = [""] * self.folder_count

        self.grid_off_radio.setChecked(True) # 라디오 버튼 상태 동기화
        self._update_view_for_grid_change()

        self.update_all_folder_labels_state()

        # UI 컨트롤 상태 복원
        self.load_button.setEnabled(True)
        self.update_match_raw_button_state()

        if self.session_management_popup and self.session_management_popup.isVisible():
            self.session_management_popup.update_all_button_states()
        
        self.save_state()
        logging.info("JPG 폴더 지정 해제 및 작업 공간 초기화 완료.")

    def clear_raw_folder(self):
        """RAW 폴더 지정 해제 및 관련 상태 초기화 (RAW 전용 모드 처리 추가)"""
        if self.is_raw_only_mode:
            # --- RAW 전용 모드 해제 및 전체 초기화 ---
            logging.info("RAW 전용 모드 해제 및 초기화...")
            self._reset_workspace()

            self.grid_off_radio.setChecked(True)
            self._update_view_for_grid_change()
            
            # RAW 전용 모드 해제 후 추가 UI 상태 조정
            self.load_button.setEnabled(True)
            self.update_match_raw_button_state()
            
            if self.session_management_popup and self.session_management_popup.isVisible():
                self.session_management_popup.update_all_button_states()
        else:
            # --- 기존 로직: JPG 모드에서 RAW 연결만 해제 ---
            self.raw_folder = ""
            self.raw_files = {}
            # UI 업데이트
            self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
            self.update_raw_folder_ui_state() # 레이블 스타일, X 버튼, 토글 상태 업데이트
            self.update_match_raw_button_state() # RAW 버튼 상태 업데이트 ("JPG - RAW 연결"로)

            current_displaying_image_path = self.get_current_image_path()
            if current_displaying_image_path:
                logging.debug(f"clear_raw_folder (else): RAW 연결 해제 후 파일 정보 업데이트 시도 - {current_displaying_image_path}")
                self.update_file_info_display(current_displaying_image_path)
            else:
                # 현재 표시 중인 이미지가 없는 경우 (예: JPG 폴더도 비어있거나 로드 전)
                # 파일 정보 UI를 기본값으로 설정
                self.update_file_info_display(None)

            self.update_all_folder_labels_state()

            if self.session_management_popup and self.session_management_popup.isVisible():
                self.session_management_popup.update_all_button_states()

            self.save_state() # <<< 상태 변경 후 저장
            logging.info("RAW 폴더 지정 해제 완료.")


    def on_language_radio_changed(self, button):
        """언어 라디오 버튼 변경 시 호출되는 함수"""
        if button == self.english_radio:
            LanguageManager.set_language("en")
        elif button == self.korean_radio:
            LanguageManager.set_language("ko")

        if hasattr(self, 'settings_popup') and self.settings_popup and self.settings_popup.isVisible():
            self.update_settings_labels_texts(self.settings_popup)

    def on_date_format_changed(self, index):
        """날짜 형식 변경 시 호출되는 함수"""
        if index < 0:
            return
        format_code = self.date_format_combo.itemData(index)
        DateFormatManager.set_date_format(format_code)

    def update_ui_texts(self):
        """UI의 모든 텍스트를 현재 언어로 업데이트"""
        # --- 메인 윈도우 UI 텍스트 업데이트 ---
        self.load_button.setText(LanguageManager.translate("이미지 불러오기"))
        self.update_match_raw_button_state()
        self.raw_toggle_button.setText(LanguageManager.translate("JPG + RAW 이동"))
        self.minimap_toggle.setText(LanguageManager.translate("미니맵"))
        if hasattr(self, 'image_label_B') and not self.image_B_path:
            self.image_label_B.setText(LanguageManager.translate("비교할 이미지를 썸네일 패널에서 이곳으로 드래그하세요."))
        if hasattr(self, 'filename_toggle_grid'):
            self.filename_toggle_grid.setText(LanguageManager.translate("파일명"))
        if not self.current_folder:
            self.folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        if not self.raw_folder:
            self.raw_folder_path_label.setText(LanguageManager.translate("폴더 경로"))
        self.update_all_folder_labels_state()
        self.update_window_title_with_selection()
        
        if hasattr(self, 'settings_popup') and self.settings_popup:
            self.settings_popup.setWindowTitle(LanguageManager.translate("설정 및 정보"))

        # --- 설정 창 관련 모든 컨트롤의 텍스트 업데이트 ---
        self.update_all_settings_controls_text()
        # --- 현재 파일 정보 다시 표시 (날짜 형식 등이 바뀌었을 수 있으므로) ---
        self.update_file_info_display(self.get_current_image_path())

    def update_settings_labels_texts(self, parent_widget):
        """설정 UI의 모든 텍스트를 현재 언어로 업데이트합니다."""
        if not parent_widget:
            return

        # --- 그룹 제목 업데이트 ---
        group_title_keys = {
            "group_title_UI_설정": "UI 설정",
            "group_title_작업_설정": "작업 설정",
            "group_title_도구_및_고급_설정": "도구 및 고급 설정"
        }
        for name, key in group_title_keys.items():
            label = parent_widget.findChild(QLabel, name)
            if label:
                label.setText(LanguageManager.translate(key))

        # --- 개별 설정 항목 라벨 업데이트 ---
        # 사용되지 않는 키를 제거하고 '성능 프로필' 키를 추가했습니다.
        setting_row_keys = {
            "언어_label": "언어",
            "테마_label": "테마",
            "컨트롤_패널_label": "컨트롤 패널",
            "날짜_형식_label": "날짜 형식",
            "불러올_이미지_형식_label": "불러올 이미지 형식",
            "분류_폴더_개수_label": "분류 폴더 개수",
            "뷰포트_이동_속도_label": "뷰포트 이동 속도",
            "마우스_휠_동작_label": "마우스 휠 동작",
            "성능_설정_ⓘ_label": "성능 설정 ⓘ",
        }
        for object_name, translation_key in setting_row_keys.items():
            label = parent_widget.findChild(QLabel, object_name)
            if label:
                label.setText(LanguageManager.translate(translation_key))
                if translation_key == "성능 설정 ⓘ":
                    tooltip_key = "시스템 사양에 맞춰 자동으로 설정된 프로필입니다.\n높은 단계일수록 더 많은 메모리와 CPU를 사용하여 작업 속도를 높입니다.\n앱이 시스템을 느리게 하거나 메모리를 너무 많이 차지하는 경우 낮은 단계로 변경해주세요."
                    tooltip_text = LanguageManager.translate(tooltip_key)
                    label.setToolTip(tooltip_text)

        # --- 라디오 버튼 텍스트 업데이트 (이전과 동일) ---
        if hasattr(self, 'panel_pos_left_radio'):
            self.panel_pos_left_radio.setText(LanguageManager.translate("좌측"))
        if hasattr(self, 'panel_pos_right_radio'):
            self.panel_pos_right_radio.setText(LanguageManager.translate("우측"))
        if hasattr(self, 'mouse_wheel_photo_radio'):
            self.mouse_wheel_photo_radio.setText(LanguageManager.translate("사진 넘기기"))
        if hasattr(self, 'mouse_wheel_none_radio'):
            self.mouse_wheel_none_radio.setText(LanguageManager.translate("없음"))

        # --- 버튼 텍스트 업데이트 (이전과 동일) ---
        if hasattr(self, 'reset_camera_settings_button'):
            self.reset_camera_settings_button.setText(LanguageManager.translate("RAW 처리 방식 초기화"))
        if hasattr(self, 'session_management_button'):
            self.session_management_button.setText(LanguageManager.translate("세션 관리"))
        if hasattr(self, 'reset_app_settings_button'):
            self.reset_app_settings_button.setText(LanguageManager.translate("프로그램 설정 초기화"))
        if hasattr(self, 'shortcuts_button'):
            self.shortcuts_button.setText(LanguageManager.translate("단축키 확인"))

        # --- 정보 및 후원 섹션 텍스트 업데이트 (이전과 동일) ---
        info_label = parent_widget.findChild(QLabel, "photosort_info_label")
        if info_label:
            info_label.setText(self.create_translated_info_text())
        for qr_label in parent_widget.findChildren(QRLinkLabel):
            if qr_label.url == "":
                if "KakaoPay" in qr_label.text() or "카카오페이" in qr_label.text():
                    qr_label.setText(LanguageManager.translate("카카오페이") if LanguageManager.get_current_language() == "ko" else "KakaoPay 🇰🇷")
                elif "NaverPay" in qr_label.text() or "네이버페이" in qr_label.text():
                    qr_label.setText(LanguageManager.translate("네이버페이") if LanguageManager.get_current_language() == "ko" else "NaverPay 🇰🇷")

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

        if not hasattr(self, 'splitter') or not self.splitter:
            logging.warning("Warning: Splitter가 아직 준비되지 않았습니다.")
            return
        if not hasattr(self, 'control_panel') or not hasattr(self, 'image_panel'):
            logging.warning("Warning: 컨트롤 또는 이미지 패널이 아직 준비되지 않았습니다.")
            return

        try:
            # 현재 썸네일 패널 표시 상태 확인
            thumbnail_visible = (self.grid_mode == "Off")
            
            # 스플리터 재구성
            self._reorganize_splitter_widgets(thumbnail_visible, self.control_panel_on_right)
            
            # 레이아웃 크기 재조정
            print("  -> adjust_layout 호출")
            self.adjust_layout()

            print("_apply_panel_position 완료")

        except Exception as e:
            logging.error(f"_apply_panel_position 오류: {e}")
            print(f"ERROR in _apply_panel_position: {e}")

def main():
    # PyInstaller로 패키징된 실행 파일을 위한 멀티프로세싱 지원 추가
    freeze_support()  # 이 호출이 멀티프로세싱 무한 재귀 문제를 해결합니다

    # <<<--- HEIC 플러그인 등록 코드를 여기로 이동 ---<<<
    try:
        pillow_heif.register_heif_opener()
        logging.info("HEIF/HEIC 지원이 활성화되었습니다. (main에서 등록)")
    except Exception as e:
        logging.error(f"HEIF/HEIC 플러그인 등록 실패: {e}")
    # <<<--------------------------------------------<<<

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
        "이미지 불러오기": "Load Images",
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
        "이미지 파일이 있는 폴더 선택": "Select Image Folder",
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
        "닫기": "Close",
        "단축키 확인": "View Shortcuts",
        "개인적인 용도로 자유롭게 사용할 수 있는 무료 소프트웨어입니다.": "This is free software that you can use freely for personal purposes.",
        "상업적 이용은 허용되지 않습니다.": "Commercial use is not permitted.",
        "이 프로그램이 마음에 드신다면, 커피 한 잔으로 응원해 주세요.": "If you truly enjoy this app, consider supporting it with a cup of coffee!",
        "QR 코드": "QR Code",
        "후원 QR 코드": "Donation QR Code",
        "네이버페이": "NaverPay",
        "카카오페이": "KakaoPay",
        "피드백 및 업데이트 확인:": "Feedback & Updates:",
        "이미지 로드 중...": "Loading image...",
        "파일명": "Filename",
        "저장된 모든 카메라 모델의 RAW 파일 처리 방식을 초기화하시겠습니까? 이 작업은 되돌릴 수 없습니다.": "Are you sure you want to reset the RAW file processing method for all saved camera models? This action cannot be undone.",
        "모든 카메라의 RAW 처리 방식 설정이 초기화되었습니다.": "RAW processing settings for all cameras have been reset.",
        "알 수 없는 카메라": "Unknown Camera",
        "정보 없음": "N/A",
        "RAW 파일 처리 방식 선택": "Select RAW Processing Method",
        "{camera_model_placeholder}의 RAW 처리 방식에 대해 다시 묻지 않습니다.": "Don't ask again for {camera_model_placeholder} RAW processing method.",
        "{model_name_placeholder}의 원본 이미지 해상도는 <b>{orig_res_placeholder}</b>입니다.<br>{model_name_placeholder}의 RAW 파일에 포함된 미리보기(프리뷰) 이미지의 해상도는 <b>{prev_res_placeholder}</b>입니다.<br>미리보기를 통해 이미지를 보시겠습니까, RAW 파일을 디코딩해서 보시겠습니까?":
            "The original image resolution for {model_name_placeholder} is <b>{orig_res_placeholder}</b>.<br>"
            "The embedded preview image resolution in the RAW file for {model_name_placeholder} is <b>{prev_res_placeholder}</b>.<br>"
            "Would you like to view images using the preview or by decoding the RAW file?",
        "미리보기 이미지 사용 (미리보기의 해상도가 충분하거나 빠른 작업 속도가 중요한 경우.)": "Use Preview Image (if preview resolution is sufficient for you or speed is important.)",
        "RAW 디코딩 (느림. 일부 카메라 호환성 문제 있음.\n미리보기의 해상도가 너무 작거나 원본 해상도가 반드시 필요한 경우에만 사용 권장.)": 
            "Decode RAW File (Slower. Compatibility issues with some cameras.\nRecommended only if preview resolution is too low or original resolution is essential.)",
        "호환성 문제로 {model_name_placeholder}의 RAW 파일을 디코딩 할 수 없습니다.<br>RAW 파일에 포함된 <b>{prev_res_placeholder}</b>의 미리보기 이미지를 사용하겠습니다.<br>({model_name_placeholder}의 원본 이미지 해상도는 <b>{orig_res_placeholder}</b>입니다.)":
            "Due to compatibility issues, RAW files from {model_name_placeholder} cannot be decoded.<br>"
            "The embedded preview image with resolution <b>{prev_res_placeholder}</b> will be used.<br>"
            "(Note: The original image resolution for {model_name_placeholder} is <b>{orig_res_placeholder}</b>.)",
        "RAW 처리 방식 초기화": "Reset RAW Processing Methods",
        "초기화": "Reset",
        "썸네일": "Thumbnails",
        "저장된 모든 카메라 모델의 RAW 파일 처리 방식을 초기화하시겠습니까? 이 작업은 되돌릴 수 없습니다.": "Are you sure you want to reset the RAW file processing method for all saved camera models? This action cannot be undone.",
        "초기화 완료": "Reset Complete",
        "모든 카메라의 RAW 처리 방식 설정이 초기화되었습니다.": "RAW processing settings for all cameras have been reset.",
        "로드된 파일과 현재 작업 상태를 초기화하시겠습니까?": "Are you sure you want to reset loaded files and the current working state?",
        "뷰포트 이동 속도": "Viewport Move Speed",
        "세션 저장 및 불러오기 🖜": "Save/Load Session 🖜", # 텍스트 링크용 (🖜 아이콘은 시스템/폰트 따라 다를 수 있음)
        "세션 관리": "Session Management", # 팝업창 제목
        "현재 세션 저장": "Save Current Session",
        "세션 이름": "Session Name",
        "저장할 세션 이름을 입력하세요:": "Enter a name for this session:",
        "선택 세션 불러오기": "Load Selected Session",
        "선택 세션 삭제": "Delete Selected Session",
        "저장된 세션 목록 (최대 20개):": "Saved Sessions (Max 20):",
        "저장 오류": "Save Error",
        "세션 이름을 입력해야 합니다.": "Session name cannot be empty.",
        "저장 한도 초과": "Save Limit Exceeded",
        "최대 20개의 세션만 저장할 수 있습니다. 기존 세션을 삭제 후 다시 시도해주세요.": "You can only save up to 20 sessions. Please delete an existing session and try again.",
        "불러오기 오류": "Load Error",
        "선택한 세션을 찾을 수 없습니다.": "The selected session could not be found.",
        "삭제 확인": "Confirm Deletion",
        "'{session_name}' 세션을 정말 삭제하시겠습니까?": "Are you sure you want to delete the session '{session_name}'?",
        "불러오기 완료": "Load Complete", # 이미 있을 수 있음
        "'{session_name}' 세션을 불러왔습니다.": "Session '{session_name}' has been loaded.",
        "불러올 이미지 형식": "Loadable Image Formats",
        "최소 하나 이상의 확장자는 선택되어야 합니다.": "At least one extension must be selected.",
        "선택한 폴더에 지원하는 이미지 파일이 없습니다.": "No supported image files found in the selected folder.",
        "폴더 불러오기": "Load Folder",
        "폴더 내에 일반 이미지 파일과 RAW 파일이 같이 있습니다.\n무엇을 불러오시겠습니까?": "The folder contains both regular image files and RAW files.\nWhat would you like to load?",
        "파일명이 같은 이미지 파일과 RAW 파일을 매칭하여 불러오기": "Match and load image files and RAW files with the same file names",
        "일반 이미지 파일만 불러오기": "Load only regular image files",
        "RAW 파일만 불러오기": "Load only RAW files",
        "선택한 폴더에 지원하는 파일이 없습니다.": "No supported files found in the selected folder.",
        "분류 폴더 개수": "Number of Sorting Folders",
        "마우스 휠 동작": "Mouse Wheel Action",
        "사진 넘기기": "Photo Navigation", 
        "없음": "None",
        "이동 - 폴더 {0}": "Move to Folder {0}",
        "이동 - 폴더 {0} [{1}]": "Move to Folder {0} [{1}]",
        "UI 설정": "UI Settings",
        "작업 설정": "Workflow Settings",
        "도구 및 고급 설정": "Tools & Advanced",
        "새 폴더명을 입력하고 Enter를 누르거나 ✓ 버튼을 클릭하세요.": "Enter a new folder name and press Enter or click the ✓ button.",
        "기준 폴더가 로드되지 않았습니다.": "Base folder has not been loaded.",
        "폴더 생성 실패": "Folder Creation Failed",
        "이미지 이동 중...": "Moving images...",
        "작업 취소됨.\n성공: {success_count}개, 실패: {fail_count}개": "Operation canceled.\nSuccess: {success_count}, Failed: {fail_count}",
        "성공: {success_count}개\n실패: {fail_count}개": "Success: {success_count}\nFailed: {fail_count}",
        "모든 파일 이동 실패: {fail_count}개": "All file moves failed: {fail_count}",
        "파일 열기 실패": "Failed to Open File",
        "연결된 프로그램이 없거나 파일을 열 수 없습니다.": "No associated program or the file cannot be opened.",
        "파일 준비 중": "Preparing Files",
        "쾌적한 작업을 위해 RAW 파일을 준비하고 있습니다.": "Preparing RAW files for a smooth workflow.",
        "잠시만 기다려주세요.": "Please wait a moment.",
        # 단축키 번역 키 시작
        "탐색": "Navigation",
        "WASD / 방향키": "WASD / Arrow Keys",
        "사진 넘기기": "Navigate photos",
        "Shift + WASD/방향키": "Shift + WASD/Arrow Keys",
        "뷰포트 이동 (확대 중에)": "Pan viewport (while zoomed)",
        "Shift + A/D": "Shift + A/D",
        "이전/다음 페이지 (그리드 모드)": "Previous/Next page (in Grid mode)",
        "Enter": "Enter",
        "사진 목록 보기": "Show photo list",
        "F5": "F5",
        "폴더 새로고침": "Refresh folder",
        "보기 설정": "View Settings",
        "G": "G",
        "그리드 모드 켜기/끄기": "Toggle Grid mode",
        "C": "C",
        "A | B 비교 모드 켜기/끄기": "Toggle A | B Compare mode",
        "Space": "Space",
        "줌 전환 (Fit/100%) 또는 그리드에서 확대": "Toggle Zoom (Fit/100%) or Zoom in from Grid",
        "F1 / F2 / F3": "F1 / F2 / F3",
        "줌 모드 변경 (Fit / 100% / 가변)": "Change Zoom mode (Fit / 100% / Variable)",
        "Z / X": "Z / X",
        "줌 아웃 (가변 모드)": "Zoom Out (in Variable mode)",
        "줌 인 (가변 모드)": "Zoom In (in Variable mode)",
        "R": "R",
        "뷰포트 중앙 정렬": "Center viewport",
        "ESC": "ESC",
        "줌 아웃 또는 그리드 복귀": "Zoom out or return to Grid",
        "파일 작업": "File Actions",
        "1 ~ 9": "1 ~ 9",
        "지정한 폴더로 사진 이동": "Move photo to assigned folder",
        "Ctrl + Z": "Ctrl + Z",
        "파일 이동 취소 (Undo)": "Undo file move",
        "Ctrl + Y / Ctrl + Shift + Z": "Ctrl + Y / Ctrl + Shift + Z",
        "파일 이동 다시 실행 (Redo)": "Redo file move",
        "Ctrl + A": "Ctrl + A",
        "페이지 전체 선택 (그리드 모드)": "Select all on page (in Grid mode)",
        "Delete": "Delete",
        "작업 상태 초기화": "Reset working state",
        "G(Grid)": "G(Grid)",
        "C(Compare)": "C(Compare)",
        "Z(Zoom Out) / X(eXpand)": "Z(Zoom Out) / X(eXpand)",
        "R(Reset)": "R(Reset)",
        # 단축키 번역 키 끝
        # EditableFolderPathLabel 및 InfoFolderPathLabel 관련 번역 키
        "새 폴더명을 입력하거나 폴더를 드래그하여 지정하세요.": "Enter a new folder name or drag a folder here.",
        "폴더를 드래그하여 지정하세요.": "Drag a folder here to assign.",
        "더블클릭하면 해당 폴더가 열립니다.": "Double-click to open the folder.",
        "더블클릭하면 해당 폴더가 열립니다 (전체 경로 표시)": "Double-click to open the folder (shows full path).",
        # EditableFolderPathLabel 및 InfoFolderPathLabel 관련 번역 키 끝
        # 누락된 번역키 추가
        "잘못된 폴더명입니다.": "Invalid folder name.",
        "유효하지 않은 폴더입니다.": "Invalid folder.",
        "알림": "Notice",
        "Zoom Fit 모드에서만 드래그 앤 드롭이 가능합니다.": "Drag and drop is only available in Zoom Fit mode.",
        "이동할 이미지가 없습니다.": "No image to move.",
        "선택된 그리드 이미지가 없습니다.": "No grid image selected.",
        "호환성 문제": "Compatibility Issue",
        "RAW 디코딩 실패. 미리보기를 대신 사용합니다.": "RAW decoding failed. Using preview instead.",
        "비교할 이미지를 썸네일 패널에서 이곳으로 드래그하세요.": "Drag an image from the thumbnail panel here to compare.",
        "새 폴더 불러오기": "Load New Folder",
        "현재 진행 중인 작업을 종료하고 새로운 폴더를 불러오시겠습니까?": "Do you want to end the current session and load a new folder?",
        "예": "Yes",
        "취소": "Cancel",
        # 성능 프로필 관련 번역키
        "성능 설정 ⓘ": "Performance Setting ⓘ",
        "저사양 (8GB RAM)": "Low Spec (8GB RAM)",
        "표준 (16GB RAM)": "Standard (16GB RAM, Default)",
        "상급 (24GB RAM)": "Upper-Mid (24GB RAM)",
        "고성능 (32GB RAM)": "Performance (32GB RAM)",
        "초고성능 (64GB RAM)": "Ultra Performance (64GB RAM)",
        "워크스테이션 (96GB+ RAM)": "Workstation (96GB+ RAM)",
        "설정 변경": "Settings Changed",
        "성능 프로필이 '{profile_name}'(으)로 변경되었습니다.": "Performance profile has been changed to '{profile_name}'.",
        "이 설정은 앱을 재시작해야 완전히 적용됩니다.": "This setting will be fully applied after restarting the app.",
        "시스템 사양에 맞춰 자동으로 설정된 프로필입니다.\n높은 단계일수록 더 많은 메모리와 CPU를 사용하여 작업 속도를 높입니다.\n앱이 시스템을 느리게 하거나 메모리를 너무 많이 차지하는 경우 낮은 단계로 변경해주세요.":
        "This profile is automatically set based on your system specifications.\nHigher levels use more memory and CPU to increase processing speed.\nIf the app slows down your system or consumes too much memory, please change to a lower setting.",
        # 프로그램 초기화 관련 번역
        "프로그램 설정 초기화": "Reset App Settings",
        "초기화 확인": "Confirm Reset",
        "모든 설정을 초기화하고 프로그램을 재시작하시겠습니까?\n이 작업은 되돌릴 수 없습니다.": "Are you sure you want to reset all settings and restart the application?\nThis action cannot be undone.",
        "재시작 중...": "Restarting...",
        "설정이 초기화되었습니다. 프로그램을 재시작합니다.": "Settings have been reset. The application will now restart.",
        "폴더를 읽는 중입니다...": "Reading folder...",
        "이미지 파일 스캔 중...": "Scanning image files...",
        "파일 정렬 중...": "Sorting files...",
        "RAW 파일 매칭 중...": "Matching RAW files...",
        "RAW 파일 정렬 중...": "Sorting RAW files...",
    }
    
    LanguageManager.initialize_translations(translations)

    # 하나만 실행되도록 단일 인스턴스 체크 (모든 플랫폼에서 동작)
    shared_memory = QSharedMemory("PhotoSortApp_SingleInstance")
    if not shared_memory.create(1):
        print("PhotoSort가 이미 실행 중입니다.")
        sys.exit(1)

    app = QApplication(sys.argv)

    UIScaleManager.initialize() # UI 스케일 모드 결정
    application_font = QFont("Arial", UIScaleManager.get("font_size", 10)) # 결정된 폰트 크기 가져오기 (기본값 10)
    app.setFont(application_font) # 애플리케이션 기본 폰트 설정

    window = PhotoSortApp()

    # load_state()의 결과를 확인하여 앱 실행 여부 결정
    if not window.load_state(): # load_state가 False를 반환하면 (첫 실행 설정 취소 등)
        logging.info("main: load_state가 False를 반환하여 애플리케이션을 시작하지 않습니다.")
        sys.exit(0) # 또는 return, 어쨌든 app.exec()를 호출하지 않음

    window.show()

    # 첫 실행이면 메인 윈도우 표시 후 설정 팝업 표시
    if hasattr(window, 'is_first_run') and window.is_first_run:
        QTimer.singleShot(100, window.show_first_run_settings_popup_delayed)

    shared_memory.detach()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

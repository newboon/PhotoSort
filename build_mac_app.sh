#!/usr/bin/env bash
set -e

# Initialize Conda for bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate photosort_env
PYTHON_BIN="$(which python)"

# PySide6 Qt 플러그인 경로를 QLibraryInfo로 조회
PY_SIDE_DIR=$($PYTHON_BIN - << 'EOF'
from PySide6.QtCore import QLibraryInfo
print(QLibraryInfo.path(QLibraryInfo.PluginsPath))
EOF
)
echo "PySide6 Qt 플러그인 경로: ${PY_SIDE_DIR}"


# ExifTool, libraw 설정은 그대로
EXIFTOOL_BIN="/opt/homebrew/bin/exiftool"
LIBRAW_DYLIB="/opt/homebrew/lib/libraw.dylib"

pyinstaller \
  --name PhotoSort \
  --windowed \
  --clean \
  --add-data "app_icon.icns:." \
  --add-data "${PY_SIDE_DIR}/platforms:Qt/plugins/platforms" \
  --add-data "${PY_SIDE_DIR}/styles:Qt/plugins/styles" \
  --add-data "${PY_SIDE_DIR}/imageformats:Qt/plugins/imageformats" \
  --add-binary "${EXIFTOOL_BIN}:." \
  --add-binary "${LIBRAW_DYLIB}:." \
  --icon app_icon.icns \
  --add-data "resources:resources" \
  --version-file version.plist \
  PhotoSort.py
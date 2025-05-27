#!/usr/bin/env bash
set -e

# 색상 출력을 위한 설정
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수들
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 버전 정보
VERSION="25.05.27"
APP_NAME="PhotoSort"
BUNDLE_ID="com.newboon.photosort"

log_info "PhotoSort v${VERSION} 빌드 시작..."

# 환경 확인
log_info "빌드 환경 확인 중..."

# Conda 환경 활성화
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate photosort_env
PYTHON_BIN="$(which python)"

log_info "Python 경로: ${PYTHON_BIN}"
log_info "Python 버전: $(${PYTHON_BIN} --version)"

# 필수 파일 존재 확인
required_files=("PhotoSort.py" "app_icon.icns" "resources")
for file in "${required_files[@]}"; do
    if [[ ! -e "$file" ]]; then
        log_error "필수 파일이 없습니다: $file"
        exit 1
    fi
done

# PySide6 Qt 플러그인 경로 조회
log_info "PySide6 Qt 플러그인 경로 조회 중..."
PY_SIDE_DIR=$($PYTHON_BIN - << 'EOF'
from PySide6.QtCore import QLibraryInfo
print(QLibraryInfo.path(QLibraryInfo.PluginsPath))
EOF
)
log_info "PySide6 Qt 플러그인 경로: ${PY_SIDE_DIR}"

# ExifTool, libraw 경로 확인
EXIFTOOL_BIN="/opt/homebrew/bin/exiftool"
LIBRAW_DYLIB="/opt/homebrew/lib/libraw.dylib"

if [[ ! -f "$EXIFTOOL_BIN" ]]; then
    log_warning "ExifTool을 찾을 수 없습니다: $EXIFTOOL_BIN"
    log_info "다른 경로에서 찾는 중..."
    EXIFTOOL_BIN=$(which exiftool 2>/dev/null || echo "")
    if [[ -z "$EXIFTOOL_BIN" ]]; then
        log_error "ExifTool을 찾을 수 없습니다. 'brew install exiftool'로 설치하세요."
        exit 1
    fi
fi

if [[ ! -f "$LIBRAW_DYLIB" ]]; then
    log_warning "libraw를 찾을 수 없습니다: $LIBRAW_DYLIB"
    # 다른 경로들 시도
    for path in "/usr/local/lib/libraw.dylib" "/opt/local/lib/libraw.dylib"; do
        if [[ -f "$path" ]]; then
            LIBRAW_DYLIB="$path"
            break
        fi
    done
fi

log_info "ExifTool 경로: ${EXIFTOOL_BIN}"
log_info "LibRaw 경로: ${LIBRAW_DYLIB}"

# 이전 빌드 정리
if [[ -d "dist" ]]; then
    log_info "이전 빌드 파일 정리 중..."
    rm -rf dist build
fi

# 버전 파일 생성 (plist 대신 간단한 버전 파일)
cat > version_info.py << EOF
version_info = {
    'version': '${VERSION}',
    'app_name': '${APP_NAME}',
    'bundle_id': '${BUNDLE_ID}'
}
EOF

# PyInstaller 실행
log_info "PyInstaller를 사용하여 PhotoSort 앱 빌드 중..."

pyinstaller \
  --name "${APP_NAME}" \
  --windowed \
  --clean \
  --onedir \
  --noconfirm \
  --icon app_icon.icns \
  --add-data "app_icon.icns:." \
  --add-data "resources:resources" \
  --add-data "version_info.py:." \
  --add-data "${PY_SIDE_DIR}/platforms:Qt/plugins/platforms" \
  --add-data "${PY_SIDE_DIR}/styles:Qt/plugins/styles" \
  --add-data "${PY_SIDE_DIR}/imageformats:Qt/plugins/imageformats" \
  --add-binary "${EXIFTOOL_BIN}:." \
  --add-binary "${LIBRAW_DYLIB}:." \
  --collect-all PySide6 \
  --collect-all PIL \
  --collect-all pillow \
  --hidden-import=PIL \
  --hidden-import=PIL.Image \
  --hidden-import=PIL.ExifTags \
  --hidden-import=exifread \
  --hidden-import=rawpy \
  --exclude-module tkinter \
  --exclude-module matplotlib \
  --exclude-module numpy.testing \
  --exclude-module test \
  --exclude-module unittest \
  PhotoSort.py

if [[ $? -ne 0 ]]; then
    log_error "PyInstaller 빌드 실패"
    exit 1
fi

log_success "PyInstaller 빌드 완료"

# 앱 번들 경로
APP_BUNDLE="dist/${APP_NAME}.app"

# 빌드 결과 확인
if [[ ! -d "$APP_BUNDLE" ]]; then
    log_error "앱 번들을 찾을 수 없습니다: $APP_BUNDLE"
    exit 1
fi

# 코드 서명 (개발용)
log_info "코드 서명 중..."
codesign --force --deep --sign - "$APP_BUNDLE" 2>/dev/null || {
    log_warning "코드 서명 실패 (계속 진행)"
}

# 격리 속성 제거
log_info "격리 속성 제거 중..."
xattr -rd com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || {
    log_info "격리 속성이 없습니다 (정상)"
}

# 실행 권한 확인
log_info "실행 권한 확인 중..."
chmod +x "$APP_BUNDLE/Contents/MacOS/${APP_NAME}"

# 앱 정보 출력
APP_SIZE=$(du -sh "$APP_BUNDLE" | cut -f1)
log_info "앱 크기: $APP_SIZE"

# 배포용 파일 생성
log_info "배포용 파일 생성 중..."

# 배포 디렉토리 생성
DIST_DIR="PhotoSort_v${VERSION}_macOS"
mkdir -p "$DIST_DIR"

# 앱 복사
cp -R "$APP_BUNDLE" "$DIST_DIR/"

# 설치 안내 파일 생성
cat > "$DIST_DIR/설치_안내.txt" << EOF
PhotoSort v${VERSION} 설치 안내
================================

1. PhotoSort.app을 Applications 폴더로 드래그하여 설치하세요.

2. 처음 실행 시 보안 경고가 나타나면:
   - 시스템 설정 > 개인정보 보호 및 보안 > 보안
   - "확인되지 않은 개발자의 앱 허용" 섹션에서 PhotoSort 허용

3. 그래도 실행되지 않으면 터미널에서 다음 명령어를 실행하세요:
   xattr -rd com.apple.quarantine /Applications/PhotoSort.app

문의사항이 있으시면 개발자에게 연락해주세요.
EOF

# ZIP 파일 생성
log_info "ZIP 파일 생성 중..."
zip -r "${DIST_DIR}.zip" "$DIST_DIR" > /dev/null

# DMG 생성 (create-dmg가 설치된 경우)
if command -v create-dmg &> /dev/null; then
    log_info "DMG 파일 생성 중..."
    create-dmg \
        --volname "${APP_NAME} v${VERSION}" \
        --window-pos 200 120 \
        --window-size 800 400 \
        --icon-size 100 \
        --icon "${APP_NAME}.app" 200 190 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 600 185 \
        "${DIST_DIR}.dmg" \
        "$DIST_DIR" 2>/dev/null || {
        log_warning "DMG 생성 실패 (선택사항)"
    }
else
    log_info "create-dmg가 설치되지 않음 (DMG 생성 건너뜀)"
    log_info "설치하려면: brew install create-dmg"
fi

# 빌드 완료 정보
log_success "빌드 완료!"
echo ""
log_info "생성된 파일들:"
echo "  - $APP_BUNDLE"
echo "  - ${DIST_DIR}/"
echo "  - ${DIST_DIR}.zip"
if [[ -f "${DIST_DIR}.dmg" ]]; then
    echo "  - ${DIST_DIR}.dmg"
fi

echo ""
log_info "배포 방법:"
echo "  1. ${DIST_DIR}.zip을 사용자에게 전달"
echo "  2. 사용자는 압축 해제 후 PhotoSort.app을 Applications 폴더로 이동"
echo "  3. 설치_안내.txt 파일을 함께 제공"

echo ""
log_info "테스트를 위해 앱을 실행해보세요:"
echo "  open \"$APP_BUNDLE\""

# 정리
rm -f version_info.py

log_success "모든 작업 완료!"
#!/usr/bin/env bash
# open-science 오프라인 설치 (Linux/macOS, 인터넷·npm 불필요)
#   ./install_offline.sh /path/to/project [opencode|opencode-v1] [python3.11]
set -euo pipefail
B="$(cd "$(dirname "$0")" && pwd)"
PROJECT="${1:?프로젝트 경로}"; TARGET="${2:-opencode}"; PY="${3:-python3}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/open-science}"
TRACK=$([ "$TARGET" = "opencode" ] && echo opencode2 || echo opencode1)
echo "[1/5] 체크섬"; (cd "$B" && sha256sum -c --quiet SHA256SUMS.txt 2>/dev/null || shasum -a 256 -c SHA256SUMS.txt >/dev/null)
echo "[2/5] venv + wheel"; mkdir -p "$INSTALL_DIR"
[ -x "$INSTALL_DIR/venv/bin/python" ] || "$PY" -m venv "$INSTALL_DIR/venv" || "$PY" -m venv --without-pip "$INSTALL_DIR/venv"
VPY="$INSTALL_DIR/venv/bin/python"
if ! "$VPY" -m pip --version >/dev/null 2>&1; then  # ensurepip 없는 Python 대비
  PIPWHL=$(ls "$B"/wheels/pip-*.whl | head -n1); echo "  pip 부트스트랩: $PIPWHL"
  "$VPY" "$PIPWHL/pip" install --no-index --find-links "$B/wheels" pip
fi
"$VPY" -m pip install --no-index --find-links "$B/wheels" --upgrade sciharness
echo "[3/5] OpenCode ($TRACK)"; mkdir -p "$INSTALL_DIR/bin/$TRACK"; cp -f "$B/bin/$TRACK/"* "$INSTALL_DIR/bin/$TRACK/"; chmod +x "$INSTALL_DIR/bin/$TRACK/opencode"
echo "[4/5] 키트"; rm -rf "$INSTALL_DIR/kit"; cp -r "$B/kit" "$INSTALL_DIR/kit"; mkdir -p "$PROJECT"
[ -f "$B/models/models.json" ] && mkdir -p "$PROJECT/.science" && cp "$B/models/models.json" "$PROJECT/.science/models.json" || true
"$VPY" "$INSTALL_DIR/kit/tools/install.py" --target "$TARGET" --project "$PROJECT" --python "$VPY" --offline
# OpenCode 1.x: @opencode-ai/plugin 을 번들 사본으로 미리 배치(폐쇄망에서 npm 설치 지연/실패 방지)
DEPZ="$B/v1-deps/opencode-plugin-deps.zip"
if [ "$TARGET" = "opencode-v1" ] && [ -f "$DEPZ" ]; then
  for D in "$PROJECT/.opencode" "${XDG_CONFIG_HOME:-$HOME/.config}/opencode"; do
    if [ -d "$D/node_modules/@opencode-ai/plugin" ]; then echo "  V1 플러그인 의존성 이미 있음: $D"; continue; fi
    if [ -f "$D/package.json" ]; then echo "  경고: $D/package.json 이 있어 덮어쓰지 않음 — $DEPZ 를 수동 병합하세요"; continue; fi
    mkdir -p "$D" && "$VPY" -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$DEPZ" "$D" && echo "  V1 플러그인 의존성 배치: $D"
  done
fi
cat > "$PROJECT/.opencode/opencode-offline.sh" <<EOF
#!/usr/bin/env bash
export SCIHARNESS_PYTHON="$VPY" OPENCODE_DISABLE_AUTOUPDATE=1 OPENCODE_DISABLE_MODELS_FETCH=1 OPENCODE_DISABLE_LSP_DOWNLOAD=1
[ -f "$PROJECT/.science/models.json" ] && export OPENCODE_MODELS_PATH="$PROJECT/.science/models.json"
cd "$PROJECT" && exec "$INSTALL_DIR/bin/$TRACK/opencode" "\$@"
EOF
chmod +x "$PROJECT/.opencode/opencode-offline.sh"
echo "[5/5] 완료. 실행: $PROJECT/.opencode/opencode-offline.sh"

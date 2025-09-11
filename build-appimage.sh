#!/bin/bash

# --- Melhoria: Sair imediatamente se um comando falhar ---
set -e

# --- Configuração ---
APP="comm-tac-writer"
VERSION="1.1.0"
LOWER_APP_NAME=$(echo "$APP" | tr '[:upper:]' '[:lower:]')
ICON_PATH="usr/share/icons/hicolor/scalable/apps/tac-writer.svg"
DESKTOP_PATH="usr/share/applications/org.communitybig.tac.desktop"

# --- Melhoria: Detectar a versão do Python automaticamente ---
PYTHON_VERSION=$(python -c "import sys; print(f'python{sys.version_info.major}.{sys.version_info.minor}')")
echo ">>> Usando a versão do Python: $PYTHON_VERSION"

# Diretório de compilação
APPDIR="${APP}.AppDir"

echo "### Iniciando a criação do AppImage para $APP v$VERSION ###"

# --- Limpeza ---
echo ">>> Limpando compilações anteriores..."
rm -rf "$APPDIR"
rm -f "${APP}"*.AppImage

# --- Passo 1: Criar a estrutura do AppDir ---
echo ">>> Criando a estrutura de diretórios em $APPDIR..."
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib"

# --- Passo 2: Copiar os arquivos da aplicação ---
echo ">>> Copiando arquivos da aplicação..."
cp -r usr/* "$APPDIR/usr/"

# --- Passo 3: Instalar dependências Python com pip ---
echo ">>> Instalando dependências Python..."
PYTHON_DEPS=(
    "reportlab"
    "pyenchant"
)
PYTHON_SITE_PACKAGES="$APPDIR/usr/lib/$PYTHON_VERSION/site-packages"
mkdir -p "$PYTHON_SITE_PACKAGES"
pip install --target="$PYTHON_SITE_PACKAGES" "${PYTHON_DEPS[@]}"

# --- Passo 4: Criar o script de inicialização AppRun ---
echo ">>> Criando o script AppRun..."
cat > "$APPDIR/AppRun" <<EOF
#!/bin/bash
HERE=\$(dirname "\$(readlink -f "\${0}")")
export PATH="\${HERE}/usr/bin:\${PATH}"
export LD_LIBRARY_PATH="\${HERE}/usr/lib:\${LD_LIBRARY_PATH}"
export PYTHONPATH="\${HERE}/usr/lib/${PYTHON_VERSION}/site-packages:\${PYTHONPATH}"
export XDG_DATA_DIRS="\${HERE}/usr/share:\${XDG_DATA_DIRS}"
export GETTEXT_PATH="\${HERE}/usr/share/locale"
exec python "\${HERE}/usr/share/tac-writer/main.py" "\$@"
EOF
chmod +x "$APPDIR/AppRun"

# --- Passo 5: Baixar e executar o linuxdeploy ---
echo ">>> Baixando e executando o linuxdeploy..."

# Baixa o linuxdeploy e o plugin GTK (com links corrigidos)
wget -c "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
# CORREÇÃO: Link para uma versão estável do plugin GTK
wget -c "https://github.com/linuxdeploy/linuxdeploy-plugin-gtk/releases/download/v3/linuxdeploy-plugin-gtk-x86_64.AppImage"
chmod +x linuxdeploy*.AppImage

# CORREÇÃO: Exporta o caminho das bibliotecas do sistema para ajudar o linuxdeploy a encontrá-las
export LD_LIBRARY_PATH=/usr/lib

# Executa o linuxdeploy para empacotar tudo
./linuxdeploy-x86_64.AppImage \
    --appdir "$APPDIR" \
    --plugin gtk \
    --output appimage \
    --desktop-file "$DESKTOP_PATH" \
    --icon-file "$ICON_PATH"

# Renomeia o arquivo final
mv "${LOWER_APP_NAME}"*.AppImage "${APP}-${VERSION}-x86_64.AppImage"

echo "### Processo concluído! ###"
echo "AppImage criado: ${APP}-${VERSION}-x86_64.AppImage"

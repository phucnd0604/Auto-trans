[app]
title = AutoTrans
project_dir = .
input_file = main.py
exec_directory = dist
project_file = pyproject.toml
icon = E:\GameDownload\AutoTrans\.venv\Lib\site-packages\PySide6\scripts\deploy_lib\pyside_icon.ico

[python]
python_path = E:\GameDownload\AutoTrans\.venv\Scripts\python.exe
packages = Nuitka==2.7.11
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]
qml_files = 
excluded_qml_plugins = 
modules = Widgets,Gui,Core
plugins = 

[android]
wheel_pyside = 
wheel_shiboken = 
plugins = 

[nuitka]
macos.permissions = 
mode = standalone
extra_args = --quiet --noinclude-qt-translations --include-package=autotrans --nofollow-import-to=torch --nofollow-import-to=quickmt --nofollow-import-to=pytest --nofollow-import-to=tests

[buildozer]
mode = debug
recipe_dir = 
jars_dir = 
ndk_path = 
sdk_path = 
local_libs = 
arch = 


[app]
title = AutoTrans
project_dir = .
input_file = main.py
exec_directory = dist
project_file = pyproject.toml
icon =

[python]
python_path = .venv\Scripts\python.exe
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
mode = onefile
extra_args = --quiet --noinclude-qt-translations --include-package=autotrans

[buildozer]
mode = debug
recipe_dir =
jars_dir =
ndk_path =
sdk_path =
local_libs =
arch =

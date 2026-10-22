[app]
title = Planacity
project_dir = ../..
input_file = packaging/windows/Planacity.py
exec_directory = build/windows
project_file =
icon = build/windows/planacity.ico

[python]
python_path =
packages = Nuitka==4.1.1
android_packages =

[qt]
qml_files =
excluded_qml_plugins =
modules = Core,Gui,Svg,Widgets
plugins = platforminputcontexts

[android]
wheel_pyside =
wheel_shiboken =
plugins =

[nuitka]
macos.permissions =
mode = standalone
extra_args = --quiet --noinclude-qt-translations --include-package-data=planacity --include-distribution-metadata=planacity --windows-console-mode=disable --assume-yes-for-downloads

[buildozer]
mode = debug
recipe_dir =
jars_dir =
ndk_path =
sdk_path =
local_libs =

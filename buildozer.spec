[app]
title = ColorAnalyzer
package.name = coloranalyzer
package.domain = org.local
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,txt
source.exclude_patterns = *.pyc_Decompiled.py,.git/*,.github/*,__pycache__/*,Dockerfile,setup.sh
version = 1.0.0
requirements = python3,kivy,plyer,numpy,opencv-python-headless,pyjnius==1.6.1
orientation = portrait
fullscreen = 0
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.build_tools_version = 34.0.0
android.ndk = 25b

[buildozer]
log_level = 2
warn_on_root = 0

# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'launch.py'
# Bytecode version: 3.12.0rc2 (3531)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

from app import build_ui
if __name__ == '__main__':
    demo = build_ui()
    demo.launch(server_name='0.0.0.0', server_port=7860, share=False, inbrowser=True)
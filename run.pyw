"""자동 시작/무창 실행용 런처.

pythonw.exe로 실행하면 콘솔 창 없이 GUI 팝업만 뜬다.
리포 루트를 sys.path에 넣어 claude_usage_monitor 패키지를 import 한다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from claude_usage_monitor.ui import main

if __name__ == "__main__":
    main()

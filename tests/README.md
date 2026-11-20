# lvparse_tool tests

Run:

    cd path\to\repo-parent
    python -m unittest discover -s lvparse_tool/tests -t . -v

Environment (required for corpus-backed tests):

    LV_GAME=<游戏根目录>
    LV_JP=<明文脚本目录>
    LV_LIB=<lvlib.py 所在目录>
